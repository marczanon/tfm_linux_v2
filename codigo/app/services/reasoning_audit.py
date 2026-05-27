"""Post-mortem de razonamiento agentico y revision humana opcional."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from codigo.app.schemas.agent_decisions import ModelingRetryDecision
from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.reasoning import (
    AgentReasoningPostmortem,
    HumanReasoningReviewRequest,
    ReasoningMetricDelta,
)
from codigo.app.schemas.state import EvaluationResult, MetricsReport

MAX_FALSE_POSITIVE_RATE = 0.10


class ReasoningAuditArtifacts(StrictBaseModel):
    """Artefactos escritos por la auditoria de razonamiento."""

    postmortem_path: str
    report_path: str
    review_request_path: str | None = None
    review_report_path: str | None = None
    review_template_path: str | None = None
    postmortem: AgentReasoningPostmortem
    review_request: HumanReasoningReviewRequest | None = None


def build_modeling_retry_postmortem(
    *,
    source_run_id: str,
    run_id: str,
    decision: ModelingRetryDecision,
    before_metrics: MetricsReport | None,
    after_metrics: MetricsReport | None,
    evaluation: EvaluationResult | None,
    request_human_review: bool = False,
) -> AgentReasoningPostmortem:
    """Construye una auditoria de hipotesis, accion y resultado real."""

    before = _metrics_dict(before_metrics)
    after = _metrics_dict(after_metrics)
    deltas = _metric_deltas(before, after)
    outcome = _reasoning_outcome(
        deltas,
        after,
        approved=False if evaluation is None else evaluation.approved,
    )
    threshold_quantile = _threshold_quantile(decision)
    return AgentReasoningPostmortem(
        postmortem_id=f"{run_id}:reasoning_postmortem:{decision.attempt_number:03d}",
        run_id=run_id,
        source_run_id=source_run_id,
        agent_name=decision.agent_name,
        decision_id=decision.decision_id,
        attempt_number=decision.attempt_number,
        max_attempts=decision.max_attempts,
        hypothesis=decision.learning_summary,
        action_taken=_action_taken(decision, threshold_quantile),
        expected_effect=decision.expected_effect,
        evidence_used=decision.evidence_used,
        before_metrics=before,
        after_metrics=after,
        metric_deltas=deltas,
        outcome=outcome,
        automatic_critique=_automatic_critique(
            outcome,
            before=before,
            after=after,
            threshold_quantile=threshold_quantile,
            evaluation=evaluation,
        ),
        reusable_lessons=_reusable_lessons(outcome),
        requires_human_review=request_human_review,
        human_review_status=(
            "pending_human_review" if request_human_review else "not_requested"
        ),
    )


def write_reasoning_postmortem(
    postmortem: AgentReasoningPostmortem,
    output_dir: str | Path,
    *,
    request_human_review: bool = False,
    reviewer_hint: str | None = None,
) -> ReasoningAuditArtifacts:
    """Persiste post-mortem, informe legible y solicitud humana opcional."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    postmortem_path = output / "reasoning_postmortem.json"
    report_path = output / "reasoning_postmortem.md"
    postmortem_path.write_text(
        json.dumps(postmortem.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    report_path.write_text(_postmortem_markdown(postmortem), encoding="utf-8")

    review_request = None
    review_request_path = None
    review_report_path = None
    review_template_path = None
    if request_human_review:
        review_request = _review_request(postmortem, reviewer_hint)
        review_request_path = output / "human_reasoning_review_request.json"
        review_report_path = output / "human_reasoning_review_request.md"
        review_template_path = output / "human_reasoning_review_template.json"
        review_request_path.write_text(
            json.dumps(review_request.model_dump(mode="json"), indent=2),
            encoding="utf-8",
        )
        review_report_path.write_text(
            _review_request_markdown(postmortem, review_request),
            encoding="utf-8",
        )
        review_template_path.write_text(
            json.dumps(_human_review_template(postmortem), indent=2),
            encoding="utf-8",
        )

    return ReasoningAuditArtifacts(
        postmortem_path=postmortem_path.as_posix(),
        report_path=report_path.as_posix(),
        review_request_path=(
            None if review_request_path is None else review_request_path.as_posix()
        ),
        review_report_path=(
            None if review_report_path is None else review_report_path.as_posix()
        ),
        review_template_path=(
            None if review_template_path is None else review_template_path.as_posix()
        ),
        postmortem=postmortem,
        review_request=review_request,
    )


def _metrics_dict(metrics: MetricsReport | None) -> dict[str, float | None]:
    if metrics is None:
        return {}
    return {
        "precision": metrics.precision,
        "recall": metrics.recall,
        "f1_score": metrics.f1_score,
        "false_positive_rate": metrics.false_positive_rate,
    }


def _metric_deltas(
    before: dict[str, float | None],
    after: dict[str, float | None],
) -> list[ReasoningMetricDelta]:
    specs = [
        ("precision", True),
        ("recall", True),
        ("f1_score", True),
        ("false_positive_rate", False),
    ]
    return [
        _metric_delta(name, higher_is_better, before.get(name), after.get(name))
        for name, higher_is_better in specs
    ]


def _metric_delta(
    name: str,
    higher_is_better: bool,
    before: float | None,
    after: float | None,
) -> ReasoningMetricDelta:
    delta = None if before is None or after is None else after - before
    improved = None
    if delta is not None:
        improved = delta > 0 if higher_is_better else delta < 0
    return ReasoningMetricDelta(
        metric=name,
        before=before,
        after=after,
        delta=delta,
        higher_is_better=higher_is_better,
        improved=improved,
    )


def _reasoning_outcome(
    deltas: list[ReasoningMetricDelta],
    after: dict[str, float | None],
    *,
    approved: bool,
) -> str:
    if approved:
        return "validated"
    recall_delta = _delta_for(deltas, "recall")
    f1_delta = _delta_for(deltas, "f1_score")
    fpr_after = after.get("false_positive_rate")
    if recall_delta is not None and recall_delta > 0:
        if fpr_after is not None and fpr_after >= 0.5:
            return "overcorrected"
        if f1_delta is not None and f1_delta > 0:
            return "partially_supported"
        return "supported"
    fpr_delta = _delta_for(deltas, "false_positive_rate")
    if recall_delta is not None and recall_delta <= 0 and fpr_delta is not None and fpr_delta >= 0:
        return "contradicted"
    return "inconclusive"


def _automatic_critique(
    outcome: str,
    *,
    before: dict[str, float | None],
    after: dict[str, float | None],
    threshold_quantile: float | None,
    evaluation: EvaluationResult | None,
) -> str:
    before_recall = before.get("recall")
    after_recall = after.get("recall")
    before_fpr = before.get("false_positive_rate")
    after_fpr = after.get("false_positive_rate")
    prefix = "La hipotesis del agente se evalua comparando metricas antes y despues."
    if outcome == "validated":
        return f"{prefix} La ejecucion queda aprobada por el evaluador."
    if outcome == "overcorrected":
        return (
            f"{prefix} La direccion del cambio fue util para recall "
            f"({_fmt(before_recall)} -> {_fmt(after_recall)}), pero la magnitud "
            f"fue excesiva: FPR paso de {_fmt(before_fpr)} a {_fmt(after_fpr)}. "
            "El razonamiento debe tratarse como caso parcialmente correcto, no "
            "como ejemplo positivo sin revision."
        )
    if outcome == "partially_supported":
        return (
            f"{prefix} El cambio mejoro recall y F1, pero no resolvio los "
            "umbrales industriales. Es una hipotesis tecnicamente plausible que "
            "requiere supervision o ajuste mas fino."
        )
    if outcome == "supported":
        return (
            f"{prefix} El cambio produjo mejora en la direccion esperada, aunque "
            "la ejecucion todavia no queda validada."
        )
    if outcome == "contradicted":
        return (
            f"{prefix} Las metricas empeoraron o no mejoraron en la direccion "
            "esperada, por lo que el razonamiento deberia descartarse como "
            "ejemplo de comportamiento deseado."
        )
    summary = "" if evaluation is None else f" Evaluacion: {evaluation.summary}"
    threshold_text = "" if threshold_quantile is None else f" Umbral cuant.: {threshold_quantile}."
    return f"{prefix} No hay evidencia suficiente para clasificarlo.{threshold_text}{summary}"


def _reusable_lessons(outcome: str) -> list[str]:
    if outcome == "validated":
        return ["usable_as_positive_reasoning_example"]
    if outcome == "overcorrected":
        return [
            "direction_can_be_correct_while_magnitude_is_unsafe",
            "do_not_optimize_recall_without_fpr_control",
        ]
    if outcome == "partially_supported":
        return [
            "threshold_adjustment_can_reduce_false_negatives",
            "requires_human_review_before_reuse",
        ]
    if outcome == "contradicted":
        return ["candidate_negative_reasoning_example"]
    return ["requires_more_evidence"]


def _action_taken(
    decision: ModelingRetryDecision,
    threshold_quantile: float | None,
) -> str:
    if decision.retry_config is None:
        return "No retry config was executed."
    threshold_text = (
        "without explicit threshold_quantile"
        if threshold_quantile is None
        else f"with threshold_quantile={threshold_quantile}"
    )
    return (
        f"Run {decision.retry_config.model_name} "
        f"{threshold_text}; should_retry={decision.should_retry}."
    )


def _threshold_quantile(decision: ModelingRetryDecision) -> float | None:
    if decision.retry_config is None:
        return None
    value = decision.retry_config.hyperparameters.get("threshold_quantile")
    return None if value is None else float(value)


def _delta_for(deltas: list[ReasoningMetricDelta], metric: str) -> float | None:
    for delta in deltas:
        if delta.metric == metric:
            return delta.delta
    return None


def _postmortem_markdown(postmortem: AgentReasoningPostmortem) -> str:
    lines = [
        f"# Post-mortem de razonamiento {postmortem.run_id}",
        "",
        f"- Run origen: `{postmortem.source_run_id}`",
        f"- Decision: `{postmortem.decision_id}`",
        f"- Intento: `{postmortem.attempt_number}/{postmortem.max_attempts}`",
        f"- Resultado del razonamiento: `{postmortem.outcome}`",
        f"- Revision humana: `{postmortem.human_review_status}`",
        "",
        "## Hipotesis del agente",
        "",
        postmortem.hypothesis,
        "",
        "## Accion ejecutada",
        "",
        postmortem.action_taken,
        "",
        "## Efecto esperado",
        "",
        postmortem.expected_effect or "n/a",
        "",
        "## Resultado observado",
        "",
        "| Metrica | Antes | Despues | Delta | Mejora |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for delta in postmortem.metric_deltas:
        lines.append(
            "| "
            f"{delta.metric} | {_fmt(delta.before)} | {_fmt(delta.after)} | "
            f"{_fmt(delta.delta)} | {_bool_text(delta.improved)} |"
        )
    lines.extend(
        [
            "",
            "## Critica automatica",
            "",
            postmortem.automatic_critique,
            "",
            "## Lecciones reutilizables",
            "",
            *[f"- `{lesson}`" for lesson in postmortem.reusable_lessons],
            "",
        ]
    )
    return "\n".join(lines)


def _review_request(
    postmortem: AgentReasoningPostmortem,
    reviewer_hint: str | None,
) -> HumanReasoningReviewRequest:
    return HumanReasoningReviewRequest(
        request_id=f"{postmortem.postmortem_id}:human_review_request",
        postmortem_id=postmortem.postmortem_id,
        run_id=postmortem.run_id,
        decision_id=postmortem.decision_id,
        reviewer_hint=reviewer_hint,
        questions=[
            "La evidencia citada justifica el cambio propuesto?",
            "La direccion del cambio fue correcta?",
            "La magnitud del cambio fue segura para un contexto industrial?",
            "Debe reutilizarse este caso como contexto positivo, negativo o caso frontera?",
        ],
    )


def _review_request_markdown(
    postmortem: AgentReasoningPostmortem,
    request: HumanReasoningReviewRequest,
) -> str:
    return "\n".join(
        [
            f"# Revision humana del razonamiento {postmortem.run_id}",
            "",
            f"- Solicitud: `{request.request_id}`",
            f"- Post-mortem: `{postmortem.postmortem_id}`",
            f"- Decision: `{postmortem.decision_id}`",
            f"- Resultado automatico: `{postmortem.outcome}`",
            "",
            "## Preguntas",
            "",
            *[f"- {question}" for question in request.questions],
            "",
            "## Veredictos permitidos",
            "",
            *[f"- `{verdict}`" for verdict in request.allowed_verdicts],
            "",
            "## Uso posterior",
            "",
            (
                "El veredicto humano debe usarse como memoria supervisada para "
                "contexto, RAG o filtrado de patrones; no cambia las metricas "
                "ni aprueba retrospectivamente la run."
            ),
            "",
        ]
    )


def _human_review_template(postmortem: AgentReasoningPostmortem) -> dict[str, Any]:
    return {
        "review_id": f"{postmortem.postmortem_id}:human_review:001",
        "postmortem_id": postmortem.postmortem_id,
        "run_id": postmortem.run_id,
        "decision_id": postmortem.decision_id,
        "reviewer": "pendiente",
        "verdict": "needs_more_evidence",
        "rationale": "pendiente",
        "reusable_as_context": False,
        "exclude_from_context": False,
        "tags": [],
    }


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _bool_text(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "si" if value else "no"
