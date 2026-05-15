import json
import unittest

from pydantic import ValidationError

from codigo.app.schemas.executor_results import ExecutorResult, ManifestResult
from codigo.app.schemas.state import ArtifactRef, PipelineError


class ExecutorResultSchemaTests(unittest.TestCase):
    def test_successful_manifest_result_is_serializable(self):
        result = ManifestResult(
            executor_name="dataset_manifest",
            status="success",
            message="Manifest generated.",
            artifacts=[
                ArtifactRef(
                    name="cwru_manifest",
                    artifact_type="manifest",
                    path="codigo/data/interim/cwru_bearing/manifest.csv",
                    producer="manifest_executor",
                    description=None,
                    metadata={"n_rows": 64},
                )
            ],
            errors=[],
            state_updates={
                "manifest_path": "codigo/data/interim/cwru_bearing/manifest.csv"
            },
            finished_at=None,
            manifest_path="codigo/data/interim/cwru_bearing/manifest.csv",
            n_rows=64,
            label_counts={"normal": 4, "fault": 60},
        )

        payload = result.model_dump(mode="json")

        self.assertEqual(payload["stage"], "dataset_manifest")
        json.dumps(payload)

    def test_failed_result_requires_structured_error(self):
        with self.assertRaises(ValidationError):
            ExecutorResult(
                executor_name="profiler",
                stage="profiling",
                status="failed",
                message="Profile failed.",
                errors=[],
            )

    def test_success_result_rejects_errors(self):
        with self.assertRaises(ValidationError):
            ExecutorResult(
                executor_name="profiler",
                stage="profiling",
                status="success",
                message="Profile generated.",
                errors=[
                    PipelineError(
                        stage="profiling",
                        node="profiler_executor",
                        message="Should not be here.",
                        recoverable=True,
                    )
                ],
            )

    def test_executor_result_rejects_payload_field(self):
        with self.assertRaises(ValidationError):
            ExecutorResult(
                executor_name="profiler",
                stage="profiling",
                status="success",
                message="Profile generated.",
                payload=[1, 2, 3],
            )

    def test_manifest_success_requires_positive_rows(self):
        with self.assertRaises(ValidationError):
            ManifestResult(
                executor_name="dataset_manifest",
                status="success",
                message="Manifest generated.",
                errors=[],
                manifest_path="codigo/data/interim/cwru_bearing/manifest.csv",
                n_rows=0,
                label_counts={},
            )


if __name__ == "__main__":
    unittest.main()
