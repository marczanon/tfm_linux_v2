import json
import unittest

from pydantic import ValidationError

from codigo.app.schemas.agent_decisions import (
    CleaningDecision,
    EvaluationDecision,
    ModelingAlternative,
    ModelingDecision,
    ModelingDecisionStrategy,
    ModelingRetryDecision,
    ReportDecision,
    ReportRevisionDecision,
    ReportSection,
    ReportVerificationDecision,
    ReportVerificationIssue,
    StructuringAlternative,
    StructuringDecision,
    SupervisorDecision,
)
from codigo.app.schemas.reasoning import (
    AgentReasoningPostmortem,
    HumanReasoningReview,
    ReasoningMetricDelta,
    ReportDebateRecord,
    ReportDebateTurn,
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

    def test_structuring_decision_declares_memory_usage(self):
        decision = StructuringDecision(
            decision_id="struct-memory-001",
            rationale="Use a prior window comparison as contextual evidence.",
            confidence=0.85,
            structuring_config=StructuringConfig(
                window_size=1024,
                overlap=0.5,
                main_channel="DE_time",
                target_sample_rate_hz=12000,
                label_mode="binary_anomaly",
                features=["mean", "std", "rms"],
            ),
            expected_features_path="codigo/data/tensors/cwru_bearing/windows_features.csv",
            expected_tensors_path="codigo/data/tensors/cwru_bearing/windows_raw.npz",
            expected_splits_path="codigo/data/tensors/cwru_bearing/splits.json",
            memory_context_id="struct-query:retrieved_memory_context",
            used_memory_context=True,
            memory_record_ids=["memory-structurer-window-001"],
            memory_usage_summary="Adapt a prior window-size comparison.",
            memory_record_uses=[
                {
                    "memory_record_id": "memory-structurer-window-001",
                    "usage": "adapted",
                    "influence_summary": "Use the memory as evidence for a comparable window.",
                }
            ],
        )

        payload = decision.model_dump(mode="json")

        self.assertTrue(payload["used_memory_context"])
        self.assertEqual(payload["memory_record_uses"][0]["usage"], "adapted")
        json.dumps(payload)

    def test_modeling_decision_accepts_comparison_candidates(self):
        decision = ModelingDecision(
            decision_id="model-001",
            rationale="Compare supported anomaly detectors.",
            confidence=0.82,
            decision_strategy=ModelingDecisionStrategy(
                strategy_type="model_family_selection",
                hypothesis="Compare supported model families before selecting one.",
            ),
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

    def test_threshold_calibration_strategy_requires_model_family_candidate(self):
        with self.assertRaises(ValidationError):
            ModelingDecision(
                decision_id="model-threshold-only",
                rationale="Only tune the threshold.",
                confidence=0.82,
                decision_strategy=ModelingDecisionStrategy(
                    strategy_type="threshold_calibration",
                    hypothesis="Try a lower threshold without considering model family.",
                ),
                modeling_config=ModelingConfig(
                    model_name="isolation_forest",
                    random_state=42,
                    hyperparameters={
                        "n_estimators": 100,
                        "threshold_quantile": 0.95,
                    },
                ),
                train_split="train",
                validation_split="validation",
                expected_model_path="codigo/models/cwru_bearing/isolation_forest.joblib",
                comparison_candidates=[],
            )

        decision = ModelingDecision(
            decision_id="model-threshold-with-family",
            rationale="Use threshold analysis but keep another family under comparison.",
            confidence=0.82,
            decision_strategy=ModelingDecisionStrategy(
                strategy_type="threshold_calibration",
                hypothesis="Assess whether threshold sensitivity explains the errors.",
                risk_notes=[
                    "Threshold analysis is diagnostic and does not replace model-family comparison."
                ],
            ),
            modeling_config=ModelingConfig(
                model_name="isolation_forest",
                random_state=42,
                hyperparameters={
                    "n_estimators": 100,
                    "threshold_quantile": 0.95,
                },
            ),
            train_split="train",
            validation_split="validation",
            expected_model_path="codigo/models/cwru_bearing/isolation_forest.joblib",
            comparison_candidates=[
                ModelingAlternative(
                    alternative_id="pca_reconstruction_error",
                    rationale="Different scoring geometry.",
                    modeling_config=ModelingConfig(
                        model_name="pca_reconstruction_error",
                        random_state=42,
                        hyperparameters={"threshold_quantile": 0.99},
                    ),
                )
            ],
        )

        self.assertEqual(
            decision.decision_strategy.strategy_type,
            "threshold_calibration",
        )

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

    def test_modeling_retry_decision_declares_memory_usage(self):
        decision = ModelingRetryDecision(
            decision_id="retry-003",
            rationale="Retry informed by a boundary memory.",
            confidence=0.8,
            source_run_id="run-failed",
            attempt_number=1,
            max_attempts=2,
            should_retry=True,
            learning_summary="A previous overcorrection warns against recall-only tuning.",
            retry_config=ModelingConfig(
                model_name="isolation_forest",
                random_state=42,
                hyperparameters={"n_estimators": 200, "threshold_quantile": 0.95},
            ),
            expected_effect="Increase recall while watching false positives.",
            memory_context_id="query-001:retrieved_memory_context",
            used_memory_context=True,
            memory_record_ids=["memory-overcorrection-001"],
            memory_usage_summary="Use the boundary memory as a cautionary example.",
            memory_record_uses=[
                {
                    "memory_record_id": "memory-overcorrection-001",
                    "usage": "adapted",
                    "influence_summary": "Lower threshold carefully, not blindly.",
                    "risk_mitigation": "Avoid a large threshold drop that repeats FPR=1.0.",
                }
            ],
            evidence_used=["failure_analysis", "memory-overcorrection-001"],
        )

        payload = decision.model_dump(mode="json")

        self.assertTrue(payload["used_memory_context"])
        self.assertEqual(payload["memory_record_ids"], ["memory-overcorrection-001"])
        self.assertEqual(payload["memory_record_uses"][0]["usage"], "adapted")
        json.dumps(payload)

    def test_modeling_retry_memory_ids_require_usage_flag(self):
        with self.assertRaises(ValidationError):
            ModelingRetryDecision(
                decision_id="retry-004",
                rationale="Cites memory while saying it was not used.",
                confidence=0.8,
                source_run_id="run-failed",
                attempt_number=1,
                max_attempts=2,
                should_retry=False,
                learning_summary="No retry.",
                stop_reason="No safe improvement.",
                used_memory_context=False,
                memory_record_ids=["memory-overcorrection-001"],
            )

    def test_evaluation_decision_declares_memory_usage(self):
        decision = EvaluationDecision(
            decision_id="eval-memory-001",
            rationale="Reject metrics using previous evaluation cautions as context.",
            confidence=0.9,
            evaluation={
                "approved": False,
                "summary": "Rejected by local protocol.",
                "next_action": "retry_with_new_config",
            },
            min_recall_required=0.9,
            max_false_positive_rate=0.1,
            memory_context_id="eval-query:retrieved_memory_context",
            used_memory_context=True,
            memory_record_ids=["memory-evaluator-tradeoff-001"],
            memory_usage_summary="Use memory as caution, not as approval.",
            memory_record_uses=[
                {
                    "memory_record_id": "memory-evaluator-tradeoff-001",
                    "usage": "adapted",
                    "influence_summary": "Keep recall and FPR bound to the protocol.",
                }
            ],
        )

        payload = decision.model_dump(mode="json")

        self.assertTrue(payload["used_memory_context"])
        self.assertEqual(payload["memory_record_ids"], ["memory-evaluator-tradeoff-001"])
        json.dumps(payload)

    def test_evaluation_memory_ids_require_usage_flag(self):
        with self.assertRaises(ValidationError):
            EvaluationDecision(
                decision_id="eval-memory-invalid-001",
                rationale="Cites memory without declaring use.",
                confidence=0.9,
                evaluation={
                    "approved": False,
                    "summary": "Rejected by local protocol.",
                    "next_action": "retry_with_new_config",
                },
                min_recall_required=0.9,
                max_false_positive_rate=0.1,
                used_memory_context=False,
                memory_record_ids=["memory-evaluator-tradeoff-001"],
            )

    def test_report_verification_decision_blocks_inconsistent_approval(self):
        issue = ReportVerificationIssue(
            issue_type="unsupported_claim",
            severity="high",
            claim_text="El informe declara validacion industrial.",
            reason="La evidencia solo cubre una ejecucion local.",
            evidence_refs=["report:final_report"],
            suggested_fix="Reformular como validacion local del TFM.",
        )

        with self.assertRaises(ValidationError):
            ReportVerificationDecision(
                decision_id="run:report_verifier:001",
                rationale="Verify report factuality.",
                confidence=0.9,
                report_path="codigo/reports/cwru_bearing/run/final_report.md",
                verification_status="approved",
                summary="Incorrectly approved.",
                unsupported_claims=[issue],
            )

    def test_report_verification_decision_serializes_issues(self):
        decision = ReportVerificationDecision(
            decision_id="run:report_verifier:001",
            rationale="Needs one factual correction.",
            confidence=0.82,
            report_path="codigo/reports/cwru_bearing/run/final_report.md",
            verification_status="needs_revision",
            summary="One claim needs correction.",
            unsupported_claims=[
                ReportVerificationIssue(
                    issue_type="unsupported_claim",
                    severity="medium",
                    claim_text="Metricas no existentes.",
                    reason="La metrica citada no aparece en el estado.",
                    evidence_refs=["metrics:missing"],
                    suggested_fix="Eliminar la metrica o citar una metrica real.",
                )
            ],
            required_corrections=["Eliminar la metrica no soportada."],
        )

        payload = decision.model_dump(mode="json")

        self.assertEqual(payload["agent_name"], "report_verifier")
        self.assertEqual(payload["verification_status"], "needs_revision")
        json.dumps(payload)

    def test_report_revision_decision_requires_rationale_for_rejected_issues(self):
        with self.assertRaises(ValidationError):
            ReportRevisionDecision(
                decision_id="run:report_writer_revision:001",
                rationale="Reject without explaining.",
                confidence=0.7,
                revision_round=1,
                revision_of_decision_id="run:report_writer:001",
                verifier_decision_id="run:report_verifier:001",
                output_path="codigo/reports/cwru_bearing/run/final_report.md",
                sections=[ReportSection(title="Resumen ejecutivo")],
                rejected_issue_ids=["issue-001"],
            )

    def test_report_debate_record_serializes_turns(self):
        record = ReportDebateRecord(
            debate_id="run:report_debate:001",
            run_id="run",
            initial_report_decision_id="run:report_writer:001",
            initial_verifier_decision_id="run:report_verifier:001",
            final_report_decision_id="run:report_writer_revision:001",
            final_verifier_decision_id="run:report_verifier:002",
            status="approved_after_revision",
            max_rounds=1,
            rounds_used=1,
            turns=[
                ReportDebateTurn(
                    turn_id="run:report_debate:writer:initial",
                    round_index=0,
                    speaker_agent="report_writer",
                    intent="draft",
                    human_summary="Redactor genera borrador.",
                )
            ],
            final_summary="Informe aceptado tras revision.",
        )

        payload = record.model_dump(mode="json")

        self.assertEqual(payload["status"], "approved_after_revision")
        self.assertEqual(payload["turns"][0]["speaker_agent"], "report_writer")
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
