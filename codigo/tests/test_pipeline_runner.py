import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codigo.app.graph.state import validate_state
from codigo.app.schemas.executor_results import ManifestResult
from codigo.app.schemas.pipeline_run import PipelineRunRequest
from codigo.app.services.dataset_adapters import describe_dataset
from codigo.app.services.pipeline_runner import (
    _agents_for_plan,
    _initial_state_with_execution_evidence,
    build_executors_from_plan,
    build_initial_state_from_plan,
    dataset_pipeline_paths,
    plan_dataset_pipeline_run,
)


class PipelineRunnerPlanningTests(unittest.TestCase):
    def test_cwru_full_run_plan_allows_supervised_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp)
            (raw_dir / "97.mat").touch()
            request = PipelineRunRequest(
                run_id="cwru-plan-test",
                dataset_id="cwru_bearing",
                raw_path=raw_dir.as_posix(),
                use_memory=True,
            )

            plan = plan_dataset_pipeline_run(request)

        self.assertEqual(plan.adapter_info.adapter_id, "cwru_bearing")
        self.assertTrue(plan.can_execute_requested_stages)
        self.assertEqual(plan.policy.status_for("modeling"), "allowed")
        self.assertEqual(plan.descriptor.data_provenance, "official")
        self.assertIn("memory", plan.effective_stages)
        self.assertTrue(plan.paths.interim_dir.endswith("cwru_bearing/cwru-plan-test"))

    def test_nasa_real_full_plan_blocks_supervised_modeling(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = _nasa_raw_dir(Path(tmp))
            request = PipelineRunRequest(
                run_id="nasa-plan-test",
                dataset_id="nasa_ims_bearing",
                raw_path=raw_dir.as_posix(),
                adapter_id="nasa_ims_bearing",
            )

            plan = plan_dataset_pipeline_run(request)

        self.assertFalse(plan.can_execute_requested_stages)
        self.assertEqual(plan.policy.status_for("modeling"), "blocked")
        self.assertEqual(plan.policy.status_for("evaluation"), "blocked")
        self.assertTrue(any("modeling" in reason for reason in plan.blocking_reasons))

    def test_nasa_diagnostic_plan_stops_before_blocked_supervised_stages(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = _nasa_raw_dir(Path(tmp))
            request = PipelineRunRequest(
                run_id="nasa-diagnostic-plan-test",
                dataset_id="nasa_ims_bearing",
                raw_path=raw_dir.as_posix(),
                adapter_id="nasa_ims_bearing",
                execution_mode="diagnostic",
            )

            plan = plan_dataset_pipeline_run(request)
            state = validate_state(build_initial_state_from_plan(plan))
            diagnostic_agents = _agents_for_plan(plan, None)
            assert diagnostic_agents is not None
            terminal_decision = diagnostic_agents.supervisor(
                state.model_copy(update={"current_stage": "modeling"})
            )

        self.assertTrue(plan.can_execute_requested_stages)
        self.assertEqual(
            plan.effective_stages,
            ["manifest", "profiling", "cleaning", "structuring"],
        )
        self.assertEqual(state.project_context.dataset, "nasa_ims_bearing")
        self.assertEqual(state.project_context.label_mode, "degradation")
        self.assertEqual(
            state.project_context.supervision_profile,
            "run_to_failure_degradation",
        )
        self.assertEqual(state.project_context.label_granularity, "event")
        self.assertEqual(state.project_context.label_source, "none")
        self.assertEqual(state.project_context.data_provenance, "unknown")
        self.assertEqual(state.project_context.main_channel, "channel_1")
        self.assertEqual(terminal_decision.next_stage, "completed")
        self.assertIsNotNone(terminal_decision.generation_trace)
        assert terminal_decision.generation_trace is not None
        self.assertEqual(
            terminal_decision.generation_trace.origin,
            "protocol_restricted",
        )
        self.assertEqual(
            terminal_decision.generation_trace.attempt_id,
            f"{terminal_decision.decision_id}:attempt:001",
        )

    def test_nasa_synthetic_labels_allow_full_supervised_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = _nasa_raw_dir(Path(tmp))
            request = PipelineRunRequest(
                run_id="nasa-synthetic-plan-test",
                dataset_id="nasa_ims_bearing",
                raw_path=raw_dir.as_posix(),
                adapter_id="nasa_ims_bearing",
                allow_synthetic_labels=True,
            )

            plan = plan_dataset_pipeline_run(request)
            state = validate_state(build_initial_state_from_plan(plan))

        self.assertTrue(plan.can_execute_requested_stages)
        self.assertEqual(plan.policy.status_for("modeling"), "allowed")
        self.assertEqual(plan.policy.status_for("evaluation"), "allowed")
        self.assertEqual(
            state.project_context.supervision_profile,
            "run_to_failure_degradation",
        )
        self.assertEqual(state.project_context.label_granularity, "file")
        self.assertEqual(state.project_context.label_source, "synthetic")
        self.assertEqual(state.project_context.data_provenance, "unknown")
        self.assertTrue(any("sinteticas" in note for note in plan.policy.notes))

    def test_nasa_temporal_policy_allows_full_supervised_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = _nasa_raw_dir(Path(tmp), n_files=3)
            request = PipelineRunRequest(
                run_id="nasa-temporal-policy-plan-test",
                dataset_id="nasa_ims_bearing",
                raw_path=raw_dir.as_posix(),
                adapter_id="nasa_ims_bearing",
                dataset_policy_id="nasa_ims_temporal_v1",
            )

            plan = plan_dataset_pipeline_run(request)
            state = validate_state(build_initial_state_from_plan(plan))

        self.assertTrue(plan.can_execute_requested_stages)
        self.assertEqual(plan.policy.status_for("modeling"), "allowed")
        self.assertEqual(plan.policy.status_for("evaluation"), "allowed")
        self.assertEqual(state.project_context.label_mode, "binary_anomaly")
        self.assertEqual(
            state.project_context.supervision_profile,
            "run_to_failure_degradation",
        )
        self.assertEqual(state.project_context.label_granularity, "proxy_temporal")
        self.assertEqual(state.project_context.label_source, "temporal_proxy")
        self.assertIn("nasa_ims_temporal_v1", state.project_context.notes or "")
        self.assertTrue(any("proxy" in note for note in plan.policy.notes))

    def test_nasa_synthetic_spec_provenance_survives_temporal_proxy_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = _nasa_raw_dir(Path(tmp), n_files=3)
            spec_path = raw_dir / "synthetic_dataset_spec.json"
            spec_path.write_text(
                json.dumps(
                    {
                        "dataset": "nasa_ims_bearing",
                        "synthetic": True,
                        "seed": 42,
                    }
                ),
                encoding="utf-8",
            )
            request = PipelineRunRequest(
                run_id="nasa-synthetic-provenance-test",
                dataset_id="nasa_ims_bearing",
                raw_path=raw_dir.as_posix(),
                adapter_id="nasa_ims_bearing",
                dataset_policy_id="nasa_ims_temporal_v1",
                allow_synthetic_labels=False,
            )

            plan = plan_dataset_pipeline_run(request)
            state = validate_state(build_initial_state_from_plan(plan))

        self.assertEqual(plan.descriptor.data_provenance, "synthetic")
        self.assertEqual(state.project_context.data_provenance, "synthetic")
        self.assertEqual(state.project_context.label_source, "temporal_proxy")
        self.assertEqual(
            state.project_context.provenance_detection_method,
            "synthetic_dataset_spec",
        )
        self.assertEqual(
            state.project_context.provenance_evidence_path,
            spec_path.as_posix(),
        )
        self.assertIn("no mediciones oficiales", state.project_context.notes or "")

    def test_nasa_temporal_policy_is_applied_to_manifest_executor(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = _nasa_raw_dir(Path(tmp), n_files=3)
            request = PipelineRunRequest(
                run_id="nasa-temporal-policy-manifest-test",
                dataset_id="nasa_ims_bearing",
                raw_path=raw_dir.as_posix(),
                adapter_id="nasa_ims_bearing",
                dataset_policy_id="nasa_ims_temporal_v1",
            )
            plan = plan_dataset_pipeline_run(request)
            executors = build_executors_from_plan(plan)

            result = executors.manifest(raw_dir.as_posix())

        self.assertEqual(result.status, "success")
        self.assertTrue(result.manifest_path.endswith("manifest_temporal_policy_v1.csv"))
        self.assertEqual(result.label_counts, {"normal": 2, "degradation": 1})
        self.assertEqual(
            result.state_updates["dataset_policy_id"],
            "nasa_ims_temporal_v1",
        )

    def test_nasa_run_to_failure_v2_requires_official_provenance(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = _nasa_raw_dir(Path(tmp), n_files=3)
            request = PipelineRunRequest(
                run_id="nasa-v2-unverified-test",
                dataset_id="nasa_ims_bearing",
                raw_path=raw_dir.as_posix(),
                adapter_id="nasa_ims_bearing",
                dataset_policy_id="nasa_ims_run_to_failure_v2",
            )

            with self.assertRaisesRegex(
                ValueError,
                "requires official data provenance; received unknown",
            ):
                plan_dataset_pipeline_run(request)

    def test_nasa_run_to_failure_v2_builds_online_blind_official_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = _nasa_raw_dir(Path(tmp), n_files=3)
            descriptor = _official_nasa_descriptor(raw_dir)
            request = PipelineRunRequest(
                run_id="nasa-v2-official-plan-test",
                dataset_id="nasa_ims_bearing",
                raw_path=raw_dir.as_posix(),
                adapter_id="nasa_ims_bearing",
                dataset_policy_id="nasa_ims_run_to_failure_v2",
            )

            with patch(
                "codigo.app.services.pipeline_runner.describe_dataset",
                return_value=descriptor,
            ):
                plan = plan_dataset_pipeline_run(request)
            state = validate_state(build_initial_state_from_plan(plan))

        self.assertTrue(plan.can_execute_requested_stages)
        self.assertEqual(plan.policy.status_for("modeling"), "allowed")
        self.assertEqual(plan.policy.status_for("evaluation"), "allowed")
        self.assertEqual(state.project_context.objective, "run_to_failure_degradation")
        self.assertEqual(state.project_context.label_mode, "degradation")
        self.assertEqual(state.project_context.label_granularity, "event")
        self.assertEqual(state.project_context.label_source, "none")
        self.assertEqual(state.project_context.data_provenance, "official")
        self.assertIn("online-blind", state.project_context.notes or "")
        self.assertIn("held out", state.project_context.notes or "")
        self.assertIn("20 %", plan.policy.notes[0])

    def test_nasa_run_to_failure_v2_uses_canonical_manifest_executor(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = _nasa_raw_dir(Path(tmp), n_files=3)
            descriptor = _official_nasa_descriptor(raw_dir)
            request = PipelineRunRequest(
                run_id="nasa-v2-manifest-test",
                dataset_id="nasa_ims_bearing",
                raw_path=raw_dir.as_posix(),
                adapter_id="nasa_ims_bearing",
                dataset_policy_id="nasa_ims_run_to_failure_v2",
            )
            with patch(
                "codigo.app.services.pipeline_runner.describe_dataset",
                return_value=descriptor,
            ):
                plan = plan_dataset_pipeline_run(request)
            executors = build_executors_from_plan(plan)
            generated = ManifestResult(
                executor_name="dataset_manifest",
                status="success",
                message="fixture manifest generated",
                manifest_path="fixture/manifest.csv",
                n_rows=3,
                label_counts={"unknown": 3},
                state_updates={"data_provenance": "official"},
            )
            applied = generated.model_copy(
                update={
                    "manifest_path": "fixture/manifest_run_to_failure_v2.csv",
                    "state_updates": {
                        "data_provenance": "official",
                        "dataset_policy_id": "nasa_ims_run_to_failure_v2",
                    },
                }
            )

            with (
                patch(
                    "codigo.app.services.pipeline_runner.generate_dataset_manifest",
                    return_value=generated,
                ),
                patch(
                    "codigo.app.services.pipeline_runner."
                    "apply_nasa_ims_run_to_failure_policy_v2_to_result",
                    return_value=applied,
                ) as apply_v2,
            ):
                result = executors.manifest(raw_dir.as_posix())

        apply_v2.assert_called_once_with(generated, plan.paths.interim_dir)
        self.assertEqual(
            result.state_updates["dataset_policy_id"],
            "nasa_ims_run_to_failure_v2",
        )

    def test_unknown_dataset_policy_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = _nasa_raw_dir(Path(tmp))
            request = PipelineRunRequest(
                run_id="nasa-unknown-policy-test",
                dataset_id="nasa_ims_bearing",
                raw_path=raw_dir.as_posix(),
                adapter_id="nasa_ims_bearing",
                dataset_policy_id="unknown_policy",
            )

            with self.assertRaisesRegex(ValueError, "unsupported dataset_policy_id"):
                plan_dataset_pipeline_run(request)

    def test_adapter_dataset_mismatch_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = _nasa_raw_dir(Path(tmp))
            request = PipelineRunRequest(
                run_id="mismatch-plan-test",
                dataset_id="cwru_bearing",
                raw_path=raw_dir.as_posix(),
                adapter_id="nasa_ims_bearing",
            )

            with self.assertRaisesRegex(ValueError, "adapter/dataset mismatch"):
                plan_dataset_pipeline_run(request)

    def test_explicit_adapter_must_support_raw_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "not_cwru"
            raw_dir.mkdir()
            (raw_dir / "README.txt").write_text("metadata only\n", encoding="utf-8")
            request = PipelineRunRequest(
                run_id="unsupported-adapter-path",
                dataset_id="cwru_bearing",
                raw_path=raw_dir.as_posix(),
                adapter_id="cwru_bearing",
            )

            with self.assertRaisesRegex(ValueError, "does not support path"):
                plan_dataset_pipeline_run(request)

    def test_run_id_cannot_be_path(self):
        with self.assertRaisesRegex(ValueError, "plain identifier"):
            PipelineRunRequest(
                run_id="bad/run",
                dataset_id="cwru_bearing",
                raw_path="codigo/data/raw/cwru_bearing/mat",
            )

    def test_dataset_paths_are_derived_from_dataset_and_run(self):
        request = PipelineRunRequest(
            run_id="path-plan-test",
            dataset_id="cwru_bearing",
            raw_path="codigo/data/raw/cwru_bearing/mat",
        )

        paths = dataset_pipeline_paths(request)

        self.assertEqual(
            paths.model_dir,
            "codigo/models/cwru_bearing/path-plan-test",
        )
        self.assertEqual(paths.memory_output_root, "codigo/reports")

    def test_initial_state_includes_request_and_plan_evidence_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw_dir = Path(tmp) / "raw"
            raw_dir.mkdir()
            (raw_dir / "97.mat").touch()
            request = PipelineRunRequest(
                run_id="cwru-plan-evidence-test",
                dataset_id="cwru_bearing",
                raw_path=raw_dir.as_posix(),
            )
            plan = plan_dataset_pipeline_run(request)
            plan = plan.model_copy(
                update={
                    "paths": plan.paths.model_copy(
                        update={"memory_output_root": (Path(tmp) / "reports").as_posix()}
                    )
                }
            )

            state = validate_state(_initial_state_with_execution_evidence(plan, None))

            evidence_artifacts = {
                artifact.name: artifact for artifact in state.artifacts
                if artifact.artifact_type == "config"
            }
            request_payload = _read_json(
                Path(evidence_artifacts["pipeline_request"].path)
            )
            plan_payload = _read_json(Path(evidence_artifacts["pipeline_plan"].path))

        self.assertEqual(request_payload["run_id"], "cwru-plan-evidence-test")
        self.assertEqual(plan_payload["request"]["dataset_id"], "cwru_bearing")
        self.assertEqual(plan_payload["descriptor"]["data_provenance"], "official")
        self.assertEqual(
            evidence_artifacts["pipeline_plan"].metadata["data_provenance"],
            "official",
        )
        self.assertTrue(plan_payload["can_execute_requested_stages"])


def _nasa_raw_dir(base: Path, *, n_files: int = 1) -> Path:
    raw_dir = base / "nasa_ims_bearing" / "2nd_test"
    raw_dir.mkdir(parents=True)
    for index in range(n_files):
        minute = 32 + index * 10
        (raw_dir / f"2004.02.12.10.{minute:02d}.39").write_text(
            "0.1\t0.2\t0.3\t0.4\n0.2\t0.3\t0.4\t0.5\n",
            encoding="utf-8",
        )
    return raw_dir.parent


def _official_nasa_descriptor(raw_dir: Path):
    descriptor = describe_dataset(raw_dir, adapter_id="nasa_ims_bearing")
    return descriptor.model_copy(
        update={
            "data_provenance": "official",
            "provenance_detection_method": "official_dataset_provenance",
            "provenance_evidence_path": "fixture/official_dataset_provenance.json",
            "provenance_evidence_sha256": "a" * 64,
        }
    )


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
