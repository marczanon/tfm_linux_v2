import unittest

from codigo.app.schemas.reasoning import (
    AgentMemoryQuery,
    ReasoningMemoryRecord,
    RetrievedMemoryContext,
    RetrievedMemoryItem,
)
from codigo.app.services.memory_quality_gate import (
    evaluate_memory_quality,
    filter_memory_context_by_quality,
)


class MemoryQualityGateTests(unittest.TestCase):
    def test_quality_gate_marks_pass_caution_and_exclude_candidates(self):
        context = RetrievedMemoryContext(
            context_id="run-memory:modeler:001:memory_query:retrieved_memory_context",
            query=AgentMemoryQuery(
                query_id="run-memory:modeler:001:memory_query",
                target_agent="modeler",
                query_text="run to failure sustained alert lead time",
                dataset="nasa_ims_bearing",
                min_similarity=0.0,
            ),
            items=[
                RetrievedMemoryItem(
                    record=_record(
                        "memory-good-001",
                        dataset="nasa_ims_bearing",
                        memory_role="evidence",
                        tags=["run_to_failure_degradation", "lead_time"],
                    ),
                    similarity=0.72,
                    retrieval_use="evidence_context",
                    rank=1,
                ),
                RetrievedMemoryItem(
                    record=_record(
                        "memory-warning-001",
                        dataset="nasa_ims_bearing",
                        memory_role="warning",
                        tags=["run_to_failure_degradation", "sustained_alert"],
                        human_verdict="partially_correct",
                    ),
                    similarity=0.31,
                    retrieval_use="negative_warning",
                    rank=2,
                ),
                RetrievedMemoryItem(
                    record=_record(
                        "memory-wrong-profile-001",
                        dataset="cwru_bearing",
                        memory_role="evidence",
                        tags=["binary_fault_classification", "cwru_bearing"],
                    ),
                    similarity=0.82,
                    retrieval_use="evidence_context",
                    rank=3,
                ),
            ],
            retrieval_backend="test",
            embedding_model="local_hash_embedding:v1",
        )

        report = evaluate_memory_quality(
            context,
            supervision_profile="run_to_failure_degradation",
        )
        filtered = filter_memory_context_by_quality(context, report)

        recommendations = {
            item.memory_record_id: item.recommendation for item in report.items
        }
        self.assertEqual(recommendations["memory-good-001"], "pass")
        self.assertEqual(recommendations["memory-warning-001"], "caution")
        self.assertEqual(
            recommendations["memory-wrong-profile-001"],
            "exclude_candidate",
        )
        self.assertEqual(report.pass_count, 1)
        self.assertEqual(report.caution_count, 1)
        self.assertEqual(report.exclude_candidate_count, 1)
        self.assertEqual(
            [item.record.memory_record_id for item in filtered.items],
            ["memory-good-001", "memory-warning-001"],
        )
        self.assertEqual([item.rank for item in filtered.items], [1, 2])


def _record(
    memory_record_id: str,
    *,
    dataset: str,
    memory_role: str,
    tags: list[str],
    human_verdict: str | None = "correct",
) -> ReasoningMemoryRecord:
    return ReasoningMemoryRecord(
        memory_record_id=memory_record_id,
        collection_name="modeler_memory",
        target_agent="modeler",
        source_type="decision_episode",
        run_id=f"run-{memory_record_id}",
        decision_id=f"run-{memory_record_id}:modeler:001",
        dataset=dataset,
        source_agent_name="modeler",
        outcome="supported",
        human_verdict=human_verdict,
        memory_role=memory_role,  # type: ignore[arg-type]
        reusable_as_context=True,
        summary=f"Memory {memory_record_id}.",
        content=f"Reusable memory {memory_record_id}.",
        tags=tags,
    )


if __name__ == "__main__":
    unittest.main()
