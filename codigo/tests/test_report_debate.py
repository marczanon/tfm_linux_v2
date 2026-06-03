import json
import tempfile
import unittest
from pathlib import Path

from codigo.app.schemas.agent_decisions import (
    ReportDecision,
    ReportRevisionDecision,
    ReportSection,
    ReportVerificationDecision,
    ReportVerificationIssue,
)
from codigo.app.services.report_debate import (
    build_report_debate_record,
    render_report_debate_markdown,
    write_report_debate_artifacts,
)


class ReportDebateTests(unittest.TestCase):
    def test_builds_debate_record_for_revision_round(self):
        debate = build_report_debate_record(
            run_id="run-debate",
            initial_report_decision=_initial_report_decision(),
            initial_verification=_verification("needs_revision"),
            final_report_decision=_revision_decision(),
            final_verification=_verification("approved", decision_suffix="002"),
            revision_decision=_revision_decision(),
            max_rounds=1,
        )

        self.assertEqual(debate.status, "approved_after_revision")
        self.assertEqual(debate.rounds_used, 1)
        self.assertEqual(
            [turn.speaker_agent for turn in debate.turns],
            [
                "report_writer",
                "report_verifier",
                "report_writer",
                "report_verifier",
                "system",
            ],
        )

    def test_writes_json_markdown_and_report_versions(self):
        debate = build_report_debate_record(
            run_id="run-debate",
            initial_report_decision=_initial_report_decision(),
            initial_verification=_verification("needs_revision"),
            final_report_decision=_revision_decision(),
            final_verification=_verification("needs_revision", decision_suffix="002"),
            revision_decision=_revision_decision(),
            max_rounds=1,
        )

        with tempfile.TemporaryDirectory() as tmp:
            artifacts = write_report_debate_artifacts(
                debate=debate,
                output_dir=tmp,
                initial_report_markdown="# Borrador inicial\n",
                revision_markdowns=[(1, "# Borrador revisado\n")],
            )
            payload = json.loads(Path(artifacts.debate_path).read_text(encoding="utf-8"))
            markdown = Path(artifacts.report_path).read_text(encoding="utf-8")

        self.assertEqual(payload["status"], "needs_human_review")
        self.assertIn("report_debate_report", [item["name"] for item in payload["artifacts"]])
        self.assertIn("## Conversacion resumida", markdown)
        self.assertIn("Redactor revisa el informe", markdown)

    def test_markdown_renderer_exposes_human_summaries(self):
        debate = build_report_debate_record(
            run_id="run-debate",
            initial_report_decision=_initial_report_decision(),
            initial_verification=_verification("approved"),
            final_report_decision=_initial_report_decision(),
            final_verification=_verification("approved"),
            max_rounds=1,
        )

        markdown = render_report_debate_markdown(debate)

        self.assertIn("# Debate controlado del informe run-debate", markdown)
        self.assertIn("Verificador marca `approved`", markdown)


def _initial_report_decision() -> ReportDecision:
    return ReportDecision(
        decision_id="run-debate:report_writer:001",
        rationale="Create report.",
        confidence=0.9,
        output_path="codigo/reports/cwru_bearing/run-debate/final_report.md",
        sections=[ReportSection(title="Resumen ejecutivo", evidence_refs=["metric:f1"])],
    )


def _revision_decision() -> ReportRevisionDecision:
    return ReportRevisionDecision(
        decision_id="run-debate:report_writer_revision:001",
        rationale="Apply verifier correction.",
        confidence=0.82,
        revision_round=1,
        revision_of_decision_id="run-debate:report_writer:001",
        verifier_decision_id="run-debate:report_verifier:001",
        output_path="codigo/reports/cwru_bearing/run-debate/final_report.md",
        sections=[ReportSection(title="Resumen ejecutivo", evidence_refs=["metric:f1"])],
        accepted_issue_ids=["industrial_claim"],
        changes_summary=["Reformular validacion industrial."],
        evidence_refs=["report:final_report"],
    )


def _verification(
    status: str,
    *,
    decision_suffix: str = "001",
) -> ReportVerificationDecision:
    issue = ReportVerificationIssue(
        issue_id="industrial_claim",
        issue_type="unsupported_claim",
        severity="medium",
        claim_text="Validacion industrial completa.",
        reason="La evidencia solo cubre una run local.",
        evidence_refs=["report:final_report"],
        suggested_fix="Reformular como validacion local.",
    )
    return ReportVerificationDecision(
        decision_id=f"run-debate:report_verifier:{decision_suffix}",
        rationale="Verify report.",
        confidence=0.8,
        report_path="codigo/reports/cwru_bearing/run-debate/final_report.md",
        verification_status=status,
        summary="Revision del informe.",
        unsupported_claims=[] if status == "approved" else [issue],
        required_corrections=[] if status == "approved" else ["Reformular claim."],
        evidence_refs=["report:final_report"],
    )


if __name__ == "__main__":
    unittest.main()
