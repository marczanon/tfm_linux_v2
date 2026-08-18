"""Rutas de consulta sobre runs persistidos."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse

from codigo.app.schemas.agent_runtime import AgentRuntimeEvent
from codigo.app.schemas.api_datasets import (
    DatasetDescribeRequest,
    DatasetDescribeResponse,
)
from codigo.app.schemas.api_memory import (
    MemoryCandidateDecisionRequest,
    MemoryCandidateDecisionResponse,
    MemoryCandidateQueueResponse,
    MemoryCurationRequest,
    MemoryCurationResponse,
    MemoryCollectionSummary,
    MemoryRecordSummary,
    MemoryStatusResponse,
)
from codigo.app.schemas.api_llm import LLMStatusResponse
from codigo.app.schemas.api_monitoring import (
    MonitoringChildRunListResponse,
    MonitoringReplaySourceSummary,
    MonitoringReviewGateCase,
    MonitoringReviewGateCoverage,
    MonitoringReviewGateOutcomeCounts,
    MonitoringReviewGateRoleResult,
    MonitoringReviewGateRoleSummary,
    MonitoringReviewGateView,
    MonitoringReviewDispatchRequest,
    MonitoringReviewDispatchResponse,
    MonitoringSessionCreateRequest,
    MonitoringSessionView,
    MonitoringStepRequest,
    MonitoringStepResponse,
    MonitoringTickListResponse,
)
from codigo.app.schemas.api_runs import ApiRunJobStatus, ApiRunRequest, ApiRunResponse
from codigo.app.schemas.api_visualization import RunVisualizationData
from codigo.app.schemas.dataset import DatasetAdapterInfo
from codigo.app.schemas.pipeline_run import PipelineRunRequest
from codigo.app.schemas.monitoring_replay import (
    MonitoringReviewDispatchCommand,
    ReplayStepCommand,
)
from codigo.app.schemas.reasoning import (
    AgentMemoryCollection,
    AgentMemoryTarget,
    MemoryRole,
    ReasoningMemoryRecord,
)
from codigo.app.schemas.state import HumanApproval
from codigo.app.schemas.state import TFMStateModel
from codigo.app.graph.pipeline import PipelineMemoryConfig
from codigo.app.services.human_review import human_review_gate_for_plan
from codigo.app.services.api_run_jobs import ApiRunJobStore
from codigo.app.services.dataset_adapters import (
    describe_dataset,
    get_dataset_adapter,
    infer_dataset_adapter,
    list_dataset_adapters,
)
from codigo.app.services.pipeline_runner import (
    plan_dataset_pipeline_run,
    run_dataset_pipeline,
    run_monitoring_review,
)
from codigo.app.agents.monitoring_reviewer import (
    monitoring_review_contract_fingerprints,
)
from codigo.app.services.memory_registry import (
    DuplicateMemoryCandidateError,
    UnsafeMemoryCandidatePathError,
    curate_memory_record,
    decide_memory_candidate,
    delete_memory_record,
    get_memory_status,
    get_memory_record,
    list_memory_collections,
    list_memory_candidate_queue,
    list_memory_records,
)
from codigo.app.services.llm import get_default_llm_status
from codigo.app.services.monitoring_replay import (
    MonitoringReplayError,
    MonitoringReplayConflictError,
    MonitoringReplayNotFoundError,
    MonitoringReplayStore,
    MonitoringReplayUnavailableError,
)
from codigo.app.services.monitoring_review_store import MonitoringReviewStore
from codigo.app.services.monitoring_review_reliability import (
    DEFAULT_MONITORING_REVIEW_RELIABILITY_OUTPUT_DIR,
    MonitoringReviewReliabilityObservation,
    MonitoringReviewReliabilityResult,
    load_published_monitoring_review_reliability,
)
from codigo.app.services.run_persistence import (
    RunIndexEntry,
    RunSnapshot,
    load_run_runtime_events,
)
from codigo.app.services.run_registry import (
    RunComparison,
    compare_runs,
    get_run,
    get_run_audit_report,
    get_run_artifacts,
    get_run_report_debate,
    list_runs,
)
from codigo.app.services.run_visualization import build_run_visualization
from codigo.app.services.vector_memory import get_default_vector_memory_store
from codigo.app.services.vector_memory import VectorMemoryStore


router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, Any]:
    """Comprueba que la API esta disponible."""

    return {
        "status": "ok",
        "runs_dir": str(_runs_dir(request)),
        "allowed_raw_roots": [root.as_posix() for root in _allowed_raw_roots(request)],
        "dataset_uploads_dir": _dataset_uploads_dir(request).as_posix(),
        "memory_dir": _memory_dir(request).as_posix(),
        "reports_root": _reports_root(request).as_posix(),
    }


@router.get(
    "/monitoring/sources",
    response_model=list[MonitoringReplaySourceSummary],
)
async def read_monitoring_sources(
    request: Request,
) -> list[MonitoringReplaySourceSummary]:
    """Lista escenarios locales registrados sin aceptar rutas arbitrarias."""

    return _monitoring_replay_store(request).list_sources()


@router.get(
    "/monitoring/review-gates/current",
    response_model=MonitoringReviewGateView,
)
async def read_current_monitoring_review_gate(
    request: Request,
) -> MonitoringReviewGateView:
    """Sirve solo el gate publicado por ``current.json`` y verifica sus hashes."""

    output_root = _monitoring_review_reliability_output_dir(request)
    if not (output_root / "current.json").is_file():
        raise HTTPException(
            status_code=404,
            detail="published monitoring review gate not found",
        )
    try:
        result = load_published_monitoring_review_reliability(
            output_root=output_root,
        )
        return _monitoring_review_gate_view(result)
    except (OSError, TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=409,
            detail="published monitoring review gate failed integrity verification",
        ) from exc


@router.post(
    "/monitoring/sessions",
    response_model=MonitoringSessionView,
    status_code=status.HTTP_201_CREATED,
)
async def create_monitoring_session(
    payload: MonitoringSessionCreateRequest,
    request: Request,
) -> MonitoringSessionView:
    """Crea una sesion manual con scoring y particiones congelados."""

    try:
        session = _monitoring_replay_store(request).create_session(
            scenario_id=payload.scenario_id,
            session_id=payload.session_id,
            activation_policy_kind=payload.activation_policy_kind,
            experiment_mode=payload.experiment_mode,
        )
        return _monitoring_review_store(request).decorate_session(session)
    except MonitoringReplayNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MonitoringReplayConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MonitoringReplayUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get(
    "/monitoring/sessions/{session_id}",
    response_model=MonitoringSessionView,
)
async def read_monitoring_session(
    session_id: str,
    request: Request,
) -> MonitoringSessionView:
    """Lee estado, ticks y triggers ya confirmados de una sesion."""

    try:
        session = _monitoring_replay_store(request).get_session(session_id)
        return _monitoring_review_store(request).decorate_session(session)
    except MonitoringReplayNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MonitoringReplayConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MonitoringReplayUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/monitoring/sessions/{session_id}/step",
    response_model=MonitoringStepResponse,
)
async def step_monitoring_session(
    session_id: str,
    payload: MonitoringStepRequest,
    request: Request,
) -> MonitoringStepResponse:
    """Avanza exactamente un tick usando CAS e idempotencia durable."""

    command = ReplayStepCommand(
        command_id=payload.command_id,
        session_id=session_id,
        expected_revision=payload.expected_revision,
    )
    try:
        return _monitoring_replay_store(request).step(
            command,
            before_apply=(
                _monitoring_review_store(
                    request
                ).assert_step_allowed_while_session_locked
            ),
        )
    except MonitoringReplayNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MonitoringReplayConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MonitoringReplayUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get(
    "/monitoring/sessions/{session_id}/ticks",
    response_model=MonitoringTickListResponse,
)
async def read_monitoring_ticks(
    session_id: str,
    request: Request,
    after_sequence: int = Query(default=0, ge=0),
) -> MonitoringTickListResponse:
    """Devuelve commits posteriores a una secuencia para polling incremental."""

    try:
        return _monitoring_replay_store(request).list_ticks(
            session_id,
            after_sequence=after_sequence,
        )
    except MonitoringReplayNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MonitoringReplayConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MonitoringReplayUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/monitoring/sessions/{session_id}/triggers/{trigger_id}/dispatch",
    response_model=MonitoringReviewDispatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def dispatch_monitoring_review(
    session_id: str,
    trigger_id: str,
    payload: MonitoringReviewDispatchRequest,
    request: Request,
) -> MonitoringReviewDispatchResponse:
    """Reserva y lanza una revision causal de siete agentes, memoria OFF."""

    review_store = _monitoring_review_store(request)
    replay_store = _monitoring_replay_store(request)
    try:
        session = replay_store.get_session(session_id)
        existing_command = review_store.get_dispatch_command(
            session_id,
            payload.command_id,
        )
        if existing_command is not None:
            command = existing_command
            if (
                command.expected_child_revision != payload.expected_child_revision
                or command.trigger_id != trigger_id
            ):
                raise MonitoringReplayConflictError(
                    "dispatch command_id was reused with another payload"
                )
            child_run_id = command.child_run_id
            review_request = review_store.load_review_request(
                session_id,
                command.request_sha256,
            )
        else:
            child_run_id = _monitoring_child_run_id(session_id, trigger_id)
            view = review_store.build_causal_view(session, trigger_id)
            evidence_catalog = review_store.load_evidence_catalog(
                session_id,
                view.view_sha256,
            )
            review_request = review_store.build_review_request(
                session,
                trigger_id,
                child_run_id=child_run_id,
                **monitoring_review_contract_fingerprints(evidence_catalog),
            )
            if _monitoring_review_use_llm(request):
                _ensure_llm_execution_is_available()
            command_payload: dict[str, Any] = {
                "command_id": payload.command_id,
                "session_id": session_id,
                "trigger_id": trigger_id,
                "trigger_event_id": review_request.trigger_event_id,
                "child_run_id": child_run_id,
                "job_id": child_run_id,
                "run_id": child_run_id,
                "attempt_no": 1,
                "expected_child_revision": payload.expected_child_revision,
                "request_ref": review_store.review_request_ref(
                    session_id,
                    child_run_id,
                ),
                "request_sha256": review_request.request_sha256,
                "causal_view_ref": review_request.causal_view_ref,
                "causal_view_sha256": review_request.causal_view_sha256,
                "issued_at": datetime.now(UTC),
            }
            command_payload["command_sha256"] = (
                MonitoringReviewDispatchCommand.canonical_sha256(command_payload)
            )
            command = MonitoringReviewDispatchCommand.model_validate(command_payload)
        receipt = review_store.reserve_dispatch(session, command)

        if receipt.outcome == "dispatched":
            try:
                _run_job_store(request).submit(
                    child_run_id,
                    _monitoring_review_job_target(
                        review_store=review_store,
                        review_request=review_request,
                        runs_dir=_runs_dir(request),
                        llm_client=_monitoring_review_llm_client(request),
                        use_llm=_monitoring_review_use_llm(request),
                    ),
                )
            except ValueError:
                # Otra peticion concurrente puede haber arrancado el mismo job
                # despues de que ambas leyesen el trigger. La reserva durable es
                # unica y el registro en memoria actua solo como lanzador local.
                if _run_job_store(request).get(child_run_id) is None:
                    review_store.mark_interrupted(
                        session_id,
                        child_run_id,
                        "the local background job could not be registered",
                    )
                    raise

        decorated = review_store.decorate_session(replay_store.get_session(session_id))
        return MonitoringReviewDispatchResponse(
            receipt=receipt,
            attempt=receipt.attempt,
            session=decorated,
        )
    except MonitoringReplayNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MonitoringReplayConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MonitoringReplayUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get(
    "/monitoring/sessions/{session_id}/child-runs",
    response_model=MonitoringChildRunListResponse,
)
async def read_monitoring_child_runs(
    session_id: str,
    request: Request,
) -> MonitoringChildRunListResponse:
    """Lista intentos hijos desde el ledger durable, no desde hilos en memoria."""

    try:
        session = _monitoring_replay_store(request).get_session(session_id)
        projection = _monitoring_review_store(request).project_session(session)
        return MonitoringChildRunListResponse(
            session_id=session_id,
            child_revision=projection.child_revision,
            child_runs=projection.attempts,
        )
    except MonitoringReplayNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except MonitoringReplayConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MonitoringReplayUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/llm/status", response_model=LLMStatusResponse)
async def read_llm_status() -> LLMStatusResponse:
    """Comprueba disponibilidad de Ollama para ejecuciones agenticas."""

    return LLMStatusResponse.model_validate(get_default_llm_status().__dict__)


@router.get("/datasets/adapters", response_model=list[DatasetAdapterInfo])
async def read_dataset_adapters() -> list[DatasetAdapterInfo]:
    """Lista adaptadores de dataset registrados en el backend."""

    return list_dataset_adapters()


@router.post("/datasets/describe", response_model=DatasetDescribeResponse)
async def describe_raw_dataset(
    describe_request: DatasetDescribeRequest,
    request: Request,
) -> DatasetDescribeResponse:
    """Describe una ruta raw permitida sin generar manifiestos ni transformar datos."""

    _ensure_raw_path_is_allowed(
        describe_request.raw_path,
        _allowed_raw_roots(request),
    )
    adapter = _dataset_adapter_or_http(
        describe_request.raw_path,
        describe_request.adapter_id,
    )
    try:
        descriptor = describe_dataset(
            describe_request.raw_path,
            adapter_id=adapter.info.adapter_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return DatasetDescribeResponse(
        adapter_info=adapter.info,
        descriptor=descriptor,
        allowed_raw_roots=[root.as_posix() for root in _allowed_raw_roots(request)],
        uploads_dir=_dataset_uploads_dir(request).as_posix(),
    )


@router.get("/memory/status", response_model=MemoryStatusResponse)
async def read_memory_status(request: Request) -> MemoryStatusResponse:
    """Expone disponibilidad y madurez cientifica sin escribir ni reindexar."""

    try:
        memory_store = _vector_memory_store(request)
    except Exception as exc:
        return get_memory_status(
            _memory_dir(request),
            _reports_root(request),
            backend_initialization_error=exc,
        )
    return get_memory_status(
        _memory_dir(request),
        _reports_root(request),
        memory_store=memory_store,
    )


@router.get("/memory/collections", response_model=list[MemoryCollectionSummary])
async def read_memory_collections(request: Request) -> list[MemoryCollectionSummary]:
    """Resume colecciones de memoria agentica persistida."""

    return list_memory_collections(
        _memory_dir(request),
        memory_store=_vector_memory_store(request),
    )


@router.get("/memory/candidates", response_model=MemoryCandidateQueueResponse)
async def read_memory_candidates(request: Request) -> MemoryCandidateQueueResponse:
    """Lista candidatos y su estado manual sin consultar solo el indice."""

    try:
        return list_memory_candidate_queue(
            _reports_root(request),
            _memory_dir(request),
        )
    except DuplicateMemoryCandidateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (UnsafeMemoryCandidatePathError, ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/memory/candidates/{candidate_id}/decision",
    response_model=MemoryCandidateDecisionResponse,
)
async def update_memory_candidate_decision(
    candidate_id: str,
    payload: MemoryCandidateDecisionRequest,
    request: Request,
) -> MemoryCandidateDecisionResponse:
    """Promueve o excluye por ID tras resolver el artefacto bajo reports_root."""

    try:
        return decide_memory_candidate(
            _reports_root(request),
            _memory_dir(request),
            candidate_id,
            action=payload.action,
            reason=payload.reason,
            reviewer=payload.reviewer,
            memory_store=_vector_memory_store(request),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except DuplicateMemoryCandidateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (UnsafeMemoryCandidatePathError, ValueError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/memory/records", response_model=list[MemoryRecordSummary])
async def read_memory_records(
    request: Request,
    collection_name: AgentMemoryCollection | None = None,
    target_agent: AgentMemoryTarget | None = None,
    dataset: str | None = None,
    memory_role: MemoryRole | None = None,
    reusable_only: bool = False,
    search_text: str | None = None,
) -> list[MemoryRecordSummary]:
    """Lista recuerdos filtrables sin reindexar memoria."""

    return list_memory_records(
        _memory_dir(request),
        collection_name=collection_name,
        target_agent=target_agent,
        dataset=dataset,
        memory_role=memory_role,
        reusable_only=reusable_only,
        search_text=search_text,
        memory_store=_vector_memory_store(request),
    )


@router.get("/memory/records/{memory_record_id}", response_model=ReasoningMemoryRecord)
async def read_memory_record(
    memory_record_id: str,
    request: Request,
) -> ReasoningMemoryRecord:
    """Abre un recuerdo completo por `memory_record_id`."""

    try:
        return get_memory_record(
            _memory_dir(request),
            memory_record_id,
            memory_store=_vector_memory_store(request),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch(
    "/memory/records/{memory_record_id}/curation",
    response_model=MemoryCurationResponse,
)
async def update_memory_record_curation(
    memory_record_id: str,
    payload: MemoryCurationRequest,
    request: Request,
) -> MemoryCurationResponse:
    """Excluye o restaura un recuerdo del contexto RAG reutilizable."""

    try:
        return curate_memory_record(
            _memory_dir(request),
            memory_record_id,
            action=payload.action,
            reason=payload.reason,
            reviewer=payload.reviewer,
            memory_store=_vector_memory_store(request),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/memory/records/{memory_record_id}",
    response_model=MemoryCurationResponse,
)
async def delete_memory_record_route(
    memory_record_id: str,
    request: Request,
    reason: str = Query(min_length=1, max_length=500),
    reviewer: str | None = Query(default=None, min_length=1, max_length=120),
) -> MemoryCurationResponse:
    """Borra un recuerdo y conserva un tombstone auditable."""

    try:
        return delete_memory_record(
            _memory_dir(request),
            memory_record_id,
            reason=reason,
            reviewer=reviewer,
            memory_store=_vector_memory_store(request),
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/runs", response_model=list[RunIndexEntry])
async def read_runs(
    request: Request,
    dataset: str | None = None,
    current_stage: str | None = None,
    approved: bool | None = Query(default=None),
) -> list[RunIndexEntry]:
    """Lista ejecuciones persistidas con filtros exactos opcionales."""

    return list_runs(
        _runs_dir(request),
        dataset=dataset,
        current_stage=current_stage,
        approved=approved,
    )


@router.post("/runs", response_model=ApiRunResponse)
async def create_run(
    api_request: ApiRunRequest,
    request: Request,
    response: Response,
) -> ApiRunResponse:
    """Planifica o ejecuta una run tras aplicar guardarrailes de API."""

    _ensure_raw_path_is_allowed(api_request.raw_path, _allowed_raw_roots(request))
    pipeline_request = PipelineRunRequest.model_validate(
        api_request.model_dump(
            exclude={"dry_run", "background", "human_review", "human_approval"}
        )
    )
    plan = _plan_or_http(pipeline_request)
    human_gate = human_review_gate_for_plan(
        plan,
        api_request.human_review,
        api_request.human_approval,
    )
    if api_request.dry_run:
        return _api_run_response(
            api_request,
            plan=plan,
            human_approval=human_gate.approval,
            human_review_reasons=human_gate.reasons,
            executed=False,
        )

    _ensure_api_execution_is_allowed(plan.can_execute_requested_stages)
    _ensure_human_review_allows_execution(
        human_gate.execution_allowed,
        human_gate.blocking_reason,
    )
    if api_request.use_llm:
        _ensure_llm_execution_is_available()
    _ensure_run_id_is_available(api_request.run_id, _runs_dir(request))
    memory_config = _api_memory_config(api_request, request, plan)
    if api_request.background:
        _ensure_run_job_id_is_available(api_request.run_id, _run_job_store(request))
        job = _run_job_store(request).submit(
            api_request.run_id,
            _run_job_target(
                pipeline_request,
                _runs_dir(request),
                human_gate.approval,
                run_dataset_pipeline,
                memory_config=memory_config,
            ),
        )
        response.status_code = status.HTTP_202_ACCEPTED
        return _api_run_response(
            api_request,
            plan=plan,
            human_approval=human_gate.approval,
            human_review_reasons=human_gate.reasons,
            executed=False,
            job=job,
        )
    result = run_dataset_pipeline(
        pipeline_request,
        runs_dir=_runs_dir(request),
        human_approval=human_gate.approval,
        memory_config=memory_config,
    )
    final_state = TFMStateModel.model_validate(result.state)
    return _api_run_response(
        api_request,
        plan=plan,
        executed=True,
        snapshot=result.snapshot,
        final_state=final_state,
        human_approval=final_state.human_approval or human_gate.approval,
        human_review_reasons=human_gate.reasons,
    )


@router.get("/run-jobs/{job_id}", response_model=ApiRunJobStatus)
async def read_run_job(job_id: str, request: Request) -> ApiRunJobStatus:
    """Devuelve el estado en memoria de una ejecucion API en segundo plano."""

    job = _run_job_store(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"run job not found: {job_id}")
    return job


@router.get("/run-jobs/{job_id}/events", response_model=list[AgentRuntimeEvent])
async def read_run_job_events(
    job_id: str,
    request: Request,
    after_sequence: int | None = Query(default=None, ge=0),
) -> list[AgentRuntimeEvent]:
    """Devuelve eventos de observabilidad agentica de un job en memoria."""

    events = _run_job_store(request).list_events(
        job_id,
        after_sequence=after_sequence,
    )
    if events is None:
        raise HTTPException(status_code=404, detail=f"run job not found: {job_id}")
    return events


@router.get("/runs/compare", response_model=RunComparison)
async def compare_persisted_runs(
    request: Request,
    run_ids: list[str] = Query(...),
) -> RunComparison:
    """Compara metricas principales entre ejecuciones persistidas."""

    try:
        return compare_runs(run_ids, _runs_dir(request))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs/{run_id}", response_model=RunSnapshot)
async def read_run(run_id: str, request: Request) -> RunSnapshot:
    """Devuelve la metadata persistida de una ejecucion."""

    return _get_run_or_404(run_id, _runs_dir(request))


@router.get("/runs/{run_id}/artifacts")
async def read_run_artifacts(run_id: str, request: Request) -> list[dict[str, Any]]:
    """Devuelve las referencias a artefactos de una ejecucion."""

    runs_dir = _runs_dir(request)
    _get_run_or_404(run_id, runs_dir)
    try:
        return get_run_artifacts(run_id, runs_dir)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/runs/{run_id}/events", response_model=list[AgentRuntimeEvent])
async def read_persisted_run_events(
    run_id: str,
    request: Request,
) -> list[AgentRuntimeEvent]:
    """Devuelve la traza historica persistida o su reconstruccion declarada."""

    try:
        return load_run_runtime_events(run_id, _runs_dir(request))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs/{run_id}/visualization", response_model=RunVisualizationData)
async def read_run_visualization(
    run_id: str,
    request: Request,
    max_points: int = Query(default=900, ge=50, le=2500),
) -> RunVisualizationData:
    """Devuelve metricas y proyeccion 2D compacta para una run persistida."""

    try:
        return build_run_visualization(
            run_id,
            _runs_dir(request),
            max_points=max_points,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/runs/{run_id}/report", response_class=PlainTextResponse)
async def read_run_report(run_id: str, request: Request) -> PlainTextResponse:
    """Devuelve el informe Markdown asociado a una ejecucion."""

    snapshot = _get_run_or_404(run_id, _runs_dir(request))
    if snapshot.report_path is None:
        raise HTTPException(status_code=404, detail=f"run has no report: {run_id}")

    report_path = Path(snapshot.report_path)
    if not report_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"report file not found for run: {run_id}",
        )
    try:
        content = report_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return PlainTextResponse(content, media_type="text/markdown")


@router.get("/runs/{run_id}/audit-report", response_class=PlainTextResponse)
async def read_run_audit_report(
    run_id: str,
    request: Request,
) -> PlainTextResponse:
    """Devuelve la auditoria humana de ejecucion separada del informe final."""

    try:
        content = get_run_audit_report(run_id, _runs_dir(request))
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"audit report not found for run: {run_id}",
        ) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return PlainTextResponse(content, media_type="text/markdown")


@router.get("/runs/{run_id}/report-debate", response_class=PlainTextResponse)
async def read_run_report_debate(
    run_id: str,
    request: Request,
) -> PlainTextResponse:
    """Devuelve el debate controlado del informe final."""

    try:
        content = get_run_report_debate(run_id, _runs_dir(request))
    except FileNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"report debate not found for run: {run_id}",
        ) from exc
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return PlainTextResponse(content, media_type="text/markdown")


def _runs_dir(request: Request) -> Path:
    return Path(request.app.state.runs_dir)


def _allowed_raw_roots(request: Request) -> list[Path]:
    roots = getattr(request.app.state, "allowed_raw_roots", [Path("codigo/data/raw")])
    return [Path(root) for root in roots]


def _run_job_store(request: Request) -> ApiRunJobStore:
    return request.app.state.run_job_store


def _dataset_uploads_dir(request: Request) -> Path:
    uploads_dir = getattr(
        request.app.state,
        "dataset_uploads_dir",
        Path("codigo/data/raw/uploads"),
    )
    return Path(uploads_dir)


def _memory_dir(request: Request) -> Path:
    return Path(getattr(request.app.state, "memory_dir", "codigo/reports/reasoning_memory"))


def _reports_root(request: Request) -> Path:
    return Path(getattr(request.app.state, "reports_root", "codigo/reports"))


def _monitoring_replay_store(request: Request) -> MonitoringReplayStore:
    return request.app.state.monitoring_replay_store


def _monitoring_review_store(request: Request) -> MonitoringReviewStore:
    return request.app.state.monitoring_review_store


def _monitoring_review_llm_client(request: Request):
    return getattr(request.app.state, "monitoring_review_llm_client", None)


def _monitoring_review_use_llm(request: Request) -> bool:
    return bool(getattr(request.app.state, "monitoring_review_use_llm", True))


def _monitoring_review_reliability_output_dir(request: Request) -> Path:
    return Path(
        getattr(
            request.app.state,
            "monitoring_review_reliability_output_dir",
            DEFAULT_MONITORING_REVIEW_RELIABILITY_OUTPUT_DIR,
        )
    )


def _monitoring_review_gate_view(
    result: MonitoringReviewReliabilityResult,
) -> MonitoringReviewGateView:
    """Reduce el resultado sellado a la proyeccion visual sin texto LLM."""

    plan = result.plan
    observations_by_case: dict[
        tuple[int, str], list[MonitoringReviewReliabilityObservation]
    ] = {}
    for item in result.observations:
        observations_by_case.setdefault(
            (item.repetition, item.context_id), []
        ).append(item)

    roles = tuple(
        MonitoringReviewGateRoleSummary(
            agent_name=role,
            outcomes=_monitoring_review_outcome_counts(
                [item for item in result.observations if item.agent_name == role],
                expected_count=(
                    plan.repetitions * len(plan.expected_contexts)
                ),
            ),
        )
        for role in plan.expected_roles
    )
    cases: list[MonitoringReviewGateCase] = []
    for context in plan.expected_contexts:
        for repetition in range(1, plan.repetitions + 1):
            observed = observations_by_case.get(
                (repetition, context.context_id),
                [],
            )
            by_role = {item.agent_name: item for item in observed}
            linked = observed[0] if observed else None
            bridge_lifecycle = (
                _bridge_lifecycle_status(linked.child_lifecycle_status)
                if linked is not None
                else None
            )
            cases.append(
                MonitoringReviewGateCase(
                    case_id=(
                        f"{plan.plan_id}:rep:{repetition:03d}:"
                        f"{context.context_id}"
                    ),
                    context_id=context.context_id,
                    context_ordinal=context.ordinal,
                    repetition=repetition,
                    trigger_type=context.trigger_type,
                    reason_code=context.reason_code,
                    condition_start_cursor=context.condition_start_cursor,
                    cutoff_cursor=context.cutoff_cursor,
                    session_id=None if linked is None else linked.session_id,
                    trigger_id=None if linked is None else linked.trigger_id,
                    child_run_id=None if linked is None else linked.child_run_id,
                    child_lifecycle_status=(
                        None if linked is None else linked.child_lifecycle_status
                    ),
                    bridge_lifecycle_status=bridge_lifecycle,
                    observed_role_count=len(observed),
                    expected_role_count=len(plan.expected_roles),
                    role_results=tuple(
                        _monitoring_review_gate_role_result(by_role.get(role), role)
                        for role in plan.expected_roles
                    ),
                )
            )

    expected = result.summary.expected_observation_count
    return MonitoringReviewGateView(
        gate_id=plan.plan_id,
        verdict=result.gate.verdict,
        blockers=result.gate.blockers,
        completed_at=result.manifest.completed_at,
        provider=result.manifest.llm_config.provider,
        model=result.manifest.llm_config.model,
        complete_repetition_count=result.summary.complete_repetition_count,
        expected_repetition_count=result.summary.expected_repetition_count,
        complete_context_count=result.summary.complete_context_count,
        expected_context_count=result.summary.expected_context_count,
        resolved_child_run_count=result.summary.resolved_child_run_count,
        expected_child_run_count=result.summary.expected_child_run_count,
        outcomes=_monitoring_review_outcome_counts(
            result.observations,
            expected_count=expected,
        ),
        roles=roles,
        cases=tuple(cases),
        coverage=(
            MonitoringReviewGateCoverage(
                kind="hypothesis_structure",
                passed_count=sum(
                    item.checks.hypothesis_structural_valid
                    for item in result.observations
                ),
                expected_count=expected,
            ),
            MonitoringReviewGateCoverage(
                kind="causal_grounding",
                passed_count=sum(
                    item.checks.grounding_valid for item in result.observations
                ),
                expected_count=expected,
            ),
            MonitoringReviewGateCoverage(
                kind="trigger_decision_result_binding",
                passed_count=sum(
                    item.checks.binding_valid for item in result.observations
                ),
                expected_count=expected,
            ),
        ),
    )


def _monitoring_review_outcome_counts(
    observations: list[MonitoringReviewReliabilityObservation]
    | tuple[MonitoringReviewReliabilityObservation, ...],
    *,
    expected_count: int,
) -> MonitoringReviewGateOutcomeCounts:
    def count(outcome: str) -> int:
        return sum(item.outcome == outcome for item in observations)

    observed_count = len(observations)
    return MonitoringReviewGateOutcomeCounts(
        expected_count=expected_count,
        observed_count=observed_count,
        first_pass_count=count("first_pass"),
        repaired_count=count("llm_repaired"),
        fallback_count=count("fallback"),
        non_agentic_count=count("non_agentic"),
        error_count=count("error"),
        missing_count=max(0, expected_count - observed_count),
    )


def _monitoring_review_gate_role_result(
    observation: MonitoringReviewReliabilityObservation | None,
    role: str,
) -> MonitoringReviewGateRoleResult:
    if observation is None:
        return MonitoringReviewGateRoleResult(
            agent_name=role,
            outcome="missing",
        )
    return MonitoringReviewGateRoleResult(
        agent_name=observation.agent_name,
        outcome=observation.outcome,
        validation_status=observation.generation_validation_status,
        recommended_action=observation.recommended_action,
    )


def _bridge_lifecycle_status(child_status: str) -> str:
    return {
        "dispatched": "dispatched",
        "running": "running",
        "resolved": "resolved",
        "failed": "failed",
        "interrupted": "failed",
    }[child_status]


def _vector_memory_store(request: Request) -> VectorMemoryStore:
    """Comparte un unico backend entre ejecucion RAG y gobierno de memoria."""

    store = getattr(request.app.state, "memory_store", None)
    if store is None:
        store = get_default_vector_memory_store(_memory_dir(request))
        request.app.state.memory_store = store
    return store


def _get_run_or_404(run_id: str, runs_dir: Path) -> RunSnapshot:
    try:
        return get_run(run_id, runs_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _plan_or_http(pipeline_request: PipelineRunRequest):
    try:
        return plan_dataset_pipeline_run(pipeline_request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _dataset_adapter_or_http(raw_path: str, adapter_id: str | None):
    try:
        adapter = (
            get_dataset_adapter(adapter_id)
            if adapter_id is not None
            else infer_dataset_adapter(raw_path)
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not adapter.supports(Path(raw_path)):
        raise HTTPException(
            status_code=400,
            detail=(
                f"dataset adapter does not support path: "
                f"{adapter.info.adapter_id} -> {raw_path}"
            ),
        )
    return adapter


def _ensure_raw_path_is_allowed(raw_path: str, allowed_roots: list[Path]) -> None:
    candidate = Path(raw_path).resolve(strict=False)
    roots = [root.resolve(strict=False) for root in allowed_roots]
    if not any(_is_relative_to(candidate, root) for root in roots):
        raise HTTPException(
            status_code=403,
            detail=(
                "raw_path is outside allowed API roots: "
                + ", ".join(root.as_posix() for root in roots)
            ),
        )


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _ensure_api_execution_is_allowed(
    can_execute_requested_stages: bool,
) -> None:
    if not can_execute_requested_stages:
        raise HTTPException(
            status_code=409,
            detail="requested stages are blocked by dataset run policy",
        )


def _api_memory_config(
    api_request: ApiRunRequest,
    request: Request,
    plan,
) -> PipelineMemoryConfig | None:
    """Conecta la peticion API con el ciclo RAG canonico del pipeline."""

    if not api_request.use_memory:
        return None
    return PipelineMemoryConfig(
        memory_store=_vector_memory_store(request),
        output_root=plan.paths.memory_output_root,
        # Las ejecuciones siempre capturan candidatos, pero no los promocionan
        # implicitamente antes de que el ciclo de calidad los valide.
        reusable_as_context=False,
    )


def _ensure_llm_execution_is_available() -> None:
    llm_status = get_default_llm_status()
    if not llm_status.available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=llm_status.detail or "Ollama is not available",
        )
    if not llm_status.model_available:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                llm_status.detail
                or f"Ollama model is not available: {llm_status.model}"
            ),
        )


def _ensure_human_review_allows_execution(
    execution_allowed: bool,
    blocking_reason: str | None,
) -> None:
    if not execution_allowed:
        raise HTTPException(
            status_code=409,
            detail=blocking_reason or "human review approval is required",
        )


def _ensure_run_id_is_available(run_id: str, runs_dir: Path) -> None:
    snapshot_path = runs_dir / run_id / "snapshot.json"
    if snapshot_path.exists():
        raise HTTPException(
            status_code=409,
            detail=f"run_id already exists: {run_id}",
        )


def _ensure_run_job_id_is_available(run_id: str, store: ApiRunJobStore) -> None:
    if store.get(run_id) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"run job already exists: {run_id}",
        )


def _run_job_target(
    pipeline_request: PipelineRunRequest,
    runs_dir: Path,
    human_approval: HumanApproval | None,
    runner,
    *,
    memory_config: PipelineMemoryConfig | None = None,
):
    def target(runtime_recorder) -> RunSnapshot:
        result = runner(
            pipeline_request,
            runs_dir=runs_dir,
            human_approval=human_approval,
            runtime_recorder=runtime_recorder,
            memory_config=memory_config,
        )
        return result.snapshot

    return target


def _monitoring_child_run_id(session_id: str, trigger_id: str) -> str:
    """Identidad acotada y estable: child_run_id == job_id == run_id."""

    digest = hashlib.sha256(
        f"{session_id}\x00{trigger_id}\x00attempt:1".encode("utf-8")
    ).hexdigest()[:24]
    return f"mon-review-{digest}"


def _monitoring_review_job_target(
    *,
    review_store: MonitoringReviewStore,
    review_request,
    runs_dir: Path,
    llm_client,
    use_llm: bool,
):
    """Adapta el runner propose-only al lanzador local no autoritativo."""

    def target(runtime_recorder) -> RunSnapshot:
        review_store.mark_running(
            review_request.session_id,
            review_request.child_run_id,
        )
        try:
            causal_view = review_store.load_causal_view(
                review_request.session_id,
                review_request.causal_view_sha256,
            )
            evidence_records = review_store.load_evidence_records(
                review_request.session_id,
                review_request.causal_view_sha256,
            )
            execution = run_monitoring_review(
                review_request,
                causal_view,
                evidence_records,
                runs_dir=runs_dir,
                runtime_recorder=runtime_recorder,
                llm_client=llm_client,
                use_llm=use_llm,
            )
            review_store.mark_terminal(
                review_request.session_id,
                review_request.child_run_id,
                execution.result,
            )
            if execution.result.status != "completed":
                raise RuntimeError(
                    execution.result.failure_reason
                    or "monitoring review did not pass the agentic gate"
                )
            return execution.snapshot
        except Exception as exc:
            try:
                review_store.mark_interrupted(
                    review_request.session_id,
                    review_request.child_run_id,
                    f"{type(exc).__name__}: {exc}",
                )
            except MonitoringReplayError:
                pass
            raise

    return target


def _api_run_response(
    api_request: ApiRunRequest,
    *,
    plan,
    executed: bool,
    snapshot: RunSnapshot | None = None,
    final_state: TFMStateModel | None = None,
    human_approval=None,
    human_review_reasons: list[str] | None = None,
    job: ApiRunJobStatus | None = None,
) -> ApiRunResponse:
    return ApiRunResponse(
        **api_request.model_dump(exclude={"human_approval"}),
        human_approval=human_approval,
        executed=executed,
        plan=plan,
        snapshot=snapshot,
        final_stage=None if final_state is None else final_state.current_stage,
        approved=(
            None
            if final_state is None or final_state.evaluation is None
            else final_state.evaluation.approved
        ),
        report_path=None if final_state is None else final_state.report_path,
        metrics=None if final_state is None else final_state.metrics,
        errors=(
            []
            if final_state is None
            else [error.message for error in final_state.errors]
        ),
        human_review_reasons=human_review_reasons or [],
        job=job,
    )
