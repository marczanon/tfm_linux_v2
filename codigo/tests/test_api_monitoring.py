from __future__ import annotations

import asyncio
import tempfile
import time
import unittest
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

import httpx

from codigo.app.api import create_app
from codigo.app.agents.monitoring_reviewer import (
    monitoring_review_contract_fingerprints,
)
from codigo.app.schemas.monitoring_replay import MonitoringReviewDispatchCommand
from codigo.app.services.monitoring_replay import MonitoringReplayStore
from codigo.app.services.monitoring_review_store import MonitoringReviewStore
from codigo.tests.test_monitoring_replay_service import _write_safe_scenario


HISTORICAL_MONITORING_REVIEW_V1_FINGERPRINTS = {
    "prompt_template_id": "monitoring_review_prompt_v1",
    "prompt_template_sha256": (
        "6935b3f9438e31e5fd06c2b7bdec11c933fa32ef7a2d1a732c129c5de1874ffa"
    ),
    "response_schema_id": "monitoring_review_decision_v1",
    "response_schema_sha256": (
        "5be26add584c3ba383fbf6a834fa1a1854bd5c86058361a980b5048a9303241a"
    ),
    "allowed_options_id": "monitoring_review_actions_v1",
    "allowed_options_sha256": (
        "d5819de71dcbfcf6502bbfd9287354e2b0ec3dea5f65d411bd5f812655e36586"
    ),
}


class APIMonitoringTests(unittest.TestCase):
    def test_startup_reconciles_a_child_job_lost_by_process_restart(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            scenario = _write_safe_scenario(base)
            replay_store = MonitoringReplayStore(
                base / "sessions",
                scenarios={scenario.scenario_id: scenario},
            )
            replay_store.create_session(
                scenario_id=scenario.scenario_id,
                session_id="api-restart-review",
                activation_policy_kind="P3",
            )
            replay_store.step(
                _step_command("api-restart-review", "step-001", 0)
            )
            replay_store.step(
                _step_command("api-restart-review", "step-002", 1)
            )
            session = replay_store.get_session("api-restart-review")
            trigger = next(
                item
                for item in session.triggers
                if item.trigger_type == "continuity_gap"
            )
            review_store = MonitoringReviewStore(
                base / "sessions",
                runs_root=base / "runs",
            )
            view = review_store.build_causal_view(session, trigger.trigger_id)
            evidence_catalog = review_store.load_evidence_catalog(
                session.state.session_id,
                view.view_sha256,
            )
            child_run_id = "api-restart-child"
            review_request = review_store.build_review_request(
                session,
                trigger.trigger_id,
                child_run_id=child_run_id,
                **monitoring_review_contract_fingerprints(evidence_catalog),
            )
            command_payload = {
                "command_id": "dispatch-before-restart",
                "session_id": session.state.session_id,
                "trigger_id": trigger.trigger_id,
                "trigger_event_id": trigger.event_id,
                "child_run_id": child_run_id,
                "job_id": child_run_id,
                "run_id": child_run_id,
                "attempt_no": 1,
                "expected_child_revision": 0,
                "request_ref": review_store.review_request_ref(
                    session.state.session_id,
                    child_run_id,
                ),
                "request_sha256": review_request.request_sha256,
                "causal_view_ref": review_request.causal_view_ref,
                "causal_view_sha256": view.view_sha256,
                "issued_at": datetime.now(UTC),
            }
            command_payload["command_sha256"] = (
                MonitoringReviewDispatchCommand.canonical_sha256(command_payload)
            )
            review_store.reserve_dispatch(
                session,
                MonitoringReviewDispatchCommand.model_validate(command_payload),
            )
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base],
                monitoring_replay_store=replay_store,
                monitoring_review_store=review_store,
                monitoring_review_use_llm=False,
            )

            _run_app_lifespan(app)
            reconciled = review_store.get_attempt(
                "api-restart-review",
                child_run_id,
            )
            stepped = _post(
                app,
                "/monitoring/sessions/api-restart-review/step",
                json={"command_id": "step-003", "expected_revision": 2},
            )

        self.assertEqual(reconciled.lifecycle_status, "interrupted")
        self.assertEqual(stepped.status_code, 200)
        self.assertEqual(stepped.json()["receipt"]["outcome"], "rejected")

    def test_source_create_step_and_incremental_ticks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            scenario = _write_safe_scenario(base)
            store = MonitoringReplayStore(
                base / "sessions",
                scenarios={scenario.scenario_id: scenario},
            )
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base],
                monitoring_replay_store=store,
            )

            sources = _get(app, "/monitoring/sources")
            created = _post(
                app,
                "/monitoring/sessions",
                json={
                    "scenario_id": scenario.scenario_id,
                    "session_id": "api-replay",
                },
            )
            stepped = _post(
                app,
                "/monitoring/sessions/api-replay/step",
                json={"command_id": "step-001", "expected_revision": 0},
            )
            session = _get(app, "/monitoring/sessions/api-replay")
            ticks = _get(
                app,
                "/monitoring/sessions/api-replay/ticks?after_sequence=0",
            )

        self.assertEqual(sources.status_code, 200)
        self.assertTrue(sources.json()[0]["available"])
        self.assertEqual(
            sources.json()[0]["available_activation_policy_kinds"],
            ["P0", "P3"],
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["state"]["revision"], 0)
        self.assertEqual(stepped.status_code, 200)
        self.assertEqual(stepped.json()["receipt"]["outcome"], "applied")
        self.assertEqual(len(stepped.json()["tick"]["frames"]), 4)
        self.assertEqual(session.json()["state"]["execution_cursor"], 0)
        self.assertEqual(len(ticks.json()["ticks"]), 1)

    def test_repeated_legacy_v1_dispatch_reuses_sealed_request_without_v3_rebuild(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            scenario = _write_safe_scenario(base)
            replay_store = MonitoringReplayStore(
                base / "sessions",
                scenarios={scenario.scenario_id: scenario},
            )
            replay_store.create_session(
                scenario_id=scenario.scenario_id,
                session_id="api-legacy-v1-replay",
                activation_policy_kind="P3",
            )
            replay_store.step(
                _step_command("api-legacy-v1-replay", "step-001", 0)
            )
            replay_store.step(
                _step_command("api-legacy-v1-replay", "step-002", 1)
            )
            session = replay_store.get_session("api-legacy-v1-replay")
            trigger = next(
                item
                for item in session.triggers
                if item.trigger_type == "continuity_gap"
            )
            review_store = MonitoringReviewStore(
                base / "sessions",
                runs_root=base / "runs",
            )
            view = review_store.build_causal_view(session, trigger.trigger_id)
            child_run_id = "api-legacy-v1-child"
            review_request = review_store.build_review_request(
                session,
                trigger.trigger_id,
                child_run_id=child_run_id,
                **HISTORICAL_MONITORING_REVIEW_V1_FINGERPRINTS,
            )
            request_ref = review_store.review_request_ref(
                session.state.session_id,
                child_run_id,
            )
            command_payload = {
                "command_id": "legacy-v1-dispatch-001",
                "session_id": session.state.session_id,
                "trigger_id": trigger.trigger_id,
                "trigger_event_id": trigger.event_id,
                "child_run_id": child_run_id,
                "job_id": child_run_id,
                "run_id": child_run_id,
                "attempt_no": 1,
                "expected_child_revision": 0,
                "request_ref": request_ref,
                "request_sha256": review_request.request_sha256,
                "causal_view_ref": review_request.causal_view_ref,
                "causal_view_sha256": view.view_sha256,
                "issued_at": datetime.now(UTC),
            }
            command_payload["command_sha256"] = (
                MonitoringReviewDispatchCommand.canonical_sha256(command_payload)
            )
            command = MonitoringReviewDispatchCommand.model_validate(
                command_payload
            )
            first_receipt = review_store.reserve_dispatch(session, command)
            request_bytes_before = Path(request_ref).read_bytes()
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base],
                monitoring_replay_store=replay_store,
                monitoring_review_store=review_store,
                monitoring_review_use_llm=False,
            )
            path = (
                "/monitoring/sessions/api-legacy-v1-replay/triggers/"
                f"{trigger.trigger_id}/dispatch"
            )

            with (
                mock.patch.object(
                    review_store,
                    "load_evidence_catalog",
                    side_effect=AssertionError(
                        "an idempotent legacy dispatch cannot rebuild a v3 catalog"
                    ),
                ) as load_catalog,
                mock.patch.object(
                    review_store,
                    "build_review_request",
                    side_effect=AssertionError(
                        "an idempotent legacy dispatch cannot rebuild its request"
                    ),
                ) as build_request,
                mock.patch(
                    "codigo.app.api.routes.monitoring_review_contract_fingerprints",
                    side_effect=AssertionError(
                        "an idempotent legacy dispatch cannot compute v3 fingerprints"
                    ),
                ) as current_fingerprints,
            ):
                repeated = _post(
                    app,
                    path,
                    json={
                        "command_id": command.command_id,
                        "expected_child_revision": 0,
                    },
                )

            persisted = review_store.load_review_request(
                session.state.session_id,
                review_request.request_sha256,
            )
            request_bytes_after = Path(request_ref).read_bytes()

        self.assertEqual(first_receipt.outcome, "dispatched")
        self.assertEqual(repeated.status_code, 202)
        self.assertEqual(repeated.json()["receipt"]["outcome"], "idempotent_replay")
        self.assertEqual(
            repeated.json()["receipt"]["request_sha256"],
            review_request.request_sha256,
        )
        self.assertEqual(request_bytes_after, request_bytes_before)
        self.assertEqual(
            persisted.prompt_template_id,
            HISTORICAL_MONITORING_REVIEW_V1_FINGERPRINTS["prompt_template_id"],
        )
        self.assertEqual(
            persisted.response_schema_id,
            HISTORICAL_MONITORING_REVIEW_V1_FINGERPRINTS["response_schema_id"],
        )
        load_catalog.assert_not_called()
        build_request.assert_not_called()
        current_fingerprints.assert_not_called()

    def test_step_body_cannot_override_path_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            scenario = _write_safe_scenario(base)
            store = MonitoringReplayStore(
                base / "sessions",
                scenarios={scenario.scenario_id: scenario},
            )
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base],
                monitoring_replay_store=store,
            )
            _post(
                app,
                "/monitoring/sessions",
                json={
                    "scenario_id": scenario.scenario_id,
                    "session_id": "api-replay",
                },
            )

            response = _post(
                app,
                "/monitoring/sessions/api-replay/step",
                json={
                    "command_id": "step-001",
                    "expected_revision": 0,
                    "session_id": "another-session",
                },
            )

        self.assertEqual(response.status_code, 422)

    def test_p3_is_selected_by_registered_kind_and_exposes_real_triggers(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            scenario = _write_safe_scenario(base)
            store = MonitoringReplayStore(
                base / "sessions",
                scenarios={scenario.scenario_id: scenario},
            )
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base],
                monitoring_replay_store=store,
            )
            created = _post(
                app,
                "/monitoring/sessions",
                json={
                    "scenario_id": scenario.scenario_id,
                    "session_id": "api-p3-replay",
                    "activation_policy_kind": "P3",
                },
            )
            _post(
                app,
                "/monitoring/sessions/api-p3-replay/step",
                json={"command_id": "step-001", "expected_revision": 0},
            )
            final = _post(
                app,
                "/monitoring/sessions/api-p3-replay/step",
                json={"command_id": "step-002", "expected_revision": 1},
            )
            repeated = _post(
                app,
                "/monitoring/sessions/api-p3-replay/step",
                json={"command_id": "step-002", "expected_revision": 1},
            )
            blocked = _post(
                app,
                "/monitoring/sessions/api-p3-replay/step",
                json={"command_id": "step-003", "expected_revision": 2},
            )
            unavailable = _post(
                app,
                "/monitoring/sessions",
                json={
                    "scenario_id": scenario.scenario_id,
                    "session_id": "api-p2-replay",
                    "activation_policy_kind": "P2",
                },
            )

        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json()["config"]["activation_policy_kind"], "P3")
        self.assertEqual(
            [event["trigger_type"] for event in final.json()["triggers"]],
            ["continuity_gap", "session_close"],
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(
            repeated.json()["receipt"]["outcome"],
            "idempotent_replay",
        )
        self.assertEqual(blocked.status_code, 409)
        self.assertIn("awaits", blocked.json()["detail"])
        self.assertEqual(unavailable.status_code, 503)
        self.assertIn("not registered", unavailable.json()["detail"])

    def test_emitted_trigger_dispatches_durable_seven_agent_child_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            scenario = _write_safe_scenario(base)
            store = MonitoringReplayStore(
                base / "sessions",
                scenarios={scenario.scenario_id: scenario},
            )
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base],
                monitoring_replay_store=store,
                monitoring_review_use_llm=False,
            )
            _post(
                app,
                "/monitoring/sessions",
                json={
                    "scenario_id": scenario.scenario_id,
                    "session_id": "api-review-bridge",
                    "activation_policy_kind": "P3",
                },
            )
            _post(
                app,
                "/monitoring/sessions/api-review-bridge/step",
                json={"command_id": "step-001", "expected_revision": 0},
            )
            final = _post(
                app,
                "/monitoring/sessions/api-review-bridge/step",
                json={"command_id": "step-002", "expected_revision": 1},
            )
            trigger = next(
                item
                for item in final.json()["triggers"]
                if item["trigger_type"] == "continuity_gap"
            )
            path = (
                "/monitoring/sessions/api-review-bridge/triggers/"
                f"{trigger['trigger_id']}/dispatch"
            )
            dispatched = _post(
                app,
                path,
                json={"command_id": "dispatch-001", "expected_child_revision": 0},
            )
            child_run_id = dispatched.json()["receipt"]["child_run_id"]
            job = _wait_for_job(app, child_run_id)
            session = _get(app, "/monitoring/sessions/api-review-bridge")
            child_runs = _get(
                app,
                "/monitoring/sessions/api-review-bridge/child-runs",
            )
            run = _get(app, f"/runs/{child_run_id}")
            events = _get(app, f"/runs/{child_run_id}/events")
            repeated = _post(
                app,
                path,
                json={"command_id": "dispatch-001", "expected_child_revision": 0},
            )
            duplicate = _post(
                app,
                path,
                json={"command_id": "dispatch-002", "expected_child_revision": 3},
            )
            step_after_child = _post(
                app,
                "/monitoring/sessions/api-review-bridge/step",
                json={"command_id": "step-003", "expected_revision": 2},
            )

        self.assertEqual(dispatched.status_code, 202)
        self.assertEqual(dispatched.json()["receipt"]["outcome"], "dispatched")
        self.assertEqual(
            dispatched.json()["attempt"],
            dispatched.json()["receipt"]["attempt"],
        )
        self.assertEqual(job.status_code, 200)
        self.assertEqual(job.json()["status"], "completed")
        self.assertEqual(session.status_code, 200)
        self.assertEqual(session.json()["child_revision"], 3)
        self.assertEqual(session.json()["child_runs"][0]["lifecycle_status"], "resolved")
        self.assertEqual(
            [
                item["lifecycle_status"]
                for item in session.json()["triggers"]
                if item["trigger_id"] == trigger["trigger_id"]
            ],
            ["emitted", "dispatched", "running", "resolved"],
        )
        self.assertEqual(child_runs.status_code, 200)
        self.assertEqual(child_runs.json()["child_runs"][0]["run_id"], child_run_id)
        self.assertEqual(run.status_code, 200)
        self.assertEqual(run.json()["n_decisions"], 7)
        self.assertEqual(
            len(
                [
                    item
                    for item in events.json()
                    if item["kind"] in {"agent_decision", "supervisor_decision"}
                ]
            ),
            7,
        )
        self.assertEqual(repeated.status_code, 202)
        self.assertEqual(repeated.json()["receipt"]["outcome"], "idempotent_replay")
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(step_after_child.status_code, 200)
        self.assertEqual(step_after_child.json()["receipt"]["outcome"], "rejected")


def _get(app, path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.get(path)

    return asyncio.run(request())


def _post(app, path: str, *, json: dict[str, object]) -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.post(path, json=json)

    return asyncio.run(request())


def _wait_for_job(app, job_id: str) -> httpx.Response:
    response = _get(app, f"/run-jobs/{job_id}")
    deadline = time.monotonic() + 5.0
    while response.json().get("status") not in {"completed", "failed"}:
        if time.monotonic() >= deadline:
            raise AssertionError(f"monitoring child job did not finish: {job_id}")
        time.sleep(0.01)
        response = _get(app, f"/run-jobs/{job_id}")
    return response


def _step_command(session_id: str, command_id: str, revision: int):
    from codigo.app.schemas.monitoring_replay import ReplayStepCommand

    return ReplayStepCommand(
        command_id=command_id,
        session_id=session_id,
        expected_revision=revision,
    )


def _run_app_lifespan(app) -> None:
    async def run() -> None:
        async with app.router.lifespan_context(app):
            return

    asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
