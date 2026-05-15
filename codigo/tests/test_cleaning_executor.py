import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import savemat

from codigo.app.executors.cleaning import clean_dataset, generate_clean_signals
from codigo.app.schemas.state import CleaningConfig


FIELDS = [
    "file_id",
    "dataset",
    "source_path",
    "label",
    "fault_type",
    "fault_diameter_inch",
    "load_hp",
    "rpm",
    "sensor_channel",
    "source_sample_rate_hz",
    "target_sample_rate_hz",
    "source_format",
    "notes",
]


def write_manifest(path: Path, mat_path: Path, sample_rate: int = 4) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow(
            {
                "file_id": "97",
                "dataset": "cwru_bearing",
                "source_path": mat_path.as_posix(),
                "label": "normal",
                "fault_type": "",
                "fault_diameter_inch": "",
                "load_hp": "0",
                "rpm": "1797",
                "sensor_channel": "DE_time",
                "source_sample_rate_hz": str(sample_rate),
                "target_sample_rate_hz": "2",
                "source_format": "mat",
                "notes": "normal_baseline",
            }
        )


def write_profile(path: Path, n_files: int = 1) -> None:
    path.write_text(json.dumps({"n_files": n_files}), encoding="utf-8")


class CleaningExecutorTests(unittest.TestCase):
    def test_clean_dataset_removes_non_finite_and_resamples(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            mat_path = base / "97.mat"
            manifest_path = base / "manifest.csv"
            profile_path = base / "profile.json"
            output_dir = base / "clean"
            summary_path = base / "summary.json"
            savemat(mat_path, {"X097_DE_time": np.array([[1.0], [np.nan], [3.0], [5.0]])})
            write_manifest(manifest_path, mat_path)
            write_profile(profile_path)

            summary = clean_dataset(
                manifest_path,
                profile_path,
                output_dir,
                CleaningConfig(
                    strategy_id="test_clean",
                    remove_non_finite=True,
                    resample_to_hz=2,
                    normalization="none",
                    audit_log_path=summary_path.as_posix(),
                ),
            )
            data = np.load(output_dir / "97.npz")

        self.assertEqual(summary["n_files"], 1)
        self.assertEqual(summary["files"][0]["non_finite_removed"], 1)
        self.assertEqual(summary["files"][0]["sample_rate_hz"], 2)
        self.assertLess(data["signal"].size, 4)
        self.assertEqual(data["label"].item(), "normal")

    def test_generate_clean_signals_returns_structured_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            mat_path = base / "97.mat"
            manifest_path = base / "manifest.csv"
            profile_path = base / "profile.json"
            output_dir = base / "clean"
            savemat(mat_path, {"X097_DE_time": np.array([[1.0], [2.0]])})
            write_manifest(manifest_path, mat_path, sample_rate=2)
            write_profile(profile_path)

            result = generate_clean_signals(
                manifest_path,
                profile_path,
                output_dir,
                CleaningConfig(
                    strategy_id="test_clean",
                    remove_non_finite=True,
                    resample_to_hz=2,
                    normalization="zscore",
                    audit_log_path=(base / "summary.json").as_posix(),
                ),
            )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.n_files_cleaned, 1)
        self.assertEqual(result.state_updates["clean_path"], output_dir.as_posix())
        self.assertEqual(len(result.artifacts), 2)

    def test_profile_manifest_mismatch_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            mat_path = base / "97.mat"
            manifest_path = base / "manifest.csv"
            profile_path = base / "profile.json"
            savemat(mat_path, {"X097_DE_time": np.array([[1.0], [2.0]])})
            write_manifest(manifest_path, mat_path)
            write_profile(profile_path, n_files=2)

            result = generate_clean_signals(manifest_path, profile_path, base / "clean")

        self.assertEqual(result.status, "failed")
        self.assertIn("profile and manifest file counts", result.errors[0].message)


if __name__ == "__main__":
    unittest.main()
