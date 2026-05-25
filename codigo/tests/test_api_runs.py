import json
import tempfile
import unittest
import asyncio
from pathlib import Path

import httpx

from codigo.app.api import create_app
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import (
    ArtifactRef,
    EvaluationResult,
    MetricsReport,
    StateMessage,
)
from codigo.app.services.run_persistence import save_run_snapshot


class APIRunsTests(unittest.TestCase):
    def test_health_returns_configured_runs_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            app = create_app(runs_dir=runs_dir)

            response = _get(app, "/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["runs_dir"], str(runs_dir))

    def test_list_runs_supports_filters(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            save_run_snapshot(_state(base, "run-approved", f1_score=0.91), runs_dir)
            save_run_snapshot(
                _state(base, "run-rejected", f1_score=0.70, approved=False),
                runs_dir,
            )
            app = create_app(runs_dir=runs_dir)

            all_response = _get(app, "/runs")
            approved_response = _get(app, "/runs", params={"approved": True})

        self.assertEqual(all_response.status_code, 200)
        self.assertEqual(approved_response.status_code, 200)
        self.assertEqual(
            {item["run_id"] for item in all_response.json()},
            {"run-approved", "run-rejected"},
        )
        self.assertEqual(
            [item["run_id"] for item in approved_response.json()],
            ["run-approved"],
        )

    def test_get_run_artifacts_and_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            save_run_snapshot(_state(base, "run-api", f1_score=0.94), runs_dir)
            app = create_app(runs_dir=runs_dir)

            snapshot_response = _get(app, "/runs/run-api")
            artifacts_response = _get(app, "/runs/run-api/artifacts")
            report_response = _get(app, "/runs/run-api/report")

        self.assertEqual(snapshot_response.status_code, 200)
        self.assertEqual(snapshot_response.json()["run_id"], "run-api")
        self.assertEqual(artifacts_response.status_code, 200)
        self.assertEqual(artifacts_response.json()[0]["artifact_type"], "metrics")
        self.assertEqual(report_response.status_code, 200)
        self.assertIn("# Report run-api", report_response.text)
        self.assertIn("text/markdown", report_response.headers["content-type"])

    def test_compare_runs_returns_metric_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            save_run_snapshot(
                _state(
                    base,
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
                    base,
                    "run-candidate",
                    precision=0.95,
                    recall=0.94,
                    f1_score=0.945,
                    false_positive_rate=0.04,
                ),
                runs_dir,
            )
            app = create_app(runs_dir=runs_dir)

            response = _get(
                app,
                "/runs/compare",
                params=[
                    ("run_ids", "run-baseline"),
                    ("run_ids", "run-candidate"),
                ],
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        metrics = {item["metric"]: item for item in payload["metrics"]}
        self.assertEqual(payload["run_ids"], ["run-baseline", "run-candidate"])
        self.assertEqual(metrics["f1_score"]["best_run_id"], "run-candidate")
        self.assertEqual(
            metrics["false_positive_rate"]["best_run_id"],
            "run-candidate",
        )

    def test_compare_runs_validation_errors_are_http_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            save_run_snapshot(_state(base, "run-present", f1_score=0.91), runs_dir)
            app = create_app(runs_dir=runs_dir)

            too_few_runs = _get(
                app,
                "/runs/compare",
                params={"run_ids": "run-present"},
            )
            missing_run = _get(
                app,
                "/runs/compare",
                params=[
                    ("run_ids", "run-present"),
                    ("run_ids", "run-missing"),
                ],
            )

        self.assertEqual(too_few_runs.status_code, 400)
        self.assertEqual(missing_run.status_code, 404)

    def test_missing_run_and_missing_report_return_404(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            save_run_snapshot(
                _state(base, "run-no-report", f1_score=0.90, write_report=False),
                runs_dir,
            )
            app = create_app(runs_dir=runs_dir)

            missing_run = _get(app, "/runs/missing-run")
            missing_report = _get(app, "/runs/run-no-report/report")

        self.assertEqual(missing_run.status_code, 404)
        self.assertEqual(missing_report.status_code, 404)


def _get(app, path: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(path, **kwargs)

    return asyncio.run(request())


def _state(
    base: Path,
    run_id: str,
    *,
    precision: float = 0.93,
    recall: float = 0.95,
    f1_score: float,
    false_positive_rate: float = 0.04,
    approved: bool = True,
    write_report: bool = True,
):
    report_path = base / "reports" / f"{run_id}.md"
    if write_report:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(f"# Report {run_id}\n", encoding="utf-8")

    state_dict = create_initial_cwru_state(
        thread_id=f"thread-{run_id}",
        run_id=run_id,
        raw_path=str(base / "raw"),
    )
    state_dict["current_stage"] = "completed"
    state_dict["next_node"] = None
    state_dict["report_path"] = str(report_path)
    state_dict["metrics"] = MetricsReport(
        metrics_path=str(base / "metrics" / f"{run_id}.json"),
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
            path=str(base / "metrics" / f"{run_id}.json"),
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
        ).model_dump(mode="json")
    ]
    return validate_state(state_dict)


if __name__ == "__main__":
    unittest.main()
