import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from codigo.app.executors.evaluation import evaluate_predictions, generate_evaluation_report


def write_predictions(path: Path) -> None:
    pd.DataFrame(
        [
            _row("w0", "train", "normal", 0, 0.10, 0),
            _row("w1", "train", "normal", 0, 0.20, 0),
            _row("w2", "validation", "normal", 0, 0.80, 1),
            _row("w3", "test", "normal", 0, 0.20, 0),
            _row("w4", "test", "normal", 0, 0.90, 1),
            _row("w5", "test", "fault", 1, 0.85, 1, "inner_race"),
            _row("w6", "test", "fault", 1, 0.10, 0, "inner_race"),
        ]
    ).to_csv(path, index=False)


def write_degradation_predictions(path: Path) -> None:
    pd.DataFrame(
        [
            _degradation_row("r0", 0.00, 0, 0.10, 0, 0.0, 1000.0, "normal"),
            _degradation_row("r1", 0.20, 0, 0.15, 0, 250.0, 750.0, "normal"),
            _degradation_row("r2", 0.45, 1, 0.40, 0, 550.0, 450.0, "degradation"),
            _degradation_row("r3", 0.70, 1, 0.80, 1, 700.0, 300.0, "degradation"),
            _degradation_row("r4", 0.90, 1, 0.95, 1, 900.0, 100.0, "degradation"),
        ]
    ).to_csv(path, index=False)


def _row(
    window_id: str,
    split: str,
    label: str,
    target: int,
    score: float,
    predicted: int,
    fault_type: str = "",
) -> dict[str, object]:
    return {
        "window_id": window_id,
        "file_id": window_id,
        "split": split,
        "label": label,
        "target": target,
        "fault_type": fault_type,
        "anomaly_score": score,
        "threshold": 0.5,
        "predicted_anomaly": predicted,
    }


def _degradation_row(
    window_id: str,
    relative_life: float,
    target: int,
    score: float,
    predicted: int,
    time_since_start_seconds: float,
    time_to_failure_seconds: float,
    label: str,
) -> dict[str, object]:
    return {
        "window_id": window_id,
        "file_id": window_id,
        "condition_id": "ims_test",
        "asset_id": "bearing_1",
        "run_id": "run_to_failure_1",
        "window_index": int(window_id[1:]),
        "timestamp_start": f"2004-02-12T10:{int(window_id[1:]):02d}:00",
        "timestamp_end": f"2004-02-12T10:{int(window_id[1:]):02d}:01",
        "time_since_start_seconds": time_since_start_seconds,
        "time_to_failure_seconds": time_to_failure_seconds,
        "relative_life": relative_life,
        "split": "test",
        "label": label,
        "target": target,
        "fault_type": "",
        "anomaly_score": score,
        "threshold": 0.5,
        "predicted_anomaly": predicted,
    }


class EvaluationExecutorTests(unittest.TestCase):
    def test_evaluate_predictions_writes_metrics_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            predictions_path = base / "predictions.csv"
            output_dir = base / "evaluation"
            write_predictions(predictions_path)

            summary = evaluate_predictions(predictions_path, output_dir)
            metrics = json.loads(Path(summary["metrics_path"]).read_text(encoding="utf-8"))
            report = Path(summary["report_fragment_path"]).read_text(encoding="utf-8")

        test_metrics = metrics["metrics_by_split"]["test"]
        self.assertEqual(summary["primary_split"], "test")
        self.assertEqual(test_metrics["confusion_matrix"], {"tn": 1, "fp": 1, "fn": 1, "tp": 1})
        self.assertEqual(test_metrics["precision"], 0.5)
        self.assertEqual(test_metrics["recall"], 0.5)
        self.assertIn("F1-score", report)

    def test_evaluate_predictions_adds_degradation_metrics_when_temporal_columns_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            predictions_path = base / "predictions.csv"
            output_dir = base / "evaluation"
            write_degradation_predictions(predictions_path)

            summary = evaluate_predictions(predictions_path, output_dir)
            metrics = json.loads(Path(summary["metrics_path"]).read_text(encoding="utf-8"))
            report = Path(summary["report_fragment_path"]).read_text(encoding="utf-8")

        degradation = metrics["degradation_metrics"]
        run_metrics = degradation["run_metrics"][0]
        self.assertIn("run_to_failure_degradation", metrics["metric_families"])
        self.assertTrue(degradation["available"])
        self.assertEqual(degradation["n_runs"], 1)
        self.assertEqual(degradation["n_windows"], 5)
        self.assertEqual(degradation["detected_runs"], 1)
        self.assertFalse(run_metrics["missed_failure"])
        self.assertEqual(run_metrics["lead_time_to_failure"], 300.0)
        self.assertEqual(run_metrics["false_alarm_rate_nominal"], 0.0)
        self.assertAlmostEqual(run_metrics["score_trend_spearman"], 1.0)
        self.assertIn("Evaluacion temporal de degradacion", report)
        self.assertIn("label_source is not present", metrics["binary_metric_context"]["warning"])

    def test_generate_evaluation_report_returns_structured_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            predictions_path = base / "predictions.csv"
            output_dir = base / "evaluation"
            write_predictions(predictions_path)

            result = generate_evaluation_report(predictions_path, output_dir)

        self.assertEqual(result.status, "success")
        self.assertEqual(result.metrics_path, (output_dir / "metrics.json").as_posix())
        self.assertEqual(result.report_fragment_path, (output_dir / "evaluation_summary.md").as_posix())
        self.assertEqual([artifact.artifact_type for artifact in result.artifacts], ["metrics", "report"])
        self.assertEqual(
            [artifact.name for artifact in result.artifacts],
            ["evaluation_metrics", "evaluation_summary"],
        )

    def test_missing_required_columns_returns_failed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            predictions_path = base / "predictions.csv"
            pd.DataFrame([{"target": 0}]).to_csv(predictions_path, index=False)

            result = generate_evaluation_report(predictions_path, base / "evaluation")

        self.assertEqual(result.status, "failed")
        self.assertIn("missing prediction columns", result.errors[0].message)

    def test_duplicate_window_id_returns_failed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            predictions_path = base / "predictions.csv"
            write_predictions(predictions_path)
            data = pd.read_csv(predictions_path)
            data.loc[1, "window_id"] = data.loc[0, "window_id"]
            data.to_csv(predictions_path, index=False)

            result = generate_evaluation_report(predictions_path, base / "evaluation")

        self.assertEqual(result.status, "failed")
        self.assertIn("duplicated window_id", result.errors[0].message)


if __name__ == "__main__":
    unittest.main()
