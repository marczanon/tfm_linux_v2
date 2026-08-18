import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from codigo.app.schemas.dataset import CommonManifestRecord
from codigo.app.services.common_manifest import (
    read_common_manifest,
    write_common_manifest,
)


class CommonManifestServiceTests(unittest.TestCase):
    def test_common_manifest_roundtrip_preserves_temporal_metadata(self):
        record = CommonManifestRecord(
            record_id="run_001",
            dataset="nasa_ims_bearing",
            source_path="codigo/data/raw/nasa_ims_bearing/2nd_test/2004.02.12.10.32.39",
            source_format="txt",
            data_provenance="synthetic",
            label="unknown",
            label_detail="bearing_1_outer_race",
            condition_id="test_to_failure",
            asset_id="bearing_test_rig",
            run_id="set_2",
            timestamp_start=datetime(2004, 2, 12, 10, 32, 39),
            timestamp_end=datetime(2004, 2, 12, 10, 32, 40, 24000),
            sampling_rate_hz=20000.0,
            target_sample_rate_hz=20000.0,
            channel_names=["channel_1", "channel_2"],
            primary_channel="channel_1",
            n_channels=2,
            metadata_json={
                "failure_event_time": "2004-02-12T10:52:40.024000",
                "failure_mode": "bearing_1_outer_race",
                "end_of_life_policy": "last_snapshot_as_failure_event",
                "official_window_labels": False,
            },
            notes=None,
        )
        with tempfile.TemporaryDirectory() as tmp:
            manifest_path = Path(tmp) / "manifest.csv"
            write_common_manifest(manifest_path, [record])

            records = read_common_manifest(manifest_path)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].record_id, "run_001")
        self.assertEqual(records[0].timestamp_start, record.timestamp_start)
        self.assertEqual(records[0].data_provenance, "synthetic")
        self.assertEqual(
            records[0].metadata_json["failure_event_time"],
            "2004-02-12T10:52:40.024000",
        )
        self.assertFalse(records[0].metadata_json["official_window_labels"])


if __name__ == "__main__":
    unittest.main()
