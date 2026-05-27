import tempfile
import unittest
from pathlib import Path

from codigo.app.schemas.agent_decisions import ModelingRetryDecision
from codigo.app.schemas.reasoning import (
    AgentMemoryQuery,
    ReasoningMemoryRecord,
    RetrievedMemoryContext,
    RetrievedMemoryItem,
)
from codigo.app.schemas.state import MetricsReport
from codigo.app.services.memory_usage_audit import (
    build_modeling_retry_memory_usage_audit,
    write_memory_usage_audit,
)


class MemoryUsageAuditTests(unittest.TestCase):
    def test_boundary_memory_repeated_failure_is_detected(self):
        decision = _retry_decision(
            threshold_quantile=0.5,
            used_memory=True,
            usage="adapted",
        )
        audit = build_modeling_retry_memory_usage_audit(
            run_id="retry-run",
            decision=decision,
            memory_context=_memory_context(),
            before_metrics=MetricsReport(recall=0.6, false_positive_rate=0.1429),
            after_metrics=MetricsReport(recall=1.0, false_positive_rate=1.0),
        )

        self.assertEqual(audit.outcome, "memory_repeated_boundary_failure")
        self.assertEqual(audit.items[0].assessment, "repeated_boundary_failure")
        self.assertEqual(
            audit.cited_memory_record_ids,
            ["memory-overcorrection-001"],
        )

    def test_audit_can_be_written_as_json_and_markdown(self):
        audit = build_modeling_retry_memory_usage_audit(
            run_id="retry-run",
            decision=_retry_decision(
                threshold_quantile=0.95,
                used_memory=True,
                usage="adapted",
            ),
            memory_context=_memory_context(),
            before_metrics=MetricsReport(recall=0.6, false_positive_rate=0.1429),
            after_metrics=MetricsReport(recall=0.7, false_positive_rate=0.2),
        )

        with tempfile.TemporaryDirectory() as tmp:
            artifacts = write_memory_usage_audit(audit, tmp)

            self.assertTrue(Path(artifacts.audit_path).exists())
            self.assertTrue(Path(artifacts.report_path).exists())
            self.assertIn(
                "Auditoria de uso de memoria",
                Path(artifacts.report_path).read_text(encoding="utf-8"),
            )

    def test_threshold_reasoning_inconsistency_is_detected(self):
        audit = build_modeling_retry_memory_usage_audit(
            run_id="retry-run",
            decision=_retry_decision(
                threshold_quantile=0.95,
                used_memory=True,
                usage="adapted",
                risk_mitigation="Use 0.95 (mayor que 0.99) to reduce FPR.",
            ),
            memory_context=_memory_context(),
            before_metrics=MetricsReport(recall=0.6, false_positive_rate=0.1429),
            after_metrics=MetricsReport(recall=0.6571, false_positive_rate=0.2143),
        )

        self.assertEqual(audit.outcome, "memory_reasoning_inconsistent")
        self.assertEqual(audit.items[0].assessment, "reasoning_inconsistent")
        self.assertIn("0.95", audit.items[0].assessment_reason)

    def test_high_quantile_contrasted_with_lower_threshold_is_not_inconsistent(self):
        audit = build_modeling_retry_memory_usage_audit(
            run_id="retry-run",
            decision=_retry_decision(
                threshold_quantile=0.99,
                used_memory=True,
                usage="adapted",
                risk_mitigation=(
                    "Use threshold 0.99 as a high conservative quantile "
                    "instead of the low 0.50 that overcorrected."
                ),
            ),
            memory_context=_memory_context(),
            before_metrics=MetricsReport(recall=0.6, false_positive_rate=0.1429),
            after_metrics=MetricsReport(recall=0.43, false_positive_rate=0.0714),
        )

        self.assertEqual(audit.outcome, "memory_aligned")
        self.assertEqual(audit.items[0].assessment, "aligned")


def _retry_decision(
    *,
    threshold_quantile: float,
    used_memory: bool,
    usage: str,
    risk_mitigation: str = "Avoid repeating FPR=1.0 by using a smaller change.",
) -> ModelingRetryDecision:
    return ModelingRetryDecision(
        decision_id="source-run:modeler_retry:001",
        rationale="Retry with memory evidence.",
        confidence=0.8,
        source_run_id="source-run",
        attempt_number=1,
        max_attempts=1,
        should_retry=True,
        learning_summary="Use memory to adjust threshold carefully.",
        retry_config={
            "model_name": "isolation_forest",
            "random_state": 42,
            "hyperparameters": {"threshold_quantile": threshold_quantile},
        },
        expected_effect="Improve recall while controlling FPR.",
        memory_context_id=(
            "query-memory:retrieved_memory_context" if used_memory else None
        ),
        used_memory_context=used_memory,
        memory_record_ids=["memory-overcorrection-001"] if used_memory else [],
        memory_usage_summary=(
            "Boundary memory warns about excessive threshold drops."
            if used_memory
            else None
        ),
        memory_record_uses=[
            {
                "memory_record_id": "memory-overcorrection-001",
                "usage": usage,
                "influence_summary": "It warns that recall-only tuning can overcorrect.",
                "risk_mitigation": risk_mitigation,
            }
        ]
        if used_memory
        else [],
    )


def _memory_context() -> RetrievedMemoryContext:
    query = AgentMemoryQuery(
        query_id="query-memory",
        target_agent="modeler",
        query_text="threshold overcorrection recall fpr",
        dataset="nasa_ims_bearing",
    )
    record = ReasoningMemoryRecord(
        memory_record_id="memory-overcorrection-001",
        collection_name="modeler_memory",
        target_agent="modeler",
        source_type="human_review",
        run_id="old-run",
        postmortem_id="old-run:reasoning_postmortem:001",
        decision_id="old-run:modeler_retry:001",
        dataset="nasa_ims_bearing",
        source_agent_name="modeler",
        outcome="overcorrected",
        human_verdict="partially_correct",
        memory_role="boundary_case",
        reusable_as_context=True,
        summary="Threshold overcorrection increased FPR to 1.0.",
        content="Lowering threshold helped recall but produced excessive FPR.",
    )
    return RetrievedMemoryContext(
        context_id="query-memory:retrieved_memory_context",
        query=query,
        items=[
            RetrievedMemoryItem(
                record=record,
                similarity=0.9,
                retrieval_use="boundary_context",
                rank=1,
            )
        ],
    )


if __name__ == "__main__":
    unittest.main()
