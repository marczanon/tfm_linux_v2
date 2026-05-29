"""Registro local en memoria para ejecuciones API en segundo plano."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock, Thread

from codigo.app.schemas.api_runs import ApiRunJobStatus
from codigo.app.services.run_persistence import RunSnapshot


class ApiRunJobStore:
    """Estado en memoria de jobs API dentro del proceso FastAPI actual."""

    def __init__(self) -> None:
        self._jobs: dict[str, ApiRunJobStatus] = {}
        self._lock = Lock()

    def create(self, run_id: str) -> ApiRunJobStatus:
        """Registra una ejecucion pendiente y devuelve su estado inicial."""

        job_id = run_id
        with self._lock:
            if job_id in self._jobs:
                raise ValueError(f"job_id already exists: {job_id}")
            job = ApiRunJobStatus(
                job_id=job_id,
                run_id=run_id,
                status="queued",
            )
            self._jobs[job_id] = job
            return job

    def submit(
        self,
        run_id: str,
        target: Callable[[], RunSnapshot],
    ) -> ApiRunJobStatus:
        """Registra y lanza una ejecucion en un hilo daemon local."""

        job = self.create(run_id)
        thread = Thread(
            target=self.run,
            args=(job.job_id, target),
            daemon=True,
        )
        thread.start()
        return job

    def get(self, job_id: str) -> ApiRunJobStatus | None:
        """Devuelve el estado actual de un job, si existe."""

        with self._lock:
            return self._jobs.get(job_id)

    def run(
        self,
        job_id: str,
        target: Callable[[], RunSnapshot],
    ) -> None:
        """Ejecuta el trabajo registrado y captura su resultado o error."""

        self._update(
            job_id,
            status="running",
            started_at=datetime.now(UTC),
            detail="run execution started",
        )
        try:
            snapshot = target()
        except Exception as exc:
            self._update(
                job_id,
                status="failed",
                finished_at=datetime.now(UTC),
                detail=f"{type(exc).__name__}: {exc}",
            )
            return
        self._update(
            job_id,
            status="completed",
            finished_at=datetime.now(UTC),
            detail="run execution completed",
            snapshot=snapshot,
        )

    def _update(self, job_id: str, **changes) -> ApiRunJobStatus:
        with self._lock:
            current = self._jobs.get(job_id)
            if current is None:
                raise ValueError(f"job_id not found: {job_id}")
            updated = current.model_copy(update=changes)
            self._jobs[job_id] = updated
            return updated
