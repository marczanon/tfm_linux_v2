import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from codigo.app.executors.evaluation import evaluate_predictions, generate_evaluation_report
from codigo.app.schemas.temporal_health import SnapshotAggregationPolicy
from codigo.app.services.temporal_health_policy import aggregate_temporal_snapshots


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
            _degradation_row("r5", 0.98, 1, 1.00, 1, 990.0, 10.0, "degradation"),
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
            trajectory = pd.read_csv(
                summary["degradation_metrics"]["snapshot_trajectory_path"]
            )

        degradation = metrics["degradation_metrics"]
        run_metrics = degradation["run_metrics"][0]
        self.assertIn("run_to_failure_degradation", metrics["metric_families"])
        self.assertTrue(degradation["available"])
        self.assertEqual(degradation["n_runs"], 1)
        self.assertEqual(degradation["n_windows"], 6)
        self.assertEqual(degradation["n_snapshots"], 6)
        self.assertEqual(degradation["temporal_unit"], "snapshot")
        self.assertEqual(degradation["binary_metrics_unit"], "window")
        self.assertEqual(
            degradation["snapshot_aggregation_policy_id"],
            "snapshot_aggregation_v1",
        )
        self.assertEqual(degradation["snapshot_alert_fraction_threshold"], 0.5)
        self.assertEqual(len(trajectory), 6)
        self.assertEqual(degradation["health_policy_id"], "temporal_health_policy_v1")
        self.assertEqual(degradation["alert_policy_id"], "alert_persistence_v1")
        self.assertEqual(
            degradation["health_indicator_policy_id"],
            "health_indicator_policy_v1",
        )
        self.assertEqual(degradation["persistent_alert_min_windows"], 3)
        self.assertEqual(degradation["detected_runs"], 1)
        self.assertEqual(degradation["confirmed_degradation_runs"], 1)
        self.assertEqual(degradation["confirmed_degradation_before_failure_rate"], 1.0)
        self.assertGreater(degradation["mean_health_index_drop"], 0.0)
        self.assertEqual(degradation["mean_health_monotonicity"], 1.0)
        self.assertGreater(degradation["mean_health_robustness"], 0.8)
        self.assertFalse(run_metrics["missed_failure"])
        self.assertFalse(run_metrics["missed_confirmed_degradation"])
        self.assertEqual(run_metrics["lead_time_to_failure"], 300.0)
        self.assertEqual(run_metrics["persistent_alert_min_windows"], 3)
        self.assertEqual(run_metrics["persistent_alert_min_snapshots"], 3)
        self.assertEqual(run_metrics["n_windows"], 6)
        self.assertEqual(run_metrics["n_snapshots"], 6)
        self.assertEqual(run_metrics["first_persistent_alert_relative_life"], 0.70)
        self.assertEqual(run_metrics["persistent_lead_time_to_failure"], 300.0)
        self.assertEqual(run_metrics["longest_alert_streak"], 3)
        self.assertEqual(
            run_metrics["health_indicator_status"],
            "degrading_health_indicator",
        )
        self.assertEqual(run_metrics["health_dominant_evidence"], "score_above_threshold")
        self.assertEqual(run_metrics["false_alarm_rate_nominal"], 0.0)
        self.assertAlmostEqual(run_metrics["score_trend_spearman"], 1.0)
        self.assertIn("Politica de salud temporal", report)
        self.assertIn("Politica de Health Indicator", report)
        self.assertIn("Evaluacion temporal de degradacion", report)
        self.assertIn("label_source is not present", metrics["binary_metric_context"]["warning"])

    def test_overlapping_window_alerts_do_not_fake_snapshot_persistence(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            predictions_path = base / "predictions.csv"
            rows = []
            for index in range(3):
                row = _degradation_row(
                    f"r{index}",
                    0.70,
                    1,
                    0.90 + index * 0.01,
                    1,
                    700.0 + index,
                    300.0 - index,
                    "degradation",
                )
                row["file_id"] = "single_snapshot"
                rows.append(row)
            pd.DataFrame(rows).to_csv(predictions_path, index=False)

            summary = evaluate_predictions(predictions_path, base / "evaluation")
            degradation = summary["degradation_metrics"]
            run_metrics = degradation["run_metrics"][0]
            trajectory = pd.read_csv(degradation["snapshot_trajectory_path"])

        self.assertEqual(degradation["n_windows"], 3)
        self.assertEqual(degradation["n_snapshots"], 1)
        self.assertEqual(summary["primary_metrics"]["n_samples"], 3)
        self.assertEqual(run_metrics["n_windows"], 3)
        self.assertEqual(run_metrics["n_snapshots"], 1)
        self.assertEqual(run_metrics["alert_persistence"], 1)
        self.assertEqual(run_metrics["longest_alert_snapshot_streak"], 1)
        self.assertIsNone(run_metrics["first_persistent_alert_snapshot_id"])
        self.assertFalse(run_metrics["confirmed_degradation_before_failure"])
        self.assertTrue(run_metrics["missed_confirmed_degradation"])
        self.assertEqual(len(trajectory), 1)
        self.assertEqual(int(trajectory.iloc[0]["n_windows"]), 3)

    def test_snapshot_aggregation_uses_robust_score_and_explicit_alert_fraction(self):
        policy = SnapshotAggregationPolicy()
        rows = [
            {
                "run_id": "run-1",
                "file_id": "snapshot-1",
                "window_id": f"w{index}",
                "relative_life": 0.5,
                "anomaly_score": score,
                "threshold": 0.5,
                "predicted_anomaly": predicted,
            }
            for index, (score, predicted) in enumerate(
                [(0.1, 0), (0.2, 0), (10.0, 1)]
            )
        ]
        rows.extend(
            {
                "run_id": "run-1",
                "file_id": "snapshot-2",
                "window_id": f"half-{index}",
                "relative_life": 0.6,
                "anomaly_score": score,
                "threshold": 0.5,
                "predicted_anomaly": predicted,
            }
            for index, (score, predicted) in enumerate([(0.4, 0), (0.6, 1)])
        )

        snapshots = aggregate_temporal_snapshots(rows, policy=policy)

        robust = snapshots[0]
        threshold_boundary = snapshots[1]
        self.assertEqual(policy.policy_id, "snapshot_aggregation_v1")
        self.assertEqual(policy.alert_fraction_threshold, 0.5)
        self.assertAlmostEqual(robust["anomaly_score"], 0.2)
        self.assertAlmostEqual(robust["anomaly_score_p90"], 8.04)
        self.assertAlmostEqual(robust["anomaly_score_mean"], 10.3 / 3.0)
        self.assertGreater(robust["anomaly_score_std"], 4.0)
        self.assertAlmostEqual(robust["window_alert_fraction"], 1.0 / 3.0)
        self.assertEqual(robust["predicted_anomaly"], 0)
        self.assertEqual(threshold_boundary["window_alert_fraction"], 0.5)
        self.assertEqual(threshold_boundary["predicted_anomaly"], 1)

    def test_causal_v2_does_not_publish_binary_metrics_without_ground_truth(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            predictions_path = base / "predictions.csv"
            rows = []
            partitions = [
                ("baseline_train", "train", "normal", "temporal_proxy", 0),
                ("baseline_train", "train", "normal", "temporal_proxy", 0),
                ("calibration", "validation", "unknown", "none", 1),
                ("monitoring", "test", "unknown", "none", 1),
                ("monitoring", "test", "unknown", "none", 1),
                ("monitoring", "test", "unknown", "none", 1),
            ]
            for index, (partition, split, label, source, target) in enumerate(
                partitions
            ):
                row = _degradation_row(
                    f"r{index}",
                    index / 5,
                    target,
                    0.1 + index * 0.15,
                    int(index in {1, 4, 5}),
                    index * 600.0,
                    (5 - index) * 600.0,
                    label,
                )
                row.update(
                    {
                        "split": split,
                        "target": 0 if partition == "baseline_train" else "",
                        "label_source": source,
                        "label_granularity": (
                            "proxy_temporal" if source == "temporal_proxy" else "none"
                        ),
                        "temporal_partition": partition,
                        "dataset_policy_id": "nasa_ims_run_to_failure_v2",
                        "timestamp_start": f"2004-02-12T{10 + index // 6:02d}:{(index % 6) * 10:02d}:00",
                    }
                )
                rows.append(row)
            pd.DataFrame(rows).to_csv(predictions_path, index=False)

            summary = evaluate_predictions(predictions_path, base / "evaluation")
            report = Path(summary["report_fragment_path"]).read_text(encoding="utf-8")
            result = generate_evaluation_report(
                predictions_path,
                base / "structured_evaluation",
            )

        self.assertEqual(summary["metric_families"], ["run_to_failure_degradation"])
        self.assertFalse(summary["binary_metric_context"]["available"])
        self.assertEqual(
            summary["binary_metric_context"]["target_interpretation"],
            "not_ground_truth",
        )
        self.assertNotIn("precision", summary["primary_metrics"])
        self.assertNotIn("recall", summary["primary_metrics"])
        self.assertNotIn("f1_score", summary["primary_metrics"])
        self.assertNotIn("roc_auc", summary["primary_metrics"])
        self.assertNotIn("pr_auc", summary["primary_metrics"])
        run_metrics = summary["degradation_metrics"]["run_metrics"][0]
        self.assertEqual(
            run_metrics["false_alarm_reference"],
            "causal_v2_pre_monitoring_partitions",
        )
        self.assertEqual(run_metrics["false_alarm_reference_snapshots"], 3)
        self.assertAlmostEqual(run_metrics["false_alarm_rate_nominal"], 1 / 3)
        degradation = summary["degradation_metrics"]
        self.assertEqual(
            degradation["interpretation_mode"],
            "causal_v2_unlabeled",
        )
        self.assertFalse(degradation["binary_ground_truth_available"])
        self.assertFalse(
            degradation["physical_onset_ground_truth_available"]
        )
        self.assertEqual(
            degradation["persistent_alert_runs"],
            degradation["confirmed_degradation_runs"],
        )
        self.assertEqual(
            run_metrics["first_persistent_alert_time_to_trajectory_end"],
            run_metrics["persistent_lead_time_to_failure"],
        )
        self.assertIsNone(run_metrics["physical_onset_confirmed"])
        self.assertIsNone(run_metrics["physical_failure_detected"])
        self.assertIn("Metricas binarias supervisadas: `no publicadas`", report)
        self.assertIn("sin ground truth fisico", report)
        self.assertIn("alerta algoritmica persistente", report)
        self.assertIn("final registrado", report)
        self.assertNotIn("Runs detectados antes de fallo", report)
        self.assertNotIn("degradacion confirmada antes de fallo", report)
        self.assertNotIn("- F1-score:", report)
        self.assertEqual(result.status, "success")
        self.assertEqual(len(result.artifacts), 3)
        self.assertIsNone(result.artifacts[0].metadata["f1_score"])
        self.assertFalse(result.artifacts[0].metadata["binary_metrics_available"])

    def test_gap_resets_persistence_and_health_indicator_in_evaluation(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            predictions_path = base / "predictions.csv"
            times = [
                "2004-02-12T10:00:00",
                "2004-02-12T10:10:00",
                "2004-02-12T10:40:00",
                "2004-02-12T10:50:00",
            ]
            scores = [0.9, 0.8, 0.1, 0.2]
            rows = []
            for index, (timestamp, score) in enumerate(zip(times, scores, strict=True)):
                row = _degradation_row(
                    f"r{index}",
                    index / 3,
                    int(index > 1),
                    score,
                    1,
                    [0.0, 600.0, 2400.0, 3000.0][index],
                    [3000.0, 2400.0, 600.0, 0.0][index],
                    "normal" if index < 2 else "degradation",
                )
                row["timestamp_start"] = timestamp
                rows.append(row)
            pd.DataFrame(rows).to_csv(predictions_path, index=False)

            summary = evaluate_predictions(predictions_path, base / "evaluation")
            degradation = summary["degradation_metrics"]
            run_metrics = degradation["run_metrics"][0]
            trajectory = pd.read_csv(degradation["snapshot_trajectory_path"])

        self.assertEqual(degradation["temporal_gap_policy_id"], "temporal_gap_v1")
        self.assertEqual(degradation["n_detected_gaps"], 1)
        self.assertEqual(degradation["n_temporal_segments"], 2)
        self.assertEqual(degradation["n_cadence_intervals"], 3)
        self.assertEqual(degradation["n_cadence_matches"], 2)
        self.assertAlmostEqual(degradation["cadence_match_rate"], 2 / 3)
        self.assertEqual(run_metrics["longest_alert_streak"], 2)
        self.assertIsNone(run_metrics["first_persistent_alert_snapshot_id"])
        self.assertEqual(run_metrics["n_detected_gaps"], 1)
        self.assertEqual(run_metrics["n_temporal_segments"], 2)
        gap_row = trajectory.loc[trajectory["gap_detected"].astype(bool)].iloc[0]
        self.assertAlmostEqual(
            gap_row["health_index_smoothed"],
            gap_row["health_index_raw"],
        )
        for column in (
            "anomaly_score_median",
            "anomaly_score_p90",
            "window_alert_fraction",
            "health_index_raw",
            "health_index_smoothed",
            "health_state",
            "temporal_segment_id",
        ):
            self.assertIn(column, trajectory.columns)

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
