"""Registro local en memoria para ejecuciones API en segundo plano."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from threading import Lock, Thread

from codigo.app.schemas.agent_runtime import AgentRuntimeEvent
from codigo.app.schemas.api_runs import ApiRunJobStatus
from codigo.app.services.agent_runtime import AgentRuntimeRecorder
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
        target: Callable[[AgentRuntimeRecorder], RunSnapshot],
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

    def list_events(
        self,
        job_id: str,
        *,
        after_sequence: int | None = None,
    ) -> list[AgentRuntimeEvent] | None:
        """Devuelve eventos runtime de un job, opcionalmente desde una secuencia."""

        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if after_sequence is None:
                return list(job.events)
            return [
                event
                for event in job.events
                if event.sequence > after_sequence
            ]

    def run(
        self,
        job_id: str,
        target: Callable[[AgentRuntimeRecorder], RunSnapshot],
    ) -> None:
        """Ejecuta el trabajo registrado y captura su resultado o error."""

        recorder = AgentRuntimeRecorder(
            run_id=job_id,
            sink=lambda event: self._append_event(job_id, event),
        )
        recorder.emit(
            kind="job_status",
            source="job",
            title="Job en ejecucion",
            summary="La ejecucion en segundo plano ha empezado.",
            stage="initialized",
            node="api_run_job",
            payload={"status": "running"},
        )
        self._update(
            job_id,
            status="running",
            started_at=datetime.now(UTC),
            detail="run execution started",
        )
        try:
            snapshot = target(recorder)
        except Exception as exc:
            recorder.emit(
                kind="error",
                source="job",
                title="Job fallido",
                summary=f"{type(exc).__name__}: {exc}",
                stage="failed",
                node="api_run_job",
                payload={"exception_type": type(exc).__name__},
            )
            self._update(
                job_id,
                status="failed",
                finished_at=datetime.now(UTC),
                detail=f"{type(exc).__name__}: {exc}",
            )
            return
        recorder.emit(
            kind="job_status",
            source="job",
            title="Job completado",
            summary="La ejecucion en segundo plano ha terminado correctamente.",
            stage="completed",
            node="api_run_job",
            payload={"status": "completed", "snapshot_dir": snapshot.snapshot_dir},
        )
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

    def _append_event(
        self,
        job_id: str,
        event: AgentRuntimeEvent,
    ) -> ApiRunJobStatus:
        with self._lock:
            current = self._jobs.get(job_id)
            if current is None:
                raise ValueError(f"job_id not found: {job_id}")
            updated = current.model_copy(
                update={"events": [*current.events, event]}
            )
            self._jobs[job_id] = updated
            return updated
