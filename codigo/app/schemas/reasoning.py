"""Esquemas para auditar razonamiento agentico y revision humana."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from codigo.app.schemas.common import StrictBaseModel

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


class HumanReasoningReviewRequest(StrictBaseModel):
    """Solicitud para que una persona etiquete el razonamiento de un agente."""

    request_id: str = Field(min_length=1)
    postmortem_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    decision_id: str = Field(min_length=1)
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
