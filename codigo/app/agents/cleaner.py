"""Agente limpiador LLM con fallback seguro."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from codigo.app.schemas.agent_decisions import CleaningDecision
from codigo.app.schemas.state import CleaningConfig, TFMStateModel
from codigo.app.services.llm import (
    JSONLLMClient,
    LLMCallError,
    LLMMessage,
    get_default_json_llm_client,
)


def decide_cleaning_action(
    state: TFMStateModel,
    *,
    llm_client: JSONLLMClient | None = None,
    use_llm: bool | None = None,
) -> CleaningDecision:
    """Decide la configuracion de limpieza usando LLM cuando este habilitado."""

    should_use_llm = _should_use_llm(llm_client, use_llm)
    if should_use_llm:
        try:
            client = llm_client or get_default_json_llm_client()
            return decide_cleaning_action_with_llm(state, client)
        except (LLMCallError, ValidationError, ValueError) as exc:
            fallback = decide_cleaning_action_deterministic(state)
            fallback.rationale = f"{fallback.rationale} Fallback after LLM failure: {exc}"
            fallback.confidence = min(fallback.confidence, 0.7)
            fallback.warnings.append(str(exc))
            return fallback

    return decide_cleaning_action_deterministic(state)


def decide_cleaning_action_with_llm(
    state: TFMStateModel,
    llm_client: JSONLLMClient,
) -> CleaningDecision:
    """Solicita al LLM una CleaningDecision y valida sus limites."""

    payload = llm_client.complete_json(
        _cleaner_messages(state),
        json_schema=CleaningDecision.model_json_schema(),
    )
    decision = CleaningDecision.model_validate(payload)
    _validate_cleaning_decision_bounds(state, decision)
    return decision


def decide_cleaning_action_deterministic(state: TFMStateModel) -> CleaningDecision:
    """Fallback reproducible para limpieza local controlada."""

    return CleaningDecision(
        decision_id=f"{state.run_id}:cleaner:{_cleaner_turn(state):03d}",
        rationale=(
            "Fallback cleaning policy: remove non-finite values, resample to "
            "the target sample rate, select the configured main channel and avoid "
            "normalization before baseline modeling."
        ),
        confidence=1.0,
        cleaning_config=_default_cleaning_config_for_state(state),
        expected_artifact_path=_default_clean_output_path(state),
        warnings=[],
    )


def _should_use_llm(
    llm_client: JSONLLMClient | None,
    use_llm: bool | None,
) -> bool:
    if use_llm is not None:
        return use_llm
    if llm_client is not None:
        return True
    return os.getenv("TFM_CLEANER_MODE", "").strip().lower() == "llm"


def _cleaner_messages(state: TFMStateModel) -> list[LLMMessage]:
    profile_summary = _profile_summary_for_llm(state.profile_path)
    return [
        LLMMessage(
            role="system",
            content=(
                "Eres el agente limpiador de un pipeline industrial. Tu tarea "
                "es proponer una configuracion de limpieza segura y reproducible. "
                "No puedes ejecutar codigo ni transformar datos. Debes devolver "
                "exclusivamente un objeto JSON compatible con CleaningDecision."
            ),
        ),
        LLMMessage(
            role="user",
            content="\n".join(
                [
                    "Contexto ligero:",
                    json.dumps(_state_summary_for_llm(state), indent=2, ensure_ascii=True),
                    "",
                    "Resumen del perfil:",
                    json.dumps(profile_summary, indent=2, ensure_ascii=True),
                    "",
                    "Formato JSON esperado:",
                    json.dumps(_cleaner_json_template(state), indent=2, ensure_ascii=True),
                    "",
                    "Reglas:",
                    "- No incluyas texto fuera del JSON.",
                    "- cleaning_config debe validar contra CleaningConfig.",
                    "- strategy_id debe ser no vacio.",
                    f"- resample_to_hz debe ser {state.project_context.target_sample_rate_hz}.",
                    (
                        "- selected_channel puede ser null o un canal declarado en "
                        "el manifiesto/perfil."
                    ),
                    "- normalization debe ser 'none', 'zscore' o 'robust'.",
                    (
                        "- expected_artifact_path debe apuntar al directorio de "
                        "senales limpias del dataset."
                    ),
                    f"- decision_id debe ser: {state.run_id}:cleaner:{_cleaner_turn(state):03d}",
                ]
            ),
        ),
    ]


def _cleaner_json_template(state: TFMStateModel) -> dict[str, Any]:
    return {
        "agent_name": "cleaner",
        "decision_id": f"{state.run_id}:cleaner:{_cleaner_turn(state):03d}",
        "rationale": "Motivo tecnico breve de la limpieza propuesta.",
        "confidence": 0.9,
        "cleaning_config": {
            "strategy_id": "cwru_clean_llm_v1",
            "remove_non_finite": True,
            "resample_to_hz": state.project_context.target_sample_rate_hz,
            "normalization": "none",
            "selected_channel": state.project_context.main_channel,
            "audit_log_path": (
                f"codigo/data/processed/{state.project_context.dataset}/"
                "cleaning_summary.json"
            ),
        },
        "expected_artifact_path": _default_clean_output_path(state),
        "warnings": [],
    }


def _state_summary_for_llm(state: TFMStateModel) -> dict[str, Any]:
    return {
        "thread_id": state.thread_id,
        "run_id": state.run_id,
        "current_stage": state.current_stage,
        "dataset": state.project_context.dataset,
        "main_channel": state.project_context.main_channel,
        "target_sample_rate_hz": state.project_context.target_sample_rate_hz,
        "manifest_path": state.manifest_path,
        "profile_path": state.profile_path,
    }


def _profile_summary_for_llm(profile_path: str | None) -> dict[str, Any]:
    if not profile_path or not Path(profile_path).exists():
        return {"available": False}

    profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    files = profile.get("files", [])
    non_finite_total = 0
    channel_sample = {}
    for item in files[:5]:
        channels = item.get("channels", {})
        for name, stats in channels.items():
            non_finite_total += int(stats.get("non_finite_count") or 0)
            channel_sample.setdefault(
                name,
                {
                    "n_samples": stats.get("n_samples"),
                    "non_finite_count": stats.get("non_finite_count"),
                    "mean": stats.get("mean"),
                    "std": stats.get("std"),
                    "rms": stats.get("rms"),
                },
            )

    return {
        "available": True,
        "dataset": profile.get("dataset"),
        "n_files": profile.get("n_files"),
        "label_counts": profile.get("label_counts"),
        "sample_rate_counts": profile.get("sample_rate_counts"),
        "channels_detected": profile.get("channels_detected"),
        "decision_summary": profile.get("decision_summary"),
        "non_finite_count_in_first_files": non_finite_total,
        "channel_sample": channel_sample,
    }


def _validate_cleaning_decision_bounds(
    state: TFMStateModel,
    decision: CleaningDecision,
) -> None:
    config = decision.cleaning_config
    expected_rate = state.project_context.target_sample_rate_hz
    if config.resample_to_hz != expected_rate:
        raise ValueError(f"resample_to_hz must be {expected_rate}")
    if not config.remove_non_finite:
        raise ValueError("remove_non_finite must stay true for the MVP")
    if not decision.expected_artifact_path:
        raise ValueError("expected_artifact_path cannot be empty")
    _validate_supported_cleaning_config(config)


def _validate_supported_cleaning_config(config: CleaningConfig) -> None:
    if config.normalization not in {"none", "zscore", "robust"}:
        raise ValueError(f"unsupported normalization: {config.normalization}")


def _default_cleaning_config_for_state(state: TFMStateModel) -> CleaningConfig:
    if state.project_context.dataset == "cwru_bearing":
        strategy_id = "cwru_clean_v1"
    else:
        strategy_id = f"{state.project_context.dataset}_clean_v1"
    return CleaningConfig(
        strategy_id=strategy_id,
        remove_non_finite=True,
        resample_to_hz=state.project_context.target_sample_rate_hz,
        normalization="none",
        selected_channel=state.project_context.main_channel,
        audit_log_path=(
            f"codigo/data/processed/{state.project_context.dataset}/"
            "cleaning_summary.json"
        ),
    )


def _default_clean_output_path(state: TFMStateModel) -> str:
    return f"codigo/data/processed/{state.project_context.dataset}/clean_signals"


def _cleaner_turn(state: TFMStateModel) -> int:
    return 1 + sum(message.name == "cleaner" for message in state.messages)
