import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import savemat

from codigo.app.executors.data_profiler import build_data_profile, generate_data_profile


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


def write_manifest(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


class DataProfilerTests(unittest.TestCase):
    def test_build_profile_extracts_channel_stats(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            mat_path = base / "97.mat"
            manifest_path = base / "manifest.csv"
            savemat(
                mat_path,
                {
                    "X097_DE_time": np.array([[1.0], [2.0], [3.0], [np.nan]]),
                    "X097_FE_time": np.array([[2.0], [4.0]]),
                    "X097RPM": np.array([[1797]]),
                },
            )
            write_manifest(
                manifest_path,
                [
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
                        "source_sample_rate_hz": "48000",
                        "target_sample_rate_hz": "12000",
                        "source_format": "mat",
                        "notes": "normal_baseline",
                    }
                ],
            )

            profile = build_data_profile(manifest_path)

        de_stats = profile["files"][0]["channels"]["DE_time"]
        self.assertEqual(profile["n_files"], 1)
        self.assertEqual(profile["label_counts"], {"normal": 1})
        self.assertEqual(profile["channels_detected"], ["DE_time", "FE_time", "RPM"])
        self.assertEqual(de_stats["n_samples"], 4)
        self.assertEqual(de_stats["non_finite_count"], 1)
        self.assertAlmostEqual(de_stats["rms"], np.sqrt((1 + 4 + 9) / 3))
        self.assertNotIn("values", de_stats)

    def test_generate_profile_writes_json_and_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            mat_path = base / "105.mat"
            manifest_path = base / "manifest.csv"
            output_path = base / "profile.json"
            savemat(mat_path, {"X105_DE_time": np.array([[1.0], [2.0]])})
            write_manifest(
                manifest_path,
                [
                    {
                        "file_id": "105",
                        "dataset": "cwru_bearing",
                        "source_path": mat_path.as_posix(),
                        "label": "fault",
                        "fault_type": "inner_race",
                        "fault_diameter_inch": "0.007",
                        "load_hp": "0",
                        "rpm": "1797",
                        "sensor_channel": "DE_time",
                        "source_sample_rate_hz": "12000",
                        "target_sample_rate_hz": "12000",
                        "source_format": "mat",
                        "notes": "",
                    }
                ],
            )

            result = generate_data_profile(manifest_path, output_path)
            profile = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.n_files_profiled, 1)
        self.assertEqual(result.state_updates["profile_path"], output_path.as_posix())
        self.assertEqual(profile["fault_type_counts"], {"inner_race": 1})

    def test_missing_file_returns_failed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            manifest_path = base / "manifest.csv"
            missing_path = base / "missing.mat"
            write_manifest(
                manifest_path,
                [
                    {
                        "file_id": "999",
                        "dataset": "cwru_bearing",
                        "source_path": missing_path.as_posix(),
                        "label": "fault",
                        "fault_type": "ball",
                        "fault_diameter_inch": "0.007",
                        "load_hp": "0",
                        "rpm": "1797",
                        "sensor_channel": "DE_time",
                        "source_sample_rate_hz": "12000",
                        "target_sample_rate_hz": "12000",
                        "source_format": "mat",
                        "notes": "",
                    }
                ],
            )

            result = generate_data_profile(manifest_path, base / "profile.json")

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.n_files_profiled, 0)
        self.assertIn("missing.mat", result.errors[0].message)


if __name__ == "__main__":
    unittest.main()
