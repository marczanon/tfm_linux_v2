import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from codigo.app.executors.structuring import (
    build_temporal_dataset,
    generate_temporal_structure,
)
from codigo.app.schemas.state import StructuringConfig


def write_clean_file(
    path: Path,
    signal: list[float],
    *,
    file_id: str,
    label: str,
    fault_type: str = "",
    sample_rate: int = 12000,
) -> None:
    np.savez_compressed(
        path,
        signal=np.asarray(signal, dtype=np.float32),
        file_id=file_id,
        label=label,
        fault_type=fault_type,
        channel="DE_time",
        sample_rate_hz=sample_rate,
    )


class StructuringExecutorTests(unittest.TestCase):
    def test_build_temporal_dataset_writes_features_tensors_and_splits(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            clean_dir = base / "clean"
            output_dir = base / "tensors"
            clean_dir.mkdir()
            write_clean_file(clean_dir / "97.npz", [1, 2, 3, 4, 5, 6, 7, 8], file_id="97", label="normal")
            write_clean_file(
                clean_dir / "105.npz",
                [2, 4, 6, 8, 10, 12, 14, 16],
                file_id="105",
                label="fault",
                fault_type="inner_race",
            )

            summary = build_temporal_dataset(
                clean_dir,
                output_dir,
                StructuringConfig(window_size=4, overlap=0.5),
            )
            with Path(summary["features_path"]).open(encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            tensors = np.load(summary["tensors_path"])
            splits = json.loads(Path(summary["splits_path"]).read_text(encoding="utf-8"))

        self.assertEqual(summary["n_windows"], 6)
        self.assertEqual(tensors["windows"].shape, (6, 4))
        self.assertEqual(rows[0]["split"], "train")
        self.assertEqual(rows[0]["target"], "0")
        self.assertIn("rms", rows[0])
        self.assertEqual(splits["files"]["test"], ["105"])
        self.assertEqual(splits["window_counts"], {"train": 3, "test": 3})

    def test_generate_temporal_structure_returns_structured_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            clean_dir = base / "clean"
            output_dir = base / "tensors"
            clean_dir.mkdir()
            write_clean_file(clean_dir / "97.npz", [1, 2, 3, 4], file_id="97", label="normal")

            result = generate_temporal_structure(
                clean_dir,
                output_dir,
                StructuringConfig(window_size=4, overlap=0.0, features=["mean", "energy"]),
            )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.n_windows, 1)
        self.assertEqual(result.state_updates["tensor_path"], (output_dir / "windows_raw.npz").as_posix())
        self.assertEqual(result.state_updates["splits_path"], (output_dir / "splits.json").as_posix())
        self.assertEqual(len(result.artifacts), 3)

    def test_sample_rate_mismatch_returns_failed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            clean_dir = base / "clean"
            clean_dir.mkdir()
            write_clean_file(
                clean_dir / "97.npz",
                [1, 2, 3, 4],
                file_id="97",
                label="normal",
                sample_rate=48000,
            )

            result = generate_temporal_structure(
                clean_dir,
                base / "tensors",
                StructuringConfig(window_size=4, target_sample_rate_hz=12000),
            )

        self.assertEqual(result.status, "failed")
        self.assertIn("sample_rate_hz=48000", result.errors[0].message)


if __name__ == "__main__":
    unittest.main()
