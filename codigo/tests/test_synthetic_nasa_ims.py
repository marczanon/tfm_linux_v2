import csv
import json
import tempfile
import unittest
from pathlib import Path

from codigo.app.services.synthetic_nasa_ims import (
    generate_synthetic_nasa_ims_binary_manifest,
    prepare_synthetic_nasa_ims_binary_dataset,
)


class SyntheticNasaIMSTests(unittest.TestCase):
    def test_prepare_and_manifest_create_labeled_common_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "raw"
            output_dir = Path(tmp) / "interim"

            spec = prepare_synthetic_nasa_ims_binary_dataset(
                raw_dir,
                seed=7,
                n_normal_files=4,
                n_fault_files=2,
                sample_count=4096,
            )
            result = generate_synthetic_nasa_ims_binary_manifest(
                raw_dir,
                output_dir,
                n_normal_files=4,
                sample_count=4096,
            )
            with open(result.manifest_path, encoding="utf-8") as file:
                rows = list(csv.DictReader(file))
            spec_payload = json.loads(
                Path(spec["spec_path"]).read_text(encoding="utf-8")
            )

        self.assertEqual(result.status, "success")
        self.assertEqual(result.n_rows, 6)
        self.assertEqual(result.label_counts, {"normal": 4, "fault": 2})
        self.assertEqual(len(rows), 6)
        self.assertEqual(rows[0]["dataset"], "nasa_ims_bearing")
        self.assertEqual(rows[0]["label"], "normal")
        self.assertEqual(rows[-1]["label"], "fault")
        self.assertEqual(json.loads(rows[0]["channel_names"])[0], "channel_1")
        self.assertTrue(json.loads(rows[-1]["metadata_json"])["synthetic"])
        self.assertTrue(spec_payload["synthetic"])


if __name__ == "__main__":
    unittest.main()
