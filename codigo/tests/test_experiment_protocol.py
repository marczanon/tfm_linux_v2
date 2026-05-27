import json
import tempfile
import unittest
from pathlib import Path

from codigo.app.graph.pipeline import PipelineExecutors
from codigo.app.schemas.agent_decisions import (
    ModelingAlternative,
    ModelingDecision,
    StructuringAlternative,
    StructuringDecision,
)
from codigo.app.services.experiment_protocol import (
    ExperimentPlan,
    ExperimentSpec,
    cwru_model_experiment_plan_from_decision,
    cwru_window_experiment_plan_from_decision,
    default_cwru_experiment_plan,
    run_cwru_experiment_plan,
)
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


class ExperimentProtocolTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
