import tempfile
import unittest
from pathlib import Path

from codigo.app.graph.state import validate_state
from codigo.app.schemas.pipeline_run import PipelineRunRequest
from codigo.app.services.pipeline_runner import (
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

        self.assertTrue(plan.can_execute_requested_stages)
        self.assertEqual(
            plan.effective_stages,
            ["manifest", "profiling", "cleaning", "structuring"],
        )
        self.assertEqual(state.project_context.dataset, "nasa_ims_bearing")
        self.assertEqual(state.project_context.label_mode, "degradation")
        self.assertEqual(state.project_context.main_channel, "channel_1")

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

        self.assertTrue(plan.can_execute_requested_stages)
        self.assertEqual(plan.policy.status_for("modeling"), "allowed")
        self.assertEqual(plan.policy.status_for("evaluation"), "allowed")
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
        self.assertIn("nasa_ims_temporal_v1", state.project_context.notes or "")
        self.assertTrue(any("proxy" in note for note in plan.policy.notes))

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


if __name__ == "__main__":
    unittest.main()
