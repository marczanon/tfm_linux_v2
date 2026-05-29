"""Auditoria cualitativa de memoria transversal en structurer/evaluator."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.reasoning import MemoryCandidate, RetrievedMemoryContext
from codigo.app.schemas.state import TFMStateModel
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR, load_run_snapshot

TransversalMemoryAgent = Literal["structurer", "evaluator"]
TransversalMemoryAuditOutcome = Literal[
    "memory_aligned",
    "memory_not_used",
    "memory_usage_invalid",
    "memory_policy_warning",
]


class AgentTransversalMemoryAudit(StrictBaseModel):
    """Auditoria de una decision agentica con memoria transversal."""

    agent_name: TransversalMemoryAgent
    decision_id: str = Field(min_length=1)
    used_memory_context: bool
    memory_context_id: str | None = Field(default=None, min_length=1)
    retrieved_memory_record_ids: list[str] = Field(default_factory=list)
    cited_memory_record_ids: list[str] = Field(default_factory=list)
    cited_without_retrieval: list[str] = Field(default_factory=list)
    missing_usage_declarations: list[str] = Field(default_factory=list)
    uncited_retrieved_record_ids: list[str] = Field(default_factory=list)
    outcome: TransversalMemoryAuditOutcome
    context_reuse_allowed: bool
    principal_evidence_requires_human_review: bool
    summary: str = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)


class TransversalMemoryAuditReport(StrictBaseModel):
    """Informe agregado para una run con memoria transversal."""

    report_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    overall_outcome: TransversalMemoryAuditOutcome
    approved: bool | None = None
    metrics: dict[str, float | None] = Field(default_factory=dict)
    agent_audits: list[AgentTransversalMemoryAudit] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TransversalMemoryAuditArtifacts(StrictBaseModel):
    """Artefactos escritos por la auditoria transversal."""

    audit_path: str
    report_path: str
    audit: TransversalMemoryAuditReport


def build_transversal_memory_audit(
    state: TFMStateModel,
) -> TransversalMemoryAuditReport:
    """Construye la auditoria para estructurador y evaluador de una run."""

    agent_audits = [
        audit
        for agent in ("structurer", "evaluator")
        if (audit := _agent_audit(state, agent)) is not None
    ]
    return TransversalMemoryAuditReport(
        report_id=f"{state.run_id}:transversal_memory_audit",
        run_id=state.run_id,
        dataset=state.project_context.dataset,
        approved=None if state.evaluation is None else state.evaluation.approved,
        metrics=_metrics_dict(state),
        overall_outcome=_overall_outcome(agent_audits),
        agent_audits=agent_audits,
    )


def audit_transversal_memory_run(
    *,
    run_id: str,
    runs_dir: str | Path = DEFAULT_RUNS_DIR,
    output_dir: str | Path | None = None,
) -> TransversalMemoryAuditArtifacts:
    """Carga una run persistida, audita memoria transversal y escribe artefactos."""

    snapshot = load_run_snapshot(run_id, runs_dir)
    state = TFMStateModel.model_validate(
        json.loads(Path(snapshot.state_path).read_text(encoding="utf-8"))
    )
    audit = build_transversal_memory_audit(state)
    target_dir = (
        Path(output_dir)
        if output_dir is not None
        else Path("codigo/reports")
        / state.project_context.dataset
        / state.run_id
        / "agent_memory"
        / "audit"
    )
    return write_transversal_memory_audit(audit, target_dir)


def write_transversal_memory_audit(
    audit: TransversalMemoryAuditReport,
    output_dir: str | Path,
) -> TransversalMemoryAuditArtifacts:
    """Persiste la auditoria transversal en JSON y Markdown."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    audit_path = output / "transversal_memory_audit.json"
    report_path = output / "transversal_memory_audit.md"
    audit_path.write_text(
        json.dumps(audit.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    report_path.write_text(_audit_markdown(audit), encoding="utf-8")
    return TransversalMemoryAuditArtifacts(
        audit_path=audit_path.as_posix(),
        report_path=report_path.as_posix(),
        audit=audit,
    )


def _agent_audit(
    state: TFMStateModel,
    agent_name: TransversalMemoryAgent,
) -> AgentTransversalMemoryAudit | None:
    decision = _latest_agent_decision(state, agent_name)
    if decision is None:
        return None
    context = _load_memory_context(state, agent_name)
    candidate = _load_memory_candidate(state, agent_name)
    retrieved_ids = (
        [] if context is None else [item.record.memory_record_id for item in context.items]
    )
    cited_ids = [str(item) for item in decision.get("memory_record_ids", [])]
    declared_use_ids = [
        str(item.get("memory_record_id"))
        for item in decision.get("memory_record_uses", [])
        if isinstance(item, dict) and item.get("memory_record_id")
    ]
    cited_without_retrieval = sorted(set(cited_ids) - set(retrieved_ids))
    missing_usage = sorted(set(cited_ids) - set(declared_use_ids))
    uncited = sorted(set(retrieved_ids) - set(cited_ids))
    notes = _policy_notes(
        state=state,
        agent_name=agent_name,
        decision=decision,
        context=context,
        candidate=candidate,
    )
    outcome = _agent_outcome(
        used_memory_context=bool(decision.get("used_memory_context")),
        context=context,
        cited_ids=cited_ids,
        cited_without_retrieval=cited_without_retrieval,
        missing_usage=missing_usage,
        notes=notes,
    )
    context_reuse_allowed = (
        outcome == "memory_aligned"
        and candidate is not None
        and candidate.reusable_as_context
        and not candidate.exclude_from_context
    )
    needs_human_review = (
        context_reuse_allowed
        and candidate is not None
        and candidate.human_verdict is None
    )
    return AgentTransversalMemoryAudit(
        agent_name=agent_name,
        decision_id=str(decision.get("decision_id", "unknown")),
        used_memory_context=bool(decision.get("used_memory_context")),
        memory_context_id=decision.get("memory_context_id"),
        retrieved_memory_record_ids=retrieved_ids,
        cited_memory_record_ids=cited_ids,
        cited_without_retrieval=cited_without_retrieval,
        missing_usage_declarations=missing_usage,
        uncited_retrieved_record_ids=uncited,
        outcome=outcome,
        context_reuse_allowed=context_reuse_allowed,
        principal_evidence_requires_human_review=needs_human_review,
        summary=_agent_summary(agent_name, outcome, context_reuse_allowed, needs_human_review),
        notes=notes,
    )


def _agent_outcome(
    *,
    used_memory_context: bool,
    context: RetrievedMemoryContext | None,
    cited_ids: list[str],
    cited_without_retrieval: list[str],
    missing_usage: list[str],
    notes: list[str],
) -> TransversalMemoryAuditOutcome:
    if not used_memory_context:
        return "memory_not_used"
    if context is None or not cited_ids or cited_without_retrieval or missing_usage:
        return "memory_usage_invalid"
    if any(note.startswith("policy_warning:") for note in notes):
        return "memory_policy_warning"
    return "memory_aligned"


def _policy_notes(
    *,
    state: TFMStateModel,
    agent_name: TransversalMemoryAgent,
    decision: dict[str, Any],
    context: RetrievedMemoryContext | None,
    candidate: MemoryCandidate | None,
) -> list[str]:
    notes: list[str] = []
    if context is not None:
        mismatched = [
            item.record.memory_record_id
            for item in context.items
            if item.record.target_agent not in {agent_name, "shared_methodology"}
        ]
        if mismatched:
            notes.append("policy_warning:retrieved_memory_target_mismatch")
        dataset_mismatch = [
            item.record.memory_record_id
            for item in context.items
            if item.record.dataset not in {None, state.project_context.dataset}
        ]
        if dataset_mismatch:
            notes.append("policy_warning:retrieved_memory_dataset_mismatch")
    if candidate is not None and candidate.target_agent != agent_name:
        notes.append("policy_warning:candidate_target_mismatch")
    if agent_name == "evaluator":
        notes.extend(_evaluator_policy_notes(state, decision))
    return notes


def _evaluator_policy_notes(
    state: TFMStateModel,
    decision: dict[str, Any],
) -> list[str]:
    metrics = state.metrics
    if metrics is None:
        return ["policy_warning:evaluator_without_metrics"]
    approved = bool(decision.get("evaluation", {}).get("approved"))
    min_recall = decision.get("min_recall_required")
    max_fpr = decision.get("max_false_positive_rate")
    recall_ok = min_recall is None or (
        metrics.recall is not None and metrics.recall >= float(min_recall)
    )
    fpr_ok = max_fpr is None or (
        metrics.false_positive_rate is not None
        and metrics.false_positive_rate <= float(max_fpr)
    )
    if approved and not (recall_ok and fpr_ok):
        return ["policy_warning:evaluator_approved_without_metric_support"]
    if approved and recall_ok and fpr_ok:
        return ["metric_policy:approval_supported_by_current_metrics"]
    return []


def _latest_agent_decision(
    state: TFMStateModel,
    agent_name: TransversalMemoryAgent,
) -> dict[str, Any] | None:
    for message in reversed(state.messages):
        if message.role != "agent" or message.name != agent_name:
            continue
        try:
            payload = json.loads(message.content)
        except json.JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None
    return None


def _load_memory_context(
    state: TFMStateModel,
    agent_name: TransversalMemoryAgent,
) -> RetrievedMemoryContext | None:
    path = _artifact_path(state, f"{agent_name}_retrieved_memory_context")
    if path is None:
        return None
    return RetrievedMemoryContext.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def _load_memory_candidate(
    state: TFMStateModel,
    agent_name: TransversalMemoryAgent,
) -> MemoryCandidate | None:
    path = _artifact_path(state, f"{agent_name}_memory_candidate")
    if path is None:
        return None
    return MemoryCandidate.model_validate_json(
        Path(path).read_text(encoding="utf-8")
    )


def _artifact_path(state: TFMStateModel, name: str) -> str | None:
    matches = [artifact.path for artifact in state.artifacts if artifact.name == name]
    return matches[-1] if matches else None


def _overall_outcome(
    agent_audits: list[AgentTransversalMemoryAudit],
) -> TransversalMemoryAuditOutcome:
    outcomes = {audit.outcome for audit in agent_audits}
    if "memory_usage_invalid" in outcomes:
        return "memory_usage_invalid"
    if "memory_policy_warning" in outcomes:
        return "memory_policy_warning"
    if outcomes == {"memory_aligned"}:
        return "memory_aligned"
    if "memory_aligned" in outcomes:
        return "memory_aligned"
    return "memory_not_used"


def _metrics_dict(state: TFMStateModel) -> dict[str, float | None]:
    metrics = state.metrics
    if metrics is None:
        return {}
    return {
        "precision": metrics.precision,
        "recall": metrics.recall,
        "f1_score": metrics.f1_score,
        "false_positive_rate": metrics.false_positive_rate,
    }


def _agent_summary(
    agent_name: str,
    outcome: str,
    context_reuse_allowed: bool,
    needs_human_review: bool,
) -> str:
    if outcome == "memory_aligned" and context_reuse_allowed:
        if needs_human_review:
            return (
                f"{agent_name} uso la memoria recuperada de forma consistente; "
                "la reutilizacion como contexto queda permitida, pero se "
                "recomienda revision humana antes de tratar el candidato como "
                "evidencia academica principal."
            )
        return f"{agent_name} uso la memoria recuperada de forma consistente."
    if outcome == "memory_not_used":
        return f"{agent_name} no declaro uso de memoria recuperada."
    if outcome == "memory_policy_warning":
        return f"{agent_name} uso memoria, pero hay advertencias de politica."
    return f"El uso de memoria de {agent_name} es invalido o incompleto."


def _audit_markdown(audit: TransversalMemoryAuditReport) -> str:
    lines = [
        f"# Auditoria de memoria transversal {audit.run_id}",
        "",
        f"- Dataset: `{audit.dataset}`",
        f"- Resultado global: `{audit.overall_outcome}`",
        f"- Run aprobada: `{audit.approved}`",
        f"- Precision: `{_fmt_metric(audit.metrics.get('precision'))}`",
        f"- Recall: `{_fmt_metric(audit.metrics.get('recall'))}`",
        f"- FPR: `{_fmt_metric(audit.metrics.get('false_positive_rate'))}`",
        "",
        "| Agente | Resultado | Contexto reutilizable | "
        "Revision para evidencia principal | Recuerdos citados |",
        "| --- | --- | --- | --- | --- |",
    ]
    for item in audit.agent_audits:
        lines.append(
            "| "
            f"{item.agent_name} | `{item.outcome}` | "
            f"`{item.context_reuse_allowed}` | "
            f"`{item.principal_evidence_requires_human_review}` | "
            f"{_format_memory_ids(item.cited_memory_record_ids)} |"
        )
    lines.extend(["", "## Notas", ""])
    for item in audit.agent_audits:
        lines.append(f"### {item.agent_name}")
        lines.append("")
        lines.append(item.summary)
        if item.notes:
            lines.extend(["", *[f"- `{note}`" for note in item.notes]])
        lines.append("")
    return "\n".join(lines)


def _fmt_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def _format_memory_ids(memory_ids: list[str]) -> str:
    return ", ".join(f"`{memory_id}`" for memory_id in memory_ids) or "n/a"
