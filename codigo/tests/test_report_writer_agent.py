import unittest

from codigo.app.agents.report_writer import decide_report_action
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import EvaluationResult, MetricsReport


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


if __name__ == "__main__":
    unittest.main()
