"""Rutas de consulta sobre runs persistidos."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import PlainTextResponse

from codigo.app.schemas.api_runs import ApiRunJobStatus, ApiRunRequest, ApiRunResponse
from codigo.app.schemas.pipeline_run import PipelineRunRequest
from codigo.app.schemas.state import HumanApproval
from codigo.app.schemas.state import TFMStateModel
from codigo.app.services.human_review import human_review_gate_for_plan
from codigo.app.services.api_run_jobs import ApiRunJobStore
from codigo.app.services.pipeline_runner import (
    plan_dataset_pipeline_run,
    run_dataset_pipeline,
)
from codigo.app.services.run_persistence import RunIndexEntry, RunSnapshot
from codigo.app.services.run_registry import (
    RunComparison,
    compare_runs,
    get_run,
    get_run_artifacts,
    list_runs,
)


router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict[str, str]:
    """Comprueba que la API esta disponible."""

    return {
        "status": "ok",
        "runs_dir": str(_runs_dir(request)),
    }


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
    if api_request.use_llm:
        raise HTTPException(
            status_code=400,
            detail="API execution with use_llm=true is not enabled yet",
        )
    if api_request.use_memory or (
        api_request.requested_stages is not None
        and "memory" in api_request.requested_stages
    ):
        raise HTTPException(
            status_code=400,
            detail="API execution with memory is not enabled yet",
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
    def target() -> RunSnapshot:
        result = runner(
            pipeline_request,
            runs_dir=runs_dir,
            human_approval=human_approval,
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
