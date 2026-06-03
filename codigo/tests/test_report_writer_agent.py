import unittest

from codigo.app.agents.report_writer import (
    decide_report_action,
    decide_report_revision_action,
)
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.agent_decisions import (
    ReportVerificationDecision,
    ReportVerificationIssue,
)
from codigo.app.schemas.state import EvaluationResult, MetricsReport, ProjectContext


class FakeLLMClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete_json(self, messages, *, json_schema=None):
        self.calls += 1
        self.messages = messages
        self.json_schema = json_schema
        return self.payload


def _state():
    state_dict = create_initial_cwru_state(
        thread_id="cwru-report-test",
        run_id="run-report-001",
    )
    state_dict["manifest_path"] = "codigo/data/interim/cwru_bearing/manifest.csv"
    state_dict["profile_path"] = "codigo/data/interim/cwru_bearing/profile.json"
    state_dict["metrics"] = MetricsReport(
        metrics_path="codigo/reports/cwru_bearing/evaluation/metrics.json",
        recall=1.0,
        f1_score=0.99,
        false_positive_rate=0.05,
    ).model_dump(mode="json")
    state_dict["evaluation"] = EvaluationResult(
        approved=True,
        summary="Ejecucion aprobada.",
        next_action="continue",
        limitations=["Validacion limitada a CWRU."],
    ).model_dump(mode="json")
    state_dict["artifacts"] = [
        {
            "name": "metrics",
            "artifact_type": "metrics",
            "path": "codigo/reports/cwru_bearing/evaluation/metrics.json",
            "producer": "evaluator",
        }
    ]
    return validate_state(state_dict)


class ReportWriterAgentTests(unittest.TestCase):
    def test_deterministic_report_writer_returns_default_markdown_plan(self):
        decision = decide_report_action(_state())

        self.assertEqual(decision.agent_name, "report_writer")
        self.assertEqual(decision.output_format, "markdown")
        self.assertEqual(
            decision.output_path,
            "codigo/reports/cwru_bearing/run-report-001/final_report.md",
        )
        self.assertIn(
            "Metricas y evaluacion",
            [section.title for section in decision.sections],
        )
        summary_section = next(
            section for section in decision.sections if section.title == "Resumen ejecutivo"
        )
        self.assertIsNotNone(summary_section.body)
        self.assertTrue(summary_section.key_findings)
        self.assertTrue(summary_section.recommendations)

    def test_deterministic_report_writer_prioritizes_temporal_metrics(self):
        decision = decide_report_action(_temporal_state())

        metrics_section = next(
            section
            for section in decision.sections
            if section.title == "Metricas y evaluacion"
        )
        body = metrics_section.body or ""
        findings = " ".join(metrics_section.key_findings)
        self.assertIn("run-to-failure", body)
        self.assertIn("lead time", body)
        self.assertIn("run_to_failure_degradation", findings)
        self.assertIn("F1 auxiliar", findings)
        self.assertIn("ground truth oficial", body)

    def test_llm_report_decision_is_used_when_valid(self):
        client = FakeLLMClient(
            {
                "agent_name": "report_writer",
                "decision_id": "run-report-001:report_writer:001",
                "rationale": "Use a concise technical report structure.",
                "confidence": 0.91,
                "output_path": "codigo/reports/cwru_bearing/run-report-001/final_report.md",
                "output_format": "markdown",
                "sections": [
                    {"title": "Resumen ejecutivo", "include_metrics": False, "include_artifacts": False, "source_paths": []},
                    {"title": "Contexto y datos", "include_metrics": False, "include_artifacts": False, "source_paths": ["codigo/data/interim/cwru_bearing/manifest.csv"]},
                    {"title": "Configuraciones del pipeline", "include_metrics": False, "include_artifacts": False, "source_paths": []},
                    {"title": "Metricas y evaluacion", "include_metrics": True, "include_artifacts": False, "source_paths": ["codigo/reports/cwru_bearing/evaluation/metrics.json"]},
                    {"title": "Artefactos generados", "include_metrics": False, "include_artifacts": True, "source_paths": ["codigo/reports/cwru_bearing/evaluation/metrics.json"]},
                    {"title": "Limitaciones y siguientes pasos", "include_metrics": False, "include_artifacts": False, "source_paths": []},
                ],
            }
        )

        decision = decide_report_action(_state(), llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.confidence, 0.91)
        self.assertIn("ReportDecision", str(client.json_schema))

    def test_invalid_llm_report_decision_falls_back(self):
        client = FakeLLMClient(
            {
                "agent_name": "report_writer",
                "decision_id": "run-report-001:report_writer:001",
                "rationale": "Invalid output path.",
                "confidence": 0.99,
                "output_path": "/tmp/report.md",
                "output_format": "markdown",
                "sections": [
                    {"title": "Resumen ejecutivo", "include_metrics": False, "include_artifacts": False, "source_paths": []}
                ],
            }
        )

        decision = decide_report_action(_state(), llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(
            decision.output_path,
            "codigo/reports/cwru_bearing/run-report-001/final_report.md",
        )
        self.assertLessEqual(decision.confidence, 0.7)
        self.assertIn("Fallback after LLM failure", decision.rationale)

    def test_deterministic_revision_accepts_verifier_issues(self):
        verification = _verification_decision()

        decision = decide_report_revision_action(_state(), verification)

        self.assertEqual(decision.agent_name, "report_writer")
        self.assertEqual(decision.revision_round, 1)
        self.assertEqual(decision.verifier_decision_id, verification.decision_id)
        self.assertIn("industrial_claim", decision.accepted_issue_ids)
        limitation_section = next(
            section
            for section in decision.sections
            if section.title == "Limitaciones y siguientes pasos"
        )
        self.assertIn("verificacion agentica", limitation_section.body or "")

    def test_valid_llm_revision_is_used(self):
        client = FakeLLMClient(
            {
                "agent_name": "report_writer",
                "decision_id": "run-report-001:report_writer_revision:001",
                "rationale": "Apply verifier correction.",
                "confidence": 0.86,
                "revision_round": 1,
                "revision_of_decision_id": "run-report-001:report_writer:001",
                "verifier_decision_id": "run-report-001:report_verifier:001",
                "output_path": "codigo/reports/cwru_bearing/run-report-001/final_report.md",
                "output_format": "markdown",
                "sections": [
                    {"title": "Resumen ejecutivo", "include_metrics": False, "include_artifacts": False, "source_paths": []},
                    {"title": "Contexto y datos", "include_metrics": False, "include_artifacts": False, "source_paths": ["codigo/data/interim/cwru_bearing/manifest.csv"]},
                    {"title": "Configuraciones del pipeline", "include_metrics": False, "include_artifacts": False, "source_paths": []},
                    {"title": "Metricas y evaluacion", "include_metrics": True, "include_artifacts": False, "source_paths": ["codigo/reports/cwru_bearing/evaluation/metrics.json"]},
                    {"title": "Artefactos generados", "include_metrics": False, "include_artifacts": True, "source_paths": ["codigo/reports/cwru_bearing/evaluation/metrics.json"]},
                    {"title": "Limitaciones y siguientes pasos", "body": "Validacion limitada a CWRU.", "include_metrics": False, "include_artifacts": False, "source_paths": []},
                ],
                "accepted_issue_ids": ["industrial_claim"],
                "rejected_issue_ids": [],
                "rejection_rationales": {},
                "changes_summary": ["Reformula validacion industrial como validacion local."],
                "evidence_refs": ["report:final_report"],
            }
        )

        decision = decide_report_revision_action(
            _state(),
            _verification_decision(),
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.confidence, 0.86)
        self.assertIn("ReportRevisionDecision", str(client.json_schema))

def _verification_decision() -> ReportVerificationDecision:
    return ReportVerificationDecision(
        decision_id="run-report-001:report_verifier:001",
        rationale="Verify report factuality.",
        confidence=0.82,
        report_path="codigo/reports/cwru_bearing/run-report-001/final_report.md",
        verification_status="needs_revision",
        summary="One claim needs correction.",
        unsupported_claims=[
            ReportVerificationIssue(
                issue_id="industrial_claim",
                issue_type="unsupported_claim",
                severity="high",
                claim_text="Validacion industrial completa.",
                reason="La evidencia solo cubre una ejecucion local del TFM.",
                evidence_refs=["report:final_report"],
                suggested_fix="Reformular como validacion local reproducible.",
            )
        ],
        required_corrections=["Reformular la validacion industrial."],
        evidence_refs=["report:final_report"],
    )


def _temporal_state():
    state_dict = create_initial_cwru_state(
        thread_id="nasa-report-test",
        run_id="run-report-nasa-temporal-001",
    )
    state_dict["project_context"] = ProjectContext(
        dataset="nasa_ims_bearing",
        machine_type="rotating_machinery",
        signal_type="vibration",
        objective="run_to_failure_degradation",
        target_sample_rate_hz=20000,
        main_channel="channel_1",
        label_mode="degradation",
        supervision_profile="run_to_failure_degradation",
        label_granularity="proxy_temporal",
        label_source="temporal_proxy",
    ).model_dump(mode="json")
    state_dict["metrics"] = MetricsReport(
        metrics_path="codigo/reports/nasa_ims_bearing/evaluation/metrics.json",
        recall=0.42,
        f1_score=0.50,
        false_positive_rate=0.40,
        extra={
            "degradation_available": True,
            "degradation_n_runs": 1,
            "degradation_mean_lead_time_to_failure": 300.0,
            "degradation_mean_false_alarm_rate_nominal": 0.0,
            "degradation_mean_score_trend_spearman": 0.8,
        },
    ).model_dump(mode="json")
    state_dict["evaluation"] = EvaluationResult(
        approved=True,
        summary="Ejecucion run-to-failure aprobada.",
        next_action="continue",
        limitations=["Etiquetas proxy temporales; no oficiales por ventana."],
    ).model_dump(mode="json")
    return validate_state(state_dict)


if __name__ == "__main__":
    unittest.main()
