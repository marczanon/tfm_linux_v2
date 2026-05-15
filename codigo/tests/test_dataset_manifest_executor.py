import csv
import tempfile
import unittest
from pathlib import Path

from codigo.app.executors.dataset_manifest import build_cwru_manifest, generate_cwru_manifest


def touch_mat(raw_dir: Path, *file_ids: str) -> None:
    for file_id in file_ids:
        (raw_dir / f"{file_id}.mat").touch()


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


if __name__ == "__main__":
    unittest.main()
