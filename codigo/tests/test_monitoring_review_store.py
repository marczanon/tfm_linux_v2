from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path

from codigo.app.agents.monitoring_reviewer import (
    monitoring_review_contract_fingerprints,
)
from codigo.app.schemas.monitoring_replay import (
    MonitoringReviewDispatchCommand,
    MonitoringReviewResult,
    ReplayStepCommand,
)
from codigo.app.services.agent_runtime import AgentRuntimeRecorder
from codigo.app.services.monitoring_replay import (
    MonitoringReplayConflictError,
    MonitoringReplayStore,
)
from codigo.app.services.monitoring_review_store import MonitoringReviewStore
from codigo.app.services.pipeline_runner import run_monitoring_review
from codigo.tests.test_monitoring_replay_service import _write_safe_scenario


class MonitoringReviewStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.scenario = _write_safe_scenario(self.base)
        self.sessions_root = self.base / "sessions"
        self.runs_root = self.base / "runs"
        self.replay = MonitoringReplayStore(
            self.sessions_root,
            scenarios={self.scenario.scenario_id: self.scenario},
        )
        self.replay.create_session(
            scenario_id=self.scenario.scenario_id,
            session_id="review-session",
            activation_policy_kind="P3",
        )
        self.replay.step(
            ReplayStepCommand(
                command_id="step-001",
                session_id="review-session",
                expected_revision=0,
            )
        )
        self.replay.step(
            ReplayStepCommand(
                command_id="step-002",
                session_id="review-session",
                expected_revision=1,
            )
        )
        self.session = self.replay.get_session("review-session")
        self.trigger = next(
            item
            for item in self.session.triggers
            if item.trigger_type == "continuity_gap"
        )
        self.store = MonitoringReviewStore(
            self.sessions_root,
            runs_root=self.runs_root,
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _reserved(self):
        view = self.store.build_causal_view(self.session, self.trigger.trigger_id)
        catalog = self.store.load_evidence_catalog(
            self.session.state.session_id,
            view.view_sha256,
        )
        child_run_id = "review-session-child-001"
        request = self.store.build_review_request(
            self.session,
            self.trigger.trigger_id,
            child_run_id=child_run_id,
            **monitoring_review_contract_fingerprints(catalog),
        )
        payload = {
            "command_id": "dispatch-001",
            "session_id": self.session.state.session_id,
            "trigger_id": self.trigger.trigger_id,
            "trigger_event_id": self.trigger.event_id,
            "child_run_id": child_run_id,
            "job_id": child_run_id,
            "run_id": child_run_id,
            "attempt_no": 1,
            "expected_child_revision": 0,
            "request_ref": self.store.review_request_ref(
                self.session.state.session_id,
                child_run_id,
            ),
            "request_sha256": request.request_sha256,
            "causal_view_ref": request.causal_view_ref,
            "causal_view_sha256": view.view_sha256,
            "issued_at": datetime.now(UTC),
        }
        payload["command_sha256"] = MonitoringReviewDispatchCommand.canonical_sha256(
            payload
        )
        command = MonitoringReviewDispatchCommand.model_validate(payload)
        receipt = self.store.reserve_dispatch(self.session, command)
        return view, request, command, receipt

    def test_trigger_view_dispatch_review_and_lifecycle_are_durable(self) -> None:
        replay_commit_before = (
            self.sessions_root / "review-session" / "commits" / "000002.json"
        ).read_bytes()
        view, request, command, receipt = self._reserved()

        self.assertEqual(receipt.outcome, "dispatched")
        self.assertEqual(receipt.child_revision, 1)
        evidence = self.store.load_evidence_records("review-session", view.view_sha256)
        self.assertEqual(len(evidence), 5)
        self.assertEqual(
            len([item for item in evidence if item["analysis_status"] == "modeled"]),
            2,
        )
        repeated = self.store.reserve_dispatch(self.session, command)
        self.assertEqual(repeated.outcome, "idempotent_replay")
        self.assertEqual(repeated.attempt, receipt.attempt)
        running = self.store.mark_running("review-session", command.child_run_id)
        recorder = AgentRuntimeRecorder(command.child_run_id, lambda _: None)
        execution = run_monitoring_review(
            request,
            view,
            self.store.load_evidence_records("review-session", view.view_sha256),
            runs_dir=self.runs_root,
            runtime_recorder=recorder,
            use_llm=False,
        )
        terminal = self.store.mark_terminal(
            "review-session",
            command.child_run_id,
            execution.result,
        )
        decorated = self.store.decorate_session(self.session)

        self.assertEqual(running.lifecycle_status, "running")
        self.assertEqual(terminal.lifecycle_status, "resolved")
        self.assertEqual(decorated.child_revision, 3)
        self.assertEqual(decorated.child_runs[0].lifecycle_status, "resolved")
        self.assertIsNone(decorated.active_child_run_id)
        self.assertEqual(
            [
                item.lifecycle_status
                for item in decorated.triggers
                if item.trigger_id == self.trigger.trigger_id
            ],
            ["emitted", "dispatched", "running", "resolved"],
        )
        self.assertEqual(
            replay_commit_before,
            (
                self.sessions_root
                / "review-session"
                / "commits"
                / "000002.json"
            ).read_bytes(),
        )
        reloaded = MonitoringReviewStore(
            self.sessions_root,
            runs_root=self.runs_root,
        ).decorate_session(self.session)
        self.assertEqual(reloaded.child_runs, decorated.child_runs)

    def test_tampered_evidence_and_reused_command_are_rejected(self) -> None:
        view, _, command, _ = self._reserved()
        evidence_path = Path(view.evidence[0].artifact_ref)
        payload = json.loads(evidence_path.read_text(encoding="utf-8"))
        payload[0]["health_state"] = "critical"
        evidence_path.write_text(json.dumps(payload), encoding="utf-8")
        with self.assertRaisesRegex(MonitoringReplayConflictError, "SHA-256"):
            self.store.load_evidence_records("review-session", view.view_sha256)

        changed_payload = command.model_dump(
            mode="python",
            exclude={"command_sha256"},
        )
        changed_payload["expected_child_revision"] = 1
        changed_payload["command_sha256"] = (
            MonitoringReviewDispatchCommand.canonical_sha256(changed_payload)
        )
        changed = MonitoringReviewDispatchCommand.model_validate(changed_payload)
        with self.assertRaisesRegex(MonitoringReplayConflictError, "reused"):
            self.store.reserve_dispatch(self.session, changed)

    def test_persisted_request_rejects_changed_contract_fingerprints(self) -> None:
        child_run_id = "review-session-child-contract"
        view = self.store.build_causal_view(self.session, self.trigger.trigger_id)
        catalog = self.store.load_evidence_catalog(
            self.session.state.session_id,
            view.view_sha256,
        )
        fingerprints = monitoring_review_contract_fingerprints(catalog)
        original = self.store.build_review_request(
            self.session,
            self.trigger.trigger_id,
            child_run_id=child_run_id,
            **fingerprints,
        )
        changed = dict(fingerprints)
        changed["prompt_template_sha256"] = "a" * 64

        with self.assertRaisesRegex(
            MonitoringReplayConflictError,
            "contract binding",
        ):
            self.store.build_review_request(
                self.session,
                self.trigger.trigger_id,
                child_run_id=child_run_id,
                **changed,
            )
        self.assertEqual(
            self.store.load_review_request(
                self.session.state.session_id,
                original.request_sha256,
            ),
            original,
        )

    def test_missing_dispatch_receipt_is_recovered_from_the_child_ledger(self) -> None:
        _, _, command, receipt = self._reserved()
        receipt_path = next(
            (
                self.sessions_root
                / "review-session"
                / "child_run_receipts"
            ).glob("*.json")
        )
        receipt_path.unlink()

        anchored_command = self.store.get_dispatch_command(
            "review-session",
            command.command_id,
        )
        recovered = self.store.reserve_dispatch(
            self.session,
            anchored_command,
        )

        self.assertEqual(anchored_command, command)
        self.assertEqual(recovered.outcome, "idempotent_replay")
        self.assertEqual(recovered.attempt, receipt.attempt)
        self.assertTrue(receipt_path.is_file())
        self.assertEqual(len(self.store.list_attempts("review-session")), 1)

    def test_restart_marks_an_orphaned_local_job_interrupted(self) -> None:
        _, _, command, _ = self._reserved()
        restarted = MonitoringReviewStore(
            self.sessions_root,
            runs_root=self.runs_root,
        )

        attempts = restarted.reconcile_orphaned_attempts(
            "review-session",
            job_exists=lambda _: False,
        )

        self.assertEqual(attempts[0].lifecycle_status, "interrupted")
        self.assertIsNone(restarted.active_child_run_id("review-session"))
        restarted.assert_step_allowed(self.session)
        repeated = restarted.reserve_dispatch(self.session, command)
        self.assertEqual(repeated.outcome, "idempotent_replay")

    def test_resolved_attempt_requires_its_exact_persisted_result(self) -> None:
        view, request, command, _ = self._reserved()
        self.store.mark_running("review-session", command.child_run_id)
        recorder = AgentRuntimeRecorder(command.child_run_id, lambda _: None)
        execution = run_monitoring_review(
            request,
            view,
            self.store.load_evidence_records("review-session", view.view_sha256),
            runs_dir=self.runs_root,
            runtime_recorder=recorder,
            use_llm=False,
        )
        self.store.mark_terminal(
            "review-session",
            command.child_run_id,
            execution.result,
        )
        runtime_events_path = Path(execution.result.runtime_events_ref)
        runtime_events_bytes = runtime_events_path.read_bytes()
        runtime_events_path.unlink()
        with self.assertRaisesRegex(
            MonitoringReplayConflictError,
            "runtime events are unavailable",
        ):
            self.store.decorate_session(self.session)
        runtime_events_path.write_bytes(runtime_events_bytes)
        (
            self.runs_root
            / command.child_run_id
            / "monitoring_review_result.json"
        ).unlink()

        with self.assertRaisesRegex(
            MonitoringReplayConflictError,
            "result is unavailable",
        ):
            self.store.decorate_session(self.session)

    def test_terminal_write_rejects_a_result_from_another_causal_envelope(self) -> None:
        view, request, command, _ = self._reserved()
        self.store.mark_running("review-session", command.child_run_id)
        recorder = AgentRuntimeRecorder(command.child_run_id, lambda _: None)
        execution = run_monitoring_review(
            request,
            view,
            self.store.load_evidence_records("review-session", view.view_sha256),
            runs_dir=self.runs_root,
            runtime_recorder=recorder,
            use_llm=False,
        )
        altered_payload = execution.result.model_dump(
            mode="python",
            exclude={"result_sha256"},
        )
        altered_payload["session_id"] = "another-session"
        altered_payload["result_sha256"] = MonitoringReviewResult.canonical_sha256(
            altered_payload
        )
        altered = MonitoringReviewResult.model_validate(altered_payload)

        with self.assertRaisesRegex(
            MonitoringReplayConflictError,
            "does not bind",
        ):
            self.store.mark_terminal(
                "review-session",
                command.child_run_id,
                altered,
            )
        self.assertEqual(
            self.store.get_attempt(
                "review-session",
                command.child_run_id,
            ).lifecycle_status,
            "running",
        )


if __name__ == "__main__":
    unittest.main()
