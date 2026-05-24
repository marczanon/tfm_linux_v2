"""Agente evaluador LLM con fallback seguro."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from codigo.app.schemas.agent_decisions import EvaluationDecision
from codigo.app.schemas.state import EvaluationResult, MetricsReport, TFMStateModel
from codigo.app.services.llm import (
    JSONLLMClient,
    LLMCallError,
    LLMMessage,
    get_default_json_llm_client,
)


MIN_RECALL_REQUIRED = 0.90
MAX_FALSE_POSITIVE_RATE = 0.10


def decide_evaluation_action(
    state: TFMStateModel,
    *,
    llm_client: JSONLLMClient | None = None,
    use_llm: bool | None = None,
) -> EvaluationDecision:
    """Interpreta metricas usando LLM cuando este habilitado."""

    should_use_llm = _should_use_llm(llm_client, use_llm)
    if should_use_llm:
        try:
            client = llm_client or get_default_json_llm_client()
            return decide_evaluation_action_with_llm(state, client)
        except (LLMCallError, ValidationError, ValueError) as exc:
            fallback = decide_evaluation_action_deterministic(state)
            fallback.rationale = f"{fallback.rationale} Fallback after LLM failure: {exc}"
            fallback.confidence = min(fallback.confidence, 0.7)
            return fallback

    return decide_evaluation_action_deterministic(state)


def decide_evaluation_action_with_llm(
    state: TFMStateModel,
    llm_client: JSONLLMClient,
) -> EvaluationDecision:
    """Solicita al LLM una EvaluationDecision y valida sus limites."""

    payload = llm_client.complete_json(
        _evaluator_messages(state),
        json_schema=EvaluationDecision.model_json_schema(),
    )
    decision = EvaluationDecision.model_validate(payload)
    _validate_evaluation_decision_bounds(state.metrics, decision)
    return decision


def decide_evaluation_action_deterministic(state: TFMStateModel) -> EvaluationDecision:
    """Fallback reproducible para aprobar o rechazar metricas del MVP."""

    metrics = state.metrics
    approved = _metrics_are_approved(metrics)
    return EvaluationDecision(
        decision_id=f"{state.run_id}:evaluator:{_evaluator_turn(state):03d}",
        rationale=(
            "Fallback CWRU evaluation policy: approve only if recall and false "
            "positive rate satisfy the local MVP thresholds."
        ),
        confidence=1.0,
        evaluation=EvaluationResult(
            approved=approved,
            summary=_evaluation_summary(metrics, approved),
            next_action="continue" if approved else "retry_with_new_config",
            limitations=_evaluation_limitations(metrics, approved),
        ),
        min_recall_required=MIN_RECALL_REQUIRED,
        max_false_positive_rate=MAX_FALSE_POSITIVE_RATE,
    )


def _should_use_llm(
    llm_client: JSONLLMClient | None,
    use_llm: bool | None,
) -> bool:
    if use_llm is not None:
        return use_llm
    if llm_client is not None:
        return True
    return os.getenv("TFM_EVALUATOR_MODE", "").strip().lower() == "llm"


def _evaluator_messages(state: TFMStateModel) -> list[LLMMessage]:
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
                    "Formato JSON esperado:",
                    json.dumps(_evaluator_json_template(state), indent=2, ensure_ascii=True),
                    "",
                    "Reglas:",
                    "- No incluyas texto fuera del JSON.",
                    "- evaluation debe validar contra EvaluationResult.",
                    f"- min_recall_required debe ser {MIN_RECALL_REQUIRED}.",
                    f"- max_false_positive_rate debe ser {MAX_FALSE_POSITIVE_RATE}.",
                    "- approved debe ser true solo si recall y FPR cumplen los umbrales.",
                    "- Si approved es true, next_action debe ser continue.",
                    "- Si approved es false, next_action debe ser retry_with_new_config.",
                    f"- decision_id debe ser: {state.run_id}:evaluator:{_evaluator_turn(state):03d}",
                ]
            ),
        ),
    ]


def _evaluator_json_template(state: TFMStateModel) -> dict[str, Any]:
    approved = _metrics_are_approved(state.metrics)
    return {
        "agent_name": "evaluator",
        "decision_id": f"{state.run_id}:evaluator:{_evaluator_turn(state):03d}",
        "rationale": "Motivo tecnico breve del juicio de evaluacion.",
        "confidence": 0.9,
        "evaluation": {
            "approved": approved,
            "summary": _evaluation_summary(state.metrics, approved),
            "next_action": "continue" if approved else "retry_with_new_config",
            "limitations": _evaluation_limitations(state.metrics, approved),
        },
        "min_recall_required": MIN_RECALL_REQUIRED,
        "max_false_positive_rate": MAX_FALSE_POSITIVE_RATE,
    }


def _state_summary_for_llm(state: TFMStateModel) -> dict[str, Any]:
    return {
        "thread_id": state.thread_id,
        "run_id": state.run_id,
        "current_stage": state.current_stage,
        "dataset": state.project_context.dataset,
        "objective": state.project_context.objective,
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
        except (OSError, json.JSONDecodeError) as exc:
            summary["metrics_file_error"] = str(exc)
    return summary


def _validate_evaluation_decision_bounds(
    metrics: MetricsReport | None,
    decision: EvaluationDecision,
) -> None:
    if decision.min_recall_required != MIN_RECALL_REQUIRED:
        raise ValueError(f"min_recall_required must be {MIN_RECALL_REQUIRED}")
    if decision.max_false_positive_rate != MAX_FALSE_POSITIVE_RATE:
        raise ValueError(
            f"max_false_positive_rate must be {MAX_FALSE_POSITIVE_RATE}"
        )

    expected_approved = _metrics_are_approved(metrics)
    if decision.evaluation.approved != expected_approved:
        raise ValueError("approved does not match deterministic MVP thresholds")
    if expected_approved and decision.evaluation.next_action != "continue":
        raise ValueError("approved evaluations must continue")
    if not expected_approved and decision.evaluation.next_action != "retry_with_new_config":
        raise ValueError("rejected evaluations must request a new config")


def _metrics_are_approved(metrics: MetricsReport | None) -> bool:
    if metrics is None:
        return False
    if metrics.recall is None or metrics.false_positive_rate is None:
        return False
    return (
        metrics.recall >= MIN_RECALL_REQUIRED
        and metrics.false_positive_rate <= MAX_FALSE_POSITIVE_RATE
    )


def _evaluation_summary(metrics: MetricsReport | None, approved: bool) -> str:
    if metrics is None:
        return "No hay metricas disponibles para aprobar la ejecucion."

    status = "aprobada" if approved else "rechazada"
    return (
        f"Ejecucion {status}: recall={_format_metric(metrics.recall)}, "
        f"F1={_format_metric(metrics.f1_score)}, "
        f"FPR={_format_metric(metrics.false_positive_rate)}."
    )


def _evaluation_limitations(
    metrics: MetricsReport | None,
    approved: bool,
) -> list[str]:
    limitations = [
        "La validacion se realiza sobre CWRU, un benchmark controlado.",
        "La generalizacion industrial requiere validar otros datasets y condiciones de carga.",
    ]
    if metrics is None:
        return ["No se han encontrado metricas en el estado."]
    if metrics.recall is None or metrics.false_positive_rate is None:
        limitations.append("Faltan recall o tasa de falsos positivos.")
    elif not approved:
        limitations.append(
            "Las metricas no cumplen los umbrales minimos del MVP local."
        )
    return limitations


def _format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _evaluator_turn(state: TFMStateModel) -> int:
    return 1 + sum(message.name == "evaluator" for message in state.messages)
