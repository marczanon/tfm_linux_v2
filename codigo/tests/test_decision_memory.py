import tempfile
import unittest
from pathlib import Path

from codigo.app.schemas.agent_decisions import EvaluationDecision, ModelingRetryDecision
from codigo.app.schemas.agent_decisions import StructuringDecision
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import EvaluationResult, MetricsReport
from codigo.app.services.decision_memory import (
    build_evaluation_decision_episode,
    build_evaluation_memory_candidate,
    build_modeling_retry_decision_episode,
    build_modeling_retry_memory_candidate,
    build_structuring_decision_episode,
    build_structuring_memory_candidate,
    write_decision_memory_artifacts,
)
from codigo.app.services.reasoning_audit import build_modeling_retry_postmortem


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
        )
        candidate = build_modeling_retry_memory_candidate(
            episode,
            reusable_as_context=True,
        )

        self.assertEqual(episode.decision_type, "modeling")
        self.assertEqual(episode.target_agent, "modeler")
        self.assertEqual(episode.options_considered[0].parameters["threshold_quantile"], 0.95)
        self.assertIn("false_positive_rate_above_target", episode.failure_modes)
        self.assertEqual(candidate.memory_role, "boundary_case")
        self.assertTrue(candidate.reusable_as_context)
        self.assertIn("when_to_reuse", candidate.model_dump())

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

        episode = build_structuring_decision_episode(
            state=state,
            decision=decision,
            execution_result_summary="Downstream model improved FPR in the comparison run.",
            outcome="supported",
        )
        candidate = build_structuring_memory_candidate(
            episode,
            reusable_as_context=True,
        )

        self.assertEqual(episode.target_agent, "structurer")
        self.assertEqual(episode.decision_type, "structuring")
        self.assertEqual(episode.options_considered[0].parameters["window_size"], 1024)
        self.assertIn("window_context_vs_temporal_resolution", episode.tradeoffs_observed)
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
            evaluation={
                "approved": False,
                "summary": "Recall and FPR remain outside the local protocol.",
                "next_action": "retry_with_new_config",
                "limitations": ["Needs a better configuration."],
            },
            min_recall_required=0.9,
            max_false_positive_rate=0.1,
        )

        episode = build_evaluation_decision_episode(
            state=state,
            decision=decision,
        )
        candidate = build_evaluation_memory_candidate(
            episode,
            reusable_as_context=True,
        )

        self.assertEqual(episode.target_agent, "evaluator")
        self.assertEqual(episode.decision_type, "evaluation")
        self.assertIn("recall_below_required", episode.tradeoffs_observed)
        self.assertIn("false_positive_rate_above_allowed", episode.failure_modes)
        self.assertEqual(candidate.target_agent, "evaluator")
        self.assertEqual(candidate.memory_role, "evidence")
        self.assertTrue(candidate.reusable_as_context)


def _retry_decision() -> ModelingRetryDecision:
    return ModelingRetryDecision(
        decision_id="source-run:modeler_retry:001",
        rationale="Retry with a moderate threshold move.",
        confidence=0.84,
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


if __name__ == "__main__":
    unittest.main()
