"""Agente evaluador LLM con fallback seguro."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from codigo.app.schemas.agent_decisions import EvaluationDecision
from codigo.app.schemas.reasoning import AgentMemoryQuery, RetrievedMemoryContext
from codigo.app.schemas.state import EvaluationResult, MetricsReport, TFMStateModel
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
from codigo.app.services.vector_memory import VectorMemoryStore


MIN_RECALL_REQUIRED = 0.90
MAX_FALSE_POSITIVE_RATE = 0.10
MIN_DEGRADATION_DETECTION_RATE = 0.50
MAX_DEGRADATION_FALSE_ALARM_RATE = 0.25
MIN_DEGRADATION_TREND_SPEARMAN = 0.00


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
        try:
            client = llm_client or get_default_json_llm_client()
            return decide_evaluation_action_with_llm(
                state,
                client,
                memory_context=memory_context,
            )
        except (LLMCallError, ValidationError, ValueError) as exc:
            fallback = decide_evaluation_action_deterministic(state)
            fallback.rationale = f"{fallback.rationale} Fallback after LLM failure: {exc}"
            fallback.confidence = min(fallback.confidence, 0.7)
            return fallback

    return decide_evaluation_action_deterministic(state)


def decide_evaluation_action_with_llm(
    state: TFMStateModel,
    llm_client: JSONLLMClient,
    *,
    memory_context: RetrievedMemoryContext | None = None,
) -> EvaluationDecision:
    """Solicita al LLM una EvaluationDecision y valida sus limites."""

    payload = llm_client.complete_json(
        _evaluator_messages(state, memory_context=memory_context),
        json_schema=EvaluationDecision.model_json_schema(),
    )
    decision = EvaluationDecision.model_validate(payload)
    _validate_evaluation_decision_bounds(
        state,
        decision,
        memory_context=memory_context,
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
        run_id=state.run_id,
        decision_id=f"{state.run_id}:evaluator:{_evaluator_turn(state):03d}",
        decision_context={
            "current_stage": state.current_stage,
            "recall": None if state.metrics is None else state.metrics.recall,
            "f1_score": None if state.metrics is None else state.metrics.f1_score,
            "false_positive_rate": (
                None if state.metrics is None else state.metrics.false_positive_rate
            ),
            "supervision_profile": state.project_context.supervision_profile,
            "label_source": state.project_context.label_source,
            "degradation_available": _metric_extra_bool(
                state.metrics,
                "degradation_available",
            ),
            "degradation_detected_before_failure_rate": _metric_extra_float(
                state.metrics,
                "degradation_detected_before_failure_rate",
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
                    "- evaluation debe validar contra EvaluationResult.",
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
                    f"- decision_id debe ser: {state.run_id}:evaluator:{_evaluator_turn(state):03d}",
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
    }
    template.update(memory_usage_json_template(memory_context))
    return template


def _state_summary_for_llm(state: TFMStateModel) -> dict[str, Any]:
    return {
        "thread_id": state.thread_id,
        "run_id": state.run_id,
        "current_stage": state.current_stage,
        "dataset": state.project_context.dataset,
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


def _validate_evaluation_decision_bounds(
    state: TFMStateModel,
    decision: EvaluationDecision,
    *,
    memory_context: RetrievedMemoryContext | None = None,
) -> None:
    if _uses_temporal_degradation_profile(state):
        if decision.min_recall_required is not None:
            raise ValueError("run-to-failure evaluation must not require recall threshold")
        if decision.max_false_positive_rate is not None:
            raise ValueError("run-to-failure evaluation must not require binary FPR threshold")
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


def _profile_specific_rules(state: TFMStateModel) -> list[str]:
    if _uses_temporal_degradation_profile(state):
        return [
            "- min_recall_required debe ser null para perfiles run-to-failure.",
            "- max_false_positive_rate debe ser null para perfiles run-to-failure.",
            (
                "- approved debe basarse en degradation_metrics: deteccion antes "
                "de fallo, falsas alarmas nominales y tendencia del score."
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
    detection_rate = _metric_extra_float(
        metrics,
        "degradation_detected_before_failure_rate",
    )
    mean_lead_time = _metric_extra_float(
        metrics,
        "degradation_mean_lead_time_to_failure",
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
        return "No hay metricas disponibles para aprobar la ejecucion."
    if _uses_temporal_degradation_profile(state):
        status = "aprobada" if approved else "completada con metricas temporales insuficientes"
        return (
            f"Ejecucion run-to-failure {status}: "
            "lead_time_medio="
            f"{_format_metric(_metric_extra_float(state.metrics, 'degradation_mean_lead_time_to_failure'))}, "
            "FAR_nominal="
            f"{_format_metric(_metric_extra_float(state.metrics, 'degradation_mean_false_alarm_rate_nominal'))}, "
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
                "Las metricas temporales no cumplen los criterios minimos de alerta temprana, falsas alarmas y tendencia."
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
        return (
            "Fallback run-to-failure evaluation policy: judge temporal "
            "degradation metrics such as early detection, nominal false alarms "
            "and score trend; binary F1 is treated only as auxiliary/proxy."
        )
    return (
        "Fallback binary evaluation policy: approve only if recall and false "
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


def _metric_extra_bool(metrics: MetricsReport | None, key: str) -> bool:
    if metrics is None:
        return False
    return metrics.extra.get(key) is True


def _format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _evaluator_turn(state: TFMStateModel) -> int:
    return 1 + sum(message.name == "evaluator" for message in state.messages)
