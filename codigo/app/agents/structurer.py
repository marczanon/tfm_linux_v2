"""Agente estructurador LLM con fallback seguro."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from codigo.app.executors.structuring import DEFAULT_STRUCTURING_CONFIG
from codigo.app.schemas.agent_decisions import StructuringDecision
from codigo.app.schemas.state import StructuringConfig, TFMStateModel
from codigo.app.services.llm import (
    JSONLLMClient,
    LLMCallError,
    LLMMessage,
    get_default_json_llm_client,
)


DEFAULT_FEATURES_PATH = "codigo/data/tensors/cwru_bearing/windows_features.csv"
DEFAULT_TENSORS_PATH = "codigo/data/tensors/cwru_bearing/windows_raw.npz"
DEFAULT_SPLITS_PATH = "codigo/data/tensors/cwru_bearing/splits.json"

SUPPORTED_FEATURES = {
    "mean",
    "std",
    "rms",
    "min",
    "max",
    "peak_to_peak",
    "skewness",
    "kurtosis",
    "crest_factor",
    "energy",
}


def decide_structuring_action(
    state: TFMStateModel,
    *,
    llm_client: JSONLLMClient | None = None,
    use_llm: bool | None = None,
) -> StructuringDecision:
    """Decide ventanas, features y salidas usando LLM cuando este habilitado."""

    should_use_llm = _should_use_llm(llm_client, use_llm)
    if should_use_llm:
        try:
            client = llm_client or get_default_json_llm_client()
            return decide_structuring_action_with_llm(state, client)
        except (LLMCallError, ValidationError, ValueError) as exc:
            fallback = decide_structuring_action_deterministic(state)
            fallback.rationale = f"{fallback.rationale} Fallback after LLM failure: {exc}"
            fallback.confidence = min(fallback.confidence, 0.7)
            return fallback

    return decide_structuring_action_deterministic(state)


def decide_structuring_action_with_llm(
    state: TFMStateModel,
    llm_client: JSONLLMClient,
) -> StructuringDecision:
    """Solicita al LLM una StructuringDecision y valida sus limites."""

    payload = llm_client.complete_json(
        _structurer_messages(state),
        json_schema=StructuringDecision.model_json_schema(),
    )
    decision = StructuringDecision.model_validate(payload)
    _validate_structuring_decision_bounds(state, decision)
    return decision


def decide_structuring_action_deterministic(state: TFMStateModel) -> StructuringDecision:
    """Fallback reproducible para el MVP CWRU."""

    return StructuringDecision(
        decision_id=f"{state.run_id}:structurer:{_structurer_turn(state):03d}",
        rationale=(
            "Fallback CWRU structuring policy: use 2048-sample windows with "
            "50% overlap, binary anomaly labels and time-domain baseline features."
        ),
        confidence=1.0,
        structuring_config=DEFAULT_STRUCTURING_CONFIG,
        expected_features_path=DEFAULT_FEATURES_PATH,
        expected_tensors_path=DEFAULT_TENSORS_PATH,
        expected_splits_path=DEFAULT_SPLITS_PATH,
    )


def _should_use_llm(
    llm_client: JSONLLMClient | None,
    use_llm: bool | None,
) -> bool:
    if use_llm is not None:
        return use_llm
    if llm_client is not None:
        return True
    return os.getenv("TFM_STRUCTURER_MODE", "").strip().lower() == "llm"


def _structurer_messages(state: TFMStateModel) -> list[LLMMessage]:
    return [
        LLMMessage(
            role="system",
            content=(
                "Eres el agente estructurador de un pipeline industrial de "
                "vibracion. Tu tarea es decidir ventanas, solapamiento y "
                "features. No puedes ejecutar codigo ni crear tensores. Debes "
                "devolver exclusivamente un objeto JSON compatible con "
                "StructuringDecision."
            ),
        ),
        LLMMessage(
            role="user",
            content="\n".join(
                [
                    "Contexto ligero:",
                    json.dumps(_state_summary_for_llm(state), indent=2, ensure_ascii=True),
                    "",
                    "Resumen de senales limpias:",
                    json.dumps(_clean_summary_for_llm(state.clean_path), indent=2, ensure_ascii=True),
                    "",
                    "Formato JSON esperado:",
                    json.dumps(_structurer_json_template(state), indent=2, ensure_ascii=True),
                    "",
                    "Reglas:",
                    "- No incluyas texto fuera del JSON.",
                    "- structuring_config debe validar contra StructuringConfig.",
                    "- window_size debe ser 2048 para el MVP CWRU.",
                    "- overlap debe ser 0.5.",
                    f"- main_channel debe ser {state.project_context.main_channel}.",
                    f"- target_sample_rate_hz debe ser {state.project_context.target_sample_rate_hz}.",
                    "- label_mode debe ser binary_anomaly.",
                    "- features solo puede contener features temporales soportadas.",
                    f"- decision_id debe ser: {state.run_id}:structurer:{_structurer_turn(state):03d}",
                ]
            ),
        ),
    ]


def _structurer_json_template(state: TFMStateModel) -> dict[str, Any]:
    return {
        "agent_name": "structurer",
        "decision_id": f"{state.run_id}:structurer:{_structurer_turn(state):03d}",
        "rationale": "Motivo tecnico breve de la estructuracion propuesta.",
        "confidence": 0.9,
        "structuring_config": {
            "window_size": 2048,
            "overlap": 0.5,
            "main_channel": state.project_context.main_channel,
            "target_sample_rate_hz": state.project_context.target_sample_rate_hz,
            "label_mode": "binary_anomaly",
            "features": list(DEFAULT_STRUCTURING_CONFIG.features),
        },
        "expected_features_path": DEFAULT_FEATURES_PATH,
        "expected_tensors_path": DEFAULT_TENSORS_PATH,
        "expected_splits_path": DEFAULT_SPLITS_PATH,
    }


def _state_summary_for_llm(state: TFMStateModel) -> dict[str, Any]:
    return {
        "thread_id": state.thread_id,
        "run_id": state.run_id,
        "current_stage": state.current_stage,
        "dataset": state.project_context.dataset,
        "objective": state.project_context.objective,
        "main_channel": state.project_context.main_channel,
        "target_sample_rate_hz": state.project_context.target_sample_rate_hz,
        "clean_path": state.clean_path,
        "cleaning_config": (
            None
            if state.cleaning_config is None
            else state.cleaning_config.model_dump(mode="json")
        ),
        "dataset_profile": (
            None
            if state.dataset_profile is None
            else state.dataset_profile.model_dump(mode="json")
        ),
    }


def _clean_summary_for_llm(clean_path: str | None) -> dict[str, Any]:
    if not clean_path:
        return {"available": False}
    clean_dir = Path(clean_path)
    if not clean_dir.exists():
        return {"available": False, "path": clean_path}

    files = sorted(clean_dir.glob("*.npz"))
    return {
        "available": True,
        "path": clean_path,
        "n_clean_files": len(files),
        "sample_files": [path.name for path in files[:5]],
    }


def _validate_structuring_decision_bounds(
    state: TFMStateModel,
    decision: StructuringDecision,
) -> None:
    config = decision.structuring_config
    expected_rate = state.project_context.target_sample_rate_hz
    if config.target_sample_rate_hz != expected_rate:
        raise ValueError(f"target_sample_rate_hz must be {expected_rate}")
    if config.main_channel != state.project_context.main_channel:
        raise ValueError(f"main_channel must be {state.project_context.main_channel}")
    if config.label_mode != "binary_anomaly":
        raise ValueError("label_mode must be binary_anomaly for the MVP")
    if config.window_size != 2048:
        raise ValueError("window_size must be 2048 for the MVP")
    if config.overlap != 0.5:
        raise ValueError("overlap must be 0.5 for the MVP")
    if not decision.expected_features_path or not decision.expected_splits_path:
        raise ValueError("expected feature and split paths are required")
    _validate_supported_features(config)


def _validate_supported_features(config: StructuringConfig) -> None:
    unsupported = sorted(set(config.features) - SUPPORTED_FEATURES)
    if unsupported:
        raise ValueError(f"unsupported features: {', '.join(unsupported)}")


def _structurer_turn(state: TFMStateModel) -> int:
    return 1 + sum(message.name == "structurer" for message in state.messages)
