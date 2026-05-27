"""Agente estructurador LLM con fallback seguro."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from codigo.app.executors.structuring import (
    DEFAULT_STRUCTURING_CONFIG,
    SUPPORTED_OVERLAPS,
    SUPPORTED_WINDOW_SIZES,
    TIME_DOMAIN_FULL_FEATURES,
    build_structuring_decision_summary,
)
from codigo.app.schemas.agent_decisions import StructuringDecision
from codigo.app.schemas.state import StructuringConfig, TFMStateModel
from codigo.app.services.llm import (
    JSONLLMClient,
    LLMCallError,
    LLMMessage,
    get_default_json_llm_client,
)


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
    """Fallback reproducible para estructuracion local controlada."""

    return StructuringDecision(
        decision_id=f"{state.run_id}:structurer:{_structurer_turn(state):03d}",
        rationale=(
            "Fallback structuring policy: use 2048-sample windows with 50% "
            "overlap and supported time-domain features."
        ),
        confidence=1.0,
        structuring_config=_default_structuring_config_for_state(state),
        expected_features_path=_default_features_path(state),
        expected_tensors_path=_default_tensors_path(state),
        expected_splits_path=_default_splits_path(state),
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
                    json.dumps(_clean_summary_for_llm(state), indent=2, ensure_ascii=True),
                    "",
                    "Formato JSON esperado:",
                    json.dumps(_structurer_json_template(state), indent=2, ensure_ascii=True),
                    "",
                    "Reglas:",
                    "- No incluyas texto fuera del JSON.",
                    "- structuring_config debe validar contra StructuringConfig.",
                    f"- window_size debe estar en {list(SUPPORTED_WINDOW_SIZES)}.",
                    f"- overlap debe estar en {list(SUPPORTED_OVERLAPS)}.",
                    f"- main_channel debe ser {state.project_context.main_channel}.",
                    f"- target_sample_rate_hz debe ser {state.project_context.target_sample_rate_hz}.",
                    "- label_mode debe ser binary_anomaly o fault_type.",
                    "- features solo puede contener features temporales soportadas.",
                    (
                        "- Usa una candidate_configuration soportada cuando el "
                        "resumen la incluya."
                    ),
                    (
                        "- Si hay varias candidate_configurations viables, "
                        "rellena comparison_candidates con 1 a 3 alternativas "
                        "comparables y justifica el trade-off de cada una."
                    ),
                    (
                        "- No inventes alternativas: cada comparison_candidate "
                        "debe respetar las mismas reglas que structuring_config."
                    ),
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
            "features": list(TIME_DOMAIN_FULL_FEATURES),
        },
        "expected_features_path": _default_features_path(state),
        "expected_tensors_path": _default_tensors_path(state),
        "expected_splits_path": _default_splits_path(state),
        "comparison_candidates": [
            {
                "alternative_id": "win_1024_ov_50",
                "structuring_config": {
                    "window_size": 1024,
                    "overlap": 0.5,
                    "main_channel": state.project_context.main_channel,
                    "target_sample_rate_hz": state.project_context.target_sample_rate_hz,
                    "label_mode": "binary_anomaly",
                    "features": list(TIME_DOMAIN_FULL_FEATURES),
                },
                "rationale": "Alternativa con mayor resolucion temporal.",
                "expected_effect": "Aumentar ventanas disponibles y sensibilidad temporal.",
            },
            {
                "alternative_id": "win_4096_ov_50",
                "structuring_config": {
                    "window_size": 4096,
                    "overlap": 0.5,
                    "main_channel": state.project_context.main_channel,
                    "target_sample_rate_hz": state.project_context.target_sample_rate_hz,
                    "label_mode": "binary_anomaly",
                    "features": list(TIME_DOMAIN_FULL_FEATURES),
                },
                "rationale": "Alternativa con mas contexto por ventana.",
                "expected_effect": "Reducir ruido local a costa de menos ventanas.",
            },
        ],
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


def _clean_summary_for_llm(state: TFMStateModel) -> dict[str, Any]:
    if not state.clean_path:
        return {"available": False}
    clean_dir = Path(state.clean_path)
    if not clean_dir.exists():
        return {"available": False, "path": state.clean_path}

    files = sorted(clean_dir.glob("*.npz"))
    return {
        "available": True,
        "path": state.clean_path,
        "n_clean_files": len(files),
        "sample_files": [path.name for path in files[:5]],
        "decision_summary": build_structuring_decision_summary(
            clean_dir,
            dataset=state.project_context.dataset,
            target_sample_rate_hz=state.project_context.target_sample_rate_hz,
            main_channel=state.project_context.main_channel,
        ),
    }


def _validate_structuring_decision_bounds(
    state: TFMStateModel,
    decision: StructuringDecision,
) -> None:
    _validate_structuring_config_bounds(state, decision.structuring_config)
    if not decision.expected_features_path or not decision.expected_splits_path:
        raise ValueError("expected feature and split paths are required")
    for candidate in decision.comparison_candidates:
        _validate_structuring_config_bounds(state, candidate.structuring_config)


def _validate_structuring_config_bounds(
    state: TFMStateModel,
    config: StructuringConfig,
) -> None:
    expected_rate = state.project_context.target_sample_rate_hz
    if config.target_sample_rate_hz != expected_rate:
        raise ValueError(f"target_sample_rate_hz must be {expected_rate}")
    if config.main_channel != state.project_context.main_channel:
        raise ValueError(f"main_channel must be {state.project_context.main_channel}")
    if config.window_size not in SUPPORTED_WINDOW_SIZES:
        raise ValueError(
            f"window_size must be one of {', '.join(map(str, SUPPORTED_WINDOW_SIZES))}"
        )
    if config.overlap not in SUPPORTED_OVERLAPS:
        raise ValueError(
            f"overlap must be one of {', '.join(map(str, SUPPORTED_OVERLAPS))}"
        )
    _validate_supported_features(config)


def _validate_supported_features(config: StructuringConfig) -> None:
    unsupported = sorted(set(config.features) - SUPPORTED_FEATURES)
    if unsupported:
        raise ValueError(f"unsupported features: {', '.join(unsupported)}")


def _default_structuring_config_for_state(state: TFMStateModel) -> StructuringConfig:
    label_mode = (
        state.project_context.label_mode
        if state.project_context.label_mode in {"binary_anomaly", "fault_type"}
        else "binary_anomaly"
    )
    return StructuringConfig(
        window_size=DEFAULT_STRUCTURING_CONFIG.window_size,
        overlap=DEFAULT_STRUCTURING_CONFIG.overlap,
        main_channel=state.project_context.main_channel,
        target_sample_rate_hz=state.project_context.target_sample_rate_hz,
        label_mode=label_mode,
        features=list(TIME_DOMAIN_FULL_FEATURES),
    )


def _default_features_path(state: TFMStateModel) -> str:
    return f"codigo/data/tensors/{state.project_context.dataset}/windows_features.csv"


def _default_tensors_path(state: TFMStateModel) -> str:
    return f"codigo/data/tensors/{state.project_context.dataset}/windows_raw.npz"


def _default_splits_path(state: TFMStateModel) -> str:
    return f"codigo/data/tensors/{state.project_context.dataset}/splits.json"


def _structurer_turn(state: TFMStateModel) -> int:
    return 1 + sum(message.name == "structurer" for message in state.messages)
