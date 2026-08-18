import unittest
from datetime import UTC, datetime

from pydantic import ValidationError

from codigo.app.schemas.agent_decisions import DecisionGenerationTrace
from codigo.app.schemas import ReplayTick as ExportedReplayTick
from codigo.app.schemas.monitoring_replay import (
    MONITORING_REVIEW_CAPABILITIES,
    MONITORING_REVIEW_ROLES,
    ActivePolicyRefs,
    AgentActivationPolicy,
    AgentActivationTriggerRule,
    CausalEvidenceArtifact,
    CausalInputView,
    MonitoringChildRunAttempt,
    MonitoringFrame,
    MonitoringReviewDecision,
    MonitoringReviewDispatchCommand,
    MonitoringReviewDispatchReceipt,
    MonitoringReviewRequest,
    MonitoringReviewResult,
    MonitoringReviewRoleResult,
    MonitoringTelemetrySummary,
    MonitoringTriggerEvent,
    ReplayActivationCheckpoint,
    ReplayActivationRuleCheckpoint,
    ReplayAssetCheckpoint,
    ReplayAssetSpec,
    ReplaySessionConfig,
    ReplaySessionState,
    ReplayStepCommand,
    ReplayStepReceipt,
    ReplayTick,
    ScoringPolicyBundle,
)
from codigo.app.schemas.reasoning import AgentHypothesis


SHA_A = "a" * 64
SHA_B = "b" * 64
SOURCE_TIME = datetime(2004, 2, 12, 10, 32, 39)
RUNTIME_TIME = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def make_policy_refs() -> ActivePolicyRefs:
    return ActivePolicyRefs(
        scoring_version="scoring-v1",
        activation_version="activation-v1",
    )


def make_asset_specs() -> tuple[ReplayAssetSpec, ...]:
    return (
        ReplayAssetSpec(
            asset_id="bearing_1",
            channel_id="channel_1",
            analysis_status="modeled",
        ),
        ReplayAssetSpec(
            asset_id="bearing_2",
            channel_id="channel_2",
            analysis_status="telemetry_only",
        ),
        ReplayAssetSpec(
            asset_id="bearing_3",
            channel_id="channel_3",
            analysis_status="telemetry_only",
        ),
        ReplayAssetSpec(
            asset_id="bearing_4",
            channel_id="channel_4",
            analysis_status="telemetry_only",
        ),
    )


def make_telemetry() -> MonitoringTelemetrySummary:
    return MonitoringTelemetrySummary(
        signal_rms=0.42,
        signal_peak_abs=1.75,
        n_samples=20480,
    )


def make_modeled_frame(
    *,
    frame_id: str = "tick-001:bearing-1:channel-1",
    tick_id: str = "tick-001",
    scoring_version: str = "scoring-v1",
) -> MonitoringFrame:
    return MonitoringFrame(
        frame_id=frame_id,
        tick_id=tick_id,
        asset_id="bearing_1",
        channel_id="channel_1",
        segment_id=0,
        analysis_status="modeled",
        telemetry=make_telemetry(),
        score=0.75,
        threshold=0.60,
        predicted_anomaly=True,
        score_ratio=1.25,
        health_index=72.0,
        risk_index=74.0,
        health_state="warning",
        scoring_version=scoring_version,
        evidence_refs=("feature:channel_1:rms",),
    )


def make_telemetry_frame(channel_number: int) -> MonitoringFrame:
    return MonitoringFrame(
        frame_id=f"tick-001:bearing-{channel_number}:channel-{channel_number}",
        tick_id="tick-001",
        asset_id=f"bearing_{channel_number}",
        channel_id=f"channel_{channel_number}",
        segment_id=0,
        analysis_status="telemetry_only",
        telemetry=make_telemetry(),
        evidence_refs=(f"telemetry:channel_{channel_number}",),
    )


def make_tick(**updates) -> ReplayTick:
    payload = {
        "tick_id": "tick-001",
        "session_id": "nasa-rft-hyb-01",
        "cursor": 0,
        "sequence": 1,
        "snapshot_id": "2004.02.12.10.32.39",
        "source_time": SOURCE_TIME,
        "input_record_hash": SHA_A,
        "active_policy_refs": make_policy_refs(),
        "frames": (
            make_modeled_frame(),
            make_telemetry_frame(2),
            make_telemetry_frame(3),
            make_telemetry_frame(4),
        ),
        "committed_at": RUNTIME_TIME,
    }
    payload.update(updates)
    return ReplayTick.model_validate(payload)


def seal_contract(model_class, payload: dict, hash_field: str):
    sealed = dict(payload)
    sealed[hash_field] = model_class.canonical_sha256(sealed)
    return model_class.model_validate(sealed)


def make_review_request(**updates) -> MonitoringReviewRequest:
    payload = {
        "request_id": "review-request-001",
        "child_run_id": "monitoring-child-001",
        "session_id": "nasa-rft-hyb-01",
        "trigger_id": "trigger-001",
        "trigger_event_id": "trigger-001:event:001",
        "origin_tick_id": "tick-001",
        "cutoff_snapshot_id": "2004.02.12.10.32.39",
        "cutoff_cursor": 0,
        "cutoff_source_time": SOURCE_TIME,
        "active_policy_refs": make_policy_refs(),
        "causal_view_ref": "artifact:causal-view:001",
        "causal_view_sha256": "3" * 64,
        "prompt_template_id": "monitoring-review-prompt-v1",
        "prompt_template_sha256": "4" * 64,
        "response_schema_id": "monitoring-review-decision-v1",
        "response_schema_sha256": "5" * 64,
        "allowed_options_id": "monitoring-review-actions-v1",
        "allowed_options_sha256": "6" * 64,
        "created_at": RUNTIME_TIME,
    }
    payload.update(updates)
    return seal_contract(
        MonitoringReviewRequest,
        payload,
        "request_sha256",
    )


def make_review_decision(
    agent_name: str,
    **updates,
) -> MonitoringReviewDecision:
    decision_id = f"monitoring-child-001:{agent_name}:decision"
    evidence_ref = "evidence-tick-001"
    hypothesis = AgentHypothesis(
        kind="operational_acceptance",
        statement=f"{agent_name} observes evidence compatible with warning",
        scope="bearing_1/channel_1 at the causal cutoff",
        evidence_cutoff="2004.02.12.10.32.39",
        expected_observation="the visible health state remains warning",
        falsification_criterion="the next permitted observation returns to healthy",
        evidence_refs=[evidence_ref],
        risk_notes=["retrospective replay is not a live deployment"],
    )
    payload = {
        "decision_id": decision_id,
        "agent_name": agent_name,
        "child_run_id": "monitoring-child-001",
        "trigger_event_id": "trigger-001:event:001",
        "cutoff_snapshot_id": "2004.02.12.10.32.39",
        "cutoff_cursor": 0,
        "cutoff_source_time": SOURCE_TIME,
        "causal_view_sha256": "3" * 64,
        "rationale": "The bounded evidence supports continued observation.",
        "confidence": 0.72,
        "hypothesis": hypothesis,
        "generation_trace": DecisionGenerationTrace.for_decision(
            decision_id,
            origin="llm",
        ),
        "observation_summary": "One modeled channel is in warning state.",
        "recommended_action": "maintain_policy",
        "action_rationale": "No validated policy change exists in frozen benchmark.",
        "evidence_refs": (evidence_ref,),
        "alternatives": ("insufficient_evidence",),
        "requires_human_review": False,
        "created_at": RUNTIME_TIME,
    }
    payload.update(updates)
    return seal_contract(
        MonitoringReviewDecision,
        payload,
        "decision_sha256",
    )


def make_role_results() -> tuple[MonitoringReviewRoleResult, ...]:
    return tuple(
        MonitoringReviewRoleResult(
            agent_name=role,
            status="completed",
            decision=make_review_decision(role),
            runtime_event_ids=(f"monitoring-child-001:{role}:completed",),
        )
        for role in MONITORING_REVIEW_ROLES
    )


def make_review_result(**updates) -> MonitoringReviewResult:
    request = make_review_request()
    payload = {
        "result_id": "monitoring-review-result-001",
        "request_id": request.request_id,
        "request_sha256": request.request_sha256,
        "child_run_id": request.child_run_id,
        "session_id": request.session_id,
        "trigger_id": request.trigger_id,
        "trigger_event_id": request.trigger_event_id,
        "origin_tick_id": request.origin_tick_id,
        "cutoff_snapshot_id": request.cutoff_snapshot_id,
        "cutoff_cursor": request.cutoff_cursor,
        "cutoff_source_time": request.cutoff_source_time,
        "active_policy_refs": request.active_policy_refs,
        "causal_view_ref": request.causal_view_ref,
        "causal_view_sha256": request.causal_view_sha256,
        "role_results": make_role_results(),
        "runtime_events_ref": "artifact:runtime-events:monitoring-child-001",
        "runtime_events_sha256": "7" * 64,
        "status": "completed",
        "completed_at": RUNTIME_TIME,
    }
    payload.update(updates)
    return seal_contract(MonitoringReviewResult, payload, "result_sha256")


class ReplaySessionContractTests(unittest.TestCase):
    def test_session_config_is_frozen_and_contains_no_future_horizon(self):
        config = ReplaySessionConfig(
            session_id="nasa-rft-hyb-01",
            pilot_id="NASA-RTF-HYB-01",
            dataset_id="nasa_ims_bearing",
            trajectory_id="set_2/channel_1",
            manifest_ref="artifact:manifest:nasa-set-2-v2",
            manifest_sha256=SHA_A,
            source_fingerprint_sha256=SHA_B,
            bootstrap_checkpoints_sha256="c" * 64,
            partition_policy_id="nasa_ims_run_to_failure_v2",
            asset_ids=("bearing_1", "bearing_2", "bearing_3", "bearing_4"),
            asset_specs=make_asset_specs(),
            experiment_mode="frozen_benchmark",
            initial_mode="manual",
            initial_speed_multiplier=1.0,
            initial_policy_refs=make_policy_refs(),
            source_timezone=None,
            created_at=RUNTIME_TIME,
        )

        dumped = config.model_dump(mode="json")

        self.assertEqual(len(dumped["asset_ids"]), 4)
        self.assertNotIn("total_snapshots", dumped)
        self.assertNotIn("failure_time", dumped)
        with self.assertRaises(ValidationError):
            config.initial_mode = "accelerated"

    def test_session_config_rejects_duplicate_assets_and_extra_fields(self):
        payload = {
            "session_id": "nasa-rft-hyb-01",
            "pilot_id": "NASA-RTF-HYB-01",
            "dataset_id": "nasa_ims_bearing",
            "trajectory_id": "set_2/channel_1",
            "manifest_ref": "artifact:manifest:nasa-set-2-v2",
            "manifest_sha256": SHA_A,
            "source_fingerprint_sha256": SHA_B,
            "bootstrap_checkpoints_sha256": "c" * 64,
            "partition_policy_id": "nasa_ims_run_to_failure_v2",
            "asset_ids": ["bearing_1", "bearing_1"],
            "asset_specs": make_asset_specs(),
            "initial_policy_refs": make_policy_refs(),
            "future_length": 984,
        }

        with self.assertRaises(ValidationError):
            ReplaySessionConfig.model_validate(payload)

        payload.pop("future_length")
        with self.assertRaisesRegex(ValidationError, "duplicates"):
            ReplaySessionConfig.model_validate(payload)

    def test_session_config_rejects_duplicate_or_mismatched_asset_specs(self):
        base = {
            "session_id": "nasa-rft-hyb-01",
            "pilot_id": "NASA-RTF-HYB-01",
            "dataset_id": "nasa_ims_bearing",
            "trajectory_id": "set_2/channel_1",
            "manifest_ref": "artifact:manifest:nasa-set-2-v2",
            "manifest_sha256": SHA_A,
            "source_fingerprint_sha256": SHA_B,
            "bootstrap_checkpoints_sha256": "c" * 64,
            "partition_policy_id": "nasa_ims_run_to_failure_v2",
            "asset_ids": ["bearing_1", "bearing_2", "bearing_3", "bearing_4"],
            "asset_specs": make_asset_specs(),
            "initial_policy_refs": make_policy_refs(),
        }
        with self.assertRaisesRegex(ValidationError, "unique asset/channel"):
            ReplaySessionConfig.model_validate(
                {
                    **base,
                    "asset_specs": [make_asset_specs()[0], make_asset_specs()[0]],
                    "asset_ids": ["bearing_1"],
                }
            )

        with self.assertRaisesRegex(ValidationError, "must match asset_specs"):
            ReplaySessionConfig.model_validate(
                {**base, "asset_ids": ["bearing_1", "bearing_2"]}
            )

    def test_session_state_validates_checkpoint_and_lifecycle_consistency(self):
        modeled = ReplayAssetCheckpoint(
            asset_id="bearing_1",
            analysis_status="modeled",
            segment_id=1,
            alert_persistence_count=2,
            recovery_persistence_count=0,
            raw_health_history=(65.0, 75.0),
            smoothed_health_history=(68.0, 72.0),
            last_source_time=SOURCE_TIME,
            last_frame_id="tick-001:bearing-1:channel-1",
            last_health_state="warning",
            scoring_version="scoring-v1",
        )
        telemetry = ReplayAssetCheckpoint(
            asset_id="bearing_2",
            analysis_status="telemetry_only",
            last_source_time=SOURCE_TIME,
            last_frame_id="tick-001:bearing-2:channel-2",
        )
        state = ReplaySessionState(
            session_id="nasa-rft-hyb-01",
            config_sha256=SHA_A,
            status="paused",
            execution_cursor=0,
            sequence=2,
            revision=1,
            mode="manual",
            speed_multiplier=1.0,
            active_policy_refs=make_policy_refs(),
            asset_checkpoints=(modeled, telemetry),
            last_committed_tick_id="tick-001",
            child_run_ids=("child-run-001",),
            active_child_run_id="child-run-001",
            updated_at=RUNTIME_TIME,
        )

        self.assertEqual(state.asset_checkpoints[0].scoring_version, "scoring-v1")
        with self.assertRaises(ValidationError):
            state.speed_multiplier = 0.0

    def test_session_state_rejects_partial_cursor_and_invalid_failure(self):
        base = {
            "session_id": "nasa-rft-hyb-01",
            "config_sha256": SHA_A,
            "active_policy_refs": make_policy_refs(),
            "updated_at": RUNTIME_TIME,
        }
        with self.assertRaisesRegex(ValidationError, "both set or both null"):
            ReplaySessionState.model_validate({**base, "execution_cursor": 0})

        with self.assertRaisesRegex(ValidationError, "failure_reason"):
            ReplaySessionState.model_validate({**base, "status": "failed"})

        with self.assertRaisesRegex(ValidationError, "only valid"):
            ReplaySessionState.model_validate(
                {**base, "status": "ready", "failure_reason": "stale error"}
            )

    def test_session_state_rejects_duplicate_checkpoints_and_unknown_child(self):
        checkpoint = ReplayAssetCheckpoint(
            asset_id="bearing_2",
            analysis_status="telemetry_only",
        )
        base = {
            "session_id": "nasa-rft-hyb-01",
            "config_sha256": SHA_A,
            "active_policy_refs": make_policy_refs(),
            "updated_at": RUNTIME_TIME,
        }
        with self.assertRaisesRegex(ValidationError, "unique asset_id"):
            ReplaySessionState.model_validate(
                {**base, "asset_checkpoints": [checkpoint, checkpoint]}
            )
        with self.assertRaisesRegex(ValidationError, "child_run_ids"):
            ReplaySessionState.model_validate(
                {**base, "active_child_run_id": "missing-child"}
            )

    def test_session_state_requires_activation_checkpoint_version_parity(self):
        with self.assertRaisesRegex(ValidationError, "activation checkpoint"):
            ReplaySessionState(
                session_id="nasa-rft-hyb-01",
                config_sha256=SHA_A,
                active_policy_refs=make_policy_refs(),
                activation_checkpoint=ReplayActivationCheckpoint(
                    activation_version="activation-v2",
                ),
                updated_at=RUNTIME_TIME,
            )


class ReplayActivationCheckpointContractTests(unittest.TestCase):
    def test_checkpoint_keeps_episode_budget_cursor_and_cooldown_state(self):
        checkpoint = ReplayActivationCheckpoint(
            activation_version="activation-v1",
            next_event_sequence=3,
            variable_run_slots_reserved=1,
            persistent_alert_armed=False,
            alert_episode_start_cursor=4,
            alert_episode_start_snapshot_id="snapshot-004",
            alert_episode_id="episode-004",
            alert_episode_handled_trigger_id="trigger-critical-004",
            alert_episode_persistence_trigger_id="trigger-persistent-004",
            last_evaluated_cursor=6,
            last_evaluated_tick_id="tick-006",
            rule_checkpoints=(
                ReplayActivationRuleCheckpoint(
                    trigger_type="state_transition",
                    last_effective_trigger_id="trigger-critical-004",
                    last_effective_source_time=SOURCE_TIME,
                ),
            ),
        )

        self.assertEqual(checkpoint.variable_run_slots_reserved, 1)
        self.assertEqual(checkpoint.alert_episode_start_cursor, 4)
        self.assertEqual(
            checkpoint.alert_episode_handled_trigger_id,
            "trigger-critical-004",
        )
        self.assertEqual(
            checkpoint.alert_episode_persistence_trigger_id,
            "trigger-persistent-004",
        )

    def test_checkpoint_rejects_partial_or_ambiguous_causal_state(self):
        with self.assertRaisesRegex(ValidationError, "cursor and snapshot"):
            ReplayActivationCheckpoint(
                activation_version="activation-v1",
                alert_episode_start_cursor=4,
            )

        with self.assertRaisesRegex(ValidationError, "handled trigger"):
            ReplayActivationCheckpoint(
                activation_version="activation-v1",
                alert_episode_handled_trigger_id="orphan-trigger",
            )

        with self.assertRaisesRegex(ValidationError, "persistent trigger"):
            ReplayActivationCheckpoint(
                activation_version="activation-v1",
                alert_episode_persistence_trigger_id="orphan-persistence",
            )

        rule = ReplayActivationRuleCheckpoint(
            trigger_type="persistent_alert",
            last_effective_trigger_id="trigger-persistent-001",
            last_effective_source_time=SOURCE_TIME,
        )
        with self.assertRaisesRegex(ValidationError, "unique trigger_type"):
            ReplayActivationCheckpoint(
                activation_version="activation-v1",
                rule_checkpoints=(rule, rule),
            )

        with self.assertRaisesRegex(ValidationError, "cursor and tick"):
            ReplayActivationCheckpoint(
                activation_version="activation-v1",
                last_evaluated_cursor=3,
            )


class MonitoringFrameAndTickContractTests(unittest.TestCase):
    def test_four_synchronized_channels_keep_diagnostics_on_channel_one_only(self):
        tick = make_tick()

        self.assertIs(ExportedReplayTick, ReplayTick)
        self.assertEqual(len(tick.frames), 4)
        self.assertEqual(tick.frames[0].analysis_status, "modeled")
        self.assertEqual(
            [frame.analysis_status for frame in tick.frames[1:]],
            ["telemetry_only", "telemetry_only", "telemetry_only"],
        )
        for frame in tick.frames[1:]:
            self.assertIsNotNone(frame.telemetry)
            self.assertIsNone(frame.score)
            self.assertIsNone(frame.predicted_anomaly)
            self.assertIsNone(frame.health_index)
            self.assertIsNone(frame.risk_index)
            self.assertIsNone(frame.health_state)
            self.assertIsNone(frame.scoring_version)

    def test_modeled_frame_requires_complete_diagnostics(self):
        payload = make_modeled_frame().model_dump()
        payload["risk_index"] = None

        with self.assertRaisesRegex(ValidationError, "risk_index"):
            MonitoringFrame.model_validate(payload)

        payload = make_modeled_frame().model_dump()
        payload["segment_id"] = None
        with self.assertRaisesRegex(ValidationError, "require segment_id"):
            MonitoringFrame.model_validate(payload)

    def test_telemetry_only_and_unavailable_are_not_diagnostics(self):
        telemetry_payload = make_telemetry_frame(2).model_dump()
        telemetry_payload["segment_id"] = None
        telemetry_frame = MonitoringFrame.model_validate(telemetry_payload)
        self.assertIsNone(telemetry_frame.segment_id)

        telemetry_payload = telemetry_frame.model_dump()
        telemetry_payload["score"] = 0.3
        with self.assertRaisesRegex(ValidationError, "cannot contain diagnostics"):
            MonitoringFrame.model_validate(telemetry_payload)

        unavailable = MonitoringFrame(
            frame_id="tick-001:bearing-5:channel-5",
            tick_id="tick-001",
            asset_id="bearing_5",
            channel_id="channel_5",
            segment_id=None,
            analysis_status="unavailable",
            unavailable_reason="channel missing in source snapshot",
        )
        self.assertIsNone(unavailable.telemetry)

        with self.assertRaisesRegex(ValidationError, "require unavailable_reason"):
            MonitoringFrame(
                frame_id="tick-001:bearing-5:channel-5",
                tick_id="tick-001",
                asset_id="bearing_5",
                channel_id="channel_5",
                analysis_status="unavailable",
            )

    def test_telemetry_summary_is_finite_and_physically_consistent(self):
        with self.assertRaises(ValidationError):
            MonitoringTelemetrySummary(
                signal_rms=float("inf"),
                signal_peak_abs=float("inf"),
                n_samples=20480,
            )
        with self.assertRaisesRegex(ValidationError, "cannot be lower"):
            MonitoringTelemetrySummary(
                signal_rms=2.0,
                signal_peak_abs=1.0,
                n_samples=20480,
            )

    def test_tick_rejects_partial_or_policy_inconsistent_frames(self):
        with self.assertRaises(ValidationError):
            make_tick(frames=())

        mismatched_tick = make_telemetry_frame(2).model_copy(
            update={"tick_id": "another-tick"}
        )
        with self.assertRaisesRegex(ValidationError, "frame.tick_id"):
            make_tick(frames=(make_modeled_frame(), mismatched_tick))

        wrong_scoring = make_modeled_frame(scoring_version="scoring-v2")
        with self.assertRaisesRegex(ValidationError, "active scoring policy"):
            make_tick(frames=(wrong_scoring,))

    def test_tick_rejects_duplicate_asset_channel_and_extra_fields(self):
        duplicate_coordinate = make_modeled_frame(
            frame_id="tick-001:duplicate",
        )
        with self.assertRaisesRegex(ValidationError, "same asset/channel"):
            make_tick(frames=(make_modeled_frame(), duplicate_coordinate))

        payload = make_tick().model_dump()
        payload["future_snapshot_id"] = "2004.02.12.10.42.39"
        with self.assertRaises(ValidationError):
            ReplayTick.model_validate(payload)


class ScoringAndCausalViewContractTests(unittest.TestCase):
    def test_scoring_bundle_keeps_model_artifacts_and_policy_ids_immutable(self):
        bundle = ScoringPolicyBundle(
            policy_version="scoring-v1",
            policy_sha256=SHA_A,
            parent_version=None,
            asset_id="bearing_1",
            channel_id="channel_1",
            model_ref="artifact:model:isolation-forest-v1",
            model_sha256=SHA_B,
            scaler_ref="artifact:scaler:robust-v1",
            scaler_sha256="c" * 64,
            features_ref="artifact:features:nasa-set-2-channel-1-v1",
            features_sha256="d" * 64,
            feature_columns=("rms", "kurtosis", "crest_factor"),
            threshold=0.6,
            aggregation_policy_id="snapshot_aggregation_v1",
            aggregation_policy_sha256="e" * 64,
            gap_policy_id="temporal_gap_v1",
            gap_policy_sha256="f" * 64,
            health_policy_id="temporal_health_policy_v1",
            health_policy_sha256="1" * 64,
            health_indicator_policy_id="health_indicator_policy_v1",
            health_indicator_policy_sha256="2" * 64,
        )

        self.assertEqual(bundle.asset_id, "bearing_1")
        self.assertEqual(bundle.threshold_operator, "greater_than")
        with self.assertRaises(ValidationError):
            bundle.threshold = 0.7

    def test_scoring_bundle_rejects_duplicate_features_and_non_finite_threshold(self):
        base = {
            "policy_version": "scoring-v1",
            "policy_sha256": SHA_A,
            "asset_id": "bearing_1",
            "channel_id": "channel_1",
            "model_ref": "artifact:model:isolation-forest-v1",
            "model_sha256": SHA_B,
            "scaler_ref": "artifact:scaler:robust-v1",
            "scaler_sha256": "c" * 64,
            "features_ref": "artifact:features:nasa-set-2-channel-1-v1",
            "features_sha256": "d" * 64,
            "feature_columns": ["rms", "rms"],
            "threshold": 0.6,
            "aggregation_policy_id": "snapshot_aggregation_v1",
            "aggregation_policy_sha256": "e" * 64,
            "gap_policy_id": "temporal_gap_v1",
            "gap_policy_sha256": "f" * 64,
            "health_policy_id": "temporal_health_policy_v1",
            "health_policy_sha256": "1" * 64,
            "health_indicator_policy_id": "health_indicator_policy_v1",
            "health_indicator_policy_sha256": "2" * 64,
        }
        with self.assertRaisesRegex(ValidationError, "duplicates"):
            ScoringPolicyBundle.model_validate(base)
        with self.assertRaises(ValidationError):
            ScoringPolicyBundle.model_validate(
                {**base, "feature_columns": ["rms"], "threshold": float("nan")}
            )
        with self.assertRaises(ValidationError):
            ScoringPolicyBundle.model_validate(
                {
                    **base,
                    "feature_columns": ["rms"],
                    "threshold_operator": "greater_than_or_equal",
                }
            )

    def make_causal_view(self, **updates) -> CausalInputView:
        evidence = CausalEvidenceArtifact(
            evidence_id="evidence-tick-001",
            artifact_ref="artifact:causal-view:tick-001",
            artifact_sha256=SHA_B,
            available_at_cursor=0,
            max_source_time=SOURCE_TIME,
            record_count=4,
            fields=(
                "asset_id",
                "channel_id",
                "source_time",
                "analysis_status",
                "signal_rms",
                "score",
                "health_state",
            ),
        )
        payload = {
            "view_id": "causal-view-001",
            "session_id": "nasa-rft-hyb-01",
            "trigger_id": "trigger-001",
            "trigger_event_id": "trigger-001:event:001",
            "origin_tick_id": "tick-001",
            "cutoff_snapshot_id": "2004.02.12.10.32.39",
            "cursor": 0,
            "cutoff_source_time": SOURCE_TIME,
            "active_policy_refs": make_policy_refs(),
            "manifest_projection_ref": "artifact:manifest-projection:cursor-000",
            "manifest_projection_sha256": "c" * 64,
            "partition_policy_id": "nasa_ims_run_to_failure_v2",
            "visible_partitions": ["baseline_train", "calibration", "monitoring"],
            "whitelisted_fields": evidence.fields,
            "evidence": [evidence],
            "created_at": RUNTIME_TIME,
        }
        payload.update(updates)
        if "view_sha256" not in updates:
            payload["view_sha256"] = CausalInputView.canonical_sha256(payload)
        return CausalInputView.model_validate(payload)

    def test_causal_view_accepts_only_whitelisted_cutoff_bounded_evidence(self):
        view = self.make_causal_view()

        self.assertEqual(view.cursor, 0)
        self.assertNotIn("failure_event_time", view.whitelisted_fields)
        self.assertNotIn("relative_life", view.whitelisted_fields)

    def test_causal_view_hash_binds_trigger_tick_and_cutoff_snapshot(self):
        view = self.make_causal_view()

        self.assertEqual(view.view_sha256, CausalInputView.canonical_sha256(view))
        with self.assertRaisesRegex(ValidationError, "canonical payload"):
            self.make_causal_view(view_sha256=SHA_A)

    def test_causal_view_rejects_future_or_non_whitelisted_evidence(self):
        future = CausalEvidenceArtifact(
            evidence_id="future-evidence",
            artifact_ref="artifact:future",
            artifact_sha256=SHA_B,
            available_at_cursor=1,
            max_source_time=datetime(2004, 2, 12, 10, 42, 39),
            record_count=1,
            fields=("score",),
        )
        with self.assertRaisesRegex(ValidationError, "after view cursor"):
            self.make_causal_view(evidence=[future])

        evidence = CausalEvidenceArtifact(
            evidence_id="not-whitelisted",
            artifact_ref="artifact:not-whitelisted",
            artifact_sha256=SHA_B,
            available_at_cursor=0,
            max_source_time=SOURCE_TIME,
            record_count=1,
            fields=("risk_index",),
        )
        with self.assertRaisesRegex(ValidationError, "view whitelist"):
            self.make_causal_view(
                evidence=[evidence],
                whitelisted_fields=["score"],
            )

        with self.assertRaises(ValidationError):
            self.make_causal_view(
                whitelisted_fields=["score", "failure_event_time"],
            )


class MonitoringReviewBridgeContractTests(unittest.TestCase):
    def test_request_freezes_roles_capabilities_memory_and_canonical_hash(self):
        request = make_review_request()

        self.assertEqual(request.requested_roles, MONITORING_REVIEW_ROLES)
        self.assertEqual(request.required_roles, MONITORING_REVIEW_ROLES)
        self.assertEqual(request.capabilities, MONITORING_REVIEW_CAPABILITIES)
        self.assertEqual(request.memory_mode, "off")
        self.assertEqual(
            request.request_sha256,
            MonitoringReviewRequest.canonical_sha256(request),
        )

        payload = request.model_dump()
        payload["requested_roles"] = tuple(reversed(MONITORING_REVIEW_ROLES))
        payload["request_sha256"] = MonitoringReviewRequest.canonical_sha256(payload)
        with self.assertRaisesRegex(ValidationError, "seven canonical roles"):
            MonitoringReviewRequest.model_validate(payload)

        payload = request.model_dump()
        payload["memory_mode"] = "on"
        payload["request_sha256"] = MonitoringReviewRequest.canonical_sha256(payload)
        with self.assertRaises(ValidationError):
            MonitoringReviewRequest.model_validate(payload)

        with self.assertRaisesRegex(ValidationError, "canonical payload"):
            MonitoringReviewRequest.model_validate(
                {**request.model_dump(), "causal_view_ref": "artifact:tampered"}
            )

    def test_decision_is_full_propose_only_and_binds_trace_evidence_and_hash(self):
        decision = make_review_decision("modeler")

        self.assertEqual(decision.decision_kind, "monitoring_review")
        self.assertEqual(decision.policy_application_status, "not_applied")
        self.assertEqual(decision.memory_mode, "off")
        self.assertEqual(
            decision.decision_sha256,
            MonitoringReviewDecision.canonical_sha256(decision),
        )

        with self.assertRaisesRegex(ValidationError, "evidence_cutoff"):
            make_review_decision(
                "modeler",
                hypothesis=decision.hypothesis.model_copy(
                    update={"evidence_cutoff": "future-snapshot"}
                ),
            )
        with self.assertRaisesRegex(ValidationError, "requires_human_review"):
            make_review_decision(
                "modeler",
                recommended_action="request_human_review",
                requires_human_review=False,
            )
        with self.assertRaisesRegex(ValidationError, "derived from decision_id"):
            make_review_decision(
                "modeler",
                generation_trace=DecisionGenerationTrace(
                    origin="llm",
                    attempt_id="foreign-attempt",
                    attempt_index=1,
                    validation_status="validated",
                ),
            )

    def test_result_requires_exactly_seven_bound_completed_role_decisions(self):
        result = make_review_result()

        self.assertEqual(
            tuple(item.agent_name for item in result.role_results),
            MONITORING_REVIEW_ROLES,
        )
        self.assertEqual(result.policy_application_status, "not_applied")
        self.assertEqual(
            result.result_sha256,
            MonitoringReviewResult.canonical_sha256(result),
        )

        with self.assertRaises(ValidationError):
            make_review_result(role_results=make_role_results()[:-1])

        mismatched = list(make_role_results())
        decision = mismatched[3].decision
        assert decision is not None
        mismatched[3] = mismatched[3].model_copy(
            update={
                "decision": make_review_decision(
                    "modeler",
                    child_run_id="different-child-run",
                )
            }
        )
        with self.assertRaisesRegex(ValidationError, "child_run_id must match"):
            make_review_result(role_results=mismatched)

    def test_failed_result_still_accounts_for_all_roles(self):
        role_results = list(make_role_results())
        role_results[3] = MonitoringReviewRoleResult(
            agent_name="modeler",
            status="failed",
            runtime_event_ids=("monitoring-child-001:modeler:failed",),
            failure_reason="invalid structured response",
        )
        result = make_review_result(
            role_results=role_results,
            status="failed",
            failure_reason="one required role failed",
        )

        self.assertEqual(len(result.role_results), 7)
        self.assertEqual(result.role_results[3].status, "failed")
        with self.assertRaisesRegex(ValidationError, "all seven roles completed"):
            make_review_result(role_results=role_results)

    def test_dispatch_contracts_bind_identity_revision_and_lifecycle(self):
        command_payload = {
            "command_id": "dispatch-command-001",
            "session_id": "nasa-rft-hyb-01",
            "trigger_id": "trigger-001",
            "trigger_event_id": "trigger-001:event:001",
            "child_run_id": "monitoring-child-001",
            "job_id": "monitoring-child-001",
            "run_id": "monitoring-child-001",
            "attempt_no": 1,
            "expected_child_revision": 0,
            "request_ref": "artifact:monitoring-review-request:001",
            "request_sha256": make_review_request().request_sha256,
            "causal_view_ref": "artifact:causal-view:001",
            "causal_view_sha256": "3" * 64,
            "issued_at": RUNTIME_TIME,
        }
        command = seal_contract(
            MonitoringReviewDispatchCommand,
            command_payload,
            "command_sha256",
        )
        attempt = MonitoringChildRunAttempt(
            session_id=command.session_id,
            trigger_id=command.trigger_id,
            trigger_event_id=command.trigger_event_id,
            child_run_id=command.child_run_id,
            job_id=command.job_id,
            run_id=command.run_id,
            attempt_no=command.attempt_no,
            child_revision=1,
            lifecycle_status="dispatched",
            request_ref=command.request_ref,
            request_sha256=command.request_sha256,
            causal_view_ref=command.causal_view_ref,
            causal_view_sha256=command.causal_view_sha256,
            dispatched_at=RUNTIME_TIME,
            updated_at=RUNTIME_TIME,
        )
        receipt_payload = {
            "receipt_id": "dispatch-receipt-001",
            "command_id": command.command_id,
            "command_sha256": command.command_sha256,
            "session_id": command.session_id,
            "trigger_id": command.trigger_id,
            "trigger_event_id": command.trigger_event_id,
            "child_run_id": command.child_run_id,
            "job_id": command.job_id,
            "run_id": command.run_id,
            "attempt_no": command.attempt_no,
            "expected_child_revision": command.expected_child_revision,
            "child_revision": 1,
            "request_ref": command.request_ref,
            "request_sha256": command.request_sha256,
            "causal_view_ref": command.causal_view_ref,
            "causal_view_sha256": command.causal_view_sha256,
            "outcome": "dispatched",
            "attempt": attempt,
            "recorded_at": RUNTIME_TIME,
        }
        receipt = seal_contract(
            MonitoringReviewDispatchReceipt,
            receipt_payload,
            "receipt_sha256",
        )

        self.assertEqual(receipt.attempt.lifecycle_status, "dispatched")
        with self.assertRaisesRegex(ValidationError, "must be identical"):
            seal_contract(
                MonitoringReviewDispatchCommand,
                {**command_payload, "job_id": "different-job"},
                "command_sha256",
            )
        with self.assertRaisesRegex(ValidationError, "require error"):
            MonitoringChildRunAttempt(
                **{
                    **attempt.model_dump(),
                    "lifecycle_status": "failed",
                    "started_at": RUNTIME_TIME,
                    "completed_at": RUNTIME_TIME,
                    "result_ref": "artifact:failed-result",
                    "result_sha256": "8" * 64,
                }
            )


class AgentActivationPolicyContractTests(unittest.TestCase):
    def test_policy_freezes_budget_schedule_roles_and_precedence(self):
        periodic = AgentActivationTriggerRule(
            trigger_type="periodic_review",
            priority=40,
            cooldown_source_seconds=1200.0,
            coalescing_group="scheduled_review",
            rearm_policy="after_cooldown",
            requested_roles=("supervisor", "evaluator"),
            counts_toward_variable_budget=True,
        )
        alert = AgentActivationTriggerRule(
            trigger_type="persistent_alert",
            priority=90,
            cooldown_source_seconds=1800.0,
            coalescing_group="health_episode",
            rearm_policy="after_recovery",
            requested_roles=("supervisor", "modeler", "evaluator"),
            counts_toward_variable_budget=True,
        )
        policy = AgentActivationPolicy(
            policy_version="activation-v1",
            policy_sha256=SHA_A,
            policy_kind="P3",
            max_variable_child_runs=3,
            periodic_cursors=(100,),
            alert_entry_persistence_ticks=3,
            alert_recovery_persistence_ticks=2,
            trigger_rules=(periodic, alert),
            precedence=("persistent_alert", "periodic_review"),
        )

        self.assertEqual(policy.budget_unit, "variable_child_runs")
        with self.assertRaises(ValidationError):
            policy.max_variable_child_runs = 4

    def test_policy_rejects_unfrozen_or_over_budget_schedule(self):
        periodic = AgentActivationTriggerRule(
            trigger_type="periodic_review",
            requested_roles=("supervisor",),
        )
        base = {
            "policy_version": "activation-v1",
            "policy_sha256": SHA_A,
            "policy_kind": "P2",
            "max_variable_child_runs": 2,
            "trigger_rules": [periodic],
            "precedence": ["periodic_review"],
        }
        with self.assertRaisesRegex(ValidationError, "sorted and unique"):
            AgentActivationPolicy.model_validate(
                {**base, "periodic_cursors": [20, 10]}
            )
        with self.assertRaisesRegex(ValidationError, "cannot exceed"):
            AgentActivationPolicy.model_validate(
                {**base, "periodic_cursors": [10, 20, 30]}
            )

    def test_fixed_or_manual_reviews_cannot_consume_variable_budget(self):
        for trigger_type in ("preflight", "session_close", "manual"):
            with self.subTest(trigger_type=trigger_type):
                with self.assertRaisesRegex(ValidationError, "outside variable budget"):
                    AgentActivationTriggerRule(
                        trigger_type=trigger_type,
                        requested_roles=("supervisor",),
                        counts_toward_variable_budget=True,
                    )

    def test_policy_kind_enforces_experimental_run_budget(self):
        with self.assertRaisesRegex(ValidationError, "P0 and P1"):
            AgentActivationPolicy(
                policy_version="activation-p0-v1",
                policy_sha256=SHA_A,
                policy_kind="P0",
                max_variable_child_runs=1,
            )

        with self.assertRaisesRegex(ValidationError, "positive variable-run"):
            AgentActivationPolicy(
                policy_version="activation-p3-v1",
                policy_sha256=SHA_A,
                policy_kind="P3",
                max_variable_child_runs=0,
            )

    def test_trigger_rule_rejects_duplicate_roles(self):
        with self.assertRaisesRegex(ValidationError, "duplicates"):
            AgentActivationTriggerRule(
                trigger_type="persistent_alert",
                requested_roles=("evaluator", "evaluator"),
            )

    def test_state_transition_targets_and_rearm_semantics_are_closed(self):
        with self.assertRaisesRegex(ValidationError, "closed target states"):
            AgentActivationTriggerRule(
                trigger_type="state_transition",
                requested_roles=("supervisor",),
            )

        with self.assertRaisesRegex(
            ValidationError,
            "only valid for state_transition",
        ):
            AgentActivationTriggerRule(
                trigger_type="persistent_alert",
                state_transition_targets=("critical",),
                requested_roles=("supervisor",),
            )

        with self.assertRaisesRegex(ValidationError, "after_recovery"):
            AgentActivationTriggerRule(
                trigger_type="state_transition",
                state_transition_targets=("critical",),
                rearm_policy="after_recovery",
                requested_roles=("supervisor",),
            )

    def test_p3_requires_complete_precedence_and_role_mapping(self):
        transition_without_roles = AgentActivationTriggerRule(
            trigger_type="state_transition",
            state_transition_targets=("warning", "critical"),
        )
        with self.assertRaisesRegex(ValidationError, "requested_roles"):
            AgentActivationPolicy(
                policy_version="activation-p3-v1",
                policy_sha256=SHA_A,
                policy_kind="P3",
                max_variable_child_runs=1,
                trigger_rules=(transition_without_roles,),
                precedence=("state_transition",),
            )

        transition = AgentActivationTriggerRule(
            trigger_type="state_transition",
            state_transition_targets=("warning", "critical"),
            requested_roles=("supervisor", "evaluator"),
        )
        with self.assertRaisesRegex(ValidationError, "every enabled trigger rule"):
            AgentActivationPolicy(
                policy_version="activation-p3-v1",
                policy_sha256=SHA_A,
                policy_kind="P3",
                max_variable_child_runs=1,
                trigger_rules=(transition,),
                precedence=(),
            )

    def test_coalescing_group_cannot_mix_variable_and_fixed_reviews(self):
        periodic = AgentActivationTriggerRule(
            trigger_type="periodic_review",
            coalescing_group="mixed-review",
            requested_roles=("supervisor",),
        )
        close = AgentActivationTriggerRule(
            trigger_type="session_close",
            coalescing_group="mixed-review",
            rearm_policy="once_per_session",
            requested_roles=("report_writer",),
            counts_toward_variable_budget=False,
        )
        with self.assertRaisesRegex(
            ValidationError,
            "cannot mix variable and fixed",
        ):
            AgentActivationPolicy(
                policy_version="activation-p3-v1",
                policy_sha256=SHA_A,
                policy_kind="P3",
                max_variable_child_runs=1,
                periodic_cursors=(0,),
                trigger_rules=(periodic, close),
                precedence=("periodic_review", "session_close"),
            )


class MonitoringTriggerEventContractTests(unittest.TestCase):
    def make_event(self, **updates) -> MonitoringTriggerEvent:
        payload = {
            "event_id": "trigger-001:event-000",
            "trigger_id": "trigger-001",
            "session_id": "nasa-rft-hyb-01",
            "sequence": 2,
            "trigger_type": "state_transition",
            "lifecycle_status": "emitted",
            "priority": 90,
            "reason_code": "health_state_escalation",
            "reason": "deterministic transition from watch to warning",
            "asset_id": "bearing_1",
            "snapshot_start_id": "2004.02.12.10.32.39",
            "snapshot_end_id": "2004.02.12.10.32.39",
            "condition_start_cursor": 0,
            "cutoff_cursor": 0,
            "cutoff_source_time": SOURCE_TIME,
            "previous_state": "watch",
            "new_state": "warning",
            "cooldown_source_seconds": 1800.0,
            "rearm_policy": "after_cooldown",
            "requested_roles": ["supervisor", "evaluator"],
            "counts_toward_variable_budget": True,
            "budget_reservation_index": 1,
            "dedupe_key": "state-transition:bearing-1:0",
            "activation_version": "activation-v1",
            "activation_policy_sha256": SHA_A,
            "origin_tick_id": "tick-001",
            "frame_ids": ["tick-001:bearing-1:channel-1"],
            "evidence_refs": ["tick:tick-001"],
            "recorded_at": RUNTIME_TIME,
        }
        payload.update(updates)
        return MonitoringTriggerEvent.model_validate(payload)

    def test_state_transition_keeps_exact_causal_links(self):
        event = self.make_event()

        self.assertEqual(event.origin_tick_id, "tick-001")
        self.assertEqual(event.cutoff_cursor, 0)
        self.assertEqual(event.activation_version, "activation-v1")

    def test_preflight_has_no_replay_cutoff(self):
        event = self.make_event(
            trigger_type="preflight",
            previous_state=None,
            new_state=None,
            origin_tick_id=None,
            frame_ids=[],
            evidence_refs=[],
            snapshot_start_id=None,
            snapshot_end_id=None,
            condition_start_cursor=None,
            cutoff_cursor=None,
            cutoff_source_time=None,
            reason_code="preflight_review",
            rearm_policy="once_per_session",
            counts_toward_variable_budget=False,
            budget_reservation_index=None,
        )

        self.assertIsNone(event.origin_tick_id)

    def test_transition_and_lifecycle_references_are_consistent(self):
        with self.assertRaisesRegex(ValidationError, "different states"):
            self.make_event(previous_state="warning", new_state="warning")

        with self.assertRaisesRegex(ValidationError, "suppression_reason"):
            self.make_event(
                trigger_type="persistent_alert",
                previous_state=None,
                new_state=None,
                lifecycle_status="suppressed",
                reason_code="persistent_confirmation",
                rearm_policy="after_recovery",
                budget_reservation_index=None,
            )

        with self.assertRaisesRegex(ValidationError, "suppressed_by_trigger_id"):
            self.make_event(
                trigger_type="persistent_alert",
                previous_state=None,
                new_state=None,
                lifecycle_status="suppressed",
                reason_code="persistent_confirmation",
                rearm_policy="after_recovery",
                budget_reservation_index=None,
                suppression_reason="cooldown",
            )

        with self.assertRaisesRegex(ValidationError, "cannot coalesce into itself"):
            self.make_event(
                trigger_type="persistent_alert",
                previous_state=None,
                new_state=None,
                lifecycle_status="coalesced",
                reason_code="persistent_confirmation",
                rearm_policy="after_recovery",
                budget_reservation_index=None,
                coalesced_into_trigger_id="trigger-001",
            )

        with self.assertRaisesRegex(ValidationError, "cannot exceed cutoff_cursor"):
            self.make_event(condition_start_cursor=1, cutoff_cursor=0)


class ReplayStepCommandContractTests(unittest.TestCase):
    def test_step_command_is_frozen_and_rejects_unknown_operations(self):
        command = ReplayStepCommand(
            command_id="command-001",
            session_id="nasa-rft-hyb-01",
            expected_revision=4,
            issued_at=RUNTIME_TIME,
        )

        self.assertEqual(command.command, "step")
        with self.assertRaises(ValidationError):
            command.expected_revision = 5
        with self.assertRaises(ValidationError):
            ReplayStepCommand.model_validate(
                {
                    **command.model_dump(),
                    "command": "play",
                }
            )

    def test_applied_and_idempotent_receipts_return_the_same_tick_revision(self):
        applied = ReplayStepReceipt(
            command_id="command-001",
            session_id="nasa-rft-hyb-01",
            expected_revision=4,
            outcome="applied",
            accepted_revision=5,
            tick_id="tick-005",
            recorded_at=RUNTIME_TIME,
        )
        replayed = ReplayStepReceipt(
            command_id="command-001",
            session_id="nasa-rft-hyb-01",
            expected_revision=4,
            outcome="idempotent_replay",
            accepted_revision=5,
            tick_id="tick-005",
            recorded_at=RUNTIME_TIME,
        )

        self.assertEqual(applied.tick_id, replayed.tick_id)
        self.assertEqual(applied.accepted_revision, replayed.accepted_revision)

    def test_step_receipt_rejects_wrong_revision_or_ambiguous_failure(self):
        with self.assertRaisesRegex(ValidationError, "exactly one revision"):
            ReplayStepReceipt(
                command_id="command-001",
                session_id="nasa-rft-hyb-01",
                expected_revision=4,
                outcome="applied",
                accepted_revision=6,
                tick_id="tick-006",
                recorded_at=RUNTIME_TIME,
            )

        with self.assertRaisesRegex(ValidationError, "different accepted_revision"):
            ReplayStepReceipt(
                command_id="command-002",
                session_id="nasa-rft-hyb-01",
                expected_revision=5,
                outcome="revision_conflict",
                accepted_revision=5,
                reason="stale client revision",
                recorded_at=RUNTIME_TIME,
            )

        conflict = ReplayStepReceipt(
            command_id="command-002",
            session_id="nasa-rft-hyb-01",
            expected_revision=4,
            outcome="revision_conflict",
            accepted_revision=5,
            reason="stale client revision",
            recorded_at=RUNTIME_TIME,
        )
        self.assertIsNone(conflict.tick_id)


if __name__ == "__main__":
    unittest.main()
