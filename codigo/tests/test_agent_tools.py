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
        self.assertIn("temporal", spec.input_schema["include"])
        self.assertIn("modeler", spec.allowed_agents)
        self.assertIn("cleaner", spec.allowed_agents)
        self.assertIn("report_verifier", spec.allowed_agents)

        modeler_tools = agent_tool_catalog(agent_name="modeler")
        self.assertEqual(
            [tool.tool_name for tool in modeler_tools],
            [
                "evidence_lookup",
                "temporal_health_lookup",
                "degradation_metrics_lookup",
                "temporal_model_readiness_assessor",
                "threshold_analysis",
            ],
        )
        verifier_tools = agent_tool_catalog(agent_name="report_verifier")
        self.assertEqual(
            [tool.tool_name for tool in verifier_tools],
            [
                "evidence_lookup",
                "temporal_health_lookup",
                "degradation_metrics_lookup",
                "temporal_model_readiness_assessor",
            ],
        )
        json.dumps(spec.model_dump(mode="json"))

    def test_catalog_declares_temporal_tools_as_read_only(self):
        health = get_agent_tool_spec("temporal_health_lookup")
        metrics = get_agent_tool_spec("degradation_metrics_lookup")
        readiness = get_agent_tool_spec("temporal_model_readiness_assessor")

        self.assertEqual(health.effect, "read_only")
        self.assertEqual(metrics.effect, "read_only")
        self.assertEqual(readiness.effect, "read_only")
        self.assertFalse(health.produces_artifacts)
        self.assertFalse(metrics.produces_artifacts)
        self.assertFalse(readiness.produces_artifacts)
        self.assertIn("cleaner", health.allowed_agents)
        self.assertIn("evaluator", metrics.allowed_agents)
        self.assertIn("modeler", readiness.allowed_agents)
        self.assertIn("run_limit", health.input_schema)
        self.assertEqual(metrics.input_schema, {})
        self.assertEqual(readiness.input_schema, {})
        json.dumps(health.model_dump(mode="json"))
        json.dumps(metrics.model_dump(mode="json"))
        json.dumps(readiness.model_dump(mode="json"))

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
        self.assertIn("metric:mean_lead_time_to_failure", refs)
        self.assertIn(
            "metric:confirmed_degradation_before_failure_rate",
            refs,
        )
        self.assertIn("metric:mean_health_index_drop", refs)
        self.assertIn("metric:mean_health_monotonicity", refs)
        self.assertIn("temporal:run_to_failure_profile", refs)
        self.assertIn("temporal:rul_not_estimated", refs)
        self.assertIn("temporal:predictions_missing", refs)
        self.assertEqual(catalog["metrics"]["extra"]["degradation_available"], True)
        self.assertFalse(catalog["temporal_evidence"]["available"])

    def test_cleaner_can_lookup_temporal_evidence_pack(self):
        with tempfile.TemporaryDirectory() as tmp:
            predictions_path = Path(tmp) / "temporal_predictions.csv"
            _write_temporal_predictions(predictions_path)
            request = AgentToolRequest(
                request_id="run-tools-temporal-001:cleaner:tool:001",
                run_id="run-tools-temporal-001",
                agent_name="cleaner",
                tool_name="evidence_lookup",
                purpose="Consultar contexto temporal antes de decidir limpieza.",
                arguments={"include": ["temporal"]},
            )

            observation = run_agent_tool_request(
                _temporal_state_with_predictions(predictions_path),
                request,
            )

        self.assertEqual(observation.status, "success")
        self.assertIn("temporal:first_spike", observation.evidence_refs)
        self.assertIn("temporal:first_persistent_alert", observation.evidence_refs)
        self.assertIn("temporal:onset_confirmed", observation.evidence_refs)
        self.assertIn("temporal:health_policy", observation.evidence_refs)
        self.assertIn("health:indicator_available", observation.evidence_refs)
        self.assertIn("health:monotonicity", observation.evidence_refs)
        self.assertIn("temporal:isolated_alert_points", observation.evidence_refs)
        self.assertIn("metric:mean_lead_time_to_failure", observation.evidence_refs)
        temporal = observation.payload["temporal"]
        self.assertTrue(temporal["available"])
        self.assertEqual(
            temporal["cleaner_context"]["role"],
            "signal_quality_gate_for_temporal_monitoring",
        )
        self.assertIn("cleaner", temporal["agent_guidance"])
        primary = temporal["primary_run"]
        self.assertEqual(primary["run_id"], "bearing_1_test_1")
        self.assertAlmostEqual(primary["first_spike"]["x"], 0.2)
        self.assertAlmostEqual(primary["first_persistent_alert"]["x"], 0.6)
        self.assertEqual(primary["episodes"]["isolated_alert_points"], 1)
        self.assertEqual(primary["episodes"]["longest_alert_streak"], 3)
        self.assertEqual(
            primary["policy"]["health_policy_id"],
            "temporal_health_policy_v1",
        )
        self.assertEqual(
            primary["policy"]["health_indicator_policy_id"],
            "health_indicator_policy_v1",
        )
        self.assertTrue(primary["onset_confirmed"]["confirmed"])
        self.assertGreater(primary["health_indicator"]["health_index_drop"], 0.0)
        self.assertIn("RUL no esta estimado", " ".join(temporal["warnings"]))
        json.dumps(observation.model_dump(mode="json"))

    def test_temporal_health_lookup_returns_focused_health_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            predictions_path = Path(tmp) / "temporal_predictions.csv"
            _write_temporal_predictions(predictions_path)
            request = AgentToolRequest(
                request_id="run-tools-temporal-001:evaluator:tool:health",
                run_id="run-tools-temporal-001",
                agent_name="evaluator",
                tool_name="temporal_health_lookup",
                purpose="Inspeccionar salud temporal y avisos sostenidos.",
                arguments={"run_limit": 1},
            )

            observation = run_agent_tool_request(
                _temporal_state_with_predictions(predictions_path),
                request,
            )

        self.assertEqual(observation.status, "success")
        self.assertIn("tool:temporal_health_lookup", observation.evidence_refs)
        self.assertIn("temporal:first_persistent_alert", observation.evidence_refs)
        self.assertIn("temporal:onset_confirmed", observation.evidence_refs)
        self.assertIn("health:dominant_evidence", observation.evidence_refs)
        self.assertIn("temporal:longest_alert_streak", observation.evidence_refs)
        payload = observation.payload
        self.assertEqual(payload["analysis_type"], "temporal_health_lookup")
        self.assertTrue(payload["available"])
        self.assertEqual(payload["run_limit"], 1)
        self.assertEqual(payload["n_runs_returned"], 1)
        self.assertEqual(payload["primary_run"]["current"]["health_state"], "critical")
        self.assertAlmostEqual(
            payload["primary_run"]["first_persistent_alert"]["x"],
            0.6,
        )
        self.assertIn("No estima RUL", payload["interpretation_guardrail"])
        json.dumps(observation.model_dump(mode="json"))

    def test_temporal_health_lookup_returns_missing_series_as_observation(self):
        request = AgentToolRequest(
            request_id="run-tools-temporal-001:cleaner:tool:health-missing",
            run_id="run-tools-temporal-001",
            agent_name="cleaner",
            tool_name="temporal_health_lookup",
            purpose="Comprobar si ya existe serie temporal.",
        )

        observation = run_agent_tool_request(_temporal_state(), request)

        self.assertEqual(observation.status, "success")
        self.assertFalse(observation.payload["available"])
        self.assertIn("temporal:predictions_missing", observation.evidence_refs)
        self.assertIn("tool:temporal_health_lookup", observation.evidence_refs)

    def test_degradation_metrics_lookup_returns_temporal_metric_payload(self):
        request = AgentToolRequest(
            request_id="run-tools-temporal-001:modeler:tool:metrics",
            run_id="run-tools-temporal-001",
            agent_name="modeler",
            tool_name="degradation_metrics_lookup",
            purpose="Consultar metricas temporales primarias.",
        )

        observation = run_agent_tool_request(_temporal_state(), request)

        self.assertEqual(observation.status, "success")
        self.assertIn("tool:degradation_metrics_lookup", observation.evidence_refs)
        self.assertIn(
            "metric:confirmed_degradation_before_failure_rate",
            observation.evidence_refs,
        )
        self.assertIn("metric:mean_health_index_drop", observation.evidence_refs)
        self.assertIn("metric:mean_lead_time_to_failure", observation.evidence_refs)
        self.assertIn("label_source:temporal_proxy", observation.evidence_refs)
        payload = observation.payload
        self.assertEqual(payload["analysis_type"], "degradation_metrics_lookup")
        self.assertTrue(payload["available"])
        self.assertEqual(
            payload["primary_metrics"]["confirmed_degradation_before_failure_rate"],
            1.0,
        )
        self.assertEqual(
            payload["primary_metrics"]["mean_persistent_lead_time_to_failure"],
            240.0,
        )
        self.assertEqual(payload["primary_metrics"]["mean_health_index_drop"], 64.0)
        self.assertEqual(
            payload["primary_metrics"]["mean_health_monotonicity"],
            0.9,
        )
        self.assertEqual(
            payload["primary_metrics"]["mean_lead_time_to_failure"],
            300.0,
        )
        self.assertIn("no son el criterio principal", payload["binary_metric_guardrail"])
        self.assertIn("etiquetas proxy", " ".join(payload["warnings"]))
        json.dumps(observation.model_dump(mode="json"))

    def test_temporal_model_readiness_blocks_when_features_missing(self):
        request = AgentToolRequest(
            request_id="run-tools-temporal-001:modeler:tool:readiness-missing",
            run_id="run-tools-temporal-001",
            agent_name="modeler",
            tool_name="temporal_model_readiness_assessor",
            purpose="Comprobar readiness antes de proponer autoencoder.",
        )

        observation = run_agent_tool_request(_temporal_state(), request)

        self.assertEqual(observation.status, "success")
        self.assertIn("tool:temporal_model_readiness_assessor", observation.evidence_refs)
        self.assertIn("readiness:autoencoder_blocked", observation.evidence_refs)
        self.assertFalse(observation.payload["autoencoder_ready"])
        self.assertFalse(observation.payload["rul_ready"])
        self.assertIn("features artifact is missing", observation.payload["blocked_reasons"])

    def test_temporal_model_readiness_allows_autoencoder_but_blocks_rul_for_single_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            features_path = Path(tmp) / "readiness_features.csv"
            _write_readiness_features(features_path)
            request = AgentToolRequest(
                request_id="run-tools-temporal-001:modeler:tool:readiness",
                run_id="run-tools-temporal-001",
                agent_name="modeler",
                tool_name="temporal_model_readiness_assessor",
                purpose="Valorar si procede autoencoder denso o RUL experimental.",
            )

            observation = run_agent_tool_request(
                _temporal_state_with_features(features_path),
                request,
            )

        self.assertEqual(observation.status, "success")
        self.assertIn("readiness:autoencoder_ready", observation.evidence_refs)
        self.assertIn("readiness:rul_blocked", observation.evidence_refs)
        payload = observation.payload
        self.assertEqual(payload["analysis_type"], "temporal_model_readiness")
        self.assertEqual(payload["policy_id"], "temporal_model_readiness_v1")
        self.assertTrue(payload["autoencoder_ready"])
        self.assertFalse(payload["rul_ready"])
        self.assertEqual(payload["n_train_nominal_windows"], 35)
        self.assertEqual(payload["n_feature_columns"], 3)
        self.assertIn(
            "insufficient_run_count_for_rul",
            payload["caution_reasons"],
        )
        self.assertEqual(
            payload["recommended_next_experiment"],
            "run_autoencoder_dense_cpu_smoke_before_rul",
        )
        self.assertIn("no entrena modelos", payload["interpretation_guardrail"])
        json.dumps(observation.model_dump(mode="json"))

    def test_temporal_health_lookup_rejects_invalid_run_limit(self):
        request = AgentToolRequest(
            request_id="run-tools-temporal-001:evaluator:tool:bad-health",
            run_id="run-tools-temporal-001",
            agent_name="evaluator",
            tool_name="temporal_health_lookup",
            purpose="Pedir un limite invalido.",
            arguments={"run_limit": 0},
        )

        observation = run_agent_tool_request(_temporal_state(), request)

        self.assertEqual(observation.status, "failed")
        self.assertIn("run_limit must be between", observation.errors[0])

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
            "degradation_detected_before_failure_rate": 1.0,
            "degradation_confirmed_degradation_before_failure_rate": 1.0,
            "degradation_mean_lead_time_to_failure": 300.0,
            "degradation_mean_persistent_lead_time_to_failure": 240.0,
            "degradation_mean_health_index_drop": 64.0,
            "degradation_mean_health_monotonicity": 0.9,
            "degradation_mean_health_robustness": 0.87,
            "degradation_mean_health_nominal_volatility": 4.0,
            "degradation_mean_health_indicator_score": 0.82,
            "degradation_mean_false_alarm_rate_nominal": 0.2,
            "degradation_mean_score_trend_spearman": 0.8,
            "degradation_missed_runs": 0,
            "degradation_missed_confirmed_degradation_runs": 0,
        }
    ).model_dump(mode="json")
    return validate_state(state_dict)


def _temporal_state_with_predictions(predictions_path: Path):
    state = _temporal_state().to_langgraph_state()
    state["artifacts"].append(
        {
            "name": "model_predictions",
            "artifact_type": "predictions",
            "path": predictions_path.as_posix(),
            "producer": "modeling_executor",
        }
    )
    return validate_state(state)


def _temporal_state_with_features(features_path: Path):
    state = _temporal_state().to_langgraph_state()
    state["artifacts"].append(
        {
            "name": "windows_features",
            "artifact_type": "features",
            "path": features_path.as_posix(),
            "producer": "structuring_executor",
        }
    )
    return validate_state(state)


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


def _write_temporal_predictions(path: Path) -> None:
    lines = [
        "window_id,run_id,window_index,time_since_start_seconds,"
        "time_to_failure_seconds,relative_life,split,label,target,"
        "anomaly_score,threshold,predicted_anomaly",
        "tw0,bearing_1_test_1,0,0,500,0.0,test,normal,0,0.10,0.60,0",
        "tw1,bearing_1_test_1,1,100,400,0.2,test,normal,0,0.65,0.60,1",
        "tw2,bearing_1_test_1,2,200,300,0.4,test,normal,0,0.30,0.60,0",
        "tw3,bearing_1_test_1,3,300,200,0.6,test,degradation,1,0.70,0.60,1",
        "tw4,bearing_1_test_1,4,400,100,0.8,test,degradation,1,0.80,0.60,1",
        "tw5,bearing_1_test_1,5,500,0,1.0,test,degradation,1,0.90,0.60,1",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_readiness_features(path: Path) -> None:
    lines = [
        "window_id,run_id,window_index,time_since_start_seconds,"
        "time_to_failure_seconds,relative_life,split,label,target,rms,energy,crest_factor"
    ]
    for index in range(50):
        split = "train" if index < 35 else "validation" if index < 42 else "test"
        label = "normal" if index < 35 else "degradation"
        target = 0 if label == "normal" else 1
        relative_life = index / 49
        lines.append(
            "rw{index},bearing_readiness_1,{index},{since},{ttf},{life:.4f},"
            "{split},{label},{target},{rms:.4f},{energy:.4f},{crest:.4f}".format(
                index=index,
                since=index * 60.0,
                ttf=(49 - index) * 60.0,
                life=relative_life,
                split=split,
                label=label,
                target=target,
                rms=0.2 + index * 0.01,
                energy=1.0 + index * 0.05,
                crest=1.5 + index * 0.005,
            )
        )
    path.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
