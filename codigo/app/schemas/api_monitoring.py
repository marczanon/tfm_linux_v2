"""Contratos HTTP estrechos para el replay historico de monitorizacion."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field, NonNegativeInt, model_validator

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.agent_decisions import AgentName, DecisionValidationStatus
from codigo.app.schemas.monitoring_replay import (
    AgentActivationPolicyKind,
    MonitoringChildRunAttempt,
    MonitoringChildRunStatus,
    MonitoringReviewRecommendedAction,
    MonitoringReviewDispatchReceipt,
    MonitoringTriggerEvent,
    MonitoringTriggerLifecycle,
    MonitoringTriggerReasonCode,
    MonitoringTriggerType,
    MONITORING_REVIEW_ROLES,
    ReplayExperimentMode,
    ReplaySessionConfig,
    ReplaySessionState,
    ReplayStepReceipt,
    ReplayTick,
)


SAFE_MONITORING_ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,159}$"

MonitoringReviewGateOutcome = Literal[
    "first_pass",
    "llm_repaired",
    "fallback",
    "non_agentic",
    "error",
    "missing",
]
MonitoringReviewGateCoverageKind = Literal[
    "hypothesis_structure",
    "causal_grounding",
    "trigger_decision_result_binding",
]
MonitoringEvidenceCampaignStatus = Literal[
    "planned",
    "running",
    "completed",
    "interrupted",
    "failed",
]
MonitoringEvidenceCampaignPhase = Literal[
    "planned",
    "pre_roll",
    "agentic_window",
    "completed",
]
MonitoringEvidenceCampaignVerdict = Literal["pending", "passed", "blocked"]
MonitoringEvidenceCampaignReviewLifecycle = Literal[
    "pending",
    "running",
    "resolved",
    "failed",
    "interrupted",
]


class MonitoringReviewGateOutcomeCounts(StrictBaseModel):
    """Recuentos disjuntos del gate, incluidos los roles no observados."""

    expected_count: NonNegativeInt
    observed_count: NonNegativeInt
    first_pass_count: NonNegativeInt
    repaired_count: NonNegativeInt
    fallback_count: NonNegativeInt
    non_agentic_count: NonNegativeInt
    error_count: NonNegativeInt
    missing_count: NonNegativeInt

    @model_validator(mode="after")
    def validate_partition(self) -> "MonitoringReviewGateOutcomeCounts":
        observed = (
            self.first_pass_count
            + self.repaired_count
            + self.fallback_count
            + self.non_agentic_count
            + self.error_count
        )
        if observed != self.observed_count:
            raise ValueError("gate outcomes must partition observed_count")
        if self.observed_count + self.missing_count != self.expected_count:
            raise ValueError("observed and missing outcomes must partition expected_count")
        return self


class MonitoringReviewGateRoleSummary(StrictBaseModel):
    """Barra agregada para uno de los siete roles canonicos."""

    agent_name: AgentName
    outcomes: MonitoringReviewGateOutcomeCounts


class MonitoringReviewGateRoleResult(StrictBaseModel):
    """Franja visual de un rol dentro de una run hija concreta."""

    agent_name: AgentName
    outcome: MonitoringReviewGateOutcome
    validation_status: DecisionValidationStatus | None = None
    recommended_action: MonitoringReviewRecommendedAction | None = None

    @model_validator(mode="after")
    def validate_missing_role(self) -> "MonitoringReviewGateRoleResult":
        if self.outcome == "missing":
            if self.validation_status is not None or self.recommended_action is not None:
                raise ValueError("missing roles cannot expose a decision")
        elif self.outcome != "error" and self.recommended_action is None:
            raise ValueError("observed non-error roles require a recommended action")
        return self


class MonitoringReviewGateCase(StrictBaseModel):
    """Celda contexto por repeticion con enlace opcional a la run hija."""

    case_id: str = Field(min_length=1, max_length=400)
    context_id: str = Field(min_length=1, max_length=160)
    context_ordinal: int = Field(ge=1, le=4)
    repetition: int = Field(ge=1)
    trigger_type: MonitoringTriggerType
    reason_code: MonitoringTriggerReasonCode
    condition_start_cursor: NonNegativeInt
    cutoff_cursor: NonNegativeInt
    session_id: str | None = Field(default=None, min_length=1, max_length=160)
    trigger_id: str | None = Field(default=None, min_length=1, max_length=240)
    child_run_id: str | None = Field(default=None, min_length=1, max_length=240)
    child_lifecycle_status: MonitoringChildRunStatus | None = None
    bridge_lifecycle_status: MonitoringTriggerLifecycle | None = None
    observed_role_count: NonNegativeInt
    expected_role_count: NonNegativeInt
    role_results: tuple[MonitoringReviewGateRoleResult, ...] = Field(min_length=7)

    @model_validator(mode="after")
    def validate_role_projection(self) -> "MonitoringReviewGateCase":
        if tuple(item.agent_name for item in self.role_results) != MONITORING_REVIEW_ROLES:
            raise ValueError("gate case roles must use canonical order")
        observed = sum(item.outcome != "missing" for item in self.role_results)
        if observed != self.observed_role_count:
            raise ValueError("observed_role_count does not match role_results")
        if self.expected_role_count != len(self.role_results):
            raise ValueError("expected_role_count does not match role_results")
        linked = (self.session_id, self.trigger_id, self.child_run_id)
        if any(value is None for value in linked) and any(
            value is not None for value in linked
        ):
            raise ValueError("gate case run links must be all present or all absent")
        return self


class MonitoringReviewGateCoverage(StrictBaseModel):
    """Cobertura exacta; el frontend muestra siempre numerador y denominador."""

    kind: MonitoringReviewGateCoverageKind
    passed_count: NonNegativeInt
    expected_count: NonNegativeInt

    @model_validator(mode="after")
    def validate_coverage(self) -> "MonitoringReviewGateCoverage":
        if self.passed_count > self.expected_count:
            raise ValueError("coverage cannot exceed its expected count")
        return self


class MonitoringReviewGateView(StrictBaseModel):
    """Proyeccion visual del unico gate publicado mediante ``current.json``."""

    schema_version: Literal["monitoring_review_gate_view_v1"] = (
        "monitoring_review_gate_view_v1"
    )
    publication_status: Literal["published"] = "published"
    gate_id: str = Field(min_length=1, max_length=160)
    verdict: Literal["passed", "blocked"]
    blockers: tuple[str, ...] = ()
    completed_at: datetime
    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    memory_mode: Literal["off"] = "off"
    policy_application_status: Literal["not_applied"] = "not_applied"
    complete_repetition_count: NonNegativeInt
    expected_repetition_count: NonNegativeInt
    complete_context_count: NonNegativeInt
    expected_context_count: NonNegativeInt
    resolved_child_run_count: NonNegativeInt
    expected_child_run_count: NonNegativeInt
    outcomes: MonitoringReviewGateOutcomeCounts
    roles: tuple[MonitoringReviewGateRoleSummary, ...] = Field(min_length=7)
    cases: tuple[MonitoringReviewGateCase, ...]
    coverage: tuple[MonitoringReviewGateCoverage, ...] = Field(min_length=3)

    @model_validator(mode="after")
    def validate_visual_projection(self) -> "MonitoringReviewGateView":
        if tuple(item.agent_name for item in self.roles) != MONITORING_REVIEW_ROLES:
            raise ValueError("gate role summaries must use canonical order")
        expected_coverage = (
            "hypothesis_structure",
            "causal_grounding",
            "trigger_decision_result_binding",
        )
        if tuple(item.kind for item in self.coverage) != expected_coverage:
            raise ValueError("gate coverage must use canonical order")
        if len(self.cases) != (
            self.expected_repetition_count * self.expected_context_count
        ):
            raise ValueError("gate cases must project every planned matrix cell")
        return self


class MonitoringEvidenceCampaignReviewView(StrictBaseModel):
    """Un trigger primario y su expediente hijo dentro de la campaña."""

    context_id: str = Field(min_length=1)
    ordinal: int = Field(ge=1, le=4)
    trigger_type: MonitoringTriggerType
    reason_code: MonitoringTriggerReasonCode
    condition_start_cursor: NonNegativeInt
    cutoff_cursor: NonNegativeInt
    source_time: str = Field(min_length=1)
    lifecycle: MonitoringEvidenceCampaignReviewLifecycle
    trigger_id: str | None = None
    child_run_id: str | None = None
    decision_count: int = Field(ge=0, le=7)
    llm_origin_count: int = Field(ge=0, le=7)
    repaired_count: int = Field(ge=0, le=7)
    fallback_count: int = Field(ge=0, le=7)
    proposal_status: str | None = None
    proposal_application_status: str | None = None
    error: str | None = None


class MonitoringEvidenceCampaignView(StrictBaseModel):
    """Proyección visual estrecha de la campaña publicada y verificada."""

    schema_version: Literal["monitoring_evidence_campaign_view_v1"] = (
        "monitoring_evidence_campaign_view_v1"
    )
    publication_status: Literal["published"] = "published"
    publication_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    published_at: datetime
    registration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registered_at: datetime
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    campaign_id: str = Field(min_length=1, max_length=140)
    session_id: str = Field(min_length=1, max_length=160)
    status: MonitoringEvidenceCampaignStatus
    phase: MonitoringEvidenceCampaignPhase
    evidence_verdict: MonitoringEvidenceCampaignVerdict
    operational_verdict: MonitoringEvidenceCampaignVerdict
    agentic_verdict: MonitoringEvidenceCampaignVerdict
    current_revision: NonNegativeInt
    execution_cursor: NonNegativeInt | None = None
    progress_ratio: float = Field(ge=0.0, le=1.0)
    reviews: tuple[MonitoringEvidenceCampaignReviewView, ...] = Field(
        min_length=4,
        max_length=4,
    )
    observed_trigger_count: NonNegativeInt
    terminal_child_run_count: NonNegativeInt
    resolved_child_run_count: NonNegativeInt
    observed_decision_count: NonNegativeInt
    physical_attempt_count: NonNegativeInt
    llm_origin_decision_count: NonNegativeInt
    repaired_decision_count: NonNegativeInt
    fallback_count: NonNegativeInt
    policy_proposal_count: NonNegativeInt
    blockers: tuple[str, ...] = ()
    started_at: datetime | None = None
    updated_at: datetime
    completed_at: datetime | None = None
    runtime_elapsed_seconds: float = Field(ge=0.0)
    execution_mode: Literal["historical_replay_accelerated"]
    experiment_mode: Literal["frozen_benchmark"]
    memory_mode: Literal["off"]
    policy_application_status: Literal["not_applied"]
    expected_total_monitoring_ticks: Literal[689]
    pre_roll_start_cursor: Literal[0]
    pre_roll_end_cursor: Literal[352]
    agentic_window_start_cursor: Literal[353]
    agentic_window_end_cursor: Literal[688]
    agentic_window_source_start: Literal["2004-02-16T22:32:39"]
    agentic_window_source_end: Literal["2004-02-19T06:22:39"]
    agentic_window_source_duration_seconds: Literal[201000]
    source_timezone_status: Literal["not_declared"]
    speed_multiplier: float = Field(gt=0.0)
    expected_trigger_count: Literal[4]
    expected_child_run_count: Literal[4]
    expected_decision_count: Literal[28]
    expected_policy_proposal_count: Literal[4]

    @model_validator(mode="after")
    def validate_campaign_projection(self) -> "MonitoringEvidenceCampaignView":
        if tuple(item.ordinal for item in self.reviews) != (1, 2, 3, 4):
            raise ValueError("campaign reviews must use canonical ordinal order")
        bounded_counts = (
            (self.observed_trigger_count, self.expected_trigger_count),
            (self.terminal_child_run_count, self.expected_child_run_count),
            (self.resolved_child_run_count, self.expected_child_run_count),
            (self.observed_decision_count, self.expected_decision_count),
            (self.llm_origin_decision_count, self.expected_decision_count),
            (self.repaired_decision_count, self.expected_decision_count),
            (self.fallback_count, self.expected_decision_count),
            (
                self.policy_proposal_count,
                self.expected_policy_proposal_count,
            ),
        )
        if any(observed > expected for observed, expected in bounded_counts):
            raise ValueError("campaign observed counts cannot exceed the plan")
        return self


class MonitoringReplaySourceSummary(StrictBaseModel):
    """Escenario local registrado que puede alimentar una sesion."""

    scenario_id: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=240)
    dataset_id: str = Field(min_length=1, max_length=160)
    trajectory_id: str = Field(min_length=1, max_length=240)
    source_label: str = Field(min_length=1, max_length=240)
    available: bool
    unavailable_reason: str | None = None
    total_monitoring_ticks: NonNegativeInt
    modeled_channel_id: str = Field(min_length=1, max_length=160)
    channel_ids: tuple[str, ...] = Field(min_length=1)
    available_activation_policy_kinds: tuple[
        AgentActivationPolicyKind, ...
    ] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_availability(self) -> "MonitoringReplaySourceSummary":
        if self.available and self.unavailable_reason is not None:
            raise ValueError("available sources cannot declare unavailable_reason")
        if not self.available and self.unavailable_reason is None:
            raise ValueError("unavailable sources require unavailable_reason")
        if self.modeled_channel_id not in self.channel_ids:
            raise ValueError("modeled_channel_id must be present in channel_ids")
        if len(self.channel_ids) != len(set(self.channel_ids)):
            raise ValueError("channel_ids must be unique")
        if len(self.available_activation_policy_kinds) != len(
            set(self.available_activation_policy_kinds)
        ):
            raise ValueError(
                "available_activation_policy_kinds must be unique"
            )
        return self


class MonitoringSessionCreateRequest(StrictBaseModel):
    """Crea una sesion desde un escenario registrado, nunca desde rutas libres."""

    scenario_id: str = Field(pattern=SAFE_MONITORING_ID_PATTERN)
    session_id: str | None = Field(
        default=None,
        pattern=SAFE_MONITORING_ID_PATTERN,
    )
    activation_policy_kind: AgentActivationPolicyKind = "P0"
    experiment_mode: ReplayExperimentMode = "frozen_benchmark"


class MonitoringStepRequest(StrictBaseModel):
    """Body HTTP de step; el identificador de sesion procede de la URL."""

    command: Literal["step"] = "step"
    command_id: str = Field(pattern=SAFE_MONITORING_ID_PATTERN)
    expected_revision: NonNegativeInt


class MonitoringSessionView(StrictBaseModel):
    """Lectura coherente de una sesion y su ledger visible."""

    source: MonitoringReplaySourceSummary
    config: ReplaySessionConfig
    state: ReplaySessionState
    total_monitoring_ticks: NonNegativeInt
    ticks: tuple[ReplayTick, ...] = Field(default_factory=tuple)
    triggers: tuple[MonitoringTriggerEvent, ...] = Field(default_factory=tuple)
    child_revision: NonNegativeInt = 0
    child_runs: tuple[MonitoringChildRunAttempt, ...] = Field(default_factory=tuple)
    active_child_run_id: str | None = Field(default=None, min_length=1, max_length=240)

    @model_validator(mode="after")
    def validate_session_identity(self) -> "MonitoringSessionView":
        if self.config.session_id != self.state.session_id:
            raise ValueError("config and state must reference the same session")
        if any(tick.session_id != self.state.session_id for tick in self.ticks):
            raise ValueError("every tick must reference the viewed session")
        if any(event.session_id != self.state.session_id for event in self.triggers):
            raise ValueError("every trigger must reference the viewed session")
        if len(self.ticks) > self.total_monitoring_ticks:
            raise ValueError("ticks cannot exceed total_monitoring_ticks")
        if any(
            item.session_id != self.state.session_id for item in self.child_runs
        ):
            raise ValueError("every child run must reference the viewed session")
        expected_child_revision = max(
            (item.child_revision for item in self.child_runs),
            default=0,
        )
        if self.child_revision != expected_child_revision:
            raise ValueError(
                "child_revision must match the latest projected child run"
            )
        active_attempts = [
            item
            for item in self.child_runs
            if item.lifecycle_status in {"dispatched", "running"}
        ]
        if len(active_attempts) > 1:
            raise ValueError("a monitoring session can have at most one active child run")
        expected_active = active_attempts[0].child_run_id if active_attempts else None
        if self.active_child_run_id != expected_active:
            raise ValueError("active_child_run_id must match the child run ledger")
        return self


class MonitoringReviewDispatchRequest(StrictBaseModel):
    """Comando HTTP estrecho; el servidor resuelve vista, roles, hashes y run."""

    command_id: str = Field(pattern=SAFE_MONITORING_ID_PATTERN)
    expected_child_revision: NonNegativeInt


class MonitoringReviewDispatchResponse(StrictBaseModel):
    """Reserva durable devuelta antes de arrancar la inferencia en background."""

    receipt: MonitoringReviewDispatchReceipt
    attempt: MonitoringChildRunAttempt | None = None
    session: MonitoringSessionView

    @model_validator(mode="after")
    def validate_attempt_projection(self) -> "MonitoringReviewDispatchResponse":
        if self.attempt != self.receipt.attempt:
            raise ValueError("attempt must match the dispatch receipt projection")
        return self


class MonitoringChildRunListResponse(StrictBaseModel):
    """Intentos persistidos de una sesion, incluso tras reiniciar la API."""

    session_id: str = Field(pattern=SAFE_MONITORING_ID_PATTERN)
    child_revision: NonNegativeInt
    child_runs: tuple[MonitoringChildRunAttempt, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_child_projection(self) -> "MonitoringChildRunListResponse":
        if any(item.session_id != self.session_id for item in self.child_runs):
            raise ValueError("every child run must reference the listed session")
        expected_revision = max(
            (item.child_revision for item in self.child_runs),
            default=0,
        )
        if self.child_revision != expected_revision:
            raise ValueError(
                "child_revision must match the latest projected child run"
            )
        return self


class MonitoringStepResponse(StrictBaseModel):
    """Resultado compacto de avanzar un unico tick."""

    receipt: ReplayStepReceipt
    state: ReplaySessionState
    tick: ReplayTick | None = None
    triggers: tuple[MonitoringTriggerEvent, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_step_result(self) -> "MonitoringStepResponse":
        if self.receipt.session_id != self.state.session_id:
            raise ValueError("receipt and state must reference the same session")
        successful = self.receipt.outcome in {"applied", "idempotent_replay"}
        if successful:
            if self.tick is None or self.tick.tick_id != self.receipt.tick_id:
                raise ValueError("successful step responses require the committed tick")
        elif self.tick is not None:
            raise ValueError("rejected step responses cannot contain a tick")
        return self


class MonitoringTickListResponse(StrictBaseModel):
    """Lectura incremental del ledger para polling posterior."""

    session_id: str = Field(pattern=SAFE_MONITORING_ID_PATTERN)
    after_sequence: NonNegativeInt = 0
    ticks: tuple[ReplayTick, ...] = Field(default_factory=tuple)
    triggers: tuple[MonitoringTriggerEvent, ...] = Field(default_factory=tuple)
