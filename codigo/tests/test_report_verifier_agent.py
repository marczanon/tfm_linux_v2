import unittest

from codigo.app.agents.report_verifier import decide_report_verification_action
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import EvaluationResult, MetricsReport, ProjectContext


class FakeLLMClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete_json(self, messages, *, json_schema=None):
        self.calls += 1
        self.messages = messages
        self.json_schema = json_schema
        if isinstance(self.payload, list):
            index = min(self.calls - 1, len(self.payload) - 1)
            return self.payload[index]
        return self.payload


class ReportVerifierAgentTests(unittest.TestCase):
    def test_deterministic_verifier_approves_supported_report(self):
        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "La ejecucion queda aprobada por el evaluador como baseline local "
                "del TFM. Recall=0.9500 y F1=0.9400. Las limitaciones indican "
                "validacion limitada a CWRU."
            ),
        )

        self.assertEqual(decision.agent_name, "report_verifier")
        self.assertEqual(decision.verification_status, "approved")
        self.assertEqual(decision.unsupported_claims, [])
        self.assertIn("report:final_report", decision.evidence_refs)

    def test_deterministic_verifier_flags_unsupported_industrial_claim(self):
        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "El sistema queda listo para produccion y cuenta con validacion "
                "industrial completa."
            ),
        )

        self.assertEqual(decision.verification_status, "needs_revision")
        self.assertEqual(len(decision.unsupported_claims), 1)
        self.assertIn("validacion industrial", decision.unsupported_claims[0].claim_text)
        self.assertTrue(decision.required_corrections)

    def test_deterministic_verifier_accepts_industrial_disclaimer(self):
        decision = decide_report_verification_action(
            _state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "La ejecucion queda como resultado local auditable del TFM. "
                "Las metricas se usan como baseline local, no como validacion "
                "industrial final. La generalizacion industrial requiere validar "
                "otros datasets y condiciones de carga. Las limitaciones se "
                "declaran de forma explicita."
            ),
        )

        self.assertEqual(decision.verification_status, "approved")
        self.assertEqual(decision.unsupported_claims, [])

    def test_deterministic_verifier_blocks_official_label_claim_for_proxy_source(self):
        decision = decide_report_verification_action(
            _temporal_proxy_state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "El dataset usa etiquetas oficiales por ventana y ground truth oficial "
                "para evaluar la degradacion."
            ),
        )

        self.assertEqual(decision.verification_status, "blocked")
        self.assertEqual(len(decision.misleading_claims), 1)
        issue = decision.misleading_claims[0]
        self.assertEqual(issue.issue_type, "policy_violation")
        self.assertEqual(issue.severity, "critical")
        self.assertIn("label_source:temporal_proxy", issue.evidence_refs)

    def test_deterministic_verifier_accepts_negated_official_label_guardrail(self):
        decision = decide_report_verification_action(
            _temporal_proxy_state(),
            report_markdown=(
                "# Informe tecnico\n\n"
                "La evaluacion usa etiquetas temporales proxy. Las etiquetas por "
                "ventana no son oficiales y no deben tratarse como ground truth "
                "oficial. Las metricas binarias quedan como apoyo, no como "
                "validacion oficial. Las limitaciones se declaran de forma "
                "explicita."
            ),
        )

        self.assertEqual(decision.verification_status, "approved")
        self.assertEqual(decision.misleading_claims, [])

    def test_llm_verification_decision_is_used_when_valid(self):
        client = FakeLLMClient(
            {
                "agent_name": "report_verifier",
                "decision_id": "run-report-001:report_verifier:001",
                "rationale": "The report is factual and mentions local scope.",
                "confidence": 0.88,
                "report_path": "codigo/reports/cwru_bearing/run-report-001/final_report.md",
                "verification_status": "approved",
                "summary": "No unsupported claims detected.",
                "unsupported_claims": [],
                "misleading_claims": [],
                "missing_limitations": [],
                "required_corrections": [],
                "acceptable_style_notes": ["Style differs but remains factual."],
                "evidence_refs": ["report:final_report", "metric:recall"],
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown="Informe local con recall persistido.",
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.confidence, 0.88)
        self.assertIn("ReportVerificationDecision", str(client.json_schema))

    def test_llm_verification_alias_payload_is_normalized(self):
        client = FakeLLMClient(
            {
                "decision": "approved",
                "run_id": "run-report-001",
                "dataset": "cwru_bearing",
                "notes": "El informe es factual y no requiere revisiones.",
                "evidence_references": ["report:final_report", "metric:recall"],
                "issues": [],
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown="Informe local con limitaciones.",
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(decision.verification_status, "approved")
        self.assertEqual(decision.summary, "El informe es factual y no requiere revisiones.")
        self.assertIn("metric:recall", decision.evidence_refs)

    def test_invalid_llm_verification_uses_guardrail_correction(self):
        client = FakeLLMClient(
            {
                "agent_name": "report_verifier",
                "decision_id": "run-report-001:report_verifier:001",
                "rationale": "Invalid path.",
                "confidence": 0.9,
                "report_path": "/tmp/final_report.md",
                "verification_status": "approved",
                "summary": "Invalid.",
            }
        )

        decision = decide_report_verification_action(
            _state(),
            report_markdown="Informe local con limitaciones.",
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(
            decision.report_path,
            "codigo/reports/cwru_bearing/run-report-001/final_report.md",
        )
        self.assertLessEqual(decision.confidence, 0.72)
        self.assertIn("Guardrail correction", decision.rationale)
        self.assertNotIn("validation errors", decision.rationale)
        self.assertNotIn("errors.pydantic.dev", decision.rationale)


def _state():
    state_dict = create_initial_cwru_state(
        thread_id="cwru-report-verifier-test",
        run_id="run-report-001",
    )
    state_dict["report_path"] = "codigo/reports/cwru_bearing/run-report-001/final_report.md"
    state_dict["metrics"] = MetricsReport(
        metrics_path="codigo/reports/cwru_bearing/evaluation/metrics.json",
        precision=0.93,
        recall=0.95,
        f1_score=0.94,
        false_positive_rate=0.04,
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


def _temporal_proxy_state():
    state_dict = create_initial_cwru_state(
        thread_id="nasa-report-verifier-test",
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
    state_dict["report_path"] = "codigo/reports/nasa_ims_bearing/run-report-nasa-temporal-001/final_report.md"
    state_dict["metrics"] = MetricsReport(
        metrics_path="codigo/reports/nasa_ims_bearing/evaluation/metrics.json",
        extra={
            "degradation_available": True,
            "degradation_mean_lead_time_to_failure": 300.0,
        },
    ).model_dump(mode="json")
    state_dict["evaluation"] = EvaluationResult(
        approved=True,
        summary="Temporal degradation metrics accepted.",
        next_action="continue",
        limitations=["Etiquetas proxy temporales; no oficiales por ventana."],
    ).model_dump(mode="json")
    return validate_state(state_dict)


if __name__ == "__main__":
    unittest.main()
