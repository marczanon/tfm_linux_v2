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
        self.assertEqual(
            descriptor.channel_names,
            ["channel_1", "channel_2", "channel_3", "channel_4"],
        )
        self.assertTrue(descriptor.has_run_to_failure)
        self.assertEqual(descriptor.metadata["candidate_file_count"], 1)
        self.assertEqual(descriptor.metadata["inferred_n_channels"], 4)
        self.assertFalse(descriptor.metadata["inconsistent_channel_counts"])

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

    def test_generic_tabular_adapter_reads_header_channels(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "signals.csv"
            csv_path.write_text("ax,ay,temp\n1.0,2.0,30.0\n", encoding="utf-8")

            descriptor = describe_dataset(csv_path, adapter_id="generic_tabular_signal")

        self.assertEqual(descriptor.dataset_id, "generic_tabular_signal")
        self.assertEqual(descriptor.channel_names, ["ax", "ay", "temp"])
        self.assertEqual(descriptor.label_availability, "none")

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


if __name__ == "__main__":
    unittest.main()
