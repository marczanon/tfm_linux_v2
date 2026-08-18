import json
import tempfile
import unittest
from pathlib import Path

from codigo.app.schemas.agent_runtime import AgentRuntimeEvent
from codigo.app.schemas.monitoring_replay import (
    CausalEvidenceCatalog,
    CausalEvidenceCatalogEntry,
    MONITORING_REVIEW_ROLES,
    MonitoringReviewDecision,
    MonitoringReviewRequest,
    MonitoringReviewResult,
    MonitoringReviewRoleResult,
)
from codigo.app.services.run_persistence import (
    load_run_runtime_events,
    save_monitoring_review_snapshot,
    serialized_json_sha256,
)
from codigo.tests.test_monitoring_replay_schema import (
    make_review_decision,
    make_review_request,
    make_review_result,
)


SUPPORT_REF = "causal-record:" + "a" * 64 + ":" + "b" * 64
SECOND_SUPPORT_REF = "causal-record:" + "a" * 64 + ":" + "c" * 64
SCOPE_REF = "evidence:monitoring-child-001:trigger-001"


class MonitoringReviewCatalogPersistenceTests(unittest.TestCase):
    def test_persists_catalog_as_artifact_and_evidence_pack_binding(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            request, result, decisions, events, catalog = _sealed_review(runs_dir)

            snapshot = save_monitoring_review_snapshot(
                request=request,
                result=result,
                decisions=decisions,
                runtime_events=events,
                evidence_catalog=catalog,
                output_dir=runs_dir,
            )

            run_dir = Path(snapshot.snapshot_dir)
            stored_catalog = CausalEvidenceCatalog.model_validate(
                _read_json(run_dir / "monitoring_review_evidence_catalog.json")
            )
            artifacts = _read_json(run_dir / "artifacts.json")
            evidence_pack = _read_json(run_dir / "evidence_pack.json")

        self.assertEqual(stored_catalog, catalog)
        self.assertEqual(snapshot.n_artifacts, 5)
        catalog_artifact = next(
            item
            for item in artifacts
            if item["name"] == "monitoring_review_evidence_catalog"
        )
        self.assertEqual(
            catalog_artifact["metadata"]["sha256"],
            catalog.catalog_sha256,
        )
        self.assertEqual(
            evidence_pack["evidence_catalog"],
            {
                "entry_count": 2,
                "ref": (
                    run_dir / "monitoring_review_evidence_catalog.json"
                ).as_posix(),
                "sha256": catalog.catalog_sha256,
            },
        )

    def test_rejects_runtime_handle_that_does_not_resolve_to_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            request, _, decisions, events, catalog = _sealed_review(runs_dir)
            altered_events = list(events)
            altered_payload = dict(altered_events[0].payload)
            altered_binding = dict(altered_payload["evidence_binding"])
            altered_binding["selected_handles"] = ["E99"]
            altered_payload["evidence_binding"] = altered_binding
            altered_events[0] = altered_events[0].model_copy(
                update={"payload": altered_payload}
            )
            altered_result = _result_for(
                request=request,
                decisions=decisions,
                events=altered_events,
                runs_dir=runs_dir,
            )

            with self.assertRaisesRegex(ValueError, "outside the catalog"):
                save_monitoring_review_snapshot(
                    request=request,
                    result=altered_result,
                    decisions=decisions,
                    runtime_events=altered_events,
                    evidence_catalog=catalog,
                    output_dir=runs_dir,
                )

    def test_rejects_hypothesis_refs_that_do_not_match_decision_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            request, _, decisions, events, catalog = _sealed_review(runs_dir)
            altered_decisions = list(decisions)
            altered_payload = altered_decisions[0].model_dump(
                mode="python",
                exclude={"decision_sha256"},
            )
            altered_payload["evidence_refs"] = (
                SUPPORT_REF,
                SECOND_SUPPORT_REF,
            )
            altered_payload["decision_sha256"] = (
                MonitoringReviewDecision.canonical_sha256(altered_payload)
            )
            altered_decisions[0] = MonitoringReviewDecision.model_validate(
                altered_payload
            )
            altered_events = list(events)
            altered_event_payload = dict(altered_events[0].payload)
            altered_event_payload["decision"] = altered_decisions[0].model_dump(
                mode="json"
            )
            altered_binding = dict(altered_event_payload["evidence_binding"])
            altered_binding["selected_handles"] = ["E01", "E02"]
            altered_binding["support_refs"] = [
                SUPPORT_REF,
                SECOND_SUPPORT_REF,
            ]
            altered_event_payload["evidence_binding"] = altered_binding
            altered_events[0] = altered_events[0].model_copy(
                update={"payload": altered_event_payload}
            )
            altered_result = _result_for(
                request=request,
                decisions=altered_decisions,
                events=altered_events,
                runs_dir=runs_dir,
            )

            with self.assertRaisesRegex(ValueError, "hypothesis refs must match"):
                save_monitoring_review_snapshot(
                    request=request,
                    result=altered_result,
                    decisions=altered_decisions,
                    runtime_events=altered_events,
                    evidence_catalog=catalog,
                    output_dir=runs_dir,
                )

    def test_record_catalog_runtime_cannot_be_saved_without_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            request, result, decisions, events, _ = _sealed_review(runs_dir)

            with self.assertRaisesRegex(ValueError, "require an evidence catalog"):
                save_monitoring_review_snapshot(
                    request=request,
                    result=result,
                    decisions=decisions,
                    runtime_events=events,
                    output_dir=runs_dir,
                )

    def test_runtime_loader_rejects_tampered_monitoring_event_projection(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            request, result, decisions, events, catalog = _sealed_review(runs_dir)
            snapshot = save_monitoring_review_snapshot(
                request=request,
                result=result,
                decisions=decisions,
                runtime_events=events,
                evidence_catalog=catalog,
                output_dir=runs_dir,
            )
            events_path = Path(snapshot.snapshot_dir) / "monitoring_review_events.json"
            payload = _read_json(events_path)
            payload[0]["payload"]["evidence_binding"]["selected_records"][0][
                "health_state"
            ] = "critical"
            events_path.write_text(json.dumps(payload), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "sealed result"):
                load_run_runtime_events(request.child_run_id, runs_dir)

    def test_runtime_loader_accepts_a_sealed_legacy_result_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            request, result, decisions, events, catalog = _sealed_review(runs_dir)
            snapshot = save_monitoring_review_snapshot(
                request=request,
                result=result,
                decisions=decisions,
                runtime_events=events,
                evidence_catalog=catalog,
                output_dir=runs_dir,
            )
            run_dir = Path(snapshot.snapshot_dir)
            request_path = run_dir / "monitoring_review_request.json"
            legacy_request = _read_json(request_path)
            legacy_request.update(
                {
                    "prompt_template_id": "monitoring_review_prompt_v1",
                    "prompt_template_sha256": (
                        "4c3a82722ffdda407d5b173277f3ef33e0ad1099f43c9fa91a00ee832ae788b4"
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
            )
            legacy_request["request_sha256"] = (
                MonitoringReviewRequest.canonical_sha256(legacy_request)
            )
            MonitoringReviewRequest.model_validate(legacy_request)
            request_path.write_text(
                json.dumps(legacy_request, ensure_ascii=True, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            (run_dir / "monitoring_review_evidence_catalog.json").unlink()
            result_path = Path(snapshot.snapshot_dir) / "monitoring_review_result.json"
            legacy_payload = _read_json(result_path)
            legacy_payload["request_sha256"] = legacy_request["request_sha256"]
            legacy_decision = legacy_payload["role_results"][0]["decision"]
            legacy_trace = legacy_decision["generation_trace"]
            legacy_trace.update(
                {
                    "origin": "guardrail_fallback",
                    "attempt_id": f"{legacy_decision['decision_id']}:attempt:003",
                    "attempt_index": 3,
                    "validation_status": "fallback_applied",
                    "fallback_cause": "legacy diagnostic fallback",
                    "fallback_from_attempt_id": (
                        f"{legacy_decision['decision_id']}:attempt:002"
                    ),
                }
            )
            legacy_decision["decision_sha256"] = (
                MonitoringReviewDecision.canonical_sha256(legacy_decision)
            )
            legacy_payload["result_sha256"] = (
                MonitoringReviewResult.canonical_sha256(legacy_payload)
            )
            result_path.write_text(
                json.dumps(legacy_payload, ensure_ascii=True, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "guardrail fallback decisions cannot be marked completed",
            ):
                MonitoringReviewResult.model_validate(legacy_payload)
            loaded = load_run_runtime_events(request.child_run_id, runs_dir)

        self.assertEqual(
            [event.event_id for event in loaded],
            [event.event_id for event in events],
        )

    def test_runtime_loader_rejects_an_invalid_current_result_shape(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            request, result, decisions, events, catalog = _sealed_review(runs_dir)
            snapshot = save_monitoring_review_snapshot(
                request=request,
                result=result,
                decisions=decisions,
                runtime_events=events,
                evidence_catalog=catalog,
                output_dir=runs_dir,
            )
            result_path = Path(snapshot.snapshot_dir) / "monitoring_review_result.json"
            invalid_payload = _read_json(result_path)
            invalid_decision = invalid_payload["role_results"][0]["decision"]
            invalid_trace = invalid_decision["generation_trace"]
            invalid_trace.update(
                {
                    "origin": "guardrail_fallback",
                    "attempt_id": f"{invalid_decision['decision_id']}:attempt:003",
                    "attempt_index": 3,
                    "validation_status": "fallback_applied",
                    "fallback_cause": "invalid current fallback",
                    "fallback_from_attempt_id": (
                        f"{invalid_decision['decision_id']}:attempt:002"
                    ),
                }
            )
            invalid_decision["decision_sha256"] = (
                MonitoringReviewDecision.canonical_sha256(invalid_decision)
            )
            invalid_payload["result_sha256"] = (
                MonitoringReviewResult.canonical_sha256(invalid_payload)
            )
            result_path.write_text(
                json.dumps(invalid_payload, ensure_ascii=True, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "legacy compatibility"):
                load_run_runtime_events(request.child_run_id, runs_dir)

    def test_runtime_loader_fails_closed_when_review_result_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            request, result, decisions, events, catalog = _sealed_review(runs_dir)
            snapshot = save_monitoring_review_snapshot(
                request=request,
                result=result,
                decisions=decisions,
                runtime_events=events,
                evidence_catalog=catalog,
                output_dir=runs_dir,
            )
            (Path(snapshot.snapshot_dir) / "monitoring_review_result.json").unlink()

            with self.assertRaisesRegex(ValueError, "result is unavailable"):
                load_run_runtime_events(request.child_run_id, runs_dir)


def _sealed_review(runs_dir: Path):
    request = make_review_request()
    catalog = _catalog(request.causal_view_sha256)
    decisions = [
        _decision_with_support(role, SUPPORT_REF)
        for role in MONITORING_REVIEW_ROLES
    ]
    events = [
        _runtime_event(
            decision,
            sequence=index,
            catalog=catalog,
        )
        for index, decision in enumerate(decisions, start=1)
    ]
    result = _result_for(
        request=request,
        decisions=decisions,
        events=events,
        runs_dir=runs_dir,
    )
    return request, result, decisions, events, catalog


def _catalog(causal_view_sha256: str) -> CausalEvidenceCatalog:
    entries = (
        CausalEvidenceCatalogEntry(
            handle="E01",
            record_index=0,
            causal_scope_ref=SCOPE_REF,
            support_ref=SUPPORT_REF,
            record_id="monitoring-child-001:tick:000000:bearing_1:channel_1",
            record_sha256="b" * 64,
            display_projection_sha256=_projection_sha("E01", "b" * 64),
        ),
        CausalEvidenceCatalogEntry(
            handle="E02",
            record_index=1,
            causal_scope_ref=SCOPE_REF,
            support_ref=SECOND_SUPPORT_REF,
            record_id="monitoring-child-001:tick:000001:bearing_1:channel_1",
            record_sha256="c" * 64,
            display_projection_sha256=_projection_sha("E02", "c" * 64),
        ),
    )
    payload = {
        "catalog_id": "causal-evidence-catalog:test",
        "causal_view_sha256": causal_view_sha256,
        "source_artifact_sha256": "a" * 64,
        "causal_scope_refs": (SCOPE_REF,),
        "entries": entries,
    }
    payload["catalog_sha256"] = CausalEvidenceCatalog.canonical_sha256(payload)
    return CausalEvidenceCatalog.model_validate(payload)


def _decision_with_support(
    agent_name: str,
    support_ref: str,
) -> MonitoringReviewDecision:
    original = make_review_decision(agent_name)
    payload = original.model_dump(mode="python", exclude={"decision_sha256"})
    hypothesis = dict(payload["hypothesis"])
    hypothesis["evidence_refs"] = [support_ref]
    payload["hypothesis"] = hypothesis
    payload["evidence_refs"] = (support_ref,)
    payload["decision_sha256"] = MonitoringReviewDecision.canonical_sha256(
        payload
    )
    return MonitoringReviewDecision.model_validate(payload)


def _runtime_event(
    decision: MonitoringReviewDecision,
    *,
    sequence: int,
    catalog: CausalEvidenceCatalog,
) -> AgentRuntimeEvent:
    return AgentRuntimeEvent(
        event_id=f"monitoring-child-001:{decision.agent_name}:completed",
        run_id=decision.child_run_id,
        sequence=sequence,
        kind=(
            "supervisor_decision"
            if decision.agent_name == "supervisor"
            else "agent_decision"
        ),
        source="supervisor" if decision.agent_name == "supervisor" else "agent",
        title=f"Decision {decision.agent_name}",
        summary=decision.observation_summary,
        stage="monitoring_review",
        node=f"{decision.agent_name}_monitoring_review",
        agent_name=decision.agent_name,
        decision_id=decision.decision_id,
        rationale=decision.rationale,
        confidence=decision.confidence,
        payload={
            "causal_view_sha256": decision.causal_view_sha256,
            "evidence_binding": {
                "mode": "server_record_catalog",
                "selection_origin": "agent",
                "catalog_sha256": catalog.catalog_sha256,
                "available_count": 2,
                "available_handles": ["E01", "E02"],
                "selected_handles": ["E01"],
                "causal_scope_refs": [SCOPE_REF],
                "support_refs": [SUPPORT_REF],
                "selected_records": [
                    _projection("E01", "b" * 64)
                ],
            },
            "decision": decision.model_dump(mode="json"),
        },
    )


def _result_for(
    *,
    request,
    decisions: list[MonitoringReviewDecision],
    events: list[AgentRuntimeEvent],
    runs_dir: Path,
) -> MonitoringReviewResult:
    original = make_review_result()
    payload = original.model_dump(mode="python", exclude={"result_sha256"})
    payload.update(
        {
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
            "role_results": tuple(
                MonitoringReviewRoleResult(
                    agent_name=decision.agent_name,
                    status="completed",
                    decision=decision,
                    runtime_event_ids=(
                        f"monitoring-child-001:{decision.agent_name}:completed",
                    ),
                )
                for decision in decisions
            ),
            "runtime_events_ref": (
                runs_dir
                / request.child_run_id
                / "monitoring_review_events.json"
            ).as_posix(),
            "runtime_events_sha256": serialized_json_sha256(
                [event.model_dump(mode="json") for event in events]
            ),
        }
    )
    payload["result_sha256"] = MonitoringReviewResult.canonical_sha256(payload)
    return MonitoringReviewResult.model_validate(payload)


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _projection(handle: str, record_sha256: str) -> dict:
    return {
        "handle": handle,
        "record_sha256": record_sha256,
        "snapshot_id": None,
        "source_time": None,
        "asset_id": None,
        "channel_id": None,
        "analysis_status": None,
        "score_ratio": None,
        "health_state": None,
        "gap_detected": None,
    }


def _projection_sha(handle: str, record_sha256: str) -> str:
    import hashlib

    return hashlib.sha256(
        json.dumps(
            _projection(handle, record_sha256),
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


if __name__ == "__main__":
    unittest.main()
