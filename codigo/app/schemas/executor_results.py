"""Contratos de salida para ejecutores deterministas."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, NonNegativeInt, model_validator

from codigo.app.schemas.common import JsonScalar, StrictBaseModel
from codigo.app.schemas.state import ArtifactRef, PipelineError, PipelineStage

ExecutorStatus = Literal["success", "skipped", "failed"]


class ExecutorResult(StrictBaseModel):
    """Resultado comun de un ejecutor determinista."""

    executor_name: str = Field(min_length=1)
    stage: PipelineStage
    status: ExecutorStatus
    message: str = Field(min_length=1)
    artifacts: list[ArtifactRef] = Field(default_factory=list)
    errors: list[PipelineError] = Field(default_factory=list)
    state_updates: dict[str, JsonScalar] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def validate_status_consistency(self) -> "ExecutorResult":
        if self.status == "failed" and not self.errors:
            raise ValueError("failed executor results require at least one error")
        if self.status == "success" and self.errors:
            raise ValueError("successful executor results cannot include errors")
        return self


class ManifestResult(ExecutorResult):
    """Resultado del ejecutor de manifiesto."""

    stage: Literal["dataset_manifest"] = "dataset_manifest"
    manifest_path: str = Field(min_length=1)
    n_rows: NonNegativeInt
    label_counts: dict[str, NonNegativeInt]

    @model_validator(mode="after")
    def validate_manifest_artifact(self) -> "ManifestResult":
        if self.status == "success" and self.n_rows == 0:
            raise ValueError("successful manifest results require n_rows > 0")
        if self.status == "success" and not self.manifest_path:
            raise ValueError("successful manifest results require manifest_path")
        return self


class ProfileResult(ExecutorResult):
    """Resultado del ejecutor de perfilado."""

    stage: Literal["profiling"] = "profiling"
    profile_path: str = Field(min_length=1)
    n_files_profiled: NonNegativeInt


class CleaningResult(ExecutorResult):
    """Resultado del ejecutor de limpieza."""

    stage: Literal["cleaning"] = "cleaning"
    clean_path: str = Field(min_length=1)
    n_files_cleaned: NonNegativeInt


class StructuringResult(ExecutorResult):
    """Resultado del ejecutor de estructuracion temporal."""

    stage: Literal["structuring"] = "structuring"
    features_path: str = Field(min_length=1)
    tensors_path: str | None
    splits_path: str = Field(min_length=1)
    n_windows: NonNegativeInt


class ModelingResult(ExecutorResult):
    """Resultado del ejecutor de modelado."""

    stage: Literal["modeling"] = "modeling"
    model_path: str = Field(min_length=1)
    predictions_path: str | None


class EvaluationExecutorResult(ExecutorResult):
    """Resultado del ejecutor de evaluacion."""

    stage: Literal["evaluation"] = "evaluation"
    metrics_path: str = Field(min_length=1)
    report_fragment_path: str | None


class ReportExecutorResult(ExecutorResult):
    """Resultado del ejecutor o agente redactor de informe."""

    stage: Literal["reporting"] = "reporting"
    report_path: str = Field(min_length=1)
