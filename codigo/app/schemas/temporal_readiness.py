"""Contratos de readiness para modelos temporales avanzados."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from codigo.app.schemas.common import StrictBaseModel


ReadinessLevel = Literal["ready", "caution", "blocked"]
CostLevel = Literal["low", "moderate", "high", "unknown"]


class TemporalModelReadinessPolicy(StrictBaseModel):
    """Politica local para autorizar modelos temporales avanzados."""

    policy_id: str = Field(default="temporal_model_readiness_v1", min_length=1)
    min_autoencoder_train_nominal_windows: int = Field(default=30, ge=1)
    min_autoencoder_feature_columns: int = Field(default=3, ge=1)
    min_temporal_windows: int = Field(default=8, ge=1)
    min_rul_runs: int = Field(default=3, ge=1)
    min_time_to_failure_coverage: float = Field(default=0.80, ge=0.0, le=1.0)
    min_finite_feature_ratio: float = Field(default=0.95, ge=0.0, le=1.0)
    max_train_degradation_fraction: float = Field(default=0.05, ge=0.0, le=1.0)


class TemporalModelReadinessAssessment(StrictBaseModel):
    """Resultado estructurado que pueden citar los agentes."""

    analysis_type: Literal["temporal_model_readiness"] = "temporal_model_readiness"
    policy_id: str = Field(min_length=1)
    available: bool
    readiness_level: ReadinessLevel
    autoencoder_ready: bool
    rul_ready: bool
    blocked_reasons: list[str] = Field(default_factory=list)
    caution_reasons: list[str] = Field(default_factory=list)
    recommended_next_experiment: str = Field(min_length=1)
    estimated_cost_level: CostLevel = "unknown"
    n_windows: int = Field(ge=0)
    n_train_windows: int = Field(ge=0)
    n_train_nominal_windows: int = Field(ge=0)
    n_feature_columns: int = Field(ge=0)
    n_runs: int = Field(ge=0)
    temporal_continuity_ok: bool
    time_to_failure_coverage: float | None = Field(default=None, ge=0.0, le=1.0)
    split_quality_ok: bool
    leakage_risk: ReadinessLevel
    finite_feature_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    features_path: str | None = None
    predictions_path: str | None = None
    splits_path: str | None = None


DEFAULT_TEMPORAL_MODEL_READINESS_POLICY = TemporalModelReadinessPolicy()
