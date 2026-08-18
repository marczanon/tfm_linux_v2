"""Contratos versionados para salud temporal run-to-failure."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from codigo.app.schemas.common import StrictBaseModel


HealthState = Literal["nominal", "watch", "warning", "critical"]


class RunToFailurePartitionPolicy(StrictBaseModel):
    """Particion causal cerrada para el benchmark run-to-failure oficial."""

    policy_id: Literal["nasa_ims_run_to_failure_v2"] = (
        "nasa_ims_run_to_failure_v2"
    )
    partition_order: tuple[
        Literal["baseline_train"],
        Literal["calibration"],
        Literal["monitoring"],
    ] = ("baseline_train", "calibration", "monitoring")
    baseline_fraction: float = Field(default=0.20, ge=0.20, le=0.20)
    calibration_fraction: float = Field(default=0.10, ge=0.10, le=0.10)
    monitoring_fraction: float = Field(default=0.70, ge=0.70, le=0.70)
    allocation_method: Literal["largest_remainder_v1"] = "largest_remainder_v1"
    baseline_split: Literal["train"] = "train"
    calibration_split: Literal["validation"] = "validation"
    monitoring_split: Literal["test"] = "test"
    min_records_per_run: int = Field(default=10, ge=10, le=10)


class TemporalGapPolicy(StrictBaseModel):
    """Regla versionada para auditar continuidad entre snapshots."""

    policy_id: Literal["temporal_gap_v1"] = "temporal_gap_v1"
    expected_cadence_seconds: float = Field(default=600.0, ge=600.0, le=600.0)
    cadence_match_tolerance_seconds: float = Field(default=0.0, ge=0.0, le=0.0)
    max_contiguous_interval_seconds: float = Field(
        default=900.0,
        ge=900.0,
        le=900.0,
    )
    gap_operator: Literal["greater_than"] = "greater_than"
    reset_alert_persistence: Literal[True] = True
    reset_causal_smoothing: Literal[True] = True


class SnapshotAggregationPolicy(StrictBaseModel):
    """Politica reproducible para reducir ventanas a una captura temporal."""

    policy_id: str = Field(default="snapshot_aggregation_v1", min_length=1)
    temporal_unit: Literal["snapshot"] = "snapshot"
    group_keys: tuple[Literal["run_id"], Literal["file_id"]] = (
        "run_id",
        "file_id",
    )
    score_aggregation: Literal["median"] = "median"
    score_p90_quantile: float = Field(default=0.90, ge=0.90, le=0.90)
    score_std_ddof: int = Field(default=0, ge=0, le=0)
    alert_fraction_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    alert_threshold_operator: Literal["greater_than_or_equal"] = (
        "greater_than_or_equal"
    )


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


DEFAULT_RUN_TO_FAILURE_PARTITION_POLICY = RunToFailurePartitionPolicy()
DEFAULT_TEMPORAL_GAP_POLICY = TemporalGapPolicy()
DEFAULT_SNAPSHOT_AGGREGATION_POLICY = SnapshotAggregationPolicy()
DEFAULT_TEMPORAL_HEALTH_POLICY = TemporalHealthPolicy()
DEFAULT_TEMPORAL_HEALTH_INDICATOR_POLICY = TemporalHealthIndicatorPolicy()
