from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from codigo.app.services.monitoring_evidence_campaign import (
    MonitoringEvidenceCampaignPlan,
    default_monitoring_evidence_campaign_plan,
    finalize_monitoring_evidence_campaign,
    load_published_monitoring_evidence_campaign,
    preregister_monitoring_evidence_campaign_plan,
    publish_monitoring_evidence_campaign,
    start_monitoring_evidence_campaign_state,
    update_monitoring_evidence_campaign_state,
    write_monitoring_evidence_campaign_artifacts,
)
from codigo.app.services.monitoring_review_reliability import (
    default_monitoring_review_reliability_plan,
)
from codigo.tests.test_monitoring_review_reliability import (
    _complete_observations,
)


class MonitoringEvidenceCampaignTests(unittest.TestCase):
    def test_plan_freezes_two_day_agentic_window_without_cutting_preroll(self):
        plan = default_monitoring_evidence_campaign_plan(
            campaign_id="campaign-plan-test",
            speed_multiplier=120.0,
            heartbeat_interval_seconds=2.0,
        )

        self.assertEqual(plan.pre_roll_tick_count, 353)
        self.assertEqual(
            (plan.agentic_window_start_cursor, plan.agentic_window_end_cursor),
            (353, 688),
        )
        self.assertEqual(plan.agentic_window_tick_count, 336)
        self.assertEqual(plan.agentic_window_source_duration_seconds, 201000)
        self.assertEqual(plan.step_interval_seconds, 5.0)
        self.assertEqual(len(plan.expected_contexts), 4)
        self.assertEqual(plan.expected_decision_count, 28)
        for critical_source in (
            "codigo/app/services/monitoring_replay.py",
            "codigo/app/services/monitoring_trigger_engine.py",
            "codigo/app/services/agent_reliability.py",
            "codigo/app/graph/pipeline.py",
        ):
            self.assertIn(critical_source, plan.source_sha256s)
        self.assertEqual(
            plan.plan_sha256,
            MonitoringEvidenceCampaignPlan.canonical_sha256(plan),
        )

        payload = plan.model_dump(mode="python", exclude={"plan_sha256"})
        payload["heartbeat_interval_seconds"] = 6.0
        payload["plan_sha256"] = MonitoringEvidenceCampaignPlan.canonical_sha256(
            payload
        )
        with self.assertRaisesRegex(ValidationError, "heartbeat interval"):
            MonitoringEvidenceCampaignPlan.model_validate(payload)

    def test_state_tracks_preroll_trigger_and_terminal_review(self):
        plan = default_monitoring_evidence_campaign_plan(
            campaign_id="campaign-state-test"
        )
        now = datetime(2026, 8, 18, 10, 0, tzinfo=UTC)
        state = start_monitoring_evidence_campaign_state(plan, started_at=now)
        state = update_monitoring_evidence_campaign_state(
            plan,
            state,
            {"kind": "campaign_heartbeat", "revision": 300},
            recorded_at=now + timedelta(seconds=1),
        )
        self.assertEqual(state.phase, "pre_roll")
        state = update_monitoring_evidence_campaign_state(
            plan,
            state,
            {
                "kind": "review_dispatching",
                "cutoff_cursor": 353,
                "trigger_id": "trigger-353",
                "child_run_id": "child-353",
            },
            recorded_at=now + timedelta(seconds=2),
        )
        self.assertEqual(state.phase, "agentic_window")
        self.assertEqual(state.reviews[0].lifecycle, "running")
        state = update_monitoring_evidence_campaign_state(
            plan,
            state,
            {
                "kind": "review_terminal",
                "cutoff_cursor": 353,
                "trigger_id": "trigger-353",
                "child_run_id": "child-353",
                "child_lifecycle": "resolved",
                "decision_count": 7,
                "llm_origin_count": 7,
                "fallback_count": 0,
                "proposal_status": "advisory_not_applied",
                "proposal_application_status": "not_applied",
            },
            recorded_at=now + timedelta(seconds=3),
        )
        self.assertEqual(state.terminal_child_run_count, 1)
        self.assertEqual(state.observed_decision_count, 7)
        self.assertEqual(state.policy_proposal_count, 1)

    def test_complete_cycle_separates_operational_and_agentic_verdicts(self):
        plan = default_monitoring_evidence_campaign_plan(
            campaign_id="campaign-final-test"
        )
        reviews = [_review(context) for context in plan.expected_contexts]
        cycle = {
            "session_id": plan.session_id,
            "session_status": "completed",
            "final_revision": 689,
            "runtime_elapsed_seconds": 123.0,
            "total_trigger_event_count": 14,
            "suppressed_trigger_count": 10,
            "variable_run_slots_reserved": 3,
            "steps_applied": 689,
            "pacing_wait_count": 688,
            "pacing_elapsed_seconds": 120.0,
            "heartbeat_count": 1376,
            "memory_mode": "off",
            "policy_application_status": "not_applied",
            "reviews": reviews,
        }
        with tempfile.TemporaryDirectory() as tmp:
            preregistration = preregister_monitoring_evidence_campaign_plan(
                plan,
                output_root=tmp,
            )
            started = preregistration.registered_at + timedelta(seconds=1)
            state = start_monitoring_evidence_campaign_state(plan, started_at=started)
            observations = _campaign_observations(plan, reviews)
            for offset, review in enumerate(reviews, start=1):
                state = update_monitoring_evidence_campaign_state(
                    plan,
                    state,
                    {"kind": "review_terminal", **review},
                    recorded_at=started + timedelta(seconds=offset),
                )
            publish_monitoring_evidence_campaign(
                plan,
                state,
                preregistration=preregistration,
                output_root=tmp,
            )

            result = finalize_monitoring_evidence_campaign(
                plan,
                state,
                preregistration=preregistration,
                cycle=cycle,
                observations=observations,
                completed_at=started + timedelta(minutes=3),
            )
            completed_publication = publish_monitoring_evidence_campaign(
                plan,
                result.final_state,
                preregistration=preregistration,
                result=result,
                output_root=tmp,
            )
            preserved_publication = publish_monitoring_evidence_campaign(
                plan,
                start_monitoring_evidence_campaign_state(plan),
                preregistration=preregistration,
                output_root=tmp,
            )
            self.assertEqual(
                preserved_publication.publication_sha256,
                completed_publication.publication_sha256,
            )
            self.assertIsNotNone(
                load_published_monitoring_evidence_campaign(
                    output_root=tmp,
                    campaign_id=plan.campaign_id,
                ).result
            )

        self.assertEqual(result.operational_verdict, "passed")
        self.assertEqual(result.agentic_verdict, "passed")
        self.assertEqual(result.evidence_verdict, "passed")
        self.assertEqual(result.first_pass_count, 28)
        self.assertEqual(len(result.physical_attempts), 28)
        self.assertEqual(result.final_state.policy_proposal_count, 4)
        self.assertEqual(result.total_trigger_event_count, 14)

        blocked_cycle = dict(cycle)
        blocked_reviews = [dict(item) for item in reviews]
        blocked_reviews[0]["child_lifecycle"] = "failed"
        blocked_reviews[0]["fallback_count"] = 1
        blocked_cycle["reviews"] = blocked_reviews
        blocked = finalize_monitoring_evidence_campaign(
            plan,
            state,
            preregistration=preregistration,
            cycle=blocked_cycle,
            observations=observations,
            completed_at=started + timedelta(minutes=4),
        )
        self.assertEqual(blocked.operational_verdict, "passed")
        self.assertEqual(blocked.agentic_verdict, "blocked")
        self.assertEqual(blocked.evidence_verdict, "blocked")

    def test_preregistration_publication_roundtrip_and_tamper_rejection(self):
        plan = default_monitoring_evidence_campaign_plan(
            campaign_id="campaign-publication-test"
        )
        state = start_monitoring_evidence_campaign_state(plan)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            registration = preregister_monitoring_evidence_campaign_plan(
                plan, output_root=root
            )
            publication = publish_monitoring_evidence_campaign(
                plan,
                state,
                preregistration=registration,
                output_root=root,
            )
            loaded = load_published_monitoring_evidence_campaign(
                output_root=root
            )
            self.assertEqual(loaded.plan, plan)
            self.assertEqual(loaded.preregistration, registration)
            self.assertEqual(loaded.state, state)
            self.assertIsNone(loaded.result)
            self.assertEqual(publication.plan_sha256, registration.plan_sha256)

            state_path = Path(publication.state_ref)
            payload = json.loads(state_path.read_text(encoding="utf-8"))
            payload["current_revision"] = 10
            state_path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises((ValidationError, ValueError)):
                load_published_monitoring_evidence_campaign(output_root=root)

    def test_publication_never_rolls_back_visible_progress(self):
        plan = default_monitoring_evidence_campaign_plan(
            campaign_id="campaign-monotonic-publication-test"
        )
        with tempfile.TemporaryDirectory() as tmp:
            registration = preregister_monitoring_evidence_campaign_plan(
                plan,
                output_root=tmp,
            )
            planned = start_monitoring_evidence_campaign_state(plan)
            publish_monitoring_evidence_campaign(
                plan,
                planned,
                preregistration=registration,
                output_root=tmp,
            )
            running = update_monitoring_evidence_campaign_state(
                plan,
                planned,
                {"kind": "campaign_heartbeat", "revision": 300},
                recorded_at=registration.registered_at + timedelta(seconds=2),
            )
            current = publish_monitoring_evidence_campaign(
                plan,
                running,
                preregistration=registration,
                output_root=tmp,
            )

            replayed_plan_only = start_monitoring_evidence_campaign_state(plan)
            preserved = publish_monitoring_evidence_campaign(
                plan,
                replayed_plan_only,
                preregistration=registration,
                output_root=tmp,
            )

            self.assertEqual(preserved.publication_sha256, current.publication_sha256)
            loaded = load_published_monitoring_evidence_campaign(output_root=tmp)
            self.assertEqual(loaded.state.current_revision, 300)
            self.assertEqual(loaded.state.status, "running")

    def test_campaign_history_survives_another_global_publication(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan_a = default_monitoring_evidence_campaign_plan(
                campaign_id="campaign-history-a"
            )
            registration_a = preregister_monitoring_evidence_campaign_plan(
                plan_a,
                output_root=tmp,
            )
            planned_a = start_monitoring_evidence_campaign_state(plan_a)
            failed_a = update_monitoring_evidence_campaign_state(
                plan_a,
                planned_a,
                {"kind": "campaign_failed", "error": "preflight failed"},
            )
            publication_a = publish_monitoring_evidence_campaign(
                plan_a,
                failed_a,
                preregistration=registration_a,
                output_root=tmp,
            )

            plan_b = default_monitoring_evidence_campaign_plan(
                campaign_id="campaign-history-b"
            )
            registration_b = preregister_monitoring_evidence_campaign_plan(
                plan_b,
                output_root=tmp,
            )
            publish_monitoring_evidence_campaign(
                plan_b,
                start_monitoring_evidence_campaign_state(plan_b),
                preregistration=registration_b,
                output_root=tmp,
            )

            preserved_a = publish_monitoring_evidence_campaign(
                plan_a,
                start_monitoring_evidence_campaign_state(plan_a),
                preregistration=registration_a,
                output_root=tmp,
            )
            self.assertEqual(
                preserved_a.publication_sha256,
                publication_a.publication_sha256,
            )
            loaded_a = load_published_monitoring_evidence_campaign(
                output_root=tmp,
                campaign_id=plan_a.campaign_id,
            )
            self.assertEqual(loaded_a.state.status, "failed")
            current = load_published_monitoring_evidence_campaign(output_root=tmp)
            self.assertEqual(current.plan.campaign_id, plan_b.campaign_id)

    def test_later_stale_state_cannot_erase_review_progress(self):
        plan = default_monitoring_evidence_campaign_plan(
            campaign_id="campaign-stale-state-test"
        )
        with tempfile.TemporaryDirectory() as tmp:
            registration = preregister_monitoring_evidence_campaign_plan(
                plan,
                output_root=tmp,
            )
            base = start_monitoring_evidence_campaign_state(plan)
            rich = update_monitoring_evidence_campaign_state(
                plan,
                base,
                {
                    "kind": "review_terminal",
                    "revision": 354,
                    "cutoff_cursor": 353,
                    "trigger_id": "trigger-353",
                    "trigger_event_id": "trigger-353:event:001",
                    "child_run_id": "child-353",
                    "child_lifecycle": "resolved",
                    "decision_count": 7,
                    "llm_origin_count": 7,
                    "proposal_id": "proposal-353",
                    "proposal_sha256": "a" * 64,
                    "proposal_status": "advisory_not_applied",
                    "proposal_application_status": "not_applied",
                },
                recorded_at=registration.registered_at + timedelta(seconds=1),
            )
            current = publish_monitoring_evidence_campaign(
                plan,
                rich,
                preregistration=registration,
                output_root=tmp,
            )
            stale = update_monitoring_evidence_campaign_state(
                plan,
                base,
                {"kind": "campaign_heartbeat", "revision": 355},
                recorded_at=registration.registered_at + timedelta(seconds=2),
            )
            preserved = publish_monitoring_evidence_campaign(
                plan,
                stale,
                preregistration=registration,
                output_root=tmp,
            )
            self.assertEqual(preserved.publication_sha256, current.publication_sha256)
            failed_stale = update_monitoring_evidence_campaign_state(
                plan,
                base,
                {
                    "kind": "campaign_failed",
                    "revision": 356,
                    "error": "stale failure",
                },
                recorded_at=registration.registered_at + timedelta(seconds=3),
            )
            still_preserved = publish_monitoring_evidence_campaign(
                plan,
                failed_stale,
                preregistration=registration,
                output_root=tmp,
            )
            self.assertEqual(
                still_preserved.publication_sha256,
                current.publication_sha256,
            )
            loaded = load_published_monitoring_evidence_campaign(
                output_root=tmp,
                campaign_id=plan.campaign_id,
            )
            self.assertEqual(loaded.state.terminal_child_run_count, 1)
            self.assertEqual(loaded.state.observed_decision_count, 7)

    def test_observation_matrix_cannot_pass_with_duplicates_or_wrong_session(self):
        plan = default_monitoring_evidence_campaign_plan(
            campaign_id="campaign-observation-matrix-test"
        )
        reviews = [_review(context) for context in plan.expected_contexts]
        cycle = {
            "session_id": plan.session_id,
            "session_status": "completed",
            "final_revision": 689,
            "total_trigger_event_count": 14,
            "suppressed_trigger_count": 10,
            "variable_run_slots_reserved": 3,
            "memory_mode": "off",
            "policy_application_status": "not_applied",
            "reviews": reviews,
        }
        with tempfile.TemporaryDirectory() as tmp:
            registration = preregister_monitoring_evidence_campaign_plan(
                plan,
                output_root=tmp,
            )
            state = start_monitoring_evidence_campaign_state(
                plan,
                started_at=registration.registered_at + timedelta(seconds=1),
            )
            observations = list(_campaign_observations(plan, reviews))
            observations[-1] = observations[0]
            duplicate_result = finalize_monitoring_evidence_campaign(
                plan,
                state,
                preregistration=registration,
                cycle=cycle,
                observations=observations,
            )
            self.assertEqual(duplicate_result.agentic_verdict, "blocked")
            self.assertIn(
                "duplicate_context_role_observation",
                duplicate_result.blockers,
            )
            self.assertIn(
                "duplicate_physical_attempt_ownership",
                duplicate_result.blockers,
            )

            observations = list(_campaign_observations(plan, reviews))
            payload = observations[0].model_dump(mode="python")
            payload["session_id"] = "another-session"
            observations[0] = type(observations[0]).model_validate(payload)
            wrong_session = finalize_monitoring_evidence_campaign(
                plan,
                state,
                preregistration=registration,
                cycle=cycle,
                observations=observations,
            )
            self.assertEqual(wrong_session.agentic_verdict, "blocked")
            self.assertIn("observation_binding_mismatch", wrong_session.blockers)

            missing_physical = finalize_monitoring_evidence_campaign(
                plan,
                state,
                preregistration=registration,
                cycle=cycle,
                observations=_campaign_observations(plan, reviews),
                physical_attempts=(),
            )
            self.assertEqual(missing_physical.agentic_verdict, "blocked")
            self.assertIn(
                "physical_attempt_ledger_mismatch",
                missing_physical.blockers,
            )


def _review(context) -> dict:
    trigger_sequence = {353: 1, 498: 11, 499: 12, 688: 14}[
        context.cutoff_cursor
    ]
    return {
        "trigger_id": f"trigger-{context.cutoff_cursor}",
        "trigger_event_id": f"trigger-{context.cutoff_cursor}:event:001",
        "trigger_sequence": trigger_sequence,
        "trigger_type": context.trigger_type,
        "reason_code": context.reason_code,
        "condition_start_cursor": context.condition_start_cursor,
        "cutoff_cursor": context.cutoff_cursor,
        "child_run_id": f"child-{context.cutoff_cursor}",
        "child_lifecycle": "resolved",
        "job_status": "completed",
        "decision_count": 7,
        "llm_origin_count": 7,
        "repaired_count": 0,
        "fallback_count": 0,
        "proposal_id": f"proposal-{context.cutoff_cursor}",
        "proposal_sha256": f"{context.ordinal}" * 64,
        "proposal_status": "advisory_not_applied",
        "proposal_agreement_status": "unanimous",
        "proposal_application_status": "not_applied",
        "error": None,
        "resumed": False,
        "run_dir": f"codigo/reports/runs/child-{context.cutoff_cursor}",
    }


def _campaign_observations(plan, reviews):
    reliability_plan = default_monitoring_review_reliability_plan(
        plan_id=plan.campaign_id
    )
    review_by_context = {
        context.context_id: review
        for context, review in zip(plan.expected_contexts, reviews, strict=True)
    }
    observations = []
    for item in _complete_observations(reliability_plan)[:28]:
        review = review_by_context[item.context_id]
        child_run_id = review["child_run_id"]
        payload = item.model_dump(mode="python")
        payload.update(
            {
                "session_id": plan.session_id,
                "trigger_id": review["trigger_id"],
                "trigger_event_id": review["trigger_event_id"],
                "child_run_id": child_run_id,
                "run_ref": f"codigo/reports/runs/{child_run_id}",
                "decision_id": f"{child_run_id}:{item.agent_name}:001",
            }
        )
        observations.append(type(item).model_validate(payload))
    return tuple(observations)


if __name__ == "__main__":
    unittest.main()
