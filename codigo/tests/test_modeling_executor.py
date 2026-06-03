import csv
import json
import tempfile
import unittest
from pathlib import Path

import joblib

from codigo.app.executors.modeling import generate_model_outputs, train_anomaly_model
from codigo.app.schemas.state import ModelingConfig


FIELDS = [
    "window_id",
    "file_id",
    "condition_id",
    "asset_id",
    "run_id",
    "window_index",
    "start",
    "end",
    "timestamp_start",
    "timestamp_end",
    "time_since_start_seconds",
    "time_to_failure_seconds",
    "relative_life",
    "split",
    "label",
    "target",
    "fault_type",
    "sample_rate_hz",
    "channel",
    "mean",
    "rms",
]


def write_features(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def feature_rows() -> list[dict[str, object]]:
    rows = []
    for index, value in enumerate([0.1, 0.2, 0.15, 0.18]):
        rows.append(_row(index, "97", "train", "normal", 0, value, value + 0.01))
    for index, value in enumerate([0.12, 0.16], start=4):
        rows.append(_row(index, "98", "validation", "normal", 0, value, value + 0.01))
    rows.append(_row(6, "99", "test", "normal", 0, 0.14, 0.15))
    rows.append(_row(7, "105", "test", "fault", 1, 4.0, 4.2, "inner_race"))
    return rows


def _row(
    index: int,
    file_id: str,
    split: str,
    label: str,
    target: int,
    mean: float,
    rms: float,
    fault_type: str = "",
) -> dict[str, object]:
    return {
        "window_id": f"{file_id}_{index:06d}",
        "file_id": file_id,
        "condition_id": "test_to_failure",
        "asset_id": "bearing_test_rig",
        "run_id": "set_2",
        "window_index": index,
        "start": index * 4,
        "end": index * 4 + 4,
        "timestamp_start": "",
        "timestamp_end": "",
        "time_since_start_seconds": index,
        "time_to_failure_seconds": 100 - index,
        "relative_life": index / 100,
        "split": split,
        "label": label,
        "target": target,
        "fault_type": fault_type,
        "sample_rate_hz": 12000,
        "channel": "DE_time",
        "mean": mean,
        "rms": rms,
    }


class ModelingExecutorTests(unittest.TestCase):
    def test_train_anomaly_model_writes_model_predictions_and_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            features_path = base / "features.csv"
            output_dir = base / "models"
            write_features(features_path, feature_rows())

            summary = train_anomaly_model(
                features_path,
                output_dir,
                ModelingConfig(
                    model_name="isolation_forest",
                    random_state=7,
                    hyperparameters={"n_estimators": 25, "threshold_quantile": 0.95},
                ),
            )
            model_bundle = joblib.load(summary["model_path"])
            with open(summary["predictions_path"], encoding="utf-8") as file:
                predictions = list(csv.DictReader(file))
            saved_summary = json.loads(Path(summary["summary_path"]).read_text(encoding="utf-8"))

        self.assertEqual(summary["n_train_windows"], 4)
        self.assertEqual(summary["n_predictions"], 8)
        self.assertEqual(model_bundle["feature_columns"], ["mean", "rms"])
        self.assertEqual(len(predictions), 8)
        self.assertEqual(predictions[0]["run_id"], "set_2")
        self.assertEqual(predictions[0]["relative_life"], "0.0")
        self.assertIn("anomaly_score", predictions[0])
        self.assertEqual(saved_summary["model_name"], "isolation_forest")

    def test_generate_model_outputs_returns_structured_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            features_path = base / "features.csv"
            output_dir = base / "models"
            write_features(features_path, feature_rows())

            result = generate_model_outputs(
                features_path,
                output_dir,
                ModelingConfig(
                    model_name="isolation_forest",
                    random_state=42,
                    hyperparameters={"n_estimators": 10, "threshold_quantile": 0.95},
                ),
            )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.model_path, (output_dir / "isolation_forest.joblib").as_posix())
        self.assertEqual(result.predictions_path, (output_dir / "predictions.csv").as_posix())
        self.assertEqual([artifact.artifact_type for artifact in result.artifacts], ["model", "predictions", "log"])
        self.assertEqual(
            [artifact.name for artifact in result.artifacts],
            ["isolation_forest_model", "model_predictions", "modeling_summary"],
        )

    def test_train_pca_reconstruction_model_writes_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            features_path = base / "features.csv"
            output_dir = base / "models"
            write_features(features_path, feature_rows())

            summary = train_anomaly_model(
                features_path,
                output_dir,
                ModelingConfig(
                    model_name="pca_reconstruction_error",
                    random_state=42,
                    hyperparameters={
                        "n_components": 0.95,
                        "svd_solver": "full",
                        "threshold_quantile": 0.95,
                    },
                ),
            )
            model_bundle = joblib.load(summary["model_path"])
            with open(summary["predictions_path"], encoding="utf-8") as file:
                predictions = list(csv.DictReader(file))

        self.assertEqual(summary["model_name"], "pca_reconstruction_error")
        self.assertEqual(
            summary["model_path"],
            (output_dir / "pca_reconstruction_error.joblib").as_posix(),
        )
        self.assertIn("scaler", model_bundle)
        self.assertEqual(len(predictions), 8)
        self.assertIn("anomaly_score", predictions[0])

    def test_train_one_class_svm_model_writes_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            features_path = base / "features.csv"
            output_dir = base / "models"
            write_features(features_path, feature_rows())

            summary = train_anomaly_model(
                features_path,
                output_dir,
                ModelingConfig(
                    model_name="one_class_svm",
                    random_state=42,
                    hyperparameters={
                        "kernel": "rbf",
                        "nu": 0.25,
                        "gamma": "scale",
                        "shrinking": True,
                        "tol": 0.001,
                        "max_iter": -1,
                        "threshold_quantile": 0.95,
                    },
                ),
            )
            model_bundle = joblib.load(summary["model_path"])
            with open(summary["predictions_path"], encoding="utf-8") as file:
                predictions = list(csv.DictReader(file))

        self.assertEqual(summary["model_name"], "one_class_svm")
        self.assertEqual(
            summary["model_path"],
            (output_dir / "one_class_svm.joblib").as_posix(),
        )
        self.assertEqual(model_bundle["model_family"], "sklearn_one_class_svm")
        self.assertIn("scaler", model_bundle)
        self.assertEqual(len(predictions), 8)
        self.assertIn("anomaly_score", predictions[0])

    def test_invalid_one_class_svm_hyperparameter_returns_failed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            features_path = base / "features.csv"
            write_features(features_path, feature_rows())

            result = generate_model_outputs(
                features_path,
                base / "models",
                ModelingConfig(
                    model_name="one_class_svm",
                    hyperparameters={"kernel": "rbf", "nu": 1.5},
                ),
            )

        self.assertEqual(result.status, "failed")
        self.assertIn("one_class_svm nu", result.errors[0].message)

    def test_unsupported_model_returns_failed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            features_path = base / "features.csv"
            write_features(features_path, feature_rows())

            result = generate_model_outputs(
                features_path,
                base / "models",
                ModelingConfig(model_name="local_outlier_factor"),
            )

        self.assertEqual(result.status, "failed")
        self.assertIn("unsupported model_name", result.errors[0].message)


if __name__ == "__main__":
    unittest.main()
