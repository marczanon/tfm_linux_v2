import asyncio
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx

import codigo.app.services.pipeline_runner as pipeline_runner_module
from codigo.app.api import create_app
from codigo.app.schemas.monitoring_replay import (
    MONITORING_REVIEW_ROLES,
    MonitoringPolicyProposal,
    MonitoringReviewDecision,
    MonitoringReviewRequest,
    MonitoringReviewResult,
)
from codigo.app.services.agent_runtime import AgentRuntimeRecorder
from codigo.app.services.llm import LLMCallError
from codigo.app.services.monitoring_replay import MonitoringReplayConflictError
from codigo.app.services.monitoring_review_store import (
    build_causal_evidence_catalog,
)
from codigo.app.services.pipeline_runner import run_monitoring_review
from codigo.app.services.run_persistence import (
    load_run_index,
    load_run_runtime_events,
    load_run_snapshot,
    save_monitoring_review_snapshot,
)
from codigo.tests.test_monitoring_reviewer import (
    FakeJSONLLMClient,
    _causal_view,
    _evidence_records,
    _llm_payload,
    _request,
)


class MonitoringReviewPersistenceTests(unittest.TestCase):
    def test_loader_rejects_removal_of_proposal_and_its_runtime_event(self):
        view = _causal_view()
        request = _request(view)
        recorder = AgentRuntimeRecorder(request.child_run_id, lambda _: None)

        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            execution = run_monitoring_review(
                request,
                view,
                _evidence_records(),
                runs_dir=runs_dir,
                runtime_recorder=recorder,
                use_llm=False,
            )
            run_dir = Path(execution.snapshot.snapshot_dir)
            (run_dir / "monitoring_policy_proposal.json").unlink()
            events_path = run_dir / "monitoring_review_events.json"
            events_payload = _read_json(events_path)
            self.assertEqual(events_payload[-1]["kind"], "policy_proposal")
            events_payload.pop()
            events_path.write_text(
                json.dumps(
                    events_payload,
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            result_path = run_dir / "monitoring_review_result.json"
            result_payload = _read_json(result_path)
            result_payload["runtime_events_sha256"] = hashlib.sha256(
                events_path.read_bytes()
            ).hexdigest()
            result_payload["result_sha256"] = (
                MonitoringReviewResult.canonical_sha256(result_payload)
            )
            result_path.write_text(
                json.dumps(
                    result_payload,
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            with self.assertRaisesRegex(
                ValueError,
                "artifact lacks its sealed runtime event",
            ):
                load_run_runtime_events(request.child_run_id, runs_dir)

    def test_runner_rejects_mutated_evidence_before_calling_the_llm(self):
        view = _causal_view()
        request = _request(view)
        records = _evidence_records()
        records[0]["score"] = 999.0
        client = FakeJSONLLMClient([_llm_payload()])
        recorder = AgentRuntimeRecorder(request.child_run_id, lambda _: None)

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(
                MonitoringReplayConflictError,
                "sealed artifact SHA-256",
            ):
                run_monitoring_review(
                    request,
                    view,
                    records,
                    runs_dir=Path(tmp) / "runs",
                    runtime_recorder=recorder,
                    llm_client=client,
                )

        self.assertEqual(client.calls, 0)
        self.assertEqual(recorder.events, [])

    def test_runner_rejects_a_stale_monitoring_review_contract(self):
        view = _causal_view()
        request = _request(view)
        stale_payload = request.model_dump(
            mode="python",
            exclude={"request_sha256"},
        )
        stale_payload["prompt_template_sha256"] = "a" * 64
        stale_payload["request_sha256"] = MonitoringReviewRequest.canonical_sha256(
            stale_payload
        )
        stale = MonitoringReviewRequest.model_validate(stale_payload)
        recorder = AgentRuntimeRecorder(stale.child_run_id, lambda _: None)

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "contract fingerprints"):
                run_monitoring_review(
                    stale,
                    view,
                    _evidence_records(),
                    runs_dir=Path(tmp) / "runs",
                    runtime_recorder=recorder,
                    use_llm=False,
                )
        self.assertEqual(recorder.events, [])

    def test_guardrail_fallback_is_a_failed_agentic_review_not_a_success(self):
        view = _causal_view()
        request = _request(view)
        client = FakeJSONLLMClient(
            [LLMCallError("simulated timeout")]
            + [_llm_payload() for _ in MONITORING_REVIEW_ROLES[1:]]
        )
        recorder = AgentRuntimeRecorder(request.child_run_id, lambda _: None)
        with tempfile.TemporaryDirectory() as tmp:
            execution = run_monitoring_review(
                request,
                view,
                _evidence_records(),
                runs_dir=Path(tmp) / "runs",
                runtime_recorder=recorder,
                llm_client=client,
            )

        self.assertEqual(execution.result.status, "failed")
        self.assertEqual(execution.result.role_results[0].status, "fallback")
        self.assertEqual(
            execution.result.role_results[0].decision.generation_trace.origin,
            "guardrail_fallback",
        )
        self.assertIn("supervisor", execution.result.failure_reason)

    def test_runner_persists_api_consultable_exactly_hashed_review(self):
        view = _causal_view()
        request = _request(view)
        client = FakeJSONLLMClient([_llm_payload() for _ in MONITORING_REVIEW_ROLES])
        persisted_events = []
        recorder = AgentRuntimeRecorder(request.child_run_id, persisted_events.append)
        forbidden = mock.Mock(side_effect=AssertionError("forbidden pipeline path"))

        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            with mock.patch.multiple(
                pipeline_runner_module,
                generate_dataset_manifest=forbidden,
                generate_data_profile=forbidden,
                generate_clean_signals=forbidden,
                generate_temporal_structure=forbidden,
                generate_model_outputs=forbidden,
                generate_evaluation_report=forbidden,
                generate_technical_report=forbidden,
                build_ollama_pipeline_agents=forbidden,
            ):
                execution = run_monitoring_review(
                    request,
                    view,
                    _evidence_records(),
                    runs_dir=runs_dir,
                    runtime_recorder=recorder,
                    llm_client=client,
                )

            snapshot = load_run_snapshot(request.child_run_id, runs_dir)
            index = load_run_index(runs_dir)
            runtime_events = load_run_runtime_events(request.child_run_id, runs_dir)
            run_dir = Path(snapshot.snapshot_dir)
            request_payload = _read_json(run_dir / "monitoring_review_request.json")
            result_payload = _read_json(run_dir / "monitoring_review_result.json")
            decisions_payload = _read_json(run_dir / "decisions.json")
            state_payload = _read_json(run_dir / "state_final.json")
            evidence_pack = _read_json(run_dir / "evidence_pack.json")
            result = MonitoringReviewResult.model_validate(result_payload)
            decisions = [
                MonitoringReviewDecision.model_validate(item["payload"])
                for item in decisions_payload
            ]

            app = create_app(
                runs_dir=runs_dir,
                allowed_raw_roots=[Path(tmp) / "unused-raw"],
                monitoring_sessions_dir=Path(tmp) / "monitoring-sessions",
            )
            list_response = _get(app, "/runs")
            run_response = _get(app, f"/runs/{request.child_run_id}")
            events_response = _get(app, f"/runs/{request.child_run_id}/events")
            artifacts_response = _get(
                app,
                f"/runs/{request.child_run_id}/artifacts",
            )
            report_response = _get(app, f"/runs/{request.child_run_id}/report")
            audit_response = _get(
                app,
                f"/runs/{request.child_run_id}/audit-report",
            )

            events_file_sha256 = hashlib.sha256(
                (run_dir / "monitoring_review_events.json").read_bytes()
            ).hexdigest()
            proposal_path = run_dir / "monitoring_policy_proposal.json"
            proposal_payload = _read_json(proposal_path)
            first_contribution = proposal_payload["contributions"][0]
            first_contribution.update(
                {
                    "recommended_action": "insufficient_evidence",
                    "proposal_kind": "abstain",
                    "advisory_subject": "policy_change",
                    "current_state": "unchanged",
                    "proposed_state": "withheld",
                }
            )
            proposal_payload["agreement_status"] = "disagreement"
            proposal_payload["aggregate_action"] = None
            proposal_payload["aggregate_kind"] = None
            proposal_payload["proposal_sha256"] = (
                MonitoringPolicyProposal.canonical_sha256(proposal_payload)
            )
            proposal_path.write_text(
                json.dumps(
                    proposal_payload,
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            events_path = run_dir / "monitoring_review_events.json"
            tampered_events = _read_json(events_path)
            tampered_events[-1]["payload"]["policy_proposal"] = proposal_payload
            events_path.write_text(
                json.dumps(
                    tampered_events,
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            result_path = run_dir / "monitoring_review_result.json"
            tampered_result = _read_json(result_path)
            tampered_result["runtime_events_sha256"] = hashlib.sha256(
                events_path.read_bytes()
            ).hexdigest()
            tampered_result["result_sha256"] = (
                MonitoringReviewResult.canonical_sha256(tampered_result)
            )
            result_path.write_text(
                json.dumps(
                    tampered_result,
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                ValueError,
                "policy proposal does not match its sealed sources",
            ):
                load_run_runtime_events(request.child_run_id, runs_dir)

            snapshot_path = run_dir / "snapshot.json"
            tampered_snapshot = _read_json(snapshot_path)
            tampered_snapshot["run_id"] = "foreign-monitoring-run"
            snapshot_path.write_text(
                json.dumps(tampered_snapshot, ensure_ascii=True),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "snapshot identity"):
                load_run_snapshot(request.child_run_id, runs_dir)

        self.assertEqual(execution.snapshot.run_id, request.child_run_id)
        self.assertEqual(snapshot.n_decisions, 7)
        self.assertEqual(index.runs[0].run_id, request.child_run_id)
        self.assertEqual(index.runs[0].n_decisions, 7)
        self.assertEqual(len(runtime_events), 8)
        self.assertEqual(len(persisted_events), 8)
        self.assertEqual(client.calls, 7)
        self.assertEqual(runtime_events[-1].kind, "policy_proposal")
        self.assertEqual(runtime_events[-1].source, "system")
        self.assertEqual(execution.policy_proposal.status, "advisory_not_applied")
        self.assertEqual(execution.policy_proposal.application_status, "not_applied")
        self.assertFalse(execution.policy_proposal.policy_validation_eligible)
        self.assertEqual(len(execution.policy_proposal.contributions), 7)
        self.assertEqual(
            tuple(item.agent_name for item in decisions),
            MONITORING_REVIEW_ROLES,
        )
        self.assertTrue(all(item.hypothesis is not None for item in decisions))
        self.assertTrue(all(item.hypothesis.evidence_refs for item in decisions))
        self.assertTrue(all(item.generation_trace is not None for item in decisions))
        self.assertTrue(all(item.memory_mode == "off" for item in decisions))
        self.assertTrue(
            all(item.policy_application_status == "not_applied" for item in decisions)
        )
        self.assertTrue(
            all(
                item.decision_sha256
                == MonitoringReviewDecision.canonical_sha256(item)
                for item in decisions
            )
        )
        self.assertEqual(request_payload["request_sha256"], request.request_sha256)
        self.assertEqual(result.request_sha256, request.request_sha256)
        self.assertEqual(
            result.result_sha256,
            MonitoringReviewResult.canonical_sha256(result),
        )
        self.assertEqual(result.runtime_events_sha256, events_file_sha256)
        self.assertEqual(result.memory_mode, "off")
        self.assertEqual(result.policy_application_status, "not_applied")
        self.assertEqual(state_payload["memory_mode"], "off")
        self.assertEqual(state_payload["policy_application_status"], "not_applied")
        self.assertEqual(
            state_payload["policy_proposal_sha256"],
            execution.policy_proposal.proposal_sha256,
        )
        self.assertNotIn("raw_path", state_payload)
        self.assertNotIn("raw_path", evidence_pack)
        self.assertNotIn("pipeline_request", evidence_pack)
        self.assertNotIn("pipeline_plan", evidence_pack)
        self.assertEqual(len(evidence_pack["decisions"]), 7)
        self.assertEqual(
            evidence_pack["policy_proposal"]["sha256"],
            execution.policy_proposal.proposal_sha256,
        )
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()[0]["run_id"], request.child_run_id)
        self.assertEqual(run_response.status_code, 200)
        self.assertEqual(run_response.json()["n_decisions"], 7)
        self.assertEqual(events_response.status_code, 200)
        self.assertEqual(len(events_response.json()), 8)
        decision_events = [
            event
            for event in events_response.json()
            if event["kind"] in {"supervisor_decision", "agent_decision"}
        ]
        proposal_events = [
            event
            for event in events_response.json()
            if event["kind"] == "policy_proposal"
        ]
        self.assertEqual(len(decision_events), 7)
        self.assertEqual(len(proposal_events), 1)
        self.assertTrue(
            all(
                event["payload"]["decision"]["hypothesis"]["evidence_refs"]
                for event in decision_events
            )
        )
        self.assertTrue(
            all(
                event["payload"]["memory_mode"] == "off"
                and event["memory_context_id"] is None
                and event["memory_record_ids"] == []
                for event in decision_events
            )
        )
        self.assertEqual(
            proposal_events[0]["payload"]["policy_application_status"],
            "not_applied",
        )
        self.assertEqual(artifacts_response.status_code, 200)
        artifact_hashes = {
            item["name"]: item["metadata"].get("sha256")
            for item in artifacts_response.json()
        }
        self.assertEqual(artifact_hashes["causal_input_view"], view.view_sha256)
        self.assertEqual(
            artifact_hashes["monitoring_review_request"],
            request.request_sha256,
        )
        self.assertEqual(
            artifact_hashes["monitoring_review_result"],
            result.result_sha256,
        )
        self.assertEqual(
            artifact_hashes["monitoring_review_events"],
            events_file_sha256,
        )
        self.assertEqual(
            artifact_hashes["monitoring_policy_proposal"],
            execution.policy_proposal.proposal_sha256,
        )
        self.assertEqual(report_response.status_code, 200)
        self.assertIn("memoria estuvo desactivada", report_response.text)
        self.assertEqual(audit_response.status_code, 200)
        self.assertIn("Roles completados: `7/7`", audit_response.text)
        forbidden.assert_not_called()

    def test_snapshot_rejects_decision_event_and_idempotency_hash_mismatches(self):
        view = _causal_view()
        request = _request(view)
        evidence_catalog = build_causal_evidence_catalog(
            view,
            _evidence_records(),
        )
        recorder = AgentRuntimeRecorder(request.child_run_id, lambda _: None)

        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            execution = run_monitoring_review(
                request,
                view,
                _evidence_records(),
                runs_dir=runs_dir,
                runtime_recorder=recorder,
                use_llm=False,
            )

            altered_decision_payload = execution.decisions[0].model_dump(
                mode="python",
                exclude={"decision_sha256"},
            )
            altered_decision_payload["rationale"] = "Altered after result sealing."
            altered_decision_payload["decision_sha256"] = (
                MonitoringReviewDecision.canonical_sha256(altered_decision_payload)
            )
            altered_decision = MonitoringReviewDecision.model_validate(
                altered_decision_payload
            )
            altered_decisions = [altered_decision, *execution.decisions[1:]]
            with self.assertRaisesRegex(ValueError, "decisions.*result"):
                save_monitoring_review_snapshot(
                    request=request,
                    result=execution.result,
                    decisions=altered_decisions,
                    runtime_events=recorder.events,
                    evidence_catalog=evidence_catalog,
                    policy_proposal=execution.policy_proposal,
                    output_dir=runs_dir,
                )

            altered_event = recorder.events[0].model_copy(
                update={"summary": "Altered after result sealing."}
            )
            with self.assertRaisesRegex(ValueError, "runtime events.*hash"):
                save_monitoring_review_snapshot(
                    request=request,
                    result=execution.result,
                    decisions=list(execution.decisions),
                    runtime_events=[altered_event, *recorder.events[1:]],
                    evidence_catalog=evidence_catalog,
                    policy_proposal=execution.policy_proposal,
                    output_dir=runs_dir,
                )

            altered_result_payload = execution.result.model_dump(
                mode="python",
                exclude={"result_sha256"},
            )
            altered_result_payload["result_id"] = "same-run:different-result"
            altered_result_payload["result_sha256"] = (
                MonitoringReviewResult.canonical_sha256(altered_result_payload)
            )
            altered_result = MonitoringReviewResult.model_validate(
                altered_result_payload
            )
            with self.assertRaisesRegex(ValueError, "idempotency conflict"):
                save_monitoring_review_snapshot(
                    request=request,
                    result=altered_result,
                    decisions=list(execution.decisions),
                    runtime_events=recorder.events,
                    evidence_catalog=evidence_catalog,
                    policy_proposal=execution.policy_proposal,
                    output_dir=runs_dir,
                )


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _get(app, path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(path)

    return asyncio.run(request())


if __name__ == "__main__":
    unittest.main()
