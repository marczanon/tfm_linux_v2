"""Aplicacion FastAPI minima del MVP local."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import replace
import os
from pathlib import Path

from fastapi import FastAPI

from codigo.app.api.routes import router
from codigo.app.services.api_run_jobs import ApiRunJobStore
from codigo.app.services.reasoning_memory_index import (
    DEFAULT_MEMORY_DIR,
    DEFAULT_REPORTS_ROOT,
)
from codigo.app.services.monitoring_replay import (
    DEFAULT_MONITORING_SESSIONS_DIR,
    MonitoringReplayStore,
)
from codigo.app.services.monitoring_review_store import MonitoringReviewStore
from codigo.app.services.monitoring_review_reliability import (
    DEFAULT_MONITORING_REVIEW_RELIABILITY_OUTPUT_DIR,
)
from codigo.app.services.llm import (
    JSONLLMClient,
    OllamaJSONClient,
    get_default_json_llm_client,
)
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR
from codigo.app.services.vector_memory import VectorMemoryStore


@asynccontextmanager
async def _application_lifespan(application: FastAPI):
    """Reconcilia una vez los hilos locales que no sobrevivieron al reinicio."""

    job_store = application.state.run_job_store
    application.state.monitoring_review_reconciliation_errors = (
        application.state.monitoring_review_store.reconcile_orphaned_sessions(
            job_exists=lambda job_id: job_store.get(job_id) is not None,
        )
    )
    yield


def create_app(
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
    allowed_raw_roots: list[Path | str] | None = None,
    run_job_store: ApiRunJobStore | None = None,
    dataset_uploads_dir: Path | str | None = None,
    memory_dir: Path | str = DEFAULT_MEMORY_DIR,
    memory_store: VectorMemoryStore | None = None,
    reports_root: Path | str = DEFAULT_REPORTS_ROOT,
    monitoring_sessions_dir: Path | str = DEFAULT_MONITORING_SESSIONS_DIR,
    monitoring_replay_store: MonitoringReplayStore | None = None,
    monitoring_review_store: MonitoringReviewStore | None = None,
    monitoring_review_llm_client: JSONLLMClient | None = None,
    monitoring_review_use_llm: bool = True,
    monitoring_review_reliability_output_dir: Path | str = (
        DEFAULT_MONITORING_REVIEW_RELIABILITY_OUTPUT_DIR
    ),
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
        lifespan=_application_lifespan,
    )
    application.state.runs_dir = Path(runs_dir)
    application.state.allowed_raw_roots = raw_roots
    application.state.dataset_uploads_dir = uploads_dir
    application.state.run_job_store = run_job_store or ApiRunJobStore(
        events_root=Path(runs_dir)
    )
    application.state.memory_dir = Path(memory_dir)
    application.state.memory_store = memory_store
    application.state.reports_root = Path(reports_root)
    application.state.monitoring_replay_store = (
        monitoring_replay_store
        or MonitoringReplayStore(sessions_root=monitoring_sessions_dir)
    )
    application.state.monitoring_review_store = (
        monitoring_review_store
        or MonitoringReviewStore(
            sessions_root=application.state.monitoring_replay_store.sessions_root,
            runs_root=runs_dir,
        )
    )
    resolved_review_client = monitoring_review_llm_client
    if resolved_review_client is None and monitoring_review_use_llm:
        resolved_review_client = get_default_json_llm_client()
        if isinstance(resolved_review_client, OllamaJSONClient):
            resolved_review_client = replace(
                resolved_review_client,
                timeout_seconds=float(
                    os.getenv("TFM_MONITORING_REVIEW_TIMEOUT_SECONDS", "180")
                ),
                num_predict=int(
                    os.getenv("TFM_MONITORING_REVIEW_NUM_PREDICT", "2048")
                ),
            )
    application.state.monitoring_review_llm_client = resolved_review_client
    application.state.monitoring_review_use_llm = monitoring_review_use_llm
    application.state.monitoring_review_reliability_output_dir = Path(
        monitoring_review_reliability_output_dir
    )
    application.include_router(router)
    return application


app = create_app()
