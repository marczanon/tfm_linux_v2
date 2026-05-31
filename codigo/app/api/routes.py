"""Rutas de consulta sobre runs persistidos."""

from __future__ import annotations

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
    MemoryCollectionSummary,
    MemoryRecordSummary,
)
from codigo.app.schemas.api_llm import LLMStatusResponse
from codigo.app.schemas.api_runs import ApiRunJobStatus, ApiRunRequest, ApiRunResponse
from codigo.app.schemas.api_visualization import RunVisualizationData
from codigo.app.schemas.dataset import DatasetAdapterInfo
from codigo.app.schemas.pipeline_run import PipelineRunRequest
from codigo.app.schemas.reasoning import (
    AgentMemoryCollection,
    AgentMemoryTarget,
    MemoryRole,
    ReasoningMemoryRecord,
)
from codigo.app.schemas.state import HumanApproval
from codigo.app.schemas.state import TFMStateModel
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
)
from codigo.app.services.memory_registry import (
    get_memory_record,
    list_memory_collections,
    list_memory_records,
)
from codigo.app.services.llm import get_default_llm_status
from codigo.app.services.run_persistence import RunIndexEntry, RunSnapshot
from codigo.app.services.run_registry import (
    RunComparison,
    compare_runs,
    get_run,
    get_run_artifacts,
    list_runs,
)
from codigo.app.services.run_visualization import build_run_visualization


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
    }


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


@router.get("/memory/collections", response_model=list[MemoryCollectionSummary])
async def read_memory_collections(request: Request) -> list[MemoryCollectionSummary]:
    """Resume colecciones de memoria agentica persistida."""

    return list_memory_collections(_memory_dir(request))


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
    )


@router.get("/memory/records/{memory_record_id}", response_model=ReasoningMemoryRecord)
async def read_memory_record(
    memory_record_id: str,
    request: Request,
) -> ReasoningMemoryRecord:
    """Abre un recuerdo completo por `memory_record_id`."""

    try:
        return get_memory_record(_memory_dir(request), memory_record_id)
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

    _ensure_api_execution_is_allowed(api_request, plan.can_execute_requested_stages)
    _ensure_human_review_allows_execution(
        human_gate.execution_allowed,
        human_gate.blocking_reason,
    )
    if api_request.use_llm:
        _ensure_llm_execution_is_available()
    _ensure_run_id_is_available(api_request.run_id, _runs_dir(request))
    if api_request.background:
        _ensure_run_job_id_is_available(api_request.run_id, _run_job_store(request))
        job = _run_job_store(request).submit(
            api_request.run_id,
            _run_job_target(
                pipeline_request,
                _runs_dir(request),
                human_gate.approval,
                run_dataset_pipeline,
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
    api_request: ApiRunRequest,
    can_execute_requested_stages: bool,
) -> None:
    if not can_execute_requested_stages:
        raise HTTPException(
            status_code=409,
            detail="requested stages are blocked by dataset run policy",
        )
    if api_request.use_memory or (
        api_request.requested_stages is not None
        and "memory" in api_request.requested_stages
    ):
        raise HTTPException(
            status_code=400,
            detail="API execution with memory is not enabled yet",
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
):
    def target(runtime_recorder) -> RunSnapshot:
        result = runner(
            pipeline_request,
            runs_dir=runs_dir,
            human_approval=human_approval,
            runtime_recorder=runtime_recorder,
        )
        return result.snapshot

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
