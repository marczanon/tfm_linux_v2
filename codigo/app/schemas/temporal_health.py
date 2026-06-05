"""Contratos versionados para salud temporal run-to-failure."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from codigo.app.schemas.common import StrictBaseModel


HealthState = Literal["nominal", "watch", "warning", "critical"]


class TemporalAlertPolicy(StrictBaseModel):
    """Politica de confirmacion de alertas temporales."""

    policy_id: str = Field(default="alert_persistence_v1", min_length=1)
    persistent_alert_min_windows: int = Field(default=3, ge=1)
    nominal_relative_life_limit: float = Field(default=0.40, ge=0.0, le=1.0)
    early_relative_life_limit: float = Field(default=0.33, ge=0.0, le=1.0)
    late_relative_life_limit: float = Field(default=0.67, ge=0.0, le=1.0)


class TemporalHealthPolicy(StrictBaseModel):
    """Politica cerrada para traducir scores a estados de salud."""

    policy_id: str = Field(default="temporal_health_policy_v1", min_length=1)
    alert_policy: TemporalAlertPolicy = Field(default_factory=TemporalAlertPolicy)
    watch_risk_threshold: float = Field(default=40.0, ge=0.0, le=100.0)
    warning_risk_threshold: float = Field(default=70.0, ge=0.0, le=100.0)
    critical_risk_threshold: float = Field(default=95.0, ge=0.0, le=100.0)
    predicted_alert_min_risk: float = Field(default=70.0, ge=0.0, le=100.0)
    critical_relative_life_threshold: float = Field(default=0.90, ge=0.0, le=1.0)


class TemporalHealthIndicatorPolicy(StrictBaseModel):
    """Politica causal para derivar Health Indicator avanzado."""

    policy_id: str = Field(default="health_indicator_policy_v1", min_length=1)
    smoothing_window: int = Field(default=3, ge=1)
    trend_window: int = Field(default=3, ge=1)
    min_drop_for_degradation: float = Field(default=5.0, ge=0.0, le=100.0)
    nominal_volatility_limit: float = Field(default=15.0, ge=0.0, le=100.0)


DEFAULT_TEMPORAL_HEALTH_POLICY = TemporalHealthPolicy()
DEFAULT_TEMPORAL_HEALTH_INDICATOR_POLICY = TemporalHealthIndicatorPolicy()
