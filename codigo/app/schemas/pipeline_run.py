"""Contratos para planificar ejecuciones multi-dataset."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.dataset import (
    DATASET_ID_PATTERN,
    DatasetAdapterInfo,
    DatasetDescriptor,
)

PipelineRunExecutionMode = Literal["full", "diagnostic"]
PipelineRunStage = Literal[
    "manifest",
    "profiling",
    "cleaning",
    "structuring",
    "modeling",
    "evaluation",
    "reporting",
    "memory",
]
PipelineCapabilityStatus = Literal["allowed", "blocked", "not_supported"]


class PipelineRunRequest(StrictBaseModel):
    """Solicitud explicita que puede emitir una API, CLI o interfaz grafica."""

    run_id: str = Field(min_length=1)
    dataset_id: str = Field(min_length=1, pattern=DATASET_ID_PATTERN)
    raw_path: str = Field(min_length=1)
    adapter_id: str | None = Field(default=None, min_length=1, pattern=DATASET_ID_PATTERN)
    dataset_policy_id: str | None = Field(
        default=None,
        min_length=1,
        pattern=DATASET_ID_PATTERN,
    )
    execution_mode: PipelineRunExecutionMode = "full"
    requested_stages: list[PipelineRunStage] | None = None
    use_memory: bool = False
    use_llm: bool = False
    allow_synthetic_labels: bool = False

    @model_validator(mode="after")
    def validate_request(self) -> "PipelineRunRequest":
        if "/" in self.run_id or "\\" in self.run_id:
            raise ValueError("run_id must be a plain identifier, not a path")
        if self.run_id in {".", ".."}:
            raise ValueError("run_id cannot be a relative path marker")
        if self.requested_stages is not None:
            if len(self.requested_stages) != len(set(self.requested_stages)):
                raise ValueError("requested_stages cannot contain duplicates")
            if "memory" in self.requested_stages and not self.use_memory:
                # La fase explicita es autoridad: evita que ejecucion, respuesta
                # y artefacto de solicitud discrepen sobre si hubo RAG.
                self.use_memory = True
        return self


class DatasetCapabilityRule(StrictBaseModel):
    """Estado de una fase del pipeline para un dataset concreto."""

    stage: PipelineRunStage
    status: PipelineCapabilityStatus
    reason: str | None = Field(default=None, min_length=1)
    requires_human_review: bool = False

    @model_validator(mode="after")
    def validate_reason(self) -> "DatasetCapabilityRule":
        if self.status != "allowed" and self.reason is None:
            raise ValueError("blocked or unsupported capabilities require reason")
        return self


class DatasetRunPolicy(StrictBaseModel):
    """Politica de capacidades que el backend debe aplicar aunque exista UI."""

    dataset_id: str = Field(min_length=1, pattern=DATASET_ID_PATTERN)
    adapter_id: str = Field(min_length=1, pattern=DATASET_ID_PATTERN)
    display_name: str = Field(min_length=1)
    capabilities: list[DatasetCapabilityRule] = Field(min_length=1)
    notes: list[str] = Field(default_factory=list)

    def status_for(self, stage: PipelineRunStage) -> PipelineCapabilityStatus:
        for capability in self.capabilities:
            if capability.stage == stage:
                return capability.status
        return "not_supported"

    def reason_for(self, stage: PipelineRunStage) -> str | None:
        for capability in self.capabilities:
            if capability.stage == stage:
                return capability.reason
        return "stage is not declared by the dataset policy"


class DatasetPipelinePaths(StrictBaseModel):
    """Rutas canonicas derivadas de dataset y run_id."""

    raw_path: str = Field(min_length=1)
    interim_dir: str = Field(min_length=1)
    clean_dir: str = Field(min_length=1)
    tensor_dir: str = Field(min_length=1)
    model_dir: str = Field(min_length=1)
    evaluation_dir: str = Field(min_length=1)
    memory_output_root: str = Field(min_length=1)


class DatasetPipelinePlan(StrictBaseModel):
    """Plan auditable que puede mostrarse antes de ejecutar."""

    request: PipelineRunRequest
    adapter_info: DatasetAdapterInfo
    descriptor: DatasetDescriptor
    policy: DatasetRunPolicy
    paths: DatasetPipelinePaths
    effective_stages: list[PipelineRunStage]
    can_execute_requested_stages: bool
    blocking_reasons: list[str] = Field(default_factory=list)
