import unittest

from codigo.app.schemas.reasoning import (
    AgentMemoryQuery,
    MemoryApplicability,
    ReasoningMemoryRecord,
    RetrievedMemoryContext,
    RetrievedMemoryItem,
)
from codigo.app.services.agent_memory import (
    memory_context_for_llm,
    memory_usage_json_template,
)


class AgentMemoryPromptContractTests(unittest.TestCase):
    def test_online_blind_projection_omits_free_text_metrics_and_outcome(self):
        context = RetrievedMemoryContext(
            context_id="query:modeler:online-blind",
            query=AgentMemoryQuery(
                query_id="query:modeler",
                target_agent="modeler",
                query_text="causal monitoring",
            ),
            items=[
                RetrievedMemoryItem(
                    record=ReasoningMemoryRecord(
                        memory_record_id="memory-retrospective-001",
                        collection_name="modeler_memory",
                        target_agent="modeler",
                        source_type="reasoning_postmortem",
                        memory_role="boundary_case",
                        reusable_as_context=True,
                        outcome="overcorrected",
                        summary="Recall rose to 1.0 after seeing monitoring labels.",
                        content="Future monitoring revealed 12 false negatives.",
                        metrics={"recall": 1.0, "false_positive_rate": 0.8},
                        tags=["causal_partition", "recall_fpr_tradeoff"],
                        applicability=MemoryApplicability(
                            supervision_profile="run_to_failure_degradation",
                            label_source="none",
                            label_granularity="none",
                            target_sample_rate_hz=20000,
                            trajectory_group_id="set-1",
                            evaluation_group_id="holdout-1",
                            transfer_scope="same_supervision_profile",
                        ),
                    ),
                    similarity=0.8,
                    retrieval_use="boundary_context",
                    rank=1,
                )
            ],
        )

        projected = memory_context_for_llm(context, online_blind=True)

        item = projected["items"][0]
        self.assertEqual(
            projected["evidence_view"],
            "online_blind_causal_projection_v1",
        )
        self.assertNotIn("summary", item)
        self.assertNotIn("content_excerpt", item)
        self.assertNotIn("metrics", item)
        self.assertNotIn("outcome", item)
        self.assertNotIn("run_id", item)
        self.assertEqual(item["safe_methodology_tags"], ["causal_partition"])
        self.assertEqual(len(item["methodological_guidance"]), 1)

    def test_retrieved_memory_requires_explicit_opt_in_in_json_template(self):
        context = RetrievedMemoryContext(
            context_id="query:modeler:retrieved_memory_context",
            query=AgentMemoryQuery(
                query_id="query:modeler",
                target_agent="modeler",
                query_text="causal threshold",
            ),
            items=[
                RetrievedMemoryItem(
                    record=ReasoningMemoryRecord(
                        memory_record_id="memory-method-001",
                        collection_name="modeler_memory",
                        target_agent="modeler",
                        source_type="methodology_note",
                        memory_role="methodology",
                        reusable_as_context=True,
                        summary="Calibrate only before monitoring.",
                        content="Use baseline and calibration without future labels.",
                    ),
                    similarity=0.9,
                    retrieval_use="methodology_context",
                    rank=1,
                )
            ],
        )

        template = memory_usage_json_template(context)

        self.assertEqual(
            template["memory_context_id"],
            "query:modeler:retrieved_memory_context",
        )
        self.assertFalse(template["used_memory_context"])
        self.assertEqual(template["memory_record_ids"], [])
        self.assertEqual(template["memory_record_uses"], [])
        self.assertIsNone(template["memory_usage_summary"])
        self.assertNotIn("available_memory_record_ids", template)


if __name__ == "__main__":
    unittest.main()
