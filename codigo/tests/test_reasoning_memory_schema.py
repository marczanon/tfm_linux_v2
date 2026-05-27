import json
import unittest

from pydantic import ValidationError

from codigo.app.schemas.reasoning import (
    AgentMemoryQuery,
    DecisionEpisode,
    DecisionOption,
    HumanReviewSettings,
    MemoryCandidate,
    ReasoningMemoryRecord,
    RetrievedMemoryContext,
    RetrievedMemoryItem,
)


class ReasoningMemorySchemaTests(unittest.TestCase):
    def test_human_review_mode_is_off_by_default(self):
        settings = HumanReviewSettings()

        self.assertEqual(settings.mode, "off")
        self.assertTrue(settings.passive_artifacts_enabled)

    def test_overcorrected_case_can_be_boundary_memory_not_positive(self):
        boundary = _memory_record(
            memory_role="boundary_case",
            outcome="overcorrected",
            human_verdict="partially_correct",
            reusable_as_context=True,
        )

        self.assertEqual(boundary.memory_role, "boundary_case")

        with self.assertRaises(ValidationError):
            _memory_record(
                memory_role="positive_example",
                outcome="overcorrected",
                human_verdict="correct",
                reusable_as_context=True,
            )

    def test_positive_memory_requires_correct_human_verdict(self):
        positive = _memory_record(
            memory_role="positive_example",
            outcome="validated",
            human_verdict="correct",
            reusable_as_context=True,
        )

        self.assertEqual(positive.human_verdict, "correct")

        with self.assertRaises(ValidationError):
            _memory_record(
                memory_role="positive_example",
                outcome="validated",
                human_verdict=None,
                reusable_as_context=True,
            )

    def test_unsafe_memory_cannot_be_positive_context(self):
        unsafe_warning = _memory_record(
            memory_role="warning",
            outcome="overcorrected",
            human_verdict="unsafe",
            reusable_as_context=True,
        )

        with self.assertRaises(ValidationError):
            RetrievedMemoryItem(
                record=unsafe_warning,
                similarity=0.91,
                retrieval_use="positive_context",
                rank=1,
            )

        item = RetrievedMemoryItem(
            record=unsafe_warning,
            similarity=0.91,
            retrieval_use="negative_warning",
            rank=1,
        )
        query = AgentMemoryQuery(
            query_id="query-unsafe-warning",
            target_agent="modeler",
            query_text="avoid threshold overcorrection",
            excluded_verdicts=[],
        )
        context = RetrievedMemoryContext(
            context_id="context-unsafe-warning",
            query=query,
            items=[item],
        )

        self.assertEqual(context.items[0].retrieval_use, "negative_warning")

    def test_excluded_memory_cannot_be_retrieved(self):
        excluded = _memory_record(
            memory_role="excluded",
            outcome="contradicted",
            human_verdict="incorrect",
            reusable_as_context=False,
            exclude_from_context=True,
        )

        with self.assertRaises(ValidationError):
            RetrievedMemoryItem(
                record=excluded,
                similarity=0.8,
                retrieval_use="negative_warning",
                rank=1,
            )

    def test_retrieved_context_is_serializable_and_agent_scoped(self):
        record = _memory_record(
            memory_role="boundary_case",
            outcome="overcorrected",
            human_verdict="partially_correct",
            reusable_as_context=True,
        )
        item = RetrievedMemoryItem(
            record=record,
            similarity=0.88,
            retrieval_use="boundary_context",
            rank=1,
        )
        query = AgentMemoryQuery(
            query_id="query-modeler-overcorrection",
            target_agent="modeler",
            query_text="recall improved but false positive rate exploded",
            top_k=3,
            min_similarity=0.5,
        )

        context = RetrievedMemoryContext(
            context_id="context-modeler-overcorrection",
            query=query,
            items=[item],
            retrieval_backend="test_vector_store",
            embedding_model="local-test-embedding",
        )

        payload = context.model_dump(mode="json")
        self.assertEqual(payload["items"][0]["record"]["target_agent"], "modeler")
        json.dumps(payload)

        other_agent_record = _memory_record(
            memory_record_id="memory-cleaner-001",
            collection_name="cleaner_memory",
            target_agent="cleaner",
            memory_role="boundary_case",
            outcome="partially_supported",
            human_verdict="partially_correct",
            reusable_as_context=True,
        )
        other_item = RetrievedMemoryItem(
            record=other_agent_record,
            similarity=0.9,
            retrieval_use="boundary_context",
            rank=1,
        )
        with self.assertRaises(ValidationError):
            RetrievedMemoryContext(
                context_id="context-wrong-agent",
                query=query,
                items=[other_item],
            )

    def test_query_cannot_request_excluded_memory_role(self):
        with self.assertRaises(ValidationError):
            AgentMemoryQuery(
                query_id="query-excluded",
                target_agent="modeler",
                query_text="retrieve excluded memory",
                allowed_memory_roles=["excluded"],
            )

    def test_decision_episode_validates_options_and_failure_modes(self):
        episode = DecisionEpisode(
            episode_id="episode-modeler-001",
            run_id="run-001",
            decision_id="modeler-decision-001",
            agent_name="modeler",
            target_agent="modeler",
            decision_type="modeling",
            dataset="nasa_ims_bearing",
            context_summary="Low recall with moderate false positive rate.",
            options_considered=[
                DecisionOption(
                    option_id="iforest-095",
                    option_type="model_config",
                    description="Isolation Forest with threshold_quantile=0.95",
                    parameters={"threshold_quantile": 0.95},
                    selected=True,
                ),
            ],
            chosen_action="Use Isolation Forest with threshold_quantile=0.95.",
            expected_effect="Improve recall while avoiding the previous overcorrection.",
            outcome="partially_supported",
            lesson_learned="Moderate threshold movement improved recall but still raised FPR.",
            tradeoffs_observed=["recall_improved_fpr_worsened"],
            when_to_reuse=["low recall caused by anomaly scores near threshold"],
            when_not_to_reuse=["false positive rate is already above target"],
            risk_if_misused="Can keep tuning the threshold when a model change is needed.",
        )

        self.assertEqual(episode.options_considered[0].parameters["threshold_quantile"], 0.95)

        with self.assertRaises(ValidationError):
            DecisionEpisode(
                episode_id="episode-bad-001",
                run_id="run-001",
                decision_id="modeler-decision-002",
                agent_name="modeler",
                target_agent="modeler",
                decision_type="modeling",
                context_summary="Overcorrection happened.",
                chosen_action="Use threshold_quantile=0.50.",
                outcome="overcorrected",
                lesson_learned="The threshold movement was too large.",
            )

    def test_memory_candidate_requires_reuse_guidance(self):
        candidate = MemoryCandidate(
            candidate_id="candidate-modeler-001",
            source_episode_id="episode-modeler-001",
            target_agent="modeler",
            run_id="run-001",
            decision_id="modeler-decision-001",
            dataset="nasa_ims_bearing",
            source_agent_name="modeler",
            outcome="partially_supported",
            memory_role="boundary_case",
            reusable_as_context=True,
            summary="Moderate threshold movement improved recall but raised FPR.",
            content="The agent changed threshold_quantile from 0.99 to 0.95.",
            when_to_reuse=["low recall with anomalies close to the threshold"],
            when_not_to_reuse=["FPR is already above the operational limit"],
            risk_if_misused="May overfit the threshold instead of changing model family.",
        )

        self.assertEqual(candidate.source_type, "memory_candidate")

        with self.assertRaises(ValidationError):
            MemoryCandidate(
                candidate_id="candidate-positive-unreviewed",
                target_agent="modeler",
                memory_role="positive_example",
                reusable_as_context=True,
                summary="Unreviewed positive candidate.",
                content="This should not become positive memory.",
                when_to_reuse=["same context"],
            )


def _memory_record(
    *,
    memory_role: str,
    outcome: str,
    human_verdict: str | None,
    reusable_as_context: bool,
    memory_record_id: str = "memory-modeler-001",
    collection_name: str = "modeler_memory",
    target_agent: str = "modeler",
    exclude_from_context: bool = False,
) -> ReasoningMemoryRecord:
    return ReasoningMemoryRecord(
        memory_record_id=memory_record_id,
        collection_name=collection_name,
        target_agent=target_agent,
        source_type="reasoning_postmortem",
        run_id="nasa-ims-synth-agentic-qwen-fase3-retry-attempt-02",
        postmortem_id="postmortem-retry-02",
        decision_id="modeler-retry-02",
        dataset="nasa_ims_bearing",
        source_agent_name="modeler",
        outcome=outcome,
        human_verdict=human_verdict,
        memory_role=memory_role,
        reusable_as_context=reusable_as_context,
        exclude_from_context=exclude_from_context,
        summary="Threshold reduction improved recall but caused unsafe FPR.",
        content=(
            "The retry lowered the anomaly threshold. Recall reached 1.0, "
            "but false positive rate also reached 1.0, so the case should be "
            "treated as overcorrection."
        ),
        metrics={
            "recall": 1.0,
            "false_positive_rate": 1.0,
            "f1_score": 0.8333,
        },
        tags=["threshold", "overcorrection", "nasa_synthetic"],
    )


if __name__ == "__main__":
    unittest.main()
