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
    dataset: Literal["cwru_bearing"] = "cwru_bearing"
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

    experiments = [
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
    return ExperimentPlan(
        plan_id=plan_id,
        description=(
            "Comparacion agentica de modelos sobre CWRU. Las alternativas "
            "proceden de la decision del agente modelador; el protocolo solo "
            "materializa y compara configuraciones soportadas."
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

    model_path = experiment_dir / "models" / f"{spec.modeling_config.model_name}.joblib"
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


def _results_table_markdown(
    plan: ExperimentPlan,
    comparison: RunComparison,
) -> str:
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
