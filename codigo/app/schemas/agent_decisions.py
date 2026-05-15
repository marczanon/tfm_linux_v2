"""Contratos de salida para agentes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, model_validator

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.state import (
    CleaningConfig,
    EvaluationResult,
    ModelingConfig,
    NodeName,
    PipelineStage,
    StructuringConfig,
)

AgentName = Literal[
    "supervisor",
    "cleaner",
    "structurer",
    "modeler",
    "evaluator",
    "report_writer",
]


class AgentDecisionBase(StrictBaseModel):
    """Campos comunes de una decision estructurada."""

    agent_name: AgentName
    decision_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SupervisorDecision(AgentDecisionBase):
    """Decision del supervisor sobre el siguiente nodo."""

    agent_name: Literal["supervisor"] = "supervisor"
    current_stage: PipelineStage
    next_stage: PipelineStage
    next_node: NodeName | None
    requires_human_review: bool = False
    stop_reason: str | None

    @model_validator(mode="after")
    def validate_terminal_decision(self) -> "SupervisorDecision":
        terminal = self.next_stage in {"completed", "failed"}
        if terminal and self.stop_reason is None:
            raise ValueError("terminal supervisor decisions require stop_reason")
        if not terminal and self.next_node is None:
            raise ValueError("non-terminal supervisor decisions require next_node")
        return self


class CleaningDecision(AgentDecisionBase):
    """Decision del agente limpiador."""

    agent_name: Literal["cleaner"] = "cleaner"
    cleaning_config: CleaningConfig
    expected_artifact_path: str = Field(min_length=1)
    warnings: list[str] = Field(default_factory=list)


class StructuringDecision(AgentDecisionBase):
    """Decision del agente estructurador."""

    agent_name: Literal["structurer"] = "structurer"
    structuring_config: StructuringConfig
    expected_features_path: str = Field(min_length=1)
    expected_tensors_path: str | None
    expected_splits_path: str = Field(min_length=1)


class ModelingDecision(AgentDecisionBase):
    """Decision del agente modelador."""

    agent_name: Literal["modeler"] = "modeler"
    modeling_config: ModelingConfig
    train_split: str = Field(default="train", min_length=1)
    validation_split: str | None = "validation"
    expected_model_path: str = Field(min_length=1)


class EvaluationDecision(AgentDecisionBase):
    """Decision estructurada del evaluador."""

    agent_name: Literal["evaluator"] = "evaluator"
    evaluation: EvaluationResult
    min_recall_required: float | None = Field(default=None, ge=0.0, le=1.0)
    max_false_positive_rate: float | None = Field(default=None, ge=0.0, le=1.0)


class ReportSection(StrictBaseModel):
    """Seccion solicitada al agente redactor."""

    title: str = Field(min_length=1)
    include_metrics: bool = False
    include_artifacts: bool = False
    source_paths: list[str] = Field(default_factory=list)


class ReportDecision(AgentDecisionBase):
    """Decision del agente redactor sobre el informe tecnico."""

    agent_name: Literal["report_writer"] = "report_writer"
    output_path: str = Field(min_length=1)
    output_format: Literal["markdown", "pdf", "latex"] = "markdown"
    sections: list[ReportSection] = Field(min_length=1)
