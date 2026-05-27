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


class StructuringAlternative(StrictBaseModel):
    """Alternativa comparable propuesta por el agente estructurador."""

    alternative_id: str = Field(min_length=1)
    structuring_config: StructuringConfig
    rationale: str = Field(min_length=1)
    expected_effect: str | None = None


MemoryRecordUseType = Literal[
    "followed",
    "adapted",
    "contradicted",
    "ignored",
]


class MemoryRecordUse(StrictBaseModel):
    """Declaracion del agente sobre como uso un recuerdo recuperado."""

    memory_record_id: str = Field(min_length=1)
    usage: MemoryRecordUseType
    influence_summary: str = Field(min_length=1)
    risk_mitigation: str | None = Field(default=None, min_length=1)


class StructuringDecision(AgentDecisionBase):
    """Decision del agente estructurador."""

    agent_name: Literal["structurer"] = "structurer"
    structuring_config: StructuringConfig
    expected_features_path: str = Field(min_length=1)
    expected_tensors_path: str | None
    expected_splits_path: str = Field(min_length=1)
    comparison_candidates: list[StructuringAlternative] = Field(default_factory=list)
    memory_context_id: str | None = Field(default=None, min_length=1)
    used_memory_context: bool = False
    memory_record_ids: list[str] = Field(default_factory=list)
    memory_usage_summary: str | None = Field(default=None, min_length=1)
    memory_record_uses: list[MemoryRecordUse] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_memory_declaration(self) -> "StructuringDecision":
        _validate_memory_usage_declaration(
            used_memory_context=self.used_memory_context,
            memory_context_id=self.memory_context_id,
            memory_record_ids=self.memory_record_ids,
            memory_usage_summary=self.memory_usage_summary,
            memory_record_uses=self.memory_record_uses,
        )
        return self


class ModelingDecision(AgentDecisionBase):
    """Decision del agente modelador."""

    agent_name: Literal["modeler"] = "modeler"
    modeling_config: ModelingConfig
    train_split: str = Field(default="train", min_length=1)
    validation_split: str | None = "validation"
    expected_model_path: str = Field(min_length=1)
    comparison_candidates: list["ModelingAlternative"] = Field(default_factory=list)


class ModelingAlternative(StrictBaseModel):
    """Alternativa comparable propuesta por el agente modelador."""

    alternative_id: str = Field(min_length=1)
    modeling_config: ModelingConfig
    rationale: str = Field(min_length=1)
    expected_effect: str | None = None


class ModelingRetryDecision(AgentDecisionBase):
    """Decision del modelador tras analizar una ejecucion fallida."""

    agent_name: Literal["modeler"] = "modeler"
    source_run_id: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    max_attempts: int = Field(ge=1)
    should_retry: bool
    learning_summary: str = Field(min_length=1)
    retry_config: ModelingConfig | None = None
    expected_effect: str | None = None
    stop_reason: str | None = None
    evidence_used: list[str] = Field(default_factory=list)
    memory_context_id: str | None = Field(default=None, min_length=1)
    used_memory_context: bool = False
    memory_record_ids: list[str] = Field(default_factory=list)
    memory_usage_summary: str | None = Field(default=None, min_length=1)
    memory_record_uses: list[MemoryRecordUse] = Field(default_factory=list)
    comparison_candidates: list[ModelingAlternative] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_retry_decision(self) -> "ModelingRetryDecision":
        if self.attempt_number > self.max_attempts:
            raise ValueError("attempt_number cannot exceed max_attempts")
        if self.should_retry:
            if self.retry_config is None:
                raise ValueError("retry decisions require retry_config")
            if not self.expected_effect:
                raise ValueError("retry decisions require expected_effect")
        elif not self.stop_reason:
            raise ValueError("stop decisions require stop_reason")
        if self.used_memory_context:
            if not self.memory_context_id:
                raise ValueError(
                    "retry decisions using memory require memory_context_id"
                )
            if not self.memory_record_ids:
                raise ValueError(
                    "retry decisions using memory require memory_record_ids"
                )
        if not self.used_memory_context and self.memory_record_ids:
            raise ValueError(
                "memory_record_ids require used_memory_context=true"
            )
        if len(set(self.memory_record_ids)) != len(self.memory_record_ids):
            raise ValueError("memory_record_ids cannot contain duplicates")
        declared_memory_ids = [item.memory_record_id for item in self.memory_record_uses]
        if len(set(declared_memory_ids)) != len(declared_memory_ids):
            raise ValueError("memory_record_uses cannot contain duplicate records")
        if not self.used_memory_context:
            if self.memory_usage_summary is not None or self.memory_record_uses:
                raise ValueError(
                    "memory usage declarations require used_memory_context=true"
                )
        return self


class EvaluationDecision(AgentDecisionBase):
    """Decision estructurada del evaluador."""

    agent_name: Literal["evaluator"] = "evaluator"
    evaluation: EvaluationResult
    min_recall_required: float | None = Field(default=None, ge=0.0, le=1.0)
    max_false_positive_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    memory_context_id: str | None = Field(default=None, min_length=1)
    used_memory_context: bool = False
    memory_record_ids: list[str] = Field(default_factory=list)
    memory_usage_summary: str | None = Field(default=None, min_length=1)
    memory_record_uses: list[MemoryRecordUse] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_memory_declaration(self) -> "EvaluationDecision":
        _validate_memory_usage_declaration(
            used_memory_context=self.used_memory_context,
            memory_context_id=self.memory_context_id,
            memory_record_ids=self.memory_record_ids,
            memory_usage_summary=self.memory_usage_summary,
            memory_record_uses=self.memory_record_uses,
        )
        return self


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


def _validate_memory_usage_declaration(
    *,
    used_memory_context: bool,
    memory_context_id: str | None,
    memory_record_ids: list[str],
    memory_usage_summary: str | None,
    memory_record_uses: list[MemoryRecordUse],
) -> None:
    if used_memory_context:
        if not memory_context_id:
            raise ValueError("decisions using memory require memory_context_id")
        if not memory_record_ids:
            raise ValueError("decisions using memory require memory_record_ids")
    if not used_memory_context:
        if memory_context_id is not None or memory_record_ids:
            raise ValueError("memory context declarations require used_memory_context=true")
        if memory_usage_summary is not None or memory_record_uses:
            raise ValueError("memory usage details require used_memory_context=true")
    if len(set(memory_record_ids)) != len(memory_record_ids):
        raise ValueError("memory_record_ids cannot contain duplicates")
    declared_memory_ids = [item.memory_record_id for item in memory_record_uses]
    if len(set(declared_memory_ids)) != len(declared_memory_ids):
        raise ValueError("memory_record_uses cannot contain duplicate records")
