"""Registro ligero de eventos runtime para observar agentes y ejecutores."""

from __future__ import annotations

from collections.abc import Callable
from threading import Lock
from typing import Any

from codigo.app.schemas.agent_runtime import (
    AgentRuntimeEvent,
    AgentRuntimeEventKind,
    AgentRuntimeEventSource,
)

AgentRuntimeSink = Callable[[AgentRuntimeEvent], None]


class AgentRuntimeRecorder:
    """Crea eventos secuenciales y los entrega a un sink externo."""

    def __init__(self, run_id: str, sink: AgentRuntimeSink) -> None:
        self.run_id = run_id
        self._sink = sink
        self._sequence = 0
        self._lock = Lock()

    def emit(
        self,
        *,
        kind: AgentRuntimeEventKind,
        source: AgentRuntimeEventSource,
        title: str,
        summary: str,
        stage: str | None = None,
        node: str | None = None,
        agent_name: str | None = None,
        decision_id: str | None = None,
        rationale: str | None = None,
        confidence: float | None = None,
        next_stage: str | None = None,
        next_node: str | None = None,
        memory_context_id: str | None = None,
        memory_record_ids: list[str] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> AgentRuntimeEvent:
        """Construye, valida y publica un evento observable."""

        with self._lock:
            self._sequence += 1
            sequence = self._sequence
        event = AgentRuntimeEvent(
            event_id=f"{self.run_id}:runtime:{sequence:04d}",
            run_id=self.run_id,
            sequence=sequence,
            kind=kind,
            source=source,
            title=title,
            summary=summary,
            stage=stage,
            node=node,
            agent_name=agent_name,
            decision_id=decision_id,
            rationale=rationale,
            confidence=confidence,
            next_stage=next_stage,
            next_node=next_node,
            memory_context_id=memory_context_id,
            memory_record_ids=memory_record_ids or [],
            payload=payload or {},
        )
        self._sink(event)
        return event
