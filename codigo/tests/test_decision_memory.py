import tempfile
import unittest
from pathlib import Path

from codigo.app.schemas.agent_decisions import (
    EvaluationDecision,
    ModelingDecision,
    ModelingRetryDecision,
)
from codigo.app.schemas.agent_decisions import StructuringDecision
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.reasoning import (
    AgentMemoryQuery,
    ReasoningMemoryRecord,
    RetrievedMemoryContext,
    RetrievedMemoryItem,
)
from codigo.app.schemas.state import EvaluationResult, MetricsReport, ProjectContext
from codigo.app.services.decision_memory import (
    build_evaluation_decision_episode,
    build_evaluation_memory_candidate,
    build_modeling_decision_episode,
    build_modeling_memory_candidate,
    build_modeling_retry_decision_episode,
    build_modeling_retry_memory_candidate,
    build_structuring_decision_episode,
    build_structuring_memory_candidate,
    write_decision_memory_artifacts,
)
from codigo.app.services.reasoning_audit import build_modeling_retry_postmortem
from codigo.app.services.vector_memory import memory_record_from_candidate


class DecisionMemoryTests(unittest.TestCase):
    def test_modeling_retry_postmortem_builds_episode_and_candidate(self):
        decision = _retry_decision()
        before = MetricsReport(
            precision=0.9130,
            recall=0.6000,
            f1_score=0.7241,
            false_positive_rate=0.1429,
        )
        after = MetricsReport(
            precision=0.8846,
            recall=0.6571,
            f1_score=0.7541,
            false_positive_rate=0.2143,
        )
        evaluation = EvaluationResult(
            approved=False,
            summary="Improved recall, but FPR remains above target.",
            next_action="stop",
            limitations=["FPR too high"],
        )
        postmortem = build_modeling_retry_postmortem(
            source_run_id="source-run",
            run_id="retry-run",
            decision=decision,
            before_metrics=before,
            after_metrics=after,
            evaluation=evaluation,
        )

        episode = build_modeling_retry_decision_episode(
            source_run_id="source-run",
            run_id="retry-run",
            decision=decision,
            postmortem=postmortem,
            before_metrics=before,
            after_metrics=after,
            evaluation=evaluation,
            data_provenance="synthetic",
        )
        candidate = build_modeling_retry_memory_candidate(
            episode,
            reusable_as_context=True,
        )
        record = memory_record_from_candidate(candidate)

        self.assertEqual(episode.decision_type, "modeling")
        self.assertEqual(episode.target_agent, "modeler")
        self.assertEqual(episode.hypothesis, decision.hypothesis)
        self.assertIn("metric:retry_f1", episode.evidence_used)
        self.assertEqual(episode.data_provenance, "synthetic")
        self.assertEqual(episode.options_considered[0].parameters["threshold_quantile"], 0.95)
        self.assertIn("false_positive_rate_above_target", episode.failure_modes)
        self.assertNotIn("retrieved_memory_context", episode.evidence_used)
        self.assertFalse(episode.used_memory_context)
        self.assertEqual(episode.cited_memory_record_ids, [])
        self.assertEqual(candidate.memory_role, "boundary_case")
        self.assertEqual(candidate.data_provenance, "synthetic")
        self.assertTrue(candidate.reusable_as_context)
        self.assertIn("Falsification criterion", candidate.content)
        self.assertIn("hypothesis_kind:model_performance", candidate.tags)
        self.assertIn("when_to_reuse", candidate.model_dump())
        for legacy_source in (episode, candidate, record):
            legacy_payload = legacy_source.model_dump(exclude={"applicability"})
            restored = type(legacy_source).model_validate(legacy_payload)
            self.assertIsNone(restored.applicability)

    def test_decision_memory_artifacts_are_written(self):
        decision = _retry_decision()
        metrics = MetricsReport(recall=0.6, false_positive_rate=0.1429)
        evaluation = EvaluationResult(
            approved=False,
            summary="Retry rejected.",
            next_action="stop",
        )
        postmortem = build_modeling_retry_postmortem(
            source_run_id="source-run",
            run_id="retry-run",
            decision=decision,
            before_metrics=metrics,
            after_metrics=metrics,
            evaluation=evaluation,
        )
        episode = build_modeling_retry_decision_episode(
            source_run_id="source-run",
            run_id="retry-run",
            decision=decision,
            postmortem=postmortem,
            before_metrics=metrics,
            after_metrics=metrics,
            evaluation=evaluation,
        )
        candidate = build_modeling_retry_memory_candidate(
            episode,
            reusable_as_context=True,
        )

        with tempfile.TemporaryDirectory() as tmp:
            artifacts = write_decision_memory_artifacts(
                episode=episode,
                candidate=candidate,
                output_dir=tmp,
            )

            self.assertTrue(Path(artifacts.episode_path).exists())
            self.assertTrue(Path(artifacts.episode_report_path).exists())
            self.assertTrue(Path(artifacts.candidate_path).exists())
            self.assertTrue(Path(artifacts.candidate_report_path).exists())
            self.assertIn(
                "Candidato de memoria",
                Path(artifacts.candidate_report_path).read_text(encoding="utf-8"),
            )
            episode_report = Path(artifacts.episode_report_path).read_text(
                encoding="utf-8"
            )
            self.assertIn("Hipotesis ex ante", episode_report)
            self.assertIn("no confirma por si solo", episode_report)

    def test_structuring_decision_builds_episode_and_candidate(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-memory-test",
                run_id="run-structuring-episode-001",
            )
        )
        decision = StructuringDecision(
            decision_id="run-structuring-episode-001:structurer:001",
            rationale="Compare a shorter supported window for temporal resolution.",
            confidence=0.88,
            hypothesis=_hypothesis(
                "temporal_representation",
                "Shorter windows preserve useful fault structure without leakage.",
                evidence_ref="artifact:clean_signal_summary",
            ),
            structuring_config={
                "window_size": 1024,
                "overlap": 0.5,
                "main_channel": "DE_time",
                "target_sample_rate_hz": 12000,
                "label_mode": "binary_anomaly",
                "features": ["mean", "std", "rms", "energy"],
            },
            expected_features_path="codigo/data/tensors/cwru_bearing/windows_features.csv",
            expected_tensors_path="codigo/data/tensors/cwru_bearing/windows_raw.npz",
            expected_splits_path="codigo/data/tensors/cwru_bearing/splits.json",
        )

        memory_context = _retrieved_memory_context("structurer")
        episode = build_structuring_decision_episode(
            state=state,
            decision=decision,
            execution_result_summary="Downstream model improved FPR in the comparison run.",
            outcome="supported",
            memory_context=memory_context,
        )
        candidate = build_structuring_memory_candidate(
            episode,
            reusable_as_context=True,
        )

        self.assertEqual(episode.target_agent, "structurer")
        self.assertEqual(episode.decision_type, "structuring")
        self.assertEqual(episode.hypothesis, decision.hypothesis)
        self.assertIn("artifact:clean_signal_summary", episode.evidence_used)
        self.assertEqual(episode.options_considered[0].parameters["window_size"], 1024)
        self.assertIn("window_context_vs_temporal_resolution", episode.tradeoffs_observed)
        self.assertEqual(
            episode.retrieved_memory_record_ids,
            ["memory-structurer-001"],
        )
        self.assertNotIn("retrieved_memory_context", episode.evidence_used)
        self.assertEqual(candidate.target_agent, "structurer")
        self.assertEqual(candidate.memory_role, "evidence")
        self.assertTrue(candidate.reusable_as_context)

    def test_evaluation_decision_builds_episode_and_candidate(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-memory-test",
            run_id="run-evaluation-episode-001",
        )
        state_dict["metrics"] = MetricsReport(
            precision=0.88,
            recall=0.82,
            f1_score=0.85,
            false_positive_rate=0.12,
        ).model_dump(mode="json")
        state = validate_state(state_dict)
        decision = EvaluationDecision(
            decision_id="run-evaluation-episode-001:evaluator:001",
            rationale="Reject because current metrics do not satisfy the protocol.",
            confidence=0.91,
            hypothesis=_hypothesis(
                "operational_acceptance",
                "The current metrics are insufficient for operational acceptance.",
                evidence_ref="metric:false_positive_rate",
            ),
            evaluation={
                "approved": False,
                "summary": "Recall and FPR remain outside the local protocol.",
                "next_action": "retry_with_new_config",
                "limitations": ["Needs a better configuration."],
            },
            min_recall_required=0.9,
            max_false_positive_rate=0.1,
        )

        memory_context = _retrieved_memory_context("evaluator")
        episode = build_evaluation_decision_episode(
            state=state,
            decision=decision,
            memory_context=memory_context,
        )
        candidate = build_evaluation_memory_candidate(
            episode,
            reusable_as_context=True,
        )

        self.assertEqual(episode.target_agent, "evaluator")
        self.assertEqual(episode.decision_type, "evaluation")
        self.assertEqual(episode.hypothesis, decision.hypothesis)
        self.assertIn("metric:false_positive_rate", episode.evidence_used)
        self.assertIn("recall_below_required", episode.tradeoffs_observed)
        self.assertIn("false_positive_rate_above_allowed", episode.failure_modes)
        self.assertEqual(
            episode.retrieved_memory_record_ids,
            ["memory-evaluator-001"],
        )
        self.assertNotIn("retrieved_memory_context", episode.evidence_used)
        self.assertEqual(candidate.target_agent, "evaluator")
        self.assertEqual(candidate.memory_role, "evidence")
        self.assertTrue(candidate.reusable_as_context)

    def test_temporal_modeling_decision_builds_episode_and_candidate(self):
        state_dict = create_initial_cwru_state(
            thread_id="nasa-memory-test",
            run_id="run-temporal-modeling-episode-001",
        )
        state_dict["project_context"] = ProjectContext(
            dataset="nasa_ims_bearing",
            machine_type="rotating_machinery",
            signal_type="vibration",
            objective="run_to_failure_degradation",
            target_sample_rate_hz=20000,
            main_channel="channel_1",
            label_mode="degradation",
            supervision_profile="run_to_failure_degradation",
            label_granularity="proxy_temporal",
            label_source="temporal_proxy",
            trajectory_group_id="nasa-bearing-trajectory-01",
            evaluation_group_id="benchmark-heldout-group-a",
            transfer_scope="same_dataset",
            data_provenance="synthetic",
        ).model_dump(mode="json")
        state_dict["metrics"] = MetricsReport(
            extra={
                "degradation_available": True,
                "degradation_mean_lead_time_to_failure": 300.0,
                "degradation_mean_false_alarm_rate_nominal": 0.02,
            },
        ).model_dump(mode="json")
        state = validate_state(state_dict)
        decision = ModelingDecision(
            decision_id="run-temporal-modeling-episode-001:modeler:001",
            rationale="Use PCA as a temporal anomaly score baseline.",
            confidence=0.82,
            hypothesis=_hypothesis(
                "model_performance",
                "The held-out degradation score should rise before historical failure.",
                evidence_ref="metric:mean_lead_time_to_failure",
            ),
            decision_strategy={
                "strategy_type": "model_family_selection",
                "hypothesis": (
                    "PCA reconstruction error should rise as degradation "
                    "approaches the historical failure point."
                ),
                "tool_names": [
                    "temporal_health_lookup",
                    "degradation_metrics_lookup",
                ],
                "evidence_refs": [
                    "temporal:first_persistent_alert",
                    "metric:mean_lead_time_to_failure",
                ],
                "optimization_targets": [
                    "detected_before_failure_rate",
                    "mean_lead_time_to_failure",
                    "mean_false_alarm_rate_nominal",
                ],
                "alert_policy": "first spike separated from sustained alert",
            },
            modeling_config={
                "model_name": "pca_reconstruction_error",
                "random_state": 42,
                "hyperparameters": {"threshold_quantile": 0.99},
            },
            expected_model_path="codigo/models/nasa_ims_bearing/pca.joblib",
        )

        memory_context = _retrieved_memory_context("modeler")
        episode = build_modeling_decision_episode(
            state=state,
            decision=decision,
            execution_result_summary="modeling ok",
            memory_context=memory_context,
        )
        candidate = build_modeling_memory_candidate(
            episode,
            reusable_as_context=True,
        )
        record = memory_record_from_candidate(candidate)

        self.assertEqual(episode.target_agent, "modeler")
        self.assertEqual(episode.hypothesis, decision.hypothesis)
        self.assertEqual(episode.outcome, "inconclusive")
        self.assertIn(
            "held-out degradation score",
            episode.context_summary,
        )
        self.assertEqual(episode.data_provenance, "synthetic")
        self.assertEqual(episode.decision_type, "modeling")
        self.assertIn("temporal_health_lookup", episode.evidence_used)
        self.assertEqual(
            episode.retrieved_memory_record_ids,
            ["memory-modeler-001"],
        )
        self.assertNotIn("retrieved_memory_context", episode.evidence_used)
        self.assertIn("target:mean_lead_time_to_failure", episode.tradeoffs_observed)
        self.assertIn("alert_policy_declared", episode.tradeoffs_observed)
        self.assertIn(
            "run_to_failure_modeling_requires_temporal_metrics",
            episode.reusable_lessons,
        )
        self.assertEqual(
            episode.after_metrics["degradation_mean_lead_time_to_failure"],
            300.0,
        )
        self.assertEqual(candidate.target_agent, "modeler")
        self.assertEqual(candidate.data_provenance, "synthetic")
        self.assertIsNotNone(episode.applicability)
        self.assertEqual(
            episode.applicability.supervision_profile,
            "run_to_failure_degradation",
        )
        self.assertEqual(episode.applicability.label_source, "temporal_proxy")
        self.assertEqual(episode.applicability.label_granularity, "proxy_temporal")
        self.assertEqual(episode.applicability.target_sample_rate_hz, 20000)
        self.assertEqual(
            episode.applicability.trajectory_group_id,
            "nasa-bearing-trajectory-01",
        )
        self.assertEqual(
            episode.applicability.evaluation_group_id,
            "benchmark-heldout-group-a",
        )
        self.assertEqual(candidate.applicability, episode.applicability)
        self.assertEqual(record.applicability, episode.applicability)
        self.assertIn("score_trend_over_binary_f1", candidate.tags)
        self.assertIn("After metrics", candidate.content)
        self.assertIn("degradation_mean_lead_time_to_failure", candidate.content)

    def test_episode_preserves_declared_memory_use_separately_from_retrieval(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="memory-declaration-test",
                run_id="memory-declaration-run",
            )
        )
        memory_context = _retrieved_memory_context("modeler")
        decision = ModelingDecision(
            decision_id="memory-declaration-run:modeler:001",
            rationale="Use a prior warning while retaining current-run evidence.",
            confidence=0.86,
            modeling_config={
                "model_name": "isolation_forest",
                "random_state": 42,
                "hyperparameters": {"threshold_quantile": 0.99},
            },
            expected_model_path="models/isolation_forest.joblib",
            memory_context_id=memory_context.context_id,
            used_memory_context=True,
            memory_record_ids=["memory-modeler-001"],
            memory_usage_summary="Adapted the warning as a threshold-risk reminder.",
            memory_record_uses=[
                {
                    "memory_record_id": "memory-modeler-001",
                    "usage": "adapted",
                    "influence_summary": "Kept a conservative threshold hypothesis.",
                    "risk_mitigation": "Current metrics remain authoritative.",
                }
            ],
        )

        episode = build_modeling_decision_episode(
            state=state,
            decision=decision,
            memory_context=memory_context,
        )

        self.assertTrue(episode.used_memory_context)
        self.assertEqual(episode.memory_context_id, memory_context.context_id)
        self.assertEqual(
            episode.cited_memory_record_ids,
            ["memory-modeler-001"],
        )
        self.assertIn("retrieved_memory_context", episode.evidence_used)
        self.assertEqual(
            episode.memory_record_uses[0]["usage"],
            "adapted",
        )

    def test_temporal_evaluation_episode_preserves_operational_guardrails(self):
        state_dict = create_initial_cwru_state(
            thread_id="nasa-memory-test",
            run_id="run-temporal-evaluation-episode-001",
        )
        state_dict["project_context"] = ProjectContext(
            dataset="nasa_ims_bearing",
            machine_type="rotating_machinery",
            signal_type="vibration",
            objective="run_to_failure_degradation",
            target_sample_rate_hz=20000,
            main_channel="channel_1",
            label_mode="degradation",
            supervision_profile="run_to_failure_degradation",
            label_granularity="proxy_temporal",
            label_source="temporal_proxy",
        ).model_dump(mode="json")
        state_dict["metrics"] = MetricsReport(
            extra={
                "degradation_available": True,
                "degradation_detected_before_failure_rate": 1.0,
                "degradation_mean_lead_time_to_failure": 300.0,
                "degradation_mean_false_alarm_rate_nominal": 0.0,
                "degradation_mean_score_trend_spearman": 0.9,
            },
        ).model_dump(mode="json")
        state = validate_state(state_dict)
        decision = EvaluationDecision(
            decision_id="run-temporal-evaluation-episode-001:evaluator:001",
            rationale="Approve with operational guardrails.",
            confidence=0.9,
            evaluation={
                "approved": True,
                "summary": "Temporal metrics satisfy the local protocol.",
                "next_action": "continue",
                "limitations": ["Proxy labels are not official per-window labels."],
            },
            min_recall_required=None,
            max_false_positive_rate=None,
            tool_names=["temporal_health_lookup", "degradation_metrics_lookup"],
            evidence_refs=[
                "tool:temporal_health_lookup",
                "metric:mean_lead_time_to_failure",
            ],
            operational_assessment=(
                "Defendible with caveats: pico aislado is not failure, aviso "
                "sostenido matters and RUL is not estimated."
            ),
            temporal_debate_points=[
                "Debate pico aislado frente a aviso sostenido.",
                "Debate falsas alarmas nominales y etiquetas proxy.",
            ],
            temporal_guardrail_checks=[
                "isolated_spike_not_failure",
                "sustained_alert_required",
                "rul_not_estimated",
                "proxy_labels_not_official",
                "f1_auxiliary_only",
            ],
        )

        episode = build_evaluation_decision_episode(
            state=state,
            decision=decision,
        )

        self.assertIn("Assessment operacional", episode.context_summary)
        self.assertIn("temporal_health_lookup", episode.evidence_used)
        self.assertIn("metric:mean_lead_time_to_failure", episode.evidence_used)
        self.assertIn("rul_not_estimated", episode.tradeoffs_observed)
        self.assertIn("temporal_guardrails_are_binding", episode.reusable_lessons)
        self.assertIn(
            "supervision_profile=run_to_failure_degradation",
            episode.when_to_reuse,
        )
        candidate = build_evaluation_memory_candidate(
            episode,
            reusable_as_context=True,
        )
        self.assertEqual(
            episode.after_metrics["degradation_mean_lead_time_to_failure"],
            300.0,
        )
        self.assertIn("rul_not_estimated", candidate.tags)
        self.assertIn("degradation_mean_lead_time_to_failure", candidate.content)


def _retry_decision() -> ModelingRetryDecision:
    return ModelingRetryDecision(
        decision_id="source-run:modeler_retry:001",
        rationale="Retry with a moderate threshold move.",
        confidence=0.84,
        hypothesis=_hypothesis(
            "model_performance",
            "A moderate threshold move should improve held-out F1 without excessive FPR.",
            evidence_ref="metric:retry_f1",
        ),
        source_run_id="source-run",
        attempt_number=1,
        max_attempts=1,
        should_retry=True,
        learning_summary="Avoid radical threshold changes and test a moderate move.",
        retry_config={
            "model_name": "isolation_forest",
            "random_state": 42,
            "hyperparameters": {
                "n_estimators": 200,
                "threshold_quantile": 0.95,
            },
        },
        expected_effect="Improve recall without repeating overcorrection.",
        evidence_used=["failure_analysis", "retrieved_memory_context"],
    )


def _hypothesis(
    kind: str,
    statement: str,
    *,
    evidence_ref: str,
) -> dict[str, object]:
    return {
        "kind": kind,
        "statement": statement,
        "scope": "Current run and declared held-out split only.",
        "evidence_cutoff": "No monitoring evidence is available before the decision.",
        "expected_observation": "The declared downstream metric changes as predicted.",
        "falsification_criterion": "Held-out evidence moves in the opposite direction.",
        "evidence_refs": [evidence_ref],
        "risk_notes": ["The observation may remain inconclusive."],
        "assumptions": ["The temporal split is leakage-free."],
    }


def _retrieved_memory_context(target_agent: str) -> RetrievedMemoryContext:
    query = AgentMemoryQuery(
        query_id=f"query-{target_agent}-001",
        target_agent=target_agent,
        query_text="Retrieve one prior decision for a causal memory test.",
        dataset="cwru_bearing",
    )
    record = ReasoningMemoryRecord(
        memory_record_id=f"memory-{target_agent}-001",
        collection_name=f"{target_agent}_memory",
        target_agent=target_agent,
        source_type="decision_episode",
        dataset="cwru_bearing",
        memory_role="evidence",
        reusable_as_context=True,
        summary="Prior decision retrieved for a test.",
        content="Use only when the current decision explicitly cites this record.",
    )
    return RetrievedMemoryContext(
        context_id=f"context-{target_agent}-001",
        query=query,
        items=[
            RetrievedMemoryItem(
                record=record,
                similarity=0.9,
                retrieval_use="evidence_context",
                rank=1,
            )
        ],
        retrieval_backend="test",
    )


if __name__ == "__main__":
    unittest.main()
