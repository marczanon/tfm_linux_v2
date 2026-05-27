"""Auditoria del uso de memoria RAG en decisiones agenticas."""

from __future__ import annotations

import json
import re
from pathlib import Path

from codigo.app.schemas.agent_decisions import ModelingRetryDecision
from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.reasoning import (
    MemoryUsageAudit,
    MemoryUsageAuditItem,
    RetrievedMemoryContext,
)
from codigo.app.schemas.state import MetricsReport

REPEATED_FAILURE_FPR_THRESHOLD = 0.5


class MemoryUsageAuditArtifacts(StrictBaseModel):
    """Artefactos persistidos para auditar uso de memoria."""

    audit_path: str
    report_path: str
    audit: MemoryUsageAudit


def build_modeling_retry_memory_usage_audit(
    *,
    run_id: str,
    decision: ModelingRetryDecision,
    memory_context: RetrievedMemoryContext | None,
    before_metrics: MetricsReport | None,
    after_metrics: MetricsReport | None,
) -> MemoryUsageAudit:
    """Contrasta lo que el agente dijo hacer con la memoria y el resultado."""

    before = _metrics_dict(before_metrics)
    after = _metrics_dict(after_metrics)
    retrieved_ids = (
        []
        if memory_context is None
        else [item.record.memory_record_id for item in memory_context.items]
    )
    cited_ids = decision.memory_record_ids
    retrieved_set = set(retrieved_ids)
    cited_set = set(cited_ids)
    uncited = sorted(retrieved_set - cited_set)
    cited_without_retrieval = sorted(cited_set - retrieved_set)

    reasoning_issue = _reasoning_inconsistency(decision)
    items = _audit_items(
        decision=decision,
        memory_context=memory_context,
        after=after,
        cited_without_retrieval=cited_without_retrieval,
        reasoning_issue=reasoning_issue,
    )
    outcome = _audit_outcome(decision, items, cited_without_retrieval)
    summary = _audit_summary(
        outcome,
        used_memory_context=decision.used_memory_context,
        retrieved_count=len(retrieved_ids),
        cited_count=len(cited_ids),
    )
    return MemoryUsageAudit(
        audit_id=f"{run_id}:memory_usage_audit:{decision.attempt_number:03d}",
        run_id=run_id,
        decision_id=decision.decision_id,
        memory_context_id=decision.memory_context_id,
        used_memory_context=decision.used_memory_context,
        memory_usage_summary=decision.memory_usage_summary,
        retrieved_memory_record_ids=retrieved_ids,
        cited_memory_record_ids=cited_ids,
        uncited_retrieved_record_ids=uncited,
        cited_without_retrieval=cited_without_retrieval,
        before_metrics=before,
        after_metrics=after,
        outcome=outcome,
        summary=summary,
        items=items,
    )


def write_memory_usage_audit(
    audit: MemoryUsageAudit,
    output_dir: str | Path,
) -> MemoryUsageAuditArtifacts:
    """Persiste auditoria en JSON y Markdown legible."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    audit_path = output / "memory_usage_audit.json"
    report_path = output / "memory_usage_audit.md"
    audit_path.write_text(
        json.dumps(audit.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    report_path.write_text(_audit_markdown(audit), encoding="utf-8")
    return MemoryUsageAuditArtifacts(
        audit_path=audit_path.as_posix(),
        report_path=report_path.as_posix(),
        audit=audit,
    )


def _audit_items(
    *,
    decision: ModelingRetryDecision,
    memory_context: RetrievedMemoryContext | None,
    after: dict[str, float | None],
    cited_without_retrieval: list[str],
    reasoning_issue: str | None,
) -> list[MemoryUsageAuditItem]:
    uses_by_id = {item.memory_record_id: item for item in decision.memory_record_uses}
    context_items = [] if memory_context is None else memory_context.items
    audit_items: list[MemoryUsageAuditItem] = []
    for item in context_items:
        record = item.record
        use = uses_by_id.get(record.memory_record_id)
        cited = record.memory_record_id in decision.memory_record_ids
        assessment, reason = _assessment_for_retrieved_item(
            cited=cited,
            declared_usage=None if use is None else use.usage,
            memory_role=record.memory_role,
            memory_outcome=record.outcome,
            after=after,
            reasoning_issue=reasoning_issue,
        )
        audit_items.append(
            MemoryUsageAuditItem(
                memory_record_id=record.memory_record_id,
                retrieval_use=item.retrieval_use,
                memory_role=record.memory_role,
                human_verdict=record.human_verdict,
                memory_outcome=record.outcome,
                cited_by_agent=cited,
                declared_usage=None if use is None else use.usage,
                influence_summary=None if use is None else use.influence_summary,
                risk_mitigation=None if use is None else use.risk_mitigation,
                assessment=assessment,
                assessment_reason=reason,
            )
        )
    for memory_record_id in cited_without_retrieval:
        audit_items.append(
            MemoryUsageAuditItem(
                memory_record_id=memory_record_id,
                cited_by_agent=True,
                assessment="cited_without_retrieval",
                assessment_reason=(
                    "El agente cito un recuerdo que no aparece en el contexto "
                    "recuperado para esta decision."
                ),
            )
        )
    return audit_items


def _assessment_for_retrieved_item(
    *,
    cited: bool,
    declared_usage: str | None,
    memory_role: str,
    memory_outcome: str | None,
    after: dict[str, float | None],
    reasoning_issue: str | None,
) -> tuple[str, str]:
    if not cited:
        return (
            "uncited_retrieved_memory",
            "El recuerdo fue recuperado, pero el agente no lo cito como usado.",
        )
    if declared_usage == "ignored":
        return (
            "ignored_retrieved_memory",
            "El agente declaro que leyo el recuerdo pero decidio no usarlo.",
        )
    if declared_usage == "contradicted":
        return (
            "contradicted_memory",
            "El agente declaro que contradijo el recuerdo recuperado.",
        )
    if reasoning_issue:
        return (
            "reasoning_inconsistent",
            reasoning_issue,
        )
    if (
        memory_role in {"boundary_case", "warning"}
        or memory_outcome == "overcorrected"
    ) and _false_positive_rate(after) >= REPEATED_FAILURE_FPR_THRESHOLD:
        return (
            "repeated_boundary_failure",
            (
                "El recuerdo advertia un caso frontera o sobrecorreccion, pero "
                "la ejecucion resultante mantiene una FPR excesiva."
            ),
        )
    return (
        "aligned",
        "No se detecta contradiccion automatica entre el recuerdo y el resultado.",
    )


def _audit_outcome(
    decision: ModelingRetryDecision,
    items: list[MemoryUsageAuditItem],
    cited_without_retrieval: list[str],
) -> str:
    if not decision.used_memory_context:
        return "memory_not_used"
    if cited_without_retrieval:
        return "inconclusive"
    assessments = {item.assessment for item in items}
    if "repeated_boundary_failure" in assessments:
        return "memory_repeated_boundary_failure"
    if "reasoning_inconsistent" in assessments:
        return "memory_reasoning_inconsistent"
    if "contradicted_memory" in assessments:
        return "memory_contradicted"
    if "ignored_retrieved_memory" in assessments:
        return "memory_ignored"
    if "aligned" in assessments:
        return "memory_aligned"
    return "inconclusive"


def _audit_summary(
    outcome: str,
    *,
    used_memory_context: bool,
    retrieved_count: int,
    cited_count: int,
) -> str:
    if not used_memory_context:
        return "El agente no declaro uso de memoria en esta decision."
    if outcome == "memory_repeated_boundary_failure":
        return (
            "El agente recupero y cito memoria, pero el resultado repitio un "
            "fallo asociado a un caso frontera o advertencia."
        )
    if outcome == "memory_reasoning_inconsistent":
        return (
            "El agente recupero y cito memoria, pero su razonamiento contiene "
            "una inconsistencia numerica o direccional que debe revisarse."
        )
    if outcome == "memory_aligned":
        return "El uso declarado de memoria no contradice la evidencia automatica."
    if outcome == "memory_ignored":
        return "El agente recupero memoria, pero declaro ignorarla total o parcialmente."
    if outcome == "memory_contradicted":
        return "El agente declaro contradecir memoria recuperada."
    return (
        f"Uso de memoria inconcluso: {retrieved_count} recuerdos recuperados y "
        f"{cited_count} citados."
    )


def _audit_markdown(audit: MemoryUsageAudit) -> str:
    lines = [
        f"# Auditoria de uso de memoria {audit.run_id}",
        "",
        f"- Decision: `{audit.decision_id}`",
        f"- Contexto de memoria: `{audit.memory_context_id or 'n/a'}`",
        f"- Memoria usada por el agente: `{audit.used_memory_context}`",
        f"- Resultado de auditoria: `{audit.outcome}`",
        f"- Resumen: {audit.summary}",
        "",
        "## Declaracion del agente",
        "",
        audit.memory_usage_summary or "n/a",
        "",
        "## Recuerdos",
        "",
        "| Recuerdo | Uso declarado | Evaluacion | Motivo |",
        "| --- | --- | --- | --- |",
    ]
    for item in audit.items:
        lines.append(
            "| "
            f"`{item.memory_record_id}` | "
            f"`{item.declared_usage or 'n/a'}` | "
            f"`{item.assessment}` | "
            f"{item.assessment_reason} |"
        )
    lines.extend(
        [
            "",
            "## Metricas",
            "",
            f"- Recall antes/despues: `{_fmt(audit.before_metrics.get('recall'))}` -> `{_fmt(audit.after_metrics.get('recall'))}`",
            f"- FPR antes/despues: `{_fmt(audit.before_metrics.get('false_positive_rate'))}` -> `{_fmt(audit.after_metrics.get('false_positive_rate'))}`",
            "",
        ]
    )
    return "\n".join(lines)


def _metrics_dict(metrics: MetricsReport | None) -> dict[str, float | None]:
    if metrics is None:
        return {}
    return {
        "precision": metrics.precision,
        "recall": metrics.recall,
        "f1_score": metrics.f1_score,
        "false_positive_rate": metrics.false_positive_rate,
    }


def _false_positive_rate(metrics: dict[str, float | None]) -> float:
    value = metrics.get("false_positive_rate")
    return 0.0 if value is None else value


def _reasoning_inconsistency(decision: ModelingRetryDecision) -> str | None:
    text = _decision_reasoning_text(decision).lower()
    issue = _numeric_comparison_issue(text)
    if issue is not None:
        return issue
    if _quantile_low_claim_issue(text):
        return (
            "El razonamiento describe threshold_quantile=0.99 como bajo, "
            "aunque 0.99 es un cuantil alto y conservador."
        )
    return None


def _decision_reasoning_text(decision: ModelingRetryDecision) -> str:
    parts = [
        decision.rationale,
        decision.learning_summary,
        decision.expected_effect or "",
        decision.memory_usage_summary or "",
    ]
    for use in decision.memory_record_uses:
        parts.append(use.influence_summary)
        parts.append(use.risk_mitigation or "")
    return "\n".join(parts)


def _numeric_comparison_issue(text: str) -> str | None:
    number = r"(?P<{name}>0(?:\.\d+)?|1(?:\.0+)?|[1-9]\d*(?:\.\d+)?)"
    relation_patterns = [
        (
            "mayor",
            re.compile(
                number.format(name="left")
                + r"\s*(?:es\s+|\()?\s*(?:mayor|superior|mas alto|más alto)"
                + r"\s+que\s*"
                + number.format(name="right")
            ),
        ),
        (
            "menor",
            re.compile(
                number.format(name="left")
                + r"\s*(?:es\s+|\()?\s*(?:menor|inferior|mas bajo|más bajo)"
                + r"\s+que\s*"
                + number.format(name="right")
            ),
        ),
    ]
    for relation, pattern in relation_patterns:
        for match in pattern.finditer(text):
            left = float(match.group("left"))
            right = float(match.group("right"))
            if relation == "mayor" and left <= right:
                return f"El razonamiento afirma que {left:g} es mayor que {right:g}."
            if relation == "menor" and left >= right:
                return f"El razonamiento afirma que {left:g} es menor que {right:g}."
    return None


def _quantile_low_claim_issue(text: str) -> bool:
    patterns = [
        r"(?:umbral|quantile|cuantil)[^.\n]{0,40}(?:bajo|baja|low)[^.\n]{0,20}\(?0\.99\)?",
        r"0\.99\s*(?:es\s+)?(?:un\s+)?(?:umbral|quantile|cuantil)?\s*(?:muy\s+)?(?:bajo|baja|low)",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def _fmt(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"
