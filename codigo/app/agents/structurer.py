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
from codigo.app.schemas.agent_decisions import (
    AgentHypothesis,
    DecisionGenerationTrace,
    StructuringDecision,
    require_agent_hypothesis,
)
from codigo.app.schemas.reasoning import AgentMemoryQuery, RetrievedMemoryContext
from codigo.app.schemas.state import StructuringConfig, TFMStateModel
from codigo.app.services.agent_memory import (
    memory_context_for_llm,
    memory_usage_json_template,
    validate_retrieved_memory_usage,
)
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
from codigo.app.services.vector_memory import VectorMemoryStore


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
    memory_context: RetrievedMemoryContext | None = None,
    llm_client: JSONLLMClient | None = None,
    use_llm: bool | None = None,
) -> StructuringDecision:
    """Decide ventanas, features y salidas usando LLM cuando este habilitado."""

    should_use_llm = _should_use_llm(llm_client, use_llm)
    if should_use_llm:
        attempt_tracker = [0]
        try:
            client = llm_client or get_default_json_llm_client()
            return decide_structuring_action_with_llm(
                state,
                client,
                memory_context=memory_context,
                _attempt_tracker=attempt_tracker,
            )
        except (ValidationError, ValueError) as exc:
            fallback = decide_structuring_action_deterministic(state)
            fallback.rationale = (
                f"{fallback.rationale} Guardrail correction after invalid "
                f"LLM structurer decision: {exc}"
            )
            fallback.confidence = min(fallback.confidence, 0.82)
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
            fallback = decide_structuring_action_deterministic(state)
            fallback.rationale = f"{fallback.rationale} Fallback after LLM failure: {exc}"
            fallback.confidence = min(fallback.confidence, 0.7)
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

    return decide_structuring_action_deterministic(state)


def decide_structuring_action_with_llm(
    state: TFMStateModel,
    llm_client: JSONLLMClient,
    *,
    memory_context: RetrievedMemoryContext | None = None,
    _attempt_tracker: list[int] | None = None,
) -> StructuringDecision:
    """Solicita al LLM una StructuringDecision y valida sus limites."""

    attempt_tracker = _attempt_tracker if _attempt_tracker is not None else [0]
    messages = _structurer_messages(state, memory_context=memory_context)
    schema = StructuringDecision.model_json_schema()
    attempt_tracker[0] = 1
    payload = llm_client.complete_json(
        messages,
        json_schema=schema,
    )
    try:
        decision = _validated_structuring_decision_from_payload(
            state,
            payload,
            memory_context=memory_context,
        )
    except (ValidationError, ValueError) as exc:
        attempt_tracker[0] = 2
        repaired_payload = llm_client.complete_json(
            _structurer_contract_repair_messages(
                state,
                messages,
                invalid_payload=payload,
                validation_error=exc,
                memory_context=memory_context,
            ),
            json_schema=schema,
        )
        decision = _validated_structuring_decision_from_payload(
            state,
            repaired_payload,
            memory_context=memory_context,
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


def _validated_structuring_decision_from_payload(
    state: TFMStateModel,
    payload: dict[str, Any],
    *,
    memory_context: RetrievedMemoryContext | None = None,
) -> StructuringDecision:
    trusted_payload = _with_server_owned_structuring_envelope(state, payload)
    decision = StructuringDecision.model_validate(trusted_payload)
    _validate_structuring_decision_bounds(
        state,
        decision,
        memory_context=memory_context,
    )
    return decision


def _with_server_owned_structuring_envelope(
    state: TFMStateModel,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Impone identidad, rutas y ausencia de restricciones experimentales."""

    trusted_payload = dict(payload)
    trusted_payload.pop("created_at", None)
    trusted_payload.pop("generation_trace", None)
    trusted_payload.pop("protocol_trace", None)
    trusted_payload["agent_name"] = "structurer"
    trusted_payload["decision_id"] = (
        f"{state.run_id}:structurer:{_structurer_turn(state):03d}"
    )
    config_payload = trusted_payload.get("structuring_config")
    if isinstance(config_payload, dict):
        trusted_payload["structuring_config"] = {
            **config_payload,
            "label_mode": state.project_context.label_mode,
        }
    candidates = trusted_payload.get("comparison_candidates")
    if isinstance(candidates, list):
        trusted_payload["comparison_candidates"] = [
            {
                **candidate,
                "structuring_config": {
                    **candidate["structuring_config"],
                    "label_mode": state.project_context.label_mode,
                },
            }
            if isinstance(candidate, dict)
            and isinstance(candidate.get("structuring_config"), dict)
            else candidate
            for candidate in candidates
        ]
    trusted_payload["expected_features_path"] = _default_features_path(state)
    trusted_payload["expected_tensors_path"] = _default_tensors_path(state)
    trusted_payload["expected_splits_path"] = _default_splits_path(state)
    return trusted_payload


def _structurer_contract_repair_messages(
    state: TFMStateModel,
    original_messages: list[LLMMessage],
    *,
    invalid_payload: dict[str, Any],
    validation_error: Exception,
    memory_context: RetrievedMemoryContext | None = None,
) -> list[LLMMessage]:
    rules = [
        "La decision anterior no valida contra los guardarrails del structurer.",
        f"Error de validacion: {validation_error}",
        "Corrige solo lo necesario y reemite un unico objeto JSON valido.",
        (
            "agent_name, decision_id y las rutas expected_* son metadatos "
            "server-owned; el servidor impondrá sus valores canónicos."
        ),
        "No ejecutes codigo ni afirmes haber generado features o tensores.",
        (
            "Incluye hypothesis con kind=temporal_representation y un criterio "
            "explicito de fuga, insuficiencia o degeneracion que pueda refutarla."
        ),
        f"window_size debe estar en {list(SUPPORTED_WINDOW_SIZES)}.",
        f"overlap debe estar en {list(SUPPORTED_OVERLAPS)}.",
        f"main_channel debe ser {state.project_context.main_channel}.",
        (
            "target_sample_rate_hz debe ser "
            f"{state.project_context.target_sample_rate_hz}."
        ),
        "features y alternativas deben respetar exactamente los limites soportados.",
        (
            "La memoria no puede relajar ventanas, solapes, canal, frecuencia, "
            "features ni particiones soportadas."
        ),
        "Declaracion de memoria esperada:",
        json.dumps(
            memory_usage_json_template(memory_context),
            indent=2,
            ensure_ascii=True,
        ),
        (
            "Si used_memory_context=true, cita solo memory_record_id recuperados "
            "y describe exactamente cada cita en memory_record_uses."
        ),
    ]
    if uses_online_blind_view(state):
        rules.extend(
            [
                (
                    "Esta es una decision online_blind: usa solo baseline train "
                    "y calibration validation; monitoring/test permanece oculto."
                ),
                (
                    "No introduzcas fallo, lead time, time_to_failure, "
                    "relative_life, RUL ni resultados retrospectivos."
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


def decide_structuring_action_deterministic(state: TFMStateModel) -> StructuringDecision:
    """Fallback reproducible para estructuracion local controlada."""

    return StructuringDecision(
        decision_id=f"{state.run_id}:structurer:{_structurer_turn(state):03d}",
        rationale=(
            "Fallback structuring policy: use 2048-sample windows with 50% "
            "overlap and supported time-domain features."
        ),
        confidence=1.0,
        hypothesis=_structurer_hypothesis(state),
        generation_trace=DecisionGenerationTrace.for_decision(
            f"{state.run_id}:structurer:{_structurer_turn(state):03d}",
            origin="deterministic",
        ),
        structuring_config=_default_structuring_config_for_state(state),
        expected_features_path=_default_features_path(state),
        expected_tensors_path=_default_tensors_path(state),
        expected_splits_path=_default_splits_path(state),
    )


def build_structurer_memory_query(
    state: TFMStateModel,
    *,
    top_k: int = 3,
    min_similarity: float = 0.0,
) -> AgentMemoryQuery:
    """Construye una consulta RAG para decisiones de estructuracion."""

    clean_summary = _clean_summary_for_llm(state)
    query_text = "\n".join(
        [
            "Structurer decision for industrial vibration anomaly detection.",
            f"Dataset: {state.project_context.dataset}",
            f"Data provenance: {state.project_context.data_provenance}",
            f"Objective: {state.project_context.objective}",
            f"Main channel: {state.project_context.main_channel}",
            f"Target sample rate: {state.project_context.target_sample_rate_hz}",
            f"Clean summary: {json.dumps(clean_summary, ensure_ascii=True)}",
            (
                "Need prior lessons about window size, overlap, feature set, "
                "temporal splits and dataset-specific structuring trade-offs."
            ),
        ]
    )
    return AgentMemoryQuery(
        query_id=f"{state.run_id}:structurer:{_structurer_turn(state):03d}:memory_query",
        target_agent="structurer",
        query_text=query_text,
        dataset=state.project_context.dataset,
        data_provenance=state.project_context.data_provenance,
        run_id=state.run_id,
        decision_id=f"{state.run_id}:structurer:{_structurer_turn(state):03d}",
        decision_context={
            **state.project_context.to_memory_applicability().model_dump(
                mode="python"
            ),
            "current_stage": state.current_stage,
            "main_channel": state.project_context.main_channel,
            "data_provenance": state.project_context.data_provenance,
            "has_clean_path": bool(state.clean_path),
        },
        allowed_memory_roles=[
            "positive_example",
            "negative_example",
            "boundary_case",
            "warning",
            "methodology",
            "evidence",
        ],
        top_k=top_k,
        min_similarity=min_similarity,
    )


def retrieve_structurer_memory_context(
    state: TFMStateModel,
    *,
    memory_store: VectorMemoryStore,
    top_k: int = 3,
    min_similarity: float = 0.0,
) -> RetrievedMemoryContext:
    """Recupera memoria supervisada para el agente estructurador."""

    query = build_structurer_memory_query(
        state,
        top_k=top_k,
        min_similarity=min_similarity,
    )
    return memory_store.query(query)


def _should_use_llm(
    llm_client: JSONLLMClient | None,
    use_llm: bool | None,
) -> bool:
    if use_llm is not None:
        return use_llm
    if llm_client is not None:
        return True
    return os.getenv("TFM_STRUCTURER_MODE", "").strip().lower() == "llm"


def _structurer_messages(
    state: TFMStateModel,
    *,
    memory_context: RetrievedMemoryContext | None = None,
) -> list[LLMMessage]:
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
                    "Memoria recuperada para el estructurador:",
                    json.dumps(
                        memory_context_for_llm(
                            memory_context,
                            online_blind=uses_online_blind_view(state),
                        ),
                        indent=2,
                        ensure_ascii=True,
                    ),
                    "",
                    "Formato JSON esperado:",
                    json.dumps(
                        _structurer_json_template(
                            state,
                            memory_context=memory_context,
                        ),
                        indent=2,
                        ensure_ascii=True,
                    ),
                    "",
                    "Reglas:",
                    "- No incluyas texto fuera del JSON.",
                    (
                        "- agent_name, decision_id y las rutas expected_* son "
                        "campos informativos server-owned; el servidor impondrá "
                        "los valores mostrados en la plantilla."
                    ),
                    "- structuring_config debe validar contra StructuringConfig.",
                    (
                        "- hypothesis debe declarar alcance, corte causal, "
                        "observacion esperada y criterio de refutacion."
                    ),
                    f"- window_size debe estar en {list(SUPPORTED_WINDOW_SIZES)}.",
                    f"- overlap debe estar en {list(SUPPORTED_OVERLAPS)}.",
                    f"- main_channel debe ser {state.project_context.main_channel}.",
                    f"- target_sample_rate_hz debe ser {state.project_context.target_sample_rate_hz}.",
                    (
                        "- label_mode es server-owned y debe corresponder al "
                        f"perfil del dataset: {state.project_context.label_mode}."
                    ),
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
                    (
                        "- La memoria recuperada solo aporta contexto historico; "
                        "no puede saltarse ventanas, solapes, canales ni features "
                        "soportadas."
                    ),
                    (
                        "- Si usas una memoria recuperada, pon "
                        "used_memory_context=true y cita sus memory_record_id."
                    ),
                    (
                        "- Para cada recuerdo citado, rellena memory_record_uses "
                        "explicando si lo sigues, adaptas, contradices o ignoras."
                    ),
                    (
                        "- Si un recuerdo es boundary_case o warning, explica "
                        "como evitas reutilizar fuera de contexto una ventana, "
                        "feature o particion que ya fue problematica."
                    ),
                    (
                        "- Si la memoria no aporta evidencia util para esta "
                        "estructura concreta, declara used_memory_context=false."
                    ),
                ]
            ),
        ),
    ]


def _structurer_json_template(
    state: TFMStateModel,
    *,
    memory_context: RetrievedMemoryContext | None = None,
) -> dict[str, Any]:
    template = {
        "agent_name": "structurer",
        "decision_id": f"{state.run_id}:structurer:{_structurer_turn(state):03d}",
        "rationale": "Motivo tecnico breve de la estructuracion propuesta.",
        "confidence": 0.9,
        "hypothesis": _structurer_hypothesis(state).model_dump(mode="json"),
        "structuring_config": {
            "window_size": 2048,
            "overlap": 0.5,
            "main_channel": state.project_context.main_channel,
            "target_sample_rate_hz": state.project_context.target_sample_rate_hz,
            "label_mode": state.project_context.label_mode,
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
                    "label_mode": state.project_context.label_mode,
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
                    "label_mode": state.project_context.label_mode,
                    "features": list(TIME_DOMAIN_FULL_FEATURES),
                },
                "rationale": "Alternativa con mas contexto por ventana.",
                "expected_effect": "Reducir ruido local a costa de menos ventanas.",
            },
        ],
    }
    template.update(memory_usage_json_template(memory_context))
    return template


def _state_summary_for_llm(state: TFMStateModel) -> dict[str, Any]:
    payload = {
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
    if not uses_online_blind_view(state):
        return payload

    profile = state.dataset_profile
    payload["dataset_profile"] = (
        None
        if profile is None
        else {
            "dataset_name": profile.dataset_name,
            "channels": profile.channels,
            "sample_rates_hz": profile.sample_rates_hz,
        }
    )
    payload["evidence_view"] = "online_blind"
    payload = sanitize_online_blind_payload(payload)
    assert_online_blind_payload(payload)
    return payload


def _clean_summary_for_llm(state: TFMStateModel) -> dict[str, Any]:
    if not state.clean_path:
        return {"available": False}
    clean_dir = Path(state.clean_path)
    if not clean_dir.exists():
        return {"available": False, "path": state.clean_path}

    online_blind = uses_online_blind_view(state)
    files = sorted(clean_dir.glob("*.npz"))
    payload = {
        "available": True,
        "path": state.clean_path,
        "n_clean_files": len(files),
        "sample_files": [path.name for path in files[:5]],
        "decision_summary": build_structuring_decision_summary(
            clean_dir,
            dataset=state.project_context.dataset,
            target_sample_rate_hz=state.project_context.target_sample_rate_hz,
            main_channel=state.project_context.main_channel,
            allowed_split_hints={"train"} if online_blind else None,
        ),
    }
    if not online_blind:
        return payload
    payload.pop("n_clean_files", None)
    payload.pop("sample_files", None)
    payload["evidence_view"] = "online_blind_baseline_only"
    payload = sanitize_online_blind_payload(payload)
    assert_online_blind_payload(payload)
    return payload


def _validate_structuring_decision_bounds(
    state: TFMStateModel,
    decision: StructuringDecision,
    *,
    memory_context: RetrievedMemoryContext | None = None,
) -> None:
    require_agent_hypothesis(
        decision,
        allowed_kinds={"temporal_representation"},
    )
    if uses_online_blind_view(state):
        assert_online_blind_payload(decision.hypothesis.model_dump(mode="json"))
    _validate_structuring_config_bounds(state, decision.structuring_config)
    if not decision.expected_features_path or not decision.expected_splits_path:
        raise ValueError("expected feature and split paths are required")
    for candidate in decision.comparison_candidates:
        _validate_structuring_config_bounds(state, candidate.structuring_config)
    validate_retrieved_memory_usage(
        memory_context=memory_context,
        memory_context_id=decision.memory_context_id,
        used_memory_context=decision.used_memory_context,
        memory_record_ids=decision.memory_record_ids,
        memory_record_uses=decision.memory_record_uses,
    )


def _structurer_hypothesis(state: TFMStateModel) -> AgentHypothesis:
    online_blind = uses_online_blind_view(state)
    return AgentHypothesis(
        kind="temporal_representation",
        statement=(
            "La ventana, el solape, las variables y la particion propuestas "
            "produciran observaciones informativas sin fuga entre grupos ni futuro."
        ),
        scope=(
            f"Dataset {state.project_context.dataset}; canal "
            f"{state.project_context.main_channel}; representacion temporal para "
            f"{state.project_context.supervision_profile}."
        ),
        evidence_cutoff=(
            "Artefacto limpio y baseline visible; calibration se reserva para "
            "calibrar y monitoring permanece oculto."
            if online_blind
            else "Artefacto limpio y metadatos de grupos disponibles antes del split."
        ),
        expected_observation=(
            "Se generan suficientes ventanas finitas y reproducibles, ninguna "
            "cruza fronteras de split y las variables conservan variabilidad util."
        ),
        falsification_criterion=(
            "Existe fuga entre train, validation o monitoring, una ventana cruza "
            "una frontera causal, o la representacion queda insuficiente o degenerada."
        ),
        evidence_refs=[
            "artifact:clean_summary",
            "policy:online_blind_split" if online_blind else "policy:group_aware_split",
        ],
        risk_notes=[
            "El solape puede inflar el numero aparente de muestras sin aportar informacion independiente."
        ],
        assumptions=[
            "Mas ventanas no implican por si solas una representacion mejor.",
            "El rendimiento posterior debe contrastarse frente a las alternativas declaradas.",
        ],
    )


def _validate_structuring_config_bounds(
    state: TFMStateModel,
    config: StructuringConfig,
) -> None:
    expected_rate = state.project_context.target_sample_rate_hz
    if config.target_sample_rate_hz != expected_rate:
        raise ValueError(f"target_sample_rate_hz must be {expected_rate}")
    if config.main_channel != state.project_context.main_channel:
        raise ValueError(f"main_channel must be {state.project_context.main_channel}")
    if config.label_mode != state.project_context.label_mode:
        raise ValueError(
            f"label_mode must be {state.project_context.label_mode}"
        )
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
    return StructuringConfig(
        window_size=DEFAULT_STRUCTURING_CONFIG.window_size,
        overlap=DEFAULT_STRUCTURING_CONFIG.overlap,
        main_channel=state.project_context.main_channel,
        target_sample_rate_hz=state.project_context.target_sample_rate_hz,
        label_mode=state.project_context.label_mode,
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
