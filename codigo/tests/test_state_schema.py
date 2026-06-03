import json
import unittest

from pydantic import ValidationError

from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import (
    ArtifactRef,
    MetricsReport,
    ProjectContext,
    StructuringConfig,
    TFMStateModel,
)


class StateSchemaTests(unittest.TestCase):
    def test_initial_cwru_state_is_valid_and_serializable(self):
        state = create_initial_cwru_state(
            thread_id="cwru-demo-001",
            run_id="2026-05-06-cwru-mvp",
        )

        validated = validate_state(state)

        self.assertEqual(validated.current_stage, "dataset_manifest")
        self.assertEqual(validated.next_node, "manifest_executor")
        self.assertEqual(validated.project_context.dataset, "cwru_bearing")
        self.assertEqual(validated.raw_path, "codigo/data/raw/cwru_bearing/mat")
        json.dumps(state)

    def test_state_rejects_unknown_top_level_fields(self):
        valid_state = create_initial_cwru_state(
            thread_id="cwru-demo-001",
            run_id="2026-05-06-cwru-mvp",
        )
        valid_state["unexpected_payload"] = "not allowed"

        with self.assertRaises(ValidationError):
            TFMStateModel.model_validate(valid_state)

    def test_artifact_reference_keeps_only_paths_and_metadata(self):
        artifact = ArtifactRef(
            name="cwru_manifest",
            artifact_type="manifest",
            path="codigo/data/interim/cwru_bearing/manifest.csv",
            producer="manifest_executor",
            metadata={"n_files": 64, "dataset": "cwru_bearing"},
        )

        dumped = artifact.model_dump(mode="json")

        self.assertEqual(dumped["artifact_type"], "manifest")
        self.assertIn("path", dumped)
        self.assertNotIn("payload", dumped)

    def test_structuring_config_validates_overlap_range(self):
        with self.assertRaises(ValidationError):
            StructuringConfig(overlap=1.0)

    def test_metrics_validate_unit_interval_values(self):
        with self.assertRaises(ValidationError):
            MetricsReport(recall=1.2)

    def test_project_context_defaults_match_cwru_mvp(self):
        context = ProjectContext()

        self.assertEqual(context.dataset, "cwru_bearing")
        self.assertEqual(context.objective, "binary_anomaly_detection")
        self.assertEqual(context.target_sample_rate_hz, 12000)
        self.assertEqual(context.main_channel, "DE_time")
        self.assertEqual(context.supervision_profile, "binary_fault_classification")
        self.assertEqual(context.label_granularity, "file")
        self.assertEqual(context.label_source, "official")


if __name__ == "__main__":
    unittest.main()
