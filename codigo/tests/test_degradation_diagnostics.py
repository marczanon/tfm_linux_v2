import csv
import json
import tempfile
import unittest
from pathlib import Path

from codigo.app.services.degradation_diagnostics import (
    generate_degradation_diagnostics,
)


class DegradationDiagnosticsTests(unittest.TestCase):
    def test_generate_degradation_diagnostics_writes_json_and_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            features_path = base / "features.csv"
            _write_features(features_path)

            summary = generate_degradation_diagnostics(
                features_path,
                base / "diagnostics",
            )
            saved = json.loads(
                Path(summary["diagnostics_path"]).read_text(encoding="utf-8")
            )
            report = Path(summary["report_path"]).read_text(encoding="utf-8")

        self.assertEqual(summary["metric_type"], "unsupervised_degradation_diagnostics")
        self.assertEqual(summary["n_files"], 3)
        self.assertEqual(summary["trend_status"], "increasing_degradation_signal")
        self.assertGreater(summary["late_early_ratio"], 1.0)
        self.assertEqual(saved["n_windows"], 6)
        self.assertIn("No se calcula recall/F1", report)

    def test_degradation_diagnostics_requires_supported_features(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            features_path = base / "features.csv"
            features_path.write_text(
                "file_id,window_index,custom\nf0,0,1.0\n",
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "no supported degradation"):
                generate_degradation_diagnostics(features_path, base / "out")


def _write_features(path: Path) -> None:
    rows = [
        {"file_id": "t0", "window_index": 0, "rms": 1.0, "energy": 10.0},
        {"file_id": "t0", "window_index": 1, "rms": 1.1, "energy": 11.0},
        {"file_id": "t1", "window_index": 0, "rms": 2.0, "energy": 20.0},
        {"file_id": "t1", "window_index": 1, "rms": 2.1, "energy": 21.0},
        {"file_id": "t2", "window_index": 0, "rms": 4.0, "energy": 40.0},
        {"file_id": "t2", "window_index": 1, "rms": 4.2, "energy": 42.0},
    ]
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=["file_id", "window_index", "rms", "energy"])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    unittest.main()
