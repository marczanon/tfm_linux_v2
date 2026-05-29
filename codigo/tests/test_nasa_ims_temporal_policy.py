import csv
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from codigo.app.executors.structuring import build_temporal_dataset
from codigo.app.schemas.state import StructuringConfig
from codigo.app.services.dataset_adapters import get_dataset_adapter
from codigo.app.services.nasa_ims_temporal_policy import (
    NASA_IMS_TEMPORAL_POLICY_V1,
    apply_nasa_ims_temporal_policy,
)


class NasaIMSTemporalPolicyTests(unittest.TestCase):
    def test_policy_rewrites_labels_and_split_hints_by_temporal_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = _nasa_raw_dir(base)
            manifest_result = get_dataset_adapter("nasa_ims_bearing").build_manifest(
                raw_dir,
                base / "interim",
            )

            summary = apply_nasa_ims_temporal_policy(
                manifest_result.manifest_path,
                base / "interim" / "manifest_temporal_policy_v1.csv",
            )
            rows = _read_rows(Path(summary.manifest_path))

        self.assertEqual(summary.label_counts, {"normal": 2, "degradation": 1})
        self.assertEqual(summary.split_counts, {"train": 1, "test": 2})
        self.assertEqual([row["label"] for row in rows], ["normal", "normal", "degradation"])
        self.assertEqual(
            [_metadata(row)["split_hint"] for row in rows],
            ["train", "test", "test"],
        )
        self.assertTrue(all(_metadata(row)["official_nasa_labels"] is False for row in rows))
        self.assertTrue(
            all(
                _metadata(row)["dataset_policy_id"] == NASA_IMS_TEMPORAL_POLICY_V1
                for row in rows
            )
        )

    def test_structuring_uses_manifest_split_hints_when_available(self):
        with tempfile.TemporaryDirectory() as tmp:
            clean_dir = Path(tmp) / "clean"
            output_dir = Path(tmp) / "tensors"
            clean_dir.mkdir()
            _write_clean_file(clean_dir, "r0", "normal", "train")
            _write_clean_file(clean_dir, "r1", "normal", "test")
            _write_clean_file(clean_dir, "r2", "degradation", "test")

            summary = build_temporal_dataset(
                clean_dir,
                output_dir,
                StructuringConfig(
                    window_size=1024,
                    overlap=0.5,
                    main_channel="channel_1",
                    target_sample_rate_hz=20000,
                    label_mode="binary_anomaly",
                ),
            )
            splits = json.loads(Path(summary["splits_path"]).read_text(encoding="utf-8"))

        self.assertEqual(splits["strategy"], "metadata_json_split_hint")
        self.assertEqual(splits["files"]["train"], ["r0"])
        self.assertEqual(splits["files"]["test"], ["r1", "r2"])
        self.assertEqual(
            splits["label_counts_by_split"]["test"],
            {"normal": 3, "degradation": 3},
        )


def _nasa_raw_dir(base: Path) -> Path:
    raw_dir = base / "nasa_ims_bearing" / "2nd_test"
    raw_dir.mkdir(parents=True)
    for minute in [32, 42, 52]:
        (raw_dir / f"2004.02.12.10.{minute}.39").write_text(
            "0.1\t0.2\t0.3\t0.4\n0.2\t0.3\t0.4\t0.5\n",
            encoding="utf-8",
        )
    return raw_dir.parent


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _metadata(row: dict[str, str]) -> dict[str, object]:
    return json.loads(row["metadata_json"])


def _write_clean_file(
    clean_dir: Path,
    file_id: str,
    label: str,
    split_hint: str,
) -> None:
    signal = np.linspace(0.0, 1.0, 2048, dtype=np.float32)
    np.savez_compressed(
        clean_dir / f"{file_id}.npz",
        signal=signal,
        file_id=file_id,
        record_id=file_id,
        dataset="nasa_ims_bearing",
        label=label,
        fault_type="",
        label_detail="",
        condition_id="test_to_failure",
        run_id="set_2",
        source_path=f"{file_id}.txt",
        channel="channel_1",
        sample_rate_hz=20000,
        metadata_json=json.dumps(
            {
                "dataset_policy_id": NASA_IMS_TEMPORAL_POLICY_V1,
                "split_hint": split_hint,
            },
            sort_keys=True,
        ),
    )


if __name__ == "__main__":
    unittest.main()
