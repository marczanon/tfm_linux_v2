"""Agente limpiador LLM con fallback seguro."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from codigo.app.schemas.agent_decisions import (
    AgentHypothesis,
    CleaningDecision,
    DecisionGenerationTrace,
    require_agent_hypothesis,
)
from codigo.app.schemas.state import CleaningConfig, TFMStateModel
from codigo.app.services.llm import (
    JSONLLMClient,
    LLMCallError,
    LLMMessage,
    get_default_json_llm_client,
)
from codigo.app.services.online_blind import (
    assert_online_blind_payload,
    sanitize_online_blind_payload,
    uses_online_blind_view,
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
        attempt_tracker = [0]
        try:
            client = llm_client or get_default_json_llm_client()
            return decide_cleaning_action_with_llm(
                state,
                client,
                _attempt_tracker=attempt_tracker,
            )
        except (ValidationError, ValueError) as exc:
            fallback = decide_cleaning_action_deterministic(state)
            fallback.rationale = (
                f"{fallback.rationale} Guardrail correction after invalid "
                f"LLM cleaner decision: {exc}"
            )
            fallback.confidence = min(fallback.confidence, 0.82)
            fallback.warnings.append(str(exc))
            failed_attempt_index = max(attempt_tracker[0], 1)
            fallback.generation_trace = DecisionGenerationTrace.for_decision(
                fallback.decision_id,
                origin="guardrail_fallback",
                attempt_index=failed_attempt_index + 1,
                validation_status="fallback_applied",
                fallback_cause=f"{type(exc).__name__}: {exc}",
                fallback_from_attempt_index=failed_attempt_index,
            )
            return fallback
        except LLMCallError as exc:
            fallback = decide_cleaning_action_deterministic(state)
            fallback.rationale = f"{fallback.rationale} Fallback after LLM failure: {exc}"
            fallback.confidence = min(fallback.confidence, 0.7)
            fallback.warnings.append(str(exc))
            failed_attempt_index = max(attempt_tracker[0], 1)
            fallback.generation_trace = DecisionGenerationTrace.for_decision(
                fallback.decision_id,
                origin="guardrail_fallback",
                attempt_index=failed_attempt_index + 1,
                validation_status="fallback_applied",
                fallback_cause=f"{type(exc).__name__}: {exc}",
                fallback_from_attempt_index=failed_attempt_index,
            )
            return fallback

    return decide_cleaning_action_deterministic(state)


def decide_cleaning_action_with_llm(
    state: TFMStateModel,
    llm_client: JSONLLMClient,
    *,
    _attempt_tracker: list[int] | None = None,
) -> CleaningDecision:
    """Solicita al LLM una CleaningDecision y valida sus limites."""

    attempt_tracker = _attempt_tracker if _attempt_tracker is not None else [0]
    messages = _cleaner_messages(state)
    schema = CleaningDecision.model_json_schema()
    attempt_tracker[0] = 1
    payload = llm_client.complete_json(
        messages,
        json_schema=schema,
    )
    try:
        decision = _validated_cleaning_decision_from_payload(state, payload)
    except (ValidationError, ValueError) as exc:
        attempt_tracker[0] = 2
        repaired_payload = llm_client.complete_json(
            _cleaner_contract_repair_messages(
                state,
                messages,
                invalid_payload=payload,
                validation_error=exc,
            ),
            json_schema=schema,
        )
        decision = _validated_cleaning_decision_from_payload(
            state,
            repaired_payload,
        )
        decision.generation_trace = DecisionGenerationTrace.for_decision(
            decision.decision_id,
            origin="llm",
            attempt_index=2,
            validation_status="repaired",
        )
        return decision
    decision.generation_trace = DecisionGenerationTrace.for_decision(
        decision.decision_id,
        origin="llm",
    )
    return decision


def _validated_cleaning_decision_from_payload(
    state: TFMStateModel,
    payload: dict[str, Any],
) -> CleaningDecision:
    trusted_payload = _with_server_owned_cleaning_envelope(state, payload)
    decision = CleaningDecision.model_validate(trusted_payload)
    _validate_cleaning_decision_bounds(state, decision)
    return decision


def _with_server_owned_cleaning_envelope(
    state: TFMStateModel,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Impone metadatos y rutas que no forman parte del razonamiento LLM."""

    trusted_payload = dict(payload)
    trusted_payload.pop("created_at", None)
    trusted_payload.pop("generation_trace", None)
    trusted_payload["agent_name"] = "cleaner"
    trusted_payload["decision_id"] = (
        f"{state.run_id}:cleaner:{_cleaner_turn(state):03d}"
    )
    trusted_payload["expected_artifact_path"] = _default_clean_output_path(state)
    return trusted_payload


def _cleaner_contract_repair_messages(
    state: TFMStateModel,
    original_messages: list[LLMMessage],
    *,
    invalid_payload: dict[str, Any],
    validation_error: Exception,
) -> list[LLMMessage]:
    rules = [
        "La decision anterior no valida contra los guardarrails del cleaner.",
        f"Error de validacion: {validation_error}",
        "Corrige solo lo necesario y reemite un unico objeto JSON valido.",
        (
            "agent_name, decision_id y expected_artifact_path son metadatos "
            "server-owned; el servidor impondrá sus valores canónicos."
        ),
        "No ejecutes codigo ni afirmes haber transformado los datos.",
        (
            "Incluye hypothesis con kind=data_quality, alcance, corte de evidencia, "
            "observacion esperada y criterio de refutacion."
        ),
        "remove_non_finite debe permanecer true.",
        f"resample_to_hz debe ser {state.project_context.target_sample_rate_hz}.",
        "normalization solo puede ser none, zscore o robust.",
        (
            "selected_channel debe ser null o corresponder al canal principal/"
            "perfil disponible."
        ),
    ]
    if uses_online_blind_view(state):
        rules.extend(
            [
                "Esta es una decision online_blind: usa solo el perfil basal visible.",
                (
                    "No introduzcas resultados de monitoring, fallo, lead time, "
                    "time_to_failure, relative_life ni RUL."
                ),
            ]
        )
    rules.append("No incluyas texto fuera del JSON.")
    return [
        *original_messages,
        LLMMessage(
            role="assistant",
            content=json.dumps(invalid_payload, indent=2, ensure_ascii=True),
        ),
        LLMMessage(role="user", content="\n".join(rules)),
    ]


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
        hypothesis=_cleaner_hypothesis(state),
        generation_trace=DecisionGenerationTrace.for_decision(
            f"{state.run_id}:cleaner:{_cleaner_turn(state):03d}",
            origin="deterministic",
        ),
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
    profile_summary = _profile_summary_for_llm(
        state.profile_path,
        online_blind=uses_online_blind_view(state),
    )
    temporal_context = _temporal_context_for_llm(state)
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
                    "Contexto temporal del perfil:",
                    json.dumps(temporal_context, indent=2, ensure_ascii=True),
                    "",
                    "Resumen del perfil:",
                    json.dumps(profile_summary, indent=2, ensure_ascii=True),
                    "",
                    "Formato JSON esperado:",
                    json.dumps(_cleaner_json_template(state), indent=2, ensure_ascii=True),
                    "",
                    "Reglas:",
                    "- No incluyas texto fuera del JSON.",
                    (
                        "- agent_name, decision_id y expected_artifact_path son "
                        "campos informativos server-owned; el servidor impondrá "
                        "los valores mostrados en la plantilla."
                    ),
                    "- cleaning_config debe validar contra CleaningConfig.",
                    (
                        "- hypothesis debe formular una hipotesis de calidad "
                        "contrastable; no una conclusion ya observada."
                    ),
                    "- strategy_id debe ser no vacio.",
                    f"- resample_to_hz debe ser {state.project_context.target_sample_rate_hz}.",
                    (
                        "- selected_channel puede ser null o un canal declarado en "
                        "el manifiesto/perfil."
                    ),
                    "- normalization debe ser 'none', 'zscore' o 'robust'.",
                    (
                        "- Si supervision_profile es run_to_failure_degradation, "
                        "tu rationale debe considerar continuidad temporal, canal "
                        "y estabilidad del score posterior."
                    ),
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
        "hypothesis": _cleaner_hypothesis(state).model_dump(mode="json"),
        "cleaning_config": {
            "strategy_id": f"{state.project_context.dataset}_clean_llm_v1",
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
        "objective": state.project_context.objective,
        "label_mode": state.project_context.label_mode,
        "supervision_profile": state.project_context.supervision_profile,
        "label_source": state.project_context.label_source,
        "label_granularity": state.project_context.label_granularity,
        "main_channel": state.project_context.main_channel,
        "target_sample_rate_hz": state.project_context.target_sample_rate_hz,
        "manifest_path": state.manifest_path,
        "profile_path": state.profile_path,
    }


def _temporal_context_for_llm(state: TFMStateModel) -> dict[str, Any]:
    return {
        "role": "signal_quality_gate_for_temporal_monitoring",
        "is_run_to_failure": (
            state.project_context.supervision_profile == "run_to_failure_degradation"
        ),
        "main_channel": state.project_context.main_channel,
        "target_sample_rate_hz": state.project_context.target_sample_rate_hz,
        "label_source": state.project_context.label_source,
        "label_granularity": state.project_context.label_granularity,
        "cleaner_responsibility": (
            "Seleccionar canal, remuestreo y tratamiento de no finitos sin "
            "romper continuidad temporal ni alterar la comparabilidad entre "
            "ventanas."
        ),
        "guardrail": (
            "El cleaner no decide fallos ni RUL; prepara senales fiables para "
            "que modeler/evaluator razonen sobre degradacion."
        ),
    }


def _profile_summary_for_llm(
    profile_path: str | None,
    *,
    online_blind: bool = False,
) -> dict[str, Any]:
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

    payload = {
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
    if not online_blind:
        return payload

    payload = {
        "available": True,
        "dataset": profile.get("dataset"),
        "sample_rates_hz": sorted(
            str(value) for value in (profile.get("sample_rate_counts") or {})
        ),
        "channels_detected": profile.get("channels_detected"),
        "non_finite_count_in_first_files": non_finite_total,
        "channel_sample": channel_sample,
        "evidence_view": "online_blind_baseline_profile",
    }
    payload = sanitize_online_blind_payload(payload)
    assert_online_blind_payload(payload)
    return payload


def _validate_cleaning_decision_bounds(
    state: TFMStateModel,
    decision: CleaningDecision,
) -> None:
    require_agent_hypothesis(
        decision,
        allowed_kinds={"data_quality"},
    )
    if uses_online_blind_view(state):
        assert_online_blind_payload(decision.hypothesis.model_dump(mode="json"))
    config = decision.cleaning_config
    expected_rate = state.project_context.target_sample_rate_hz
    if config.resample_to_hz != expected_rate:
        raise ValueError(f"resample_to_hz must be {expected_rate}")
    if not config.remove_non_finite:
        raise ValueError("remove_non_finite must stay true for the MVP")
    if not decision.expected_artifact_path:
        raise ValueError("expected_artifact_path cannot be empty")
    _validate_supported_cleaning_config(config)


def _cleaner_hypothesis(state: TFMStateModel) -> AgentHypothesis:
    online_blind = uses_online_blind_view(state)
    return AgentHypothesis(
        kind="data_quality",
        statement=(
            "Eliminar valores no finitos y armonizar canal y frecuencia reducira "
            "los defectos observados sin destruir continuidad ni señal util."
        ),
        scope=(
            f"Dataset {state.project_context.dataset}; canal "
            f"{state.project_context.main_channel}; limpieza previa al modelado."
        ),
        evidence_cutoff=(
            "Manifiesto y perfil basal visible; monitoring permanece oculto."
            if online_blind
            else "Manifiesto y perfil estadistico disponibles antes de limpiar."
        ),
        expected_observation=(
            "El artefacto limpio no contiene valores no finitos, conserva el orden "
            "temporal y mantiene una cobertura util al muestreo objetivo."
        ),
        falsification_criterion=(
            "Persisten defectos objetivo, aparecen discontinuidades nuevas o la "
            "retencion y distribucion de la señal cambian sin justificacion."
        ),
        evidence_refs=[
            "manifest:signal_inventory",
            "profile:baseline_summary" if online_blind else "profile:dataset_summary",
        ],
        risk_notes=[
            "Una limpieza excesiva puede borrar cambios de señal relevantes para degradacion."
        ],
        assumptions=[
            "La limpieza no debe usar resultados posteriores para elegir su politica.",
            "La ejecucion determinista medira el efecto; proponerla no demuestra que funcione.",
        ],
    )


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
