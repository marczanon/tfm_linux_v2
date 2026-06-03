import tempfile
import unittest
from pathlib import Path

from codigo.app.executors.reporting import generate_technical_report
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.agent_decisions import ReportDecision, ReportSection
from codigo.app.schemas.state import ArtifactRef, EvaluationResult, MetricsReport


class ReportingExecutorTests(unittest.TestCase):
    def test_generate_technical_report_writes_markdown_artifact(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            report_path = base / "final_report.md"
            state = _state()
            decision = _decision(report_path)

            result = generate_technical_report(state, decision)
            content = report_path.read_text(encoding="utf-8")

        self.assertEqual(result.status, "success")
        self.assertEqual(result.report_path, str(report_path))
        self.assertEqual(result.state_updates["report_path"], str(report_path))
        self.assertEqual([artifact.artifact_type for artifact in result.artifacts], ["report"])
        self.assertEqual(result.artifacts[0].name, "final_report")
        self.assertIn("# Informe tecnico de deteccion de anomalias", content)
        self.assertIn("Resumen narrativo redactado por el agente.", content)
        self.assertIn("Hallazgo redactado.", content)
        self.assertIn("## Metricas y evaluacion", content)
        self.assertIn("Recall: `0.9500`", content)
        self.assertIn("Validacion limitada a CWRU.", content)

    def test_unsupported_report_format_returns_failed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state = _state()
            decision = _decision(base / "final_report.pdf", output_format="pdf")

            result = generate_technical_report(state, decision)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.artifacts, [])
        self.assertIn("only markdown reports", result.errors[0].message)


def _state():
    state_dict = create_initial_cwru_state(
        thread_id="cwru-reporting-test",
        run_id="run-reporting-001",
    )
    state_dict["metrics"] = MetricsReport(
        metrics_path="codigo/reports/cwru_bearing/evaluation/metrics.json",
        precision=0.93,
        recall=0.95,
        f1_score=0.94,
        roc_auc=0.97,
        pr_auc=0.96,
        false_positive_rate=0.04,
    ).model_dump(mode="json")
    state_dict["evaluation"] = EvaluationResult(
        approved=True,
        summary="Ejecucion aprobada.",
        next_action="continue",
        limitations=["Validacion limitada a CWRU."],
    ).model_dump(mode="json")
    state_dict["artifacts"] = [
        ArtifactRef(
            name="metrics",
            artifact_type="metrics",
            path="codigo/reports/cwru_bearing/evaluation/metrics.json",
            producer="evaluator",
        ).model_dump(mode="json")
    ]
    return validate_state(state_dict)


def _decision(
    report_path: Path,
    *,
    output_format: str = "markdown",
) -> ReportDecision:
    return ReportDecision(
        decision_id="run-reporting-001:report_writer:001",
        rationale="Create a concise final report.",
        confidence=1.0,
        output_path=str(report_path),
        output_format=output_format,
        sections=[
            ReportSection(
                title="Resumen ejecutivo",
                body="Resumen narrativo redactado por el agente.",
                key_findings=["Hallazgo redactado."],
                recommendations=["Revision humana del informe antes de entrega."],
            ),
            ReportSection(title="Metricas y evaluacion", include_metrics=True),
            ReportSection(title="Artefactos generados", include_artifacts=True),
            ReportSection(title="Limitaciones y siguientes pasos"),
        ],
    )


if __name__ == "__main__":
    unittest.main()
