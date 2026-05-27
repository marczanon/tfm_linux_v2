import json
import unittest

from pydantic import ValidationError

from codigo.app.schemas.agent_decisions import (
    CleaningDecision,
    ModelingAlternative,
    ModelingDecision,
    ModelingRetryDecision,
    ReportDecision,
    ReportSection,
    StructuringAlternative,
    StructuringDecision,
    SupervisorDecision,
)
from codigo.app.schemas.reasoning import (
    AgentReasoningPostmortem,
    HumanReasoningReview,
    ReasoningMetricDelta,
)
from codigo.app.schemas.state import CleaningConfig, ModelingConfig, StructuringConfig


class AgentDecisionSchemaTests(unittest.TestCase):
    def test_supervisor_decision_requires_next_node_when_not_terminal(self):
        with self.assertRaises(ValidationError):
            SupervisorDecision(
                decision_id="d-001",
                rationale="Continue with manifest generation.",
                confidence=0.9,
                current_stage="initialized",
                next_stage="dataset_manifest",
                next_node=None,
                requires_human_review=False,
                stop_reason=None,
            )

    def test_supervisor_terminal_decision_requires_stop_reason(self):
        with self.assertRaises(ValidationError):
            SupervisorDecision(
                decision_id="d-002",
                rationale="Stop after completion.",
                confidence=0.9,
                current_stage="reporting",
                next_stage="completed",
                next_node=None,
                requires_human_review=False,
                stop_reason=None,
            )

    def test_cleaning_decision_is_json_serializable(self):
        decision = CleaningDecision(
            decision_id="clean-001",
            rationale="Remove non-finite values and keep raw scale.",
            confidence=0.8,
            cleaning_config=CleaningConfig(
                strategy_id="cwru_cleaning_v1",
                remove_non_finite=True,
                resample_to_hz=12000,
                normalization="none",
                audit_log_path=None,
            ),
            expected_artifact_path="codigo/data/processed/cwru_bearing/clean_signals",
        )

        payload = decision.model_dump(mode="json")

        self.assertEqual(payload["agent_name"], "cleaner")
        json.dumps(payload)

    def test_agent_decision_rejects_extra_fields(self):
        with self.assertRaises(ValidationError):
            CleaningDecision(
                decision_id="clean-002",
                rationale="No extras allowed.",
                confidence=0.8,
                cleaning_config=CleaningConfig(),
                expected_artifact_path="codigo/data/processed/cwru_bearing/clean_signals",
                arbitrary_text="surprise",
            )

    def test_report_decision_requires_at_least_one_section(self):
        with self.assertRaises(ValidationError):
            ReportDecision(
                decision_id="report-001",
                rationale="Create report.",
                confidence=0.7,
                output_path="codigo/reports/cwru_bearing/report.md",
                output_format="markdown",
                sections=[],
            )

    def test_report_decision_accepts_structured_sections(self):
        decision = ReportDecision(
            decision_id="report-002",
            rationale="Create report with metrics.",
            confidence=0.7,
            output_path="codigo/reports/cwru_bearing/report.md",
            output_format="markdown",
            sections=[
                ReportSection(
                    title="Metricas",
                    include_metrics=True,
                    include_artifacts=True,
                    source_paths=["codigo/data/tensors/cwru_bearing/windows_features.csv"],
                )
            ],
        )

        self.assertEqual(decision.sections[0].title, "Metricas")

    def test_structuring_decision_accepts_comparison_candidates(self):
        decision = StructuringDecision(
            decision_id="struct-001",
            rationale="Use baseline windows but compare temporal resolution.",
            confidence=0.85,
            structuring_config=StructuringConfig(
                window_size=2048,
                overlap=0.5,
                main_channel="DE_time",
                target_sample_rate_hz=12000,
                label_mode="binary_anomaly",
                features=["mean", "std", "rms"],
            ),
            expected_features_path="codigo/data/tensors/cwru_bearing/windows_features.csv",
            expected_tensors_path="codigo/data/tensors/cwru_bearing/windows_raw.npz",
            expected_splits_path="codigo/data/tensors/cwru_bearing/splits.json",
            comparison_candidates=[
                StructuringAlternative(
                    alternative_id="win_1024_ov_50",
                    rationale="More temporal resolution.",
                    expected_effect="More windows and shorter context.",
                    structuring_config=StructuringConfig(
                        window_size=1024,
                        overlap=0.5,
                        main_channel="DE_time",
                        target_sample_rate_hz=12000,
                        label_mode="binary_anomaly",
                        features=["mean", "std", "rms"],
                    ),
                )
            ],
        )

        payload = decision.model_dump(mode="json")

        self.assertEqual(payload["comparison_candidates"][0]["alternative_id"], "win_1024_ov_50")
        json.dumps(payload)

    def test_modeling_decision_accepts_comparison_candidates(self):
        decision = ModelingDecision(
            decision_id="model-001",
            rationale="Compare supported anomaly detectors.",
            confidence=0.82,
            modeling_config=ModelingConfig(
                model_name="isolation_forest",
                random_state=42,
                hyperparameters={"n_estimators": 100, "threshold_quantile": 0.99},
            ),
            train_split="train",
            validation_split="validation",
            expected_model_path="codigo/models/cwru_bearing/isolation_forest.joblib",
            comparison_candidates=[
                ModelingAlternative(
                    alternative_id="pca_reconstruction_error",
                    rationale="Linear reconstruction baseline.",
                    expected_effect="Different false positive profile.",
                    modeling_config=ModelingConfig(
                        model_name="pca_reconstruction_error",
                        random_state=42,
                        hyperparameters={
                            "n_components": 0.95,
                            "threshold_quantile": 0.99,
                        },
                    ),
                )
            ],
        )

        payload = decision.model_dump(mode="json")

        self.assertEqual(
            payload["comparison_candidates"][0]["modeling_config"]["model_name"],
            "pca_reconstruction_error",
        )
        json.dumps(payload)

    def test_modeling_retry_decision_requires_config_when_retrying(self):
        with self.assertRaises(ValidationError):
            ModelingRetryDecision(
                decision_id="retry-001",
                rationale="Try again without a concrete config.",
                confidence=0.8,
                source_run_id="run-failed",
                attempt_number=1,
                max_attempts=2,
                should_retry=True,
                learning_summary="Recall is too low.",
                expected_effect="Increase recall.",
            )

    def test_modeling_retry_decision_accepts_stop_reason(self):
        decision = ModelingRetryDecision(
            decision_id="retry-002",
            rationale="No more useful retries.",
            confidence=0.8,
            source_run_id="run-failed",
            attempt_number=2,
            max_attempts=2,
            should_retry=False,
            learning_summary="Previous attempts exhausted the allowed options.",
            stop_reason="Maximum attempts reached without adequate improvement.",
            evidence_used=["metrics", "confusion_matrix"],
        )

        payload = decision.model_dump(mode="json")

        self.assertFalse(payload["should_retry"])
        self.assertEqual(payload["agent_name"], "modeler")
        json.dumps(payload)

    def test_reasoning_postmortem_is_json_serializable(self):
        postmortem = AgentReasoningPostmortem(
            postmortem_id="run-001:reasoning_postmortem:001",
            run_id="run-001",
            source_run_id="run-source",
            agent_name="modeler",
            decision_id="run-source:modeler_retry:001",
            attempt_number=1,
            max_attempts=2,
            hypothesis="Lower threshold should catch missed anomalies.",
            action_taken="Isolation Forest with threshold_quantile=0.95.",
            expected_effect="Increase recall with moderate FPR cost.",
            before_metrics={"recall": 0.6},
            after_metrics={"recall": 0.7},
            metric_deltas=[
                ReasoningMetricDelta(
                    metric="recall",
                    before=0.6,
                    after=0.7,
                    delta=0.1,
                    higher_is_better=True,
                    improved=True,
                )
            ],
            outcome="partially_supported",
            automatic_critique="Recall improved but FPR must still be checked.",
        )

        payload = postmortem.model_dump(mode="json")

        self.assertEqual(payload["outcome"], "partially_supported")
        json.dumps(payload)

    def test_human_reasoning_review_accepts_verdict(self):
        review = HumanReasoningReview(
            review_id="review-001",
            postmortem_id="postmortem-001",
            run_id="run-001",
            decision_id="decision-001",
            reviewer="advisor",
            verdict="partially_correct",
            rationale="Correct direction, unsafe magnitude.",
            reusable_as_context=True,
            tags=["threshold", "overcorrection"],
        )

        payload = review.model_dump(mode="json")

        self.assertEqual(payload["verdict"], "partially_correct")
        json.dumps(payload)


if __name__ == "__main__":
    unittest.main()
