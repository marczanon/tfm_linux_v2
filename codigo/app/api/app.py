"""Aplicacion FastAPI minima del MVP local."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from codigo.app.api.routes import router
from codigo.app.services.api_run_jobs import ApiRunJobStore
from codigo.app.services.reasoning_memory_index import DEFAULT_MEMORY_DIR
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR


def create_app(
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
    allowed_raw_roots: list[Path | str] | None = None,
    run_job_store: ApiRunJobStore | None = None,
    dataset_uploads_dir: Path | str | None = None,
    memory_dir: Path | str = DEFAULT_MEMORY_DIR,
) -> FastAPI:
    """Crea la API configurando el directorio local de ejecuciones."""

    raw_roots = [Path(root) for root in (allowed_raw_roots or [Path("codigo/data/raw")])]
    uploads_dir = Path(dataset_uploads_dir) if dataset_uploads_dir else raw_roots[0] / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    application = FastAPI(
        title="TFM Multiagente API",
        version="0.1.0",
        description=(
            "API minima para consultar ejecuciones persistidas del pipeline "
            "multiagente industrial."
        ),
    )
    application.state.runs_dir = Path(runs_dir)
    application.state.allowed_raw_roots = raw_roots
    application.state.dataset_uploads_dir = uploads_dir
    application.state.run_job_store = run_job_store or ApiRunJobStore()
    application.state.memory_dir = Path(memory_dir)
    application.include_router(router)
    return application


app = create_app()
