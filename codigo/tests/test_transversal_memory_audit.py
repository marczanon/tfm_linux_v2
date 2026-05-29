import tempfile
import unittest
from pathlib import Path

from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.agent_decisions import EvaluationDecision, StructuringDecision
from codigo.app.schemas.reasoning import (
    AgentMemoryQuery,
    MemoryCandidate,
    ReasoningMemoryRecord,
    RetrievedMemoryContext,
    RetrievedMemoryItem,
)
from codigo.app.schemas.state import (
    ArtifactRef,
    EvaluationResult,
    MetricsReport,
    StateMessage,
    TFMStateModel,
)
from codigo.app.services.run_persistence import save_run_snapshot
from codigo.app.services.transversal_memory_audit import (
    audit_transversal_memory_run,
    build_transversal_memory_audit,
)


class TransversalMemoryAuditTests(unittest.TestCase):
    def test_aligned_structurer_and_evaluator_memory_are_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            state = _state_with_transversal_memory(base)
            snapshot = save_run_snapshot(state, base / "runs")
            artifacts = audit_transversal_memory_run(
                run_id=snapshot.run_id,
                runs_dir=base / "runs",
                output_dir=base / "audit",
            )

            self.assertTrue(Path(artifacts.audit_path).exists())
            self.assertTrue(Path(artifacts.report_path).exists())
            self.assertEqual(artifacts.audit.overall_outcome, "memory_aligned")
            self.assertEqual(artifacts.audit.dataset, "cwru_bearing")
            self.assertEqual(artifacts.audit.metrics["recall"], 1.0)
            self.assertEqual(len(artifacts.audit.agent_audits), 2)
            for item in artifacts.audit.agent_audits:
                self.assertEqual(item.outcome, "memory_aligned")
                self.assertTrue(item.context_reuse_allowed)
                self.assertTrue(item.principal_evidence_requires_human_review)
                self.assertEqual(item.cited_without_retrieval, [])
                self.assertEqual(item.missing_usage_declarations, [])

    def test_citing_memory_not_retrieved_invalidates_agent_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = _state_with_transversal_memory(
                Path(tmp),
                structurer_cited_id="memory-structurer-not-retrieved",
            )

            audit = build_transversal_memory_audit(state)
            structurer_audit = next(
                item for item in audit.agent_audits if item.agent_name == "structurer"
            )

            self.assertEqual(audit.overall_outcome, "memory_usage_invalid")
            self.assertEqual(structurer_audit.outcome, "memory_usage_invalid")
            self.assertFalse(structurer_audit.context_reuse_allowed)
            self.assertEqual(
                structurer_audit.cited_without_retrieval,
                ["memory-structurer-not-retrieved"],
            )


def _state_with_transversal_memory(
    base: Path,
    *,
    structurer_cited_id: str = "memory-structurer-001",
    evaluator_cited_id: str = "memory-evaluator-001",
) -> TFMStateModel:
    state = validate_state(
        create_initial_cwru_state(
            thread_id="audit-thread",
            run_id="audit-run",
            raw_path="codigo/data/raw/cwru_bearing/mat",
        )
    )
    state.current_stage = "completed"
    state.metrics = MetricsReport(
        precision=0.99,
        recall=1.0,
        f1_score=0.995,
        false_positive_rate=0.05,
    )
    state.evaluation = EvaluationResult(
        approved=True,
        summary="Metrics satisfy the local protocol.",
        next_action="continue",
    )

    structurer_context_path = _write_memory_context(
        base,
        agent_name="structurer",
        memory_record_id="memory-structurer-001",
    )
    evaluator_context_path = _write_memory_context(
        base,
        agent_name="evaluator",
        memory_record_id="memory-evaluator-001",
    )
    structurer_candidate_path = _write_memory_candidate(base, "structurer")
    evaluator_candidate_path = _write_memory_candidate(base, "evaluator")

    structurer_decision = _structuring_decision(structurer_cited_id)
    evaluator_decision = _evaluation_decision(evaluator_cited_id)
    state.messages = [
        StateMessage(
            role="agent",
            name="structurer",
            content=structurer_decision.model_dump_json(),
        ),
        StateMessage(
            role="agent",
            name="evaluator",
            content=evaluator_decision.model_dump_json(),
        ),
    ]
    state.artifacts = [
        ArtifactRef(
            name="structurer_retrieved_memory_context",
            artifact_type="config",
            path=structurer_context_path.as_posix(),
            producer="structurer",
        ),
        ArtifactRef(
            name="structurer_memory_candidate",
            artifact_type="config",
            path=structurer_candidate_path.as_posix(),
            producer="structurer",
        ),
        ArtifactRef(
            name="evaluator_retrieved_memory_context",
            artifact_type="config",
            path=evaluator_context_path.as_posix(),
            producer="evaluator",
        ),
        ArtifactRef(
            name="evaluator_memory_candidate",
            artifact_type="config",
            path=evaluator_candidate_path.as_posix(),
            producer="evaluator",
        ),
    ]
    return state


def _write_memory_context(
    base: Path,
    *,
    agent_name: str,
    memory_record_id: str,
) -> Path:
    output = base / agent_name
    output.mkdir(parents=True, exist_ok=True)
    context = _memory_context(agent_name, memory_record_id)
    path = output / "retrieved_memory_context.json"
    path.write_text(context.model_dump_json(indent=2), encoding="utf-8")
    return path


def _write_memory_candidate(base: Path, agent_name: str) -> Path:
    output = base / agent_name
    output.mkdir(parents=True, exist_ok=True)
    candidate = MemoryCandidate(
        candidate_id=f"{agent_name}-candidate-001",
        target_agent=agent_name,
        run_id="audit-run",
        decision_id=f"audit-run:{agent_name}:001",
        dataset="cwru_bearing",
        source_agent_name=agent_name,
        outcome="supported",
        memory_role="evidence",
        reusable_as_context=True,
        summary=f"{agent_name} supported memory candidate.",
        content=f"{agent_name} reused prior CWRU evidence consistently.",
        when_to_reuse=["Use as cautious CWRU context after retrieval audit."],
    )
    path = output / "memory_candidate.json"
    path.write_text(candidate.model_dump_json(indent=2), encoding="utf-8")
    return path


def _memory_context(agent_name: str, memory_record_id: str) -> RetrievedMemoryContext:
    query = AgentMemoryQuery(
        query_id=f"audit-run:{agent_name}:memory_query",
        target_agent=agent_name,
        query_text=f"{agent_name} CWRU memory evidence",
        dataset="cwru_bearing",
    )
    record = ReasoningMemoryRecord(
        memory_record_id=memory_record_id,
        collection_name=f"{agent_name}_memory",
        target_agent=agent_name,
        source_type="decision_episode",
        run_id="historic-run",
        decision_id=f"historic-run:{agent_name}:001",
        dataset="cwru_bearing",
        source_agent_name=agent_name,
        outcome="supported",
        memory_role="evidence",
        reusable_as_context=True,
        summary=f"Historic {agent_name} evidence.",
        content=f"Historic {agent_name} decision on CWRU was supported.",
    )
    return RetrievedMemoryContext(
        context_id=f"audit-run:{agent_name}:memory_query:retrieved_memory_context",
        query=query,
        items=[
            RetrievedMemoryItem(
                record=record,
                similarity=0.9,
                retrieval_use="evidence_context",
                rank=1,
            )
        ],
    )


def _structuring_decision(memory_record_id: str) -> StructuringDecision:
    return StructuringDecision(
        decision_id="audit-run:structurer:001",
        rationale="Use retrieved CWRU structuring evidence.",
        confidence=0.9,
        structuring_config={
            "window_size": 2048,
            "overlap": 0.5,
            "main_channel": "DE_time",
            "target_sample_rate_hz": 12000,
            "label_mode": "binary_anomaly",
            "features": ["mean", "std", "rms", "energy"],
        },
        expected_features_path="codigo/data/tensors/cwru_bearing/windows_features.csv",
        expected_tensors_path="codigo/data/tensors/cwru_bearing/windows_raw.npz",
        expected_splits_path="codigo/data/tensors/cwru_bearing/splits.json",
        memory_context_id="audit-run:structurer:memory_query:retrieved_memory_context",
        used_memory_context=True,
        memory_record_ids=[memory_record_id],
        memory_usage_summary="Use memory as supporting context.",
        memory_record_uses=[
            {
                "memory_record_id": memory_record_id,
                "usage": "adapted",
                "influence_summary": "Prior evidence supports this structure.",
                "risk_mitigation": "Generate fresh artifacts for the current run.",
            }
        ],
    )


def _evaluation_decision(memory_record_id: str) -> EvaluationDecision:
    return EvaluationDecision(
        decision_id="audit-run:evaluator:001",
        rationale="Approve because current metrics satisfy thresholds.",
        confidence=0.9,
        evaluation={
            "approved": True,
            "summary": "Recall and FPR satisfy the protocol.",
            "next_action": "continue",
        },
        min_recall_required=0.9,
        max_false_positive_rate=0.1,
        memory_context_id="audit-run:evaluator:memory_query:retrieved_memory_context",
        used_memory_context=True,
        memory_record_ids=[memory_record_id],
        memory_usage_summary="Use memory as a methodological reminder.",
        memory_record_uses=[
            {
                "memory_record_id": memory_record_id,
                "usage": "adapted",
                "influence_summary": "Prior evidence reinforces the threshold policy.",
                "risk_mitigation": "Approval still depends on current metrics.",
            }
        ],
    )


if __name__ == "__main__":
    unittest.main()
