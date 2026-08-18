import tempfile
import unittest
from pathlib import Path

from codigo.app.executors.reporting import generate_technical_report
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.agent_decisions import ReportDecision, ReportSection
from codigo.app.schemas.state import (
    ArtifactRef,
    EvaluationResult,
    MetricsReport,
    ProjectContext,
)


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
        self.assertIn("Procedencia de datos: `official`", content)
        self.assertIn("Resumen narrativo redactado por el agente.", content)
        self.assertIn("Hallazgo redactado.", content)
        self.assertIn("## Metricas y evaluacion", content)
        self.assertIn("Recall: `0.9500`", content)
        self.assertIn("Validacion limitada a CWRU.", content)

    def test_report_header_and_artifact_always_disclose_synthetic_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "final_report.md"
            state = _synthetic_state()
            result = generate_technical_report(state, _decision(report_path))
            content = report_path.read_text(encoding="utf-8")

        self.assertEqual(result.status, "success")
        self.assertIn("Procedencia de datos: `synthetic`", content)
        self.assertIn("no son senales oficiales", content)
        self.assertIn("synthetic_dataset_spec", content)
        self.assertEqual(
            result.artifacts[0].metadata["data_provenance"],
            "synthetic",
        )
        self.assertEqual(
            result.artifacts[0].metadata["provenance_detection_method"],
            "synthetic_dataset_spec",
        )

    def test_unsupported_report_format_returns_failed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state = _state()
            decision = _decision(base / "final_report.pdf", output_format="pdf")

            result = generate_technical_report(state, decision)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.artifacts, [])
        self.assertIn("only markdown reports", result.errors[0].message)

    def test_official_v2_renderer_does_not_repeat_legacy_physical_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            report_path = Path(tmp) / "final_report.md"
            state = _official_v2_state_with_legacy_summary()
            decision = ReportDecision(
                decision_id="run-reporting-official-v2-001:report_writer:001",
                rationale="Render scoped official v2 evidence.",
                confidence=1.0,
                output_path=str(report_path),
                output_format="markdown",
                sections=[
                    ReportSection(title="Resumen ejecutivo"),
                    ReportSection(
                        title="Metricas y evaluacion",
                        include_metrics=True,
                    ),
                ],
            )

            result = generate_technical_report(state, decision)
            content = report_path.read_text(encoding="utf-8").lower()

        self.assertEqual(result.status, "success")
        self.assertIn("aceptada por controles operativos internos", content)
        self.assertIn("alerta algoritmica persistente", content)
        self.assertIn("final registrado", content)
        self.assertIn("alertas pre-monitorizacion", content)
        self.assertIn("ground truth", content)
        self.assertNotIn("onset confirmado", content)
        self.assertNotIn("fallo detectado", content)
        self.assertNotIn("lead time persistente hasta fallo", content)


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


def _synthetic_state():
    state_dict = create_initial_cwru_state(
        thread_id="nasa-reporting-test",
        run_id="run-reporting-001",
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
        data_provenance="synthetic",
        provenance_detection_method="synthetic_dataset_spec",
        provenance_evidence_path=(
            "codigo/data/raw/nasa_ims_bearing/synthetic_dataset_spec.json"
        ),
        provenance_evidence_sha256="a" * 64,
    ).model_dump(mode="json")
    return validate_state(state_dict)


def _official_v2_state_with_legacy_summary():
    state_dict = create_initial_cwru_state(
        thread_id="nasa-reporting-official-v2-test",
        run_id="run-reporting-official-v2-001",
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
        label_granularity="event",
        label_source="none",
        data_provenance="official",
        provenance_detection_method="official_dataset_provenance",
    ).model_dump(mode="json")
    state_dict["metrics"] = MetricsReport(
        extra={
            "degradation_available": True,
            "degradation_confirmed_degradation_before_failure_rate": 1.0,
            "degradation_mean_persistent_lead_time_to_failure": 201600.5632,
            "degradation_mean_false_alarm_rate_nominal": 0.0,
            "degradation_mean_score_trend_spearman": 0.7937,
        },
    ).model_dump(mode="json")
    # Simula una run ya persistida con la semantica legacy para comprobar que el
    # renderer nuevo no propaga ese texto al informe regenerado.
    state_dict["evaluation"] = EvaluationResult(
        approved=True,
        summary="Ejecucion aprobada: onset confirmado y fallo detectado.",
        next_action="continue",
        limitations=["RUL no estimado."],
    ).model_dump(mode="json")
    return validate_state(state_dict)


if __name__ == "__main__":
    unittest.main()
