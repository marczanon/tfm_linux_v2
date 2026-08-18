import json
import tempfile
import unittest
from pathlib import Path

from codigo.app.services.dataset_adapters import (
    describe_dataset,
    get_dataset_adapter,
    infer_dataset_adapter,
    list_dataset_adapters,
)


class DatasetAdaptersTests(unittest.TestCase):
    def test_registry_lists_expected_adapters(self):
        infos = list_dataset_adapters()

        adapter_ids = {info.adapter_id for info in infos}
        self.assertIn("cwru_bearing", adapter_ids)
        self.assertIn("nasa_ims_bearing", adapter_ids)
        self.assertIn("generic_tabular_signal", adapter_ids)
        nasa_info = next(
            info for info in infos if info.adapter_id == "nasa_ims_bearing"
        )
        self.assertTrue(nasa_info.supports_manifest)
        self.assertIn("zip", nasa_info.supported_source_formats)

    def test_unknown_adapter_returns_clear_error(self):
        with self.assertRaisesRegex(ValueError, "unknown dataset adapter"):
            get_dataset_adapter("missing_adapter")

    def test_infer_cwru_adapter_from_mat_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp)
            (raw_dir / "97.mat").touch()

            adapter = infer_dataset_adapter(raw_dir)
            descriptor = adapter.describe(raw_dir)

        self.assertEqual(adapter.info.adapter_id, "cwru_bearing")
        self.assertEqual(descriptor.dataset_id, "cwru_bearing")
        self.assertIn("DE_time", descriptor.channel_names)
        self.assertEqual(descriptor.label_availability, "file_level")
        self.assertEqual(descriptor.supervision_profile, "binary_fault_classification")
        self.assertEqual(descriptor.label_granularity, "file")
        self.assertEqual(descriptor.label_source, "official")

    def test_nasa_hint_does_not_match_incidental_substrings(self):
        with tempfile.TemporaryDirectory(prefix="tmpims") as tmp:
            raw_dir = Path(tmp)
            (raw_dir / "97.mat").touch()

            adapter = infer_dataset_adapter(raw_dir)

        self.assertEqual(adapter.info.adapter_id, "cwru_bearing")

    def test_describe_dataset_uses_explicit_nasa_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "nasa_ims_bearing"
            raw_dir.mkdir()
            (raw_dir / "2003.10.22.12.06.24.txt").write_text(
                "0.1 0.2 0.3 0.4\n0.2 0.3 0.4 0.5\n",
                encoding="utf-8",
            )

            descriptor = describe_dataset(raw_dir, adapter_id="nasa_ims_bearing")

        self.assertEqual(descriptor.dataset_id, "nasa_ims_bearing")
        self.assertEqual(descriptor.task_type, "run_to_failure")
        self.assertEqual(descriptor.supervision_profile, "run_to_failure_degradation")
        self.assertEqual(descriptor.label_granularity, "event")
        self.assertEqual(descriptor.label_source, "none")
        self.assertEqual(descriptor.data_provenance, "unknown")
        self.assertEqual(descriptor.provenance_detection_method, "unverified")
        self.assertIsNone(descriptor.provenance_evidence_path)
        self.assertEqual(
            descriptor.channel_names,
            ["channel_1", "channel_2", "channel_3", "channel_4"],
        )
        self.assertTrue(descriptor.has_run_to_failure)
        self.assertEqual(descriptor.metadata["candidate_file_count"], 1)
        self.assertEqual(descriptor.metadata["inferred_n_channels"], 4)
        self.assertFalse(descriptor.metadata["inconsistent_channel_counts"])

    def test_nasa_descriptor_and_manifest_trace_synthetic_spec_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_root = Path(tmp) / "synthetic_nasa_ims"
            raw_dir = raw_root / "2nd_test"
            raw_dir.mkdir(parents=True)
            (raw_dir / "2004.02.12.10.32.39").write_text(
                "0.1\t0.2\t0.3\t0.4\n0.2\t0.3\t0.4\t0.5\n",
                encoding="utf-8",
            )
            spec_path = raw_root / "synthetic_dataset_spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "dataset": "nasa_ims_bearing",
                        "synthetic": True,
                        "seed": 42,
                    }
                ),
                encoding="utf-8",
            )

            adapter = get_dataset_adapter("nasa_ims_bearing")
            descriptor = adapter.describe(raw_root)
            result = adapter.build_manifest(raw_root, Path(tmp) / "interim")
            rows = _read_manifest_rows(Path(result.manifest_path))
            metadata = _metadata(rows[0])

        self.assertEqual(descriptor.data_provenance, "synthetic")
        self.assertEqual(
            descriptor.provenance_detection_method,
            "synthetic_dataset_spec",
        )
        self.assertEqual(descriptor.provenance_evidence_path, spec_path.as_posix())
        self.assertRegex(descriptor.provenance_evidence_sha256 or "", r"^[0-9a-f]{64}$")
        self.assertTrue(any("no son mediciones oficiales" in note for note in descriptor.notes))
        self.assertEqual(rows[0]["data_provenance"], "synthetic")
        self.assertEqual(metadata["data_provenance"], "synthetic")
        self.assertEqual(
            metadata["provenance_detection_method"],
            "synthetic_dataset_spec",
        )
        self.assertFalse(metadata["official_nasa_measurements"])
        self.assertEqual(result.artifacts[0].metadata["data_provenance"], "synthetic")
        self.assertEqual(result.state_updates["data_provenance"], "synthetic")

    def test_nasa_rejects_inconsistent_synthetic_provenance_spec(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_root = Path(tmp) / "synthetic_nasa_ims"
            raw_dir = raw_root / "2nd_test"
            raw_dir.mkdir(parents=True)
            (raw_dir / "2004.02.12.10.32.39").write_text(
                "0.1\t0.2\t0.3\t0.4\n",
                encoding="utf-8",
            )
            (raw_root / "synthetic_dataset_spec.json").write_text(
                json.dumps(
                    {
                        "dataset": "nasa_ims_bearing",
                        "synthetic": False,
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "synthetic=true"):
                describe_dataset(raw_root, adapter_id="nasa_ims_bearing")

    def test_infers_nasa_adapter_from_timestamp_files_without_dataset_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "bearing_run"
            raw_dir.mkdir()
            (raw_dir / "2003.10.22.12.06.24").write_text(
                "0.1 0.2\n0.2 0.3\n",
                encoding="utf-8",
            )

            adapter = infer_dataset_adapter(raw_dir)
            descriptor = adapter.describe(raw_dir)

        self.assertEqual(adapter.info.adapter_id, "nasa_ims_bearing")
        self.assertEqual(descriptor.channel_names, ["channel_1", "channel_2"])
        self.assertEqual(descriptor.metadata["file_extensions"], "<none>")

    def test_nasa_descriptor_reports_inconsistent_channel_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "nasa_ims_bearing"
            raw_dir.mkdir()
            (raw_dir / "2003.10.22.12.06.24.txt").write_text(
                "0.1 0.2 0.3 0.4\n",
                encoding="utf-8",
            )
            (raw_dir / "2003.10.22.12.16.24.txt").write_text(
                "0.1 0.2 0.3\n",
                encoding="utf-8",
            )

            descriptor = describe_dataset(raw_dir, adapter_id="nasa_ims_bearing")

        self.assertTrue(descriptor.metadata["inconsistent_channel_counts"])
        self.assertEqual(descriptor.metadata["channel_count_values"], "3,4")
        self.assertTrue(
            any("inconsistentes" in note for note in descriptor.notes),
        )

    def test_nasa_manifest_generation_requires_preextracted_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "nasa_ims_bearing.zip"
            output_dir = Path(tmp) / "interim"
            raw_dir.write_text("placeholder", encoding="utf-8")
            adapter = get_dataset_adapter("nasa_ims_bearing")

            with self.assertRaisesRegex(ValueError, "preextracted directory"):
                adapter.build_manifest(raw_dir, output_dir)

    def test_nasa_manifest_preserves_temporal_failure_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "nasa_ims_bearing" / "2nd_test"
            raw_dir.mkdir(parents=True)
            for minute in [32, 42, 52]:
                (raw_dir / f"2004.02.12.10.{minute}.39").write_text(
                    "0.1\t0.2\t0.3\t0.4\n0.2\t0.3\t0.4\t0.5\n",
                    encoding="utf-8",
                )
            result = get_dataset_adapter("nasa_ims_bearing").build_manifest(
                raw_dir.parent,
                Path(tmp) / "interim",
            )

            rows = _read_manifest_rows(Path(result.manifest_path))
            metadata = [_metadata(row) for row in rows]

        self.assertEqual([row["timestamp_start"] for row in rows], [
            "2004-02-12T10:32:39",
            "2004-02-12T10:42:39",
            "2004-02-12T10:52:39",
        ])
        self.assertTrue(all(item["official_window_labels"] is False for item in metadata))
        self.assertEqual({row["data_provenance"] for row in rows}, {"unknown"})
        self.assertEqual({item["data_provenance"] for item in metadata}, {"unknown"})
        self.assertEqual({item["label_source"] for item in metadata}, {"none"})
        self.assertEqual({item["label_granularity"] for item in metadata}, {"event"})
        self.assertEqual(
            {item["supervision_profile"] for item in metadata},
            {"run_to_failure_degradation"},
        )
        self.assertEqual(
            {item["failure_event_time"] for item in metadata},
            {"2004-02-12T10:52:40.024000"},
        )
        self.assertEqual({item["failure_mode"] for item in metadata}, {"bearing_1_outer_race"})
        self.assertEqual(
            {item["end_of_life_policy"] for item in metadata},
            {"last_snapshot_as_failure_event"},
        )
        self.assertEqual(
            [item["temporal_order_index"] for item in metadata],
            [0, 1, 2],
        )

    def test_generic_tabular_adapter_reads_header_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "signals.csv"
            csv_path.write_text("ax,ay,temp\n1.0,2.0,30.0\n", encoding="utf-8")

            descriptor = describe_dataset(csv_path, adapter_id="generic_tabular_signal")

        self.assertEqual(descriptor.dataset_id, "generic_tabular_signal")
        self.assertEqual(descriptor.channel_names, ["ax", "ay", "temp"])
        self.assertEqual(descriptor.label_availability, "none")
        self.assertEqual(descriptor.supervision_profile, "unlabeled_diagnostic")
        self.assertEqual(descriptor.label_granularity, "none")
        self.assertEqual(descriptor.label_source, "none")

    def test_infer_generic_tabular_adapter_from_plain_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "signals.csv"
            csv_path.write_text("ax,ay,temp\n1.0,2.0,30.0\n", encoding="utf-8")

            adapter = infer_dataset_adapter(csv_path)

        self.assertEqual(adapter.info.adapter_id, "generic_tabular_signal")

    def test_missing_path_cannot_be_inferred(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"

            with self.assertRaisesRegex(ValueError, "no dataset adapter supports path"):
                infer_dataset_adapter(missing)


def _read_manifest_rows(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _metadata(row: dict[str, str]) -> dict[str, object]:
    import json

    return json.loads(row["metadata_json"])


if __name__ == "__main__":
    unittest.main()
