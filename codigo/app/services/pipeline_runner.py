"""Planificador y runner comun para ejecuciones multi-dataset."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from codigo.app.executors.cleaning import generate_clean_signals
from codigo.app.executors.data_profiler import generate_data_profile
from codigo.app.executors.dataset_manifest import generate_dataset_manifest
from codigo.app.executors.evaluation import generate_evaluation_report
from codigo.app.executors.modeling import generate_model_outputs
from codigo.app.executors.reporting import generate_technical_report
from codigo.app.executors.structuring import generate_temporal_structure
from codigo.app.graph.pipeline import (
    PersistedPipelineRun,
    PipelineAgents,
    PipelineExecutors,
    PipelineMemoryConfig,
    run_and_persist_pipeline,
)
from codigo.app.graph.state import TFMState, create_initial_cwru_state
from codigo.app.schemas.agent_decisions import SupervisorDecision
from codigo.app.schemas.executor_results import ModelingResult
from codigo.app.schemas.pipeline_run import (
    DatasetCapabilityRule,
    DatasetPipelinePaths,
    DatasetPipelinePlan,
    DatasetRunPolicy,
    PipelineRunRequest,
    PipelineRunStage,
)
from codigo.app.schemas.state import (
    ArtifactRef,
    CleaningConfig,
    HumanApproval,
    PipelineError,
    ProjectContext,
    TFMStateModel,
)
from codigo.app.services.dataset_adapters import (
    describe_dataset,
    get_dataset_adapter,
    infer_dataset_adapter,
)
from codigo.app.services.llm_agents import build_ollama_pipeline_agents
from codigo.app.services.nasa_ims_temporal_policy import (
    NASA_IMS_TEMPORAL_POLICY_V1,
    apply_nasa_ims_temporal_policy_to_result,
)
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR
from codigo.app.services.agent_runtime import AgentRuntimeRecorder

FULL_RUN_STAGES: list[PipelineRunStage] = [
    "manifest",
    "profiling",
    "cleaning",
    "structuring",
    "modeling",
    "evaluation",
    "reporting",
]
DIAGNOSTIC_RUN_STAGES: list[PipelineRunStage] = [
    "manifest",
    "profiling",
    "cleaning",
    "structuring",
]
NASA_MODELING_BLOCK_REASON = (
    "NASA IMS real requiere declarar una politica temporal versionada o "
    "etiquetas sinteticas/controladas antes de modelado/evaluacion supervisados."
)
SUPPORTED_DATASET_POLICIES: dict[str, set[str]] = {
    "nasa_ims_bearing": {NASA_IMS_TEMPORAL_POLICY_V1},
}


def plan_dataset_pipeline_run(request: PipelineRunRequest) -> DatasetPipelinePlan:
    """Construye un plan trazable sin ejecutar transformaciones."""

    adapter = (
        get_dataset_adapter(request.adapter_id)
        if request.adapter_id is not None
        else infer_dataset_adapter(request.raw_path)
    )
    if not adapter.supports(Path(request.raw_path)):
        raise ValueError(
            "dataset adapter does not support path: "
            f"{adapter.info.adapter_id} -> {request.raw_path}"
        )
    if adapter.info.dataset_id != request.dataset_id:
        raise ValueError(
            "adapter/dataset mismatch: "
            f"adapter {adapter.info.adapter_id} targets {adapter.info.dataset_id}, "
            f"request targets {request.dataset_id}"
        )
    descriptor = describe_dataset(request.raw_path, adapter_id=adapter.info.adapter_id)
    if descriptor.dataset_id != request.dataset_id:
        raise ValueError(
            "descriptor/dataset mismatch: "
            f"descriptor {descriptor.dataset_id}, request {request.dataset_id}"
        )
    _validate_dataset_policy_id(request)
    policy = dataset_run_policy_for_request(request, adapter.info.display_name)
    effective_stages = _effective_stages(request)
    blocking_reasons = _blocking_reasons(policy, effective_stages)
    return DatasetPipelinePlan(
        request=request,
        adapter_info=adapter.info,
        descriptor=descriptor,
        policy=policy,
        paths=dataset_pipeline_paths(request),
        effective_stages=effective_stages,
        can_execute_requested_stages=not blocking_reasons,
        blocking_reasons=blocking_reasons,
    )


def dataset_run_policy_for_request(
    request: PipelineRunRequest,
    display_name: str | None = None,
) -> DatasetRunPolicy:
    """Devuelve la politica de capacidades para el dataset solicitado."""

    name = display_name or request.dataset_id
    if request.dataset_id == "cwru_bearing":
        return DatasetRunPolicy(
            dataset_id=request.dataset_id,
            adapter_id=request.adapter_id or "cwru_bearing",
            display_name=name,
            capabilities=[
                DatasetCapabilityRule(stage=stage, status="allowed")
                for stage in [*FULL_RUN_STAGES, "memory"]
            ],
            notes=[
                "CWRU se mantiene como benchmark de regresion con etiquetas "
                "compatibles con evaluacion supervisada local."
            ],
        )
    if request.dataset_id == "nasa_ims_bearing":
        return _nasa_policy(request, name)
    return DatasetRunPolicy(
        dataset_id=request.dataset_id,
        adapter_id=request.adapter_id or request.dataset_id,
        display_name=name,
        capabilities=[
            DatasetCapabilityRule(
                stage=stage,
                status="not_supported",
                reason="dataset is not wired into the common pipeline runner yet",
            )
            for stage in [*FULL_RUN_STAGES, "memory"]
        ],
        notes=["El adaptador puede existir, pero aun no hay politica de ejecucion."],
    )


def dataset_pipeline_paths(request: PipelineRunRequest) -> DatasetPipelinePaths:
    """Deriva rutas canonicas para una ejecucion."""

    dataset = request.dataset_id
    run_id = request.run_id
    return DatasetPipelinePaths(
        raw_path=request.raw_path,
        interim_dir=(Path("codigo/data/interim") / dataset / run_id).as_posix(),
        clean_dir=(
            Path("codigo/data/processed") / dataset / run_id / "clean_signals"
        ).as_posix(),
        tensor_dir=(Path("codigo/data/tensors") / dataset / run_id).as_posix(),
        model_dir=(Path("codigo/models") / dataset / run_id).as_posix(),
        evaluation_dir=(
            Path("codigo/reports") / dataset / run_id / "evaluation"
        ).as_posix(),
        memory_output_root=Path("codigo/reports").as_posix(),
    )


def build_initial_state_from_plan(plan: DatasetPipelinePlan) -> TFMState:
    """Crea el estado inicial comun a partir del plan validado."""

    request = plan.request
    if request.dataset_id == "cwru_bearing":
        return create_initial_cwru_state(
            thread_id=f"{request.run_id}-thread",
            run_id=request.run_id,
            raw_path=request.raw_path,
        )
    if request.dataset_id == "nasa_ims_bearing":
        return _nasa_initial_state(plan)
    raise ValueError(f"unsupported dataset for pipeline state: {request.dataset_id}")


def build_executors_from_plan(plan: DatasetPipelinePlan) -> PipelineExecutors:
    """Construye ejecutores deterministas parametrizados por dataset/run."""

    paths = plan.paths
    adapter_id = plan.adapter_info.adapter_id

    def manifest(raw_dir: str):
        result = generate_dataset_manifest(
            raw_dir,
            paths.interim_dir,
            adapter_id=adapter_id,
        )
        if (
            result.status == "success"
            and plan.request.dataset_id == "nasa_ims_bearing"
            and plan.request.dataset_policy_id == NASA_IMS_TEMPORAL_POLICY_V1
        ):
            return apply_nasa_ims_temporal_policy_to_result(
                result,
                paths.interim_dir,
            )
        return result

    def cleaning(manifest_path: str, profile_path: str, config: CleaningConfig):
        audit_path = Path(paths.clean_dir).parent / "cleaning_summary.json"
        return generate_clean_signals(
            manifest_path,
            profile_path,
            paths.clean_dir,
            config.model_copy(update={"audit_log_path": audit_path.as_posix()}),
        )

    return PipelineExecutors(
        manifest=manifest,
        profile=lambda manifest_path: generate_data_profile(
            manifest_path,
            Path(paths.interim_dir) / "profile.json",
        ),
        cleaning=cleaning,
        structuring=lambda clean_dir, config: generate_temporal_structure(
            clean_dir,
            paths.tensor_dir,
            config,
        ),
        modeling=lambda features_path, config: _modeling_executor(
            plan,
            features_path,
            config,
        ),
        evaluation=lambda predictions_path: generate_evaluation_report(
            predictions_path,
            paths.evaluation_dir,
        ),
        reporting=generate_technical_report,
    )


def run_dataset_pipeline(
    request: PipelineRunRequest,
    *,
    agents: PipelineAgents | None = None,
    runs_dir: str | Path = DEFAULT_RUNS_DIR,
    memory_config: PipelineMemoryConfig | None = None,
    human_approval: HumanApproval | None = None,
    runtime_recorder: AgentRuntimeRecorder | None = None,
) -> PersistedPipelineRun:
    """Ejecuta el pipeline comun si la politica permite las fases pedidas."""

    plan = plan_dataset_pipeline_run(request)
    if not plan.can_execute_requested_stages:
        raise ValueError(
            "requested pipeline stages are blocked: "
            + "; ".join(plan.blocking_reasons)
        )
    return run_and_persist_pipeline(
        _initial_state_with_execution_evidence(plan, human_approval),
        executors=build_executors_from_plan(plan),
        agents=_agents_for_plan(plan, agents),
        runs_dir=runs_dir,
        memory_config=memory_config,
        runtime_recorder=runtime_recorder,
    )


def _initial_state_with_execution_evidence(
    plan: DatasetPipelinePlan,
    human_approval: HumanApproval | None,
) -> TFMState:
    state = build_initial_state_from_plan(plan)
    updated = dict(state)
    artifacts = list(updated.get("artifacts") or [])
    artifacts.extend(
        artifact.model_dump(mode="json")
        for artifact in _write_pipeline_evidence_artifacts(plan)
    )
    updated["artifacts"] = artifacts
    if human_approval is not None:
        updated["human_approval"] = human_approval.model_dump(mode="json")
    return TFMState(**updated)


def _write_pipeline_evidence_artifacts(
    plan: DatasetPipelinePlan,
) -> list[ArtifactRef]:
    evidence_dir = (
        Path(plan.paths.memory_output_root)
        / plan.request.dataset_id
        / plan.request.run_id
        / "evidence"
    )
    evidence_dir.mkdir(parents=True, exist_ok=True)
    request_path = evidence_dir / "pipeline_request.json"
    plan_path = evidence_dir / "pipeline_plan.json"
    _write_json_file(request_path, plan.request.model_dump(mode="json"))
    _write_json_file(plan_path, plan.model_dump(mode="json"))
    return [
        ArtifactRef(
            name="pipeline_request",
            artifact_type="config",
            path=request_path.as_posix(),
            producer="pipeline_runner",
            description="Solicitud exacta recibida por el runner comun.",
            metadata={"schema": "PipelineRunRequest"},
        ),
        ArtifactRef(
            name="pipeline_plan",
            artifact_type="config",
            path=plan_path.as_posix(),
            producer="pipeline_runner",
            description="Plan preflight aplicado antes de ejecutar.",
            metadata={
                "schema": "DatasetPipelinePlan",
                "can_execute_requested_stages": plan.can_execute_requested_stages,
                "n_effective_stages": len(plan.effective_stages),
            },
        ),
    ]


def _write_json_file(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _nasa_policy(request: PipelineRunRequest, display_name: str) -> DatasetRunPolicy:
    supervised_allowed = (
        request.allow_synthetic_labels
        or request.dataset_policy_id == NASA_IMS_TEMPORAL_POLICY_V1
    )
    capabilities: list[DatasetCapabilityRule] = [
        DatasetCapabilityRule(stage="manifest", status="allowed"),
        DatasetCapabilityRule(stage="profiling", status="allowed"),
        DatasetCapabilityRule(stage="cleaning", status="allowed"),
        DatasetCapabilityRule(stage="structuring", status="allowed"),
        DatasetCapabilityRule(stage="reporting", status="allowed"),
        DatasetCapabilityRule(stage="memory", status="allowed"),
    ]
    if supervised_allowed:
        capabilities.extend(
            [
                DatasetCapabilityRule(stage="modeling", status="allowed"),
                DatasetCapabilityRule(stage="evaluation", status="allowed"),
            ]
        )
        if request.dataset_policy_id == NASA_IMS_TEMPORAL_POLICY_V1:
            notes = [
                "NASA IMS se permite en modo supervisado con politica temporal "
                "nasa_ims_temporal_v1: etiquetas proxy por orden temporal, no "
                "etiquetas oficiales NASA."
            ]
        else:
            notes = [
                "NASA IMS se permite en modo supervisado solo porque la peticion "
                "declara etiquetas sinteticas/controladas."
            ]
    else:
        capabilities.extend(
            [
                DatasetCapabilityRule(
                    stage="modeling",
                    status="blocked",
                    reason=NASA_MODELING_BLOCK_REASON,
                    requires_human_review=True,
                ),
                DatasetCapabilityRule(
                    stage="evaluation",
                    status="blocked",
                    reason=NASA_MODELING_BLOCK_REASON,
                    requires_human_review=True,
                ),
            ]
        )
        notes = [
            "NASA IMS real puede manifestarse, perfilarse, limpiarse y "
            "estructurarse, pero no pasar a evaluacion supervisada sin politica "
            "temporal y de etiquetas."
        ]
    return DatasetRunPolicy(
        dataset_id=request.dataset_id,
        adapter_id=request.adapter_id or "nasa_ims_bearing",
        display_name=display_name,
        capabilities=capabilities,
        notes=notes,
    )


def _validate_dataset_policy_id(request: PipelineRunRequest) -> None:
    if request.dataset_policy_id is None:
        return
    supported = SUPPORTED_DATASET_POLICIES.get(request.dataset_id, set())
    if request.dataset_policy_id not in supported:
        available = ", ".join(sorted(supported)) or "<none>"
        raise ValueError(
            "unsupported dataset_policy_id for "
            f"{request.dataset_id}: {request.dataset_policy_id}; "
            f"available: {available}"
        )


def _agents_for_plan(
    plan: DatasetPipelinePlan,
    agents: PipelineAgents | None,
) -> PipelineAgents | None:
    configured_agents = agents
    if configured_agents is None and plan.request.use_llm:
        configured_agents = build_ollama_pipeline_agents()
    if plan.request.execution_mode != "diagnostic":
        return configured_agents
    base = configured_agents or PipelineAgents()

    def supervisor(state: TFMStateModel) -> SupervisorDecision:
        if state.current_stage == _stage_after_diagnostic_cutoff(plan):
            return SupervisorDecision(
                decision_id=f"{state.run_id}:supervisor:{_supervisor_turn(state):03d}",
                current_stage=state.current_stage,
                next_stage="completed",
                next_node=None,
                requires_human_review=False,
                stop_reason=(
                    "diagnostic execution completed before blocked or "
                    "unrequested downstream stages"
                ),
                rationale=(
                    "Execution mode is diagnostic; manifest, profiling, "
                    "cleaning and structuring have already been reached."
                ),
                confidence=1.0,
            )
        return base.supervisor(state)

    return PipelineAgents(
        supervisor=supervisor,
        cleaner=base.cleaner,
        structurer=base.structurer,
        modeler=base.modeler,
        evaluator=base.evaluator,
        report_writer=base.report_writer,
        report_reviser=base.report_reviser,
        report_verifier=base.report_verifier,
    )


def _stage_after_diagnostic_cutoff(plan: DatasetPipelinePlan) -> str:
    if "structuring" in plan.effective_stages:
        return "modeling"
    if "cleaning" in plan.effective_stages:
        return "structuring"
    if "profiling" in plan.effective_stages:
        return "cleaning"
    return "profiling"


def _supervisor_turn(state: TFMStateModel) -> int:
    return 1 + sum(message.role == "supervisor" for message in state.messages)


def _effective_stages(request: PipelineRunRequest) -> list[PipelineRunStage]:
    if request.requested_stages is not None:
        stages = list(request.requested_stages)
    elif request.execution_mode == "diagnostic":
        stages = list(DIAGNOSTIC_RUN_STAGES)
    else:
        stages = list(FULL_RUN_STAGES)
    if request.use_memory and "memory" not in stages:
        stages.append("memory")
    return stages


def _blocking_reasons(
    policy: DatasetRunPolicy,
    stages: list[PipelineRunStage],
) -> list[str]:
    reasons: list[str] = []
    for stage in stages:
        status = policy.status_for(stage)
        if status == "allowed":
            continue
        reason = policy.reason_for(stage) or "stage is not allowed"
        reasons.append(f"{stage}: {reason}")
    return reasons


def _nasa_initial_state(plan: DatasetPipelinePlan) -> TFMState:
    request = plan.request
    descriptor = plan.descriptor
    main_channel = descriptor.channel_names[0] if descriptor.channel_names else "channel_1"
    target_rate = int(descriptor.sampling_rate_hz or 20000)
    if request.dataset_policy_id == NASA_IMS_TEMPORAL_POLICY_V1:
        objective = "binary_anomaly_detection"
        label_mode = "binary_anomaly"
        notes = (
            "NASA IMS run with temporal proxy policy nasa_ims_temporal_v1; "
            "labels and split hints are derived from chronological order and "
            "are not official NASA IMS annotations."
        )
    elif request.allow_synthetic_labels:
        objective = "binary_anomaly_detection"
        label_mode = "binary_anomaly"
        notes = (
            "NASA IMS synthetic-like run; labels are controlled by the local "
            "benchmark and are not official NASA IMS annotations."
        )
    else:
        objective = "run_to_failure_degradation"
        label_mode = "degradation"
        notes = (
            "NASA IMS real/preextracted run; supervised modeling remains blocked "
            "until temporal split and label policy are defined."
        )
    state = TFMStateModel(
        thread_id=f"{request.run_id}-thread",
        run_id=request.run_id,
        current_stage="dataset_manifest",
        next_node="manifest_executor",
        project_context=ProjectContext(
            dataset="nasa_ims_bearing",
            machine_type="rotating_machinery",
            signal_type="vibration",
            objective=objective,
            target_sample_rate_hz=target_rate,
            main_channel=main_channel,
            label_mode=label_mode,
            supervision_profile="run_to_failure_degradation",
            label_granularity=(
                "proxy_temporal"
                if request.dataset_policy_id == NASA_IMS_TEMPORAL_POLICY_V1
                else "file"
                if request.allow_synthetic_labels
                else "event"
            ),
            label_source=(
                "temporal_proxy"
                if request.dataset_policy_id == NASA_IMS_TEMPORAL_POLICY_V1
                else "synthetic"
                if request.allow_synthetic_labels
                else "none"
            ),
            notes=notes,
        ),
        raw_path=request.raw_path,
    )
    return TFMState(**state.to_langgraph_state())


def _modeling_executor(
    plan: DatasetPipelinePlan,
    features_path: str,
    config,
) -> ModelingResult:
    if plan.policy.status_for("modeling") != "allowed":
        return _blocked_modeling(plan)
    return generate_model_outputs(features_path, plan.paths.model_dir, config)


def _blocked_modeling(plan: DatasetPipelinePlan) -> ModelingResult:
    output = Path(plan.paths.model_dir)
    output.mkdir(parents=True, exist_ok=True)
    log_path = output / "modeling_blocked.json"
    reason = plan.policy.reason_for("modeling") or "modeling is blocked"
    payload = {
        "status": "blocked",
        "dataset": plan.request.dataset_id,
        "adapter_id": plan.adapter_info.adapter_id,
        "reason": reason,
        "required_action": "define_dataset_run_policy_before_modeling",
        "generated_at": datetime.now(UTC).isoformat(),
    }
    log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return ModelingResult(
        executor_name="modeling",
        status="failed",
        message="Modeling blocked by dataset run policy.",
        errors=[
            PipelineError(
                stage="modeling",
                node="modeling_executor",
                message=reason,
                recoverable=True,
            )
        ],
        model_path=log_path.as_posix(),
        predictions_path=None,
    )
