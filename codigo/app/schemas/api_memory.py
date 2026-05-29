"""Contratos API para consultar memoria agentica persistida."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, NonNegativeInt

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.reasoning import (
    AgentMemoryCollection,
    AgentMemoryTarget,
    HumanReasoningVerdict,
    MemoryRole,
    MemorySourceType,
    ReasoningOutcome,
)


class MemoryCollectionSummary(StrictBaseModel):
    """Resumen compacto de una coleccion vectorial de memoria."""

    collection_name: AgentMemoryCollection
    target_agent: AgentMemoryTarget
    n_records: NonNegativeInt = 0
    n_reusable: NonNegativeInt = 0
    n_excluded: NonNegativeInt = 0
    datasets: list[str] = Field(default_factory=list)
    memory_roles: dict[str, NonNegativeInt] = Field(default_factory=dict)
    source_types: dict[str, NonNegativeInt] = Field(default_factory=dict)
    human_verdicts: dict[str, NonNegativeInt] = Field(default_factory=dict)
    latest_created_at: datetime | None = None


class MemoryRecordSummary(StrictBaseModel):
    """Vista ligera de un registro de memoria para listados de UI."""

    memory_record_id: str = Field(min_length=1)
    collection_name: AgentMemoryCollection
    target_agent: AgentMemoryTarget
    source_type: MemorySourceType
    run_id: str | None = Field(default=None, min_length=1)
    decision_id: str | None = Field(default=None, min_length=1)
    dataset: str | None = Field(default=None, min_length=1)
    source_agent_name: str | None = Field(default=None, min_length=1)
    outcome: ReasoningOutcome | None = None
    human_verdict: HumanReasoningVerdict | None = None
    memory_role: MemoryRole
    reusable_as_context: bool
    exclude_from_context: bool
    summary: str = Field(min_length=1)
    source_path: str | None = Field(default=None, min_length=1)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime
