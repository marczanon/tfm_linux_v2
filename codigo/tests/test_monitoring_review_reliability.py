import tempfile
import unittest
import copy
import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from codigo.app.agents.monitoring_reviewer import (
    decide_monitoring_review_action,
    monitoring_review_contract_fingerprints,
)
from codigo.app.schemas.monitoring_replay import (
    MONITORING_REVIEW_ROLES,
    ActivePolicyRefs,
    CausalEvidenceArtifact,
    CausalInputView,
    MonitoringReviewDecision,
    MonitoringReviewRequest,
    MonitoringReviewResult,
    MonitoringReviewRoleResult,
    MonitoringTriggerEvent,
)
from codigo.app.services.agent_reliability import (
    AgentReliabilityAttempt,
    AgentReliabilityModelConfig,
)
from codigo.app.services.monitoring_review_reliability import (
    EXPECTED_NASA_P3_PRIMARY_CONTEXTS,
    MonitoringReviewReliabilityObservation,
    MonitoringReviewReliabilityRoleChecks,
    assess_monitoring_review_reliability_gate,
    build_monitoring_review_reliability_result,
    default_monitoring_review_reliability_plan,
    load_published_monitoring_review_reliability,
    observe_monitoring_review_result,
    preregister_monitoring_review_reliability_plan,
    publish_monitoring_review_reliability,
    summarize_monitoring_review_reliability,
    write_monitoring_review_reliability_artifacts,
)
from codigo.app.services.monitoring_review_store import (
    build_causal_evidence_catalog,
)


class MonitoringReviewReliabilityTests(unittest.TestCase):
    def test_default_plan_freezes_exact_nasa_p3_pack(self):
        plan = default_monitoring_review_reliability_plan()

        self.assertEqual(plan.scenario_id, "NASA-RTF-HYB-01")
        self.assertEqual(plan.activation_policy_kind, "P3")
        self.assertEqual(plan.experiment_mode, "frozen_benchmark")
        self.assertEqual(plan.selector, "all_primary_emitted")
        self.assertEqual(plan.repetitions, 3)
        self.assertFalse(plan.memory_enabled)
        self.assertFalse(plan.policy_application_enabled)
        self.assertEqual(plan.llm_config.model, "qwen3.5:4b")
        self.assertFalse(plan.llm_config.think)
        self.assertEqual(plan.llm_config.timeout_seconds, 180.0)
        self.assertEqual(plan.llm_config.temperature, 0.0)
        self.assertEqual(plan.llm_config.num_ctx, 8192)
        self.assertEqual(plan.llm_config.num_predict, 4096)
        self.assertEqual(plan.llm_config.max_json_repair_attempts, 0)
        self.assertEqual(
            plan.llm_config.transport_trace_scope,
            "physical_ollama_chat",
        )
        self.assertEqual(
            plan.model_digest_sha256,
            "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd",
        )
        self.assertEqual(plan.expected_roles, MONITORING_REVIEW_ROLES)
        self.assertEqual(plan.expected_contexts, EXPECTED_NASA_P3_PRIMARY_CONTEXTS)
        self.assertEqual(
            [
                (
                    item.trigger_type,
                    item.condition_start_cursor,
                    item.cutoff_cursor,
                )
                for item in plan.expected_contexts
            ],
            [
                ("state_transition", 353, 353),
                ("persistent_alert", 496, 498),
                ("state_transition", 499, 499),
                ("session_close", 688, 688),
            ],
        )
        self.assertEqual(plan.expected_child_run_count, 12)
        self.assertEqual(plan.expected_observation_count, 84)

    def test_complete_pack_passes_and_one_repair_remains_agentic(self):
        plan = default_monitoring_review_reliability_plan()
        observations = _complete_observations(plan)
        repaired = observations[0].model_dump(mode="json")
        repaired.update(
            outcome="llm_repaired",
            generation_validation_status="repaired",
            generation_attempt_index=2,
            physical_attempts=[
                repaired["physical_attempts"][0],
                {
                    **repaired["physical_attempts"][0],
                    "attempt_index": 85,
                    "kind": "initial",
                    "prompt_sha256": "4" * 64,
                    "response_sha256": "5" * 64,
                },
            ],
        )
        observations[0] = MonitoringReviewReliabilityObservation.model_validate(
            repaired
        )

        summary = summarize_monitoring_review_reliability(plan, observations)
        gate = assess_monitoring_review_reliability_gate(plan, summary)

        self.assertEqual(summary.observation_count, 84)
        self.assertEqual(summary.child_run_count, 12)
        self.assertEqual(summary.resolved_child_run_count, 12)
        self.assertEqual(summary.complete_repetition_count, 3)
        self.assertEqual(summary.first_pass_count, 83)
        self.assertEqual(summary.repaired_count, 1)
        self.assertEqual(summary.llm_origin_rate, 1.0)
        self.assertGreater(summary.first_pass_rate, 0.90)
        self.assertEqual(gate.verdict, "passed")
        self.assertEqual(len(summary.action_consistency), 28)

    def test_fallback_and_unscoped_physical_claim_block_gate(self):
        plan = default_monitoring_review_reliability_plan()
        observations = _complete_observations(plan)
        fallback = observations[0].model_dump(mode="json")
        fallback.update(
            outcome="fallback",
            generation_origin="guardrail_fallback",
            generation_validation_status="fallback_applied",
            generation_attempt_index=2,
        )
        checks = dict(fallback["checks"])
        checks.update(
            claims_scoped=False,
            unsupported_claim_ids=["confirmed_physical_degradation"],
            details=["unsupported_claims:confirmed_physical_degradation"],
        )
        fallback["checks"] = checks
        observations[0] = MonitoringReviewReliabilityObservation.model_validate(
            fallback
        )

        summary = summarize_monitoring_review_reliability(plan, observations)
        gate = assess_monitoring_review_reliability_gate(plan, summary)

        self.assertEqual(gate.verdict, "blocked")
        self.assertIn("fallback_count:1", gate.blockers)
        self.assertTrue(
            any(item.startswith("claims_scoped_rate:") for item in gate.blockers)
        )

    def test_hidden_json_repair_and_missing_physical_trace_block_gate(self):
        plan = default_monitoring_review_reliability_plan()
        observations = _complete_observations(plan)
        hidden_repair = observations[0].model_dump(mode="json")
        hidden_repair.update(outcome="llm_repaired")
        hidden_repair["physical_attempts"][0]["kind"] = "json_repair"
        hidden_repair["checks"]["physical_trace_valid"] = False
        observations[0] = MonitoringReviewReliabilityObservation.model_validate(
            hidden_repair
        )

        summary = summarize_monitoring_review_reliability(plan, observations)
        gate = assess_monitoring_review_reliability_gate(plan, summary)

        self.assertEqual(gate.verdict, "blocked")
        self.assertIn("physical_json_repair_call_count:1", gate.blockers)
        self.assertTrue(
            any(item.startswith("physical_trace_rate:") for item in gate.blockers)
        )

        missing_trace = _complete_observations(plan)[0].model_dump(mode="json")
        missing_trace["physical_attempts"] = []
        with self.assertRaisesRegex(ValueError, "physical_trace_valid"):
            MonitoringReviewReliabilityObservation.model_validate(missing_trace)

    def test_duplicate_trigger_identity_cannot_complete_three_by_four_pack(self):
        plan = default_monitoring_review_reliability_plan()
        observations = _complete_observations(plan)
        first_trigger_id = observations[0].trigger_id
        for index, item in enumerate(observations):
            if item.repetition == 1 and item.context_ordinal == 2:
                payload = item.model_dump(mode="json")
                payload["trigger_id"] = first_trigger_id
                observations[index] = (
                    MonitoringReviewReliabilityObservation.model_validate(payload)
                )

        summary = summarize_monitoring_review_reliability(plan, observations)
        gate = assess_monitoring_review_reliability_gate(plan, summary)

        self.assertEqual(summary.complete_repetition_count, 2)
        self.assertEqual(gate.verdict, "blocked")
        self.assertIn("complete_repetition_count:2!=3", gate.blockers)

    def test_observer_uses_sealed_contracts_and_scopes_physical_claims(self):
        plan = default_monitoring_review_reliability_plan()
        trigger, view, catalog, request, result = _sealed_review_pack()
        repair_attempt = AgentReliabilityAttempt(
            attempt_index=2,
            kind="json_repair",
            status="success",
            message_count=3,
            prompt_sha256="1" * 64,
            schema_sha256="2" * 64,
            response_sha256="3" * 64,
            elapsed_ms=10.0,
        )

        observations = observe_monitoring_review_result(
            plan,
            repetition=1,
            context_id="state_transition_353",
            trigger=trigger,
            causal_view=view,
            evidence_catalog=catalog,
            request=request,
            result=result,
            child_lifecycle_status="resolved",
            physical_attempts_by_role={"supervisor": [repair_attempt]},
        )

        self.assertEqual(len(observations), 7)
        self.assertEqual(observations[0].outcome, "llm_repaired")
        self.assertTrue(
            all(not item.checks.physical_trace_valid for item in observations)
        )
        self.assertTrue(all(item.checks.binding_valid for item in observations))
        self.assertTrue(all(item.checks.grounding_valid for item in observations))
        self.assertTrue(
            all(item.checks.hypothesis_structural_valid for item in observations)
        )
        self.assertTrue(all(item.checks.claims_scoped for item in observations))

        unsafe_decision_payload = result.role_results[0].decision.model_dump(
            mode="python",
            exclude={"decision_sha256"},
        )
        unsafe_decision_payload["rationale"] = (
            "La degradacion confirmada antes del fallo queda demostrada."
        )
        unsafe_decision_payload["decision_sha256"] = (
            MonitoringReviewDecision.canonical_sha256(unsafe_decision_payload)
        )
        unsafe_decision = MonitoringReviewDecision.model_validate(
            unsafe_decision_payload
        )
        unsafe_result = _replace_result_decision(result, unsafe_decision)
        unsafe_observations = observe_monitoring_review_result(
            plan,
            repetition=1,
            context_id="state_transition_353",
            trigger=trigger,
            causal_view=view,
            evidence_catalog=catalog,
            request=request,
            result=unsafe_result,
            child_lifecycle_status="resolved",
        )

        self.assertFalse(unsafe_observations[0].checks.claims_scoped)
        self.assertIn(
            "confirmed_physical_degradation",
            unsafe_observations[0].checks.unsupported_claim_ids,
        )

        unsafe_scope_payload = result.role_results[0].decision.model_dump(
            mode="python",
            exclude={"decision_sha256"},
        )
        unsafe_scope_payload["hypothesis"]["scope"] = (
            "Fallo detectado y confirmado en el rodamiento fisico."
        )
        unsafe_scope_payload["decision_sha256"] = (
            MonitoringReviewDecision.canonical_sha256(unsafe_scope_payload)
        )
        unsafe_scope_decision = MonitoringReviewDecision.model_validate(
            unsafe_scope_payload
        )
        unsafe_scope_result = _replace_result_decision(
            result,
            unsafe_scope_decision,
        )
        unsafe_scope_observations = observe_monitoring_review_result(
            plan,
            repetition=1,
            context_id="state_transition_353",
            trigger=trigger,
            causal_view=view,
            evidence_catalog=catalog,
            request=request,
            result=unsafe_scope_result,
            child_lifecycle_status="resolved",
        )

        self.assertFalse(unsafe_scope_observations[0].checks.claims_scoped)
        self.assertIn(
            "detected_physical_failure",
            unsafe_scope_observations[0].checks.unsupported_claim_ids,
        )

    def test_preregistration_is_immutable_and_publication_roundtrips_current(self):
        plan = default_monitoring_review_reliability_plan(
            plan_id="monitoring-reliability-roundtrip"
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            preregistration = preregister_monitoring_review_reliability_plan(
                plan,
                output_root=root,
            )
            same = preregister_monitoring_review_reliability_plan(
                plan,
                output_root=root,
            )
            self.assertEqual(same.plan_sha256, preregistration.plan_sha256)

            changed = default_monitoring_review_reliability_plan(
                plan_id=plan.plan_id,
                minimum_first_pass_rate=0.95,
            )
            with self.assertRaisesRegex(ValueError, "idempotency conflict"):
                preregister_monitoring_review_reliability_plan(
                    changed,
                    output_root=root,
                )

            with self.assertRaisesRegex(ValueError, "runtime llm_config differs"):
                build_monitoring_review_reliability_result(
                    plan,
                    _complete_observations(plan),
                    preregistration=preregistration,
                    llm_config=AgentReliabilityModelConfig(
                        provider="ollama",
                        model="qwen3.5:4b",
                    ),
                    started_at=max(
                        datetime.now(UTC),
                        preregistration.registered_at,
                    ),
                    completed_at=max(
                        datetime.now(UTC),
                        preregistration.registered_at,
                    )
                    + timedelta(seconds=1),
                )

            started_at = max(datetime.now(UTC), preregistration.registered_at)
            result = build_monitoring_review_reliability_result(
                plan,
                _complete_observations(plan),
                preregistration=preregistration,
                llm_config=plan.llm_config,
                started_at=started_at,
                completed_at=started_at + timedelta(seconds=1),
            )
            artifacts = write_monitoring_review_reliability_artifacts(
                result,
                output_root=root,
            )
            publication = publish_monitoring_review_reliability(
                result,
                artifacts,
                output_root=root,
            )
            loaded = load_published_monitoring_review_reliability(
                output_root=root,
            )

            self.assertTrue((root / "current.json").is_file())
            self.assertEqual(publication.plan_id, plan.plan_id)
            self.assertEqual(loaded, result)
            self.assertNotIn(
                "ollama_host",
                Path(artifacts.manifest_path).read_text(encoding="utf-8"),
            )
            first_line = Path(artifacts.observations_path).read_text(
                encoding="utf-8"
            ).splitlines()[0]
            self.assertNotIn("rationale", first_line)
            self.assertNotIn("observation_summary", first_line)


def _complete_observations(plan):
    observations = []
    checks = MonitoringReviewReliabilityRoleChecks(
        trace_valid=True,
        physical_trace_valid=True,
        binding_valid=True,
        grounding_valid=True,
        hypothesis_structural_valid=True,
        claims_scoped=True,
        action_catalog_valid=True,
        memory_mode_valid=True,
        policy_application_valid=True,
    )
    for repetition in range(1, plan.repetitions + 1):
        session_id = f"session-{repetition:03d}"
        for context in plan.expected_contexts:
            child_run_id = f"child-{repetition:03d}-{context.ordinal:02d}"
            for role_index, role in enumerate(plan.expected_roles, start=1):
                physical_attempt_index = (
                    (repetition - 1) * len(plan.expected_contexts) * len(plan.expected_roles)
                    + (context.ordinal - 1) * len(plan.expected_roles)
                    + role_index
                )
                observations.append(
                    MonitoringReviewReliabilityObservation(
                        observation_id=(
                            f"{plan.plan_id}:rep:{repetition:03d}:"
                            f"{context.context_id}:{role}"
                        ),
                        plan_id=plan.plan_id,
                        repetition=repetition,
                        context_id=context.context_id,
                        context_ordinal=context.ordinal,
                        trigger_type=context.trigger_type,
                        reason_code=context.reason_code,
                        condition_start_cursor=context.condition_start_cursor,
                        cutoff_cursor=context.cutoff_cursor,
                        session_id=session_id,
                        trigger_id=f"trigger-{repetition:03d}-{context.ordinal:02d}",
                        trigger_event_id=(
                            f"trigger-{repetition:03d}-{context.ordinal:02d}:event:001"
                        ),
                        child_run_id=child_run_id,
                        run_ref=f"codigo/reports/runs/{child_run_id}",
                        request_sha256="a" * 64,
                        result_sha256="b" * 64,
                        causal_view_sha256="c" * 64,
                        child_lifecycle_status="resolved",
                        review_status="completed",
                        agent_name=role,
                        outcome="first_pass",
                        decision_id=f"{child_run_id}:{role}:001",
                        decision_sha256="d" * 64,
                        generation_origin="llm",
                        generation_validation_status="validated",
                        generation_attempt_index=1,
                        hypothesis_kind="routing_readiness",
                        hypothesis_sha256="e" * 64,
                        recommended_action="maintain_policy",
                        evidence_refs=(f"evidence:{child_run_id}",),
                        physical_attempts=(
                            AgentReliabilityAttempt(
                                attempt_index=physical_attempt_index,
                                kind="initial",
                                status="success",
                                message_count=2,
                                prompt_sha256="1" * 64,
                                schema_sha256="2" * 64,
                                response_sha256="3" * 64,
                                elapsed_ms=10.0,
                            ),
                        ),
                        checks=checks,
                    )
                )
    return observations


class _JSONClient:
    def __init__(self, payload):
        self.payload = payload

    def complete_json(self, messages, *, json_schema=None):
        del messages, json_schema
        return copy.deepcopy(self.payload)


def _sealed_review_pack():
    source_time = datetime(2004, 2, 16, 8, 0, 0)
    recorded_at = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
    evidence_ref = "evidence:session-001:trigger-001"
    records = [
        {
            "record_id": f"frame-{342 + index}",
            "asset_id": "bearing_1",
            "channel_id": "channel_1",
            "snapshot_id": (
                source_time - timedelta(minutes=10 * (11 - index))
            ).strftime("%Y.%m.%d.%H.%M.%S"),
            "source_time": (
                source_time - timedelta(minutes=10 * (11 - index))
            ).isoformat(),
            "analysis_status": "modeled",
            "score": 0.1 + index * 0.1,
            "threshold": 1.0,
            "health_state": "critical" if index == 11 else "warning",
        }
        for index in range(12)
    ]
    evidence_sha256 = hashlib.sha256(
        json.dumps(
            records,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    evidence = CausalEvidenceArtifact(
        evidence_id=evidence_ref,
        artifact_ref="artifact:monitoring-evidence:353",
        artifact_sha256=evidence_sha256,
        available_at_cursor=353,
        max_source_time=source_time,
        record_count=len(records),
        fields=(
            "record_id",
            "asset_id",
            "channel_id",
            "snapshot_id",
            "source_time",
            "analysis_status",
            "score",
            "threshold",
            "health_state",
        ),
    )
    view_payload = {
        "view_id": "causal-view:session-001:trigger-001",
        "session_id": "session-001",
        "trigger_id": "trigger-001",
        "trigger_event_id": "trigger-001:event:001",
        "origin_tick_id": "tick-353",
        "cutoff_snapshot_id": "2004.02.16.08.00.00",
        "cursor": 353,
        "cutoff_source_time": source_time,
        "active_policy_refs": ActivePolicyRefs(
            scoring_version="scoring-v1",
            activation_version="activation-v1",
        ),
        "manifest_projection_ref": "artifact:manifest:353",
        "manifest_projection_sha256": "5" * 64,
        "partition_policy_id": "nasa_ims_run_to_failure_v2",
        "visible_partitions": ("monitoring",),
        "whitelisted_fields": evidence.fields,
        "evidence": (evidence,),
        "created_at": recorded_at,
    }
    view_payload["view_sha256"] = CausalInputView.canonical_sha256(view_payload)
    view = CausalInputView.model_validate(view_payload)
    catalog = build_causal_evidence_catalog(view, records)

    request_payload = {
        "request_id": "monitoring-review:child-001",
        "child_run_id": "child-001",
        "session_id": view.session_id,
        "trigger_id": view.trigger_id,
        "trigger_event_id": view.trigger_event_id,
        "origin_tick_id": view.origin_tick_id,
        "cutoff_snapshot_id": view.cutoff_snapshot_id,
        "cutoff_cursor": view.cursor,
        "cutoff_source_time": view.cutoff_source_time,
        "active_policy_refs": view.active_policy_refs,
        "causal_view_ref": "artifact:causal-view:353",
        "causal_view_sha256": view.view_sha256,
        **monitoring_review_contract_fingerprints(catalog),
        "created_at": recorded_at,
    }
    request_payload["request_sha256"] = MonitoringReviewRequest.canonical_sha256(
        request_payload
    )
    request = MonitoringReviewRequest.model_validate(request_payload)
    llm_payload = {
        "rationale": "The causal prefix warrants cautious observation.",
        "confidence": 0.72,
        "hypothesis": {
            "kind": "routing_readiness",
            "statement": "The algorithmic warning may persist in later frames.",
            "scope": "bearing_1/channel_1",
            "evidence_cutoff": view.cutoff_snapshot_id,
            "expected_observation": "A later permitted score remains elevated.",
            "falsification_criterion": "A later permitted score returns nominal.",
            "evidence_refs": ["E01"],
            "risk_notes": ["This does not prove a physical failure."],
            "assumptions": [],
        },
        "observation_summary": "The visible score is above its threshold.",
        "recommended_action": "maintain_policy",
        "action_rationale": "The review is propose-only.",
        "evidence_refs": ["E01"],
        "alternatives": ["intensify_observation"],
        "requires_human_review": False,
        "memory_mode": "off",
        "policy_application_status": "not_applied",
    }
    decisions = tuple(
        decide_monitoring_review_action(
            agent_name=role,
            request=request,
            causal_view=view,
            evidence_records=records,
            evidence_catalog=catalog,
            llm_client=_JSONClient(llm_payload),
        )
        for role in MONITORING_REVIEW_ROLES
    )
    role_results = tuple(
        MonitoringReviewRoleResult(
            agent_name=decision.agent_name,
            status="completed",
            decision=decision,
            runtime_event_ids=(f"event:{decision.agent_name}",),
        )
        for decision in decisions
    )
    result_payload = {
        "result_id": "child-001:result",
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
        "role_results": role_results,
        "memory_mode": "off",
        "policy_application_status": "not_applied",
        "runtime_events_ref": "artifact:runtime-events:child-001",
        "runtime_events_sha256": "6" * 64,
        "status": "completed",
        "completed_at": recorded_at,
    }
    result_payload["result_sha256"] = MonitoringReviewResult.canonical_sha256(
        result_payload
    )
    result = MonitoringReviewResult.model_validate(result_payload)
    trigger = MonitoringTriggerEvent(
        event_id=view.trigger_event_id,
        trigger_id=view.trigger_id,
        session_id=view.session_id,
        sequence=1,
        trigger_type="state_transition",
        lifecycle_status="emitted",
        priority=90,
        reason_code="health_state_escalation",
        reason="Synthetic sealed trigger for reliability tests.",
        episode_id="episode-001",
        asset_id="bearing_1",
        snapshot_start_id=view.cutoff_snapshot_id,
        snapshot_end_id=view.cutoff_snapshot_id,
        condition_start_cursor=353,
        cutoff_cursor=353,
        cutoff_source_time=source_time,
        previous_state="warning",
        new_state="critical",
        cooldown_source_seconds=51600.0,
        coalescing_group="monitoring_review",
        rearm_policy="after_cooldown",
        requested_roles=MONITORING_REVIEW_ROLES,
        counts_toward_variable_budget=True,
        budget_reservation_index=1,
        dedupe_key="state-transition-353",
        activation_version="activation-v1",
        activation_policy_sha256="7" * 64,
        origin_tick_id=view.origin_tick_id,
        frame_ids=("frame-353",),
        evidence_refs=(evidence_ref,),
        recorded_at=recorded_at,
    )
    return trigger, view, catalog, request, result


def _replace_result_decision(result, decision):
    role_results = list(result.role_results)
    role_results[0] = role_results[0].model_copy(update={"decision": decision})
    payload = result.model_dump(mode="python", exclude={"result_sha256"})
    payload["role_results"] = tuple(role_results)
    payload["result_sha256"] = MonitoringReviewResult.canonical_sha256(payload)
    return MonitoringReviewResult.model_validate(payload)


if __name__ == "__main__":
    unittest.main()
