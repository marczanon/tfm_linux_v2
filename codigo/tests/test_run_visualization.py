import asyncio
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


def _state_with_visual_artifacts(base: Path, run_id: str):
    features_path = base / "features.csv"
    predictions_path = base / "predictions.csv"
    _write_visual_csvs(features_path, predictions_path)
    state = _state_without_visual_artifacts(base, run_id)
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
        ]
    )
    return state


def _state_without_visual_artifacts(base: Path, run_id: str):
    state_dict = create_initial_cwru_state(
        thread_id=f"thread-{run_id}",
        run_id=run_id,
        raw_path=str(base / "raw"),
    )
    state_dict["current_stage"] = "completed"
    state_dict["next_node"] = None
    state_dict["metrics"] = MetricsReport(
        metrics_path=str(base / "metrics.json"),
        precision=0.90,
        recall=0.92,
        f1_score=0.91,
        false_positive_rate=0.03,
    ).model_dump(mode="json")
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
