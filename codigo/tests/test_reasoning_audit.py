import tempfile
import unittest
from pathlib import Path

from codigo.app.schemas.agent_decisions import ModelingRetryDecision
from codigo.app.schemas.state import EvaluationResult, MetricsReport
from codigo.app.services.reasoning_audit import (
    build_modeling_retry_postmortem,
    write_reasoning_postmortem,
)


class ReasoningAuditTests(unittest.TestCase):
    def test_postmortem_detects_overcorrection(self):
        decision = _retry_decision(threshold_quantile=0.5)

        postmortem = build_modeling_retry_postmortem(
            source_run_id="source-run",
            run_id="retry-run",
            decision=decision,
            before_metrics=MetricsReport(
                precision=0.88,
                recall=0.65,
                f1_score=0.75,
                false_positive_rate=0.21,
            ),
            after_metrics=MetricsReport(
                precision=0.71,
                recall=1.0,
                f1_score=0.83,
                false_positive_rate=1.0,
            ),
            evaluation=EvaluationResult(
                approved=False,
                summary="Rejected due high FPR.",
                next_action="stop",
            ),
            request_human_review=True,
        )

        self.assertEqual(postmortem.outcome, "overcorrected")
        self.assertEqual(postmortem.human_review_status, "pending_human_review")
        self.assertIn("do_not_optimize_recall_without_fpr_control", postmortem.reusable_lessons)

    def test_write_postmortem_creates_review_request_when_triggered(self):
        decision = _retry_decision(threshold_quantile=0.95)
        postmortem = build_modeling_retry_postmortem(
            source_run_id="source-run",
            run_id="retry-run",
            decision=decision,
            before_metrics=MetricsReport(recall=0.60, f1_score=0.72, false_positive_rate=0.14),
            after_metrics=MetricsReport(recall=0.66, f1_score=0.75, false_positive_rate=0.21),
            evaluation=None,
            request_human_review=True,
        )

        with tempfile.TemporaryDirectory() as tmp:
            artifacts = write_reasoning_postmortem(
                postmortem,
                tmp,
                request_human_review=True,
                reviewer_hint="advisor",
            )

            self.assertTrue(Path(artifacts.postmortem_path).exists())
            self.assertTrue(Path(artifacts.report_path).exists())
            self.assertTrue(Path(artifacts.review_request_path).exists())
            self.assertTrue(Path(artifacts.review_report_path).exists())
            self.assertTrue(Path(artifacts.review_template_path).exists())
            self.assertEqual(artifacts.review_request.reviewer_hint, "advisor")


def _retry_decision(threshold_quantile: float) -> ModelingRetryDecision:
    return ModelingRetryDecision(
        decision_id="source-run:modeler_retry:001",
        rationale="Lower the threshold to catch missed anomalies.",
        confidence=0.85,
        source_run_id="source-run",
        attempt_number=1,
        max_attempts=2,
        should_retry=True,
        learning_summary="False negatives indicate a threshold that is too conservative.",
        retry_config={
            "model_name": "isolation_forest",
            "random_state": 42,
            "hyperparameters": {
                "n_estimators": 200,
                "max_samples": "auto",
                "contamination": "auto",
                "max_features": 1.0,
                "bootstrap": False,
                "n_jobs": 1,
                "threshold_quantile": threshold_quantile,
            },
        },
        expected_effect="Increase recall with a limited false positive cost.",
        evidence_used=["false_negative_summary", "threshold_convention"],
    )


if __name__ == "__main__":
    unittest.main()
