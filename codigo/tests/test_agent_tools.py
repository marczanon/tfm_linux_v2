import json
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError

from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.reasoning import (
    AgentToolObservation,
    AgentToolRequest,
    AgentToolSpec,
)
from codigo.app.schemas.state import EvaluationResult, MetricsReport, ProjectContext
from codigo.app.services.agent_tools import (
    agent_tool_catalog,
    build_state_evidence_catalog,
    get_agent_tool_spec,
    run_agent_tool_request,
)


class AgentToolsTests(unittest.TestCase):
    def test_catalog_declares_read_only_evidence_lookup(self):
        spec = get_agent_tool_spec("evidence_lookup")

        self.assertEqual(spec.tool_name, "evidence_lookup")
        self.assertEqual(spec.effect, "read_only")
        self.assertFalse(spec.produces_artifacts)
        self.assertIn("modeler", spec.allowed_agents)
        self.assertIn("report_verifier", spec.allowed_agents)

        modeler_tools = agent_tool_catalog(agent_name="modeler")
        self.assertEqual(
            [tool.tool_name for tool in modeler_tools],
            ["evidence_lookup", "threshold_analysis"],
        )
        verifier_tools = agent_tool_catalog(agent_name="report_verifier")
        self.assertEqual([tool.tool_name for tool in verifier_tools], ["evidence_lookup"])
        json.dumps(spec.model_dump(mode="json"))

    def test_catalog_declares_threshold_analysis_as_read_only_diagnostic(self):
        spec = get_agent_tool_spec("threshold_analysis")

        self.assertEqual(spec.effect, "read_only")
        self.assertIn("modeler", spec.allowed_agents)
        self.assertIn("evaluator", spec.allowed_agents)
        self.assertNotIn("report_writer", spec.allowed_agents)
        self.assertFalse(spec.produces_artifacts)

    def test_read_only_spec_cannot_produce_artifacts(self):
        with self.assertRaises(ValidationError):
            AgentToolSpec(
                tool_name="evidence_lookup",
                description="Invalid read-only tool.",
                allowed_agents=["modeler"],
                effect="read_only",
                produces_artifacts=True,
            )

    def test_evidence_lookup_returns_selected_run_evidence(self):
        request = AgentToolRequest(
            request_id="run-tools-001:modeler:tool:001",
            run_id="run-tools-001",
            agent_name="modeler",
            tool_name="evidence_lookup",
            purpose="Consultar metricas y artefactos antes de decidir.",
            arguments={
                "include": ["metrics", "evaluation", "artifacts"],
                "artifact_limit": 5,
            },
        )

        observation = run_agent_tool_request(_state(), request)

        self.assertEqual(observation.status, "success")
        self.assertIn("metric:recall", observation.evidence_refs)
        self.assertIn("evaluation:approved", observation.evidence_refs)
        self.assertIn("artifact:evaluation_metrics", observation.evidence_refs)
        self.assertEqual(observation.payload["metrics"]["recall"], 0.95)
        self.assertEqual(observation.payload["n_artifacts_total"], 1)
        self.assertNotIn("project_context", observation.payload)
        json.dumps(observation.model_dump(mode="json"))

    def test_evidence_lookup_rejects_unknown_sections_as_failed_observation(self):
        request = AgentToolRequest(
            request_id="run-tools-001:modeler:tool:bad",
            run_id="run-tools-001",
            agent_name="modeler",
            tool_name="evidence_lookup",
            purpose="Pedir una seccion inexistente.",
            arguments={"include": ["metrics", "not_real"]},
        )

        observation = run_agent_tool_request(_state(), request)

        self.assertEqual(observation.status, "failed")
        self.assertIn("unknown evidence_lookup section", observation.errors[0])

    def test_evidence_lookup_blocks_wrong_run_id(self):
        request = AgentToolRequest(
            request_id="other-run:modeler:tool:001",
            run_id="other-run",
            agent_name="modeler",
            tool_name="evidence_lookup",
            purpose="Consultar evidencia de otra run.",
        )

        observation = run_agent_tool_request(_state(), request)

        self.assertEqual(observation.status, "blocked")
        self.assertIn("run_id does not match", observation.errors[0])

    def test_evidence_catalog_is_closed_and_report_verifier_compatible(self):
        catalog = build_state_evidence_catalog(_state())

        self.assertIn("report:final_report", catalog["allowed_evidence_refs"])
        self.assertIn("metric:f1_score", catalog["allowed_evidence_refs"])
        self.assertIn("limitation:1", catalog["allowed_evidence_refs"])
        self.assertEqual(catalog["metrics"]["precision"], 0.93)

    def test_evidence_catalog_exposes_temporal_profile_refs(self):
        catalog = build_state_evidence_catalog(_temporal_state())

        refs = catalog["allowed_evidence_refs"]
        self.assertIn("supervision_profile:run_to_failure_degradation", refs)
        self.assertIn("label_source:temporal_proxy", refs)
        self.assertIn("metric_extra:degradation_mean_lead_time_to_failure", refs)
        self.assertEqual(catalog["metrics"]["extra"]["degradation_available"], True)

    def test_threshold_analysis_returns_sensitivity_without_recommendation(self):
        with tempfile.TemporaryDirectory() as tmp:
            predictions_path = Path(tmp) / "predictions.csv"
            _write_predictions(predictions_path)
            request = AgentToolRequest(
                request_id="run-tools-001:modeler:tool:threshold",
                run_id="run-tools-001",
                agent_name="modeler",
                tool_name="threshold_analysis",
                purpose="Analizar sensibilidad sin decidir el umbral.",
                arguments={
                    "primary_split": "test",
                    "threshold_source_split": "validation",
                    "quantiles": [0.5, 0.75, 1.0],
                    "near_threshold_limit": 2,
                },
            )

            observation = run_agent_tool_request(
                _state_with_predictions(predictions_path),
                request,
            )

        self.assertEqual(observation.status, "success")
        self.assertIn("artifact:model_predictions", observation.evidence_refs)
        self.assertIn("tool:threshold_analysis", observation.evidence_refs)
        self.assertIn("sin recomendar", observation.summary)
        self.assertEqual(observation.payload["analysis_type"], "threshold_sensitivity")
        self.assertEqual(len(observation.payload["candidate_metrics"]), 3)
        self.assertEqual(len(observation.payload["near_threshold_windows"]), 2)
        self.assertIn("interpretation_guardrail", observation.payload)
        self.assertNotIn("recommended_threshold", observation.payload)
        json.dumps(observation.model_dump(mode="json"))

    def test_threshold_analysis_blocks_when_predictions_are_missing(self):
        request = AgentToolRequest(
            request_id="run-tools-001:modeler:tool:no-predictions",
            run_id="run-tools-001",
            agent_name="modeler",
            tool_name="threshold_analysis",
            purpose="Analizar umbral sin predicciones.",
        )

        observation = run_agent_tool_request(_state(), request)

        self.assertEqual(observation.status, "blocked")
        self.assertIn("predictions artifact", observation.errors[0])

    def test_threshold_analysis_rejects_invalid_quantiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            predictions_path = Path(tmp) / "predictions.csv"
            _write_predictions(predictions_path)
            request = AgentToolRequest(
                request_id="run-tools-001:modeler:tool:bad-threshold",
                run_id="run-tools-001",
                agent_name="modeler",
                tool_name="threshold_analysis",
                purpose="Pedir cuantiles invalidos.",
                arguments={"quantiles": [0.95, 2.0]},
            )

            observation = run_agent_tool_request(
                _state_with_predictions(predictions_path),
                request,
            )

        self.assertEqual(observation.status, "failed")
        self.assertIn("quantiles must be in", observation.errors[0])

    def test_failed_observation_requires_error(self):
        with self.assertRaises(ValidationError):
            AgentToolObservation(
                observation_id="bad-observation",
                request_id="request-001",
                run_id="run-tools-001",
                agent_name="modeler",
                tool_name="evidence_lookup",
                status="failed",
                summary="Failed without error.",
            )


def _state():
    state_dict = create_initial_cwru_state(
        thread_id="agent-tools-test-thread",
        run_id="run-tools-001",
    )
    state_dict["report_path"] = "codigo/reports/cwru_bearing/run-tools-001/final_report.md"
    state_dict["metrics"] = MetricsReport(
        metrics_path="codigo/reports/cwru_bearing/run-tools-001/evaluation/metrics.json",
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
            "name": "evaluation_metrics",
            "artifact_type": "metrics",
            "path": "codigo/reports/cwru_bearing/run-tools-001/evaluation/metrics.json",
            "producer": "evaluator",
        }
    ]
    return validate_state(state_dict)


def _state_with_predictions(predictions_path: Path):
    state = _state().to_langgraph_state()
    state["artifacts"].append(
        {
            "name": "model_predictions",
            "artifact_type": "predictions",
            "path": predictions_path.as_posix(),
            "producer": "modeling_executor",
        }
    )
    return validate_state(state)


def _temporal_state():
    state_dict = create_initial_cwru_state(
        thread_id="agent-tools-temporal-test-thread",
        run_id="run-tools-temporal-001",
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
        extra={
            "degradation_available": True,
            "degradation_mean_lead_time_to_failure": 300.0,
        }
    ).model_dump(mode="json")
    return validate_state(state_dict)


def _write_predictions(path: Path) -> None:
    lines = [
        "window_id,file_id,split,label,target,anomaly_score,threshold,predicted_anomaly",
        "v1,fv,validation,normal,0,0.10,0.50,0",
        "v2,fv,validation,normal,0,0.30,0.50,0",
        "v3,fv,validation,fault,1,0.60,0.50,1",
        "v4,fv,validation,fault,1,0.90,0.50,1",
        "t1,ft,test,normal,0,0.20,0.50,0",
        "t2,ft,test,normal,0,0.55,0.50,1",
        "t3,ft,test,fault,1,0.45,0.50,0",
        "t4,ft,test,fault,1,0.80,0.50,1",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
