"""Contratos API para consultar memoria agentica persistida."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, NonNegativeInt, model_validator

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.dataset import DataProvenance
from codigo.app.schemas.reasoning import (
    AgentMemoryCollection,
    AgentMemoryTarget,
    HumanReasoningVerdict,
    MemoryRole,
    MemorySourceType,
    ReasoningMemoryRecord,
    ReasoningOutcome,
)


MemoryCandidateQueueStatus = Literal[
    "pending",
    "promoted",
    "stale_promotion",
    "excluded",
    "deleted",
    "reusable",
]

MemoryReadinessBlockerCode = Literal[
    "backend_unavailable",
    "empty_corpus",
    "no_reusable_memory",
    "no_official_provenance",
    "insufficient_dataset_coverage",
    "insufficient_agent_coverage",
    "candidate_queue_unavailable",
    "pending_candidates",
    "frozen_manifest_unavailable",
]


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
    data_provenance: DataProvenance = "unknown"
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


class MemoryCurationRequest(StrictBaseModel):
    """Operacion manual de gobierno sobre un recuerdo persistido."""

    action: Literal["exclude", "restore"]
    reason: str = Field(min_length=1, max_length=500)
    reviewer: str | None = Field(default=None, min_length=1, max_length=120)


class MemoryCandidateQueueItem(StrictBaseModel):
    """Vista trazable de un artefacto candidato pendiente de gobierno."""

    candidate_id: str = Field(min_length=1)
    memory_record_id: str = Field(min_length=1)
    target_agent: AgentMemoryTarget
    dataset: str | None = Field(default=None, min_length=1)
    data_provenance: DataProvenance = "unknown"
    memory_role: MemoryRole
    human_verdict: HumanReasoningVerdict | None = None
    status: MemoryCandidateQueueStatus
    current_governance_action: Literal[
        "exclude",
        "restore",
        "delete",
        "promote",
    ] | None = None
    summary: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    created_at: datetime


class MemoryCandidateQueueSummary(StrictBaseModel):
    """Contadores de estado de la cola manual de candidatos."""

    n_candidates: NonNegativeInt = 0
    n_pending: NonNegativeInt = 0
    n_promoted: NonNegativeInt = 0
    n_stale_promotions: NonNegativeInt = 0
    n_excluded: NonNegativeInt = 0
    n_deleted: NonNegativeInt = 0
    n_reusable: NonNegativeInt = 0


class MemoryCandidateQueueResponse(StrictBaseModel):
    """Listado completo y resumen de la cola de candidatos."""

    summary: MemoryCandidateQueueSummary
    candidates: list[MemoryCandidateQueueItem] = Field(default_factory=list)


class MemoryBackendStatus(StrictBaseModel):
    """Backend configurado y resultado de una sonda de lectura real."""

    configured_backend: str = Field(min_length=1, max_length=80)
    backend_name: str = Field(min_length=1, max_length=120)
    operational: bool
    embedding_model: str | None = Field(default=None, min_length=1, max_length=160)
    error_type: str | None = Field(default=None, min_length=1, max_length=120)
    diagnostic: str | None = Field(default=None, min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_availability_result(self) -> "MemoryBackendStatus":
        if self.operational and (
            self.error_type is not None or self.diagnostic is not None
        ):
            raise ValueError("an operational memory backend cannot expose an error")
        if not self.operational and (
            self.error_type is None or self.diagnostic is None
        ):
            raise ValueError("an unavailable memory backend requires an error diagnostic")
        return self


class MemoryCorpusStatus(StrictBaseModel):
    """Contenido util del corpus y estado independiente de su cola de candidatos."""

    available: bool
    total_records: NonNegativeInt = 0
    reusable_records: NonNegativeInt = 0
    official_records: NonNegativeInt = 0
    official_reusable_records: NonNegativeInt = 0
    shared_methodology_records: NonNegativeInt = 0
    shared_methodology_reusable_records: NonNegativeInt = 0
    corpus_fingerprint: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    frozen_manifest_available: bool = False
    reusable_dataset_coverage: list[str] = Field(default_factory=list)
    reusable_agent_coverage: list[AgentMemoryTarget] = Field(default_factory=list)
    n_reusable_datasets: NonNegativeInt = 0
    n_reusable_agents: NonNegativeInt = 0
    candidate_queue_available: bool
    pending_candidates: NonNegativeInt = 0
    candidate_queue_error_type: str | None = Field(
        default=None,
        min_length=1,
        max_length=120,
    )
    candidate_queue_diagnostic: str | None = Field(
        default=None,
        min_length=1,
        max_length=500,
    )

    @model_validator(mode="after")
    def validate_corpus_counts(self) -> "MemoryCorpusStatus":
        if not self.available and any(
            (
                self.total_records,
                self.reusable_records,
                self.official_records,
                self.official_reusable_records,
                self.shared_methodology_records,
                self.shared_methodology_reusable_records,
                self.n_reusable_datasets,
                self.n_reusable_agents,
            )
        ):
            raise ValueError("an unavailable corpus cannot report observed record counts")
        if not self.available and self.corpus_fingerprint is not None:
            raise ValueError("an unavailable corpus cannot expose a fingerprint")
        if self.reusable_records > self.total_records:
            raise ValueError("reusable_records cannot exceed total_records")
        if self.official_records > self.total_records:
            raise ValueError("official_records cannot exceed total_records")
        if self.official_reusable_records > self.reusable_records:
            raise ValueError("official_reusable_records cannot exceed reusable_records")
        if self.official_reusable_records > self.official_records:
            raise ValueError("official_reusable_records cannot exceed official_records")
        if self.shared_methodology_records > self.total_records:
            raise ValueError("shared_methodology_records cannot exceed total_records")
        if self.shared_methodology_reusable_records > self.reusable_records:
            raise ValueError(
                "shared_methodology_reusable_records cannot exceed reusable_records"
            )
        if (
            self.shared_methodology_reusable_records
            > self.shared_methodology_records
        ):
            raise ValueError(
                "shared_methodology_reusable_records cannot exceed "
                "shared_methodology_records"
            )
        if self.n_reusable_datasets != len(self.reusable_dataset_coverage):
            raise ValueError("n_reusable_datasets must match reusable_dataset_coverage")
        if self.n_reusable_agents != len(self.reusable_agent_coverage):
            raise ValueError("n_reusable_agents must match reusable_agent_coverage")
        if self.candidate_queue_available and (
            self.candidate_queue_error_type is not None
            or self.candidate_queue_diagnostic is not None
        ):
            raise ValueError("an available candidate queue cannot expose an error")
        if not self.candidate_queue_available and (
            self.candidate_queue_error_type is None
            or self.candidate_queue_diagnostic is None
        ):
            raise ValueError("an unavailable candidate queue requires an error diagnostic")
        return self


class MemoryScientificReadinessBlocker(StrictBaseModel):
    """Causa concreta que impide interpretar un benchmark del efecto de memoria."""

    code: MemoryReadinessBlockerCode
    message: str = Field(min_length=1, max_length=500)


class MemoryScientificReadiness(StrictBaseModel):
    """Precondiciones minimas para atribuir resultados al uso de memoria."""

    ready_for_memory_effect_benchmark: bool
    minimum_reusable_datasets: int = Field(default=2, ge=2)
    minimum_reusable_agents: int = Field(default=2, ge=2)
    blockers: list[MemoryScientificReadinessBlocker] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_readiness(self) -> "MemoryScientificReadiness":
        if self.ready_for_memory_effect_benchmark == bool(self.blockers):
            raise ValueError("readiness must be true exactly when there are no blockers")
        codes = [blocker.code for blocker in self.blockers]
        if len(codes) != len(set(codes)):
            raise ValueError("scientific readiness blocker codes must be unique")
        return self


class MemoryStatusResponse(StrictBaseModel):
    """Diagnostico no destructivo de disponibilidad y madurez de la memoria RAG."""

    backend: MemoryBackendStatus
    corpus: MemoryCorpusStatus
    scientific_readiness: MemoryScientificReadiness
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MemoryCandidateDecisionRequest(StrictBaseModel):
    """Decision manual explicita sobre un candidato sin mutar su artefacto."""

    action: Literal["promote", "exclude"]
    reason: str = Field(min_length=1, max_length=500)
    reviewer: str = Field(min_length=1, max_length=120)


class MemoryGovernanceEvent(StrictBaseModel):
    """Evento inmutable de gobierno manual sobre un recuerdo."""

    event_id: str = Field(min_length=1)
    memory_record_id: str = Field(min_length=1)
    action: Literal["exclude", "restore", "delete", "promote"]
    reason: str | None = Field(default=None, min_length=1, max_length=500)
    reviewer: str | None = Field(default=None, min_length=1, max_length=120)
    source_hash: str | None = Field(
        default=None,
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_manual_promotion(self) -> "MemoryGovernanceEvent":
        if self.action == "promote" and (self.reason is None or self.reviewer is None):
            raise ValueError("manual promotion requires reason and reviewer")
        return self


class MemoryGovernanceOverride(StrictBaseModel):
    """Estado vigente e historial auditable de un recuerdo gobernado."""

    memory_record_id: str = Field(min_length=1)
    current_action: Literal["exclude", "restore", "delete", "promote"]
    updated_at: datetime
    history: list[MemoryGovernanceEvent] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_history(self) -> "MemoryGovernanceOverride":
        if any(
            event.memory_record_id != self.memory_record_id
            for event in self.history
        ):
            raise ValueError("governance event IDs must match the governed record")
        latest = self.history[-1]
        if latest.action != self.current_action or latest.occurred_at != self.updated_at:
            raise ValueError("current governance state must match the latest event")
        return self


class MemoryGovernanceLedger(StrictBaseModel):
    """Overlay local que sobrevive a la reconstruccion del indice derivado."""

    schema_version: Literal["1.0"] = "1.0"
    overrides: list[MemoryGovernanceOverride] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_unique_records(self) -> "MemoryGovernanceLedger":
        record_ids = [override.memory_record_id for override in self.overrides]
        if len(record_ids) != len(set(record_ids)):
            raise ValueError("governance ledger cannot repeat memory record IDs")
        return self


class MemoryGovernanceApplication(StrictBaseModel):
    """Aplicacion de un override durante una indexacion concreta."""

    memory_record_id: str = Field(min_length=1)
    action: Literal["exclude", "restore", "delete", "promote"]
    effect: Literal[
        "excluded",
        "restored",
        "tombstoned",
        "promoted",
        "source_hash_mismatch",
        "restore_blocked_role_excluded",
    ]
    event_id: str = Field(min_length=1)
    occurred_at: datetime


class MemoryCurationResponse(StrictBaseModel):
    """Resultado de excluir, restaurar o borrar memoria."""

    memory_record_id: str = Field(min_length=1)
    action: Literal["exclude", "restore", "delete"]
    reason: str | None = None
    record: ReasoningMemoryRecord | None = None
    governance_event: MemoryGovernanceEvent | None = None


class MemoryCandidateDecisionResponse(StrictBaseModel):
    """Resultado de promover o excluir un candidato de memoria."""

    candidate: MemoryCandidateQueueItem
    action: Literal["promote", "exclude"]
    reason: str = Field(min_length=1)
    record: ReasoningMemoryRecord
    governance_event: MemoryGovernanceEvent
