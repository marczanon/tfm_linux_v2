"""Contratos de telemetria runtime para observabilidad agentica."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field, NonNegativeInt

from codigo.app.schemas.common import StrictBaseModel

AgentRuntimeEventKind = Literal[
    "job_status",
    "supervisor_decision",
    "agent_decision",
    "memory_retrieval",
    "executor_result",
    "policy_proposal",
    "error",
]

AgentRuntimeEventSource = Literal[
    "job",
    "supervisor",
    "agent",
    "memory",
    "executor",
    "system",
]


class AgentRuntimeEvent(StrictBaseModel):
    """Evento compacto para seguir una ejecucion agentica en tiempo real."""

    event_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    sequence: NonNegativeInt
    kind: AgentRuntimeEventKind
    source: AgentRuntimeEventSource
    title: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    stage: str | None = Field(default=None, min_length=1)
    node: str | None = Field(default=None, min_length=1)
    agent_name: str | None = Field(default=None, min_length=1)
    decision_id: str | None = Field(default=None, min_length=1)
    rationale: str | None = Field(default=None, min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    next_stage: str | None = Field(default=None, min_length=1)
    next_node: str | None = Field(default=None, min_length=1)
    memory_context_id: str | None = Field(default=None, min_length=1)
    memory_record_ids: list[str] = Field(default_factory=list)
    payload: dict[str, Any] = Field(default_factory=dict)
