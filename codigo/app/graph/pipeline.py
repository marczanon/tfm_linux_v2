"""Grafo LangGraph supervisado para el MVP CWRU."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from codigo.app.agents.cleaner import decide_cleaning_action
from codigo.app.agents.evaluator import decide_evaluation_action
from codigo.app.agents.modeler import decide_modeling_action
from codigo.app.agents.report_writer import decide_report_action
from codigo.app.agents.structurer import decide_structuring_action
from codigo.app.agents.supervisor import decide_supervisor_action
from codigo.app.executors.cleaning import (
    DEFAULT_CLEANING_CONFIG,
    generate_clean_signals,
)
from codigo.app.executors.data_profiler import generate_data_profile
from codigo.app.executors.dataset_manifest import generate_cwru_manifest
from codigo.app.executors.evaluation import generate_evaluation_report
from codigo.app.executors.modeling import (
    DEFAULT_MODELING_CONFIG,
    generate_model_outputs,
)
from codigo.app.executors.reporting import generate_technical_report
from codigo.app.executors.structuring import (
    DEFAULT_STRUCTURING_CONFIG,
    generate_temporal_structure,
)
from codigo.app.graph.state import TFMState, validate_state
from codigo.app.schemas.executor_results import (
    CleaningResult,
    EvaluationExecutorResult,
    ExecutorResult,
    ManifestResult,
    ModelingResult,
    ProfileResult,
    ReportExecutorResult,
    StructuringResult,
)
from codigo.app.schemas.agent_decisions import (
    CleaningDecision,
    EvaluationDecision,
    ModelingDecision,
    ReportDecision,
    StructuringDecision,
    SupervisorDecision,
)
from codigo.app.schemas.state import (
    DatasetProfileSummary,
    MetricsReport,
    PipelineError,
    StateMessage,
    TFMStateModel,
)


@dataclass(frozen=True)
class PipelineExecutors:
    """Funciones deterministas usadas por los nodos del grafo."""

    manifest: Callable[..., ManifestResult] = generate_cwru_manifest
    profile: Callable[..., ProfileResult] = generate_data_profile
    cleaning: Callable[..., CleaningResult] = generate_clean_signals
    structuring: Callable[..., StructuringResult] = generate_temporal_structure
    modeling: Callable[..., ModelingResult] = generate_model_outputs
    evaluation: Callable[..., EvaluationExecutorResult] = generate_evaluation_report
    reporting: Callable[..., ReportExecutorResult] = generate_technical_report


@dataclass(frozen=True)
class PipelineAgents:
    """Agentes que toman decisiones dentro del grafo."""

    supervisor: Callable[[TFMStateModel], SupervisorDecision] = decide_supervisor_action
    cleaner: Callable[[TFMStateModel], CleaningDecision] = decide_cleaning_action
    structurer: Callable[[TFMStateModel], StructuringDecision] = decide_structuring_action
    modeler: Callable[[TFMStateModel], ModelingDecision] = decide_modeling_action
    evaluator: Callable[[TFMStateModel], EvaluationDecision] = decide_evaluation_action
    report_writer: Callable[[TFMStateModel], ReportDecision] = decide_report_action


def build_cwru_pipeline(
    executors: PipelineExecutors | None = None,
    agents: PipelineAgents | None = None,
) -> Any:
    """Compila el grafo supervisado minimo del MVP CWRU."""

    runner = executors or PipelineExecutors()
    agent_runner = agents or PipelineAgents()
    graph = StateGraph(TFMState)
    graph.add_node("supervisor", lambda state: _supervisor_node(state, agent_runner))
    graph.add_node(
        "manifest_executor",
        lambda state: _manifest_node(state, runner),
    )
    graph.add_node(
        "profiler_executor",
        lambda state: _profile_node(state, runner),
    )
    graph.add_node("cleaner_agent", lambda state: _cleaner_node(state, agent_runner))
    graph.add_node(
        "cleaning_executor",
        lambda state: _cleaning_node(state, runner),
    )
    graph.add_node(
        "structuring_agent",
        lambda state: _structurer_node(state, agent_runner),
    )
    graph.add_node(
        "structuring_executor",
        lambda state: _structuring_node(state, runner),
    )
    graph.add_node("modeling_agent", lambda state: _modeler_node(state, agent_runner))
    graph.add_node(
        "modeling_executor",
        lambda state: _modeling_node(state, runner),
    )
    graph.add_node("evaluator", lambda state: _evaluation_node(state, runner))
    graph.add_node(
        "evaluation_agent",
        lambda state: _evaluator_agent_node(state, agent_runner),
    )
    graph.add_node(
        "report_writer",
        lambda state: _report_writer_node(state, runner, agent_runner),
    )

    graph.add_edge(START, "supervisor")
    graph.add_conditional_edges("supervisor", _route_from_supervisor)
    graph.add_edge("manifest_executor", "supervisor")
    graph.add_edge("profiler_executor", "supervisor")
    graph.add_edge("cleaner_agent", "supervisor")
    graph.add_edge("cleaning_executor", "supervisor")
    graph.add_edge("structuring_agent", "supervisor")
    graph.add_edge("structuring_executor", "supervisor")
    graph.add_edge("modeling_agent", "supervisor")
    graph.add_edge("modeling_executor", "supervisor")
    graph.add_edge("evaluator", "supervisor")
    graph.add_edge("evaluation_agent", "supervisor")
    graph.add_edge("report_writer", "supervisor")
    return graph.compile()


def run_cwru_pipeline(
    initial_state: TFMState,
    executors: PipelineExecutors | None = None,
    agents: PipelineAgents | None = None,
) -> TFMState:
    """Ejecuta el grafo compilado y devuelve el estado final validado."""

    final_state = build_cwru_pipeline(executors, agents).invoke(initial_state)
    return TFMState(**validate_state(final_state).to_langgraph_state())


def _supervisor_node(state: TFMState, agents: PipelineAgents) -> TFMState:
    model = validate_state(state)
    decision = agents.supervisor(model)
    updated = model.to_langgraph_state()
    updated["messages"] = [
        *updated["messages"],
        StateMessage(
            role="supervisor",
            name="supervisor",
            content=decision.model_dump_json(),
        ).model_dump(mode="json"),
    ]
    updated["current_stage"] = decision.next_stage
    updated["next_node"] = decision.next_node
    return TFMState(**validate_state(updated).to_langgraph_state())


def _manifest_node(state: TFMState, executors: PipelineExecutors) -> TFMState:
    model = validate_state(state)
    result = executors.manifest(raw_dir=model.raw_path)
    return _apply_result(
        model,
        result,
        next_stage="profiling",
        next_node="supervisor",
    )


def _profile_node(state: TFMState, executors: PipelineExecutors) -> TFMState:
    model = validate_state(state)
    if not model.manifest_path:
        return _missing_input_state(model, "profiling", "profiler_executor", "manifest_path")

    result = executors.profile(manifest_path=model.manifest_path)
    profile_summary = _dataset_profile_from_path(result.profile_path)
    extra_updates = {}
    if profile_summary is not None:
        extra_updates["dataset_profile"] = profile_summary.model_dump(mode="json")
    return _apply_result(
        model,
        result,
        next_stage="cleaning",
        next_node="supervisor",
        extra_updates=extra_updates,
    )


def _cleaner_node(state: TFMState, agents: PipelineAgents) -> TFMState:
    model = validate_state(state)
    decision = agents.cleaner(model)
    updated = model.to_langgraph_state()
    updated["messages"] = [
        *updated["messages"],
        StateMessage(
            role="agent",
            name="cleaner",
            content=decision.model_dump_json(),
        ).model_dump(mode="json"),
    ]
    updated["cleaning_config"] = decision.cleaning_config.model_dump(mode="json")
    updated["current_stage"] = "cleaning"
    updated["next_node"] = "supervisor"
    return TFMState(**validate_state(updated).to_langgraph_state())


def _cleaning_node(state: TFMState, executors: PipelineExecutors) -> TFMState:
    model = validate_state(state)
    if not model.manifest_path:
        return _missing_input_state(model, "cleaning", "cleaning_executor", "manifest_path")
    if not model.profile_path:
        return _missing_input_state(model, "cleaning", "cleaning_executor", "profile_path")

    config = model.cleaning_config or DEFAULT_CLEANING_CONFIG
    result = executors.cleaning(
        manifest_path=model.manifest_path,
        profile_path=model.profile_path,
        config=config,
    )
    return _apply_result(
        model,
        result,
        next_stage="structuring",
        next_node="supervisor",
        extra_updates={"cleaning_config": config.model_dump(mode="json")},
    )


def _structurer_node(state: TFMState, agents: PipelineAgents) -> TFMState:
    model = validate_state(state)
    decision = agents.structurer(model)
    updated = model.to_langgraph_state()
    updated["messages"] = [
        *updated["messages"],
        StateMessage(
            role="agent",
            name="structurer",
            content=decision.model_dump_json(),
        ).model_dump(mode="json"),
    ]
    updated["structuring_config"] = decision.structuring_config.model_dump(mode="json")
    updated["current_stage"] = "structuring"
    updated["next_node"] = "supervisor"
    return TFMState(**validate_state(updated).to_langgraph_state())


def _structuring_node(state: TFMState, executors: PipelineExecutors) -> TFMState:
    model = validate_state(state)
    if not model.clean_path:
        return _missing_input_state(model, "structuring", "structuring_executor", "clean_path")

    config = model.structuring_config or DEFAULT_STRUCTURING_CONFIG
    result = executors.structuring(clean_dir=model.clean_path, config=config)
    return _apply_result(
        model,
        result,
        next_stage="modeling",
        next_node="supervisor",
        extra_updates={"structuring_config": config.model_dump(mode="json")},
    )


def _modeler_node(state: TFMState, agents: PipelineAgents) -> TFMState:
    model = validate_state(state)
    decision = agents.modeler(model)
    updated = model.to_langgraph_state()
    updated["messages"] = [
        *updated["messages"],
        StateMessage(
            role="agent",
            name="modeler",
            content=decision.model_dump_json(),
        ).model_dump(mode="json"),
    ]
    updated["modeling_config"] = decision.modeling_config.model_dump(mode="json")
    updated["current_stage"] = "modeling"
    updated["next_node"] = "supervisor"
    return TFMState(**validate_state(updated).to_langgraph_state())


def _modeling_node(state: TFMState, executors: PipelineExecutors) -> TFMState:
    model = validate_state(state)
    features_path = _artifact_path(model, "features") or _features_from_tensor_path(model)
    if not features_path:
        return _missing_input_state(model, "modeling", "modeling_executor", "features artifact")

    config = model.modeling_config or DEFAULT_MODELING_CONFIG
    result = executors.modeling(features_path=features_path, config=config)
    return _apply_result(
        model,
        result,
        next_stage="evaluation",
        next_node="supervisor",
        extra_updates={"modeling_config": config.model_dump(mode="json")},
    )


def _evaluation_node(state: TFMState, executors: PipelineExecutors) -> TFMState:
    model = validate_state(state)
    predictions_path = _artifact_path(model, "predictions")
    if not predictions_path:
        return _missing_input_state(model, "evaluation", "evaluator", "predictions artifact")

    result = executors.evaluation(predictions_path=predictions_path)
    metrics = _metrics_from_path(result.metrics_path)
    extra_updates = {}
    if metrics is not None:
        extra_updates["metrics"] = metrics.model_dump(mode="json")
    return _apply_result(
        model,
        result,
        next_stage="evaluation",
        next_node="supervisor",
        extra_updates=extra_updates,
    )


def _evaluator_agent_node(state: TFMState, agents: PipelineAgents) -> TFMState:
    model = validate_state(state)
    decision = agents.evaluator(model)
    updated = model.to_langgraph_state()
    updated["messages"] = [
        *updated["messages"],
        StateMessage(
            role="agent",
            name="evaluator",
            content=decision.model_dump_json(),
        ).model_dump(mode="json"),
    ]
    updated["evaluation"] = decision.evaluation.model_dump(mode="json")
    updated["current_stage"] = "evaluation"
    updated["next_node"] = "supervisor"
    return TFMState(**validate_state(updated).to_langgraph_state())


def _report_writer_node(
    state: TFMState,
    executors: PipelineExecutors,
    agents: PipelineAgents,
) -> TFMState:
    model = validate_state(state)
    decision = agents.report_writer(model)
    updated = model.to_langgraph_state()
    updated["messages"] = [
        *updated["messages"],
        StateMessage(
            role="agent",
            name="report_writer",
            content=decision.model_dump_json(),
        ).model_dump(mode="json"),
    ]
    updated_model = validate_state(updated)
    result = executors.reporting(state=updated_model, decision=decision)
    return _apply_result(
        updated_model,
        result,
        next_stage="reporting",
        next_node="supervisor",
    )


def _apply_result(
    model: TFMStateModel,
    result: ExecutorResult,
    *,
    next_stage: str,
    next_node: str | None,
    extra_updates: dict[str, Any] | None = None,
) -> TFMState:
    state = model.to_langgraph_state()
    state["artifacts"] = [
        *state["artifacts"],
        *[artifact.model_dump(mode="json") for artifact in result.artifacts],
    ]
    state["errors"] = [
        *state["errors"],
        *[error.model_dump(mode="json") for error in result.errors],
    ]
    state["messages"] = [
        *state["messages"],
        StateMessage(
            role="tool",
            name=result.executor_name,
            content=f"{result.stage}: {result.message}",
        ).model_dump(mode="json"),
    ]

    if result.status != "success":
        state["current_stage"] = "failed"
        state["next_node"] = None
        return TFMState(**validate_state(state).to_langgraph_state())

    for key, value in result.state_updates.items():
        if key in _DIRECT_STATE_UPDATE_FIELDS:
            state[key] = value
    if extra_updates:
        state.update(extra_updates)
    state["current_stage"] = next_stage
    state["next_node"] = next_node
    return TFMState(**validate_state(state).to_langgraph_state())


def _missing_input_state(
    model: TFMStateModel,
    stage: str,
    node: str,
    field_name: str,
) -> TFMState:
    error = PipelineError(
        stage=stage,
        node=node,
        message=f"missing required state field: {field_name}",
        recoverable=True,
    )
    result = ExecutorResult(
        executor_name=node,
        stage=stage,
        status="failed",
        message=f"{node} could not start.",
        errors=[error],
    )
    return _apply_result(model, result, next_stage="failed", next_node=None)


def _route_from_supervisor(state: TFMState) -> str:
    next_node = validate_state(state).next_node
    return END if next_node is None else next_node


def _artifact_path(model: TFMStateModel, artifact_type: str) -> str | None:
    matches = [
        artifact.path
        for artifact in model.artifacts
        if artifact.artifact_type == artifact_type
    ]
    return matches[-1] if matches else None


def _features_from_tensor_path(model: TFMStateModel) -> str | None:
    if not model.tensor_path:
        return None
    return str(Path(model.tensor_path).with_name("windows_features.csv"))


def _dataset_profile_from_path(path: str | None) -> DatasetProfileSummary | None:
    if not path or not Path(path).exists():
        return None
    profile = json.loads(Path(path).read_text(encoding="utf-8"))
    return DatasetProfileSummary(
        dataset_name=str(profile.get("dataset", "cwru_bearing")),
        n_files=int(profile.get("n_files", 0)),
        channels=list(profile.get("channels_detected", [])),
        sample_rates_hz=[
            int(rate)
            for rate in profile.get("sample_rate_counts", {}).keys()
        ],
        label_counts={
            str(label): int(count)
            for label, count in profile.get("label_counts", {}).items()
        },
        stats_path=path,
        summary={
            "manifest_path": profile.get("manifest_path"),
            "generated_at": profile.get("generated_at"),
        },
    )


def _metrics_from_path(path: str | None) -> MetricsReport | None:
    if not path or not Path(path).exists():
        return None
    summary = json.loads(Path(path).read_text(encoding="utf-8"))
    metrics = summary.get("primary_metrics", {})
    return MetricsReport(
        metrics_path=path,
        precision=metrics.get("precision"),
        recall=metrics.get("recall"),
        f1_score=metrics.get("f1_score"),
        roc_auc=metrics.get("roc_auc"),
        pr_auc=metrics.get("pr_auc"),
        false_positive_rate=metrics.get("false_positive_rate"),
        extra={
            "primary_split": summary.get("primary_split"),
            "n_predictions": summary.get("n_predictions"),
        },
    )


_DIRECT_STATE_UPDATE_FIELDS = {
    "manifest_path",
    "profile_path",
    "extracted_signals_path",
    "clean_path",
    "tensor_path",
    "splits_path",
    "report_path",
}
