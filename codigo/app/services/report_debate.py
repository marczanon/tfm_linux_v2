"""Registro auditable del debate controlado sobre el informe final."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import Field

from codigo.app.schemas.agent_decisions import (
    ReportDecision,
    ReportRevisionDecision,
    ReportVerificationDecision,
    ReportVerificationIssue,
)
from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.reasoning import (
    ReportDebateRecord,
    ReportDebateStatus,
    ReportDebateTurn,
    ReportDebateTurnIntent,
)


class ReportDebateArtifacts(StrictBaseModel):
    """Artefactos persistidos para el debate del informe."""

    debate_path: str = Field(min_length=1)
    report_path: str = Field(min_length=1)
    initial_report_path: str = Field(min_length=1)
    revision_report_paths: list[str] = Field(default_factory=list)
    debate: ReportDebateRecord


def build_report_debate_record(
    *,
    run_id: str,
    initial_report_decision: ReportDecision,
    initial_verification: ReportVerificationDecision,
    final_report_decision: ReportDecision | ReportRevisionDecision,
    final_verification: ReportVerificationDecision,
    revision_decision: ReportRevisionDecision | None = None,
    max_rounds: int = 1,
) -> ReportDebateRecord:
    """Construye el registro JSON del debate sin decidir contenido nuevo."""

    rounds_used = 0 if revision_decision is None else revision_decision.revision_round
    status = _debate_status(
        initial_verification=initial_verification,
        final_verification=final_verification,
        revision_decision=revision_decision,
    )
    unresolved = _issue_summaries(final_verification)
    turns = [
        _initial_writer_turn(run_id, initial_report_decision),
        _verification_turn(
            run_id,
            round_index=0,
            decision=initial_verification,
            intent="verification",
        ),
    ]
    if revision_decision is not None:
        turns.extend(
            [
                _revision_turn(run_id, revision_decision),
                _verification_turn(
                    run_id,
                    round_index=revision_decision.revision_round,
                    decision=final_verification,
                    intent="reverification",
                ),
            ]
        )
    turns.append(
        ReportDebateTurn(
            turn_id=f"{run_id}:report_debate:final",
            round_index=rounds_used,
            speaker_agent="system",
            source_decision_id=final_verification.decision_id,
            intent="final_resolution",
            human_summary=_final_summary(status, final_verification),
            claims_or_objections=unresolved,
            status="verified"
            if status in {"approved_without_revision", "approved_after_revision"}
            else "unresolved",
        )
    )
    return ReportDebateRecord(
        debate_id=f"{run_id}:report_debate:001",
        run_id=run_id,
        initial_report_decision_id=initial_report_decision.decision_id,
        initial_verifier_decision_id=initial_verification.decision_id,
        final_report_decision_id=final_report_decision.decision_id,
        final_verifier_decision_id=final_verification.decision_id,
        status=status,
        max_rounds=max_rounds,
        rounds_used=rounds_used,
        turns=turns,
        final_summary=_final_summary(status, final_verification),
        unresolved_issues=unresolved,
        human_review_recommended=status in {"needs_human_review", "blocked"},
    )


def write_report_debate_artifacts(
    *,
    debate: ReportDebateRecord,
    output_dir: str | Path,
    initial_report_markdown: str,
    revision_markdowns: list[tuple[int, str]] | None = None,
) -> ReportDebateArtifacts:
    """Persiste debate JSON, Markdown humano y versiones de informe."""

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    debate_path = output / "report_debate.json"
    report_path = output / "report_debate.md"
    initial_path = output / "final_report_initial.md"
    initial_path.write_text(initial_report_markdown, encoding="utf-8")

    revision_paths: list[str] = []
    for round_index, content in revision_markdowns or []:
        path = output / f"final_report_revision_{round_index:03d}.md"
        path.write_text(content, encoding="utf-8")
        revision_paths.append(path.as_posix())

    artifact_meta = [
        {"name": "report_debate", "path": debate_path.as_posix()},
        {"name": "report_debate_report", "path": report_path.as_posix()},
        {"name": "final_report_initial", "path": initial_path.as_posix()},
        *[
            {
                "name": f"final_report_revision_{index + 1:03d}",
                "path": path,
            }
            for index, path in enumerate(revision_paths)
        ],
    ]
    debate = debate.model_copy(update={"artifacts": artifact_meta})
    debate_path.write_text(
        json.dumps(debate.model_dump(mode="json"), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    report_path.write_text(render_report_debate_markdown(debate), encoding="utf-8")
    return ReportDebateArtifacts(
        debate_path=debate_path.as_posix(),
        report_path=report_path.as_posix(),
        initial_report_path=initial_path.as_posix(),
        revision_report_paths=revision_paths,
        debate=debate,
    )


def render_report_debate_markdown(debate: ReportDebateRecord) -> str:
    """Renderiza una version legible del debate para humanos."""

    lines = [
        f"# Debate controlado del informe {debate.run_id}",
        "",
        "## Resultado",
        "",
        f"- Estado: `{debate.status}`",
        f"- Rondas usadas: `{debate.rounds_used}/{debate.max_rounds}`",
        f"- Revision humana recomendada: `{debate.human_review_recommended}`",
        f"- Resumen: {debate.final_summary}",
        "",
        "## Conversacion resumida",
        "",
    ]
    for turn in debate.turns:
        lines.extend(
            [
                f"### {turn.round_index} | {turn.speaker_agent}",
                "",
                f"- Intencion: `{turn.intent}`",
                f"- Estado: `{turn.status}`",
                f"- Resumen humano: {turn.human_summary}",
            ]
        )
        _extend_list(lines, "Objeciones o claims", turn.claims_or_objections)
        _extend_list(lines, "Puntos aceptados", turn.accepted_points)
        _extend_list(lines, "Puntos rechazados", turn.rejected_points)
        _extend_list(lines, "Cambios pedidos", turn.changes_requested)
        _extend_list(lines, "Cambios aplicados", turn.changes_applied)
        _extend_list(lines, "Evidencia", [f"`{ref}`" for ref in turn.evidence_refs])
        lines.append("")
    if debate.unresolved_issues:
        lines.extend(["## Incidencias no resueltas", ""])
        lines.extend([f"- {item}" for item in debate.unresolved_issues])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _initial_writer_turn(
    run_id: str,
    decision: ReportDecision,
) -> ReportDebateTurn:
    return ReportDebateTurn(
        turn_id=f"{run_id}:report_debate:writer:initial",
        round_index=0,
        speaker_agent="report_writer",
        source_decision_id=decision.decision_id,
        intent="draft",
        human_summary=(
            f"Redactor genera el borrador inicial con {len(decision.sections)} "
            "secciones."
        ),
        changes_applied=[section.title for section in decision.sections],
        evidence_refs=_section_evidence_refs(decision.sections),
        status="informational",
    )


def _verification_turn(
    run_id: str,
    *,
    round_index: int,
    decision: ReportVerificationDecision,
    intent: ReportDebateTurnIntent,
) -> ReportDebateTurn:
    issues = _verification_issues(decision)
    return ReportDebateTurn(
        turn_id=f"{run_id}:report_debate:verifier:{round_index:03d}",
        round_index=round_index,
        speaker_agent="report_verifier",
        source_decision_id=decision.decision_id,
        intent=intent,
        human_summary=(
            f"Verificador marca `{decision.verification_status}` con "
            f"{len(issues)} incidencia(s). {decision.summary}"
        ),
        claims_or_objections=_issue_summaries(decision),
        changes_requested=decision.required_corrections,
        evidence_refs=sorted(
            set(decision.evidence_refs)
            | {
                ref
                for issue in issues
                for ref in issue.evidence_refs
            }
        ),
        status="verified"
        if decision.verification_status == "approved"
        else "unresolved",
    )


def _revision_turn(
    run_id: str,
    decision: ReportRevisionDecision,
) -> ReportDebateTurn:
    return ReportDebateTurn(
        turn_id=f"{run_id}:report_debate:writer:revision:{decision.revision_round:03d}",
        round_index=decision.revision_round,
        speaker_agent="report_writer",
        source_decision_id=decision.decision_id,
        intent="revision",
        human_summary=(
            f"Redactor revisa el informe y acepta "
            f"{len(decision.accepted_issue_ids)} incidencia(s)."
        ),
        accepted_points=decision.accepted_issue_ids,
        rejected_points=decision.rejected_issue_ids,
        changes_applied=decision.changes_summary,
        evidence_refs=decision.evidence_refs,
        status="accepted" if decision.accepted_issue_ids else "informational",
    )


def _debate_status(
    *,
    initial_verification: ReportVerificationDecision,
    final_verification: ReportVerificationDecision,
    revision_decision: ReportRevisionDecision | None,
) -> ReportDebateStatus:
    if final_verification.verification_status == "approved":
        return (
            "approved_without_revision"
            if revision_decision is None
            else "approved_after_revision"
        )
    if final_verification.verification_status == "blocked":
        return "blocked"
    if revision_decision is None and initial_verification.verification_status != "approved":
        return "needs_human_review"
    return "needs_human_review"


def _final_summary(
    status: ReportDebateStatus,
    final_verification: ReportVerificationDecision,
) -> str:
    if status == "approved_without_revision":
        return "El informe inicial fue aceptado por el verificador."
    if status == "approved_after_revision":
        return "El informe revisado fue aceptado por el verificador."
    if status == "blocked":
        return "El debate conserva incidencias criticas sin resolver."
    if status == "needs_human_review":
        return "El debate agoto sus rondas y recomienda revision humana."
    return final_verification.summary


def _verification_issues(
    decision: ReportVerificationDecision,
) -> list[ReportVerificationIssue]:
    return [
        *decision.unsupported_claims,
        *decision.misleading_claims,
        *decision.missing_limitations,
    ]


def _issue_summaries(decision: ReportVerificationDecision) -> list[str]:
    issues = _verification_issues(decision)
    return [
        (
            f"{_issue_id(issue, index)} | {issue.severity} | "
            f"{issue.claim_text}: {issue.reason}"
        )
        for index, issue in enumerate(issues, start=1)
    ]


def _issue_id(issue: ReportVerificationIssue, index: int) -> str:
    return issue.issue_id or f"verification_issue_{index:03d}"


def _section_evidence_refs(sections) -> list[str]:
    refs: set[str] = set()
    for section in sections:
        refs.update(section.evidence_refs)
    return sorted(refs)


def _extend_list(lines: list[str], title: str, values: list[str]) -> None:
    if not values:
        return
    lines.append(f"- {title}:")
    lines.extend([f"  - {value}" for value in values])
