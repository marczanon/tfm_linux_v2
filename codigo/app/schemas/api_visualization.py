"""Contratos API para visualizaciones de runs persistidas."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, NonNegativeInt

from codigo.app.schemas.common import StrictBaseModel


class VisualizationMetric(StrictBaseModel):
    """Metrica numerica preparada para graficas."""

    name: str = Field(min_length=1)
    label: str = Field(min_length=1)
    value: float | None = None
    higher_is_better: bool = True


class ProjectionPoint(StrictBaseModel):
    """Punto de una proyeccion 2D de ventanas/features."""

    window_id: str = Field(min_length=1)
    x: float
    y: float
    split: str | None = None
    label: str | None = None
    target: int | None = None
    fault_type: str | None = None
    anomaly_score: float | None = None
    threshold: float | None = None
    predicted_anomaly: int | None = None


class ProjectionBoundary(StrictBaseModel):
    """Frontera visual aproximada en el espacio 2D."""

    kind: Literal["ellipse_approximation"] = "ellipse_approximation"
    center_x: float
    center_y: float
    radius_x: float
    radius_y: float
    threshold: float | None = None
    note: str = Field(min_length=1)


TemporalXAxis = Literal["relative_life", "time_since_start_seconds", "window_index"]
HealthState = Literal["nominal", "watch", "warning", "critical"]


class TemporalSeriesPoint(StrictBaseModel):
    """Punto temporal compacto de una ventana predicha."""

    window_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    x: float
    timestamp_start: str | None = None
    timestamp_end: str | None = None
    relative_life: float | None = None
    time_since_start_seconds: float | None = None
    time_to_failure_seconds: float | None = None
    split: str | None = None
    label: str | None = None
    anomaly_score: float
    threshold: float | None = None
    predicted_anomaly: int | None = None
    score_ratio: float | None = None
    risk_index: float | None = None
    health_index: float | None = None
    health_state: HealthState = "nominal"
    state_reason: str = Field(min_length=1)


class TemporalRunSeries(StrictBaseModel):
    """Serie temporal de una trayectoria run-to-failure."""

    run_id: str = Field(min_length=1)
    x_axis: TemporalXAxis
    points: list[TemporalSeriesPoint]
    n_points_total: NonNegativeInt
    n_points_sampled: NonNegativeInt
    threshold: float | None = None
    first_alert_x: float | None = None
    first_alert_time: str | None = None
    first_alert_time_to_failure_seconds: float | None = None
    failure_x: float | None = None
    failure_time: str | None = None
    score_min: float | None = None
    score_max: float | None = None
    current_x: float | None = None
    current_time: str | None = None
    current_time_to_failure_seconds: float | None = None
    current_risk_index: float | None = None
    current_health_index: float | None = None
    current_health_state: HealthState = "nominal"
    current_state_reason: str = Field(
        default="Sin evidencia temporal suficiente.",
        min_length=1,
    )
    alert_points: NonNegativeInt = 0
    warning_points: NonNegativeInt = 0
    critical_points: NonNegativeInt = 0


class TemporalSeriesData(StrictBaseModel):
    """Datos temporales para visualizar degradacion por run."""

    available: bool
    x_axis: TemporalXAxis | None = None
    runs: list[TemporalRunSeries] = Field(default_factory=list)
    n_runs_total: NonNegativeInt = 0
    n_points_total: NonNegativeInt = 0
    warnings: list[str] = Field(default_factory=list)


class RunVisualizationData(StrictBaseModel):
    """Datos compactos para la pestaña de visualizacion."""

    run_id: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    metrics: list[VisualizationMetric]
    projection_available: bool
    projection_points: list[ProjectionPoint] = Field(default_factory=list)
    projection_boundary: ProjectionBoundary | None = None
    temporal_series: TemporalSeriesData | None = None
    n_points_total: NonNegativeInt = 0
    n_points_sampled: NonNegativeInt = 0
    source_paths: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
