import unittest

from pydantic import ValidationError

from codigo.app.schemas.dataset import (
    CommonManifestRecord,
    DatasetDescriptor,
    DatasetManifest,
    DatasetManifestRow,
)


def make_normal_row(file_id: str = "97") -> DatasetManifestRow:
    return DatasetManifestRow(
        file_id=file_id,
        dataset="cwru_bearing",
        source_path=f"codigo/data/raw/cwru_bearing/mat/{file_id}.mat",
        label="normal",
        fault_type=None,
        fault_diameter_inch=None,
        load_hp=0,
        rpm=1797,
        sensor_channel="DE_time",
        source_sample_rate_hz=12000,
        target_sample_rate_hz=12000,
        source_format="mat",
        notes=None,
    )


class DatasetSchemaTests(unittest.TestCase):
    def test_valid_normal_manifest_row_uses_explicit_null_fault_fields(self):
        row = make_normal_row()

        self.assertEqual(row.label, "normal")
        self.assertIsNone(row.fault_type)
        self.assertIsNone(row.fault_diameter_inch)

    def test_missing_nullable_fault_type_is_rejected(self):
        payload = make_normal_row().model_dump()
        payload.pop("fault_type")

        with self.assertRaises(ValidationError):
            DatasetManifestRow.model_validate(payload)

    def test_normal_row_rejects_fault_metadata(self):
        payload = make_normal_row().model_dump()
        payload["fault_type"] = "inner_race"
        payload["fault_diameter_inch"] = 0.007

        with self.assertRaises(ValidationError):
            DatasetManifestRow.model_validate(payload)

    def test_fault_row_requires_fault_type_and_diameter(self):
        payload = make_normal_row("105").model_dump()
        payload["label"] = "fault"
        payload["fault_type"] = None
        payload["fault_diameter_inch"] = None

        with self.assertRaises(ValidationError):
            DatasetManifestRow.model_validate(payload)

    def test_manifest_rejects_duplicate_file_ids(self):
        row = make_normal_row("97")

        with self.assertRaises(ValidationError):
            DatasetManifest(dataset="cwru_bearing", rows=[row, row])

    def test_manifest_computes_label_counts(self):
        normal = make_normal_row("97")
        fault = DatasetManifestRow(
            file_id="105",
            dataset="cwru_bearing",
            source_path="codigo/data/raw/cwru_bearing/mat/105.mat",
            label="fault",
            fault_type="inner_race",
            fault_diameter_inch=0.007,
            load_hp=0,
            rpm=1797,
            sensor_channel="DE_time",
            source_sample_rate_hz=12000,
            target_sample_rate_hz=12000,
            source_format="mat",
            notes=None,
        )

        manifest = DatasetManifest(dataset="cwru_bearing", rows=[normal, fault])

        self.assertEqual(manifest.label_counts, {"normal": 1, "fault": 1})

    def test_dataset_descriptor_accepts_cwru_and_nasa_shapes(self):
        cwru = DatasetDescriptor(
            dataset_id="cwru_bearing",
            dataset_name="CWRU Bearing Dataset",
            domain="rotating_machinery",
            asset_type="bearing",
            raw_path="codigo/data/raw/cwru_bearing/mat",
            source_format="directory",
            adapter_id="cwru_bearing",
            label_availability="file_level",
            task_type="binary_anomaly",
            sampling_rate_hz=None,
            channel_names=["DE_time", "FE_time", "BA_time", "RPM"],
            has_multiple_conditions=True,
            has_run_to_failure=False,
            metadata={"target_sample_rate_hz": 12000},
            notes=[],
        )
        nasa = DatasetDescriptor(
            dataset_id="nasa_ims_bearing",
            dataset_name="NASA IMS Bearing Dataset",
            domain="rotating_machinery",
            asset_type="bearing",
            raw_path="codigo/data/raw/nasa_ims_bearing",
            source_format="directory",
            adapter_id="nasa_ims_bearing",
            label_availability="partial",
            task_type="run_to_failure",
            sampling_rate_hz=None,
            channel_names=["channel_1", "channel_2"],
            has_multiple_conditions=True,
            has_run_to_failure=True,
            metadata={},
            notes=["synthetic descriptor"],
        )

        self.assertEqual(cwru.adapter_id, "cwru_bearing")
        self.assertTrue(nasa.has_run_to_failure)

    def test_dataset_descriptor_rejects_invalid_ids_and_duplicate_channels(self):
        payload = {
            "dataset_id": "NASA IMS",
            "dataset_name": "NASA IMS Bearing Dataset",
            "domain": "rotating_machinery",
            "asset_type": "bearing",
            "raw_path": "codigo/data/raw/nasa_ims_bearing",
            "source_format": "directory",
            "adapter_id": "nasa_ims_bearing",
            "label_availability": "partial",
            "task_type": "run_to_failure",
            "sampling_rate_hz": None,
            "channel_names": ["x", "x"],
            "has_multiple_conditions": True,
            "has_run_to_failure": True,
            "metadata": {},
            "notes": [],
        }

        with self.assertRaises(ValidationError):
            DatasetDescriptor.model_validate(payload)

        payload["dataset_id"] = "nasa_ims_bearing"
        with self.assertRaises(ValidationError):
            DatasetDescriptor.model_validate(payload)

    def test_common_manifest_record_validates_channels_and_metadata(self):
        record = CommonManifestRecord(
            record_id="test_001",
            dataset="nasa_ims_bearing",
            source_path="codigo/data/raw/nasa_ims_bearing/1st_test/2003.txt",
            source_format="txt",
            label="unknown",
            label_detail=None,
            condition_id="1st_test",
            asset_id="bearing_1",
            run_id="1st_test",
            timestamp_start=None,
            timestamp_end=None,
            sampling_rate_hz=20000.0,
            target_sample_rate_hz=12000.0,
            channel_names=["channel_1", "channel_2"],
            primary_channel="channel_1",
            n_channels=2,
            metadata_json={"measurement_index": 1},
            notes=None,
        )

        self.assertEqual(record.primary_channel, "channel_1")

    def test_common_manifest_record_rejects_invalid_channel_payloads(self):
        payload = {
            "record_id": "test_001",
            "dataset": "nasa_ims_bearing",
            "source_path": "codigo/data/raw/nasa_ims_bearing/1st_test/2003.txt",
            "source_format": "txt",
            "label": "unknown",
            "label_detail": None,
            "condition_id": "1st_test",
            "asset_id": "bearing_1",
            "run_id": "1st_test",
            "timestamp_start": None,
            "timestamp_end": None,
            "sampling_rate_hz": 20000.0,
            "target_sample_rate_hz": 12000.0,
            "channel_names": ["channel_1", "channel_2"],
            "primary_channel": "missing",
            "n_channels": 2,
            "metadata_json": {"measurement_index": 1},
            "notes": None,
        }

        with self.assertRaises(ValidationError):
            CommonManifestRecord.model_validate(payload)

        payload["primary_channel"] = "channel_1"
        payload["n_channels"] = 3
        with self.assertRaises(ValidationError):
            CommonManifestRecord.model_validate(payload)

        payload["n_channels"] = 2
        payload["metadata_json"] = "not-json"
        with self.assertRaises(ValidationError):
            CommonManifestRecord.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
