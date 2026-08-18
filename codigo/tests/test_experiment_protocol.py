import json
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from codigo.app.graph.pipeline import PipelineAgents, PipelineExecutors
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.agent_decisions import (
    DecisionGenerationTrace,
    ModelingAlternative,
    ModelingDecision,
    ModelingDecisionStrategy,
    StructuringAlternative,
    StructuringDecision,
)
from codigo.app.services.experiment_protocol import (
    ExperimentPlan,
    ExperimentSpec,
    PreQwenCheckEvidence,
    assess_pre_qwen_readiness,
    current_pre_qwen_capability_evidence,
    cwru_model_experiment_plan_from_decision,
    cwru_window_experiment_plan_from_decision,
    default_cwru_experiment_plan,
    default_run_to_failure_model_suite_plan,
    run_cwru_experiment_plan,
    run_run_to_failure_experiment_plan,
    run_to_failure_model_experiment_plan_from_decision,
    write_pre_qwen_readiness_artifacts,
    _experiment_agents,
    _run_to_failure_experiment_agents,
)
from codigo.app.services.nasa_ims_temporal_policy import (
    NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
)
from codigo.app.services.run_persistence import RunSnapshot
from codigo.app.services.run_registry import MetricComparison, RunComparison, RunComparisonRow
from codigo.app.schemas.executor_results import (
    CleaningResult,
    EvaluationExecutorResult,
    ManifestResult,
    ModelingResult,
    ProfileResult,
    ReportExecutorResult,
    StructuringResult,
)
from codigo.app.schemas.state import ArtifactRef, ModelingConfig, StructuringConfig
from codigo.scripts.run_run_to_failure_model_suite import (
    DEFAULT_RUN_TO_FAILURE_V1_RAW_PATH,
    DEFAULT_RUN_TO_FAILURE_V2_RAW_PATH,
    _effective_plan_id,
    _effective_raw_path,
    _execution_manifest,
    _parse_model_families,
    _summary,
)


class ExperimentProtocolTests(unittest.TestCase):
    def test_pre_qwen_matrix_is_complete_and_current_evidence_stays_blocked(self):
        assessment = assess_pre_qwen_readiness(
            current_pre_qwen_capability_evidence()
        )
        checks = {check.check_id: check for check in assessment.checks}
        expected_perturbations = {
            "perturbation_channels",
            "perturbation_sample_rate",
            "perturbation_gain_offset_polarity",
            "perturbation_nan_dropout",
            "perturbation_temporal_order",
            "perturbation_truncated_trajectory",
            "perturbation_future_label_bait",
            "perturbation_adversarial_memory_corpus",
        }

        self.assertEqual(assessment.verdict, "blocked")
        self.assertIn("BLOCKED", assessment.verdict_reason)
        self.assertTrue(all(check.required for check in assessment.checks))
        self.assertTrue(expected_perturbations.issubset(checks))
        self.assertIn("trace_origin_attempt_fallback", checks)
        self.assertIn("trace_decision_config_artifact_link", checks)
        self.assertIn("corpus_frozen_versioned", checks)
        self.assertIn("corpus_no_future_or_label_leakage", checks)
        self.assertIn("dataset_nasa_ims_official", checks)
        self.assertIn("dataset_cwru_official", checks)
        self.assertIn("dataset_generic_third_format", checks)
        self.assertEqual(
            checks["dataset_nasa_ims_official"].availability,
            "available",
        )
        self.assertEqual(
            checks["dataset_nasa_ims_official"].outcome,
            "not_run",
        )
        self.assertTrue(checks["dataset_nasa_ims_official"].blocking)
        self.assertEqual(
            checks["trace_origin_attempt_fallback"].availability,
            "available",
        )
        self.assertEqual(
            checks["trace_origin_attempt_fallback"].outcome,
            "not_run",
        )
        self.assertEqual(
            checks["dataset_generic_third_format"].availability,
            "pending",
        )
        self.assertIn(
            "dataset_nasa_ims_official",
            assessment.available_check_ids,
        )
        self.assertIn(
            "dataset_generic_third_format",
            assessment.pending_check_ids,
        )
        self.assertEqual(assessment.passed_check_ids, [])
        self.assertEqual(
            checks["perturbation_channels"].criterion_kind,
            "invariance",
        )
        self.assertEqual(
            checks["perturbation_sample_rate"].criterion_kind,
            "adaptation",
        )

    def test_pre_qwen_readiness_requires_every_check_to_pass_with_evidence(self):
        matrix = assess_pre_qwen_readiness()
        evidence = [
            PreQwenCheckEvidence(
                check_id=check.check_id,
                availability="available",
                outcome="passed",
                evidence_refs=[f"test-evidence:{check.check_id}"],
            )
            for check in reversed(matrix.checks)
        ]

        assessment = assess_pre_qwen_readiness(evidence)

        self.assertEqual(assessment.verdict, "ready")
        self.assertEqual(assessment.blocker_ids, [])
        self.assertEqual(assessment.pending_check_ids, [])
        self.assertEqual(assessment.not_run_check_ids, [])
        self.assertEqual(
            assessment.passed_check_ids,
            [check.check_id for check in assessment.checks],
        )

    def test_pre_qwen_evidence_rejects_unverifiable_or_ambiguous_states(self):
        with self.assertRaisesRegex(ValueError, "at least one evidence ref"):
            PreQwenCheckEvidence(
                check_id="dataset_cwru_official",
                availability="available",
            )

        with self.assertRaisesRegex(ValueError, "pending checks"):
            PreQwenCheckEvidence(
                check_id="dataset_cwru_official",
                availability="pending",
                outcome="passed",
                evidence_refs=["invalid:pending-check"],
            )

        with self.assertRaisesRegex(ValueError, "unknown pre-Qwen check_id"):
            assess_pre_qwen_readiness(
                [PreQwenCheckEvidence(check_id="unknown_requirement")]
            )

        duplicated = PreQwenCheckEvidence(check_id="dataset_cwru_official")
        with self.assertRaisesRegex(ValueError, "duplicated pre-Qwen evidence"):
            assess_pre_qwen_readiness([duplicated, duplicated])

    def test_pre_qwen_artifacts_are_deterministic_and_do_not_claim_execution(self):
        assessment = assess_pre_qwen_readiness(
            current_pre_qwen_capability_evidence()
        )
        with tempfile.TemporaryDirectory() as tmp:
            paths = write_pre_qwen_readiness_artifacts(
                assessment,
                output_dir=Path(tmp),
            )
            json_path = Path(paths.json_path)
            markdown_path = Path(paths.markdown_path)
            first_json = json_path.read_text(encoding="utf-8")
            first_markdown = markdown_path.read_text(encoding="utf-8")

            write_pre_qwen_readiness_artifacts(
                assessment,
                output_dir=Path(tmp),
            )

            self.assertEqual(first_json, json_path.read_text(encoding="utf-8"))
            self.assertEqual(
                first_markdown,
                markdown_path.read_text(encoding="utf-8"),
            )

        payload = json.loads(first_json)
        self.assertEqual(payload["verdict"], "blocked")
        self.assertNotIn("generated_at", payload)
        self.assertTrue(payload["not_run_check_ids"])
        self.assertIn("# Preparacion pre-Qwen: BLOCKED", first_markdown)
        self.assertIn("no acredita ejecuciones", first_markdown)
        self.assertIn("Decision de reutilizacion", first_markdown)
        self.assertNotIn("| ID |", first_markdown)

    def test_default_plan_defines_two_supported_isolation_forest_runs(self):
        plan = default_cwru_experiment_plan()

        self.assertEqual(plan.plan_id, "cwru_iforest_threshold_v1")
        self.assertEqual(len(plan.experiments), 2)
        self.assertEqual(
            [spec.experiment_id for spec in plan.experiments],
            ["baseline_threshold_099", "conservative_threshold_100"],
        )
        self.assertEqual(
            [spec.modeling_config.model_name for spec in plan.experiments],
            ["isolation_forest", "isolation_forest"],
        )
        self.assertEqual(
            [
                spec.modeling_config.hyperparameters["threshold_quantile"]
                for spec in plan.experiments
            ],
            [0.99, 1.0],
        )
        self.assertTrue(
            all(spec.modeling_config.hyperparameters["n_jobs"] == 1 for spec in plan.experiments)
        )
        self.assertTrue(all(spec.structuring_config is None for spec in plan.experiments))

    def test_experiment_report_writer_records_protocol_generation_trace(self):
        spec = default_cwru_experiment_plan().experiments[0]
        agents = _experiment_agents(spec, Path("reports/controlled-experiment"))
        state = validate_state(
            create_initial_cwru_state(
                thread_id="experiment-report-trace-thread",
                run_id="experiment-report-trace-run",
            )
        )

        decision = agents.report_writer(state)

        self.assertIsNotNone(decision.generation_trace)
        assert decision.generation_trace is not None
        self.assertEqual(decision.generation_trace.origin, "protocol_restricted")
        self.assertEqual(
            decision.generation_trace.attempt_id,
            f"{decision.decision_id}:attempt:001",
        )

    def test_window_plan_is_built_from_agent_structuring_decision(self):
        decision = StructuringDecision(
            decision_id="run:structurer:001",
            rationale="Selected middle-size windows.",
            confidence=0.9,
            structuring_config=_structuring_config(2048, 0.5),
            expected_features_path="codigo/data/tensors/cwru_bearing/windows_features.csv",
            expected_tensors_path="codigo/data/tensors/cwru_bearing/windows_raw.npz",
            expected_splits_path="codigo/data/tensors/cwru_bearing/splits.json",
            comparison_candidates=[
                StructuringAlternative(
                    alternative_id="short_window",
                    rationale="Compare higher temporal resolution.",
                    expected_effect="More windows.",
                    structuring_config=_structuring_config(1024, 0.5),
                )
            ],
        )

        plan = cwru_window_experiment_plan_from_decision(decision, plan_id="window_plan")

        self.assertEqual(plan.plan_id, "window_plan")
        self.assertEqual(len(plan.experiments), 2)
        self.assertEqual(
            [spec.structuring_config.window_size for spec in plan.experiments],
            [2048, 1024],
        )
        self.assertEqual(
            [spec.experiment_id for spec in plan.experiments],
            ["win_2048_ov_50_selected", "win_1024_ov_50_short_window"],
        )

    def test_window_plan_requires_agent_to_propose_two_unique_configs(self):
        decision = StructuringDecision(
            decision_id="run:structurer:001",
            rationale="Only one config.",
            confidence=0.9,
            structuring_config=_structuring_config(2048, 0.5),
            expected_features_path="codigo/data/tensors/cwru_bearing/windows_features.csv",
            expected_tensors_path="codigo/data/tensors/cwru_bearing/windows_raw.npz",
            expected_splits_path="codigo/data/tensors/cwru_bearing/splits.json",
        )

        with self.assertRaisesRegex(ValueError, "at least two unique"):
            cwru_window_experiment_plan_from_decision(decision)

    def test_experiment_plan_rejects_path_like_identifiers(self):
        plan = ExperimentPlan(
            plan_id="invalid/plan",
            description="invalid plan",
            experiments=[
                _spec("one", "run-one", 0.99),
                _spec("two", "run-two", 1.0),
            ],
        )

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "plan_id"):
                run_cwru_experiment_plan(
                    plan,
                    experiments_dir=Path(tmp) / "experiments",
                    runs_dir=Path(tmp) / "runs",
                    executor_factory=lambda _spec, _dir: _fake_executors(_dir, {}),
                )

    def test_run_cwru_experiment_plan_persists_and_compares_fake_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            seen_thresholds: dict[str, float] = {}
            plan = ExperimentPlan(
                plan_id="test_plan",
                description="test experimental plan",
                experiments=[
                    _spec("baseline", "run-baseline", 0.99),
                    _spec("candidate", "run-candidate", 1.0),
                ],
            )

            result = run_cwru_experiment_plan(
                plan,
                experiments_dir=base / "experiments",
                runs_dir=base / "runs",
                raw_path=str(base / "raw"),
                executor_factory=lambda spec, experiment_dir: _fake_executors(
                    experiment_dir,
                    seen_thresholds,
                    f1_score=0.82 if spec.experiment_id == "baseline" else 0.88,
                    false_positive_rate=0.06 if spec.experiment_id == "baseline" else 0.03,
                ),
            )

            plan_payload = json.loads(Path(result.plan_path).read_text(encoding="utf-8"))
            comparison_payload = json.loads(
                Path(result.comparison_path).read_text(encoding="utf-8")
            )
            table = Path(result.results_table_path).read_text(encoding="utf-8")

        self.assertEqual([run.run_id for run in result.runs], ["run-baseline", "run-candidate"])
        self.assertEqual(seen_thresholds, {"baseline": 0.99, "candidate": 1.0})
        self.assertEqual(plan_payload["plan_id"], "test_plan")
        self.assertEqual(comparison_payload["run_ids"], ["run-baseline", "run-candidate"])
        self.assertEqual(
            result.comparison.metrics[2].metric,
            "f1_score",
        )
        self.assertEqual(result.comparison.metrics[2].best_run_id, "run-candidate")
        self.assertIn(
            "| baseline | `run-baseline` | n/a | n/a | isolation_forest | 0.9900",
            table,
        )
        self.assertIn(
            "| candidate | `run-candidate` | n/a | n/a | isolation_forest | 1.0000",
            table,
        )

    def test_run_window_plan_applies_structuring_config_in_fake_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            seen_thresholds: dict[str, float] = {}
            seen_windows: dict[str, int] = {}
            plan = ExperimentPlan(
                plan_id="window_plan",
                description="window plan",
                experiments=[
                    _spec(
                        "short",
                        "run-short",
                        0.99,
                        structuring_config=_structuring_config(1024, 0.5),
                    ),
                    _spec(
                        "long",
                        "run-long",
                        0.99,
                        structuring_config=_structuring_config(4096, 0.5),
                    ),
                ],
            )

            result = run_cwru_experiment_plan(
                plan,
                experiments_dir=base / "experiments",
                runs_dir=base / "runs",
                raw_path=str(base / "raw"),
                executor_factory=lambda spec, experiment_dir: _fake_executors(
                    experiment_dir,
                    seen_thresholds,
                    seen_windows=seen_windows,
                ),
            )
            table = Path(result.results_table_path).read_text(encoding="utf-8")

        self.assertEqual(seen_windows, {"short": 1024, "long": 4096})
        self.assertIn("| short | `run-short` | 1024 | 0.5000", table)
        self.assertIn("| long | `run-long` | 4096 | 0.5000", table)

    def test_model_plan_is_built_from_agent_modeling_decision(self):
        decision = ModelingDecision(
            decision_id="run:modeler:001",
            rationale="Selected Isolation Forest.",
            confidence=0.9,
            modeling_config=_modeling_config("isolation_forest", {"threshold_quantile": 0.99}),
            train_split="train",
            validation_split="validation",
            expected_model_path="codigo/models/cwru_bearing/isolation_forest.joblib",
            comparison_candidates=[
                ModelingAlternative(
                    alternative_id="pca",
                    rationale="Compare linear reconstruction error.",
                    expected_effect="Different precision/recall trade-off.",
                    modeling_config=_modeling_config(
                        "pca_reconstruction_error",
                        {"n_components": 0.95, "threshold_quantile": 0.99},
                    ),
                )
            ],
        )

        plan = cwru_model_experiment_plan_from_decision(decision, plan_id="model_plan")

        self.assertEqual(plan.plan_id, "model_plan")
        self.assertEqual(len(plan.experiments), 2)
        self.assertEqual(
            [spec.modeling_config.model_name for spec in plan.experiments],
            ["isolation_forest", "pca_reconstruction_error"],
        )

    def test_model_plan_requires_agent_to_propose_two_unique_configs(self):
        decision = ModelingDecision(
            decision_id="run:modeler:001",
            rationale="Only one model.",
            confidence=0.9,
            modeling_config=_modeling_config("isolation_forest", {"threshold_quantile": 0.99}),
            train_split="train",
            validation_split="validation",
            expected_model_path="codigo/models/cwru_bearing/isolation_forest.joblib",
        )

        with self.assertRaisesRegex(ValueError, "at least two unique"):
            cwru_model_experiment_plan_from_decision(decision)

    def test_default_run_to_failure_suite_defines_four_model_families(self):
        plan = default_run_to_failure_model_suite_plan()

        self.assertEqual(plan.dataset, "nasa_ims_bearing")
        self.assertEqual(plan.adapter_id, "nasa_ims_bearing")
        self.assertEqual(plan.dataset_policy_id, "nasa_ims_temporal_v1")
        self.assertEqual(plan.supervision_profile, "run_to_failure_degradation")
        self.assertEqual(
            [spec.modeling_config.model_name for spec in plan.experiments],
            [
                "pca_reconstruction_error",
                "isolation_forest",
                "one_class_svm",
                "autoencoder_dense",
            ],
        )

    def test_causal_v2_suite_excludes_advanced_model_until_causal_readiness(self):
        plan = default_run_to_failure_model_suite_plan(
            plan_id="rtf_causal_v2",
            dataset_policy_id=NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
        )

        self.assertEqual(
            plan.dataset_policy_id,
            NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
        )
        self.assertEqual(
            [spec.modeling_config.model_name for spec in plan.experiments],
            [
                "pca_reconstruction_error",
                "isolation_forest",
                "one_class_svm",
            ],
        )
        structuring_configs = [
            spec.structuring_config for spec in plan.experiments
        ]
        self.assertTrue(all(config is not None for config in structuring_configs))
        self.assertTrue(
            all(config == structuring_configs[0] for config in structuring_configs)
        )
        fixed = structuring_configs[0]
        assert fixed is not None
        self.assertEqual(fixed.window_size, 2048)
        self.assertEqual(fixed.overlap, 0.5)
        self.assertEqual(fixed.window_size * (1.0 - fixed.overlap), 1024)
        self.assertEqual(fixed.main_channel, "channel_1")
        self.assertEqual(fixed.target_sample_rate_hz, 20000)
        for spec in plan.experiments:
            effect = (spec.expected_effect or "").lower()
            self.assertNotIn("alerta temprana", effect)
            self.assertNotIn("falsas alarmas", effect)
            self.assertNotIn("lead time", effect)
        self.assertNotIn("F1", plan.description)
        self.assertIn("monitorizacion ciega", plan.description)
        self.assertIn("compatibilidad del contrato legacy", plan.description)
        self.assertIn("target vacio en calibracion y monitorizacion", plan.description)

    def test_causal_v2_suite_rejects_autoencoder_and_single_family_plans(self):
        with self.assertRaisesRegex(ValueError, "autoencoder_dense is disabled"):
            default_run_to_failure_model_suite_plan(
                dataset_policy_id=NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
                model_families=["pca_reconstruction_error", "autoencoder_dense"],
            )

        with self.assertRaisesRegex(ValueError, "at least two distinct"):
            default_run_to_failure_model_suite_plan(
                dataset_policy_id=NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
                model_families=["pca_reconstruction_error"],
            )

    def test_suite_cli_family_parser_accepts_repeated_and_csv_values(self):
        selected = _parse_model_families(
            [
                "pca_reconstruction_error,isolation_forest",
                "one_class_svm",
                "isolation_forest",
            ]
        )

        self.assertEqual(
            selected,
            [
                "pca_reconstruction_error",
                "isolation_forest",
                "one_class_svm",
            ],
        )
        plan = default_run_to_failure_model_suite_plan(
            dataset_policy_id=NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
            model_families=selected,
        )
        self.assertEqual(len(plan.experiments), 3)

    def test_suite_cli_uses_policy_specific_defaults_without_breaking_v1(self):
        v1 = SimpleNamespace(
            plan_id=None,
            raw_path=None,
            dataset_policy_id="nasa_ims_temporal_v1",
        )
        v2 = SimpleNamespace(
            plan_id=None,
            raw_path=None,
            dataset_policy_id=NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
        )

        self.assertEqual(_effective_plan_id(v1), "run_to_failure_agentic_model_suite_v1")
        self.assertEqual(_effective_raw_path(v1), DEFAULT_RUN_TO_FAILURE_V1_RAW_PATH)
        self.assertEqual(_effective_plan_id(v2), "run_to_failure_agentic_model_suite_v2")
        self.assertEqual(_effective_raw_path(v2), DEFAULT_RUN_TO_FAILURE_V2_RAW_PATH)

    def test_execution_manifest_persists_llm_configuration_without_hosts(self):
        args = _suite_args(use_memory=False)

        manifest = _execution_manifest(args)
        plan = default_run_to_failure_model_suite_plan(
            dataset_policy_id=NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
        ).model_copy(update={"execution_manifest": manifest})
        payload = plan.model_dump(mode="json")["execution_manifest"]

        self.assertTrue(payload["use_llm"])
        self.assertEqual(payload["llm_backend"], "ollama")
        self.assertEqual(payload["llm_model"], "qwen3.5:4b")
        self.assertTrue(payload["llm_think"])
        self.assertEqual(payload["llm_timeout_seconds"], 180.0)
        self.assertFalse(payload["use_memory"])
        self.assertEqual(payload["memory_backend"], "disabled")
        self.assertNotIn("host", json.dumps(payload).lower())

    def test_execution_manifest_persists_memory_backend_embedding_and_top_k(self):
        args = _suite_args(use_memory=True)

        with patch.dict("os.environ", {"TFM_MEMORY_BACKEND": "qdrant"}):
            manifest = _execution_manifest(args)

        self.assertTrue(manifest.use_memory)
        self.assertEqual(manifest.memory_backend, "qdrant")
        self.assertEqual(manifest.embedding_provider, "ollama")
        self.assertEqual(manifest.embedding_model, "qwen3-embedding:0.6b")
        self.assertEqual(manifest.embedding_timeout_seconds, 60.0)
        self.assertEqual(manifest.structurer_top_k, 4)
        self.assertEqual(manifest.modeler_top_k, 5)
        self.assertEqual(manifest.evaluator_top_k, 6)
        self.assertEqual(manifest.memory_min_similarity, 0.2)
        self.assertTrue(manifest.generate_decision_memory)
        self.assertTrue(manifest.require_human_review_before_reuse)

    def test_run_to_failure_model_plan_is_built_from_modeler_decision(self):
        decision = ModelingDecision(
            decision_id="rtf:modeler:001",
            rationale="Selected PCA for temporal health score.",
            confidence=0.9,
            modeling_config=_modeling_config(
                "pca_reconstruction_error",
                {"n_components": 0.95, "threshold_quantile": 0.99},
            ),
            train_split="train",
            validation_split="validation",
            expected_model_path="codigo/models/nasa_ims_bearing/pca.joblib",
            comparison_candidates=[
                ModelingAlternative(
                    alternative_id="iforest",
                    rationale="Compare isolation score.",
                    expected_effect="Temporal sensitivity comparison.",
                    modeling_config=_modeling_config(
                        "isolation_forest",
                        {"threshold_quantile": 0.99},
                    ),
                ),
                ModelingAlternative(
                    alternative_id="ocsvm",
                    rationale="Compare nonlinear margin.",
                    expected_effect="False alarm trade-off comparison.",
                    modeling_config=_modeling_config(
                        "one_class_svm",
                        {"threshold_quantile": 0.99},
                    ),
                ),
            ],
        )

        plan = run_to_failure_model_experiment_plan_from_decision(
            decision,
            plan_id="rtf_model_plan",
        )

        self.assertEqual(plan.dataset, "nasa_ims_bearing")
        self.assertEqual(len(plan.experiments), 3)
        self.assertEqual(
            [spec.modeling_config.model_name for spec in plan.experiments],
            [
                "pca_reconstruction_error",
                "isolation_forest",
                "one_class_svm",
            ],
        )

    def test_run_to_failure_suite_preserves_agent_memory_reasoning_under_fixed_model(self):
        spec = default_run_to_failure_model_suite_plan().experiments[0]
        seen_memory_contexts = []
        seen_agent_proposals = []

        def base_modeler(state, *, memory_context=None):
            seen_memory_contexts.append(memory_context)
            proposal = ModelingDecision(
                decision_id=f"{state.run_id}:modeler:base",
                rationale="The recalled warning changes the temporal hypothesis.",
                confidence=0.82,
                generation_trace=DecisionGenerationTrace.for_decision(
                    f"{state.run_id}:modeler:base",
                    origin="llm",
                ),
                decision_strategy=ModelingDecisionStrategy(
                    strategy_type="feature_model_fit",
                    hypothesis="Prioritize stable lead time over isolated score peaks.",
                    evidence_refs=["memory:warning-lead-time"],
                ),
                modeling_config=_modeling_config(
                    "isolation_forest",
                    {"threshold_quantile": 0.99},
                ),
                expected_model_path="codigo/models/base.joblib",
                memory_context_id="memory-context-001",
                used_memory_context=True,
                memory_record_ids=["memory-warning-lead-time"],
                memory_usage_summary="Used as a warning against isolated peaks.",
                memory_record_uses=[
                    {
                        "memory_record_id": "memory-warning-lead-time",
                        "usage": "adapted",
                        "influence_summary": "Favours persistent lead time.",
                        "risk_mitigation": "The suite still fixes the model family.",
                    }
                ],
            )
            seen_agent_proposals.append(proposal)
            return proposal

        agents = _run_to_failure_experiment_agents(
            spec,
            base_agents=PipelineAgents(modeler=base_modeler),
        )
        state = validate_state(
            create_initial_cwru_state(
                thread_id="rtf-agent-memory-thread",
                run_id="rtf-agent-memory",
                raw_path="codigo/data/raw/nasa_ims_bearing",
            )
        )
        memory_context = object()

        decision = agents.modeler(state, memory_context=memory_context)

        self.assertEqual(seen_memory_contexts, [memory_context])
        self.assertEqual(decision.modeling_config, spec.modeling_config)
        self.assertNotIn(
            "Prioritize stable lead time over isolated score peaks.",
            decision.decision_strategy.hypothesis,
        )
        self.assertIn("pca_reconstruction_error", decision.decision_strategy.hypothesis)
        self.assertFalse(decision.used_memory_context)
        self.assertEqual(decision.memory_record_ids, [])
        self.assertIsNotNone(decision.protocol_trace)
        trace = decision.protocol_trace
        assert trace is not None
        self.assertEqual(
            trace.agent_proposal.model_dump(),
            seen_agent_proposals[0].model_dump(exclude={"protocol_trace"}),
        )
        self.assertTrue(trace.proposal_influenced_by_memory)
        self.assertFalse(trace.execution_influenced_by_memory)
        self.assertEqual(
            trace.agent_proposal.memory_record_ids,
            ["memory-warning-lead-time"],
        )
        self.assertEqual(
            trace.agent_proposal.decision_strategy.hypothesis,
            "Prioritize stable lead time over isolated score peaks.",
        )
        self.assertIn("modeling_config", trace.overridden_fields)
        self.assertIn("used_memory_context", trace.overridden_fields)
        self.assertIn("generation_trace", trace.overridden_fields)
        self.assertEqual(decision.generation_trace.origin, "protocol_restricted")
        self.assertEqual(decision.generation_trace.attempt_index, 2)
        self.assertEqual(trace.agent_proposal.generation_trace.origin, "llm")
        restored = ModelingDecision.model_validate_json(decision.model_dump_json())
        self.assertEqual(restored.protocol_trace, trace)

    def test_causal_v2_fixed_strategy_hides_future_and_binary_evidence(self):
        spec = default_run_to_failure_model_suite_plan(
            dataset_policy_id=NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
        ).experiments[0]

        def base_modeler(state, *, memory_context=None):
            del memory_context
            return ModelingDecision(
                decision_id=f"{state.run_id}:modeler:base",
                rationale="Historical proposal retained only for audit.",
                confidence=0.7,
                decision_strategy=ModelingDecisionStrategy(
                    strategy_type="feature_model_fit",
                    hypothesis="Maximize lead time before failure and binary F1.",
                    evidence_refs=[
                        "metric:mean_lead_time_to_failure",
                        "metric:f1_score",
                    ],
                ),
                modeling_config=_modeling_config(
                    "isolation_forest",
                    {"threshold_quantile": 0.99},
                ),
                expected_model_path="codigo/models/proposal.joblib",
            )

        agents = _run_to_failure_experiment_agents(
            spec,
            base_agents=PipelineAgents(modeler=base_modeler),
            dataset_policy_id=NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
        )
        state = validate_state(
            create_initial_cwru_state(
                thread_id="rtf-causal-v2-thread",
                run_id="rtf-causal-v2",
                raw_path="codigo/data/raw/nasa_ims_bearing/official/2nd_test",
            )
        )

        decision = agents.modeler(state)

        executed_strategy = json.dumps(
            decision.decision_strategy.model_dump(mode="json")
        ).lower()
        for unavailable in (
            "lead_time",
            "before_failure",
            "time_to_failure",
            "f1_score",
            "precision",
            "recall",
        ):
            self.assertNotIn(unavailable, executed_strategy)
        self.assertIn("partition:baseline_train", executed_strategy)
        self.assertIn("constraint:monitoring_held_out", executed_strategy)
        trace = decision.protocol_trace
        assert trace is not None
        self.assertEqual(
            trace.agent_proposal.decision_strategy.hypothesis,
            "Maximize lead time before failure and binary F1.",
        )
        self.assertFalse(trace.execution_influenced_by_memory)

    def test_causal_v2_suite_observes_structurer_before_fixed_config(self):
        spec = default_run_to_failure_model_suite_plan(
            dataset_policy_id=NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
        ).experiments[0]
        seen_memory_contexts = []
        seen_agent_proposals = []

        def base_structurer(state, *, memory_context=None):
            seen_memory_contexts.append(memory_context)
            proposal = StructuringDecision(
                decision_id=f"{state.run_id}:structurer:base",
                rationale="Memory suggests shorter windows for earlier changes.",
                confidence=0.78,
                generation_trace=DecisionGenerationTrace.for_decision(
                    f"{state.run_id}:structurer:base",
                    origin="llm",
                ),
                structuring_config=_structuring_config(1024, 0.5),
                expected_features_path="codigo/data/tensors/proposal/features.csv",
                expected_tensors_path="codigo/data/tensors/proposal/windows.npz",
                expected_splits_path="codigo/data/tensors/proposal/splits.json",
                memory_context_id="memory-context-structurer",
                used_memory_context=True,
                memory_record_ids=["memory-short-window"],
                memory_usage_summary="Adapted a prior temporal-resolution lesson.",
                memory_record_uses=[
                    {
                        "memory_record_id": "memory-short-window",
                        "usage": "adapted",
                        "influence_summary": "Favours earlier temporal changes.",
                        "risk_mitigation": "Keep the fixed suite config for execution.",
                    }
                ],
            )
            seen_agent_proposals.append(proposal)
            return proposal

        agents = _run_to_failure_experiment_agents(
            spec,
            base_agents=PipelineAgents(structurer=base_structurer),
            dataset_policy_id=NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
        )
        state = validate_state(
            create_initial_cwru_state(
                thread_id="rtf-structurer-memory-thread",
                run_id="rtf-structurer-memory",
                raw_path="codigo/data/raw/nasa_ims_bearing",
            )
        )
        memory_context = object()

        decision = agents.structurer(state, memory_context=memory_context)

        self.assertEqual(seen_memory_contexts, [memory_context])
        self.assertEqual(decision.structuring_config, spec.structuring_config)
        self.assertEqual(decision.structuring_config.window_size, 2048)
        self.assertEqual(decision.structuring_config.overlap, 0.5)
        self.assertFalse(decision.used_memory_context)
        self.assertEqual(decision.memory_record_ids, [])
        self.assertIsNotNone(decision.protocol_trace)
        trace = decision.protocol_trace
        assert trace is not None
        self.assertEqual(
            trace.agent_proposal.model_dump(),
            seen_agent_proposals[0].model_dump(exclude={"protocol_trace"}),
        )
        self.assertEqual(
            trace.agent_proposal.structuring_config,
            _structuring_config(1024, 0.5),
        )
        self.assertTrue(trace.proposal_influenced_by_memory)
        self.assertFalse(trace.execution_influenced_by_memory)
        self.assertIn("structuring_config", trace.overridden_fields)
        self.assertIn("used_memory_context", trace.overridden_fields)
        self.assertIn("generation_trace", trace.overridden_fields)
        self.assertEqual(decision.generation_trace.origin, "protocol_restricted")
        self.assertEqual(decision.generation_trace.attempt_index, 2)
        self.assertEqual(trace.agent_proposal.generation_trace.origin, "llm")
        restored = StructuringDecision.model_validate_json(decision.model_dump_json())
        self.assertEqual(restored.protocol_trace, trace)

    def test_run_to_failure_plan_uses_temporal_results_table_with_fake_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plan = default_run_to_failure_model_suite_plan(plan_id="rtf_suite")
            result = run_run_to_failure_experiment_plan(
                plan,
                raw_path=str(base / "raw"),
                experiments_dir=base / "experiments",
                runs_dir=base / "runs",
                run_factory=_fake_run_to_failure_run,
                comparison_factory=_fake_run_to_failure_comparison,
            )
            table = Path(result.results_table_path).read_text(encoding="utf-8")

            self.assertEqual(len(result.runs), 4)
        self.assertEqual(result.comparison.run_ids, [spec.run_id for spec in plan.experiments])
        self.assertIn("Onset confirmado", table)
        self.assertIn("Lead persistente", table)
        self.assertIn("HI drop", table)
        self.assertIn("HI mono", table)
        self.assertIn("F1 aux", table)
        self.assertIn("Las metricas binarias se muestran como auxiliares/proxy", table)

    def test_causal_v2_results_table_omits_binary_and_future_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            plan = default_run_to_failure_model_suite_plan(
                plan_id="rtf_causal_v2",
                dataset_policy_id=NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
            )
            result = run_run_to_failure_experiment_plan(
                plan,
                raw_path=str(base / "official"),
                experiments_dir=base / "experiments",
                runs_dir=base / "runs",
                run_factory=_fake_run_to_failure_run,
                comparison_factory=_fake_run_to_failure_comparison,
            )
            table = Path(result.results_table_path).read_text(encoding="utf-8")
            comparison_payload = json.loads(
                Path(result.comparison_path).read_text(encoding="utf-8")
            )
            stdout_payload = _summary(
                result,
                SimpleNamespace(
                    dataset_policy_id=NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
                    use_llm=True,
                    use_memory=False,
                ),
                str(base / "official"),
            )

        self.assertEqual(len(result.runs), 3)
        self.assertNotIn("Lead persistente", table)
        self.assertNotIn("Onset confirmado", table)
        self.assertNotIn("F1 aux", table)
        self.assertNotIn("FPR aux", table)
        self.assertIn("Controles internos", table)
        self.assertIn("Alerta persistente", table)
        self.assertIn("Intervalo al fin registrado", table)
        self.assertIn("Tasa alerta premonitorizacion", table)
        self.assertNotIn("FAR nominal", table)
        self.assertNotIn("degradation_mean_persistent_lead_time_to_failure", table)
        self.assertNotIn(
            "degradation_confirmed_degradation_before_failure_rate",
            table,
        )
        self.assertIn("omite deliberadamente precision, recall, F1 y FPR", table)
        self.assertEqual(comparison_payload["metrics"], [])
        forbidden = {
            "degradation_detected_before_failure_rate",
            "degradation_confirmed_degradation_before_failure_rate",
            "degradation_mean_lead_time_to_failure",
            "degradation_mean_persistent_lead_time_to_failure",
            "degradation_missed_runs",
            "degradation_missed_confirmed_degradation_runs",
        }
        self.assertTrue(
            forbidden.isdisjoint(
                metric["metric"]
                for metric in comparison_payload["degradation_metrics"]
            )
        )
        for row in comparison_payload["rows"]:
            self.assertTrue(forbidden.isdisjoint(row))
            self.assertNotIn("f1_score", row)
            self.assertNotIn("false_positive_rate", row)
        self.assertFalse(stdout_payload["binary_metrics_reported"])
        self.assertTrue(
            forbidden.isdisjoint(
                metric["metric"]
                for metric in stdout_payload["degradation_best_by_metric"]
            )
        )


def _spec(
    experiment_id: str,
    run_id: str,
    threshold: float,
    *,
    structuring_config: StructuringConfig | None = None,
) -> ExperimentSpec:
    return ExperimentSpec(
        experiment_id=experiment_id,
        run_id=run_id,
        description=f"threshold {threshold}",
        modeling_config=ModelingConfig(
            model_name="isolation_forest",
            random_state=42,
            hyperparameters={
                "n_estimators": 200,
                "max_samples": "auto",
                "contamination": "auto",
                "max_features": 1.0,
                "bootstrap": False,
                "n_jobs": 1,
                "threshold_quantile": threshold,
            },
        ),
        structuring_config=structuring_config,
    )


def _suite_args(*, use_memory: bool) -> SimpleNamespace:
    return SimpleNamespace(
        use_llm=True,
        model="qwen3.5:4b",
        think=True,
        timeout_seconds=180.0,
        use_memory=use_memory,
        memory_dir=Path("codigo/reports/reasoning_memory"),
        embedding_provider="ollama",
        embedding_model="qwen3-embedding:0.6b",
        embedding_timeout_seconds=60.0,
        hash_dimension=128,
        structurer_top_k=4,
        modeler_top_k=5,
        evaluator_top_k=6,
        memory_min_similarity=0.2,
        skip_decision_memory=False,
        require_human_review_before_reuse=True,
    )


def _structuring_config(window_size: int, overlap: float) -> StructuringConfig:
    return StructuringConfig(
        window_size=window_size,
        overlap=overlap,
        main_channel="DE_time",
        target_sample_rate_hz=12000,
        label_mode="binary_anomaly",
        features=["mean", "std", "rms"],
    )


def _modeling_config(
    model_name: str,
    updates: dict[str, object],
) -> ModelingConfig:
    if model_name == "isolation_forest":
        hyperparameters = {
            "n_estimators": 200,
            "max_samples": "auto",
            "contamination": "auto",
            "max_features": 1.0,
            "bootstrap": False,
            "n_jobs": 1,
            **updates,
        }
    elif model_name == "one_class_svm":
        hyperparameters = {
            "kernel": "rbf",
            "nu": 0.05,
            "gamma": "scale",
            "shrinking": True,
            "tol": 0.001,
            "max_iter": -1,
            **updates,
        }
    else:
        hyperparameters = {
            "svd_solver": "full",
            "whiten": False,
            **updates,
        }
    return ModelingConfig(
        model_name=model_name,
        random_state=42,
        hyperparameters=hyperparameters,
    )


def _fake_executors(
    experiment_dir: Path,
    seen_thresholds: dict[str, float],
    *,
    f1_score: float = 0.82,
    false_positive_rate: float = 0.06,
    seen_windows: dict[str, int] | None = None,
) -> PipelineExecutors:
    paths = {
        "manifest": experiment_dir / "interim" / "manifest.csv",
        "profile": experiment_dir / "interim" / "profile.json",
        "clean_dir": experiment_dir / "processed" / "clean_signals",
        "features": experiment_dir / "tensors" / "windows_features.csv",
        "tensors": experiment_dir / "tensors" / "windows_raw.npz",
        "splits": experiment_dir / "tensors" / "splits.json",
        "model": experiment_dir / "models" / "isolation_forest.joblib",
        "predictions": experiment_dir / "models" / "predictions.csv",
        "metrics": experiment_dir / "evaluation" / "metrics.json",
        "evaluation_report": experiment_dir / "evaluation" / "summary.md",
    }

    def manifest(raw_dir: str):
        paths["manifest"].parent.mkdir(parents=True, exist_ok=True)
        paths["manifest"].write_text("file_id,label\n97,normal\n105,fault\n", encoding="utf-8")
        return ManifestResult(
            executor_name="dataset_manifest",
            status="success",
            message=f"manifest ok for {raw_dir}",
            artifacts=[
                ArtifactRef(
                    name="manifest",
                    artifact_type="manifest",
                    path=str(paths["manifest"]),
                    producer="manifest_executor",
                )
            ],
            errors=[],
            state_updates={"manifest_path": str(paths["manifest"])},
            manifest_path=str(paths["manifest"]),
            n_rows=2,
            label_counts={"normal": 1, "fault": 1},
        )

    def profile(manifest_path: str):
        paths["profile"].parent.mkdir(parents=True, exist_ok=True)
        paths["profile"].write_text(
            json.dumps(
                {
                    "dataset": "cwru_bearing",
                    "manifest_path": manifest_path,
                    "generated_at": "2026-05-24T00:00:00+00:00",
                    "n_files": 2,
                    "label_counts": {"normal": 1, "fault": 1},
                    "sample_rate_counts": {"12000": 2},
                    "channels_detected": ["DE_time"],
                }
            ),
            encoding="utf-8",
        )
        return ProfileResult(
            executor_name="data_profiler",
            status="success",
            message="profile ok",
            artifacts=[
                ArtifactRef(
                    name="profile",
                    artifact_type="profile",
                    path=str(paths["profile"]),
                    producer="profiler_executor",
                )
            ],
            errors=[],
            state_updates={"profile_path": str(paths["profile"])},
            profile_path=str(paths["profile"]),
            n_files_profiled=2,
        )

    def cleaning(manifest_path: str, profile_path: str, config):
        paths["clean_dir"].mkdir(parents=True, exist_ok=True)
        return CleaningResult(
            executor_name="cleaning",
            status="success",
            message=f"cleaning ok from {manifest_path} and {profile_path}",
            artifacts=[
                ArtifactRef(
                    name="clean",
                    artifact_type="clean_signals",
                    path=str(paths["clean_dir"]),
                    producer="cleaning_executor",
                    metadata={"strategy_id": config.strategy_id},
                )
            ],
            errors=[],
            state_updates={"clean_path": str(paths["clean_dir"])},
            clean_path=str(paths["clean_dir"]),
            n_files_cleaned=2,
        )

    def structuring(clean_dir: str, config):
        if seen_windows is not None:
            seen_windows[experiment_dir.name] = config.window_size
        paths["features"].parent.mkdir(parents=True, exist_ok=True)
        paths["features"].write_text(
            "window_id,file_id,split,label,target,mean\n"
            "w0,97,train,normal,0,0.0\n"
            "w1,97,test,normal,0,0.1\n"
            "w2,105,test,fault,1,2.0\n",
            encoding="utf-8",
        )
        return StructuringResult(
            executor_name="structuring",
            status="success",
            message=f"structuring ok from {clean_dir}",
            artifacts=[
                ArtifactRef(
                    name="features",
                    artifact_type="features",
                    path=str(paths["features"]),
                    producer="structuring_executor",
                    metadata={"window_size": config.window_size},
                ),
                ArtifactRef(
                    name="tensors",
                    artifact_type="tensors",
                    path=str(paths["tensors"]),
                    producer="structuring_executor",
                ),
                ArtifactRef(
                    name="splits",
                    artifact_type="splits",
                    path=str(paths["splits"]),
                    producer="structuring_executor",
                ),
            ],
            errors=[],
            state_updates={
                "tensor_path": str(paths["tensors"]),
                "splits_path": str(paths["splits"]),
            },
            features_path=str(paths["features"]),
            tensors_path=str(paths["tensors"]),
            splits_path=str(paths["splits"]),
            n_windows=3,
        )

    def modeling(features_path: str, config):
        experiment_id = experiment_dir.name
        seen_thresholds[experiment_id] = float(config.hyperparameters["threshold_quantile"])
        return ModelingResult(
            executor_name="modeling",
            status="success",
            message=f"modeling ok from {features_path}",
            artifacts=[
                ArtifactRef(
                    name="model",
                    artifact_type="model",
                    path=str(paths["model"]),
                    producer="modeling_executor",
                    metadata={"model_name": config.model_name},
                ),
                ArtifactRef(
                    name="predictions",
                    artifact_type="predictions",
                    path=str(paths["predictions"]),
                    producer="modeling_executor",
                ),
            ],
            errors=[],
            state_updates={},
            model_path=str(paths["model"]),
            predictions_path=str(paths["predictions"]),
        )

    def evaluation(predictions_path: str):
        paths["metrics"].parent.mkdir(parents=True, exist_ok=True)
        paths["metrics"].write_text(
            json.dumps(
                {
                    "primary_split": "test",
                    "primary_metrics": {
                        "precision": 0.9,
                        "recall": 0.95,
                        "f1_score": f1_score,
                        "roc_auc": 0.97,
                        "pr_auc": 0.96,
                        "false_positive_rate": false_positive_rate,
                    },
                    "n_predictions": 3,
                }
            ),
            encoding="utf-8",
        )
        return EvaluationExecutorResult(
            executor_name="evaluation",
            status="success",
            message=f"evaluation ok from {predictions_path}",
            artifacts=[
                ArtifactRef(
                    name="metrics",
                    artifact_type="metrics",
                    path=str(paths["metrics"]),
                    producer="evaluator",
                ),
                ArtifactRef(
                    name="evaluation_report",
                    artifact_type="report",
                    path=str(paths["evaluation_report"]),
                    producer="evaluator",
                ),
            ],
            errors=[],
            state_updates={"metrics_path": str(paths["metrics"])},
            metrics_path=str(paths["metrics"]),
            report_fragment_path=str(paths["evaluation_report"]),
        )

    def reporting(state, decision):
        report_path = Path(decision.output_path)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text("# Report\n", encoding="utf-8")
        return ReportExecutorResult(
            executor_name="report_writer",
            status="success",
            message="reporting ok",
            artifacts=[
                ArtifactRef(
                    name="final_report",
                    artifact_type="report",
                    path=str(report_path),
                    producer="report_writer",
                )
            ],
            errors=[],
            state_updates={"report_path": str(report_path)},
            report_path=str(report_path),
        )

    return PipelineExecutors(
        manifest=manifest,
        profile=profile,
        cleaning=cleaning,
        structuring=structuring,
        modeling=modeling,
        evaluation=evaluation,
        reporting=reporting,
    )


def _fake_run_to_failure_run(
    spec: ExperimentSpec,
    experiment_dir: Path,
):
    snapshot_dir = experiment_dir / "snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot = RunSnapshot(
        run_id=spec.run_id,
        thread_id=f"{spec.run_id}-thread",
        dataset="nasa_ims_bearing",
        current_stage="completed",
        approved=True,
        report_path=str(snapshot_dir / "final_report.md"),
        snapshot_dir=str(snapshot_dir),
        state_path=str(snapshot_dir / "state.json"),
        decisions_path=str(snapshot_dir / "decisions.json"),
        artifacts_path=str(snapshot_dir / "artifacts.json"),
        metrics_path=str(snapshot_dir / "metrics.json"),
        evaluation_path=str(snapshot_dir / "evaluation.json"),
        summary_path=str(snapshot_dir / "summary.json"),
        metadata_path=str(snapshot_dir / "metadata.json"),
        created_at=datetime.now(UTC),
    )
    return SimpleNamespace(snapshot=snapshot)


def _fake_run_to_failure_comparison(
    run_ids: list[str],
    _runs_dir,
) -> RunComparison:
    rows = []
    for index, run_id in enumerate(run_ids):
        rows.append(
            RunComparisonRow(
                run_id=run_id,
                dataset="nasa_ims_bearing",
                current_stage="completed",
                approved=index != 1,
                supervision_profile="run_to_failure_degradation",
                label_source="temporal_proxy",
                label_granularity="proxy_temporal",
                model_name=[
                    "pca_reconstruction_error",
                    "isolation_forest",
                    "one_class_svm",
                    "autoencoder_dense",
                ][index],
                metric_families=[
                    "binary_classification",
                    "run_to_failure_degradation",
                ],
                f1_score=0.6 + index * 0.05,
                false_positive_rate=0.2 + index * 0.1,
                degradation_available=True,
                degradation_n_runs=1,
                degradation_persistent_alert_run_rate=1.0,
                degradation_mean_first_persistent_alert_time_to_trajectory_end=(
                    900.0 - index * 100.0
                ),
                degradation_mean_pre_monitoring_alert_rate=0.1 + index * 0.05,
                degradation_detected_before_failure_rate=1.0,
                degradation_confirmed_degradation_before_failure_rate=(
                    1.0 if index != 1 else 0.0
                ),
                degradation_mean_lead_time_to_failure=1200.0 - index * 100.0,
                degradation_mean_persistent_lead_time_to_failure=(
                    900.0 - index * 100.0 if index != 1 else None
                ),
                degradation_mean_false_alarm_rate_nominal=0.1 + index * 0.05,
                degradation_mean_score_trend_spearman=0.7 - index * 0.1,
                degradation_mean_health_index_drop=65.0 - index * 10.0,
                degradation_mean_health_monotonicity=0.9 - index * 0.1,
                degradation_missed_runs=0,
                degradation_missed_confirmed_degradation_runs=0 if index != 1 else 1,
                degradation_mean_initial_final_separation=0.5 + index * 0.1,
                snapshot_path=f"/tmp/{run_id}",
            )
        )
    return RunComparison(
        generated_at=datetime.now(UTC),
        run_ids=run_ids,
        rows=rows,
        metrics=[
            MetricComparison(
                metric="f1_score",
                higher_is_better=True,
                best_run_id=run_ids[-1],
                best_value=0.7,
            )
        ],
        degradation_metrics=[
            MetricComparison(
                metric="degradation_persistent_alert_run_rate",
                metric_family="run_to_failure_degradation",
                higher_is_better=True,
                best_run_id=run_ids[0],
                best_value=1.0,
            ),
            MetricComparison(
                metric=(
                    "degradation_mean_first_persistent_alert_time_to_trajectory_end"
                ),
                metric_family="run_to_failure_degradation",
                higher_is_better=True,
                best_run_id=run_ids[0],
                best_value=900.0,
            ),
            MetricComparison(
                metric="degradation_mean_pre_monitoring_alert_rate",
                metric_family="run_to_failure_degradation",
                higher_is_better=False,
                best_run_id=run_ids[0],
                best_value=0.1,
            ),
            MetricComparison(
                metric="degradation_confirmed_degradation_before_failure_rate",
                metric_family="run_to_failure_degradation",
                higher_is_better=True,
                best_run_id=run_ids[0],
                best_value=1.0,
            ),
            MetricComparison(
                metric="degradation_mean_persistent_lead_time_to_failure",
                metric_family="run_to_failure_degradation",
                higher_is_better=True,
                best_run_id=run_ids[0],
                best_value=900.0,
            ),
            MetricComparison(
                metric="degradation_mean_false_alarm_rate_nominal",
                metric_family="run_to_failure_degradation",
                higher_is_better=False,
                best_run_id=run_ids[0],
                best_value=0.1,
            ),
            MetricComparison(
                metric="degradation_mean_health_index_drop",
                metric_family="run_to_failure_degradation",
                higher_is_better=True,
                best_run_id=run_ids[0],
                best_value=65.0,
            )
        ],
    )


if __name__ == "__main__":
    unittest.main()
