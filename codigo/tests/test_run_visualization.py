import asyncio
import json
import tempfile
import unittest
from pathlib import Path

import httpx

from codigo.app.api import create_app
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import (
    ArtifactRef,
    EvaluationResult,
    MetricsReport,
    StateMessage,
)
from codigo.app.services.run_persistence import save_run_snapshot
from codigo.app.services.run_visualization import build_run_visualization


class RunVisualizationTests(unittest.TestCase):
    def test_visualization_endpoint_returns_metrics_projection_and_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            state = _state_with_visual_artifacts(base, "run-viz")
            save_run_snapshot(state, runs_dir)
            app = create_app(runs_dir=runs_dir)

            response = _get(
                app,
                "/runs/run-viz/visualization",
                params={"max_points": 50},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["run_id"], "run-viz")
        self.assertTrue(payload["projection_available"])
        self.assertEqual(payload["n_points_total"], 60)
        self.assertLessEqual(payload["n_points_sampled"], 50)
        self.assertTrue(payload["projection_points"])
        self.assertIsNotNone(payload["projection_boundary"])
        self.assertIn("features", payload["source_paths"])
        metrics = {item["name"]: item["value"] for item in payload["metrics"]}
        self.assertEqual(metrics["f1_score"], 0.91)

    def test_visualization_endpoint_returns_temporal_degradation_series(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            state = _state_with_temporal_artifacts(base, "run-temporal-viz")
            save_run_snapshot(state, runs_dir)
            app = create_app(runs_dir=runs_dir)

            response = _get(
                app,
                "/runs/run-temporal-viz/visualization",
                params={"max_points": 50},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["supervision_profile"], "run_to_failure_degradation")
        self.assertEqual(payload["label_source"], "temporal_proxy")
        self.assertEqual(payload["model_name"], "pca_reconstruction_error")
        self.assertEqual(payload["projection_role"], "diagnostic")
        self.assertIn("run_to_failure_degradation", payload["metric_families"])
        primary = {item["name"]: item for item in payload["primary_metrics"]}
        self.assertEqual(
            primary["detected_before_failure_rate"]["metric_family"],
            "run_to_failure_degradation",
        )
        self.assertEqual(primary["mean_lead_time_to_failure"]["value_kind"], "seconds")
        auxiliary = {item["name"]: item["metric_family"] for item in payload["auxiliary_metrics"]}
        self.assertEqual(auxiliary["f1_score"], "binary_classification")
        temporal = payload["temporal_series"]
        self.assertTrue(temporal["available"])
        self.assertEqual(temporal["x_axis"], "relative_life")
        self.assertEqual(temporal["n_runs_total"], 1)
        run = temporal["runs"][0]
        self.assertEqual(run["run_id"], "bearing_1_test_1")
        self.assertEqual(run["n_points_total"], 8)
        self.assertAlmostEqual(run["first_alert_x"], 0.714, places=3)
        self.assertAlmostEqual(run["first_alert_time_to_failure_seconds"], 300.0)
        self.assertAlmostEqual(run["first_persistent_alert_x"], 0.571, places=3)
        self.assertEqual(run["persistent_alert_min_windows"], 3)
        self.assertEqual(run["failure_x"], 1.0)
        self.assertEqual(run["failure_reference"], "historic_replay")
        self.assertEqual(run["threshold"], 0.6)
        self.assertEqual(run["current_health_state"], "critical")
        self.assertAlmostEqual(run["current_health_index"], 0.0)
        self.assertEqual(run["alert_points"], 4)
        self.assertEqual(run["warning_points"], 2)
        self.assertEqual(run["critical_points"], 2)
        self.assertEqual(run["isolated_alert_points"], 0)
        self.assertEqual(run["alert_episodes"], 1)
        self.assertEqual(run["longest_alert_streak"], 4)
        self.assertTrue(run["points"])
        self.assertEqual(run["points"][0]["health_state"], "nominal")
        self.assertGreater(run["points"][0]["health_index"], 80.0)
        self.assertEqual(run["points"][-1]["health_state"], "critical")

    def test_visualization_endpoint_returns_agent_recommendation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            state = _state_with_temporal_agent_decisions(
                base,
                "run-temporal-agent-viz",
            )
            save_run_snapshot(state, runs_dir)
            app = create_app(runs_dir=runs_dir)

            response = _get(
                app,
                "/runs/run-temporal-agent-viz/visualization",
                params={"max_points": 50},
            )

        self.assertEqual(response.status_code, 200)
        recommendation = response.json()["agent_recommendation"]
        self.assertTrue(recommendation["available"])
        self.assertEqual(recommendation["source_agent"], "evaluator")
        self.assertEqual(recommendation["status"], "caution")
        self.assertEqual(recommendation["confidence"], 0.78)
        self.assertIn("temporal:current_health", recommendation["evidence_refs"])
        self.assertIn("temporal_health_lookup", recommendation["tool_names"])
        self.assertIn(
            "RUL no estimado; solo lead time historico.",
            recommendation["limitations"],
        )
        self.assertTrue(recommendation["guardrail_checks"])
        self.assertIn("pca_reconstruction_error", recommendation["modeler_summary"])

    def test_visualization_service_degrades_when_projection_artifacts_are_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            state = _state_without_visual_artifacts(base, "run-no-viz")
            save_run_snapshot(state, runs_dir)

            payload = build_run_visualization("run-no-viz", runs_dir)

        self.assertFalse(payload.projection_available)
        self.assertEqual(payload.projection_points, [])
        self.assertTrue(payload.warnings)
        self.assertEqual(payload.metrics[2].name, "f1_score")

    def test_visualization_service_projects_features_without_predictions(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            state = _state_with_feature_artifact(base, "run-diagnostic-viz")
            save_run_snapshot(state, runs_dir)

            payload = build_run_visualization("run-diagnostic-viz", runs_dir)

        self.assertTrue(payload.projection_available)
        self.assertEqual(payload.projection_boundary, None)
        self.assertTrue(payload.projection_points)
        self.assertIn("features", payload.source_paths)
        self.assertNotIn("predictions", payload.source_paths)
        self.assertTrue(any("predicciones" in warning for warning in payload.warnings))


def _state_with_visual_artifacts(base: Path, run_id: str):
    features_path = base / "features.csv"
    predictions_path = base / "predictions.csv"
    _write_visual_csvs(features_path, predictions_path)
    state = _state_with_feature_artifact(base, run_id)
    state.artifacts.extend(
        [
            ArtifactRef(
                name="model_predictions",
                artifact_type="predictions",
                path=str(predictions_path),
                producer="modeling_executor",
            ),
        ]
    )
    return state


def _state_with_temporal_artifacts(base: Path, run_id: str):
    features_path = base / "temporal_features.csv"
    predictions_path = base / "temporal_predictions.csv"
    metrics_path = base / "temporal_metrics.json"
    _write_temporal_csvs(features_path, predictions_path)
    _write_temporal_metrics(metrics_path)
    state = _state_without_visual_artifacts(base, run_id, run_to_failure=True)
    state.artifacts.extend(
        [
            ArtifactRef(
                name="windows_features",
                artifact_type="features",
                path=str(features_path),
                producer="structuring_executor",
            ),
            ArtifactRef(
                name="model_predictions",
                artifact_type="predictions",
                path=str(predictions_path),
                producer="modeling_executor",
            ),
            ArtifactRef(
                name="evaluation_metrics",
                artifact_type="metrics",
                path=str(metrics_path),
                producer="evaluation_executor",
            ),
        ]
    )
    return state


def _state_with_temporal_agent_decisions(base: Path, run_id: str):
    state = _state_with_temporal_artifacts(base, run_id)
    modeler_decision = {
        "agent_name": "modeler",
        "decision_id": f"{run_id}:modeler:001",
        "rationale": "PCA permite score continuo para degradacion temporal.",
        "confidence": 0.74,
        "modeling_config": {
            "model_name": "pca_reconstruction_error",
            "hyperparameters": {"threshold_quantile": 0.99},
        },
        "decision_strategy": {
            "strategy_type": "temporal_anomaly_score",
            "hypothesis": (
                "El score de reconstruccion debe crecer hacia el tramo final."
            ),
            "tool_names": [
                "temporal_health_lookup",
                "degradation_metrics_lookup",
            ],
            "evidence_refs": [
                "temporal:current_health",
                "degradation:mean_lead_time_to_failure",
            ],
            "optimization_targets": [
                "detected_before_failure_rate",
                "mean_lead_time_to_failure",
            ],
            "alert_policy": "primer pico separado de aviso sostenido",
        },
    }
    evaluator_decision = {
        "agent_name": "evaluator",
        "decision_id": f"{run_id}:evaluator:001",
        "rationale": "La deteccion llega antes del fallo historico.",
        "confidence": 0.78,
        "tool_names": [
            "temporal_health_lookup",
            "degradation_metrics_lookup",
        ],
        "evidence_refs": [
            "temporal:current_health",
            "temporal:first_persistent_alert",
            "degradation:mean_lead_time_to_failure",
        ],
        "operational_assessment": (
            "Monitorizacion defendible como replay historico, con aviso "
            "sostenido antes de fallo."
        ),
        "temporal_debate_points": [
            "El primer pico no debe confundirse con degradacion sostenida.",
            "El aviso sostenido reduce ruido frente a ventanas aisladas.",
        ],
        "temporal_guardrail_checks": [
            "F1 tratada como metrica auxiliar.",
            "RUL no estimado por el pipeline actual.",
        ],
        "evaluation": {
            "approved": True,
            "summary": "Aprobada con cautelas temporales.",
            "next_action": "continue",
            "limitations": [
                "RUL no estimado; solo lead time historico.",
                "Etiquetas proxy temporales.",
            ],
        },
    }
    state.messages.extend(
        [
            StateMessage(
                role="agent",
                name="modeler",
                content=json.dumps(modeler_decision),
            ),
            StateMessage(
                role="agent",
                name="evaluator",
                content=json.dumps(evaluator_decision),
            ),
        ]
    )
    return state


def _state_with_feature_artifact(base: Path, run_id: str):
    features_path = base / "features.csv"
    predictions_path = base / "predictions.csv"
    _write_visual_csvs(features_path, predictions_path)
    state = _state_without_visual_artifacts(base, run_id)
    state.artifacts.append(
        ArtifactRef(
            name="windows_features",
            artifact_type="features",
            path=str(features_path),
            producer="structuring_executor",
        )
    )
    return state


def _state_without_visual_artifacts(
    base: Path,
    run_id: str,
    *,
    run_to_failure: bool = False,
):
    state_dict = create_initial_cwru_state(
        thread_id=f"thread-{run_id}",
        run_id=run_id,
        raw_path=str(base / "raw"),
    )
    if run_to_failure:
        state_dict["project_context"].update(
            {
                "dataset": "nasa_ims_bearing",
                "machine_type": "rotating_machinery",
                "objective": "run_to_failure_degradation",
                "label_mode": "degradation",
                "supervision_profile": "run_to_failure_degradation",
                "label_source": "temporal_proxy",
                "label_granularity": "proxy_temporal",
                "main_channel": "channel_1",
            }
        )
    state_dict["current_stage"] = "completed"
    state_dict["next_node"] = None
    state_dict["metrics"] = MetricsReport(
        metrics_path=str(base / "metrics.json"),
        precision=0.90,
        recall=0.92,
        f1_score=0.91,
        false_positive_rate=0.03,
        extra=(
            {
                "metric_families": (
                    "binary_classification, run_to_failure_degradation"
                ),
                "degradation_available": True,
            }
            if run_to_failure
            else {}
        ),
    ).model_dump(mode="json")
    if run_to_failure:
        state_dict["modeling_config"] = {
            "model_name": "pca_reconstruction_error",
            "random_state": 42,
            "hyperparameters": {"threshold_quantile": 0.99},
        }
    state_dict["evaluation"] = EvaluationResult(
        approved=True,
        summary="Run aprobada.",
        next_action="continue",
        limitations=[],
    ).model_dump(mode="json")
    return validate_state(state_dict)


def _write_visual_csvs(features_path: Path, predictions_path: Path) -> None:
    features_lines = [
        "window_id,split,label,target,fault_type,mean,std,rms,energy",
    ]
    prediction_lines = [
        "window_id,split,label,target,fault_type,anomaly_score,threshold,predicted_anomaly",
    ]
    for index in range(60):
        anomaly = int(index >= 45)
        label = "fault" if anomaly else "normal"
        score = 0.70 + index * 0.01 if anomaly else 0.20 + index * 0.002
        features_lines.append(
            f"w{index},test,{label},{anomaly},{label},{index * 0.1:.3f},"
            f"{1.0 + anomaly * 1.5:.3f},{1.1 + index * 0.03:.3f},"
            f"{10 + anomaly * 20 + index:.3f}"
        )
        prediction_lines.append(
            f"w{index},test,{label},{anomaly},{label},{score:.3f},0.600,{anomaly}"
        )
    features_path.write_text("\n".join(features_lines), encoding="utf-8")
    predictions_path.write_text("\n".join(prediction_lines), encoding="utf-8")


def _write_temporal_csvs(features_path: Path, predictions_path: Path) -> None:
    features_lines = [
        "window_id,run_id,relative_life,split,label,target,mean,std,rms,energy",
    ]
    prediction_lines = [
        "window_id,run_id,window_index,timestamp_start,timestamp_end,"
        "time_since_start_seconds,time_to_failure_seconds,relative_life,"
        "split,label,target,anomaly_score,threshold,predicted_anomaly",
    ]
    for index in range(8):
        relative_life = index / 7
        predicted = int(index >= 5)
        label = "degradation" if index >= 3 else "normal"
        target = int(label != "normal")
        time_since_start = index * 100.0
        time_to_failure = 800.0 - time_since_start
        score = 0.12 + index * 0.13
        features_lines.append(
            f"tw{index},bearing_1_test_1,{relative_life:.3f},test,{label},"
            f"{target},{index * 0.2:.3f},{1.0 + index * 0.04:.3f},"
            f"{1.1 + index * 0.07:.3f},{8.0 + index * 1.5:.3f}"
        )
        prediction_lines.append(
            f"tw{index},bearing_1_test_1,{index},"
            f"2004-02-12T10:{index:02d}:00,2004-02-12T10:{index:02d}:01,"
            f"{time_since_start:.1f},{time_to_failure:.1f},{relative_life:.3f},"
            f"test,{label},{target},{score:.3f},0.600,{predicted}"
        )
    features_path.write_text("\n".join(features_lines), encoding="utf-8")
    predictions_path.write_text("\n".join(prediction_lines), encoding="utf-8")


def _write_temporal_metrics(metrics_path: Path) -> None:
    metrics_path.write_text(
        """
{
  "metric_families": ["binary_classification", "run_to_failure_degradation"],
  "binary_metric_context": {
    "label_source": "temporal_proxy",
    "label_granularity": "proxy_temporal"
  },
  "degradation_metrics": {
    "available": true,
    "detected_before_failure_rate": 1.0,
    "mean_lead_time_to_failure": 300.0,
    "mean_false_alarm_rate_nominal": 0.125,
    "mean_score_trend_spearman": 0.91,
    "missed_runs": 0,
    "mean_initial_final_separation": 0.42
  }
}
""".strip(),
        encoding="utf-8",
    )


def _get(app, path: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(path, **kwargs)

    return asyncio.run(request())


if __name__ == "__main__":
    unittest.main()
