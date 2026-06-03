"""Esquemas para auditar razonamiento agentico y revision humana."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, model_validator

from codigo.app.schemas.common import JsonScalar, StrictBaseModel

ReasoningOutcome = Literal[
    "validated",
    "supported",
    "partially_supported",
    "overcorrected",
    "contradicted",
    "inconclusive",
]

HumanReviewStatus = Literal[
    "not_requested",
    "pending_human_review",
    "reviewed",
]

HumanReasoningVerdict = Literal[
    "correct",
    "partially_correct",
    "incorrect",
    "unsafe",
    "needs_more_evidence",
]

HumanReviewMode = Literal["off", "passive", "required"]

AgentMemoryTarget = Literal[
    "cleaner",
    "structurer",
    "modeler",
    "evaluator",
    "report_writer",
    "researcher",
    "shared_methodology",
]

AgentMemoryCollection = Literal[
    "cleaner_memory",
    "structurer_memory",
    "modeler_memory",
    "evaluator_memory",
    "report_writer_memory",
    "researcher_memory",
    "shared_methodology_memory",
]

MemorySourceType = Literal[
    "decision_episode",
    "memory_candidate",
    "reasoning_postmortem",
    "human_review",
    "memory_usage_audit",
    "experiment_summary",
    "technical_documentation",
    "methodology_note",
]

MemoryRole = Literal[
    "positive_example",
    "negative_example",
    "boundary_case",
    "warning",
    "methodology",
    "evidence",
    "excluded",
]

MemoryRetrievalUse = Literal[
    "positive_context",
    "negative_warning",
    "boundary_context",
    "methodology_context",
    "evidence_context",
]

MemoryUsageAuditOutcome = Literal[
    "memory_not_used",
    "memory_aligned",
    "memory_repeated_boundary_failure",
    "memory_reasoning_inconsistent",
    "memory_ignored",
    "memory_contradicted",
    "inconclusive",
]

MemoryUsageAuditAssessment = Literal[
    "aligned",
    "repeated_boundary_failure",
    "reasoning_inconsistent",
    "ignored_retrieved_memory",
    "contradicted_memory",
    "uncited_retrieved_memory",
    "cited_without_retrieval",
    "not_applicable",
]

AgentToolName = Literal[
    "evidence_lookup",
    "temporal_health_lookup",
    "degradation_metrics_lookup",
    "threshold_analysis",
]

AgentToolAgent = Literal[
    "supervisor",
    "cleaner",
    "structurer",
    "modeler",
    "evaluator",
    "report_writer",
    "report_verifier",
    "researcher",
]

AgentToolEffect = Literal[
    "read_only",
    "writes_artifact",
    "requires_human_review",
]

AgentToolObservationStatus = Literal["success", "failed", "blocked"]

AgentToolArgumentValue = JsonScalar | list[JsonScalar]

DecisionEpisodeType = Literal[
    "cleaning",
    "structuring",
    "modeling",
    "evaluation",
    "reporting",
    "research",
    "supervision",
    "memory_management",
    "methodology",
]

ReportDebateStatus = Literal[
    "approved_without_revision",
    "approved_after_revision",
    "needs_human_review",
    "blocked",
    "inconclusive",
]

ReportDebateSpeaker = Literal["report_writer", "report_verifier", "system"]

ReportDebateTurnIntent = Literal[
    "draft",
    "verification",
    "revision",
    "reverification",
    "final_resolution",
]

ReportDebateTurnStatus = Literal[
    "informational",
    "accepted",
    "rejected",
    "verified",
    "unresolved",
]


class AgentToolSpec(StrictBaseModel):
    """Herramienta segura que un agente puede elegir como fuente de observacion."""

    tool_name: AgentToolName
    description: str = Field(min_length=1)
    allowed_agents: list[AgentToolAgent] = Field(min_length=1)
    effect: AgentToolEffect = "read_only"
    input_schema: dict[str, object] = Field(default_factory=dict)
    output_schema: dict[str, object] = Field(default_factory=dict)
    produces_artifacts: bool = False
    human_summary_template: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_tool_policy(self) -> "AgentToolSpec":
        if self.effect == "read_only" and self.produces_artifacts:
            raise ValueError("read-only tools cannot produce artifacts")
        if len(set(self.allowed_agents)) != len(self.allowed_agents):
            raise ValueError("allowed_agents cannot contain duplicates")
        return self


class AgentToolRequest(StrictBaseModel):
    """Solicitud estructurada de uso de una herramienta por parte de un agente."""

    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    agent_name: AgentToolAgent
    tool_name: AgentToolName
    purpose: str = Field(min_length=1)
    arguments: dict[str, AgentToolArgumentValue] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AgentToolObservation(StrictBaseModel):
    """Observacion devuelta por una herramienta agentica segura."""

    observation_id: str = Field(min_length=1)
    request_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    agent_name: AgentToolAgent
    tool_name: AgentToolName
    status: AgentToolObservationStatus
    summary: str = Field(min_length=1)
    evidence_refs: list[str] = Field(default_factory=list)
    payload: dict[str, object] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_observation_status(self) -> "AgentToolObservation":
        if self.status == "success" and self.errors:
            raise ValueError("successful tool observations cannot include errors")
        if self.status in {"failed", "blocked"} and not self.errors:
            raise ValueError("failed or blocked tool observations require errors")
        return self


class ReportDebateTurn(StrictBaseModel):
    """Turno legible y auditable de un debate controlado del informe."""

    turn_id: str = Field(min_length=1)
    round_index: int = Field(ge=0)
    speaker_agent: ReportDebateSpeaker
    source_decision_id: str | None = Field(default=None, min_length=1)
    intent: ReportDebateTurnIntent
    human_summary: str = Field(min_length=1)
    claims_or_objections: list[str] = Field(default_factory=list)
    accepted_points: list[str] = Field(default_factory=list)
    rejected_points: list[str] = Field(default_factory=list)
    changes_requested: list[str] = Field(default_factory=list)
    changes_applied: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    status: ReportDebateTurnStatus = "informational"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ReportDebateRecord(StrictBaseModel):
    """Registro completo del debate controlado del informe final."""

    debate_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    initial_report_decision_id: str = Field(min_length=1)
    initial_verifier_decision_id: str = Field(min_length=1)
    final_report_decision_id: str = Field(min_length=1)
    final_verifier_decision_id: str = Field(min_length=1)
    status: ReportDebateStatus
    max_rounds: int = Field(ge=0)
    rounds_used: int = Field(ge=0)
    turns: list[ReportDebateTurn] = Field(default_factory=list)
    final_summary: str = Field(min_length=1)
    unresolved_issues: list[str] = Field(default_factory=list)
    human_review_recommended: bool = False
    artifacts: list[dict[str, JsonScalar]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_debate_record(self) -> "ReportDebateRecord":
        if self.rounds_used > self.max_rounds:
            raise ValueError("rounds_used cannot exceed max_rounds")
        if self.status in {"needs_human_review", "blocked"} and not (
            self.unresolved_issues or self.human_review_recommended
        ):
            raise ValueError(
                "unresolved debate outcomes require unresolved issues or human review"
            )
        return self


class ReasoningMetricDelta(StrictBaseModel):
    """Cambio de una metrica antes y despues de una decision agentica."""

    metric: str = Field(min_length=1)
    before: float | None = None
    after: float | None = None
    delta: float | None = None
    higher_is_better: bool
    improved: bool | None = None


class AgentReasoningPostmortem(StrictBaseModel):
    """Post-mortem auditable de una hipotesis agentica y su resultado."""

    postmortem_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    source_run_id: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    max_attempts: int = Field(ge=1)
    hypothesis: str = Field(min_length=1)
    action_taken: str = Field(min_length=1)
    expected_effect: str | None = None
    evidence_used: list[str] = Field(default_factory=list)
    before_metrics: dict[str, float | None] = Field(default_factory=dict)
    after_metrics: dict[str, float | None] = Field(default_factory=dict)
    metric_deltas: list[ReasoningMetricDelta] = Field(default_factory=list)
    outcome: ReasoningOutcome
    automatic_critique: str = Field(min_length=1)
    reusable_lessons: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    human_review_status: HumanReviewStatus = "not_requested"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DecisionOption(StrictBaseModel):
    """Alternativa considerada por un agente antes de decidir."""

    option_id: str = Field(min_length=1)
    option_type: str = Field(min_length=1)
    description: str = Field(min_length=1)
    parameters: dict[str, JsonScalar] = Field(default_factory=dict)
    expected_effect: str | None = Field(default=None, min_length=1)
    risk_notes: list[str] = Field(default_factory=list)
    selected: bool = False


class DecisionEpisode(StrictBaseModel):
    """Episodio general de decision agentica reutilizable como memoria."""

    episode_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    target_agent: AgentMemoryTarget
    decision_type: DecisionEpisodeType
    dataset: str | None = Field(default=None, min_length=1)
    context_summary: str = Field(min_length=1)
    options_considered: list[DecisionOption] = Field(default_factory=list)
    chosen_action: str = Field(min_length=1)
    expected_effect: str | None = Field(default=None, min_length=1)
    evidence_used: list[str] = Field(default_factory=list)
    retrieved_memory_record_ids: list[str] = Field(default_factory=list)
    execution_result_summary: str | None = Field(default=None, min_length=1)
    before_metrics: dict[str, float | None] = Field(default_factory=dict)
    after_metrics: dict[str, float | None] = Field(default_factory=dict)
    metric_deltas: list[ReasoningMetricDelta] = Field(default_factory=list)
    tradeoffs_observed: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    outcome: ReasoningOutcome
    lesson_learned: str = Field(min_length=1)
    reusable_lessons: list[str] = Field(default_factory=list)
    when_to_reuse: list[str] = Field(default_factory=list)
    when_not_to_reuse: list[str] = Field(default_factory=list)
    risk_if_misused: str | None = Field(default=None, min_length=1)
    human_review_status: HumanReviewStatus = "not_requested"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_episode(self) -> "DecisionEpisode":
        option_ids = [option.option_id for option in self.options_considered]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("decision episode option_id values must be unique")
        selected_options = [option for option in self.options_considered if option.selected]
        if len(selected_options) > 1:
            raise ValueError("decision episodes can mark at most one selected option")
        if self.outcome in {"overcorrected", "contradicted"} and not self.failure_modes:
            raise ValueError(
                "failed or overcorrected episodes must describe failure_modes"
            )
        return self


class MemoryCandidate(StrictBaseModel):
    """Leccion destilada de un episodio, lista para indexacion vectorial."""

    candidate_id: str = Field(min_length=1)
    source_episode_id: str | None = Field(default=None, min_length=1)
    target_agent: AgentMemoryTarget
    source_type: MemorySourceType = "memory_candidate"
    run_id: str | None = Field(default=None, min_length=1)
    decision_id: str | None = Field(default=None, min_length=1)
    dataset: str | None = Field(default=None, min_length=1)
    source_agent_name: str | None = Field(default=None, min_length=1)
    outcome: ReasoningOutcome | None = None
    human_verdict: HumanReasoningVerdict | None = None
    memory_role: MemoryRole
    reusable_as_context: bool = False
    exclude_from_context: bool = False
    summary: str = Field(min_length=1)
    content: str = Field(min_length=1)
    when_to_reuse: list[str] = Field(default_factory=list)
    when_not_to_reuse: list[str] = Field(default_factory=list)
    risk_if_misused: str | None = Field(default=None, min_length=1)
    metrics: dict[str, float | None] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_candidate_policy(self) -> "MemoryCandidate":
        if self.reusable_as_context and self.exclude_from_context:
            raise ValueError(
                "memory candidates cannot be both reusable and excluded"
            )
        if self.memory_role == "excluded" and not self.exclude_from_context:
            raise ValueError("excluded memory candidates must set exclude_from_context")
        if self.reusable_as_context and not self.exclude_from_context:
            if not self.when_to_reuse:
                raise ValueError("reusable memory candidates require when_to_reuse")
        if self.memory_role in {"warning", "negative_example"}:
            if not self.when_not_to_reuse and self.risk_if_misused is None:
                raise ValueError(
                    "warning or negative memory candidates require avoidance guidance"
                )
        if self.memory_role == "positive_example":
            if not self.reusable_as_context:
                raise ValueError("positive memory candidates must be reusable")
            if self.human_verdict != "correct":
                raise ValueError(
                    "positive memory candidates require a correct human verdict"
                )
            if self.outcome in {"overcorrected", "contradicted"}:
                raise ValueError(
                    "unsafe or contradicted outcomes cannot be positive candidates"
                )
        return self


class HumanReasoningReviewRequest(StrictBaseModel):
    """Solicitud para que una persona etiquete el razonamiento de un agente."""

    request_id: str = Field(min_length=1)
    postmortem_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    human_review_mode: Literal["passive", "required"] = "passive"
    status: Literal["pending_human_review"] = "pending_human_review"
    reviewer_hint: str | None = None
    questions: list[str] = Field(default_factory=list)
    allowed_verdicts: list[HumanReasoningVerdict] = Field(
        default_factory=lambda: [
            "correct",
            "partially_correct",
            "incorrect",
            "unsafe",
            "needs_more_evidence",
        ]
    )
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HumanReasoningReview(StrictBaseModel):
    """Etiqueta humana validada para reutilizar o descartar razonamientos."""

    review_id: str = Field(min_length=1)
    request_id: str | None = Field(default=None, min_length=1)
    postmortem_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    reviewer: str = Field(min_length=1)
    verdict: HumanReasoningVerdict
    rationale: str = Field(min_length=1)
    reusable_as_context: bool = False
    exclude_from_context: bool = False
    tags: list[str] = Field(default_factory=list)
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_context_flags(self) -> "HumanReasoningReview":
        if self.reusable_as_context and self.exclude_from_context:
            raise ValueError(
                "human reviews cannot be both reusable and excluded from context"
            )
        return self


class HumanReviewSettings(StrictBaseModel):
    """Configuracion conmutable de Human-in-the-loop para una ejecucion."""

    mode: HumanReviewMode = "off"
    reviewer: str | None = Field(default=None, min_length=1)
    required_decision_points: list[str] = Field(default_factory=list)
    passive_artifacts_enabled: bool = True


class ReasoningMemoryRecord(StrictBaseModel):
    """Fragmento candidato a memoria agentica supervisada."""

    memory_record_id: str = Field(min_length=1)
    collection_name: AgentMemoryCollection
    target_agent: AgentMemoryTarget
    source_type: MemorySourceType
    source_path: str | None = Field(default=None, min_length=1)
    source_hash: str | None = Field(default=None, min_length=1)
    run_id: str | None = Field(default=None, min_length=1)
    postmortem_id: str | None = Field(default=None, min_length=1)
    decision_id: str | None = Field(default=None, min_length=1)
    dataset: str | None = Field(default=None, min_length=1)
    source_agent_name: str | None = Field(default=None, min_length=1)
    outcome: ReasoningOutcome | None = None
    human_verdict: HumanReasoningVerdict | None = None
    memory_role: MemoryRole
    reusable_as_context: bool = False
    exclude_from_context: bool = False
    summary: str = Field(min_length=1)
    content: str = Field(min_length=1)
    metrics: dict[str, float | None] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    embedding_model: str | None = Field(default=None, min_length=1)
    embedding_version: str | None = Field(default=None, min_length=1)
    embedding_dimension: int | None = Field(default=None, ge=1)
    vector_id: str | None = Field(default=None, min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_memory_policy(self) -> "ReasoningMemoryRecord":
        if self.reusable_as_context and self.exclude_from_context:
            raise ValueError(
                "memory records cannot be both reusable and excluded from context"
            )
        if self.memory_role == "excluded" and not self.exclude_from_context:
            raise ValueError("excluded memory records must set exclude_from_context")
        if self.memory_role == "positive_example":
            if not self.reusable_as_context:
                raise ValueError("positive memory examples must be reusable")
            if self.human_verdict != "correct":
                raise ValueError(
                    "positive memory examples require a correct human verdict"
                )
            if self.outcome in {"overcorrected", "contradicted"}:
                raise ValueError(
                    "unsafe or contradicted outcomes cannot be positive examples"
                )
        if self.human_verdict == "unsafe" and self.memory_role == "positive_example":
            raise ValueError("unsafe human verdicts cannot be positive examples")
        if self.outcome == "overcorrected" and self.memory_role == "positive_example":
            raise ValueError("overcorrected outcomes cannot be positive examples")
        return self


class AgentMemoryQuery(StrictBaseModel):
    """Consulta trazable contra una memoria vectorial de agente."""

    query_id: str = Field(min_length=1)
    target_agent: AgentMemoryTarget
    query_text: str = Field(min_length=1)
    dataset: str | None = Field(default=None, min_length=1)
    run_id: str | None = Field(default=None, min_length=1)
    decision_id: str | None = Field(default=None, min_length=1)
    decision_context: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict
    )
    allowed_memory_roles: list[MemoryRole] = Field(
        default_factory=lambda: [
            "positive_example",
            "negative_example",
            "boundary_case",
            "warning",
            "methodology",
            "evidence",
        ]
    )
    excluded_verdicts: list[HumanReasoningVerdict] = Field(
        default_factory=lambda: ["unsafe"]
    )
    top_k: int = Field(default=3, ge=1, le=10)
    min_similarity: float = Field(default=0.0, ge=0.0, le=1.0)
    human_review_mode: HumanReviewMode = "off"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_query_policy(self) -> "AgentMemoryQuery":
        if "excluded" in self.allowed_memory_roles:
            raise ValueError("queries cannot request excluded memory records")
        return self


class RetrievedMemoryItem(StrictBaseModel):
    """Registro recuperado con puntuacion y uso previsto en el prompt."""

    record: ReasoningMemoryRecord
    similarity: float = Field(ge=0.0, le=1.0)
    retrieval_use: MemoryRetrievalUse
    rank: int = Field(ge=1)

    @model_validator(mode="after")
    def validate_retrieval_use(self) -> "RetrievedMemoryItem":
        if self.record.exclude_from_context:
            raise ValueError("excluded memory records cannot be retrieved")
        if not self.record.reusable_as_context:
            raise ValueError("non-reusable memory records cannot be retrieved")
        if self.retrieval_use == "positive_context":
            if self.record.memory_role != "positive_example":
                raise ValueError(
                    "positive retrieval requires a positive memory example"
                )
            if self.record.human_verdict == "unsafe":
                raise ValueError("unsafe memory cannot be positive context")
        if self.record.memory_role == "warning" and self.retrieval_use != "negative_warning":
            raise ValueError("warning memory must be retrieved as negative_warning")
        if (
            self.record.memory_role == "boundary_case"
            and self.retrieval_use != "boundary_context"
        ):
            raise ValueError("boundary memory must be retrieved as boundary_context")
        return self


class RetrievedMemoryContext(StrictBaseModel):
    """Contexto RAG compacto que puede recibir un agente antes de decidir."""

    context_id: str = Field(min_length=1)
    query: AgentMemoryQuery
    items: list[RetrievedMemoryItem] = Field(default_factory=list)
    retrieval_backend: str | None = Field(default=None, min_length=1)
    embedding_model: str | None = Field(default=None, min_length=1)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_context(self) -> "RetrievedMemoryContext":
        if len(self.items) > self.query.top_k:
            raise ValueError("retrieved memory context exceeds query top_k")
        for item in self.items:
            record = item.record
            if record.target_agent not in {
                self.query.target_agent,
                "shared_methodology",
            }:
                raise ValueError("retrieved memory target does not match query agent")
            if record.memory_role not in self.query.allowed_memory_roles:
                raise ValueError("retrieved memory role is not allowed by query")
            if (
                record.human_verdict is not None
                and record.human_verdict in self.query.excluded_verdicts
            ):
                raise ValueError("retrieved memory verdict is excluded by query")
            if item.similarity < self.query.min_similarity:
                raise ValueError("retrieved memory similarity is below query minimum")
        return self


class MemoryUsageAuditItem(StrictBaseModel):
    """Auditoria de un recuerdo recuperado frente a la decision del agente."""

    memory_record_id: str = Field(min_length=1)
    retrieval_use: MemoryRetrievalUse | None = None
    memory_role: MemoryRole | None = None
    human_verdict: HumanReasoningVerdict | None = None
    memory_outcome: ReasoningOutcome | None = None
    cited_by_agent: bool = False
    declared_usage: str | None = Field(default=None, min_length=1)
    influence_summary: str | None = Field(default=None, min_length=1)
    risk_mitigation: str | None = Field(default=None, min_length=1)
    assessment: MemoryUsageAuditAssessment
    assessment_reason: str = Field(min_length=1)


class MemoryUsageAudit(StrictBaseModel):
    """Post-mortem especifico del uso de memoria RAG por un agente."""

    audit_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
    memory_context_id: str | None = Field(default=None, min_length=1)
    used_memory_context: bool = False
    memory_usage_summary: str | None = Field(default=None, min_length=1)
    retrieved_memory_record_ids: list[str] = Field(default_factory=list)
    cited_memory_record_ids: list[str] = Field(default_factory=list)
    uncited_retrieved_record_ids: list[str] = Field(default_factory=list)
    cited_without_retrieval: list[str] = Field(default_factory=list)
    before_metrics: dict[str, float | None] = Field(default_factory=dict)
    after_metrics: dict[str, float | None] = Field(default_factory=dict)
    outcome: MemoryUsageAuditOutcome
    summary: str = Field(min_length=1)
    items: list[MemoryUsageAuditItem] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
