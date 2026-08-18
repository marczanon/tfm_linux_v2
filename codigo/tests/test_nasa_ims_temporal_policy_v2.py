import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from codigo.app.schemas.dataset import CommonManifestRecord
from codigo.app.schemas.temporal_health import (
    RunToFailurePartitionPolicy,
    TemporalGapPolicy,
)
from codigo.app.services.common_manifest import (
    read_common_manifest,
    write_common_manifest,
)
from codigo.app.services.nasa_ims_temporal_policy import (
    NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
    apply_nasa_ims_run_to_failure_policy_v2,
)


class NasaIMSRunToFailurePolicyV2Tests(unittest.TestCase):
    def test_policy_contracts_freeze_partition_and_gap_rules(self):
        partition = RunToFailurePartitionPolicy()
        gaps = TemporalGapPolicy()

        self.assertEqual(partition.policy_id, NASA_IMS_RUN_TO_FAILURE_POLICY_V2)
        self.assertEqual(
            (
                partition.baseline_fraction,
                partition.calibration_fraction,
                partition.monitoring_fraction,
            ),
            (0.20, 0.10, 0.70),
        )
        self.assertEqual(partition.allocation_method, "largest_remainder_v1")
        self.assertEqual(gaps.policy_id, "temporal_gap_v1")
        self.assertEqual(gaps.expected_cadence_seconds, 600.0)
        self.assertEqual(gaps.max_contiguous_interval_seconds, 900.0)
        self.assertTrue(gaps.reset_alert_persistence)
        self.assertTrue(gaps.reset_causal_smoothing)

        with self.assertRaises(ValidationError):
            RunToFailurePartitionPolicy(baseline_fraction=0.25)
        with self.assertRaises(ValidationError):
            TemporalGapPolicy(max_contiguous_interval_seconds=1200.0)

    def test_v2_sorts_records_and_applies_20_10_70_without_degradation_proxy(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "manifest.csv"
            output = base / "manifest_v2.csv"
            records = _official_records(10)
            write_common_manifest(source, list(reversed(records)))

            summary = apply_nasa_ims_run_to_failure_policy_v2(source, output)
            rewritten = read_common_manifest(output)

        self.assertEqual(summary.partition_counts, {
            "baseline_train": 2,
            "calibration": 1,
            "monitoring": 7,
        })
        self.assertEqual(summary.split_counts, {
            "train": 2,
            "validation": 1,
            "test": 7,
        })
        self.assertEqual(summary.label_counts, {"normal": 2, "unknown": 8})
        self.assertEqual(
            [record.timestamp_start for record in rewritten],
            sorted(record.timestamp_start for record in rewritten),
        )
        self.assertEqual(
            [record.metadata_json["temporal_partition"] for record in rewritten],
            ["baseline_train"] * 2 + ["calibration"] + ["monitoring"] * 7,
        )
        self.assertEqual(
            [record.metadata_json["split_hint"] for record in rewritten],
            ["train"] * 2 + ["validation"] + ["test"] * 7,
        )
        self.assertEqual(
            [record.label for record in rewritten],
            ["normal"] * 2 + ["unknown"] * 8,
        )
        self.assertNotIn("degradation", {record.label for record in rewritten})
        self.assertTrue(
            all(record.data_provenance == "official" for record in rewritten)
        )
        self.assertTrue(
            all(
                record.metadata_json["official_nasa_labels"] is False
                for record in rewritten
            )
        )
        self.assertTrue(
            all(
                record.metadata_json["official_window_labels"] is False
                for record in rewritten
            )
        )
        self.assertEqual(
            [record.metadata_json["label_source"] for record in rewritten],
            ["temporal_proxy"] * 2 + ["none"] * 8,
        )
        self.assertEqual(summary.n_intervals, 9)
        self.assertEqual(summary.cadence_interval_counts, {"600": 9})
        self.assertEqual(summary.cadence_match_count, 9)
        self.assertEqual(summary.cadence_deviation_count, 0)
        self.assertEqual(summary.gap_count, 0)
        self.assertEqual(summary.max_interval_seconds, 600.0)

    def test_v2_requires_official_provenance_for_every_record(self):
        for provenance in ("synthetic", "unknown"):
            with self.subTest(provenance=provenance), tempfile.TemporaryDirectory() as tmp:
                base = Path(tmp)
                source = base / "manifest.csv"
                records = _official_records(10)
                records[4] = _record(
                    4,
                    records[4].timestamp_start,
                    provenance=provenance,
                )
                write_common_manifest(source, records)

                with self.assertRaisesRegex(
                    ValueError,
                    "requires official data provenance.*record-0004",
                ):
                    apply_nasa_ims_run_to_failure_policy_v2(
                        source,
                        base / "manifest_v2.csv",
                    )

    def test_set2_size_uses_exact_largest_remainder_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "manifest.csv"
            output = base / "manifest_v2.csv"
            write_common_manifest(source, _official_records(984))

            summary = apply_nasa_ims_run_to_failure_policy_v2(source, output)

        self.assertEqual(summary.n_rows, 984)
        self.assertEqual(summary.partition_counts, {
            "baseline_train": 197,
            "calibration": 98,
            "monitoring": 689,
        })
        self.assertEqual(summary.split_counts, {
            "train": 197,
            "validation": 98,
            "test": 689,
        })
        self.assertEqual(summary.label_counts, {"normal": 197, "unknown": 787})
        self.assertEqual(summary.n_intervals, 983)
        self.assertEqual(summary.cadence_interval_counts, {"600": 983})
        self.assertEqual(summary.cadence_match_count, 983)
        self.assertEqual(summary.gap_count, 0)

    def test_gap_audit_marks_missing_snapshot_and_starts_new_segment(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "manifest.csv"
            output = base / "manifest_v2.csv"
            offsets = [0, 600, 1200, 1800, 2400, 3600, 4200, 4800, 5400, 6000]
            write_common_manifest(
                source,
                [
                    _record(
                        index,
                        _START + timedelta(seconds=offset),
                    )
                    for index, offset in enumerate(offsets)
                ],
            )

            summary = apply_nasa_ims_run_to_failure_policy_v2(source, output)
            rewritten = read_common_manifest(output)

        gap_row = rewritten[5]
        self.assertEqual(summary.cadence_interval_counts, {"1200": 1, "600": 8})
        self.assertEqual(summary.cadence_match_count, 8)
        self.assertEqual(summary.cadence_deviation_count, 1)
        self.assertEqual(summary.gap_count, 1)
        self.assertEqual(summary.max_interval_seconds, 1200.0)
        self.assertTrue(gap_row.metadata_json["gap_before"])
        self.assertEqual(gap_row.metadata_json["gap_before_seconds"], 1200.0)
        self.assertEqual(
            gap_row.metadata_json["estimated_missing_snapshots_before"],
            1,
        )
        self.assertEqual(gap_row.metadata_json["temporal_segment_index"], 1)
        self.assertEqual(rewritten[4].metadata_json["temporal_segment_index"], 0)
        self.assertEqual(rewritten[-1].metadata_json["temporal_segment_index"], 1)

    def test_duplicate_timestamps_are_rejected_after_stable_sort(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            records = _official_records(10)
            records[5] = _record(5, records[4].timestamp_start)
            source = base / "manifest.csv"
            write_common_manifest(source, records)

            with self.assertRaisesRegex(ValueError, "strictly increasing timestamps"):
                apply_nasa_ims_run_to_failure_policy_v2(
                    source,
                    base / "manifest_v2.csv",
                )


_START = datetime(2004, 2, 12, 10, 32, 39)
_EVIDENCE_PATH = "/fixture/official_dataset_provenance.json"
_EVIDENCE_SHA256 = "a" * 64


def _official_records(n_records: int) -> list[CommonManifestRecord]:
    return [
        _record(index, _START + timedelta(seconds=index * 600))
        for index in range(n_records)
    ]


def _record(
    index: int,
    timestamp: datetime | None,
    *,
    provenance: str = "official",
) -> CommonManifestRecord:
    is_official = provenance == "official"
    return CommonManifestRecord(
        record_id=f"record-{index:04d}",
        dataset="nasa_ims_bearing",
        source_path=f"/fixture/2nd_test/record-{index:04d}",
        source_format="txt",
        data_provenance=provenance,
        label="unknown",
        label_detail="bearing_1_outer_race",
        condition_id="test_to_failure",
        asset_id="bearing_test_rig",
        run_id="set_2",
        timestamp_start=timestamp,
        timestamp_end=(
            None if timestamp is None else timestamp + timedelta(seconds=1.024)
        ),
        sampling_rate_hz=20000,
        target_sample_rate_hz=20000,
        channel_names=["channel_1", "channel_2", "channel_3", "channel_4"],
        primary_channel="channel_1",
        n_channels=4,
        metadata_json={
            "data_provenance": provenance,
            "official_nasa_measurements": is_official,
            "provenance_detection_method": (
                "official_dataset_provenance" if is_official else "unverified"
            ),
            "provenance_evidence_path": _EVIDENCE_PATH if is_official else None,
            "provenance_evidence_sha256": (
                _EVIDENCE_SHA256 if is_official else None
            ),
            "official_subset_id": "set_2" if is_official else None,
            "failure_event_time": "2004-02-19T06:22:40.024000",
            "failure_mode": "bearing_1_outer_race",
            "final_failure": "bearing_1_outer_race",
        },
        notes="preextracted_nasa_ims_snapshot; readme_set_2",
    )


if __name__ == "__main__":
    unittest.main()
