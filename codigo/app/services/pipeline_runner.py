"""Planificador y runner comun para ejecuciones multi-dataset."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
    run_monitoring_review_graph,
)
from codigo.app.graph.state import TFMState, create_initial_cwru_state
from codigo.app.agents.monitoring_reviewer import (
    monitoring_review_contract_fingerprints,
)
from codigo.app.schemas.agent_decisions import (
    AgentHypothesis,
    DecisionGenerationTrace,
    SupervisorDecision,
)
from codigo.app.schemas.dataset import DataProvenance
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
from codigo.app.schemas.monitoring_replay import (
    CausalEvidenceCatalog,
    CausalInputView,
    MONITORING_REVIEW_ROLES,
    MonitoringReviewDecision,
    MonitoringPolicyProposal,
    MonitoringReviewRequest,
    MonitoringReviewResult,
    MonitoringReviewRoleResult,
)
from codigo.app.services.dataset_adapters import (
    describe_dataset,
    get_dataset_adapter,
    infer_dataset_adapter,
)
from codigo.app.services.llm_agents import build_ollama_pipeline_agents
from codigo.app.services.nasa_ims_temporal_policy import (
    NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
    NASA_IMS_TEMPORAL_POLICY_V1,
    apply_nasa_ims_run_to_failure_policy_v2_to_result,
    apply_nasa_ims_temporal_policy_to_result,
)
from codigo.app.services.run_persistence import (
    DEFAULT_RUNS_DIR,
    RunSnapshot,
    save_monitoring_review_snapshot,
    serialized_json_sha256,
)
from codigo.app.services.agent_runtime import AgentRuntimeRecorder
from codigo.app.services.llm import JSONLLMClient
from codigo.app.services.monitoring_review_store import (
    build_causal_evidence_catalog,
    validate_causal_evidence_records,
)
from codigo.app.services.monitoring_policy_proposal import (
    build_monitoring_policy_proposal,
)


@dataclass(frozen=True)
class PersistedMonitoringReview:
    """Resultado del subgrafo causal y su run consultable por la aplicacion."""

    request: MonitoringReviewRequest
    result: MonitoringReviewResult
    decisions: tuple[MonitoringReviewDecision, ...]
    policy_proposal: MonitoringPolicyProposal
    snapshot: RunSnapshot

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
    "NASA IMS requiere declarar una politica temporal versionada o "
    "etiquetas sinteticas/controladas antes de modelado/evaluacion supervisados."
)
SUPPORTED_DATASET_POLICIES: dict[str, set[str]] = {
    "nasa_ims_bearing": {
        NASA_IMS_TEMPORAL_POLICY_V1,
        NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
    },
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
    _validate_dataset_policy_provenance(
        request,
        descriptor.data_provenance,
    )
    policy = dataset_run_policy_for_request(
        request,
        adapter.info.display_name,
        data_provenance=descriptor.data_provenance,
    )
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
    *,
    data_provenance: DataProvenance = "unknown",
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
        return _nasa_policy(request, name, data_provenance)
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
        ):
            if plan.request.dataset_policy_id == NASA_IMS_TEMPORAL_POLICY_V1:
                return apply_nasa_ims_temporal_policy_to_result(
                    result,
                    paths.interim_dir,
                )
            if (
                plan.request.dataset_policy_id
                == NASA_IMS_RUN_TO_FAILURE_POLICY_V2
            ):
                return apply_nasa_ims_run_to_failure_policy_v2_to_result(
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


def run_monitoring_review(
    request: MonitoringReviewRequest,
    causal_view: CausalInputView,
    evidence_records: list[dict[str, Any]],
    *,
    evidence_catalog: CausalEvidenceCatalog | None = None,
    runs_dir: str | Path = DEFAULT_RUNS_DIR,
    runtime_recorder: AgentRuntimeRecorder,
    llm_client: JSONLLMClient | None = None,
    use_llm: bool = True,
) -> PersistedMonitoringReview:
    """Ejecuta siete revisores sobre un prefijo ya validado, sin ejecutores/RAG."""

    if request.memory_mode != "off":
        raise ValueError("monitoring review v1 requires memory_mode=off")
    validate_causal_evidence_records(causal_view, evidence_records)
    effective_catalog = evidence_catalog or build_causal_evidence_catalog(
        causal_view,
        evidence_records,
    )
    if effective_catalog != build_causal_evidence_catalog(
        causal_view,
        evidence_records,
    ):
        raise ValueError("monitoring review evidence catalog does not match its view")
    expected_fingerprints = monitoring_review_contract_fingerprints(
        effective_catalog
    )
    if any(
        getattr(request, field) != value
        for field, value in expected_fingerprints.items()
    ):
        raise ValueError(
            "monitoring review request does not match the effective contract fingerprints"
        )
    if request.causal_view_sha256 != causal_view.view_sha256:
        raise ValueError("monitoring review request does not bind the causal view")
    if (
        request.session_id != causal_view.session_id
        or request.trigger_id != causal_view.trigger_id
        or request.trigger_event_id != causal_view.trigger_event_id
        or request.cutoff_cursor != causal_view.cursor
        or request.cutoff_source_time != causal_view.cutoff_source_time
    ):
        raise ValueError("monitoring review request/view causal envelope mismatch")
    graph_state = run_monitoring_review_graph(
        request=request,
        causal_view=causal_view,
        evidence_records=evidence_records,
        evidence_catalog=effective_catalog,
        runtime_recorder=runtime_recorder,
        llm_client=llm_client,
        use_llm=use_llm,
    )
    decisions = tuple(
        MonitoringReviewDecision.model_validate(item)
        for item in graph_state["decisions"]
    )
    runtime_ids = graph_state["runtime_event_ids"]
    role_results_list: list[MonitoringReviewRoleResult] = []
    for role in MONITORING_REVIEW_ROLES:
        decision = next(item for item in decisions if item.agent_name == role)
        fallback = decision.generation_trace.origin == "guardrail_fallback"
        role_results_list.append(
            MonitoringReviewRoleResult(
                agent_name=role,
                status="fallback" if fallback else "completed",
                decision=decision,
                runtime_event_ids=tuple(runtime_ids[role]),
                failure_reason=(
                    decision.generation_trace.fallback_cause if fallback else None
                ),
            )
        )
    role_results = tuple(role_results_list)
    fallback_roles = [
        item.agent_name for item in role_results if item.status == "fallback"
    ]
    policy_proposal = build_monitoring_policy_proposal(
        request=request,
        decisions=decisions,
        evidence_catalog=effective_catalog,
    )
    runtime_recorder.emit(
        kind="policy_proposal",
        source="system",
        title="Propuesta consultiva de politica",
        summary=_monitoring_policy_proposal_summary(policy_proposal),
        stage="monitoring_review",
        node="monitoring_policy_proposal",
        payload={
            "trace_origin": "deterministic_server",
            "review_kind": request.review_kind,
            "session_id": request.session_id,
            "trigger_id": request.trigger_id,
            "trigger_event_id": request.trigger_event_id,
            "cutoff_cursor": request.cutoff_cursor,
            "cutoff_snapshot_id": request.cutoff_snapshot_id,
            "causal_view_sha256": request.causal_view_sha256,
            "memory_mode": "off",
            "policy_application_status": "not_applied",
            "policy_proposal": policy_proposal.model_dump(mode="json"),
        },
    )
    events_payload = [
        event.model_dump(mode="json") for event in runtime_recorder.events
    ]
    runtime_events_ref = (
        Path(runs_dir)
        / request.child_run_id
        / "monitoring_review_events.json"
    ).as_posix()
    result_payload: dict[str, Any] = {
        "result_id": f"{request.child_run_id}:result",
        "request_id": request.request_id,
        "request_sha256": request.request_sha256,
        "child_run_id": request.child_run_id,
        "session_id": request.session_id,
        "trigger_id": request.trigger_id,
        "trigger_event_id": request.trigger_event_id,
        "origin_tick_id": request.origin_tick_id,
        "cutoff_snapshot_id": request.cutoff_snapshot_id,
        "cutoff_cursor": request.cutoff_cursor,
        "cutoff_source_time": request.cutoff_source_time,
        "active_policy_refs": request.active_policy_refs,
        "causal_view_ref": request.causal_view_ref,
        "causal_view_sha256": request.causal_view_sha256,
        "requested_roles": request.requested_roles,
        "required_roles": request.required_roles,
        "capabilities": request.capabilities,
        "role_results": role_results,
        "memory_mode": "off",
        "policy_application_status": "not_applied",
        "runtime_events_ref": runtime_events_ref,
        "runtime_events_sha256": serialized_json_sha256(events_payload),
        "status": "failed" if fallback_roles else "completed",
        "failure_reason": (
            "guardrail fallback observed in roles: " + ", ".join(fallback_roles)
            if fallback_roles
            else None
        ),
        "completed_at": datetime.now(UTC),
    }
    result_payload["result_sha256"] = MonitoringReviewResult.canonical_sha256(
        result_payload
    )
    result = MonitoringReviewResult.model_validate(result_payload)
    snapshot = save_monitoring_review_snapshot(
        request=request,
        result=result,
        decisions=list(decisions),
        runtime_events=runtime_recorder.events,
        evidence_catalog=effective_catalog,
        policy_proposal=policy_proposal,
        output_dir=runs_dir,
    )
    return PersistedMonitoringReview(
        request=request,
        result=result,
        decisions=decisions,
        policy_proposal=policy_proposal,
        snapshot=snapshot,
    )


def _monitoring_policy_proposal_summary(
    proposal: MonitoringPolicyProposal,
) -> str:
    """Rotulo determinista; no atribuye eficacia ni aplicacion a la sintesis."""

    if proposal.agreement_status == "invalid_review":
        return "Revision no elegible para sintesis agentiva; propuesta no aplicada."
    if proposal.agreement_status == "disagreement":
        return "Los siete roles discrepan; no se selecciona una accion agregada."
    action = (proposal.aggregate_action or "sin_accion").replace("_", " ")
    return f"Recomendacion unanime: {action}; propuesta consultiva no aplicada."


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
                "data_provenance": plan.descriptor.data_provenance,
            },
        ),
    ]


def _write_json_file(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _nasa_policy(
    request: PipelineRunRequest,
    display_name: str,
    data_provenance: DataProvenance,
) -> DatasetRunPolicy:
    supervised_allowed = (
        request.allow_synthetic_labels
        or request.dataset_policy_id == NASA_IMS_TEMPORAL_POLICY_V1
        or (
            request.dataset_policy_id == NASA_IMS_RUN_TO_FAILURE_POLICY_V2
            and data_provenance == "official"
        )
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
        if request.dataset_policy_id == NASA_IMS_RUN_TO_FAILURE_POLICY_V2:
            notes = [
                "NASA IMS oficial se ejecuta con la politica causal "
                "nasa_ims_run_to_failure_v2: baseline 20 %, calibracion 10 % "
                "y monitorizacion ciega 70 %, sin crear etiquetas de fallo "
                "por ventana."
            ]
        elif request.dataset_policy_id == NASA_IMS_TEMPORAL_POLICY_V1:
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
            "NASA IMS puede manifestarse, perfilarse, limpiarse y estructurarse, "
            "pero no pasar a evaluacion supervisada sin politica temporal y de "
            "etiquetas."
        ]
    notes.append(_nasa_data_provenance_policy_note(data_provenance))
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


def _validate_dataset_policy_provenance(
    request: PipelineRunRequest,
    data_provenance: DataProvenance,
) -> None:
    if (
        request.dataset_policy_id == NASA_IMS_RUN_TO_FAILURE_POLICY_V2
        and data_provenance != "official"
    ):
        raise ValueError(
            "nasa_ims_run_to_failure_v2 requires official data provenance; "
            f"received {data_provenance}"
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
            decision_id = (
                f"{state.run_id}:supervisor:{_supervisor_turn(state):03d}"
            )
            return SupervisorDecision(
                decision_id=decision_id,
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
                hypothesis=AgentHypothesis(
                    kind="routing_readiness",
                    statement=(
                        "La ejecucion diagnostica ya alcanzo su corte declarado y "
                        "puede cerrarse sin ejecutar fases no solicitadas."
                    ),
                    scope=(
                        f"Run {state.run_id}; modo diagnostic; etapa {state.current_stage}."
                    ),
                    evidence_cutoff=(
                        "Estado y artefactos producidos hasta el corte diagnostico."
                    ),
                    expected_observation=(
                        "La run termina como completed y no se invoca ninguna fase posterior."
                    ),
                    falsification_criterion=(
                        "Falta un artefacto obligatorio del corte, se ejecuta una fase "
                        "no solicitada o el cierre contradice el estado persistido."
                    ),
                    evidence_refs=["protocol:diagnostic_mode", "state:current_stage"],
                    risk_notes=[
                        "Completar un diagnostico no implica completar el pipeline integral."
                    ],
                    assumptions=[
                        "El alcance diagnostico esta declarado en la solicitud de la run."
                    ],
                ),
                generation_trace=DecisionGenerationTrace.for_decision(
                    decision_id,
                    origin="protocol_restricted",
                ),
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
    provenance_note = _nasa_data_provenance_policy_note(
        descriptor.data_provenance,
    )
    if request.dataset_policy_id == NASA_IMS_RUN_TO_FAILURE_POLICY_V2:
        objective = "run_to_failure_degradation"
        label_mode = "degradation"
        notes = (
            "NASA IMS official online-blind run with causal policy "
            "nasa_ims_run_to_failure_v2. Training uses only the initial "
            "baseline, threshold calibration uses only the following "
            "calibration partition, and the monitoring partition remains "
            "held out from agent decisions. No official per-window failure "
            f"labels are assumed. {provenance_note}"
        )
    elif request.dataset_policy_id == NASA_IMS_TEMPORAL_POLICY_V1:
        objective = "binary_anomaly_detection"
        label_mode = "binary_anomaly"
        notes = (
            "NASA IMS run with temporal proxy policy nasa_ims_temporal_v1; "
            "labels and split hints are derived from chronological order and "
            f"are not official NASA IMS annotations. {provenance_note}"
        )
    elif request.allow_synthetic_labels:
        objective = "binary_anomaly_detection"
        label_mode = "binary_anomaly"
        notes = (
            "NASA IMS synthetic-like run; labels are controlled by the local "
            f"benchmark and are not official NASA IMS annotations. {provenance_note}"
        )
    else:
        objective = "run_to_failure_degradation"
        label_mode = "degradation"
        notes = (
            "NASA IMS preextracted run; supervised modeling remains blocked until "
            f"temporal split and label policy are defined. {provenance_note}"
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
                "event"
                if request.dataset_policy_id == NASA_IMS_RUN_TO_FAILURE_POLICY_V2
                else "proxy_temporal"
                if request.dataset_policy_id == NASA_IMS_TEMPORAL_POLICY_V1
                else "file"
                if request.allow_synthetic_labels
                else "event"
            ),
            label_source=(
                "none"
                if request.dataset_policy_id == NASA_IMS_RUN_TO_FAILURE_POLICY_V2
                else "temporal_proxy"
                if request.dataset_policy_id == NASA_IMS_TEMPORAL_POLICY_V1
                else "synthetic"
                if request.allow_synthetic_labels
                else "none"
            ),
            data_provenance=descriptor.data_provenance,
            provenance_detection_method=descriptor.provenance_detection_method,
            provenance_evidence_path=descriptor.provenance_evidence_path,
            provenance_evidence_sha256=descriptor.provenance_evidence_sha256,
            notes=notes,
        ),
        raw_path=request.raw_path,
    )
    return TFMState(**state.to_langgraph_state())


def _nasa_data_provenance_policy_note(data_provenance: DataProvenance) -> str:
    if data_provenance == "synthetic":
        return (
            "Procedencia synthetic confirmada: las senales son un benchmark local "
            "tipo NASA IMS y no mediciones oficiales de NASA."
        )
    if data_provenance == "official":
        return "Procedencia official declarada con evidencia trazable."
    return (
        "Procedencia unknown: no presentar las senales como datos oficiales NASA "
        "hasta aportar evidencia de origen."
    )


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
