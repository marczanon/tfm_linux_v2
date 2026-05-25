import tempfile
import unittest
from pathlib import Path

from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import ArtifactRef, EvaluationResult, MetricsReport
from codigo.app.services.run_persistence import save_run_snapshot
from codigo.app.services.run_registry import (
    compare_runs,
    get_run,
    get_run_artifacts,
    list_runs,
)


class RunRegistryTests(unittest.TestCase):
    def test_list_runs_filters_by_dataset_stage_and_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            save_run_snapshot(_state("run-a", f1_score=0.80, approved=True), runs_dir)
            save_run_snapshot(_state("run-b", f1_score=0.70, approved=False), runs_dir)

            approved_runs = list_runs(runs_dir, approved=True)
            completed_runs = list_runs(runs_dir, current_stage="completed")
            cwru_runs = list_runs(runs_dir, dataset="cwru_bearing")

        self.assertEqual([run.run_id for run in approved_runs], ["run-a"])
        self.assertEqual({run.run_id for run in completed_runs}, {"run-a", "run-b"})
        self.assertEqual({run.run_id for run in cwru_runs}, {"run-a", "run-b"})

    def test_get_run_and_artifacts_load_snapshot_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            save_run_snapshot(_state("run-artifacts", f1_score=0.88), runs_dir)

            snapshot = get_run("run-artifacts", runs_dir)
            artifacts = get_run_artifacts("run-artifacts", runs_dir)

        self.assertEqual(snapshot.run_id, "run-artifacts")
        self.assertEqual(artifacts[0]["artifact_type"], "metrics")

    def test_compare_runs_summarizes_best_and_worst_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            save_run_snapshot(
                _state(
                    "run-baseline",
                    precision=0.90,
                    recall=0.92,
                    f1_score=0.91,
                    false_positive_rate=0.08,
                ),
                runs_dir,
            )
            save_run_snapshot(
                _state(
                    "run-candidate",
                    precision=0.95,
                    recall=0.94,
                    f1_score=0.945,
                    false_positive_rate=0.04,
                ),
                runs_dir,
            )

            comparison = compare_runs(["run-baseline", "run-candidate"], runs_dir)

        metrics = {metric.metric: metric for metric in comparison.metrics}
        self.assertEqual(comparison.run_ids, ["run-baseline", "run-candidate"])
        self.assertEqual(metrics["f1_score"].best_run_id, "run-candidate")
        self.assertEqual(metrics["precision"].best_value, 0.95)
        self.assertEqual(metrics["false_positive_rate"].best_run_id, "run-candidate")
        self.assertFalse(metrics["false_positive_rate"].higher_is_better)

    def test_compare_runs_requires_at_least_two_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                compare_runs(["run-a"], Path(tmp) / "runs")

    def test_compare_runs_reports_missing_run_ids(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            save_run_snapshot(_state("run-present", f1_score=0.80), runs_dir)

            with self.assertRaises(FileNotFoundError):
                compare_runs(["run-present", "run-missing"], runs_dir)


def _state(
    run_id: str,
    *,
    precision: float = 0.93,
    recall: float = 0.95,
    f1_score: float,
    false_positive_rate: float = 0.04,
    approved: bool = True,
):
    state_dict = create_initial_cwru_state(
        thread_id=f"thread-{run_id}",
        run_id=run_id,
    )
    state_dict["current_stage"] = "completed"
    state_dict["next_node"] = None
    state_dict["report_path"] = f"codigo/reports/cwru_bearing/{run_id}.md"
    state_dict["metrics"] = MetricsReport(
        metrics_path=f"codigo/reports/cwru_bearing/{run_id}/metrics.json",
        precision=precision,
        recall=recall,
        f1_score=f1_score,
        false_positive_rate=false_positive_rate,
    ).model_dump(mode="json")
    state_dict["evaluation"] = EvaluationResult(
        approved=approved,
        summary="Ejecucion aprobada." if approved else "Ejecucion rechazada.",
        next_action="continue" if approved else "retry_with_new_config",
        limitations=[],
    ).model_dump(mode="json")
    state_dict["artifacts"] = [
        ArtifactRef(
            name="metrics",
            artifact_type="metrics",
            path=f"codigo/reports/cwru_bearing/{run_id}/metrics.json",
            producer="evaluator",
        ).model_dump(mode="json")
    ]
    return validate_state(state_dict)


if __name__ == "__main__":
    unittest.main()
