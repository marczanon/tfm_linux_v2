import csv
import json
import tempfile
import unittest
from pathlib import Path

from codigo.app.services.iteration_analysis import (
    build_prediction_failure_analysis,
    generate_prediction_failure_analysis,
)


FIELDS = [
    "window_id",
    "file_id",
    "split",
    "label",
    "target",
    "fault_type",
    "anomaly_score",
    "threshold",
    "predicted_anomaly",
]


class IterationAnalysisTests(unittest.TestCase):
    def test_failure_analysis_summarizes_false_negatives_and_threshold_direction(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            predictions_path = base / "predictions.csv"
            metrics_path = base / "metrics.json"
            _write_predictions(
                predictions_path,
                [
                    _row("tn", "normal", 0, 0.20, 0),
                    _row("fp", "normal", 0, 0.80, 1),
                    _row("fn", "fault", 1, 0.40, 0),
                    _row("tp", "fault", 1, 0.90, 1),
                ],
            )
            metrics_path.write_text(
                json.dumps(
                    {
                        "primary_metrics": {
                            "precision": 0.5,
                            "recall": 0.5,
                            "f1_score": 0.5,
                            "false_positive_rate": 0.5,
                        }
                    }
                ),
                encoding="utf-8",
            )

            analysis = build_prediction_failure_analysis(
                predictions_path,
                metrics_path=metrics_path,
                attempt_number=1,
                max_attempts=2,
            )

        self.assertEqual(analysis["confusion_matrix"], {"tn": 1, "fp": 1, "fn": 1, "tp": 1})
        self.assertIn("low_recall_many_missed_anomalies", analysis["failure_modes"])
        self.assertIn("high_false_positive_rate", analysis["failure_modes"])
        self.assertEqual(analysis["false_negative_summary"]["count"], 1)
        self.assertIn("Lowering", analysis["decision_guidance"]["scoring_convention"])

    def test_generate_failure_analysis_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            predictions_path = base / "predictions.csv"
            _write_predictions(
                predictions_path,
                [
                    _row("tn", "normal", 0, 0.20, 0),
                    _row("tp", "fault", 1, 0.90, 1),
                ],
            )

            artifacts = generate_prediction_failure_analysis(
                predictions_path,
                base / "analysis",
            )

            self.assertTrue(Path(artifacts.analysis_path).exists())
            self.assertTrue(Path(artifacts.report_path).exists())
            self.assertEqual(artifacts.analysis["false_negative_summary"]["count"], 0)


def _row(
    window_id: str,
    label: str,
    target: int,
    score: float,
    predicted: int,
) -> dict[str, object]:
    return {
        "window_id": window_id,
        "file_id": f"file-{window_id}",
        "split": "test",
        "label": label,
        "target": target,
        "fault_type": "",
        "anomaly_score": score,
        "threshold": 0.60,
        "predicted_anomaly": predicted,
    }


def _write_predictions(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
