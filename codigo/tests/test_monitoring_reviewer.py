import copy
import hashlib
import json
import unittest
from collections import Counter
from datetime import UTC, datetime, timedelta
from unittest import mock

from pydantic import ValidationError

import codigo.app.graph.pipeline as pipeline_module
from codigo.app.agents.monitoring_reviewer import (
    decide_monitoring_review_action,
    monitoring_review_contract_fingerprints,
    monitoring_review_llm_response_schema,
)
from codigo.app.graph.pipeline import (
    build_monitoring_review_graph,
    run_monitoring_review_graph,
)
from codigo.app.schemas.monitoring_replay import (
    MONITORING_REVIEW_ROLES,
    ActivePolicyRefs,
    CausalEvidenceArtifact,
    CausalInputView,
    MonitoringReviewRequest,
)
from codigo.app.services.agent_runtime import AgentRuntimeRecorder
from codigo.app.services.monitoring_review_store import (
    build_causal_evidence_catalog,
)


SOURCE_TIME = datetime(2004, 2, 12, 10, 32, 39)
RUNTIME_TIME = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
EVIDENCE_REF = "evidence-tick-001"
SELECTED_HANDLE = "E02"


class FakeJSONLLMClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0
        self.requests = []

    def complete_json(self, messages, *, json_schema=None):
        self.calls += 1
        self.requests.append((list(messages), json_schema))
        if not self.responses:
            raise AssertionError("fake LLM received an unexpected call")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return copy.deepcopy(response)


def _seal(model_class, payload: dict, hash_field: str):
    sealed = dict(payload)
    sealed[hash_field] = model_class.canonical_sha256(sealed)
    return model_class.model_validate(sealed)


def _causal_view() -> CausalInputView:
    evidence_records = _evidence_records()
    evidence_sha256 = hashlib.sha256(
        json.dumps(
            evidence_records,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    evidence = CausalEvidenceArtifact(
        evidence_id=EVIDENCE_REF,
        artifact_ref="artifact:monitoring-evidence:tick-001",
        artifact_sha256=evidence_sha256,
        available_at_cursor=0,
        max_source_time=SOURCE_TIME,
        record_count=len(evidence_records),
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
    payload = {
        "view_id": "causal-view-001",
        "session_id": "nasa-rft-hyb-01",
        "trigger_id": "trigger-001",
        "trigger_event_id": "trigger-001:event:001",
        "origin_tick_id": "tick-001",
        "cutoff_snapshot_id": "2004.02.12.10.32.39",
        "cursor": 0,
        "cutoff_source_time": SOURCE_TIME,
        "active_policy_refs": ActivePolicyRefs(
            scoring_version="scoring-v1",
            activation_version="activation-v1",
        ),
        "manifest_projection_ref": "artifact:manifest-projection:cursor-000",
        "manifest_projection_sha256": "c" * 64,
        "partition_policy_id": "nasa_ims_run_to_failure_v2",
        "visible_partitions": (
            "baseline_train",
            "calibration",
            "monitoring",
        ),
        "whitelisted_fields": evidence.fields,
        "evidence": (evidence,),
        "created_at": RUNTIME_TIME,
    }
    return _seal(CausalInputView, payload, "view_sha256")


def _request(view: CausalInputView) -> MonitoringReviewRequest:
    payload = {
        "request_id": "monitoring-review-request-001",
        "child_run_id": "monitoring-child-001",
        "session_id": view.session_id,
        "trigger_id": view.trigger_id,
        "trigger_event_id": view.trigger_event_id,
        "origin_tick_id": view.origin_tick_id,
        "cutoff_snapshot_id": view.cutoff_snapshot_id,
        "cutoff_cursor": view.cursor,
        "cutoff_source_time": view.cutoff_source_time,
        "active_policy_refs": view.active_policy_refs,
        "causal_view_ref": "artifact:causal-view:001",
        "causal_view_sha256": view.view_sha256,
        **monitoring_review_contract_fingerprints(_catalog(view)),
        "created_at": RUNTIME_TIME,
    }
    return _seal(MonitoringReviewRequest, payload, "request_sha256")


def _evidence_records() -> list[dict]:
    records = []
    for index, state in enumerate(("nominal", "warning", "warning"), start=1):
        observed_at = SOURCE_TIME - timedelta(minutes=10 * (3 - index))
        records.append({
            "record_id": f"monitoring-frame-{index:03d}",
            "asset_id": "bearing_1",
            "channel_id": "channel_1",
            "snapshot_id": observed_at.strftime("%Y.%m.%d.%H.%M.%S"),
            "source_time": observed_at.isoformat(),
            "analysis_status": "modeled",
            "score": 0.45 + index * 0.10,
            "threshold": 0.60,
            "health_state": state,
        })
    return records


def _catalog(view: CausalInputView):
    return build_causal_evidence_catalog(view, _evidence_records())


def _support_ref(view: CausalInputView, handle: str = SELECTED_HANDLE) -> str:
    return next(
        item.support_ref for item in _catalog(view).entries if item.handle == handle
    )


def _llm_payload(**updates) -> dict:
    payload = {
        # Campos hostiles: el servidor debe sustituirlos, no confiar en ellos.
        "decision_id": "llm-owned-decision-id",
        "decision_sha256": "0" * 64,
        "agent_name": "modeler",
        "decision_kind": "monitoring_review",
        "child_run_id": "llm-owned-child-run",
        "trigger_event_id": "future-trigger:event:999",
        "cutoff_snapshot_id": "future-snapshot",
        "cutoff_cursor": 999,
        "cutoff_source_time": "2099-01-01T00:00:00",
        "causal_view_sha256": "9" * 64,
        "rationale": "The visible prefix warrants cautious observation.",
        "confidence": 0.71,
        "hypothesis": {
            "kind": "revision_effectiveness",
            "statement": "The warning may persist in subsequent causal frames.",
            "scope": "bearing_1/channel_1",
            "evidence_cutoff": "future-snapshot",
            "expected_observation": "The visible score remains above threshold.",
            "falsification_criterion": "A later permitted frame returns healthy.",
            "evidence_refs": [SELECTED_HANDLE],
            "risk_notes": ["Replay evidence does not prove a physical failure."],
            "assumptions": [],
        },
        "generation_trace": {
            "origin": "deterministic",
            "attempt_id": "llm-owned-attempt",
            "attempt_index": 99,
            "validation_status": "validated",
        },
        "observation_summary": "The current modeled channel is warning.",
        "recommended_action": "maintain_policy",
        "action_rationale": "The frozen policy cannot be changed by this review.",
        "evidence_refs": [SELECTED_HANDLE],
        "alternatives": ["intensify_observation"],
        "requires_human_review": False,
        "memory_mode": "on",
        "policy_application_status": "applied",
        "created_at": "2099-01-01T00:00:00Z",
    }
    payload.update(updates)
    return payload


def _llm_payload_with_unsupported_claim(field_path: str) -> dict:
    payload = _llm_payload()
    claim = "Fallo detectado y confirmado en el rodamiento fisico."
    if field_path.startswith("hypothesis."):
        field_name = field_path.removeprefix("hypothesis.")
        if field_name in {"risk_notes", "assumptions"}:
            payload["hypothesis"][field_name] = [claim]
        else:
            payload["hypothesis"][field_name] = claim
    else:
        payload[field_path] = claim
    return payload


class MonitoringReviewerAgentTests(unittest.TestCase):
    def test_llm_schema_closes_both_evidence_fields_to_exact_record_handles(self):
        view = _causal_view()
        schema = monitoring_review_llm_response_schema(_catalog(view))
        decision_refs = schema["properties"]["evidence_refs"]
        hypothesis_refs = schema["$defs"]["AgentHypothesis"]["properties"][
            "evidence_refs"
        ]

        for refs in (decision_refs, hypothesis_refs):
            self.assertEqual(refs["minItems"], 1)
            self.assertEqual(refs["maxItems"], 3)
            self.assertTrue(refs["uniqueItems"])
            self.assertEqual(
                refs["items"]["enum"],
                ["E01", "E02", "E03"],
            )

    def test_server_owns_identity_cutoff_trace_memory_and_policy_fields(self):
        view = _causal_view()
        request = _request(view)
        client = FakeJSONLLMClient([_llm_payload()])

        decision = decide_monitoring_review_action(
            agent_name="evaluator",
            request=request,
            causal_view=view,
            evidence_records=_evidence_records(),
            allowed_evidence_refs=(EVIDENCE_REF,),
            llm_client=client,
        )

        self.assertEqual(decision.decision_id, "monitoring-child-001:evaluator:001")
        self.assertEqual(decision.agent_name, "evaluator")
        self.assertEqual(decision.child_run_id, request.child_run_id)
        self.assertEqual(decision.trigger_event_id, request.trigger_event_id)
        self.assertEqual(decision.cutoff_snapshot_id, request.cutoff_snapshot_id)
        self.assertEqual(decision.cutoff_cursor, request.cutoff_cursor)
        self.assertEqual(decision.cutoff_source_time, request.cutoff_source_time)
        self.assertEqual(decision.causal_view_sha256, view.view_sha256)
        self.assertEqual(decision.hypothesis.kind, "operational_acceptance")
        self.assertEqual(
            decision.hypothesis.evidence_cutoff,
            request.cutoff_snapshot_id,
        )
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.attempt_index, 1)
        self.assertEqual(decision.memory_mode, "off")
        self.assertEqual(decision.policy_application_status, "not_applied")
        selected_ref = _support_ref(view)
        self.assertEqual(decision.evidence_refs, (selected_ref,))
        self.assertEqual(decision.hypothesis.evidence_refs, [selected_ref])
        prompt = client.requests[0][0][-1].content
        self.assertIn(SELECTED_HANDLE, prompt)
        self.assertNotIn(EVIDENCE_REF, prompt)
        self.assertNotIn("monitoring-frame-002", prompt)
        self.assertEqual(
            decision.decision_sha256,
            type(decision).canonical_sha256(decision),
        )

    def test_multiple_handles_materialize_only_the_selected_records(self):
        view = _causal_view()
        request = _request(view)
        selected = ["E01", "E03"]
        payload = _llm_payload(
            evidence_refs=selected,
            hypothesis={
                **_llm_payload()["hypothesis"],
                "evidence_refs": selected,
            },
        )

        decision = decide_monitoring_review_action(
            agent_name="modeler",
            request=request,
            causal_view=view,
            evidence_records=_evidence_records(),
            evidence_catalog=_catalog(view),
            llm_client=FakeJSONLLMClient([payload]),
        )

        expected = (_support_ref(view, "E01"), _support_ref(view, "E03"))
        self.assertEqual(decision.evidence_refs, expected)
        self.assertEqual(tuple(decision.hypothesis.evidence_refs), expected)
        self.assertNotIn(_support_ref(view, "E02"), decision.evidence_refs)

    def test_decision_and_hypothesis_handle_mismatch_repairs_exactly_once(self):
        view = _causal_view()
        request = _request(view)
        mismatch = _llm_payload(
            evidence_refs=["E01"],
            hypothesis={
                **_llm_payload()["hypothesis"],
                "evidence_refs": ["E02"],
            },
        )
        client = FakeJSONLLMClient([mismatch, _llm_payload()])

        decision = decide_monitoring_review_action(
            agent_name="structurer",
            request=request,
            causal_view=view,
            evidence_records=_evidence_records(),
            evidence_catalog=_catalog(view),
            llm_client=client,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.generation_trace.validation_status, "repaired")
        self.assertEqual(decision.evidence_refs, (_support_ref(view),))

    def test_refs_and_evidence_records_must_belong_to_causal_view(self):
        view = _causal_view()
        request = _request(view)
        client = FakeJSONLLMClient([_llm_payload()])

        with self.assertRaisesRegex(ValueError, "causal view"):
            decide_monitoring_review_action(
                agent_name="modeler",
                request=request,
                causal_view=view,
                evidence_records=_evidence_records(),
                allowed_evidence_refs=("not-in-causal-view",),
                llm_client=client,
            )
        self.assertEqual(client.calls, 0)

        leaked_records = [
            {
                **_evidence_records()[0],
                "raw_path": "/secret/raw/future-suffix.csv",
            }
        ]
        with self.assertRaisesRegex(ValueError, "sealed artifact"):
            decide_monitoring_review_action(
                agent_name="modeler",
                request=request,
                causal_view=view,
                evidence_records=leaked_records,
                allowed_evidence_refs=(EVIDENCE_REF,),
                llm_client=FakeJSONLLMClient([_llm_payload()]),
            )

        future_records = [
            {
                **_evidence_records()[0],
                "source_time": "2099-01-01T00:00:00",
            }
        ]
        with self.assertRaisesRegex(ValueError, "sealed artifact"):
            decide_monitoring_review_action(
                agent_name="modeler",
                request=request,
                causal_view=view,
                evidence_records=future_records,
                allowed_evidence_refs=(EVIDENCE_REF,),
                llm_client=FakeJSONLLMClient([_llm_payload()]),
            )

    def test_canonical_or_record_ref_from_llm_repairs_to_closed_handle(self):
        view = _causal_view()
        request = _request(view)
        invalid = _llm_payload(
            evidence_refs=[EVIDENCE_REF],
            hypothesis={
                **_llm_payload()["hypothesis"],
                "evidence_refs": ["monitoring-frame-001"],
            },
        )
        client = FakeJSONLLMClient([invalid, _llm_payload()])

        decision = decide_monitoring_review_action(
            agent_name="supervisor",
            request=request,
            causal_view=view,
            evidence_records=_evidence_records(),
            allowed_evidence_refs=(EVIDENCE_REF,),
            llm_client=client,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.generation_trace.validation_status, "repaired")
        selected_ref = _support_ref(view)
        self.assertEqual(decision.evidence_refs, (selected_ref,))
        self.assertEqual(decision.hypothesis.evidence_refs, [selected_ref])
        repair_prompt = client.requests[1][0][-1].content
        self.assertIn(SELECTED_HANDLE, repair_prompt)
        self.assertNotIn(EVIDENCE_REF, repair_prompt)

    def test_repeated_invalid_handle_uses_grounded_fallback(self):
        view = _causal_view()
        request = _request(view)
        unhashable_ref = _llm_payload(evidence_refs=[{"record_id": "frame-1"}])
        padded_ref = _llm_payload(
            evidence_refs=[f" {SELECTED_HANDLE} "],
        )
        client = FakeJSONLLMClient([unhashable_ref, padded_ref])

        decision = decide_monitoring_review_action(
            agent_name="cleaner",
            request=request,
            causal_view=view,
            evidence_records=_evidence_records(),
            allowed_evidence_refs=(EVIDENCE_REF,),
            llm_client=client,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.generation_trace.origin, "guardrail_fallback")
        self.assertEqual(decision.generation_trace.attempt_index, 3)
        fallback_ref = _support_ref(view, "E03")
        self.assertEqual(decision.evidence_refs, (fallback_ref,))
        self.assertEqual(decision.hypothesis.evidence_refs, [fallback_ref])
        for _, schema in client.requests:
            self.assertEqual(
                schema["properties"]["evidence_refs"]["items"]["enum"],
                ["E01", "E02", "E03"],
            )

    def test_prior_decision_from_another_review_is_rejected_before_llm(self):
        view = _causal_view()
        request = _request(view)
        prior = decide_monitoring_review_action(
            agent_name="supervisor",
            request=request,
            causal_view=view,
            evidence_records=_evidence_records(),
            allowed_evidence_refs=(EVIDENCE_REF,),
            llm_client=FakeJSONLLMClient([_llm_payload()]),
        )
        foreign = prior.model_copy(update={"child_run_id": "another-child"})
        client = FakeJSONLLMClient([_llm_payload()])

        with self.assertRaisesRegex(ValueError, "same causal review"):
            decide_monitoring_review_action(
                agent_name="cleaner",
                request=request,
                causal_view=view,
                evidence_records=_evidence_records(),
                allowed_evidence_refs=(EVIDENCE_REF,),
                prior_decisions=(foreign,),
                llm_client=client,
            )

        self.assertEqual(client.calls, 0)

    def test_every_free_text_rejects_unsupported_official_v2_claim_and_repairs(self):
        view = _causal_view()
        request = _request(view)
        free_text_fields = (
            "rationale",
            "observation_summary",
            "action_rationale",
            "hypothesis.statement",
            "hypothesis.scope",
            "hypothesis.expected_observation",
            "hypothesis.falsification_criterion",
            "hypothesis.risk_notes",
            "hypothesis.assumptions",
        )

        for field_path in free_text_fields:
            with self.subTest(field_path=field_path):
                client = FakeJSONLLMClient(
                    [
                        _llm_payload_with_unsupported_claim(field_path),
                        _llm_payload(),
                    ]
                )

                decision = decide_monitoring_review_action(
                    agent_name="evaluator",
                    request=request,
                    causal_view=view,
                    evidence_records=_evidence_records(),
                    allowed_evidence_refs=(EVIDENCE_REF,),
                    llm_client=client,
                )

                self.assertEqual(client.calls, 2)
                self.assertEqual(decision.generation_trace.origin, "llm")
                self.assertEqual(decision.generation_trace.attempt_index, 2)
                self.assertEqual(
                    decision.generation_trace.validation_status,
                    "repaired",
                )
                repair_prompt = client.requests[1][0][-1].content
                self.assertIn("detected_physical_failure", repair_prompt)
                self.assertIn("hypothesis.scope", repair_prompt)

    def test_repeated_unsupported_official_v2_claim_falls_back_after_one_retry(self):
        view = _causal_view()
        request = _request(view)
        client = FakeJSONLLMClient(
            [
                _llm_payload_with_unsupported_claim("hypothesis.scope"),
                _llm_payload_with_unsupported_claim("hypothesis.assumptions"),
            ]
        )

        decision = decide_monitoring_review_action(
            agent_name="evaluator",
            request=request,
            causal_view=view,
            evidence_records=_evidence_records(),
            allowed_evidence_refs=(EVIDENCE_REF,),
            llm_client=client,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.generation_trace.origin, "guardrail_fallback")
        self.assertEqual(decision.generation_trace.attempt_index, 3)
        self.assertEqual(
            decision.generation_trace.validation_status,
            "fallback_applied",
        )
        self.assertIn(
            "detected_physical_failure",
            decision.generation_trace.fallback_cause,
        )


class MonitoringReviewGraphTests(unittest.TestCase):
    def test_build_has_only_the_fixed_seven_role_chain(self):
        graph = build_monitoring_review_graph(
            runtime_recorder=AgentRuntimeRecorder(
                "monitoring-child-001",
                lambda _: None,
            ),
            use_llm=False,
        ).get_graph()

        self.assertEqual(
            set(graph.nodes),
            {"__start__", *MONITORING_REVIEW_ROLES, "__end__"},
        )
        self.assertEqual(
            set((edge.source, edge.target) for edge in graph.edges),
            {
                ("__start__", MONITORING_REVIEW_ROLES[0]),
                *zip(
                    MONITORING_REVIEW_ROLES[:-1],
                    MONITORING_REVIEW_ROLES[1:],
                    strict=True,
                ),
                (MONITORING_REVIEW_ROLES[-1], "__end__"),
            },
        )

    def test_run_orders_seven_roles_counts_repair_and_fallback_without_side_paths(self):
        view = _causal_view()
        request = _request(view)
        invalid_ref = _llm_payload(
            evidence_refs=["not-visible"],
            hypothesis={
                **_llm_payload()["hypothesis"],
                "evidence_refs": ["not-visible"],
            },
        )
        invalid_action = _llm_payload(recommended_action="fit_new_model")
        client = FakeJSONLLMClient(
            [
                _llm_payload(),
                invalid_ref,
                _llm_payload(),
                invalid_action,
                invalid_action,
                _llm_payload(),
                _llm_payload(),
                _llm_payload(),
                _llm_payload(),
            ]
        )
        events = []
        recorder = AgentRuntimeRecorder(request.child_run_id, events.append)

        forbidden = mock.Mock(side_effect=AssertionError("forbidden side path"))
        with mock.patch.multiple(
            pipeline_module,
            generate_cwru_manifest=forbidden,
            generate_data_profile=forbidden,
            generate_clean_signals=forbidden,
            generate_temporal_structure=forbidden,
            generate_model_outputs=forbidden,
            generate_evaluation_report=forbidden,
            generate_technical_report=forbidden,
            call_agent_with_optional_memory=forbidden,
            retrieve_structurer_memory_context=forbidden,
            retrieve_modeler_memory_context=forbidden,
            retrieve_evaluator_memory_context=forbidden,
            write_decision_memory_artifacts=forbidden,
        ):
            final = run_monitoring_review_graph(
                request=request,
                causal_view=view,
                evidence_records=_evidence_records(),
                allowed_evidence_refs=(EVIDENCE_REF,),
                runtime_recorder=recorder,
                llm_client=client,
            )

        decisions = final["decisions"]
        self.assertEqual(
            tuple(item["agent_name"] for item in decisions),
            MONITORING_REVIEW_ROLES,
        )
        self.assertEqual(client.calls, 9)
        traces = Counter(
            (
                item["generation_trace"]["origin"],
                item["generation_trace"]["validation_status"],
            )
            for item in decisions
        )
        self.assertEqual(
            traces,
            Counter(
                {
                    ("llm", "validated"): 5,
                    ("llm", "repaired"): 1,
                    ("guardrail_fallback", "fallback_applied"): 1,
                }
            ),
        )
        self.assertEqual(
            tuple(item["hypothesis"]["kind"] for item in decisions),
            (
                "routing_readiness",
                "data_quality",
                "temporal_representation",
                "model_performance",
                "operational_acceptance",
                "report_grounding",
                "report_fidelity",
            ),
        )
        self.assertEqual(decisions[1]["generation_trace"]["attempt_index"], 2)
        self.assertEqual(decisions[2]["generation_trace"]["attempt_index"], 3)
        self.assertEqual(
            decisions[2]["generation_trace"]["fallback_from_attempt_id"],
            "monitoring-child-001:structurer:001:attempt:002",
        )
        self.assertTrue(
            all(item["hypothesis"]["evidence_refs"] for item in decisions)
        )
        allowed_support = {
            item.support_ref for item in _catalog(view).entries
        }
        self.assertTrue(
            all(set(item["evidence_refs"]).issubset(allowed_support) for item in decisions)
        )
        self.assertTrue(all(item["memory_mode"] == "off" for item in decisions))
        self.assertTrue(
            all(
                item["policy_application_status"] == "not_applied"
                for item in decisions
            )
        )
        self.assertEqual(
            [
                event.payload["evidence_binding"]["selection_origin"]
                for event in events
            ],
            [
                "agent",
                "agent",
                "server_fallback",
                "agent",
                "agent",
                "agent",
                "agent",
            ],
        )
        self.assertEqual(
            [event.agent_name for event in events],
            list(MONITORING_REVIEW_ROLES),
        )
        self.assertEqual(len(events), 7)
        self.assertTrue(all(event.memory_context_id is None for event in events))
        self.assertTrue(all(event.memory_record_ids == [] for event in events))
        self.assertTrue(
            all(
                event.payload["evidence_binding"]["mode"]
                == "server_record_catalog"
                and event.payload["evidence_binding"]["catalog_sha256"]
                == _catalog(view).catalog_sha256
                and event.payload["evidence_binding"]["available_handles"]
                == ["E01", "E02", "E03"]
                and event.payload["evidence_binding"]["support_refs"]
                == event.payload["decision"]["evidence_refs"]
                for event in events
            )
        )
        self.assertEqual(
            tuple(final["runtime_event_ids"]),
            MONITORING_REVIEW_ROLES,
        )
        all_prompt_text = "\n".join(
            message.content
            for messages, _ in client.requests
            for message in messages
        )
        self.assertNotIn("/secret/raw", all_prompt_text)
        forbidden.assert_not_called()


if __name__ == "__main__":
    unittest.main()
