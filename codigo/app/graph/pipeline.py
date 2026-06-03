"""Grafo LangGraph supervisado para el MVP CWRU."""

from __future__ import annotations

import json
import inspect
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langgraph.graph import END, START, StateGraph

from codigo.app.agents.cleaner import decide_cleaning_action
from codigo.app.agents.evaluator import (
    decide_evaluation_action,
    retrieve_evaluator_memory_context,
)
from codigo.app.agents.modeler import decide_modeling_action
from codigo.app.agents.report_writer import (
    decide_report_action,
    decide_report_revision_action,
)
from codigo.app.agents.report_verifier import (
    decide_report_verification_action,
    render_report_verification_markdown,
)
from codigo.app.agents.structurer import (
    decide_structuring_action,
    retrieve_structurer_memory_context,
)
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
    ReportRevisionDecision,
    ReportVerificationDecision,
    StructuringDecision,
    SupervisorDecision,
)
from codigo.app.schemas.reasoning import RetrievedMemoryContext
from codigo.app.schemas.state import (
    ArtifactRef,
    DatasetProfileSummary,
    MetricsReport,
    PipelineError,
    StateMessage,
    TFMStateModel,
)
from codigo.app.services.decision_memory import (
    build_evaluation_decision_episode,
    build_evaluation_memory_candidate,
    build_structuring_decision_episode,
    build_structuring_memory_candidate,
    write_decision_memory_artifacts,
)
from codigo.app.services.run_persistence import (
    DEFAULT_RUNS_DIR,
    RunSnapshot,
    save_run_snapshot,
)
from codigo.app.services.agent_runtime import AgentRuntimeRecorder
from codigo.app.services.report_debate import (
    ReportDebateArtifacts,
    build_report_debate_record,
    write_report_debate_artifacts,
)
from codigo.app.services.vector_memory import VectorMemoryStore


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
    report_reviser: Callable[..., ReportRevisionDecision] = (
        decide_report_revision_action
    )
    report_verifier: Callable[[TFMStateModel], ReportVerificationDecision] = (
        decide_report_verification_action
    )


@dataclass(frozen=True)
class PipelineMemoryConfig:
    """Configuracion opcional de memoria RAG para agentes del grafo."""

    memory_store: VectorMemoryStore | None = None
    output_root: Path | str = Path("codigo/reports")
    structurer_top_k: int = 3
    evaluator_top_k: int = 3
    min_similarity: float = 0.0
    generate_decision_memory: bool = True
    reusable_as_context: bool = True


@dataclass(frozen=True)
class PersistedPipelineRun:
    """Resultado de ejecutar el pipeline y guardar su snapshot local."""

    state: TFMState
    snapshot: RunSnapshot


def build_cwru_pipeline(
    executors: PipelineExecutors | None = None,
    agents: PipelineAgents | None = None,
    memory_config: PipelineMemoryConfig | None = None,
    runtime_recorder: AgentRuntimeRecorder | None = None,
) -> Any:
    """Compila el grafo supervisado minimo del MVP CWRU."""

    runner = executors or PipelineExecutors()
    agent_runner = agents or PipelineAgents()
    memory_runner = memory_config
    graph = StateGraph(TFMState)
    graph.add_node(
        "supervisor",
        lambda state: _supervisor_node(state, agent_runner, runtime_recorder),
    )
    graph.add_node(
        "manifest_executor",
        lambda state: _manifest_node(state, runner, runtime_recorder),
    )
    graph.add_node(
        "profiler_executor",
        lambda state: _profile_node(state, runner, runtime_recorder),
    )
    graph.add_node(
        "cleaner_agent",
        lambda state: _cleaner_node(state, agent_runner, runtime_recorder),
    )
    graph.add_node(
        "cleaning_executor",
        lambda state: _cleaning_node(state, runner, runtime_recorder),
    )
    graph.add_node(
        "structuring_agent",
        lambda state: _structurer_node(
            state,
            agent_runner,
            memory_runner,
            runtime_recorder,
        ),
    )
    graph.add_node(
        "structuring_executor",
        lambda state: _structuring_node(
            state,
            runner,
            memory_runner,
            runtime_recorder,
        ),
    )
    graph.add_node(
        "modeling_agent",
        lambda state: _modeler_node(state, agent_runner, runtime_recorder),
    )
    graph.add_node(
        "modeling_executor",
        lambda state: _modeling_node(state, runner, runtime_recorder),
    )
    graph.add_node(
        "evaluator",
        lambda state: _evaluation_node(state, runner, runtime_recorder),
    )
    graph.add_node(
        "evaluation_agent",
        lambda state: _evaluator_agent_node(
            state,
            agent_runner,
            memory_runner,
            runtime_recorder,
        ),
    )
    graph.add_node(
        "report_writer",
        lambda state: _report_writer_node(
            state,
            runner,
            agent_runner,
            runtime_recorder,
        ),
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
    memory_config: PipelineMemoryConfig | None = None,
    runtime_recorder: AgentRuntimeRecorder | None = None,
) -> TFMState:
    """Ejecuta el grafo compilado y devuelve el estado final validado."""

    final_state = build_cwru_pipeline(
        executors=executors,
        agents=agents,
        memory_config=memory_config,
        runtime_recorder=runtime_recorder,
    ).invoke(initial_state)
    return TFMState(**validate_state(final_state).to_langgraph_state())


def run_and_persist_cwru_pipeline(
    initial_state: TFMState,
    executors: PipelineExecutors | None = None,
    agents: PipelineAgents | None = None,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
    memory_config: PipelineMemoryConfig | None = None,
    runtime_recorder: AgentRuntimeRecorder | None = None,
) -> PersistedPipelineRun:
    """Ejecuta el pipeline y guarda un snapshot local de la ejecucion."""

    final_state = run_cwru_pipeline(
        initial_state,
        executors=executors,
        agents=agents,
        memory_config=memory_config,
        runtime_recorder=runtime_recorder,
    )
    snapshot = save_run_snapshot(validate_state(final_state), runs_dir)
    return PersistedPipelineRun(state=final_state, snapshot=snapshot)


build_pipeline = build_cwru_pipeline
run_pipeline = run_cwru_pipeline
run_and_persist_pipeline = run_and_persist_cwru_pipeline


def _supervisor_node(
    state: TFMState,
    agents: PipelineAgents,
    runtime_recorder: AgentRuntimeRecorder | None,
) -> TFMState:
    model = validate_state(state)
    decision = agents.supervisor(model)
    _emit_decision_event(
        runtime_recorder,
        model=model,
        decision=decision,
        kind="supervisor_decision",
        source="supervisor",
        node="supervisor",
        title="Supervisor decide siguiente nodo",
        payload={
            "requires_human_review": decision.requires_human_review,
            "stop_reason": decision.stop_reason,
        },
    )
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


def _manifest_node(
    state: TFMState,
    executors: PipelineExecutors,
    runtime_recorder: AgentRuntimeRecorder | None,
) -> TFMState:
    model = validate_state(state)
    result = executors.manifest(raw_dir=model.raw_path)
    return _apply_result(
        model,
        result,
        next_stage="profiling",
        next_node="supervisor",
        runtime_recorder=runtime_recorder,
    )


def _profile_node(
    state: TFMState,
    executors: PipelineExecutors,
    runtime_recorder: AgentRuntimeRecorder | None,
) -> TFMState:
    model = validate_state(state)
    if not model.manifest_path:
        return _missing_input_state(
            model,
            "profiling",
            "profiler_executor",
            "manifest_path",
            runtime_recorder,
        )

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
        runtime_recorder=runtime_recorder,
    )


def _cleaner_node(
    state: TFMState,
    agents: PipelineAgents,
    runtime_recorder: AgentRuntimeRecorder | None,
) -> TFMState:
    model = validate_state(state)
    decision = agents.cleaner(model)
    _emit_decision_event(
        runtime_recorder,
        model=model,
        decision=decision,
        kind="agent_decision",
        source="agent",
        node="cleaner_agent",
        title="Limpiador propone configuracion",
        payload={
            "cleaning_config": decision.cleaning_config.model_dump(mode="json"),
            "expected_artifact_path": decision.expected_artifact_path,
            "warnings": decision.warnings,
        },
    )
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


def _cleaning_node(
    state: TFMState,
    executors: PipelineExecutors,
    runtime_recorder: AgentRuntimeRecorder | None,
) -> TFMState:
    model = validate_state(state)
    if not model.manifest_path:
        return _missing_input_state(
            model,
            "cleaning",
            "cleaning_executor",
            "manifest_path",
            runtime_recorder,
        )
    if not model.profile_path:
        return _missing_input_state(
            model,
            "cleaning",
            "cleaning_executor",
            "profile_path",
            runtime_recorder,
        )

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
        runtime_recorder=runtime_recorder,
    )


def _structurer_node(
    state: TFMState,
    agents: PipelineAgents,
    memory_config: PipelineMemoryConfig | None,
    runtime_recorder: AgentRuntimeRecorder | None,
) -> TFMState:
    model = validate_state(state)
    memory_context = _retrieve_structurer_context(model, memory_config)
    _emit_memory_event(
        runtime_recorder,
        model=model,
        agent_name="structurer",
        memory_context=memory_context,
    )
    memory_context_path = _write_memory_context_artifact(
        model,
        "structurer",
        memory_context,
        memory_config,
    )
    decision = _call_agent_with_optional_memory(
        agents.structurer,
        model,
        memory_context,
    )
    _emit_decision_event(
        runtime_recorder,
        model=model,
        decision=decision,
        kind="agent_decision",
        source="agent",
        node="structuring_agent",
        title="Estructurador decide ventanas y features",
        payload={
            "structuring_config": decision.structuring_config.model_dump(mode="json"),
            "comparison_candidates": [
                candidate.model_dump(mode="json")
                for candidate in decision.comparison_candidates
            ],
            "used_memory_context": decision.used_memory_context,
            "memory_usage_summary": decision.memory_usage_summary,
            "memory_record_uses": [
                item.model_dump(mode="json")
                for item in decision.memory_record_uses
            ],
        },
    )
    updated = model.to_langgraph_state()
    memory_artifacts = _memory_context_artifacts(
        "structurer",
        memory_context,
        memory_context_path,
    )
    updated["messages"] = [
        *updated["messages"],
        StateMessage(
            role="agent",
            name="structurer",
            content=decision.model_dump_json(),
        ).model_dump(mode="json"),
    ]
    updated["artifacts"] = [
        *updated["artifacts"],
        *[artifact.model_dump(mode="json") for artifact in memory_artifacts],
    ]
    updated["structuring_config"] = decision.structuring_config.model_dump(mode="json")
    updated["current_stage"] = "structuring"
    updated["next_node"] = "supervisor"
    return TFMState(**validate_state(updated).to_langgraph_state())


def _structuring_node(
    state: TFMState,
    executors: PipelineExecutors,
    memory_config: PipelineMemoryConfig | None,
    runtime_recorder: AgentRuntimeRecorder | None,
) -> TFMState:
    model = validate_state(state)
    if not model.clean_path:
        return _missing_input_state(
            model,
            "structuring",
            "structuring_executor",
            "clean_path",
            runtime_recorder,
        )

    config = model.structuring_config or DEFAULT_STRUCTURING_CONFIG
    result = executors.structuring(clean_dir=model.clean_path, config=config)
    updated = _apply_result(
        model,
        result,
        next_stage="modeling",
        next_node="supervisor",
        extra_updates={"structuring_config": config.model_dump(mode="json")},
        runtime_recorder=runtime_recorder,
    )
    if result.status != "success":
        return updated
    return _append_structuring_decision_memory_artifacts(
        updated,
        result,
        memory_config,
    )


def _modeler_node(
    state: TFMState,
    agents: PipelineAgents,
    runtime_recorder: AgentRuntimeRecorder | None,
) -> TFMState:
    model = validate_state(state)
    decision = agents.modeler(model)
    _emit_decision_event(
        runtime_recorder,
        model=model,
        decision=decision,
        kind="agent_decision",
        source="agent",
        node="modeling_agent",
        title="Modelador selecciona algoritmo",
        payload={
            "decision_strategy": decision.decision_strategy.model_dump(mode="json"),
            "modeling_config": decision.modeling_config.model_dump(mode="json"),
            "train_split": decision.train_split,
            "validation_split": decision.validation_split,
            "comparison_candidates": [
                candidate.model_dump(mode="json")
                for candidate in decision.comparison_candidates
            ],
        },
    )
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


def _modeling_node(
    state: TFMState,
    executors: PipelineExecutors,
    runtime_recorder: AgentRuntimeRecorder | None,
) -> TFMState:
    model = validate_state(state)
    features_path = _artifact_path(model, "features") or _features_from_tensor_path(model)
    if not features_path:
        return _missing_input_state(
            model,
            "modeling",
            "modeling_executor",
            "features artifact",
            runtime_recorder,
        )

    config = model.modeling_config or DEFAULT_MODELING_CONFIG
    result = executors.modeling(features_path=features_path, config=config)
    return _apply_result(
        model,
        result,
        next_stage="evaluation",
        next_node="supervisor",
        extra_updates={"modeling_config": config.model_dump(mode="json")},
        runtime_recorder=runtime_recorder,
    )


def _evaluation_node(
    state: TFMState,
    executors: PipelineExecutors,
    runtime_recorder: AgentRuntimeRecorder | None,
) -> TFMState:
    model = validate_state(state)
    predictions_path = _artifact_path(model, "predictions")
    if not predictions_path:
        return _missing_input_state(
            model,
            "evaluation",
            "evaluator",
            "predictions artifact",
            runtime_recorder,
        )

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
        runtime_recorder=runtime_recorder,
    )


def _evaluator_agent_node(
    state: TFMState,
    agents: PipelineAgents,
    memory_config: PipelineMemoryConfig | None,
    runtime_recorder: AgentRuntimeRecorder | None,
) -> TFMState:
    model = validate_state(state)
    memory_context = _retrieve_evaluator_context(model, memory_config)
    _emit_memory_event(
        runtime_recorder,
        model=model,
        agent_name="evaluator",
        memory_context=memory_context,
    )
    memory_context_path = _write_memory_context_artifact(
        model,
        "evaluator",
        memory_context,
        memory_config,
    )
    decision = _call_agent_with_optional_memory(
        agents.evaluator,
        model,
        memory_context,
    )
    _emit_decision_event(
        runtime_recorder,
        model=model,
        decision=decision,
        kind="agent_decision",
        source="agent",
        node="evaluation_agent",
        title="Evaluador interpreta metricas",
        payload={
            "evaluation": decision.evaluation.model_dump(mode="json"),
            "min_recall_required": decision.min_recall_required,
            "max_false_positive_rate": decision.max_false_positive_rate,
            "used_memory_context": decision.used_memory_context,
            "memory_usage_summary": decision.memory_usage_summary,
            "memory_record_uses": [
                item.model_dump(mode="json")
                for item in decision.memory_record_uses
            ],
        },
    )
    updated = model.to_langgraph_state()
    memory_artifacts = _memory_context_artifacts(
        "evaluator",
        memory_context,
        memory_context_path,
    )
    updated["messages"] = [
        *updated["messages"],
        StateMessage(
            role="agent",
            name="evaluator",
            content=decision.model_dump_json(),
        ).model_dump(mode="json"),
    ]
    updated["artifacts"] = [
        *updated["artifacts"],
        *[artifact.model_dump(mode="json") for artifact in memory_artifacts],
    ]
    updated["evaluation"] = decision.evaluation.model_dump(mode="json")
    updated["current_stage"] = "evaluation"
    updated["next_node"] = "supervisor"
    updated_state = TFMState(**validate_state(updated).to_langgraph_state())
    return _append_evaluation_decision_memory_artifacts(
        updated_state,
        memory_config,
    )


def _report_writer_node(
    state: TFMState,
    executors: PipelineExecutors,
    agents: PipelineAgents,
    runtime_recorder: AgentRuntimeRecorder | None,
) -> TFMState:
    model = validate_state(state)
    decision = agents.report_writer(model)
    _emit_decision_event(
        runtime_recorder,
        model=model,
        decision=decision,
        kind="agent_decision",
        source="agent",
        node="report_writer",
        title="Redactor prepara informe",
        payload={
            "output_path": decision.output_path,
            "output_format": decision.output_format,
            "sections": [
                section.model_dump(mode="json")
                for section in decision.sections
            ],
        },
    )
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
    reported_state = _apply_result(
        updated_model,
        result,
        next_stage="reporting",
        next_node="supervisor",
        runtime_recorder=runtime_recorder,
    )
    if result.status != "success":
        return reported_state
    return _report_debate_step(
        reported_state,
        executors,
        agents,
        initial_report_decision=decision,
        runtime_recorder=runtime_recorder,
    )


def _report_debate_step(
    state: TFMState,
    executors: PipelineExecutors,
    agents: PipelineAgents,
    *,
    initial_report_decision: ReportDecision,
    runtime_recorder: AgentRuntimeRecorder | None,
) -> TFMState:
    model = validate_state(state)
    initial_report_markdown = _read_report_markdown(model)
    initial_verification = agents.report_verifier(model)
    _emit_report_verification_event(
        runtime_recorder,
        model=model,
        decision=initial_verification,
        title="Verificador audita borrador",
        round_index=0,
    )
    model = validate_state(
        _append_agent_message(model, "report_verifier", initial_verification)
    )

    revision_decision: ReportRevisionDecision | None = None
    final_report_decision: ReportDecision | ReportRevisionDecision = (
        initial_report_decision
    )
    final_verification = initial_verification
    revision_markdowns: list[tuple[int, str]] = []

    if initial_verification.verification_status != "approved":
        revision_decision = agents.report_reviser(
            model,
            initial_verification,
            original_decision=initial_report_decision,
            revision_round=1,
        )
        _emit_decision_event(
            runtime_recorder,
            model=model,
            decision=revision_decision,
            kind="agent_decision",
            source="agent",
            node="report_writer",
            title="Redactor revisa informe",
            payload={
                "revision_round": revision_decision.revision_round,
                "accepted_issue_ids": revision_decision.accepted_issue_ids,
                "rejected_issue_ids": revision_decision.rejected_issue_ids,
                "changes_summary": revision_decision.changes_summary,
            },
        )
        model = validate_state(
            _append_agent_message(model, "report_writer", revision_decision)
        )
        result = executors.reporting(state=model, decision=revision_decision)
        rendered_revision = _apply_result(
            model,
            result,
            next_stage="reporting",
            next_node="supervisor",
            runtime_recorder=runtime_recorder,
        )
        if result.status != "success":
            return rendered_revision
        model = validate_state(rendered_revision)
        final_report_decision = revision_decision
        revision_markdowns.append(
            (revision_decision.revision_round, _read_report_markdown(model))
        )
        final_verification = agents.report_verifier(model)
        _emit_report_verification_event(
            runtime_recorder,
            model=model,
            decision=final_verification,
            title="Verificador reevalua informe",
            round_index=revision_decision.revision_round,
        )
        model = validate_state(
            _append_agent_message(model, "report_verifier", final_verification)
        )

    output_dir = _report_evidence_output_dir(model)
    debate = build_report_debate_record(
        run_id=model.run_id,
        initial_report_decision=initial_report_decision,
        initial_verification=initial_verification,
        final_report_decision=final_report_decision,
        final_verification=final_verification,
        revision_decision=revision_decision,
        max_rounds=1,
    )
    debate_artifacts = write_report_debate_artifacts(
        debate=debate,
        output_dir=output_dir,
        initial_report_markdown=initial_report_markdown,
        revision_markdowns=revision_markdowns,
    )
    artifacts = [
        *_write_report_verification_artifacts(model, final_verification),
        *_report_debate_artifact_refs(debate_artifacts),
    ]
    updated = model.to_langgraph_state()
    updated["artifacts"] = [
        *updated["artifacts"],
        *[artifact.model_dump(mode="json") for artifact in artifacts],
    ]
    return TFMState(**validate_state(updated).to_langgraph_state())


def _retrieve_structurer_context(
    model: TFMStateModel,
    memory_config: PipelineMemoryConfig | None,
) -> RetrievedMemoryContext | None:
    if memory_config is None or memory_config.memory_store is None:
        return None
    return retrieve_structurer_memory_context(
        model,
        memory_store=memory_config.memory_store,
        top_k=memory_config.structurer_top_k,
        min_similarity=memory_config.min_similarity,
    )


def _retrieve_evaluator_context(
    model: TFMStateModel,
    memory_config: PipelineMemoryConfig | None,
) -> RetrievedMemoryContext | None:
    if memory_config is None or memory_config.memory_store is None:
        return None
    return retrieve_evaluator_memory_context(
        model,
        memory_store=memory_config.memory_store,
        top_k=memory_config.evaluator_top_k,
        min_similarity=memory_config.min_similarity,
    )


def _write_report_verification_artifacts(
    model: TFMStateModel,
    decision: ReportVerificationDecision,
) -> list[ArtifactRef]:
    output_dir = _report_evidence_output_dir(model)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "report_verification.json"
    markdown_path = output_dir / "report_verification.md"
    json_path.write_text(
        json.dumps(decision.model_dump(mode="json"), indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    markdown_path.write_text(
        render_report_verification_markdown(decision),
        encoding="utf-8",
    )
    return [
        ArtifactRef(
            name="report_verification",
            artifact_type="config",
            path=json_path.as_posix(),
            producer="report_verifier",
            description="Decision estructurada del verificador del informe final.",
            metadata={
                "decision_id": decision.decision_id,
                "verification_status": decision.verification_status,
            },
        ),
        ArtifactRef(
            name="report_verification_report",
            artifact_type="report",
            path=markdown_path.as_posix(),
            producer="report_verifier",
            description="Vista humana de la verificacion del informe final.",
            metadata={
                "decision_id": decision.decision_id,
                "verification_status": decision.verification_status,
            },
        ),
    ]


def _report_debate_artifact_refs(
    artifacts: ReportDebateArtifacts,
) -> list[ArtifactRef]:
    refs = [
        ArtifactRef(
            name="report_debate",
            artifact_type="config",
            path=artifacts.debate_path,
            producer="report_writer",
            description="Registro JSON del debate controlado del informe.",
            metadata={
                "debate_id": artifacts.debate.debate_id,
                "status": artifacts.debate.status,
                "rounds_used": artifacts.debate.rounds_used,
            },
        ),
        ArtifactRef(
            name="report_debate_report",
            artifact_type="report",
            path=artifacts.report_path,
            producer="report_writer",
            description="Vista humana del debate controlado del informe.",
            metadata={
                "debate_id": artifacts.debate.debate_id,
                "status": artifacts.debate.status,
            },
        ),
        ArtifactRef(
            name="final_report_initial",
            artifact_type="report",
            path=artifacts.initial_report_path,
            producer="report_writer",
            description="Borrador inicial del informe antes del debate.",
            metadata={"debate_id": artifacts.debate.debate_id},
        ),
    ]
    for index, path in enumerate(artifacts.revision_report_paths, start=1):
        refs.append(
            ArtifactRef(
                name=f"final_report_revision_{index:03d}",
                artifact_type="report",
                path=path,
                producer="report_writer",
                description="Version revisada del informe durante el debate.",
                metadata={
                    "debate_id": artifacts.debate.debate_id,
                    "revision_round": index,
                },
            )
        )
    return refs


def _emit_report_verification_event(
    runtime_recorder: AgentRuntimeRecorder | None,
    *,
    model: TFMStateModel,
    decision: ReportVerificationDecision,
    title: str,
    round_index: int,
) -> None:
    _emit_decision_event(
        runtime_recorder,
        model=model,
        decision=decision,
        kind="agent_decision",
        source="agent",
        node="report_verifier",
        title=title,
        payload={
            "debate_round": round_index,
            "verification_status": decision.verification_status,
            "n_unsupported_claims": len(decision.unsupported_claims),
            "n_misleading_claims": len(decision.misleading_claims),
            "n_missing_limitations": len(decision.missing_limitations),
            "required_corrections": decision.required_corrections,
            "human_summary": decision.summary,
        },
        summary=decision.summary,
    )


def _append_agent_message(
    model: TFMStateModel,
    agent_name: str,
    decision: Any,
) -> TFMState:
    updated = model.to_langgraph_state()
    updated["messages"] = [
        *updated["messages"],
        StateMessage(
            role="agent",
            name=agent_name,
            content=decision.model_dump_json(),
        ).model_dump(mode="json"),
    ]
    return TFMState(**validate_state(updated).to_langgraph_state())


def _read_report_markdown(model: TFMStateModel) -> str:
    if not model.report_path:
        return ""
    path = Path(model.report_path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _report_evidence_output_dir(model: TFMStateModel) -> Path:
    if model.report_path:
        return Path(model.report_path).parent / "evidence"
    return (
        Path("codigo/reports")
        / model.project_context.dataset
        / model.run_id
        / "evidence"
    )


def _call_agent_with_optional_memory(
    agent: Callable[..., Any],
    model: TFMStateModel,
    memory_context: RetrievedMemoryContext | None,
) -> Any:
    if memory_context is None or not _accepts_memory_context(agent):
        return agent(model)
    return agent(model, memory_context=memory_context)


def _accepts_memory_context(agent: Callable[..., Any]) -> bool:
    try:
        signature = inspect.signature(agent)
    except (TypeError, ValueError):
        return False
    return "memory_context" in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def _write_memory_context_artifact(
    model: TFMStateModel,
    agent_name: str,
    memory_context: RetrievedMemoryContext | None,
    memory_config: PipelineMemoryConfig | None,
) -> str | None:
    if memory_context is None or memory_config is None:
        return None
    output_dir = _agent_memory_output_dir(model, agent_name, memory_config)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "retrieved_memory_context.json"
    path.write_text(
        json.dumps(memory_context.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    return path.as_posix()


def _memory_context_artifacts(
    agent_name: str,
    memory_context: RetrievedMemoryContext | None,
    memory_context_path: str | None,
) -> list[ArtifactRef]:
    if memory_context is None or memory_context_path is None:
        return []
    return [
        ArtifactRef(
            name=f"{agent_name}_retrieved_memory_context",
            artifact_type="config",
            path=memory_context_path,
            producer=agent_name,
            description=f"Contexto RAG recuperado para el agente {agent_name}.",
            metadata={
                "context_id": memory_context.context_id,
                "query_id": memory_context.query.query_id,
                "n_items": len(memory_context.items),
            },
        )
    ]


def _append_structuring_decision_memory_artifacts(
    state: TFMState,
    result: StructuringResult,
    memory_config: PipelineMemoryConfig | None,
) -> TFMState:
    if memory_config is None or not memory_config.generate_decision_memory:
        return state
    model = validate_state(state)
    decision = _latest_structuring_decision(model)
    if decision is None:
        return state
    memory_context = _latest_memory_context(model, "structurer")
    episode = build_structuring_decision_episode(
        state=model,
        decision=decision,
        execution_result_summary=(
            f"{result.message} n_windows={result.n_windows}; "
            f"features_path={result.features_path}; splits_path={result.splits_path}."
        ),
        outcome="supported",
        memory_context=memory_context,
    )
    candidate = build_structuring_memory_candidate(
        episode,
        reusable_as_context=memory_config.reusable_as_context,
    )
    artifacts = write_decision_memory_artifacts(
        episode=episode,
        candidate=candidate,
        output_dir=_agent_memory_output_dir(model, "structurer", memory_config),
    )
    return _append_artifacts(
        model,
        _decision_memory_artifact_refs("structurer", artifacts),
    )


def _append_evaluation_decision_memory_artifacts(
    state: TFMState,
    memory_config: PipelineMemoryConfig | None,
) -> TFMState:
    if memory_config is None or not memory_config.generate_decision_memory:
        return state
    model = validate_state(state)
    decision = _latest_evaluation_decision(model)
    if decision is None:
        return state
    memory_context = _latest_memory_context(model, "evaluator")
    episode = build_evaluation_decision_episode(
        state=model,
        decision=decision,
        memory_context=memory_context,
    )
    candidate = build_evaluation_memory_candidate(
        episode,
        reusable_as_context=memory_config.reusable_as_context,
    )
    artifacts = write_decision_memory_artifacts(
        episode=episode,
        candidate=candidate,
        output_dir=_agent_memory_output_dir(model, "evaluator", memory_config),
    )
    return _append_artifacts(
        model,
        _decision_memory_artifact_refs("evaluator", artifacts),
    )


def _decision_memory_artifact_refs(
    agent_name: str,
    artifacts: Any,
) -> list[ArtifactRef]:
    return [
        ArtifactRef(
            name=f"{agent_name}_decision_episode",
            artifact_type="config",
            path=artifacts.episode_path,
            producer=agent_name,
            description=f"Episodio de decision generado para {agent_name}.",
            metadata={"episode_id": artifacts.episode.episode_id},
        ),
        ArtifactRef(
            name=f"{agent_name}_decision_episode_report",
            artifact_type="report",
            path=artifacts.episode_report_path,
            producer=agent_name,
            description=f"Informe legible del episodio de decision de {agent_name}.",
            metadata={"episode_id": artifacts.episode.episode_id},
        ),
        ArtifactRef(
            name=f"{agent_name}_memory_candidate",
            artifact_type="config",
            path=artifacts.candidate_path,
            producer=agent_name,
            description=f"Candidato de memoria destilado para {agent_name}.",
            metadata={"candidate_id": artifacts.candidate.candidate_id},
        ),
        ArtifactRef(
            name=f"{agent_name}_memory_candidate_report",
            artifact_type="report",
            path=artifacts.candidate_report_path,
            producer=agent_name,
            description=f"Informe legible del candidato de memoria de {agent_name}.",
            metadata={"candidate_id": artifacts.candidate.candidate_id},
        ),
    ]


def _append_artifacts(
    model: TFMStateModel,
    artifacts: list[ArtifactRef],
) -> TFMState:
    if not artifacts:
        return TFMState(**model.to_langgraph_state())
    updated = model.to_langgraph_state()
    updated["artifacts"] = [
        *updated["artifacts"],
        *[artifact.model_dump(mode="json") for artifact in artifacts],
    ]
    return TFMState(**validate_state(updated).to_langgraph_state())


def _latest_structuring_decision(model: TFMStateModel) -> StructuringDecision | None:
    for message in reversed(model.messages):
        if message.role == "agent" and message.name == "structurer":
            return StructuringDecision.model_validate_json(message.content)
    return None


def _latest_evaluation_decision(model: TFMStateModel) -> EvaluationDecision | None:
    for message in reversed(model.messages):
        if message.role == "agent" and message.name == "evaluator":
            return EvaluationDecision.model_validate_json(message.content)
    return None


def _latest_memory_context(
    model: TFMStateModel,
    agent_name: str,
) -> RetrievedMemoryContext | None:
    artifact_name = f"{agent_name}_retrieved_memory_context"
    for artifact in reversed(model.artifacts):
        if artifact.name == artifact_name:
            return RetrievedMemoryContext.model_validate_json(
                Path(artifact.path).read_text(encoding="utf-8")
            )
    return None


def _emit_decision_event(
    runtime_recorder: AgentRuntimeRecorder | None,
    *,
    model: TFMStateModel,
    decision: Any,
    kind: str,
    source: str,
    node: str,
    title: str,
    payload: dict[str, Any] | None = None,
    summary: str | None = None,
) -> None:
    rationale = getattr(decision, "rationale", None)
    agent_name = getattr(decision, "agent_name", None)
    memory_record_ids = getattr(decision, "memory_record_ids", [])
    event_payload = {
        "state": _state_runtime_payload(model),
        "decision": decision.model_dump(mode="json"),
    }
    if payload:
        event_payload.update(payload)
    _emit_runtime_event(
        runtime_recorder,
        kind=kind,
        source=source,
        title=title,
        summary=summary or rationale or title,
        stage=model.current_stage,
        node=node,
        agent_name=agent_name,
        decision_id=getattr(decision, "decision_id", None),
        rationale=rationale,
        confidence=getattr(decision, "confidence", None),
        next_stage=getattr(decision, "next_stage", None),
        next_node=getattr(decision, "next_node", None),
        memory_context_id=getattr(decision, "memory_context_id", None),
        memory_record_ids=list(memory_record_ids or []),
        payload=event_payload,
    )


def _emit_memory_event(
    runtime_recorder: AgentRuntimeRecorder | None,
    *,
    model: TFMStateModel,
    agent_name: str,
    memory_context: RetrievedMemoryContext | None,
) -> None:
    if memory_context is None:
        _emit_runtime_event(
            runtime_recorder,
            kind="memory_retrieval",
            source="memory",
            title=f"Memoria para {agent_name}",
            summary="No se recupero contexto de memoria para esta decision.",
            stage=model.current_stage,
            node=f"{agent_name}_memory",
            agent_name=agent_name,
            payload={
                "state": _state_runtime_payload(model),
                "available": False,
                "items": [],
            },
        )
        return
    items = [
        {
            "rank": item.rank,
            "similarity": round(item.similarity, 6),
            "retrieval_use": item.retrieval_use,
            "memory_record_id": item.record.memory_record_id,
            "memory_role": item.record.memory_role,
            "human_verdict": item.record.human_verdict,
            "run_id": item.record.run_id,
            "summary": item.record.summary,
            "tags": item.record.tags[:8],
        }
        for item in memory_context.items[:5]
    ]
    record_ids = [item["memory_record_id"] for item in items]
    _emit_runtime_event(
        runtime_recorder,
        kind="memory_retrieval",
        source="memory",
        title=f"Memoria recuperada para {agent_name}",
        summary=f"{len(memory_context.items)} recuerdos recuperados.",
        stage=model.current_stage,
        node=f"{agent_name}_memory",
        agent_name=agent_name,
        memory_context_id=memory_context.context_id,
        memory_record_ids=record_ids,
        payload={
            "state": _state_runtime_payload(model),
            "available": True,
            "query_id": memory_context.query.query_id,
            "retrieval_backend": memory_context.retrieval_backend,
            "embedding_model": memory_context.embedding_model,
            "items": items,
        },
    )


def _emit_executor_event(
    runtime_recorder: AgentRuntimeRecorder | None,
    *,
    model: TFMStateModel,
    result: ExecutorResult,
    next_stage: str,
    next_node: str | None,
) -> None:
    _emit_runtime_event(
        runtime_recorder,
        kind="executor_result",
        source="executor",
        title=f"Ejecutor {result.executor_name}",
        summary=result.message,
        stage=result.stage,
        node=result.executor_name,
        next_stage="failed" if result.status != "success" else next_stage,
        next_node=None if result.status != "success" else next_node,
        payload={
            "state": _state_runtime_payload(model),
            "status": result.status,
            "artifact_names": [artifact.name for artifact in result.artifacts],
            "artifact_types": [artifact.artifact_type for artifact in result.artifacts],
            "errors": [error.model_dump(mode="json") for error in result.errors],
            "state_updates": result.state_updates,
        },
    )


def _emit_runtime_event(
    runtime_recorder: AgentRuntimeRecorder | None,
    **event: Any,
) -> None:
    if runtime_recorder is None:
        return
    try:
        runtime_recorder.emit(**event)
    except Exception:
        return


def _state_runtime_payload(model: TFMStateModel) -> dict[str, Any]:
    return {
        "dataset": model.project_context.dataset,
        "current_stage": model.current_stage,
        "next_node": model.next_node,
        "n_messages": len(model.messages),
        "n_artifacts": len(model.artifacts),
        "n_errors": len(model.errors),
        "has_profile": model.profile_path is not None,
        "has_clean_path": model.clean_path is not None,
        "has_tensor_path": model.tensor_path is not None,
        "has_metrics": model.metrics is not None,
        "has_evaluation": model.evaluation is not None,
    }


def _agent_memory_output_dir(
    model: TFMStateModel,
    agent_name: str,
    memory_config: PipelineMemoryConfig,
) -> Path:
    return (
        Path(memory_config.output_root)
        / model.project_context.dataset
        / model.run_id
        / "agent_memory"
        / agent_name
    )


def _apply_result(
    model: TFMStateModel,
    result: ExecutorResult,
    *,
    next_stage: str,
    next_node: str | None,
    extra_updates: dict[str, Any] | None = None,
    runtime_recorder: AgentRuntimeRecorder | None = None,
) -> TFMState:
    _emit_executor_event(
        runtime_recorder,
        model=model,
        result=result,
        next_stage=next_stage,
        next_node=next_node,
    )
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
    runtime_recorder: AgentRuntimeRecorder | None = None,
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
    return _apply_result(
        model,
        result,
        next_stage="failed",
        next_node=None,
        runtime_recorder=runtime_recorder,
    )


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
    degradation = summary.get("degradation_metrics", {})
    metric_families = summary.get("metric_families", [])
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
            "metric_families": (
                ", ".join(metric_families)
                if isinstance(metric_families, list)
                else metric_families
            ),
            "degradation_available": degradation.get("available"),
            "degradation_n_runs": degradation.get("n_runs"),
            "degradation_missed_runs": degradation.get("missed_runs"),
            "degradation_detected_before_failure_rate": degradation.get(
                "detected_before_failure_rate"
            ),
            "degradation_mean_lead_time_to_failure": degradation.get(
                "mean_lead_time_to_failure"
            ),
            "degradation_mean_false_alarm_rate_nominal": degradation.get(
                "mean_false_alarm_rate_nominal"
            ),
            "degradation_mean_score_trend_spearman": degradation.get(
                "mean_score_trend_spearman"
            ),
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
