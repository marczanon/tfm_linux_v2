from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError

from codigo.app.schemas.monitoring_replay import MONITORING_REVIEW_ROLES
from codigo.app.schemas.monitoring_replay import ReplayStepCommand
from codigo.app.services import monitoring_cinematic_export as cinematic
from codigo.app.services.monitoring_evidence_campaign import (
    default_monitoring_evidence_campaign_plan,
)
from codigo.app.services.monitoring_replay import MonitoringReplayStore
from codigo.tests.test_monitoring_replay_service import _write_safe_scenario


class MonitoringCinematicExportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.campaign_plan = default_monitoring_evidence_campaign_plan()
        if cls.campaign_plan.plan_sha256 != cinematic.OFFICIAL_CAMPAIGN_PLAN_SHA256:
            raise AssertionError("frozen campaign sources no longer match official plan")

    def test_capture_plan_is_bound_to_official_campaign_and_preregisters_once(self):
        plan = cinematic.default_monitoring_cinematic_capture_plan(
            self.campaign_plan,
            capture_id="cinematic-plan-test",
        )
        self.assertEqual(
            plan.campaign_plan_sha256,
            cinematic.OFFICIAL_CAMPAIGN_PLAN_SHA256,
        )
        self.assertEqual(plan.expected_beat_count, 726)
        self.assertEqual(plan.expected_video_frame_count, 1121)
        self.assertEqual(
            plan.keyframes,
            (
                "tick:000",
                "tick:352",
                "trigger:353",
                "tick:496",
                "trigger:498",
                "trigger:499",
                "trigger:688",
                "final_verdict",
            ),
        )
        for source in (
            "codigo/app/services/monitoring_cinematic_export.py",
            "codigo/scripts/export_monitoring_campaign_cinematic.py",
            "codigo/frontend/scripts/capture-monitoring-cinematic.mjs",
            "codigo/frontend/src/lib/monitoringCinematic.ts",
            "codigo/frontend/src/lib/agentRuntime.ts",
            "codigo/frontend/src/lib/agentStory.ts",
        ):
            self.assertIn(source, plan.source_sha256s)

        registered_at = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as tmp:
            registration = cinematic.preregister_monitoring_cinematic_capture(
                plan,
                output_root=tmp,
                registered_at=registered_at,
            )
            repeated = cinematic.preregister_monitoring_cinematic_capture(
                plan,
                output_root=tmp,
                registered_at=registered_at + timedelta(minutes=1),
            )
            loaded_plan, loaded_registration = (
                cinematic.load_monitoring_cinematic_preregistration(
                    plan.capture_id,
                    output_root=tmp,
                )
            )

        self.assertEqual(repeated, registration)
        self.assertEqual(loaded_plan, plan)
        self.assertEqual(loaded_registration, registration)
        self.assertEqual(registration.registered_at, registered_at)

    def test_preregistration_lock_is_idempotent_under_threads(self):
        plan = cinematic.default_monitoring_cinematic_capture_plan(
            self.campaign_plan,
            capture_id="cinematic-lock-test",
        )
        registered_at = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
        with tempfile.TemporaryDirectory() as tmp:
            def register():
                return cinematic.preregister_monitoring_cinematic_capture(
                    plan,
                    output_root=tmp,
                    registered_at=registered_at,
                )

            with ThreadPoolExecutor(max_workers=4) as executor:
                registrations = list(executor.map(lambda _: register(), range(8)))

        self.assertEqual(
            {item.registration_sha256 for item in registrations},
            {registrations[0].registration_sha256},
        )

    def test_source_validation_detects_a_changed_renderer(self):
        plan = cinematic.default_monitoring_cinematic_capture_plan(
            self.campaign_plan,
            capture_id="cinematic-source-test",
        )
        payload = plan.model_dump(mode="python")
        first_source = next(iter(payload["source_sha256s"]))
        payload["source_sha256s"][first_source] = "0" * 64
        payload["capture_plan_sha256"] = (
            cinematic.MonitoringCinematicCapturePlan.canonical_sha256(payload)
        )
        changed = cinematic.MonitoringCinematicCapturePlan.model_validate(payload)

        with self.assertRaisesRegex(ValueError, "renderer source changed"):
            cinematic.validate_monitoring_cinematic_sources(changed)

    def test_builds_exact_726_beat_chain_with_legible_agent_fields(self):
        ticks = _ticks()
        reviews = _reviews(ticks)
        beats = cinematic.build_monitoring_cinematic_timeline(
            campaign_id="nasa-p3-agentic-window-56h-v1",
            session_id="nasa-p3-agentic-window-56h-v1-session",
            ticks=ticks,
            reviews=reviews,
            operational_verdict="passed",
            agentic_verdict="blocked",
            evidence_verdict="blocked",
            blockers=("fallback_count",),
        )

        self.assertEqual(len(beats), 726)
        self.assertEqual(sum(item.duration_frames for item in beats), 1121)
        self.assertEqual(beats[0].previous_beat_sha256, "0" * 64)
        self.assertEqual(beats[-1].previous_beat_sha256, beats[-2].beat_sha256)
        self.assertEqual(beats[-1].kind, "final_verdict")
        self.assertEqual(beats[-1].display_projection.verdict.agentic, "blocked")
        trigger = beats[354]
        decision = beats[355]
        proposal = beats[362]
        self.assertEqual(trigger.kind, "trigger")
        self.assertEqual(trigger.cursor, 353)
        self.assertEqual(decision.kind, "agent_decision")
        self.assertEqual(decision.display_projection.decision.agent_name, "supervisor")
        self.assertEqual(
            decision.display_projection.decision.expected_observation,
            "Aumentará el cociente score/umbral.",
        )
        self.assertEqual(
            decision.display_projection.decision.falsification_criterion,
            "El cociente volverá por debajo de uno.",
        )
        self.assertEqual(decision.display_projection.decision.evidence_handles, ("E01",))
        self.assertEqual(proposal.kind, "policy_proposal")
        self.assertEqual(proposal.display_projection.proposal.application_status, "not_applied")
        self.assertEqual(
            [item.analysis_status for item in decision.display_projection.assets],
            ["modeled", "telemetry_only", "telemetry_only", "telemetry_only"],
        )
        self.assertTrue(
            all(
                item.health_state is None
                for item in decision.display_projection.assets[1:]
            )
        )

    def test_tampered_beat_is_rejected_by_its_hash(self):
        beat = cinematic.build_monitoring_cinematic_timeline(
            campaign_id="nasa-p3-agentic-window-56h-v1",
            session_id="nasa-p3-agentic-window-56h-v1-session",
            ticks=_ticks(),
            reviews=_reviews(_ticks()),
            operational_verdict="passed",
            agentic_verdict="passed",
            evidence_verdict="passed",
        )[355]
        payload = beat.model_dump(mode="json")
        payload["display_projection"]["decision"]["hypothesis"] = "Texto alterado"

        with self.assertRaisesRegex(ValidationError, "beat_sha256"):
            cinematic.MonitoringCinematicBeat.model_validate(payload)

    def test_export_precondition_allows_adverse_terminal_result_but_not_planned(self):
        plan = cinematic.default_monitoring_cinematic_capture_plan(
            self.campaign_plan,
            capture_id="cinematic-terminal-test",
        )
        with tempfile.TemporaryDirectory() as tmp:
            registration = cinematic.preregister_monitoring_cinematic_capture(
                plan,
                output_root=tmp,
                registered_at=datetime(2026, 8, 18, 9, 0, tzinfo=UTC),
            )
        adverse_result = SimpleNamespace(
            started_at=datetime(2026, 8, 18, 10, 0, tzinfo=UTC),
            final_state=SimpleNamespace(status="failed", current_revision=689),
        )
        adverse = SimpleNamespace(
            plan=self.campaign_plan,
            state=SimpleNamespace(status="failed"),
            result=adverse_result,
            publication=SimpleNamespace(result_ref="result.json"),
        )
        cinematic._validate_export_preconditions(plan, registration, adverse)

        planned = SimpleNamespace(
            plan=self.campaign_plan,
            state=SimpleNamespace(status="planned"),
            result=None,
            publication=SimpleNamespace(result_ref=None),
        )
        with self.assertRaisesRegex(ValueError, "published campaign result"):
            cinematic._validate_export_preconditions(plan, registration, planned)

    def test_review_binding_rejects_a_different_valid_catalog_identity(self):
        review = SimpleNamespace(
            trigger_id="trigger-1",
            trigger_event_id="trigger-1:event:001",
            cutoff_cursor=353,
            proposal_id="proposal-1",
            proposal_sha256="a" * 64,
        )
        trigger = SimpleNamespace(origin_tick_id="session:tick:000353")
        result = SimpleNamespace(
            child_run_id="child-1",
            session_id="session",
            trigger_id="trigger-1",
            trigger_event_id="trigger-1:event:001",
            cutoff_cursor=353,
            origin_tick_id="session:tick:000353",
            request_id="request-1",
            request_sha256="b" * 64,
            causal_view_sha256="c" * 64,
        )
        proposal = SimpleNamespace(
            proposal_id="proposal-1",
            proposal_sha256="a" * 64,
            child_run_id="child-1",
            trigger_event_id="trigger-1:event:001",
            request_id="request-1",
            request_sha256="b" * 64,
            causal_view_sha256="c" * 64,
            evidence_catalog_sha256="d" * 64,
        )

        with self.assertRaisesRegex(ValueError, "do not bind"):
            cinematic._validate_review_artifact_binding(
                session_id="session",
                child_run_id="child-1",
                review=review,
                trigger=trigger,
                result=result,
                proposal=proposal,
                catalog=SimpleNamespace(catalog_sha256="e" * 64),
            )

    def test_read_only_session_load_confines_state_repair_to_a_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            scenario = _write_safe_scenario(base)
            sessions_root = base / "sessions"
            store = MonitoringReplayStore(
                sessions_root,
                scenarios={scenario.scenario_id: scenario},
            )
            initial = store.create_session(
                scenario_id=scenario.scenario_id,
                session_id="cinematic-read-only",
            )
            store.step(
                ReplayStepCommand(
                    command_id="step-001",
                    session_id="cinematic-read-only",
                    expected_revision=0,
                )
            )
            session_dir = sessions_root / "cinematic-read-only"
            state_path = session_dir / "state.json"
            state_path.write_text(
                json.dumps(initial.state.model_dump(mode="json")),
                encoding="utf-8",
            )
            before = {
                path.relative_to(session_dir).as_posix(): path.read_bytes()
                for path in session_dir.rglob("*")
                if path.is_file() and not path.is_symlink()
            }

            loaded = cinematic._load_monitoring_session_read_only(
                sessions_root,
                session_id="cinematic-read-only",
                scenarios={scenario.scenario_id: scenario},
            )
            after = {
                path.relative_to(session_dir).as_posix(): path.read_bytes()
                for path in session_dir.rglob("*")
                if path.is_file() and not path.is_symlink()
            }

        self.assertEqual(loaded.state.revision, 1)
        self.assertEqual(loaded.state.execution_cursor, 0)
        self.assertEqual(before, after)


def _sha(label: str) -> str:
    return hashlib.sha256(label.encode("utf-8")).hexdigest()


def _assets(cursor: int):
    return (
        cinematic.MonitoringCinematicAssetProjection(
            asset_id="bearing_1",
            asset_label="Rodamiento 1",
            channel_id="channel_1",
            analysis_status="modeled",
            analysis_label="Estado algorítmico",
            signal_rms=0.1 + cursor / 100000,
            signal_peak_abs=0.5,
            health_index=75.0,
            risk_index=25.0,
            health_state="watch",
            health_state_label="Vigilancia",
            score=0.2,
            threshold=0.25,
            score_ratio=0.8,
            gap_detected=False,
        ),
        *(
            cinematic.MonitoringCinematicAssetProjection(
                asset_id=f"bearing_{index}",
                asset_label=f"Rodamiento {index}",
                channel_id=f"channel_{index}",
                analysis_status="telemetry_only",
                analysis_label="Solo telemetría · sin diagnóstico",
                signal_rms=0.05 + index / 100,
                signal_peak_abs=0.4 + index / 100,
                gap_detected=False,
            )
            for index in range(2, 5)
        ),
    )


def _ticks():
    start = datetime(2004, 2, 14, 12, 0, 39)
    committed = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
    return tuple(
        cinematic.MonitoringCinematicTickMaterial(
            cursor=cursor,
            source_time=start + timedelta(minutes=10 * cursor),
            wall_time=committed + timedelta(seconds=cursor),
            tick_id=f"session:tick:{cursor:06d}",
            commit_sha256=_sha(f"commit-{cursor}"),
            assets=_assets(cursor),
        )
        for cursor in range(689)
    )


def _reviews(ticks):
    contexts = (
        (1, 353, "state_transition", "health_state_escalation", 353),
        (2, 498, "persistent_alert", "persistent_confirmation", 496),
        (3, 499, "state_transition", "health_state_escalation", 499),
        (4, 688, "session_close", "session_completed", 688),
    )
    wall = datetime(2026, 8, 18, 11, 0, tzinfo=UTC)
    reviews = []
    for ordinal, cursor, trigger_type, reason, condition_start in contexts:
        child = f"child-{ordinal}"
        decisions = tuple(
            cinematic.MonitoringCinematicDecisionMaterial(
                event_id=f"{child}:runtime:{index:04d}",
                event_sequence=index + 1,
                decision_id=f"{child}:{role}:001",
                decision_sha256=_sha(f"decision-{ordinal}-{role}"),
                wall_time=wall + timedelta(minutes=ordinal, seconds=index),
                projection=cinematic.MonitoringCinematicDecisionProjection(
                    agent_name=role,
                    role_label=role.replace("_", " ").title(),
                    hypothesis=f"Hipótesis {role} para el trigger {ordinal}.",
                    expected_observation="Aumentará el cociente score/umbral.",
                    falsification_criterion="El cociente volverá por debajo de uno.",
                    recommended_action="maintain_policy",
                    action_label="Mantener observación",
                    confidence=0.8,
                    evidence_handles=(f"E{index:02d}",),
                    generation_origin="llm",
                    generation_validation_status="validated",
                ),
            )
            for index, role in enumerate(MONITORING_REVIEW_ROLES, start=1)
        )
        reviews.append(
            cinematic.MonitoringCinematicReviewMaterial(
                ordinal=ordinal,
                cursor=cursor,
                source_time=ticks[cursor].source_time,
                tick_id=ticks[cursor].tick_id,
                trigger_id=f"trigger-{ordinal}",
                trigger_event_id=f"trigger-{ordinal}:event:001",
                trigger_wall_time=wall + timedelta(minutes=ordinal),
                child_run_id=child,
                trigger=cinematic.MonitoringCinematicTriggerProjection(
                    ordinal=ordinal,
                    trigger_type=trigger_type,
                    trigger_type_label="Cambio visible",
                    reason_code=reason,
                    summary="El motor determinista abre una revisión causal.",
                    condition_start_cursor=condition_start,
                    cutoff_cursor=cursor,
                ),
                decisions=decisions,
                proposal=cinematic.MonitoringCinematicProposalMaterial(
                    event_id=f"{child}:runtime:0009",
                    event_sequence=9,
                    proposal_id=f"proposal-{ordinal}",
                    proposal_sha256=_sha(f"proposal-{ordinal}"),
                    wall_time=wall + timedelta(minutes=ordinal, seconds=9),
                    projection=cinematic.MonitoringCinematicProposalProjection(
                        status="advisory_not_applied",
                        agreement_status="unanimous",
                        agreement_label="unanimidad",
                        application_status="not_applied",
                        aggregate_action="maintain_policy",
                        action_counts={"maintain_policy": 7},
                        human_review_recommended=False,
                    ),
                ),
            )
        )
    return tuple(reviews)


if __name__ == "__main__":
    unittest.main()
