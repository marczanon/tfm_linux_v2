import unittest
from datetime import UTC, datetime, timedelta

from codigo.app.schemas.monitoring_replay import (
    ActivePolicyRefs,
    AgentActivationPolicy,
    AgentActivationTriggerRule,
    MonitoringFrame,
    ReplayAssetCheckpoint,
    ReplayTick,
)
from codigo.app.services.monitoring_trigger_engine import (
    evaluate_monitoring_triggers,
    initial_activation_checkpoint,
)


SESSION_ID = "nasa-rft-trigger-test"
POLICY_SHA256 = "a" * 64
SOURCE_START = datetime(2004, 2, 12, 10, 32, 39)
RUNTIME_START = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def make_rule(
    trigger_type,
    *,
    priority=50,
    cooldown_source_seconds=0.0,
    coalescing_group=None,
    state_transition_targets=(),
):
    fixed_trigger = trigger_type in {"preflight", "session_close", "manual"}
    if trigger_type == "persistent_alert":
        rearm_policy = "after_recovery"
    elif trigger_type in {"preflight", "session_close"}:
        rearm_policy = "once_per_session"
    elif trigger_type == "manual":
        rearm_policy = "manual"
    else:
        rearm_policy = "after_cooldown"
    return AgentActivationTriggerRule(
        trigger_type=trigger_type,
        priority=priority,
        cooldown_source_seconds=cooldown_source_seconds,
        coalescing_group=coalescing_group,
        rearm_policy=rearm_policy,
        state_transition_targets=state_transition_targets,
        requested_roles=("supervisor", "evaluator"),
        counts_toward_variable_budget=not fixed_trigger,
    )


def make_p3_policy(
    *rules,
    max_variable_child_runs=3,
    periodic_cursors=(),
    precedence=None,
    alert_recovery_persistence_ticks=1,
):
    return AgentActivationPolicy(
        policy_version="activation-p3-test-v1",
        policy_sha256=POLICY_SHA256,
        policy_kind="P3",
        max_variable_child_runs=max_variable_child_runs,
        periodic_cursors=periodic_cursors,
        alert_entry_persistence_ticks=3,
        alert_recovery_persistence_ticks=alert_recovery_persistence_ticks,
        trigger_rules=rules,
        precedence=(
            tuple(rule.trigger_type for rule in rules)
            if precedence is None
            else precedence
        ),
    )


def make_tick(
    cursor,
    health_state,
    *,
    segment_id=0,
    gap_detected=False,
):
    tick_id = f"tick-{cursor:03d}"
    source_time = SOURCE_START + timedelta(seconds=60 * cursor)
    score_by_state = {
        "nominal": 0.20,
        "watch": 0.45,
        "warning": 0.80,
        "critical": 0.95,
    }
    health_by_state = {
        "nominal": 92.0,
        "watch": 72.0,
        "warning": 48.0,
        "critical": 18.0,
    }
    score = score_by_state[health_state]
    frame = MonitoringFrame(
        frame_id=f"{tick_id}:bearing-1:channel-1",
        tick_id=tick_id,
        asset_id="bearing_1",
        channel_id="channel_1",
        interval_seconds=600.0 if gap_detected else 60.0,
        gap_detected=gap_detected,
        segment_id=segment_id,
        analysis_status="modeled",
        score=score,
        threshold=0.60,
        predicted_anomaly=score > 0.60,
        score_ratio=score / 0.60,
        health_index=health_by_state[health_state],
        risk_index=100.0 - health_by_state[health_state],
        health_state=health_state,
        scoring_version="scoring-test-v1",
        evidence_refs=(f"evidence:{tick_id}:channel-1",),
    )
    return ReplayTick(
        tick_id=tick_id,
        session_id=SESSION_ID,
        cursor=cursor,
        sequence=cursor + 1,
        snapshot_id=f"snapshot-{cursor:03d}",
        source_time=source_time,
        input_record_hash=f"{cursor % 16:x}" * 64,
        active_policy_refs=ActivePolicyRefs(
            scoring_version="scoring-test-v1",
            activation_version="activation-p3-test-v1",
        ),
        frames=(frame,),
        committed_at=RUNTIME_START + timedelta(seconds=cursor),
    )


def make_asset_checkpoint(
    tick,
    health_state,
    *,
    alert_count,
    recovery_count,
    segment_id=0,
):
    health_value = tick.frames[0].health_index
    return ReplayAssetCheckpoint(
        asset_id="bearing_1",
        analysis_status="modeled",
        segment_id=segment_id,
        alert_persistence_count=alert_count,
        recovery_persistence_count=recovery_count,
        raw_health_history=(health_value,),
        smoothed_health_history=(health_value,),
        last_source_time=tick.source_time,
        last_frame_id=tick.frames[0].frame_id,
        last_health_state=health_state,
        scoring_version="scoring-test-v1",
    )


class TriggerHarness:
    def __init__(self, policy):
        self.policy = policy
        self.checkpoint = initial_activation_checkpoint(policy)
        self.prior_events = ()
        self.previous_asset_checkpoint = ReplayAssetCheckpoint(
            asset_id="bearing_1",
            analysis_status="modeled",
            scoring_version="scoring-test-v1",
        )
        self.cursor = 0

    def step(
        self,
        health_state,
        *,
        alert_count,
        recovery_count,
        segment_id=0,
        gap_detected=False,
        session_completed=False,
    ):
        tick = make_tick(
            self.cursor,
            health_state,
            segment_id=segment_id,
            gap_detected=gap_detected,
        )
        current = make_asset_checkpoint(
            tick,
            health_state,
            alert_count=alert_count,
            recovery_count=recovery_count,
            segment_id=segment_id,
        )
        result = evaluate_monitoring_triggers(
            session_id=SESSION_ID,
            tick=tick,
            previous_asset_checkpoints=(self.previous_asset_checkpoint,),
            current_asset_checkpoints=(current,),
            prior_events=self.prior_events,
            policy=self.policy,
            checkpoint=self.checkpoint,
            session_completed=session_completed,
        )
        self.prior_events += result.events
        self.previous_asset_checkpoint = current
        self.checkpoint = result.checkpoint
        self.cursor += 1
        return tick, result


class MonitoringTriggerEngineTests(unittest.TestCase):
    def test_k3_separates_alert_start_from_confirmation(self):
        policy = make_p3_policy(
            make_rule(
                "persistent_alert",
                priority=90,
                coalescing_group="health_episode",
            ),
            max_variable_child_runs=1,
        )
        harness = TriggerHarness(policy)

        first_tick, first = harness.step(
            "warning",
            alert_count=1,
            recovery_count=0,
        )
        _, second = harness.step(
            "warning",
            alert_count=2,
            recovery_count=0,
        )
        confirmation_tick, third = harness.step(
            "warning",
            alert_count=3,
            recovery_count=0,
        )

        self.assertEqual(first.events, ())
        self.assertEqual(second.events, ())
        self.assertEqual(len(third.events), 1)
        event = third.events[0]
        self.assertEqual(event.trigger_type, "persistent_alert")
        self.assertEqual(event.lifecycle_status, "emitted")
        self.assertEqual(event.reason_code, "persistent_confirmation")
        self.assertEqual(event.condition_start_cursor, 0)
        self.assertEqual(event.cutoff_cursor, 2)
        self.assertEqual(event.snapshot_start_id, first_tick.snapshot_id)
        self.assertEqual(event.snapshot_end_id, confirmation_tick.snapshot_id)
        self.assertEqual(event.budget_reservation_index, 1)
        self.assertFalse(third.checkpoint.persistent_alert_armed)

    def test_recovery_rearms_and_a_new_k3_episode_gets_a_new_slot(self):
        policy = make_p3_policy(
            make_rule("persistent_alert", coalescing_group="health_episode"),
            max_variable_child_runs=2,
        )
        harness = TriggerHarness(policy)
        for count in (1, 2):
            harness.step("warning", alert_count=count, recovery_count=0)
        _, first_confirmation = harness.step(
            "warning",
            alert_count=3,
            recovery_count=0,
        )
        first_event = first_confirmation.events[0]

        _, recovered = harness.step(
            "watch",
            alert_count=0,
            recovery_count=1,
        )
        self.assertEqual(recovered.events, ())
        self.assertTrue(recovered.checkpoint.persistent_alert_armed)
        self.assertIsNone(recovered.checkpoint.alert_episode_id)

        for count in (1, 2):
            harness.step("warning", alert_count=count, recovery_count=0)
        _, second_confirmation = harness.step(
            "warning",
            alert_count=3,
            recovery_count=0,
        )
        second_event = second_confirmation.events[0]

        self.assertEqual(second_event.lifecycle_status, "emitted")
        self.assertEqual(second_event.budget_reservation_index, 2)
        self.assertNotEqual(second_event.episode_id, first_event.episode_id)
        self.assertEqual(
            second_confirmation.checkpoint.variable_run_slots_reserved,
            2,
        )

    def test_critical_transition_then_persistence_uses_one_slot_per_episode(self):
        policy = make_p3_policy(
            make_rule(
                "state_transition",
                priority=100,
                coalescing_group="health_episode",
                state_transition_targets=("critical",),
            ),
            make_rule(
                "persistent_alert",
                priority=90,
                coalescing_group="health_episode",
            ),
            max_variable_child_runs=2,
            precedence=("state_transition", "persistent_alert"),
        )
        harness = TriggerHarness(policy)
        harness.step("watch", alert_count=0, recovery_count=1)
        _, critical = harness.step(
            "critical",
            alert_count=1,
            recovery_count=0,
        )
        critical_event = critical.events[0]
        harness.step("critical", alert_count=2, recovery_count=0)
        _, persistent = harness.step(
            "critical",
            alert_count=3,
            recovery_count=0,
        )

        self.assertEqual(critical_event.trigger_type, "state_transition")
        self.assertEqual(critical_event.lifecycle_status, "emitted")
        self.assertEqual(critical_event.budget_reservation_index, 1)
        self.assertEqual(len(persistent.events), 1)
        persistence_event = persistent.events[0]
        self.assertEqual(persistence_event.trigger_type, "persistent_alert")
        self.assertEqual(persistence_event.lifecycle_status, "suppressed")
        self.assertEqual(
            persistence_event.suppression_reason,
            "episode_already_covered",
        )
        self.assertEqual(
            persistence_event.suppressed_by_trigger_id,
            critical_event.trigger_id,
        )
        self.assertEqual(persistence_event.episode_id, critical_event.episode_id)
        self.assertEqual(persistent.checkpoint.variable_run_slots_reserved, 1)

    def test_one_recovery_tick_does_not_repeat_an_r2_critical_episode(self):
        policy = make_p3_policy(
            make_rule(
                "state_transition",
                priority=100,
                coalescing_group="health_episode",
                state_transition_targets=("critical",),
            ),
            make_rule(
                "persistent_alert",
                priority=90,
                coalescing_group="health_episode",
            ),
            max_variable_child_runs=2,
            precedence=("state_transition", "persistent_alert"),
            alert_recovery_persistence_ticks=2,
        )
        harness = TriggerHarness(policy)
        harness.step("watch", alert_count=0, recovery_count=2)
        _, critical = harness.step(
            "critical",
            alert_count=1,
            recovery_count=0,
        )
        critical_event = critical.events[0]
        harness.step("critical", alert_count=2, recovery_count=0)
        _, first_persistence = harness.step(
            "critical",
            alert_count=3,
            recovery_count=0,
        )
        self.assertEqual(
            first_persistence.events[0].suppression_reason,
            "episode_already_covered",
        )

        _, partial_recovery = harness.step(
            "watch",
            alert_count=0,
            recovery_count=1,
        )
        self.assertFalse(partial_recovery.checkpoint.persistent_alert_armed)
        self.assertEqual(
            partial_recovery.checkpoint.alert_episode_id,
            critical_event.episode_id,
        )
        self.assertEqual(
            partial_recovery.checkpoint.alert_episode_handled_trigger_id,
            critical_event.trigger_id,
        )

        harness.step("warning", alert_count=1, recovery_count=0)
        harness.step("warning", alert_count=2, recovery_count=0)
        _, reentry_confirmation = harness.step(
            "warning",
            alert_count=3,
            recovery_count=0,
        )
        self.assertEqual(reentry_confirmation.events, ())
        self.assertEqual(
            reentry_confirmation.checkpoint.variable_run_slots_reserved,
            1,
        )

    def test_non_alert_cancels_an_unconfirmed_candidate_even_with_r2(self):
        policy = make_p3_policy(
            make_rule("persistent_alert", coalescing_group="health_episode"),
            max_variable_child_runs=1,
            alert_recovery_persistence_ticks=2,
        )
        harness = TriggerHarness(policy)
        harness.step("warning", alert_count=1, recovery_count=0)
        _, interrupted = harness.step(
            "watch",
            alert_count=0,
            recovery_count=1,
        )
        self.assertTrue(interrupted.checkpoint.persistent_alert_armed)
        self.assertIsNone(interrupted.checkpoint.alert_episode_id)

        first_new_tick, _ = harness.step(
            "warning",
            alert_count=1,
            recovery_count=0,
        )
        harness.step("warning", alert_count=2, recovery_count=0)
        confirmation_tick, confirmation = harness.step(
            "warning",
            alert_count=3,
            recovery_count=0,
        )

        self.assertEqual(len(confirmation.events), 1)
        self.assertEqual(
            confirmation.events[0].condition_start_cursor,
            first_new_tick.cursor,
        )
        self.assertEqual(
            confirmation.events[0].snapshot_end_id,
            confirmation_tick.snapshot_id,
        )

    def test_budget_suppression_is_decided_once_during_partial_recovery(self):
        policy = make_p3_policy(
            make_rule("continuity_gap", coalescing_group="continuity"),
            make_rule("persistent_alert", coalescing_group="health_episode"),
            max_variable_child_runs=1,
            precedence=("continuity_gap", "persistent_alert"),
            alert_recovery_persistence_ticks=2,
        )
        harness = TriggerHarness(policy)
        _, gap = harness.step(
            "nominal",
            alert_count=0,
            recovery_count=1,
            segment_id=1,
            gap_detected=True,
        )
        self.assertEqual(gap.events[0].budget_reservation_index, 1)
        for count in (1, 2):
            harness.step(
                "warning",
                alert_count=count,
                recovery_count=0,
                segment_id=1,
            )
        _, first_decision = harness.step(
            "warning",
            alert_count=3,
            recovery_count=0,
            segment_id=1,
        )
        self.assertEqual(first_decision.events[0].suppression_reason, "budget")
        self.assertIsNotNone(
            first_decision.checkpoint.alert_episode_persistence_trigger_id
        )

        harness.step(
            "watch",
            alert_count=0,
            recovery_count=1,
            segment_id=1,
        )
        for count in (1, 2):
            harness.step(
                "warning",
                alert_count=count,
                recovery_count=0,
                segment_id=1,
            )
        _, repeated_confirmation = harness.step(
            "warning",
            alert_count=3,
            recovery_count=0,
            segment_id=1,
        )
        self.assertEqual(repeated_confirmation.events, ())
        self.assertEqual(
            repeated_confirmation.checkpoint.variable_run_slots_reserved,
            1,
        )

    def test_gap_resets_the_candidate_streak_before_new_k3_confirmation(self):
        policy = make_p3_policy(
            make_rule("continuity_gap", coalescing_group="continuity"),
            make_rule("persistent_alert", coalescing_group="health_episode"),
            max_variable_child_runs=2,
            precedence=("continuity_gap", "persistent_alert"),
        )
        harness = TriggerHarness(policy)
        _, initial = harness.step(
            "warning",
            alert_count=1,
            recovery_count=0,
        )
        initial_episode_id = initial.checkpoint.alert_episode_id
        gap_tick, gap_result = harness.step(
            "warning",
            alert_count=1,
            recovery_count=0,
            segment_id=1,
            gap_detected=True,
        )

        self.assertEqual(len(gap_result.events), 1)
        self.assertEqual(gap_result.events[0].trigger_type, "continuity_gap")
        self.assertNotEqual(
            gap_result.checkpoint.alert_episode_id,
            initial_episode_id,
        )
        harness.step(
            "warning",
            alert_count=2,
            recovery_count=0,
            segment_id=1,
        )
        confirmation_tick, confirmed = harness.step(
            "warning",
            alert_count=3,
            recovery_count=0,
            segment_id=1,
        )
        persistence_event = confirmed.events[0]

        self.assertEqual(persistence_event.trigger_type, "persistent_alert")
        self.assertEqual(persistence_event.condition_start_cursor, 1)
        self.assertEqual(persistence_event.snapshot_start_id, gap_tick.snapshot_id)
        self.assertEqual(
            persistence_event.snapshot_end_id,
            confirmation_tick.snapshot_id,
        )

    def test_cooldown_uses_source_time_and_does_not_reserve_another_slot(self):
        policy = make_p3_policy(
            make_rule(
                "periodic_review",
                cooldown_source_seconds=120.0,
                coalescing_group="periodic",
            ),
            max_variable_child_runs=2,
            periodic_cursors=(0, 1),
        )
        harness = TriggerHarness(policy)
        _, first = harness.step("nominal", alert_count=0, recovery_count=1)
        _, second = harness.step("nominal", alert_count=0, recovery_count=1)

        first_event = first.events[0]
        second_event = second.events[0]
        self.assertEqual(first_event.lifecycle_status, "emitted")
        self.assertEqual(second_event.lifecycle_status, "suppressed")
        self.assertEqual(second_event.suppression_reason, "cooldown")
        self.assertEqual(
            second_event.suppressed_by_trigger_id,
            first_event.trigger_id,
        )
        self.assertIsNone(second_event.budget_reservation_index)
        self.assertEqual(second.checkpoint.variable_run_slots_reserved, 1)

    def test_precedence_coalesces_compatible_candidates_into_one_slot(self):
        policy = make_p3_policy(
            make_rule(
                "state_transition",
                priority=100,
                coalescing_group="review",
                state_transition_targets=("critical",),
            ),
            make_rule(
                "periodic_review",
                priority=40,
                coalescing_group="review",
            ),
            max_variable_child_runs=2,
            periodic_cursors=(1,),
            precedence=("state_transition", "periodic_review"),
        )
        harness = TriggerHarness(policy)
        harness.step("watch", alert_count=0, recovery_count=1)
        _, result = harness.step(
            "critical",
            alert_count=1,
            recovery_count=0,
        )

        self.assertEqual(len(result.events), 2)
        primary, coalesced = result.events
        self.assertEqual(primary.trigger_type, "state_transition")
        self.assertEqual(primary.lifecycle_status, "emitted")
        self.assertEqual(primary.budget_reservation_index, 1)
        self.assertEqual(coalesced.trigger_type, "periodic_review")
        self.assertEqual(coalesced.lifecycle_status, "coalesced")
        self.assertEqual(coalesced.coalesced_into_trigger_id, primary.trigger_id)
        self.assertIsNone(coalesced.budget_reservation_index)
        self.assertEqual(result.checkpoint.variable_run_slots_reserved, 1)

    def test_precedence_orders_ready_before_cooldown_suppression(self):
        policy = make_p3_policy(
            make_rule(
                "state_transition",
                priority=100,
                coalescing_group="state",
                state_transition_targets=("critical",),
            ),
            make_rule(
                "persistent_alert",
                priority=90,
                cooldown_source_seconds=1000.0,
                coalescing_group="persistent",
            ),
            max_variable_child_runs=3,
            precedence=("state_transition", "persistent_alert"),
        )
        harness = TriggerHarness(policy)
        for count in (1, 2, 3):
            harness.step("warning", alert_count=count, recovery_count=0)
        harness.step("watch", alert_count=0, recovery_count=1)
        harness.step("warning", alert_count=1, recovery_count=0)
        harness.step("warning", alert_count=2, recovery_count=0)
        _, collision = harness.step(
            "critical",
            alert_count=3,
            recovery_count=0,
        )

        self.assertEqual(
            [event.trigger_type for event in collision.events],
            ["state_transition", "persistent_alert"],
        )
        self.assertEqual(collision.events[0].lifecycle_status, "emitted")
        self.assertEqual(collision.events[1].lifecycle_status, "suppressed")
        self.assertEqual(collision.events[1].suppression_reason, "cooldown")
        self.assertLess(
            collision.events[0].sequence,
            collision.events[1].sequence,
        )

    def test_budget_suppresses_variable_event_but_not_session_close(self):
        policy = make_p3_policy(
            make_rule(
                "state_transition",
                priority=90,
                coalescing_group="health",
                state_transition_targets=("warning", "critical"),
            ),
            make_rule(
                "session_close",
                priority=10,
                coalescing_group="close",
            ),
            max_variable_child_runs=1,
            precedence=("state_transition", "session_close"),
        )
        harness = TriggerHarness(policy)
        harness.step("watch", alert_count=0, recovery_count=1)
        _, warning = harness.step(
            "warning",
            alert_count=1,
            recovery_count=0,
        )
        self.assertEqual(warning.events[0].budget_reservation_index, 1)

        _, completed = harness.step(
            "critical",
            alert_count=2,
            recovery_count=0,
            session_completed=True,
        )
        by_type = {event.trigger_type: event for event in completed.events}

        self.assertEqual(
            by_type["state_transition"].suppression_reason,
            "budget",
        )
        self.assertEqual(by_type["session_close"].lifecycle_status, "emitted")
        self.assertFalse(
            by_type["session_close"].counts_toward_variable_budget
        )
        self.assertIsNone(by_type["session_close"].budget_reservation_index)
        self.assertEqual(completed.checkpoint.variable_run_slots_reserved, 1)

    def test_p0_never_creates_events_or_advances_activation_state(self):
        policy = AgentActivationPolicy(
            policy_version="activation-p0-test-v1",
            policy_sha256=POLICY_SHA256,
            policy_kind="P0",
            max_variable_child_runs=0,
        )
        tick = make_tick(0, "critical")
        previous = ReplayAssetCheckpoint(
            asset_id="bearing_1",
            analysis_status="modeled",
            scoring_version="scoring-test-v1",
        )
        current = make_asset_checkpoint(
            tick,
            "critical",
            alert_count=3,
            recovery_count=0,
        )
        checkpoint = initial_activation_checkpoint(policy)

        result = evaluate_monitoring_triggers(
            session_id=SESSION_ID,
            tick=tick,
            previous_asset_checkpoints=(previous,),
            current_asset_checkpoints=(current,),
            prior_events=(),
            policy=policy,
            checkpoint=checkpoint,
            session_completed=True,
        )

        self.assertEqual(result.events, ())
        self.assertIs(result.checkpoint, checkpoint)
        self.assertEqual(result.checkpoint.variable_run_slots_reserved, 0)
        self.assertIsNone(result.checkpoint.last_evaluated_cursor)


if __name__ == "__main__":
    unittest.main()
