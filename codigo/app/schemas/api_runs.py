"""Contratos publicos para ejecucion controlada desde API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.pipeline_run import DatasetPipelinePlan, PipelineRunRequest
from codigo.app.schemas.reasoning import HumanReviewSettings
from codigo.app.schemas.state import HumanApproval
from codigo.app.schemas.state import MetricsReport
from codigo.app.services.run_persistence import RunSnapshot

ApiRunJobState = Literal["queued", "running", "completed", "failed"]


class ApiRunJobStatus(StrictBaseModel):
    """Estado observable de una ejecucion API aceptada en segundo plano."""

    job_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    status: ApiRunJobState
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    finished_at: datetime | None = None
    detail: str | None = Field(default=None, min_length=1)
    snapshot: RunSnapshot | None = None


class ApiRunRequest(PipelineRunRequest):
    """Solicitud API para planificar o ejecutar una run local."""

    dry_run: bool = True
    background: bool = False
    human_review: HumanReviewSettings = Field(default_factory=HumanReviewSettings)
    human_approval: HumanApproval | None = None


class ApiRunResponse(ApiRunRequest):
    """Respuesta compacta de `POST /runs`."""

    executed: bool
    plan: DatasetPipelinePlan
    snapshot: RunSnapshot | None = None
    final_stage: str | None = Field(default=None, min_length=1)
    approved: bool | None = None
    report_path: str | None = None
    metrics: MetricsReport | None = None
    errors: list[str] = Field(default_factory=list)
    human_review_reasons: list[str] = Field(default_factory=list)
    job: ApiRunJobStatus | None = None
