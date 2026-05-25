import csv
import json
import tempfile
import unittest
from pathlib import Path

from codigo.app.executors.dataset_manifest import (
    build_cwru_manifest,
    generate_cwru_manifest,
    generate_dataset_manifest,
)
from codigo.app.services.dataset_adapters import get_dataset_adapter


def touch_mat(raw_dir: Path, *file_ids: str) -> None:
    for file_id in file_ids:
        (raw_dir / f"{file_id}.mat").touch()


def write_nasa_snapshot(path: Path, n_channels: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    values = [f"{index / 10:.1f}" for index in range(1, n_channels + 1)]
    path.write_text("\t".join(values) + "\n", encoding="utf-8")


class DatasetManifestExecutorTests(unittest.TestCase):
    def test_build_manifest_maps_normal_and_fault_metadata(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp)
            touch_mat(raw_dir, "97", "105", "130", "3001")

            manifest = build_cwru_manifest(raw_dir)

        rows = {row.file_id: row for row in manifest.rows}
        self.assertEqual(manifest.label_counts, {"normal": 1, "fault": 3})
        self.assertEqual(rows["97"].source_sample_rate_hz, 48000)
        self.assertEqual(rows["105"].fault_type, "inner_race")
        self.assertEqual(rows["130"].notes, "outer_position=6")
        self.assertEqual(rows["3001"].fault_diameter_inch, 0.028)

    def test_generate_manifest_writes_csv_and_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "raw"
            raw_dir.mkdir()
            output = base / "interim" / "manifest.csv"
            touch_mat(raw_dir, "97", "105")

            result = generate_cwru_manifest(raw_dir, output)

            with output.open(encoding="utf-8") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.n_rows, 2)
        self.assertEqual(result.state_updates["manifest_path"], str(output))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["file_id"], "97")
        self.assertEqual(rows[0]["fault_type"], "")

    def test_unknown_file_id_returns_failed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp)
            touch_mat(raw_dir, "9999")

            result = generate_cwru_manifest(raw_dir, raw_dir / "manifest.csv")

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.n_rows, 0)
        self.assertIn("unknown CWRU file_id", result.errors[0].message)

    def test_empty_raw_dir_returns_failed_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp)

            result = generate_cwru_manifest(raw_dir, raw_dir / "manifest.csv")

        self.assertEqual(result.status, "failed")
        self.assertIn("no .mat files found", result.errors[0].message)

    def test_cwru_adapter_build_manifest_delegates_to_existing_executor(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "raw"
            output_dir = base / "interim"
            raw_dir.mkdir()
            touch_mat(raw_dir, "97", "105")
            adapter = get_dataset_adapter("cwru_bearing")

            result = adapter.build_manifest(raw_dir, output_dir)

            with (output_dir / "manifest.csv").open(encoding="utf-8") as file:
                rows = list(csv.DictReader(file))

        self.assertEqual(result.status, "success")
        self.assertEqual(result.manifest_path, str(output_dir / "manifest.csv"))
        self.assertEqual(result.label_counts, {"normal": 1, "fault": 1})
        self.assertEqual([row["file_id"] for row in rows], ["97", "105"])

    def test_generic_manifest_wrapper_matches_cwru_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "raw"
            direct_output = base / "direct" / "manifest.csv"
            adapter_output_dir = base / "adapter"
            raw_dir.mkdir()
            touch_mat(raw_dir, "97", "105", "130")

            direct = generate_cwru_manifest(raw_dir, direct_output)
            wrapped = generate_dataset_manifest(
                raw_dir,
                adapter_output_dir,
            )

            with direct_output.open(encoding="utf-8") as file:
                direct_rows = list(csv.DictReader(file))
            with (adapter_output_dir / "manifest.csv").open(encoding="utf-8") as file:
                wrapped_rows = list(csv.DictReader(file))

        self.assertEqual(direct.status, "success")
        self.assertEqual(wrapped.status, "success")
        self.assertEqual(wrapped.n_rows, direct.n_rows)
        self.assertEqual(wrapped.label_counts, direct.label_counts)
        self.assertEqual(wrapped_rows, direct_rows)

    def test_generic_manifest_wrapper_reports_unsupported_adapter(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "signals"
            raw_dir.mkdir()
            (raw_dir / "sample.csv").write_text("x,y\n1,2\n", encoding="utf-8")

            result = generate_dataset_manifest(
                raw_dir,
                base / "interim",
                adapter_id="generic_tabular_signal",
            )

        self.assertEqual(result.status, "failed")
        self.assertIn("does not support manifest generation", result.errors[0].message)

    def test_nasa_manifest_wrapper_writes_common_manifest_for_preextracted_tree(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "nasa_ims_bearing"
            output_dir = base / "interim"
            write_nasa_snapshot(raw_dir / "1st_test" / "2003.10.22.12.06.24", 8)
            write_nasa_snapshot(raw_dir / "2nd_test" / "2004.02.12.10.32.39", 4)
            write_nasa_snapshot(
                raw_dir / "4th_test" / "txt" / "2004.03.04.09.27.46",
                4,
            )

            result = generate_dataset_manifest(
                raw_dir,
                output_dir,
                adapter_id="nasa_ims_bearing",
            )

            with (output_dir / "manifest.csv").open(encoding="utf-8") as file:
                rows = list(csv.DictReader(file))

        rows_by_run = {row["run_id"]: row for row in rows}
        set_1_channels = json.loads(rows_by_run["set_1"]["channel_names"])
        set_3_metadata = json.loads(
            rows_by_run["set_3_local_variant"]["metadata_json"]
        )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.n_rows, 3)
        self.assertEqual(result.label_counts, {"unknown": 3})
        self.assertEqual(result.state_updates["adapter_id"], "nasa_ims_bearing")
        self.assertEqual(set(rows_by_run), {"set_1", "set_2", "set_3_local_variant"})
        self.assertEqual(rows_by_run["set_1"]["dataset"], "nasa_ims_bearing")
        self.assertEqual(rows_by_run["set_1"]["source_format"], "txt")
        self.assertEqual(rows_by_run["set_1"]["label"], "unknown")
        self.assertEqual(rows_by_run["set_1"]["n_channels"], "8")
        self.assertEqual(
            set_1_channels,
            [f"channel_{index}" for index in range(1, 9)],
        )
        self.assertEqual(
            rows_by_run["set_1"]["timestamp_start"],
            "2003-10-22T12:06:24",
        )
        self.assertEqual(rows_by_run["set_1"]["sampling_rate_hz"], "20000.0")
        self.assertTrue(set_3_metadata["local_variant"])
        self.assertEqual(set_3_metadata["points_per_file"], 20480)

    def test_nasa_manifest_wrapper_rejects_channel_mismatch(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "nasa_ims_bearing"
            write_nasa_snapshot(raw_dir / "1st_test" / "2003.10.22.12.06.24", 4)

            result = generate_dataset_manifest(
                raw_dir,
                base / "interim",
                adapter_id="nasa_ims_bearing",
            )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.n_rows, 0)
        self.assertIn("channel count mismatch", result.errors[0].message)

    def test_nasa_manifest_wrapper_rejects_zip_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_path = base / "4.+Bearings.zip"
            raw_path.write_text("placeholder", encoding="utf-8")

            result = generate_dataset_manifest(
                raw_path,
                base / "interim",
                adapter_id="nasa_ims_bearing",
            )

        self.assertEqual(result.status, "failed")
        self.assertIn("preextracted directory", result.errors[0].message)


if __name__ == "__main__":
    unittest.main()
