"""Protocolo experimental local para ejecuciones CWRU comparables."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from pydantic import Field

from codigo.app.schemas.agent_decisions import (
    ModelingDecision,
    ModelingDecisionStrategy,
    ReportDecision,
    ReportSection,
    StructuringDecision,
)
from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.state import ModelingConfig, StructuringConfig, TFMStateModel
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR, RunSnapshot
from codigo.app.services.run_registry import RunComparison, compare_runs

if TYPE_CHECKING:
    from codigo.app.graph.pipeline import PipelineAgents, PipelineExecutors


DEFAULT_EXPERIMENTS_DIR = Path("codigo/experiments/cwru_local")
DEFAULT_PLAN_ID = "cwru_iforest_threshold_v1"
DEFAULT_WINDOW_PLAN_ID = "cwru_agentic_window_sensitivity_v1"
DEFAULT_MODEL_PLAN_ID = "cwru_agentic_model_comparison_v1"
DEFAULT_RUN_TO_FAILURE_EXPERIMENTS_DIR = Path("codigo/experiments/run_to_failure")
DEFAULT_RUN_TO_FAILURE_PLAN_ID = "run_to_failure_agentic_model_suite_v1"
DEFAULT_RUN_TO_FAILURE_POLICY_ID = "nasa_ims_temporal_v1"


class ExperimentSpec(StrictBaseModel):
    """Configuracion de una ejecucion dentro de un plan experimental."""

    experiment_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    description: str = Field(min_length=1)
    modeling_config: ModelingConfig
    structuring_config: StructuringConfig | None = None
    expected_effect: str | None = None


class ExperimentPlan(StrictBaseModel):
    """Manifiesto ligero de un conjunto de experimentos comparables."""

    plan_id: str = Field(min_length=1)
    dataset: Literal["cwru_bearing", "nasa_ims_bearing"] = "cwru_bearing"
    adapter_id: str | None = Field(default=None, min_length=1)
    dataset_policy_id: str | None = Field(default=None, min_length=1)
    supervision_profile: str | None = Field(default=None, min_length=1)
    description: str = Field(min_length=1)
    experiments: list[ExperimentSpec] = Field(min_length=2)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExperimentRunSummary(StrictBaseModel):
    """Resumen de una ejecucion concreta dentro de un plan."""

    experiment_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    snapshot: RunSnapshot


class ExperimentPlanResult(StrictBaseModel):
    """Resultado persistido de ejecutar un plan experimental."""

    plan_id: str = Field(min_length=1)
    plan_path: str = Field(min_length=1)
    comparison_path: str = Field(min_length=1)
    results_table_path: str = Field(min_length=1)
    generated_at: datetime
    runs: list[ExperimentRunSummary] = Field(min_length=2)
    comparison: RunComparison


ExperimentExecutorFactory = Callable[[ExperimentSpec, Path], "PipelineExecutors"]
RunToFailureExperimentRunner = Callable[[ExperimentSpec, Path], "PersistedPipelineRun"]
RunComparisonFactory = Callable[[list[str], Path | str], RunComparison]


def default_cwru_experiment_plan(
    plan_id: str = DEFAULT_PLAN_ID,
) -> ExperimentPlan:
    """Devuelve el primer plan local: baseline y umbral mas conservador."""

    baseline_config = _modeling_config_with_hyperparameters({})
    conservative_config = _modeling_config_with_hyperparameters(
        {"threshold_quantile": 1.0}
    )
    return ExperimentPlan(
        plan_id=plan_id,
        description=(
            "Comparacion local de Isolation Forest sobre CWRU variando solo "
            "el cuantil usado para fijar el umbral de anomalia."
        ),
        experiments=[
            ExperimentSpec(
                experiment_id="baseline_threshold_099",
                run_id=f"{plan_id}_baseline_threshold_099",
                description=(
                    "Baseline del MVP con threshold_quantile=0.99 y 200 "
                    "arboles."
                ),
                modeling_config=baseline_config,
                expected_effect="Referencia reproducible del MVP local.",
            ),
            ExperimentSpec(
                experiment_id="conservative_threshold_100",
                run_id=f"{plan_id}_conservative_threshold_100",
                description=(
                    "Umbral mas conservador usando threshold_quantile=1.0 "
                    "manteniendo el resto de hiperparametros."
                ),
                modeling_config=conservative_config,
                expected_effect=(
                    "Reducir falsos positivos a costa de posible menor recall."
                ),
            ),
        ],
    )


def default_run_to_failure_model_suite_plan(
    plan_id: str = DEFAULT_RUN_TO_FAILURE_PLAN_ID,
) -> ExperimentPlan:
    """Devuelve la suite canonica inicial para `run_to_failure_degradation`."""

    from codigo.app.executors.modeling import (
        DEFAULT_AUTOENCODER_DENSE_CONFIG,
        DEFAULT_MODELING_CONFIG,
        DEFAULT_OCSVM_MODELING_CONFIG,
        DEFAULT_PCA_MODELING_CONFIG,
    )

    experiments = [
        ExperimentSpec(
            experiment_id="pca_reconstruction_error",
            run_id=f"{plan_id}_pca_reconstruction_error",
            description=(
                "Baseline interpretable de error de reconstruccion PCA para "
                "Health Indicator temporal."
            ),
            modeling_config=_copy_modeling_config(DEFAULT_PCA_MODELING_CONFIG),
            expected_effect=(
                "Producir un score estable y explicable para comparar "
                "alerta temprana, tendencia y falsas alarmas."
            ),
        ),
        ExperimentSpec(
            experiment_id="isolation_forest",
            run_id=f"{plan_id}_isolation_forest",
            description=(
                "Detector no supervisado por aislamiento como familia "
                "alternativa al score de reconstruccion."
            ),
            modeling_config=_copy_modeling_config(DEFAULT_MODELING_CONFIG),
            expected_effect=(
                "Contrastar sensibilidad temprana frente a coste de falsas "
                "alarmas nominales."
            ),
        ),
        ExperimentSpec(
            experiment_id="one_class_svm",
            run_id=f"{plan_id}_one_class_svm",
            description=(
                "Frontera no lineal One-Class SVM para comparar estabilidad "
                "temporal y persistencia de alertas."
            ),
            modeling_config=_copy_modeling_config(DEFAULT_OCSVM_MODELING_CONFIG),
            expected_effect=(
                "Evaluar si una frontera no lineal mejora tendencia o reduce "
                "picos aislados."
            ),
        ),
        ExperimentSpec(
            experiment_id="autoencoder_dense",
            run_id=f"{plan_id}_autoencoder_dense",
            description=(
                "Autoencoder denso PyTorch para comparar reconstruccion no "
                "lineal aprendida frente a PCA y detectores clasicos."
            ),
            modeling_config=_copy_modeling_config(DEFAULT_AUTOENCODER_DENSE_CONFIG),
            expected_effect=(
                "Evaluar si el error de reconstruccion no lineal mejora "
                "sensibilidad temporal sin aumentar falsas alarmas nominales."
            ),
        ),
    ]
    return ExperimentPlan(
        plan_id=plan_id,
        dataset="nasa_ims_bearing",
        adapter_id="nasa_ims_bearing",
        dataset_policy_id=DEFAULT_RUN_TO_FAILURE_POLICY_ID,
        supervision_profile="run_to_failure_degradation",
        description=(
            "Suite canonica agentica run-to-failure sobre el runner comun. "
            "Compara familias soportadas por metricas temporales, manteniendo "
            "F1 como metrica auxiliar/proxy."
        ),
        experiments=experiments,
    )


def cwru_window_experiment_plan_from_decision(
    decision: StructuringDecision,
    *,
    plan_id: str = DEFAULT_WINDOW_PLAN_ID,
) -> ExperimentPlan:
    """Crea un plan de ventanas a partir de alternativas propuestas por el agente."""

    candidates = [
        (
            "selected",
            decision.structuring_config,
            decision.rationale,
            "Configuracion principal elegida por el agente estructurador.",
        )
    ]
    candidates.extend(
        (
            candidate.alternative_id,
            candidate.structuring_config,
            candidate.rationale,
            candidate.expected_effect,
        )
        for candidate in decision.comparison_candidates
    )

    unique: list[tuple[str, StructuringConfig, str, str | None]] = []
    seen: set[tuple[int, float, tuple[str, ...]]] = set()
    for label, config, rationale, expected_effect in candidates:
        key = (config.window_size, config.overlap, tuple(config.features))
        if key in seen:
            continue
        seen.add(key)
        unique.append((label, config, rationale, expected_effect))

    if len(unique) < 2:
        raise ValueError(
            "agent decision must include at least two unique structuring configurations"
        )

    default_modeling = _modeling_config_with_hyperparameters({})
    experiments = [
        ExperimentSpec(
            experiment_id=_window_experiment_id(label, config),
            run_id=f"{plan_id}_{_window_experiment_id(label, config)}",
            description=rationale,
            modeling_config=default_modeling,
            structuring_config=config,
            expected_effect=expected_effect,
        )
        for label, config, rationale, expected_effect in unique
    ]
    return ExperimentPlan(
        plan_id=plan_id,
        description=(
            "Comparacion agentica de configuraciones de ventana sobre CWRU. "
            "Las alternativas proceden de la decision del agente estructurador; "
            "el protocolo solo materializa y compara ejecuciones reproducibles."
        ),
        experiments=experiments,
    )


def cwru_model_experiment_plan_from_decision(
    decision: ModelingDecision,
    *,
    plan_id: str = DEFAULT_MODEL_PLAN_ID,
    structuring_config: StructuringConfig | None = None,
) -> ExperimentPlan:
    """Crea un plan de modelos a partir de alternativas propuestas por el agente."""

    experiments = _model_experiment_specs_from_decision(
        decision,
        plan_id=plan_id,
        structuring_config=structuring_config,
    )
    return ExperimentPlan(
        plan_id=plan_id,
        description=(
            "Comparacion agentica de modelos sobre CWRU. Las alternativas "
            "proceden de la decision del agente modelador; el protocolo solo "
            "materializa y compara configuraciones soportadas."
        ),
        experiments=experiments,
    )


def run_to_failure_model_experiment_plan_from_decision(
    decision: ModelingDecision,
    *,
    plan_id: str = DEFAULT_RUN_TO_FAILURE_PLAN_ID,
    dataset: Literal["nasa_ims_bearing"] = "nasa_ims_bearing",
    adapter_id: str = "nasa_ims_bearing",
    dataset_policy_id: str = DEFAULT_RUN_TO_FAILURE_POLICY_ID,
    structuring_config: StructuringConfig | None = None,
) -> ExperimentPlan:
    """Crea una suite run-to-failure desde la decision del modeler."""

    experiments = _model_experiment_specs_from_decision(
        decision,
        plan_id=plan_id,
        structuring_config=structuring_config,
    )
    return ExperimentPlan(
        plan_id=plan_id,
        dataset=dataset,
        adapter_id=adapter_id,
        dataset_policy_id=dataset_policy_id,
        supervision_profile="run_to_failure_degradation",
        description=(
            "Suite agentica run-to-failure derivada de la decision del modeler. "
            "El protocolo materializa la configuracion elegida y sus "
            "alternativas soportadas para comparar lead time, falsas alarmas, "
            "tendencia y persistencia."
        ),
        experiments=experiments,
    )


def run_cwru_experiment_plan(
    plan: ExperimentPlan | None = None,
    *,
    experiments_dir: Path | str = DEFAULT_EXPERIMENTS_DIR,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
    raw_path: str = "codigo/data/raw/cwru_bearing/mat",
    executor_factory: ExperimentExecutorFactory | None = None,
) -> ExperimentPlanResult:
    """Ejecuta un plan CWRU completo y guarda comparacion y tabla Markdown."""

    from codigo.app.graph.state import create_initial_cwru_state
    from codigo.app.graph.pipeline import run_and_persist_cwru_pipeline

    experiment_plan = plan or default_cwru_experiment_plan()
    _validate_plain_names(experiment_plan)
    plan_dir = Path(experiments_dir) / experiment_plan.plan_id
    plan_dir.mkdir(parents=True, exist_ok=True)

    plan_path = plan_dir / "experiment_plan.json"
    comparison_path = plan_dir / "comparison.json"
    table_path = plan_dir / "results_table.md"
    _write_json(plan_path, experiment_plan.model_dump(mode="json"))

    run_summaries: list[ExperimentRunSummary] = []
    for spec in experiment_plan.experiments:
        experiment_dir = plan_dir / spec.experiment_id
        experiment_dir.mkdir(parents=True, exist_ok=True)
        state = create_initial_cwru_state(
            thread_id=f"{experiment_plan.plan_id}:{spec.experiment_id}",
            run_id=spec.run_id,
            raw_path=raw_path,
        )
        executors = (
            executor_factory(spec, experiment_dir)
            if executor_factory is not None
            else _experiment_executors(experiment_dir)
        )
        agents = _experiment_agents(spec, experiment_dir)
        persisted = run_and_persist_cwru_pipeline(
            state,
            executors=executors,
            agents=agents,
            runs_dir=runs_dir,
        )
        run_summaries.append(
            ExperimentRunSummary(
                experiment_id=spec.experiment_id,
                run_id=spec.run_id,
                snapshot=persisted.snapshot,
            )
        )

    comparison = compare_runs(
        [spec.run_id for spec in experiment_plan.experiments],
        runs_dir=runs_dir,
    )
    _write_json(comparison_path, comparison.model_dump(mode="json"))
    table_path.write_text(
        _results_table_markdown(experiment_plan, comparison),
        encoding="utf-8",
    )

    return ExperimentPlanResult(
        plan_id=experiment_plan.plan_id,
        plan_path=str(plan_path),
        comparison_path=str(comparison_path),
        results_table_path=str(table_path),
        generated_at=datetime.now(UTC),
        runs=run_summaries,
        comparison=comparison,
    )


def run_run_to_failure_experiment_plan(
    plan: ExperimentPlan | None = None,
    *,
    raw_path: str,
    experiments_dir: Path | str = DEFAULT_RUN_TO_FAILURE_EXPERIMENTS_DIR,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
    memory_config: "PipelineMemoryConfig | None" = None,
    agents: "PipelineAgents | None" = None,
    use_llm: bool = False,
    run_factory: RunToFailureExperimentRunner | None = None,
    comparison_factory: RunComparisonFactory | None = None,
) -> ExperimentPlanResult:
    """Ejecuta una suite run-to-failure usando el runner comun multi-dataset."""

    experiment_plan = plan or default_run_to_failure_model_suite_plan()
    if experiment_plan.dataset != "nasa_ims_bearing":
        raise ValueError("run-to-failure experiment plan must use nasa_ims_bearing")
    _validate_plain_names(experiment_plan)
    plan_dir = Path(experiments_dir) / experiment_plan.plan_id
    plan_dir.mkdir(parents=True, exist_ok=True)

    plan_path = plan_dir / "experiment_plan.json"
    comparison_path = plan_dir / "comparison.json"
    table_path = plan_dir / "results_table.md"
    _write_json(plan_path, experiment_plan.model_dump(mode="json"))

    run_summaries: list[ExperimentRunSummary] = []
    for spec in experiment_plan.experiments:
        experiment_dir = plan_dir / spec.experiment_id
        experiment_dir.mkdir(parents=True, exist_ok=True)
        persisted = (
            run_factory(spec, experiment_dir)
            if run_factory is not None
            else _run_run_to_failure_experiment_spec(
                spec,
                experiment_plan,
                raw_path=raw_path,
                runs_dir=runs_dir,
                memory_config=memory_config,
                agents=agents,
                use_llm=use_llm,
            )
        )
        run_summaries.append(
            ExperimentRunSummary(
                experiment_id=spec.experiment_id,
                run_id=spec.run_id,
                snapshot=persisted.snapshot,
            )
        )

    compare = comparison_factory or compare_runs
    comparison = compare(
        [spec.run_id for spec in experiment_plan.experiments],
        runs_dir,
    )
    _write_json(comparison_path, comparison.model_dump(mode="json"))
    table_path.write_text(
        _results_table_markdown(experiment_plan, comparison),
        encoding="utf-8",
    )

    return ExperimentPlanResult(
        plan_id=experiment_plan.plan_id,
        plan_path=str(plan_path),
        comparison_path=str(comparison_path),
        results_table_path=str(table_path),
        generated_at=datetime.now(UTC),
        runs=run_summaries,
        comparison=comparison,
    )


def _experiment_executors(experiment_dir: Path) -> "PipelineExecutors":
    from codigo.app.executors.evaluation import generate_evaluation_report
    from codigo.app.executors.modeling import generate_model_outputs
    from codigo.app.executors.reporting import generate_technical_report
    from codigo.app.executors.structuring import generate_temporal_structure
    from codigo.app.graph.pipeline import PipelineExecutors

    tensor_dir = experiment_dir / "tensors"
    model_dir = experiment_dir / "models"
    evaluation_dir = experiment_dir / "evaluation"

    def structuring(clean_dir: str, config: StructuringConfig):
        return generate_temporal_structure(
            clean_dir=clean_dir,
            output_dir=tensor_dir,
            config=config,
        )

    def modeling(features_path: str, config: ModelingConfig):
        return generate_model_outputs(
            features_path=features_path,
            output_dir=model_dir,
            config=config,
        )

    def evaluation(predictions_path: str):
        return generate_evaluation_report(
            predictions_path=predictions_path,
            output_dir=evaluation_dir,
        )

    return PipelineExecutors(
        structuring=structuring,
        modeling=modeling,
        evaluation=evaluation,
        reporting=generate_technical_report,
    )


def _experiment_agents(
    spec: ExperimentSpec,
    experiment_dir: Path,
) -> "PipelineAgents":
    from codigo.app.agents.cleaner import decide_cleaning_action_deterministic
    from codigo.app.agents.evaluator import decide_evaluation_action_deterministic
    from codigo.app.agents.structurer import decide_structuring_action_deterministic
    from codigo.app.agents.supervisor import decide_supervisor_action_deterministic
    from codigo.app.graph.pipeline import PipelineAgents

    model_path = experiment_dir / "models" / _model_filename(spec.modeling_config.model_name)
    tensor_dir = experiment_dir / "tensors"
    report_path = experiment_dir / "final_report.md"

    def structurer(state: TFMStateModel) -> StructuringDecision:
        if spec.structuring_config is None:
            return decide_structuring_action_deterministic(state)
        return StructuringDecision(
            decision_id=(
                f"{state.run_id}:structurer:"
                f"{_agent_turn(state, 'structurer'):03d}"
            ),
            rationale=(
                "Agentic experiment protocol is materializing a "
                "StructuringConfig proposed by the structurer decision."
            ),
            confidence=1.0,
            structuring_config=spec.structuring_config,
            expected_features_path=str(tensor_dir / "windows_features.csv"),
            expected_tensors_path=str(tensor_dir / "windows_raw.npz"),
            expected_splits_path=str(tensor_dir / "splits.json"),
        )

    def modeler(state: TFMStateModel) -> ModelingDecision:
        return ModelingDecision(
            decision_id=f"{state.run_id}:modeler:{_agent_turn(state, 'modeler'):03d}",
            rationale=(
                "Experiment protocol selected this ModelingConfig from a "
                "predefined local plan; the executor remains deterministic."
            ),
            confidence=1.0,
            modeling_config=spec.modeling_config,
            train_split="train",
            validation_split="validation",
            expected_model_path=str(model_path),
        )

    def report_writer(state: TFMStateModel) -> ReportDecision:
        metrics_path = None if state.metrics is None else state.metrics.metrics_path
        return ReportDecision(
            decision_id=(
                f"{state.run_id}:report_writer:"
                f"{_agent_turn(state, 'report_writer'):03d}"
            ),
            rationale=(
                "Experiment protocol writes each final report inside the "
                "experiment directory to avoid overwriting comparable runs."
            ),
            confidence=1.0,
            output_path=str(report_path),
            output_format="markdown",
            sections=[
                ReportSection(title="Resumen ejecutivo"),
                ReportSection(
                    title="Contexto y datos",
                    source_paths=[
                        path for path in [state.manifest_path, state.profile_path] if path
                    ],
                ),
                ReportSection(title="Configuraciones del pipeline"),
                ReportSection(
                    title="Metricas y evaluacion",
                    include_metrics=True,
                    source_paths=[path for path in [metrics_path] if path],
                ),
                ReportSection(
                    title="Artefactos generados",
                    include_artifacts=True,
                    source_paths=[artifact.path for artifact in state.artifacts],
                ),
                ReportSection(title="Limitaciones y siguientes pasos"),
            ],
        )

    return PipelineAgents(
        supervisor=decide_supervisor_action_deterministic,
        cleaner=decide_cleaning_action_deterministic,
        structurer=structurer,
        modeler=modeler,
        evaluator=decide_evaluation_action_deterministic,
        report_writer=report_writer,
    )


def _run_run_to_failure_experiment_spec(
    spec: ExperimentSpec,
    plan: ExperimentPlan,
    *,
    raw_path: str,
    runs_dir: Path | str,
    memory_config: "PipelineMemoryConfig | None",
    agents: "PipelineAgents | None",
    use_llm: bool,
) -> PersistedPipelineRun:
    from codigo.app.schemas.pipeline_run import PipelineRunRequest
    from codigo.app.services.pipeline_runner import run_dataset_pipeline

    request = PipelineRunRequest(
        run_id=spec.run_id,
        dataset_id=plan.dataset,
        raw_path=raw_path,
        adapter_id=plan.adapter_id or plan.dataset,
        dataset_policy_id=plan.dataset_policy_id,
        use_memory=memory_config is not None,
        use_llm=use_llm,
    )
    return run_dataset_pipeline(
        request,
        agents=_run_to_failure_experiment_agents(spec, base_agents=agents),
        runs_dir=runs_dir,
        memory_config=memory_config,
    )


def _run_to_failure_experiment_agents(
    spec: ExperimentSpec,
    *,
    base_agents: "PipelineAgents | None" = None,
) -> "PipelineAgents":
    from codigo.app.graph.pipeline import PipelineAgents

    base = base_agents or PipelineAgents()

    def structurer(state: TFMStateModel) -> StructuringDecision:
        if spec.structuring_config is None:
            return base.structurer(state)
        return StructuringDecision(
            decision_id=(
                f"{state.run_id}:structurer:"
                f"{_agent_turn(state, 'structurer'):03d}"
            ),
            rationale=(
                "Run-to-failure experiment protocol materializes a "
                "StructuringConfig selected for a comparable suite."
            ),
            confidence=1.0,
            structuring_config=spec.structuring_config,
            expected_features_path=(
                f"codigo/data/tensors/{state.project_context.dataset}/"
                f"{state.run_id}/windows_features.csv"
            ),
            expected_tensors_path=(
                f"codigo/data/tensors/{state.project_context.dataset}/"
                f"{state.run_id}/windows_raw.npz"
            ),
            expected_splits_path=(
                f"codigo/data/tensors/{state.project_context.dataset}/"
                f"{state.run_id}/splits.json"
            ),
        )

    def modeler(state: TFMStateModel) -> ModelingDecision:
        return ModelingDecision(
            decision_id=f"{state.run_id}:modeler:{_agent_turn(state, 'modeler'):03d}",
            rationale=(
                "Run-to-failure experiment protocol materializes a model family "
                "from the canonical suite. The agentic decision is preserved as "
                "a structured ModelingDecision and the deterministic executor "
                "trains the selected configuration."
            ),
            confidence=1.0,
            decision_strategy=_run_to_failure_experiment_strategy(spec),
            modeling_config=spec.modeling_config,
            train_split="train",
            validation_split="validation",
            expected_model_path=(
                f"codigo/models/{state.project_context.dataset}/{state.run_id}/"
                f"{_model_filename(spec.modeling_config.model_name)}"
            ),
        )

    return PipelineAgents(
        supervisor=base.supervisor,
        cleaner=base.cleaner,
        structurer=structurer if spec.structuring_config is not None else base.structurer,
        modeler=modeler,
        evaluator=base.evaluator,
        report_writer=base.report_writer,
        report_reviser=base.report_reviser,
        report_verifier=base.report_verifier,
    )


def _run_to_failure_experiment_strategy(
    spec: ExperimentSpec,
) -> ModelingDecisionStrategy:
    return ModelingDecisionStrategy(
        strategy_type="feature_model_fit",
        hypothesis=(
            f"Comparar {spec.modeling_config.model_name} como score temporal "
            "run-to-failure frente a las demas familias de la suite canonica."
        ),
        evidence_refs=[
            "tool:temporal_health_lookup",
            "tool:degradation_metrics_lookup",
            "temporal:run_to_failure_profile",
            "temporal:first_persistent_alert",
            "temporal:longest_alert_streak",
            "metric:mean_lead_time_to_failure",
            "metric:mean_false_alarm_rate_nominal",
            "metric:mean_score_trend_spearman",
            "label_source:temporal_proxy",
        ],
        risk_notes=[
            "La suite materializa modelos comparables; no convierte etiquetas proxy en oficiales.",
            "La aprobacion depende de metricas temporales y guardarrails del evaluador.",
        ],
        tool_names=[
            "temporal_health_lookup",
            "degradation_metrics_lookup",
        ],
        optimization_targets=[
            "detected_before_failure_rate",
            "mean_lead_time_to_failure",
            "mean_false_alarm_rate_nominal",
            "mean_score_trend_spearman",
        ],
        alert_policy=(
            "Comparar pico aislado, aviso sostenido, falsas alarmas nominales "
            "y tendencia antes de aprobar cualquier familia de modelo."
        ),
    )


def _model_experiment_specs_from_decision(
    decision: ModelingDecision,
    *,
    plan_id: str,
    structuring_config: StructuringConfig | None,
) -> list[ExperimentSpec]:
    candidates = [
        (
            "selected",
            decision.modeling_config,
            decision.rationale,
            "Configuracion principal elegida por el agente modelador.",
        )
    ]
    candidates.extend(
        (
            candidate.alternative_id,
            candidate.modeling_config,
            candidate.rationale,
            candidate.expected_effect,
        )
        for candidate in decision.comparison_candidates
    )

    unique: list[tuple[str, ModelingConfig, str, str | None]] = []
    seen: set[tuple[str, str]] = set()
    for label, config, rationale, expected_effect in candidates:
        key = (
            config.model_name,
            json.dumps(config.hyperparameters, sort_keys=True),
        )
        if key in seen:
            continue
        seen.add(key)
        unique.append((label, config, rationale, expected_effect))

    if len(unique) < 2:
        raise ValueError(
            "agent decision must include at least two unique modeling configurations"
        )

    return [
        ExperimentSpec(
            experiment_id=_model_experiment_id(label, config),
            run_id=f"{plan_id}_{_model_experiment_id(label, config)}",
            description=rationale,
            modeling_config=config,
            structuring_config=structuring_config,
            expected_effect=expected_effect,
        )
        for label, config, rationale, expected_effect in unique
    ]


def _modeling_config_with_hyperparameters(
    updates: dict[str, int | float | str | bool | None],
) -> ModelingConfig:
    from codigo.app.executors.modeling import DEFAULT_MODELING_CONFIG

    payload = DEFAULT_MODELING_CONFIG.model_dump(mode="json")
    hyperparameters = dict(payload["hyperparameters"])
    hyperparameters.update(updates)
    return ModelingConfig(
        model_name=payload["model_name"],
        random_state=payload["random_state"],
        hyperparameters=hyperparameters,
    )


def _copy_modeling_config(config: ModelingConfig) -> ModelingConfig:
    return ModelingConfig.model_validate(config.model_dump(mode="json"))


def _results_table_markdown(
    plan: ExperimentPlan,
    comparison: RunComparison,
) -> str:
    if plan.dataset == "nasa_ims_bearing" or comparison.degradation_metrics:
        return _run_to_failure_results_table_markdown(plan, comparison)

    specs_by_run_id = {spec.run_id: spec for spec in plan.experiments}
    lines = [
        f"# Resultados experimentales: {plan.plan_id}",
        "",
        plan.description,
        "",
        "| Experimento | Run ID | window_size | overlap | model_name | threshold_quantile | n_estimators | Aprobado | Precision | Recall | F1 | FPR |",
        "| --- | --- | ---: | ---: | --- | ---: | ---: | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in comparison.rows:
        spec = specs_by_run_id[row.run_id]
        hyperparameters = spec.modeling_config.hyperparameters
        structuring = spec.structuring_config
        lines.append(
            " | ".join(
                [
                    f"| {spec.experiment_id}",
                    f"`{row.run_id}`",
                    _metric_text(None if structuring is None else structuring.window_size),
                    _metric_text(None if structuring is None else structuring.overlap),
                    spec.modeling_config.model_name,
                    _metric_text(hyperparameters.get("threshold_quantile")),
                    _metric_text(hyperparameters.get("n_estimators")),
                    _approval_text(row.approved),
                    _metric_text(row.precision),
                    _metric_text(row.recall),
                    _metric_text(row.f1_score),
                    f"{_metric_text(row.false_positive_rate)} |",
                ]
            )
        )
    lines.extend(["", "## Mejor ejecucion por metrica", ""])
    for metric in comparison.metrics:
        direction = "mayor es mejor" if metric.higher_is_better else "menor es mejor"
        lines.append(
            "- "
            f"{metric.metric}: `{metric.best_run_id}` "
            f"({_metric_text(metric.best_value)}, {direction})"
        )
    return "\n".join(lines).rstrip() + "\n"


def _run_to_failure_results_table_markdown(
    plan: ExperimentPlan,
    comparison: RunComparison,
) -> str:
    specs_by_run_id = {spec.run_id: spec for spec in plan.experiments}
    lines = [
        f"# Resultados experimentales: {plan.plan_id}",
        "",
        plan.description,
        "",
        "| Experimento | Run ID | modelo | threshold_quantile | Aprobado | Onset confirmado | Lead persistente | FAR nominal | Tendencia | HI drop | HI mono | Onsets perdidos | F1 aux | FPR aux |",
        "| --- | --- | --- | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in comparison.rows:
        spec = specs_by_run_id[row.run_id]
        hyperparameters = spec.modeling_config.hyperparameters
        lines.append(
            " | ".join(
                [
                    f"| {spec.experiment_id}",
                    f"`{row.run_id}`",
                    spec.modeling_config.model_name,
                    _metric_text(hyperparameters.get("threshold_quantile")),
                    _approval_text(row.approved),
                    _metric_text(
                        row.degradation_confirmed_degradation_before_failure_rate
                    ),
                    _metric_text(
                        row.degradation_mean_persistent_lead_time_to_failure
                    ),
                    _metric_text(row.degradation_mean_false_alarm_rate_nominal),
                    _metric_text(row.degradation_mean_score_trend_spearman),
                    _metric_text(row.degradation_mean_health_index_drop),
                    _metric_text(row.degradation_mean_health_monotonicity),
                    _metric_text(row.degradation_missed_confirmed_degradation_runs),
                    _metric_text(row.f1_score),
                    f"{_metric_text(row.false_positive_rate)} |",
                ]
            )
        )
    lines.extend(["", "## Mejor ejecucion por metrica temporal", ""])
    metric_rows = comparison.degradation_metrics or comparison.metrics
    for metric in metric_rows:
        direction = "mayor es mejor" if metric.higher_is_better else "menor es mejor"
        lines.append(
            "- "
            f"{metric.metric}: `{metric.best_run_id}` "
            f"({_metric_text(metric.best_value)}, {direction})"
        )
    lines.extend(
        [
            "",
            "## Nota metodologica",
            "",
            "Las metricas binarias se muestran como auxiliares/proxy. La lectura "
            "principal del perfil run-to-failure usa onset confirmado antes de "
            "fallo, lead time persistente, falsas alarmas nominales, tendencia "
            "score/Health Indicator, monotonicidad y onsets perdidos.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _validate_plain_names(plan: ExperimentPlan) -> None:
    _ensure_plain_name("plan_id", plan.plan_id)
    seen_experiment_ids: set[str] = set()
    seen_run_ids: set[str] = set()
    for spec in plan.experiments:
        _ensure_plain_name("experiment_id", spec.experiment_id)
        _ensure_plain_name("run_id", spec.run_id)
        if spec.experiment_id in seen_experiment_ids:
            raise ValueError(f"duplicated experiment_id: {spec.experiment_id}")
        if spec.run_id in seen_run_ids:
            raise ValueError(f"duplicated run_id: {spec.run_id}")
        seen_experiment_ids.add(spec.experiment_id)
        seen_run_ids.add(spec.run_id)


def _ensure_plain_name(field_name: str, value: str) -> None:
    path = Path(value)
    if path.name != value or path.is_absolute():
        raise ValueError(f"{field_name} must be a plain directory name")


def _window_experiment_id(label: str, config: StructuringConfig) -> str:
    return (
        f"win_{config.window_size}_ov_{int(config.overlap * 100):02d}_"
        f"{_plain_token(label)}"
    )


def _model_experiment_id(label: str, config: ModelingConfig) -> str:
    suffix = _plain_token(label)
    if config.model_name == "isolation_forest":
        threshold = config.hyperparameters.get("threshold_quantile", "auto")
        return f"iforest_thr_{_plain_token(str(threshold))}_{suffix}"
    if config.model_name == "pca_reconstruction_error":
        components = config.hyperparameters.get("n_components", "auto")
        return f"pca_nc_{_plain_token(str(components))}_{suffix}"
    return f"{_plain_token(config.model_name)}_{suffix}"


def _model_filename(model_name: str) -> str:
    suffix = "pt" if model_name == "autoencoder_dense" else "joblib"
    return f"{model_name}.{suffix}"


def _plain_token(value: str) -> str:
    cleaned = "".join(
        character.lower() if character.isalnum() else "_"
        for character in value
    )
    collapsed = "_".join(part for part in cleaned.split("_") if part)
    return collapsed or "candidate"


def _agent_turn(state: TFMStateModel, agent_name: str) -> int:
    return 1 + sum(
        message.role == "agent" and message.name == agent_name
        for message in state.messages
    )


def _approval_text(value: bool | None) -> str:
    if value is None:
        return "n/a"
    return "si" if value else "no"


def _metric_text(value: object) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
