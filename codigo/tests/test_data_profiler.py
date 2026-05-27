import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import savemat

from codigo.app.executors.data_profiler import (
    build_data_profile,
    generate_data_profile,
)
from codigo.app.executors.dataset_manifest import generate_dataset_manifest


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
        decision = profile["decision_summary"]
        self.assertEqual(decision["quality_status"], "needs_resampling")
        self.assertIn("resample", decision["required_actions"])
        self.assertIn("select_channel", decision["required_actions"])
        self.assertIn("DE_time", decision["recommended_channels"])
        self.assertTrue(decision["supported_cleaning_options"])

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

    def test_build_profile_uses_csv_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            csv_path = base / "signals.csv"
            manifest_path = base / "manifest.csv"
            pd.DataFrame(
                {"sensor_a": [1.0, 2.0, np.nan], "tag": ["x", "y", "z"]}
            ).to_csv(csv_path, index=False)
            write_manifest(
                manifest_path,
                [
                    {
                        "file_id": "csv-001",
                        "dataset": "cwru_bearing",
                        "source_path": csv_path.as_posix(),
                        "label": "normal",
                        "fault_type": "",
                        "fault_diameter_inch": "",
                        "load_hp": "0",
                        "rpm": "0",
                        "sensor_channel": "sensor_a",
                        "source_sample_rate_hz": "100",
                        "target_sample_rate_hz": "100",
                        "source_format": "csv",
                        "notes": "",
                    }
                ],
            )

            profile = build_data_profile(manifest_path)

        stats = profile["files"][0]["channels"]["sensor_a"]
        self.assertEqual(profile["channels_detected"], ["sensor_a"])
        self.assertEqual(stats["n_samples"], 3)
        self.assertEqual(stats["non_finite_count"], 1)
        decision = profile["decision_summary"]
        self.assertEqual(decision["quality_status"], "clean")
        self.assertEqual(decision["required_actions"], ["remove_non_finite"])
        self.assertEqual(decision["recommended_channels"], ["sensor_a"])

    def test_build_profile_uses_common_nasa_ims_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "nasa_ims_bearing"
            snapshot = raw_dir / "2nd_test" / "2004.02.12.10.32.39"
            snapshot.parent.mkdir(parents=True)
            snapshot.write_text(
                "0.1\t0.2\t0.3\t0.4\n0.5\t0.6\t0.7\t0.8\n",
                encoding="utf-8",
            )
            manifest_result = generate_dataset_manifest(
                raw_dir,
                base / "interim",
                adapter_id="nasa_ims_bearing",
            )

            profile = build_data_profile(manifest_result.manifest_path)

        channel_1 = profile["files"][0]["channels"]["channel_1"]
        self.assertEqual(manifest_result.status, "success")
        self.assertEqual(profile["dataset"], "nasa_ims_bearing")
        self.assertEqual(profile["manifest_format"], "common")
        self.assertEqual(profile["n_files"], 1)
        self.assertEqual(profile["label_counts"], {"unknown": 1})
        self.assertEqual(profile["sample_rate_counts"], {"20000": 1})
        self.assertEqual(profile["run_counts"], {"set_2": 1})
        self.assertEqual(
            profile["channels_detected"],
            ["channel_1", "channel_2", "channel_3", "channel_4"],
        )
        self.assertEqual(profile["files"][0]["primary_channel"], "channel_1")
        self.assertEqual(profile["files"][0]["n_channels_manifest"], 4)
        self.assertEqual(profile["files"][0]["metadata"]["points_per_file"], 20480)
        self.assertEqual(channel_1["n_samples"], 2)
        self.assertAlmostEqual(channel_1["mean"], 0.3)
        decision = profile["decision_summary"]
        self.assertEqual(decision["quality_status"], "needs_channel_selection")
        self.assertEqual(
            decision["recommended_channels"],
            ["channel_1", "channel_2", "channel_3", "channel_4"],
        )
        self.assertIn("select_channel", decision["required_actions"])
        self.assertIn(
            "sample_count_differs_from_manifest_expectation",
            decision["non_blocking_warnings"],
        )
        self.assertEqual(
            decision["supported_cleaning_options"][0]["selected_channel"],
            "channel_1",
        )

    def test_build_profile_marks_constant_channel_as_insufficient_quality(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            csv_path = base / "constant.csv"
            manifest_path = base / "manifest.csv"
            pd.DataFrame({"sensor_a": [5.0, 5.0, 5.0, 5.0]}).to_csv(
                csv_path,
                index=False,
            )
            write_manifest(
                manifest_path,
                [
                    {
                        "file_id": "constant-001",
                        "dataset": "cwru_bearing",
                        "source_path": csv_path.as_posix(),
                        "label": "normal",
                        "fault_type": "",
                        "fault_diameter_inch": "",
                        "load_hp": "0",
                        "rpm": "0",
                        "sensor_channel": "sensor_a",
                        "source_sample_rate_hz": "100",
                        "target_sample_rate_hz": "100",
                        "source_format": "csv",
                        "notes": "",
                    }
                ],
            )

            profile = build_data_profile(manifest_path)

        channel = profile["files"][0]["channels"]["sensor_a"]
        decision = profile["decision_summary"]
        self.assertIn("constant_signal", channel["quality_flags"])
        self.assertEqual(decision["quality_status"], "insufficient_quality")
        self.assertEqual(decision["recommended_channels"], [])
        self.assertEqual(decision["blocking_warnings"], ["no_viable_signal_channel"])
        self.assertTrue(decision["candidate_channels"][0]["blocking"])

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
