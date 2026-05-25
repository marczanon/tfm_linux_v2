"""Rutas de consulta sobre runs persistidos."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse

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


def _get_run_or_404(run_id: str, runs_dir: Path) -> RunSnapshot:
    try:
        return get_run(run_id, runs_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"run not found: {run_id}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
