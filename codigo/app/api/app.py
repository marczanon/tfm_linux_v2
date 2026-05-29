"""Aplicacion FastAPI minima del MVP local."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from codigo.app.api.routes import router
from codigo.app.services.api_run_jobs import ApiRunJobStore
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR


def create_app(
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
    allowed_raw_roots: list[Path | str] | None = None,
    run_job_store: ApiRunJobStore | None = None,
) -> FastAPI:
    """Crea la API configurando el directorio local de ejecuciones."""

    application = FastAPI(
        title="TFM Multiagente API",
        version="0.1.0",
        description=(
            "API minima para consultar ejecuciones persistidas del pipeline "
            "multiagente industrial."
        ),
    )
    application.state.runs_dir = Path(runs_dir)
    application.state.allowed_raw_roots = [
        Path(root) for root in (allowed_raw_roots or [Path("codigo/data/raw")])
    ]
    application.state.run_job_store = run_job_store or ApiRunJobStore()
    application.include_router(router)
    return application


app = create_app()
