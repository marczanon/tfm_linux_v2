"""Agente evaluador LLM con fallback seguro."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from codigo.app.schemas.agent_decisions import (
    AgentHypothesis,
    DecisionGenerationTrace,
    EvaluationDecision,
    require_agent_hypothesis,
)
from codigo.app.schemas.reasoning import AgentMemoryQuery, RetrievedMemoryContext
from codigo.app.schemas.state import EvaluationResult, MetricsReport, TFMStateModel
from codigo.app.services.agent_memory import (
    memory_context_for_llm,
    memory_usage_json_template,
    validate_retrieved_memory_usage,
)
from codigo.app.services.agent_tools import agent_tool_catalog
from codigo.app.services.llm import (
    JSONLLMClient,
    LLMCallError,
    LLMMessage,
    get_default_json_llm_client,
)
from codigo.app.services.online_blind import (
    assert_official_v2_claims_are_scoped,
    uses_online_blind_view,
)
from codigo.app.services.vector_memory import VectorMemoryStore


MIN_RECALL_REQUIRED = 0.90
MAX_FALSE_POSITIVE_RATE = 0.10
MIN_DEGRADATION_DETECTION_RATE = 0.50
MAX_DEGRADATION_FALSE_ALARM_RATE = 0.25
MIN_DEGRADATION_TREND_SPEARMAN = 0.00
RUN_TO_FAILURE_EVALUATOR_TOOLS = {
    "temporal_health_lookup",
    "degradation_metrics_lookup",
}
RUN_TO_FAILURE_GUARDRAILS = {
    "isolated_spike_not_failure",
    "sustained_alert_required",
    "rul_not_estimated",
    "proxy_labels_not_official",
    "f1_auxiliary_only",
}
OFFICIAL_V2_RUN_TO_FAILURE_GUARDRAILS = RUN_TO_FAILURE_GUARDRAILS | {
    "physical_ground_truth_not_available",
    "operational_acceptance_only",
    "recorded_end_not_physical_failure",
}


def decide_evaluation_action(
    state: TFMStateModel,
    *,
    memory_context: RetrievedMemoryContext | None = None,
    llm_client: JSONLLMClient | None = None,
    use_llm: bool | None = None,
) -> EvaluationDecision:
    """Interpreta metricas usando LLM cuando este habilitado."""

    should_use_llm = _should_use_llm(llm_client, use_llm)
    if should_use_llm:
        attempt_tracker = [0]
        try:
            client = llm_client or get_default_json_llm_client()
            return decide_evaluation_action_with_llm(
                state,
                client,
                memory_context=memory_context,
                _attempt_tracker=attempt_tracker,
            )
        except (ValidationError, ValueError) as exc:
            fallback = decide_evaluation_action_deterministic(state)
            fallback.rationale = (
                f"{fallback.rationale} Guardrail correction after invalid "
                f"LLM evaluator decision: {exc}"
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
            fallback = decide_evaluation_action_deterministic(state)
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

    return decide_evaluation_action_deterministic(state)


def decide_evaluation_action_with_llm(
    state: TFMStateModel,
    llm_client: JSONLLMClient,
    *,
    memory_context: RetrievedMemoryContext | None = None,
    _attempt_tracker: list[int] | None = None,
) -> EvaluationDecision:
    """Solicita al LLM una EvaluationDecision y valida sus limites."""

    attempt_tracker = _attempt_tracker if _attempt_tracker is not None else [0]
    messages = _evaluator_messages(state, memory_context=memory_context)
    schema = EvaluationDecision.model_json_schema()
    attempt_tracker[0] = 1
    payload = llm_client.complete_json(
        messages,
        json_schema=schema,
    )
    try:
        decision = _validated_evaluation_decision_from_payload(
            state,
            payload,
            memory_context=memory_context,
        )
    except (ValidationError, ValueError) as exc:
        attempt_tracker[0] = 2
        repaired_payload = llm_client.complete_json(
            _evaluator_contract_repair_messages(
                messages,
                state=state,
                invalid_payload=payload,
                validation_error=exc,
            ),
            json_schema=schema,
        )
        decision = _validated_evaluation_decision_from_payload(
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


def decide_evaluation_action_deterministic(state: TFMStateModel) -> EvaluationDecision:
    """Fallback reproducible para juzgar metricas y continuar a informe."""

    metrics = state.metrics
    approved = _evaluation_is_approved(state)
    return EvaluationDecision(
        decision_id=f"{state.run_id}:evaluator:{_evaluator_turn(state):03d}",
        rationale=_evaluation_policy_rationale(state),
        confidence=1.0,
        hypothesis=_evaluator_hypothesis(state, approved=approved),
        generation_trace=DecisionGenerationTrace.for_decision(
            f"{state.run_id}:evaluator:{_evaluator_turn(state):03d}",
            origin="deterministic",
        ),
        evaluation=EvaluationResult(
            approved=approved,
            summary=_evaluation_summary(state, approved),
            next_action=_evaluation_next_action(metrics),
            limitations=_evaluation_limitations(
                state,
                approved,
            ),
        ),
        min_recall_required=(
            None if _uses_temporal_degradation_profile(state) else MIN_RECALL_REQUIRED
        ),
        max_false_positive_rate=(
            None
            if _uses_temporal_degradation_profile(state)
            else MAX_FALSE_POSITIVE_RATE
        ),
        **_temporal_operational_decision_fields(state, approved),
    )


def build_evaluator_memory_query(
    state: TFMStateModel,
    *,
    top_k: int = 3,
    min_similarity: float = 0.0,
) -> AgentMemoryQuery:
    """Construye una consulta RAG para decisiones de evaluacion."""

    metrics_summary = _metrics_summary_for_llm(state.metrics)
    query_text = "\n".join(
        [
            "Evaluator decision for industrial anomaly detection metrics.",
            f"Dataset: {state.project_context.dataset}",
            f"Data provenance: {state.project_context.data_provenance}",
            f"Objective: {state.project_context.objective}",
            f"Supervision profile: {state.project_context.supervision_profile}",
            f"Label source: {state.project_context.label_source}",
            f"Metrics: {json.dumps(metrics_summary, ensure_ascii=True)}",
            (
                "Need prior lessons about approval, rejection, stopping, "
                "metric trade-offs, methodological caveats and when to ask for "
                "a new configuration."
            ),
        ]
    )
    return AgentMemoryQuery(
        query_id=f"{state.run_id}:evaluator:{_evaluator_turn(state):03d}:memory_query",
        target_agent="evaluator",
        query_text=query_text,
        dataset=state.project_context.dataset,
        data_provenance=state.project_context.data_provenance,
        run_id=state.run_id,
        decision_id=f"{state.run_id}:evaluator:{_evaluator_turn(state):03d}",
        decision_context={
            **state.project_context.to_memory_applicability().model_dump(
                mode="python"
            ),
            "current_stage": state.current_stage,
            "recall": None if state.metrics is None else state.metrics.recall,
            "f1_score": None if state.metrics is None else state.metrics.f1_score,
            "false_positive_rate": (
                None if state.metrics is None else state.metrics.false_positive_rate
            ),
            "data_provenance": state.project_context.data_provenance,
            "degradation_available": _metric_extra_bool(
                state.metrics,
                "degradation_available",
            ),
            "degradation_detected_before_failure_rate": _metric_extra_float(
                state.metrics,
                "degradation_detected_before_failure_rate",
            ),
            "degradation_confirmed_degradation_before_failure_rate": _metric_extra_float(
                state.metrics,
                "degradation_confirmed_degradation_before_failure_rate",
            ),
            "degradation_mean_persistent_lead_time_to_failure": _metric_extra_float(
                state.metrics,
                "degradation_mean_persistent_lead_time_to_failure",
            ),
            "degradation_mean_health_index_drop": _metric_extra_float(
                state.metrics,
                "degradation_mean_health_index_drop",
            ),
            "degradation_mean_health_monotonicity": _metric_extra_float(
                state.metrics,
                "degradation_mean_health_monotonicity",
            ),
            "degradation_mean_health_robustness": _metric_extra_float(
                state.metrics,
                "degradation_mean_health_robustness",
            ),
            "degradation_mean_false_alarm_rate_nominal": _metric_extra_float(
                state.metrics,
                "degradation_mean_false_alarm_rate_nominal",
            ),
            "degradation_mean_score_trend_spearman": _metric_extra_float(
                state.metrics,
                "degradation_mean_score_trend_spearman",
            ),
            "min_recall_required": MIN_RECALL_REQUIRED,
            "max_false_positive_rate": MAX_FALSE_POSITIVE_RATE,
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


def _validated_evaluation_decision_from_payload(
    state: TFMStateModel,
    payload: dict[str, Any],
    *,
    memory_context: RetrievedMemoryContext | None = None,
) -> EvaluationDecision:
    trusted_payload = _with_server_owned_evaluation_envelope(state, payload)
    decision = EvaluationDecision.model_validate(trusted_payload)
    _validate_evaluation_decision_bounds(
        state,
        decision,
        memory_context=memory_context,
    )
    return decision


def _with_server_owned_evaluation_envelope(
    state: TFMStateModel,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Impone identidad y umbrales del protocolo sin alterar el juicio LLM."""

    trusted_payload = dict(payload)
    trusted_payload.pop("created_at", None)
    trusted_payload.pop("generation_trace", None)
    trusted_payload["agent_name"] = "evaluator"
    trusted_payload["decision_id"] = (
        f"{state.run_id}:evaluator:{_evaluator_turn(state):03d}"
    )
    uses_temporal_profile = _uses_temporal_degradation_profile(state)
    trusted_payload["min_recall_required"] = (
        None if uses_temporal_profile else MIN_RECALL_REQUIRED
    )
    trusted_payload["max_false_positive_rate"] = (
        None if uses_temporal_profile else MAX_FALSE_POSITIVE_RATE
    )
    return trusted_payload


def _evaluator_contract_repair_messages(
    original_messages: list[LLMMessage],
    *,
    state: TFMStateModel,
    invalid_payload: dict[str, Any],
    validation_error: Exception,
) -> list[LLMMessage]:
    return [
        *original_messages,
        LLMMessage(
            role="assistant",
            content=json.dumps(invalid_payload, indent=2, ensure_ascii=True),
        ),
        LLMMessage(
            role="user",
            content="\n".join(
                [
                    "La decision anterior no valida contra los guardarrails del evaluador.",
                    f"Error de validacion: {validation_error}",
                    "Corrige solo lo necesario y reemite un unico objeto JSON valido.",
                    "No relajes umbrales ni inventes evidencia.",
                    (
                        "Incluye hypothesis con kind=operational_acceptance, "
                        "evidencia visible y un criterio que pueda refutar el veredicto."
                    ),
                    (
                        "agent_name, decision_id y los umbrales del protocolo son "
                        "metadatos server-owned; el servidor impondrá sus valores "
                        "canónicos."
                    ),
                    "Para run-to-failure, RUL no esta estimado: no escribas que existe RUL estimado.",
                    *(
                        [
                            "Para NASA IMS oficial v2, approved solo representa aceptacion por controles operativos internos.",
                            "Describe primera alerta algoritmica persistente, tiempo retrospectivo hasta el final registrado y tasa de alertas pre-monitorizacion.",
                            "No afirmes onset fisico, deteccion o diagnostico validados, fallo predicho ni RUL.",
                        ]
                        if uses_online_blind_view(state)
                        else []
                    ),
                    "No incluyas texto fuera del JSON.",
                ]
            ),
        ),
    ]


def retrieve_evaluator_memory_context(
    state: TFMStateModel,
    *,
    memory_store: VectorMemoryStore,
    top_k: int = 3,
    min_similarity: float = 0.0,
) -> RetrievedMemoryContext:
    """Recupera memoria supervisada para el agente evaluador."""

    query = build_evaluator_memory_query(
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
    return os.getenv("TFM_EVALUATOR_MODE", "").strip().lower() == "llm"


def _evaluator_messages(
    state: TFMStateModel,
    *,
    memory_context: RetrievedMemoryContext | None = None,
) -> list[LLMMessage]:
    return [
        LLMMessage(
            role="system",
            content=(
                "Eres el agente evaluador de un pipeline industrial de "
                "deteccion de anomalias. Tu tarea es interpretar metricas ya "
                "calculadas y emitir un juicio estructurado. No puedes recalcular "
                "metricas, modificar predicciones ni ejecutar codigo. Debes "
                "devolver exclusivamente un objeto JSON compatible con "
                "EvaluationDecision."
            ),
        ),
        LLMMessage(
            role="user",
            content="\n".join(
                [
                    "Contexto ligero:",
                    json.dumps(_state_summary_for_llm(state), indent=2, ensure_ascii=True),
                    "",
                    "Metricas disponibles:",
                    json.dumps(_metrics_summary_for_llm(state.metrics), indent=2, ensure_ascii=True),
                    "",
                    "Herramientas agenticas disponibles:",
                    json.dumps(_evaluator_tool_catalog_for_llm(), indent=2, ensure_ascii=True),
                    "",
                    "Memoria recuperada para el evaluador:",
                    json.dumps(
                        memory_context_for_llm(memory_context),
                        indent=2,
                        ensure_ascii=True,
                    ),
                    "",
                    "Formato JSON esperado:",
                    json.dumps(
                        _evaluator_json_template(
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
                        "- agent_name, decision_id, min_recall_required y "
                        "max_false_positive_rate son campos informativos "
                        "server-owned; el servidor impondrá los valores del "
                        "protocolo mostrados en la plantilla."
                    ),
                    "- evaluation debe validar contra EvaluationResult.",
                    (
                        "- hypothesis debe separar el veredicto de las condiciones "
                        "que lo apoyarian o lo refutarian; no uses approved como prueba."
                    ),
                    *_profile_specific_rules(state),
                    "- Si hay metricas, next_action debe ser continue para generar informe.",
                    (
                        "- Si approved es false, no marques la run como fallo: "
                        "explica las metricas bajas en summary y limitations."
                    ),
                    (
                        "- La memoria recuperada puede ayudar a redactar el "
                        "juicio y las limitaciones, pero no puede cambiar los "
                        "umbrales ni aprobar metricas que no los cumplen."
                    ),
                    (
                        "- Si usas memoria, pon used_memory_context=true, cita "
                        "sus memory_record_id y explica el uso de cada recuerdo."
                    ),
                    (
                        "- Si un recuerdo es boundary_case o warning, usalo "
                        "como cautela metodologica, no como permiso para aprobar."
                    ),
                    (
                        "- Si la memoria no aporta evidencia util para este "
                        "juicio, declara used_memory_context=false."
                    ),
                ]
            ),
        ),
    ]


def _evaluator_json_template(
    state: TFMStateModel,
    *,
    memory_context: RetrievedMemoryContext | None = None,
) -> dict[str, Any]:
    approved = _evaluation_is_approved(state)
    template = {
        "agent_name": "evaluator",
        "decision_id": f"{state.run_id}:evaluator:{_evaluator_turn(state):03d}",
        "rationale": "Motivo tecnico breve del juicio de evaluacion.",
        "confidence": 0.9,
        "hypothesis": _evaluator_hypothesis(
            state,
            approved=approved,
        ).model_dump(mode="json"),
        "evaluation": {
            "approved": approved,
            "summary": _evaluation_summary(state, approved),
            "next_action": _evaluation_next_action(state.metrics),
            "limitations": _evaluation_limitations(
                state,
                approved,
            ),
        },
        "min_recall_required": (
            None if _uses_temporal_degradation_profile(state) else MIN_RECALL_REQUIRED
        ),
        "max_false_positive_rate": (
            None
            if _uses_temporal_degradation_profile(state)
            else MAX_FALSE_POSITIVE_RATE
        ),
        **_temporal_operational_decision_fields(state, approved),
    }
    template.update(memory_usage_json_template(memory_context))
    return template


def _state_summary_for_llm(state: TFMStateModel) -> dict[str, Any]:
    return {
        "thread_id": state.thread_id,
        "run_id": state.run_id,
        "current_stage": state.current_stage,
        "dataset": state.project_context.dataset,
        "data_provenance": state.project_context.data_provenance,
        "objective": state.project_context.objective,
        "supervision_profile": state.project_context.supervision_profile,
        "label_source": state.project_context.label_source,
        "label_granularity": state.project_context.label_granularity,
        "modeling_config": (
            None
            if state.modeling_config is None
            else state.modeling_config.model_dump(mode="json")
        ),
        "metrics_path": None if state.metrics is None else state.metrics.metrics_path,
        "artifact_types": [artifact.artifact_type for artifact in state.artifacts],
    }


def _metrics_summary_for_llm(metrics: MetricsReport | None) -> dict[str, Any]:
    if metrics is None:
        return {"available": False}

    summary: dict[str, Any] = {
        "available": True,
        "metrics": metrics.model_dump(mode="json"),
    }
    if metrics.metrics_path and Path(metrics.metrics_path).exists():
        try:
            raw = json.loads(Path(metrics.metrics_path).read_text(encoding="utf-8"))
            summary["primary_split"] = raw.get("primary_split")
            summary["primary_metrics"] = raw.get("primary_metrics")
            summary["split_counts"] = raw.get("split_counts")
            summary["label_counts"] = raw.get("label_counts")
            summary["metric_families"] = raw.get("metric_families")
            summary["binary_metric_context"] = raw.get("binary_metric_context")
            summary["degradation_metrics"] = raw.get("degradation_metrics")
        except (OSError, json.JSONDecodeError) as exc:
            summary["metrics_file_error"] = str(exc)
    return summary


def _evaluator_tool_catalog_for_llm() -> list[dict[str, Any]]:
    return [
        {
            "tool_name": spec.tool_name,
            "effect": spec.effect,
            "description": spec.description,
            "input_schema": spec.input_schema,
        }
        for spec in agent_tool_catalog(agent_name="evaluator")
    ]


def _validate_evaluation_decision_bounds(
    state: TFMStateModel,
    decision: EvaluationDecision,
    *,
    memory_context: RetrievedMemoryContext | None = None,
) -> None:
    require_agent_hypothesis(
        decision,
        allowed_kinds={"operational_acceptance"},
    )
    if _uses_temporal_degradation_profile(state):
        if decision.min_recall_required is not None:
            raise ValueError("run-to-failure evaluation must not require recall threshold")
        if decision.max_false_positive_rate is not None:
            raise ValueError("run-to-failure evaluation must not require binary FPR threshold")
        _validate_temporal_operational_decision(state, decision)
    else:
        if decision.min_recall_required != MIN_RECALL_REQUIRED:
            raise ValueError(f"min_recall_required must be {MIN_RECALL_REQUIRED}")
        if decision.max_false_positive_rate != MAX_FALSE_POSITIVE_RATE:
            raise ValueError(
                f"max_false_positive_rate must be {MAX_FALSE_POSITIVE_RATE}"
            )

    expected_approved = _evaluation_is_approved(state)
    if decision.evaluation.approved != expected_approved:
        raise ValueError("approved does not match deterministic evaluation policy")
    if expected_approved and decision.evaluation.next_action != "continue":
        raise ValueError("approved evaluations must continue")
    if state.metrics is not None and decision.evaluation.next_action != "continue":
        raise ValueError("evaluations with metrics must continue to reporting")
    validate_retrieved_memory_usage(
        memory_context=memory_context,
        memory_context_id=decision.memory_context_id,
        used_memory_context=decision.used_memory_context,
        memory_record_ids=decision.memory_record_ids,
        memory_record_uses=decision.memory_record_uses,
    )


def _evaluator_hypothesis(
    state: TFMStateModel,
    *,
    approved: bool,
) -> AgentHypothesis:
    temporal = _uses_temporal_degradation_profile(state)
    online_blind = uses_online_blind_view(state)
    verdict = "satisface" if approved else "no satisface"
    if temporal:
        expected = (
            "Todas las metricas temporales disponibles, guardarrailes y limitaciones "
            "son coherentes con el alcance operativo del veredicto."
        )
        falsifier = (
            "Falta una evidencia necesaria, un guardarrail contradice el veredicto "
            "o se extrapola una alerta algoritmica a fallo fisico o pronostico."
        )
        refs = _temporal_evaluation_evidence_refs(state)
        cutoff = (
            "Metricas retrospectivas de monitoring ya ejecutado y artefactos cerrados; "
            "no existe ground truth fisico oficial."
            if online_blind
            else "Metricas temporales y artefactos cerrados antes de redactar el informe."
        )
        risks = [
            "Aprobar monitorizacion algoritmica no equivale a validar diagnostico fisico o RUL."
        ]
    else:
        expected = (
            "Recall y false positive rate cumplen de forma conjunta los umbrales "
            "declarados y las limitaciones no contradicen la decision."
        )
        falsifier = (
            "Se incumple algun umbral, falta una metrica requerida, existe fuga o "
            "la aprobacion depende de una unica medida aislada."
        )
        refs = [
            "metrics:classification",
            "policy:min_recall",
            "policy:max_false_positive_rate",
        ]
        cutoff = "Metricas held-out persistidas y configuracion efectiva de la run."
        risks = [
            "El veredicto local no demuestra generalizacion fuera del benchmark evaluado."
        ]
    return AgentHypothesis(
        kind="operational_acceptance",
        statement=(
            f"La evidencia disponible {verdict} los criterios predefinidos para "
            "el veredicto operativo emitido dentro de su alcance declarado."
        ),
        scope=(
            f"Run {state.run_id}; dataset {state.project_context.dataset}; "
            f"perfil {state.project_context.supervision_profile}."
        ),
        evidence_cutoff=cutoff,
        expected_observation=expected,
        falsification_criterion=falsifier,
        evidence_refs=refs,
        risk_notes=risks,
        assumptions=[
            "La propia aprobacion del evaluador no confirma su hipotesis; requiere contraste independiente."
        ],
    )


def _temporal_operational_decision_fields(
    state: TFMStateModel,
    approved: bool,
) -> dict[str, Any]:
    if not _uses_temporal_degradation_profile(state):
        return {}
    return {
        "tool_names": [
            "temporal_health_lookup",
            "degradation_metrics_lookup",
            "temporal_model_readiness_assessor",
        ],
        "evidence_refs": _temporal_evaluation_evidence_refs(state),
        "operational_assessment": _temporal_operational_assessment(state, approved),
        "temporal_debate_points": _temporal_debate_points(state, approved),
        "temporal_guardrail_checks": sorted(
            OFFICIAL_V2_RUN_TO_FAILURE_GUARDRAILS
            if uses_online_blind_view(state)
            else RUN_TO_FAILURE_GUARDRAILS
        ),
    }


def _temporal_evaluation_evidence_refs(state: TFMStateModel) -> list[str]:
    if uses_online_blind_view(state):
        return sorted(
            {
                "tool:temporal_health_lookup",
                "tool:degradation_metrics_lookup",
                "tool:temporal_model_readiness_assessor",
                "temporal:first_persistent_algorithmic_alert",
                "temporal:recorded_trajectory_end",
                "temporal:health_policy",
                "temporal:alert_policy",
                "temporal:health_indicator_policy",
                "temporal:isolated_alert_points",
                "temporal:longest_alert_streak",
                "temporal:rul_not_estimated",
                "health:indicator_available",
                "health:monotonicity",
                "health:robustness",
                "health:dominant_evidence",
                "readiness:temporal_model_readiness",
                "metric:persistent_algorithmic_alert_rate",
                "metric:retrospective_time_to_recorded_end",
                "metric:pre_monitoring_alert_rate",
                "metric:mean_health_index_drop",
                "metric:mean_health_monotonicity",
                "metric:mean_health_robustness",
                "metric:mean_score_trend_spearman",
                "scope:physical_ground_truth_unavailable",
                f"label_source:{state.project_context.label_source}",
            }
        )
    refs = [
        "tool:temporal_health_lookup",
        "tool:degradation_metrics_lookup",
        "tool:temporal_model_readiness_assessor",
        "temporal:first_persistent_alert",
        "temporal:onset_confirmed",
        "temporal:health_policy",
        "temporal:alert_policy",
        "temporal:health_indicator_policy",
        "temporal:isolated_alert_points",
        "temporal:longest_alert_streak",
        "temporal:rul_not_estimated",
        "health:indicator_available",
        "health:monotonicity",
        "health:robustness",
        "health:dominant_evidence",
        "readiness:temporal_model_readiness",
        "metric:confirmed_degradation_before_failure_rate",
        "metric:mean_persistent_lead_time_to_failure",
        "metric:mean_health_index_drop",
        "metric:mean_health_monotonicity",
        "metric:mean_health_robustness",
        "metric:mean_lead_time_to_failure",
        "metric:mean_false_alarm_rate_nominal",
        "metric:mean_score_trend_spearman",
        f"label_source:{state.project_context.label_source}",
    ]
    return sorted(set(refs))


def _temporal_operational_assessment(
    state: TFMStateModel,
    approved: bool,
) -> str:
    if state.metrics is None:
        if uses_online_blind_view(state):
            return (
                "No hay metricas temporales para aplicar los controles operativos "
                "internos ni distinguir pico aislado de alerta persistente; la "
                "ejecucion oficial causal v2 queda incompleta. No hay ground truth "
                "fisico por snapshot y RUL no esta estimado."
            )
        return (
            "No hay metricas temporales; la deteccion no es defendible "
            "operacionalmente y debe tratarse como incompleta."
        )
    if uses_online_blind_view(state):
        status = (
            "supera los controles operativos internos"
            if approved
            else "no supera todavia los controles operativos internos"
        )
        return (
            f"La ejecucion oficial causal v2 {status}: se auditan la primera "
            "alerta algoritmica persistente, la tasa de alertas pre-monitorizacion "
            "y la tendencia del score bajo una politica temporal versionada. El "
            "Health Indicator aporta evidencia descriptiva de caida, monotonicidad "
            "y robustez. Un pico aislado no equivale a un evento fisico; no hay "
            "ground truth por snapshot para validar deteccion, diagnostico o inicio "
            "fisico. RUL no esta estimado."
        )
    status = "defendible con cautelas" if approved else "no defendible todavia"
    return (
        f"La deteccion run-to-failure es {status}: se juzga por aviso sostenido, "
        "lead time persistente, falsas alarmas nominales y tendencia del score "
        "bajo una politica temporal versionada. El Health Indicator avanzado "
        "aporta evidencia auxiliar de caida, monotonicidad y robustez. Un pico "
        "aislado no equivale a fallo; RUL no esta estimado y las etiquetas proxy "
        "no son ground truth oficial por ventana."
    )


def _temporal_debate_points(
    state: TFMStateModel,
    approved: bool,
) -> list[str]:
    if uses_online_blind_view(state):
        points = [
            "Distinguir pico aislado de alerta algoritmica persistente antes de interpretar riesgo.",
            "Interpretar el intervalo retrospectivo respecto al final registrado, no como RUL.",
            "Distinguir score de anomalia, Health Indicator y estado operacional.",
            "Revisar monotonicidad y robustez del Health Indicator como evidencia descriptiva.",
            "Valorar la tasa de alertas pre-monitorizacion y sus limites no independientes.",
            "Citar la politica temporal usada para confirmar persistencia algoritmica.",
            "Declarar que label_source=none implica ausencia de ground truth fisico por snapshot.",
            "Tratar F1, recall y precision como no aplicables sin etiquetas binarias oficiales.",
        ]
        if not approved:
            points.append(
                "Solicitar otra estrategia si tendencia, persistencia o alertas pre-monitorizacion no son suficientes."
            )
        return points
    points = [
        "Distinguir pico aislado de aviso sostenido antes de interpretar riesgo.",
        "Comprobar que el onset confirmado existe sin presentar RUL estimado.",
        "Distinguir score de anomalia, Health Indicator y estado operacional.",
        "Revisar monotonicidad y robustez del Health Indicator antes de recomendar operacion.",
        "Valorar falsas alarmas nominales frente a utilidad industrial.",
        "Citar la politica temporal usada para confirmar alertas sostenidas.",
        "Tratar F1, recall y precision como metricas auxiliares/proxy.",
    ]
    if state.project_context.label_source in {"none", "temporal_proxy", "synthetic"}:
        points.append(
            "Declarar que las etiquetas por ventana son proxy o experimentales, no oficiales."
        )
    if not approved:
        points.append(
            "Solicitar nueva estrategia si deteccion temprana, tendencia o falsas alarmas no son suficientes."
        )
    return points


def _validate_temporal_operational_decision(
    state: TFMStateModel,
    decision: EvaluationDecision,
) -> None:
    missing_tools = sorted(RUN_TO_FAILURE_EVALUATOR_TOOLS - set(decision.tool_names))
    if missing_tools:
        raise ValueError(
            "run-to-failure evaluator decision must use tools: "
            + ", ".join(missing_tools)
        )
    refs = set(decision.evidence_refs)
    required_tool_refs = {f"tool:{name}" for name in RUN_TO_FAILURE_EVALUATOR_TOOLS}
    missing_tool_refs = sorted(required_tool_refs - refs)
    if missing_tool_refs:
        raise ValueError(
            "run-to-failure evaluator decision must cite tool refs: "
            + ", ".join(missing_tool_refs)
        )
    if not any(
        ref.startswith("temporal:") or ref.startswith("metric:mean_")
        for ref in refs
    ):
        raise ValueError(
            "run-to-failure evaluator decision must cite temporal or degradation evidence"
        )
    if decision.operational_assessment is None:
        raise ValueError(
            "run-to-failure evaluator decision requires operational_assessment"
        )
    assessment = decision.operational_assessment.lower()
    if "rul" not in assessment:
        raise ValueError("operational_assessment must mention RUL limitation")
    if "pico" not in assessment and "spike" not in assessment:
        raise ValueError("operational_assessment must address isolated spikes")
    if "sosten" not in assessment and "persistent" not in assessment:
        raise ValueError("operational_assessment must address sustained alerts")
    debate_text = " ".join(decision.temporal_debate_points).lower()
    if uses_online_blind_view(state):
        required_concepts = {
            "pico": ("pico", "spike"),
            "persistent alert": ("persist", "sosten"),
            "pre-monitoring alerts": ("pre-monitor",),
            "ground truth": ("ground truth",),
        }
        for concept, alternatives in required_concepts.items():
            if not any(word in debate_text for word in alternatives):
                raise ValueError(
                    "official v2 temporal_debate_points must address " + concept
                )
    else:
        for word in ["pico", "sosten", "falsas", "proxy"]:
            if word not in debate_text:
                raise ValueError(
                    "temporal_debate_points must debate spike, sustained alert, "
                    "false alarms and proxy labels"
                )
    missing_guardrails = sorted(
        (
            OFFICIAL_V2_RUN_TO_FAILURE_GUARDRAILS
            if uses_online_blind_view(state)
            else RUN_TO_FAILURE_GUARDRAILS
        )
        - set(decision.temporal_guardrail_checks)
    )
    if missing_guardrails:
        raise ValueError(
            "run-to-failure evaluator decision missing guardrail checks: "
            + ", ".join(missing_guardrails)
        )
    if any(_claims_estimated_rul(point) for point in decision.temporal_debate_points):
        raise ValueError("temporal_debate_points cannot claim estimated RUL")
    assert_official_v2_claims_are_scoped(
        state,
        [
            decision.rationale,
            decision.hypothesis.statement,
            decision.hypothesis.scope,
            decision.hypothesis.evidence_cutoff,
            decision.hypothesis.expected_observation,
            decision.hypothesis.falsification_criterion,
            *decision.hypothesis.risk_notes,
            *decision.hypothesis.assumptions,
            decision.evaluation.summary,
            *decision.evaluation.limitations,
            decision.operational_assessment,
            *decision.temporal_debate_points,
        ],
    )


def _claims_estimated_rul(text: str) -> bool:
    normalized = text.lower()
    if "estimated rul" in normalized:
        return "not estimated" not in normalized and "no estimated" not in normalized
    if "rul estimado" not in normalized:
        return False
    negations = [
        "sin presentar",
        "sin estimar",
        "no presentar",
        "no esta",
        "no está",
        "no se",
        "no hay",
        "no existe",
    ]
    return not any(negation in normalized for negation in negations)


def _profile_specific_rules(state: TFMStateModel) -> list[str]:
    if _uses_temporal_degradation_profile(state):
        if uses_online_blind_view(state):
            return [
                "- min_recall_required debe ser null para el protocolo oficial causal v2.",
                "- max_false_positive_rate debe ser null para el protocolo oficial causal v2.",
                (
                    "- approved es solo el resultado de controles operativos internos; "
                    "en la narrativa usa 'aceptada por controles operativos internos'."
                ),
                (
                    "- Interpreta los campos historicos confirmed_degradation y "
                    "lead_time_to_failure solo como compatibilidad interna: comunica "
                    "primera alerta algoritmica persistente y tiempo retrospectivo "
                    "hasta el final registrado."
                ),
                (
                    "- Comunica degradation_mean_false_alarm_rate_nominal como tasa "
                    "de alertas pre-monitorizacion; no la presentes como FPR binaria."
                ),
                (
                    "- No afirmes onset fisico, deteccion o diagnostico validados, "
                    "evento fisico predicho, RUL ni generalizacion industrial."
                ),
                "- label_source=none significa que no existen etiquetas binarias oficiales por snapshot.",
                "- F1, recall, precision, ROC-AUC y PR-AUC no son aplicables como validacion binaria.",
                (
                    "- tool_names debe incluir temporal_health_lookup y "
                    "degradation_metrics_lookup."
                ),
                (
                    "- evidence_refs debe citar herramientas, alerta algoritmica, "
                    "final registrado y alcance sin ground truth fisico."
                ),
                (
                    "- operational_assessment debe acotar el resultado a controles "
                    "internos y mencionar ausencia de ground truth y RUL."
                ),
                (
                    "- temporal_debate_points debe debatir pico aislado, alerta "
                    "persistente, alertas pre-monitorizacion y ausencia de ground truth."
                ),
                (
                    "- temporal_guardrail_checks debe incluir los controles generales "
                    "y physical_ground_truth_not_available, operational_acceptance_only "
                    "y recorded_end_not_physical_failure."
                ),
            ]
        return [
            "- min_recall_required debe ser null para perfiles run-to-failure.",
            "- max_false_positive_rate debe ser null para perfiles run-to-failure.",
            (
                "- approved debe basarse en degradation_metrics: onset confirmado "
                "antes de fallo, lead time persistente, falsas alarmas nominales "
                "y tendencia del score."
            ),
            (
                "- No suspendas NASA IMS por no tener etiquetas oficiales por "
                "ventana si existen metricas temporales de degradacion."
            ),
            (
                "- No presentes F1 como metrica principal del perfil "
                "run-to-failure; puede citarse solo como metrica auxiliar/proxy."
            ),
            (
                "- Declara como limitacion cualquier label_source none, "
                "temporal_proxy o synthetic."
            ),
        (
            "- tool_names debe incluir temporal_health_lookup y "
            "degradation_metrics_lookup."
        ),
        (
            "- Si se menciona autoencoder, LSTM o RUL experimental, exige "
            "temporal_model_readiness_assessor y refs readiness:*."
        ),
        (
            "- evidence_refs debe citar las herramientas usadas y al menos "
                "una metrica temporal o referencia temporal."
            ),
            (
                "- operational_assessment debe juzgar si la deteccion es "
                "defendible industrialmente, no solo numericamente correcta."
            ),
            (
                "- temporal_debate_points debe debatir pico aislado, aviso "
                "sostenido, falsas alarmas nominales y etiquetas proxy."
            ),
            (
                "- temporal_guardrail_checks debe incluir isolated_spike_not_failure, "
                "sustained_alert_required, rul_not_estimated, "
                "proxy_labels_not_official y f1_auxiliary_only."
            ),
        ]
    return [
        f"- min_recall_required debe ser {MIN_RECALL_REQUIRED}.",
        f"- max_false_positive_rate debe ser {MAX_FALSE_POSITIVE_RATE}.",
        "- approved debe ser true solo si recall y FPR cumplen los umbrales.",
    ]


def _evaluation_is_approved(state: TFMStateModel) -> bool:
    if _uses_temporal_degradation_profile(state):
        return _degradation_metrics_are_approved(state.metrics)
    return _metrics_are_approved(state.metrics)


def _metrics_are_approved(metrics: MetricsReport | None) -> bool:
    if metrics is None:
        return False
    if metrics.recall is None or metrics.false_positive_rate is None:
        return False
    return (
        metrics.recall >= MIN_RECALL_REQUIRED
        and metrics.false_positive_rate <= MAX_FALSE_POSITIVE_RATE
    )


def _degradation_metrics_are_approved(metrics: MetricsReport | None) -> bool:
    if metrics is None or not _metric_extra_bool(metrics, "degradation_available"):
        return False
    confirmed_detection_rate = _metric_extra_float(
        metrics,
        "degradation_confirmed_degradation_before_failure_rate",
    )
    first_spike_detection_rate = _metric_extra_float(
        metrics,
        "degradation_detected_before_failure_rate",
    )
    detection_rate = (
        confirmed_detection_rate
        if confirmed_detection_rate is not None
        else first_spike_detection_rate
    )
    persistent_lead_time = _metric_extra_float(
        metrics,
        "degradation_mean_persistent_lead_time_to_failure",
    )
    first_spike_lead_time = _metric_extra_float(
        metrics,
        "degradation_mean_lead_time_to_failure",
    )
    mean_lead_time = (
        persistent_lead_time
        if persistent_lead_time is not None
        else first_spike_lead_time
    )
    false_alarm_rate = _metric_extra_float(
        metrics,
        "degradation_mean_false_alarm_rate_nominal",
    )
    trend = _metric_extra_float(
        metrics,
        "degradation_mean_score_trend_spearman",
    )
    detected_enough = (
        detection_rate >= MIN_DEGRADATION_DETECTION_RATE
        if detection_rate is not None
        else mean_lead_time is not None and mean_lead_time >= 0.0
    )
    false_alarm_ok = (
        True
        if false_alarm_rate is None
        else false_alarm_rate <= MAX_DEGRADATION_FALSE_ALARM_RATE
    )
    trend_ok = (
        True
        if trend is None
        else trend >= MIN_DEGRADATION_TREND_SPEARMAN
    )
    return bool(detected_enough and false_alarm_ok and trend_ok)


def _evaluation_next_action(metrics: MetricsReport | None) -> str:
    if metrics is None:
        return "stop"
    return "continue"


def _evaluation_summary(state: TFMStateModel, approved: bool) -> str:
    if state.metrics is None:
        if uses_online_blind_view(state):
            return (
                "No hay metricas disponibles para aplicar los controles "
                "operativos internos de la ejecucion oficial causal v2."
            )
        return "No hay metricas disponibles para aprobar la ejecucion."
    if _uses_temporal_degradation_profile(state):
        if uses_online_blind_view(state):
            status = (
                "aceptada por controles operativos internos"
                if approved
                else "completada sin superar los controles operativos internos"
            )
            return (
                f"Ejecucion run-to-failure {status}: "
                "trayectorias_con_alerta_algoritmica_persistente="
                f"{_format_metric(_metric_extra_float_any(state.metrics, 'degradation_confirmed_degradation_before_failure_rate', 'degradation_detected_before_failure_rate'))}, "
                "tiempo_retrospectivo_hasta_fin_registrado="
                f"{_format_metric(_metric_extra_float_any(state.metrics, 'degradation_mean_persistent_lead_time_to_failure', 'degradation_mean_lead_time_to_failure'))}, "
                "tasa_alertas_pre_monitorizacion="
                f"{_format_metric(_metric_extra_float(state.metrics, 'degradation_mean_false_alarm_rate_nominal'))}, "
                "HI_drop="
                f"{_format_metric(_metric_extra_float(state.metrics, 'degradation_mean_health_index_drop'))}, "
                "HI_monotonicidad="
                f"{_format_metric(_metric_extra_float(state.metrics, 'degradation_mean_health_monotonicity'))}, "
                "tendencia_score="
                f"{_format_metric(_metric_extra_float(state.metrics, 'degradation_mean_score_trend_spearman'))}."
            )
        status = "aprobada" if approved else "completada con metricas temporales insuficientes"
        return (
            f"Ejecucion run-to-failure {status}: "
            "onset_confirmado="
            f"{_format_metric(_metric_extra_float_any(state.metrics, 'degradation_confirmed_degradation_before_failure_rate', 'degradation_detected_before_failure_rate'))}, "
            "lead_time_persistente="
            f"{_format_metric(_metric_extra_float_any(state.metrics, 'degradation_mean_persistent_lead_time_to_failure', 'degradation_mean_lead_time_to_failure'))}, "
            "FAR_nominal="
            f"{_format_metric(_metric_extra_float(state.metrics, 'degradation_mean_false_alarm_rate_nominal'))}, "
            "HI_drop="
            f"{_format_metric(_metric_extra_float(state.metrics, 'degradation_mean_health_index_drop'))}, "
            "HI_monotonicidad="
            f"{_format_metric(_metric_extra_float(state.metrics, 'degradation_mean_health_monotonicity'))}, "
            "tendencia_score="
            f"{_format_metric(_metric_extra_float(state.metrics, 'degradation_mean_score_trend_spearman'))}."
        )

    status = "aprobada" if approved else "completada con metricas insuficientes"
    return (
        f"Ejecucion {status}: recall={_format_metric(state.metrics.recall)}, "
        f"F1={_format_metric(state.metrics.f1_score)}, "
        f"FPR={_format_metric(state.metrics.false_positive_rate)}."
    )


def _evaluation_limitations(
    state: TFMStateModel,
    approved: bool,
) -> list[str]:
    metrics = state.metrics
    dataset_name = state.project_context.dataset
    limitations = [
        f"La validacion se realiza sobre {dataset_name} con el protocolo local.",
        "La generalizacion industrial requiere validar otros datasets y condiciones de carga.",
    ]
    if metrics is None:
        return ["No se han encontrado metricas en el estado."]
    if _uses_temporal_degradation_profile(state):
        if uses_online_blind_view(state):
            limitations.extend(
                [
                    "No hay ground truth fisico por snapshot; la run no valida deteccion, diagnostico ni localizacion de un inicio fisico.",
                    "El intervalo comunicado se calcula retrospectivamente respecto al final registrado y no constituye RUL.",
                    "La tasa pre-monitorizacion incluye calibracion usada para fijar el umbral y no es una estimacion independiente de rendimiento.",
                    "La aceptacion solo indica cumplimiento de controles operativos internos del protocolo local.",
                ]
            )
            if not _metric_extra_bool(metrics, "degradation_available"):
                limitations.append("Faltan metricas temporales de trayectoria.")
            elif not approved:
                limitations.append(
                    "Las metricas de trayectoria no cumplen los controles internos de persistencia, alertas pre-monitorizacion y tendencia."
                )
            return limitations
        limitations.append(
            "El perfil run-to-failure se evalua por trayectoria temporal, no por F1 como metrica principal."
        )
        if state.project_context.label_source in {"none", "temporal_proxy", "synthetic"}:
            limitations.append(
                "Las etiquetas por ventana no son oficiales; la interpretacion depende de la politica temporal declarada."
            )
        if not _metric_extra_bool(metrics, "degradation_available"):
            limitations.append("Faltan metricas temporales de degradacion.")
        elif not approved:
            limitations.append(
                "Las metricas temporales no cumplen los criterios minimos de onset confirmado, falsas alarmas y tendencia."
            )
        return limitations
    if metrics.recall is None or metrics.false_positive_rate is None:
        limitations.append("Faltan recall o tasa de falsos positivos.")
    elif not approved:
        limitations.append(
            "Las metricas no cumplen los umbrales minimos del MVP local."
        )
    return limitations


def _evaluation_policy_rationale(state: TFMStateModel) -> str:
    if _uses_temporal_degradation_profile(state):
        if uses_online_blind_view(state):
            return (
                "Deterministic official causal v2 policy: apply internal operational "
                "controls to persistent algorithmic alerts, retrospective time to "
                "the recorded trajectory end, pre-monitoring alert rate and score "
                "trend. This is not physical detection, diagnosis, onset or RUL validation."
            )
        return (
            "Deterministic run-to-failure evaluation policy: judge temporal "
            "degradation metrics such as confirmed onset before failure, "
            "persistent lead time, nominal false alarms and score trend; binary "
            "F1 is treated only as auxiliary/proxy."
        )
    return (
        "Deterministic binary evaluation policy: approve only if recall and false "
        "positive rate satisfy the local MVP thresholds; complete the run "
        "with explicit limitations when metrics are below threshold."
    )


def _uses_temporal_degradation_profile(state: TFMStateModel) -> bool:
    return state.project_context.supervision_profile == "run_to_failure_degradation"


def _metric_extra_float(metrics: MetricsReport | None, key: str) -> float | None:
    if metrics is None:
        return None
    value = metrics.extra.get(key)
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    return None


def _metric_extra_float_any(metrics: MetricsReport | None, *keys: str) -> float | None:
    for key in keys:
        value = _metric_extra_float(metrics, key)
        if value is not None:
            return value
    return None


def _metric_extra_bool(metrics: MetricsReport | None, key: str) -> bool:
    if metrics is None:
        return False
    return metrics.extra.get(key) is True


def _format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _evaluator_turn(state: TFMStateModel) -> int:
    return 1 + sum(message.name == "evaluator" for message in state.messages)
