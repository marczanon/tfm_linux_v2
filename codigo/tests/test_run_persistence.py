import json
import tempfile
import unittest
from pathlib import Path

from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import (
    ArtifactRef,
    EvaluationResult,
    MetricsReport,
    StateMessage,
)
from codigo.app.services.run_persistence import (
    extract_decisions,
    load_run_index,
    load_run_snapshot,
    save_run_snapshot,
)


class RunPersistenceTests(unittest.TestCase):
    def test_save_run_snapshot_writes_expected_files_and_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            state = _completed_state("run-persist-001")

            snapshot = save_run_snapshot(state, runs_dir)
            loaded = load_run_snapshot("run-persist-001", runs_dir)
            index = load_run_index(runs_dir)

            run_dir = runs_dir / "run-persist-001"
            state_payload = _read_json(run_dir / "state_final.json")
            decisions = _read_json(run_dir / "decisions.json")
            artifacts = _read_json(run_dir / "artifacts.json")
            metrics = _read_json(run_dir / "metrics.json")
            evaluation = _read_json(run_dir / "evaluation.json")
            summary = (run_dir / "summary.md").read_text(encoding="utf-8")

        self.assertEqual(snapshot.run_id, "run-persist-001")
        self.assertEqual(loaded.run_id, snapshot.run_id)
        self.assertEqual(state_payload["current_stage"], "completed")
        self.assertEqual([item["agent_name"] for item in decisions], ["supervisor", "cleaner"])
        self.assertEqual(artifacts[0]["artifact_type"], "metrics")
        self.assertEqual(metrics["f1_score"], 0.94)
        self.assertTrue(evaluation["approved"])
        self.assertIn("# Run run-persist-001", summary)
        self.assertEqual(len(index.runs), 1)
        self.assertEqual(index.runs[0].run_id, "run-persist-001")
        self.assertEqual(index.runs[0].f1_score, 0.94)

    def test_save_run_snapshot_replaces_existing_index_entry(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            state = _completed_state("run-persist-dup")

            first = save_run_snapshot(state, runs_dir)
            second = save_run_snapshot(state, runs_dir)
            index = load_run_index(runs_dir)

        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(len(index.runs), 1)
        self.assertEqual(index.runs[0].run_id, "run-persist-dup")

    def test_save_run_snapshot_rejects_path_like_run_id(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-persistence-test",
            run_id="../bad",
        )
        state = validate_state(state_dict)

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                save_run_snapshot(state, Path(tmp) / "runs")

    def test_extract_decisions_ignores_tool_messages(self):
        state = _completed_state("run-persist-decisions")

        decisions = extract_decisions(state)

        self.assertEqual(len(decisions), 2)
        self.assertEqual([item["role"] for item in decisions], ["supervisor", "agent"])


def _completed_state(run_id: str):
    state_dict = create_initial_cwru_state(
        thread_id="cwru-persistence-test",
        run_id=run_id,
    )
    state_dict["current_stage"] = "completed"
    state_dict["next_node"] = None
    state_dict["report_path"] = "codigo/reports/cwru_bearing/final_report.md"
    state_dict["metrics"] = MetricsReport(
        metrics_path="codigo/reports/cwru_bearing/evaluation/metrics.json",
        precision=0.93,
        recall=0.95,
        f1_score=0.94,
        roc_auc=0.97,
        pr_auc=0.96,
        false_positive_rate=0.04,
    ).model_dump(mode="json")
    state_dict["evaluation"] = EvaluationResult(
        approved=True,
        summary="Ejecucion aprobada.",
        next_action="continue",
        limitations=["Validacion limitada a CWRU."],
    ).model_dump(mode="json")
    state_dict["artifacts"] = [
        ArtifactRef(
            name="metrics",
            artifact_type="metrics",
            path="codigo/reports/cwru_bearing/evaluation/metrics.json",
            producer="evaluator",
        ).model_dump(mode="json")
    ]
    state_dict["messages"] = [
        StateMessage(
            role="supervisor",
            name="supervisor",
            content=json.dumps(
                {
                    "agent_name": "supervisor",
                    "decision_id": f"{run_id}:supervisor:001",
                    "next_stage": "completed",
                }
            ),
        ).model_dump(mode="json"),
        StateMessage(
            role="tool",
            name="evaluation",
            content="evaluation: ok",
        ).model_dump(mode="json"),
        StateMessage(
            role="agent",
            name="cleaner",
            content=json.dumps(
                {
                    "agent_name": "cleaner",
                    "decision_id": f"{run_id}:cleaner:001",
                }
            ),
        ).model_dump(mode="json"),
    ]
    return validate_state(state_dict)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
