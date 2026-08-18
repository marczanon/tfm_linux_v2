import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np

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
    "temporal_partition",
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


def run_to_failure_v2_rows() -> list[dict[str, object]]:
    rows = [
        _row(
            index,
            "baseline",
            "train",
            "normal",
            0,
            value,
            value + 0.01,
            temporal_partition="baseline_train",
        )
        for index, value in enumerate([0.1, 0.2, 0.15, 0.18])
    ]
    rows.extend(
        [
            _row(
                4,
                "calibration",
                "validation",
                "unknown",
                "",
                0.12,
                0.13,
                temporal_partition="calibration",
            ),
            _row(
                5,
                "calibration",
                "validation",
                "unknown",
                "",
                0.16,
                0.17,
                temporal_partition="calibration",
            ),
            _row(
                6,
                "monitoring",
                "test",
                "unknown",
                "",
                0.14,
                0.15,
                temporal_partition="monitoring",
            ),
            _row(
                7,
                "monitoring",
                "test",
                "unknown",
                "",
                4.0,
                4.2,
                temporal_partition="monitoring",
            ),
        ]
    )
    return rows


def _row(
    index: int,
    file_id: str,
    split: str,
    label: str,
    target: int | str,
    mean: float,
    rms: float,
    fault_type: str = "",
    *,
    temporal_partition: str = "",
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
        "temporal_partition": temporal_partition,
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
        self.assertEqual(saved_summary["threshold_source_split"], "validation")
        self.assertIsNone(saved_summary["threshold_source_partition"])
        self.assertEqual(saved_summary["n_threshold_source_windows"], 2)
        self.assertEqual(saved_summary["n_calibration_windows"], 0)

    def test_run_to_failure_v2_calibrates_threshold_only_on_validation_partition(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            features_path = base / "features.csv"
            output_dir = base / "models"
            write_features(features_path, run_to_failure_v2_rows())

            summary = train_anomaly_model(
                features_path,
                output_dir,
                ModelingConfig(
                    model_name="pca_reconstruction_error",
                    random_state=42,
                    hyperparameters={
                        "n_components": 1,
                        "svd_solver": "full",
                        "threshold_quantile": 0.95,
                    },
                ),
            )
            with open(summary["predictions_path"], encoding="utf-8") as file:
                predictions = list(csv.DictReader(file))
            model_bundle = joblib.load(summary["model_path"])

        calibration_scores = np.asarray(
            [
                float(row["anomaly_score"])
                for row in predictions
                if row["temporal_partition"] == "calibration"
            ]
        )
        self.assertAlmostEqual(
            summary["threshold"],
            float(np.quantile(calibration_scores, 0.95)),
        )
        self.assertEqual(summary["threshold_source_split"], "validation")
        self.assertEqual(summary["threshold_source_partition"], "calibration")
        self.assertEqual(summary["n_threshold_source_windows"], 2)
        self.assertEqual(summary["n_calibration_windows"], 2)
        self.assertEqual(model_bundle["threshold_source_split"], "validation")
        self.assertEqual(model_bundle["threshold_source_partition"], "calibration")
        self.assertEqual(predictions[-1]["temporal_partition"], "monitoring")

    def test_run_to_failure_v2_monitoring_scores_cannot_change_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            config = ModelingConfig(
                model_name="pca_reconstruction_error",
                random_state=42,
                hyperparameters={
                    "n_components": 1,
                    "svd_solver": "full",
                    "threshold_quantile": 0.95,
                },
            )
            original_rows = run_to_failure_v2_rows()
            changed_rows = [dict(row) for row in original_rows]
            for row in changed_rows:
                if row["temporal_partition"] == "monitoring":
                    row["mean"] = float(row["mean"]) + 1000.0
                    row["rms"] = float(row["rms"]) - 500.0
            original_path = base / "original.csv"
            changed_path = base / "changed.csv"
            write_features(original_path, original_rows)
            write_features(changed_path, changed_rows)

            original = train_anomaly_model(original_path, base / "m1", config)
            changed = train_anomaly_model(changed_path, base / "m2", config)

        self.assertAlmostEqual(original["threshold"], changed["threshold"])

    def test_run_to_failure_v2_calibration_changes_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            config = ModelingConfig(
                model_name="pca_reconstruction_error",
                random_state=42,
                hyperparameters={
                    "n_components": 1,
                    "svd_solver": "full",
                    "threshold_quantile": 0.95,
                },
            )
            original_rows = run_to_failure_v2_rows()
            changed_rows = [dict(row) for row in original_rows]
            for row in changed_rows:
                if row["temporal_partition"] == "calibration":
                    row["rms"] = float(row["rms"]) + 10.0
            original_path = base / "original.csv"
            changed_path = base / "changed.csv"
            write_features(original_path, original_rows)
            write_features(changed_path, changed_rows)

            original = train_anomaly_model(original_path, base / "m1", config)
            changed = train_anomaly_model(changed_path, base / "m2", config)

        self.assertNotAlmostEqual(original["threshold"], changed["threshold"])

    def test_run_to_failure_v2_missing_calibration_blocks_threshold_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            rows = [
                row
                for row in run_to_failure_v2_rows()
                if row["temporal_partition"] != "calibration"
            ]
            features_path = base / "features.csv"
            write_features(features_path, rows)

            with self.assertRaisesRegex(
                ValueError,
                "requires calibration windows.*fallback to train/test is forbidden",
            ):
                train_anomaly_model(
                    features_path,
                    base / "models",
                    ModelingConfig(
                        model_name="pca_reconstruction_error",
                        random_state=42,
                        hyperparameters={
                            "n_components": 1,
                            "svd_solver": "full",
                            "threshold_quantile": 0.95,
                        },
                    ),
                )

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
        self.assertEqual(
            result.artifacts[0].metadata["threshold_source_split"],
            "validation",
        )
        self.assertEqual(result.artifacts[0].metadata["n_calibration_windows"], 0)
        self.assertEqual(
            result.artifacts[2].metadata["n_threshold_source_windows"],
            2,
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

    def test_invalid_autoencoder_hyperparameter_returns_failed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            features_path = base / "features.csv"
            write_features(features_path, feature_rows())

            result = generate_model_outputs(
                features_path,
                base / "models",
                ModelingConfig(
                    model_name="autoencoder_dense",
                    hyperparameters={"freeform_layers": "128,64"},
                ),
            )

        self.assertEqual(result.status, "failed")
        self.assertIn("unsupported autoencoder_dense", result.errors[0].message)

    @unittest.skipIf(
        importlib.util.find_spec("torch") is not None,
        "PyTorch is available; missing dependency path is not applicable.",
    )
    def test_autoencoder_returns_clear_error_when_pytorch_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            features_path = base / "features.csv"
            write_features(features_path, feature_rows())

            result = generate_model_outputs(
                features_path,
                base / "models",
                ModelingConfig(
                    model_name="autoencoder_dense",
                    random_state=42,
                    hyperparameters={
                        "hidden_layers": "4",
                        "latent_dim": 1,
                        "learning_rate": 0.001,
                        "batch_size": 4,
                        "max_epochs": 3,
                        "patience": 1,
                        "weight_decay": 0.0,
                        "threshold_quantile": 0.95,
                        "device": "cpu",
                    },
                ),
            )

        self.assertEqual(result.status, "failed")
        self.assertIn("PyTorch is required", result.errors[0].message)

    @unittest.skipIf(
        importlib.util.find_spec("torch") is None,
        "PyTorch is not installed in this environment.",
    )
    def test_train_autoencoder_dense_model_writes_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            features_path = base / "features.csv"
            output_dir = base / "models"
            write_features(features_path, feature_rows())

            summary = train_anomaly_model(
                features_path,
                output_dir,
                ModelingConfig(
                    model_name="autoencoder_dense",
                    random_state=42,
                    hyperparameters={
                        "hidden_layers": "4",
                        "latent_dim": 1,
                        "learning_rate": 0.001,
                        "batch_size": 4,
                        "max_epochs": 5,
                        "patience": 2,
                        "weight_decay": 0.0,
                        "threshold_quantile": 0.95,
                        "device": "cpu",
                    },
                ),
            )
            with open(summary["predictions_path"], encoding="utf-8") as file:
                predictions = list(csv.DictReader(file))
            preprocessor_exists = Path(summary["preprocessor_path"]).exists()
            training_curve_exists = Path(summary["training_curve_path"]).exists()

        self.assertEqual(summary["model_name"], "autoencoder_dense")
        self.assertEqual(summary["model_path"], (output_dir / "autoencoder_dense.pt").as_posix())
        self.assertEqual(summary["model_family"], "torch_autoencoder_dense")
        self.assertTrue(preprocessor_exists)
        self.assertTrue(training_curve_exists)
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
