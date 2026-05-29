import json
import tempfile
import time
import unittest
import asyncio
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

import httpx

from codigo.app.api import create_app
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import (
    ArtifactRef,
    EvaluationResult,
    HumanApproval,
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

    def test_post_runs_dry_run_returns_plan_without_execution(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base / "raw"],
            )

            response = _post(
                app,
                "/runs",
                json={
                    "run_id": "api-plan-cwru",
                    "dataset_id": "cwru_bearing",
                    "adapter_id": "cwru_bearing",
                    "raw_path": raw_dir.as_posix(),
                },
            )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["dry_run"])
        self.assertFalse(payload["executed"])
        self.assertTrue(payload["plan"]["can_execute_requested_stages"])
        self.assertIsNone(payload["snapshot"])

    def test_post_runs_rejects_raw_path_outside_allowed_roots(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "external" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base / "raw"],
            )

            response = _post(
                app,
                "/runs",
                json={
                    "run_id": "api-forbidden-path",
                    "dataset_id": "cwru_bearing",
                    "adapter_id": "cwru_bearing",
                    "raw_path": raw_dir.as_posix(),
                },
            )

        self.assertEqual(response.status_code, 403)

    def test_post_runs_execute_blocks_dataset_policy_violations(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = _nasa_raw_dir(base)
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base / "raw"],
            )

            response = _post(
                app,
                "/runs",
                json={
                    "run_id": "api-blocked-nasa",
                    "dataset_id": "nasa_ims_bearing",
                    "adapter_id": "nasa_ims_bearing",
                    "raw_path": raw_dir.as_posix(),
                    "dry_run": False,
                },
            )

        self.assertEqual(response.status_code, 409)

    def test_post_runs_execute_persists_snapshot_when_allowed(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(runs_dir=runs_dir, allowed_raw_roots=[base / "raw"])

            def fake_run_dataset_pipeline(pipeline_request, *, runs_dir, **kwargs):
                state = _state(
                    base,
                    pipeline_request.run_id,
                    f1_score=0.66,
                    approved=False,
                )
                snapshot = save_run_snapshot(state, runs_dir)
                return SimpleNamespace(
                    state=state.to_langgraph_state(),
                    snapshot=snapshot,
                )

            with patch(
                "codigo.app.api.routes.run_dataset_pipeline",
                side_effect=fake_run_dataset_pipeline,
            ):
                response = _post(
                    app,
                    "/runs",
                    json={
                        "run_id": "api-execute-cwru",
                        "dataset_id": "cwru_bearing",
                        "adapter_id": "cwru_bearing",
                        "raw_path": raw_dir.as_posix(),
                        "dry_run": False,
                    },
                )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["dry_run"])
        self.assertTrue(payload["executed"])
        self.assertEqual(payload["final_stage"], "completed")
        self.assertFalse(payload["approved"])
        self.assertEqual(payload["snapshot"]["run_id"], "api-execute-cwru")

    def test_post_runs_passive_human_review_returns_non_blocking_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(runs_dir=base / "runs", allowed_raw_roots=[base / "raw"])

            response = _post(
                app,
                "/runs",
                json={
                    "run_id": "api-passive-review",
                    "dataset_id": "cwru_bearing",
                    "adapter_id": "cwru_bearing",
                    "raw_path": raw_dir.as_posix(),
                    "human_review": {
                        "mode": "passive",
                        "reviewer": "advisor",
                        "required_decision_points": ["modeling"],
                    },
                },
            )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["executed"])
        self.assertFalse(payload["human_approval"]["required"])
        self.assertIsNone(payload["human_approval"]["approved"])
        self.assertIn("modeling", payload["human_review_reasons"][0])

    def test_post_runs_required_human_review_blocks_without_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(runs_dir=base / "runs", allowed_raw_roots=[base / "raw"])

            response = _post(
                app,
                "/runs",
                json={
                    "run_id": "api-required-review-blocked",
                    "dataset_id": "cwru_bearing",
                    "adapter_id": "cwru_bearing",
                    "raw_path": raw_dir.as_posix(),
                    "dry_run": False,
                    "human_review": {
                        "mode": "required",
                        "required_decision_points": ["modeling"],
                    },
                },
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("human review", response.json()["detail"])

    def test_post_runs_required_human_review_executes_with_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(runs_dir=runs_dir, allowed_raw_roots=[base / "raw"])

            def fake_run_dataset_pipeline(
                pipeline_request,
                *,
                runs_dir,
                human_approval=None,
                **kwargs,
            ):
                state = _state(
                    base,
                    pipeline_request.run_id,
                    f1_score=0.91,
                    human_approval=human_approval,
                )
                snapshot = save_run_snapshot(state, runs_dir)
                return SimpleNamespace(
                    state=state.to_langgraph_state(),
                    snapshot=snapshot,
                )

            with patch(
                "codigo.app.api.routes.run_dataset_pipeline",
                side_effect=fake_run_dataset_pipeline,
            ):
                response = _post(
                    app,
                    "/runs",
                    json={
                        "run_id": "api-required-review-approved",
                        "dataset_id": "cwru_bearing",
                        "adapter_id": "cwru_bearing",
                        "raw_path": raw_dir.as_posix(),
                        "dry_run": False,
                        "human_review": {
                            "mode": "required",
                            "required_decision_points": ["modeling"],
                        },
                        "human_approval": {
                            "required": True,
                            "approved": True,
                            "reviewer": "advisor",
                            "reason": "Small local execution approved.",
                        },
                    },
                )

        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["executed"])
        self.assertTrue(payload["human_approval"]["approved"])
        self.assertEqual(payload["human_approval"]["reviewer"], "advisor")

    def test_get_run_job_missing_returns_404(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(runs_dir=Path(tmp) / "runs")

            response = _get(app, "/run-jobs/missing-job")

        self.assertEqual(response.status_code, 404)

    def test_post_runs_background_job_persists_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(runs_dir=runs_dir, allowed_raw_roots=[base / "raw"])

            def fake_run_dataset_pipeline(pipeline_request, *, runs_dir, **kwargs):
                state = _state(base, pipeline_request.run_id, f1_score=0.89)
                snapshot = save_run_snapshot(state, runs_dir)
                return SimpleNamespace(
                    state=state.to_langgraph_state(),
                    snapshot=snapshot,
                )

            with patch(
                "codigo.app.api.routes.run_dataset_pipeline",
                side_effect=fake_run_dataset_pipeline,
            ):
                response = _post(
                    app,
                    "/runs",
                    json={
                        "run_id": "api-background-cwru",
                        "dataset_id": "cwru_bearing",
                        "adapter_id": "cwru_bearing",
                        "raw_path": raw_dir.as_posix(),
                        "dry_run": False,
                        "background": True,
                    },
                )

            payload = response.json()
            self.assertEqual(response.status_code, 202)
            self.assertFalse(payload["executed"])
            self.assertIsNone(payload["snapshot"])
            self.assertEqual(payload["job"]["run_id"], "api-background-cwru")

            job_response = _get(app, "/run-jobs/api-background-cwru")
            job_payload = _wait_for_job(app, "api-background-cwru", "completed")
            self.assertEqual(job_response.status_code, 200)
            self.assertEqual(job_payload["status"], "completed")
            self.assertEqual(job_payload["snapshot"]["run_id"], "api-background-cwru")

            snapshot_response = _get(app, "/runs/api-background-cwru")
            self.assertEqual(snapshot_response.status_code, 200)
            self.assertEqual(snapshot_response.json()["run_id"], "api-background-cwru")

    def test_post_runs_background_job_records_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            raw_dir = base / "raw" / "cwru"
            raw_dir.mkdir(parents=True)
            (raw_dir / "97.mat").touch()
            app = create_app(runs_dir=base / "runs", allowed_raw_roots=[base / "raw"])

            def fake_run_dataset_pipeline(*args, **kwargs):
                raise RuntimeError("simulated execution error")

            with patch(
                "codigo.app.api.routes.run_dataset_pipeline",
                side_effect=fake_run_dataset_pipeline,
            ):
                response = _post(
                    app,
                    "/runs",
                    json={
                        "run_id": "api-background-failed",
                        "dataset_id": "cwru_bearing",
                        "adapter_id": "cwru_bearing",
                        "raw_path": raw_dir.as_posix(),
                        "dry_run": False,
                        "background": True,
                    },
                )

            self.assertEqual(response.status_code, 202)
            job_response = _get(app, "/run-jobs/api-background-failed")
            job_payload = _wait_for_job(app, "api-background-failed", "failed")
            self.assertEqual(job_response.status_code, 200)
            self.assertEqual(job_payload["status"], "failed")
            self.assertIn("RuntimeError", job_payload["detail"])


def _get(app, path: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(path, **kwargs)

    return asyncio.run(request())


def _post(app, path: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.post(path, **kwargs)

    return asyncio.run(request())


def _nasa_raw_dir(base: Path) -> Path:
    raw_dir = base / "raw" / "nasa_ims_bearing" / "2nd_test"
    raw_dir.mkdir(parents=True)
    (raw_dir / "2004.02.12.10.32.39").write_text(
        "0.1\t0.2\t0.3\t0.4\n0.2\t0.3\t0.4\t0.5\n",
        encoding="utf-8",
    )
    return raw_dir.parent


def _wait_for_job(app, job_id: str, expected_status: str) -> dict:
    for _ in range(100):
        response = _get(app, f"/run-jobs/{job_id}")
        payload = response.json()
        if payload["status"] == expected_status:
            return payload
        time.sleep(0.01)
    return _get(app, f"/run-jobs/{job_id}").json()


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
    human_approval: HumanApproval | None = None,
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
        next_action="continue",
        limitations=[],
    ).model_dump(mode="json")
    if human_approval is not None:
        state_dict["human_approval"] = human_approval.model_dump(mode="json")
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
