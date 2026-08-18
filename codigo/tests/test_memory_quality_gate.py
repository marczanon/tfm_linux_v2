import unittest

from codigo.app.schemas.reasoning import (
    AgentMemoryQuery,
    MemoryApplicability,
    ReasoningMemoryRecord,
    RetrievedMemoryContext,
    RetrievedMemoryItem,
)
from codigo.app.services.memory_quality_gate import (
    MemoryQualityGatePolicy,
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
                data_provenance="synthetic",
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
        self.assertIn(
            "legacy_applicability_fallback",
            report.items[0].reason_codes,
        )
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

    def test_quality_gate_makes_unknown_caution_and_excludes_conflict(self):
        context = RetrievedMemoryContext(
            context_id="run-synthetic:modeler:memory_query:retrieved_memory_context",
            query=AgentMemoryQuery(
                query_id="run-synthetic:modeler:memory_query",
                target_agent="modeler",
                query_text="run to failure provenance policy",
                dataset="nasa_ims_bearing",
                data_provenance="synthetic",
            ),
            items=[
                RetrievedMemoryItem(
                    record=_record(
                        "memory-provenance-match",
                        dataset="nasa_ims_bearing",
                        memory_role="evidence",
                        tags=["run_to_failure_degradation"],
                        data_provenance="synthetic",
                    ),
                    similarity=0.8,
                    retrieval_use="evidence_context",
                    rank=1,
                ),
                RetrievedMemoryItem(
                    record=_record(
                        "memory-provenance-unknown",
                        dataset="nasa_ims_bearing",
                        memory_role="evidence",
                        tags=["run_to_failure_degradation"],
                        data_provenance="unknown",
                    ),
                    similarity=0.8,
                    retrieval_use="evidence_context",
                    rank=2,
                ),
                RetrievedMemoryItem(
                    record=_record(
                        "memory-provenance-conflict",
                        dataset="nasa_ims_bearing",
                        memory_role="evidence",
                        tags=["run_to_failure_degradation"],
                        data_provenance="official",
                    ),
                    similarity=0.8,
                    retrieval_use="evidence_context",
                    rank=3,
                ),
            ],
        )

        report = evaluate_memory_quality(
            context,
            supervision_profile="run_to_failure_degradation",
        )
        by_id = {item.memory_record_id: item for item in report.items}

        self.assertEqual(report.data_provenance, "synthetic")
        self.assertEqual(by_id["memory-provenance-match"].recommendation, "pass")
        self.assertIn(
            "provenance_match",
            by_id["memory-provenance-match"].reason_codes,
        )
        self.assertEqual(
            by_id["memory-provenance-unknown"].recommendation,
            "caution",
        )
        self.assertIn(
            "provenance_unknown",
            by_id["memory-provenance-unknown"].reason_codes,
        )
        self.assertEqual(
            by_id["memory-provenance-conflict"].recommendation,
            "exclude_candidate",
        )
        self.assertIn(
            "provenance_conflict",
            by_id["memory-provenance-conflict"].reason_codes,
        )

    def test_quality_gate_excludes_binary_metric_memory_from_unlabeled_rtf(self):
        context = RetrievedMemoryContext(
            context_id="run-official:modeler:memory_query:retrieved_memory_context",
            query=AgentMemoryQuery(
                query_id="run-official:modeler:memory_query",
                target_agent="modeler",
                query_text="causal run-to-failure monitoring without window labels",
                dataset="nasa_ims_bearing",
                data_provenance="official",
            ),
            items=[
                RetrievedMemoryItem(
                    record=_record(
                        "memory-binary-threshold-boundary",
                        dataset="nasa_ims_bearing",
                        memory_role="boundary_case",
                        tags=[
                            "recall_fpr_tradeoff",
                            "threshold_quantile",
                            "overcorrection",
                        ],
                        data_provenance="unknown",
                        metrics={
                            "precision": 0.71,
                            "recall": 1.0,
                            "f1_score": 0.83,
                            "false_positive_rate": 1.0,
                        },
                    ),
                    similarity=0.56,
                    retrieval_use="boundary_context",
                    rank=1,
                )
            ],
        )

        report = evaluate_memory_quality(
            context,
            supervision_profile="run_to_failure_degradation",
        )
        filtered = filter_memory_context_by_quality(context, report)

        self.assertEqual(report.exclude_candidate_count, 1)
        self.assertEqual(report.items[0].recommendation, "exclude_candidate")
        self.assertIn("profile_conflict", report.items[0].reason_codes)
        self.assertEqual(filtered.items, [])

    def test_typed_applicability_excludes_profile_and_label_conflicts(self):
        query = AgentMemoryQuery(
            query_id="typed-applicability:modeler:query",
            target_agent="modeler",
            query_text="causal run-to-failure applicability",
            dataset="nasa_ims_bearing",
            data_provenance="synthetic",
            decision_context=_query_applicability_context(),
        )
        context = RetrievedMemoryContext(
            context_id="typed-applicability:context",
            query=query,
            items=[
                RetrievedMemoryItem(
                    record=_record(
                        "typed-match",
                        dataset="nasa_ims_bearing",
                        memory_role="evidence",
                        tags=["misleading_binary_tag"],
                        applicability=_applicability(),
                    ),
                    similarity=0.9,
                    retrieval_use="evidence_context",
                    rank=1,
                ),
                RetrievedMemoryItem(
                    record=_record(
                        "typed-profile-conflict",
                        dataset="nasa_ims_bearing",
                        memory_role="evidence",
                        tags=["run_to_failure_degradation"],
                        applicability=_applicability(
                            supervision_profile="binary_fault_classification"
                        ),
                    ),
                    similarity=0.9,
                    retrieval_use="evidence_context",
                    rank=2,
                ),
                RetrievedMemoryItem(
                    record=_record(
                        "typed-label-conflict",
                        dataset="nasa_ims_bearing",
                        memory_role="evidence",
                        tags=["run_to_failure_degradation"],
                        applicability=_applicability(label_source="official"),
                    ),
                    similarity=0.9,
                    retrieval_use="evidence_context",
                    rank=3,
                ),
            ],
        )

        report = evaluate_memory_quality(context)
        by_id = {item.memory_record_id: item for item in report.items}

        self.assertEqual(by_id["typed-match"].recommendation, "pass")
        self.assertIn("typed_applicability", by_id["typed-match"].reason_codes)
        self.assertNotIn("profile_conflict", by_id["typed-match"].reason_codes)
        self.assertEqual(
            by_id["typed-profile-conflict"].recommendation,
            "exclude_candidate",
        )
        self.assertIn(
            "supervision_profile_conflict",
            by_id["typed-profile-conflict"].reason_codes,
        )
        self.assertEqual(
            by_id["typed-label-conflict"].recommendation,
            "exclude_candidate",
        )
        self.assertIn(
            "label_source_conflict",
            by_id["typed-label-conflict"].reason_codes,
        )

    def test_benchmark_excludes_same_evaluation_group_and_keeps_separated_group(self):
        context = RetrievedMemoryContext(
            context_id="group-isolation:context",
            query=AgentMemoryQuery(
                query_id="group-isolation:modeler:query",
                target_agent="modeler",
                query_text="held-out memory effect benchmark",
                dataset="nasa_ims_bearing",
                data_provenance="synthetic",
                decision_context=_query_applicability_context(
                    trajectory_group_id="trajectory-query",
                    evaluation_group_id="evaluation-heldout-a",
                ),
            ),
            items=[
                RetrievedMemoryItem(
                    record=_record(
                        "same-evaluation-group",
                        dataset="nasa_ims_bearing",
                        memory_role="evidence",
                        tags=[],
                        applicability=_applicability(
                            trajectory_group_id="trajectory-source-a",
                            evaluation_group_id="evaluation-heldout-a",
                        ),
                    ),
                    similarity=0.9,
                    retrieval_use="evidence_context",
                    rank=1,
                ),
                RetrievedMemoryItem(
                    record=_record(
                        "separated-evaluation-group",
                        dataset="nasa_ims_bearing",
                        memory_role="evidence",
                        tags=[],
                        applicability=_applicability(
                            trajectory_group_id="trajectory-source-b",
                            evaluation_group_id="evaluation-training-b",
                        ),
                    ),
                    similarity=0.9,
                    retrieval_use="evidence_context",
                    rank=2,
                ),
            ],
        )

        report = evaluate_memory_quality(
            context,
            policy=MemoryQualityGatePolicy(benchmark_mode=True),
        )
        by_id = {item.memory_record_id: item for item in report.items}

        self.assertEqual(
            by_id["same-evaluation-group"].recommendation,
            "exclude_candidate",
        )
        self.assertIn(
            "evaluation_group_leakage",
            by_id["same-evaluation-group"].reason_codes,
        )
        self.assertEqual(
            by_id["separated-evaluation-group"].recommendation,
            "pass",
        )
        self.assertIn(
            "evaluation_group_separated",
            by_id["separated-evaluation-group"].reason_codes,
        )
        self.assertIn(
            "trajectory_group_separated",
            by_id["separated-evaluation-group"].reason_codes,
        )

    def test_sample_rate_mismatch_and_unknown_applicability_are_cautions(self):
        query = AgentMemoryQuery(
            query_id="sample-rate:modeler:query",
            target_agent="modeler",
            query_text="sample-rate transfer boundary",
            dataset="nasa_ims_bearing",
            data_provenance="synthetic",
            decision_context=_query_applicability_context(),
        )
        context = RetrievedMemoryContext(
            context_id="sample-rate:context",
            query=query,
            items=[
                RetrievedMemoryItem(
                    record=_record(
                        "sample-rate-mismatch",
                        dataset="nasa_ims_bearing",
                        memory_role="evidence",
                        tags=[],
                        applicability=_applicability(target_sample_rate_hz=12000),
                    ),
                    similarity=0.9,
                    retrieval_use="evidence_context",
                    rank=1,
                ),
                RetrievedMemoryItem(
                    record=_record(
                        "typed-applicability-unknown",
                        dataset="nasa_ims_bearing",
                        memory_role="evidence",
                        tags=[],
                        applicability=MemoryApplicability(),
                    ),
                    similarity=0.9,
                    retrieval_use="evidence_context",
                    rank=2,
                ),
            ],
        )

        caution_report = evaluate_memory_quality(context)
        exclusion_report = evaluate_memory_quality(
            context,
            policy=MemoryQualityGatePolicy(
                exclude_incompatible_sample_rate=True
            ),
        )
        caution_by_id = {
            item.memory_record_id: item for item in caution_report.items
        }
        exclusion_by_id = {
            item.memory_record_id: item for item in exclusion_report.items
        }

        self.assertEqual(
            caution_by_id["sample-rate-mismatch"].recommendation,
            "caution",
        )
        self.assertIn(
            "sample_rate_incompatible_caution",
            caution_by_id["sample-rate-mismatch"].reason_codes,
        )
        self.assertEqual(
            exclusion_by_id["sample-rate-mismatch"].recommendation,
            "exclude_candidate",
        )
        self.assertIn(
            "sample_rate_incompatible_excluded",
            exclusion_by_id["sample-rate-mismatch"].reason_codes,
        )
        self.assertEqual(
            caution_by_id["typed-applicability-unknown"].recommendation,
            "caution",
        )
        self.assertIn(
            "supervision_profile_unknown",
            caution_by_id["typed-applicability-unknown"].reason_codes,
        )


def _record(
    memory_record_id: str,
    *,
    dataset: str,
    memory_role: str,
    tags: list[str],
    human_verdict: str | None = "correct",
    data_provenance: str = "synthetic",
    metrics: dict[str, float] | None = None,
    applicability: MemoryApplicability | None = None,
) -> ReasoningMemoryRecord:
    return ReasoningMemoryRecord(
        memory_record_id=memory_record_id,
        collection_name="modeler_memory",
        target_agent="modeler",
        source_type="decision_episode",
        run_id=f"run-{memory_record_id}",
        decision_id=f"run-{memory_record_id}:modeler:001",
        dataset=dataset,
        data_provenance=data_provenance,  # type: ignore[arg-type]
        applicability=applicability,
        source_agent_name="modeler",
        outcome="supported",
        human_verdict=human_verdict,
        memory_role=memory_role,  # type: ignore[arg-type]
        reusable_as_context=True,
        summary=f"Memory {memory_record_id}.",
        content=f"Reusable memory {memory_record_id}.",
        metrics=metrics or {},
        tags=tags,
    )


def _applicability(**updates: object) -> MemoryApplicability:
    values: dict[str, object] = {
        "supervision_profile": "run_to_failure_degradation",
        "label_source": "temporal_proxy",
        "label_granularity": "proxy_temporal",
        "target_sample_rate_hz": 20000,
        "trajectory_group_id": "trajectory-source",
        "evaluation_group_id": "evaluation-training",
        "transfer_scope": "same_dataset",
    }
    values.update(updates)
    return MemoryApplicability.model_validate(values)


def _query_applicability_context(**updates: object) -> dict[str, object]:
    values: dict[str, object] = {
        "supervision_profile": "run_to_failure_degradation",
        "label_source": "temporal_proxy",
        "label_granularity": "proxy_temporal",
        "target_sample_rate_hz": 20000,
        "trajectory_group_id": "trajectory-query",
        "evaluation_group_id": "evaluation-query",
        "transfer_scope": "same_dataset",
    }
    values.update(updates)
    return values


if __name__ == "__main__":
    unittest.main()
