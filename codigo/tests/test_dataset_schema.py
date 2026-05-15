import unittest

from pydantic import ValidationError

from codigo.app.schemas.dataset import DatasetManifest, DatasetManifestRow


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


if __name__ == "__main__":
    unittest.main()
