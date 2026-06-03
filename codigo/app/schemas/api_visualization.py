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
    metric_family: Literal[
        "binary_classification",
        "run_to_failure_degradation",
    ] = "binary_classification"
    value_kind: Literal["ratio", "seconds", "count", "score"] = "ratio"
    note: str | None = None


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
    first_persistent_alert_x: float | None = None
    first_persistent_alert_time: str | None = None
    first_persistent_alert_time_to_failure_seconds: float | None = None
    persistent_alert_min_windows: NonNegativeInt = 3
    failure_x: float | None = None
    failure_time: str | None = None
    failure_reference: str = Field(
        default="historic_replay",
        min_length=1,
    )
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
    isolated_alert_points: NonNegativeInt = 0
    alert_episodes: NonNegativeInt = 0
    longest_alert_streak: NonNegativeInt = 0


class TemporalSeriesData(StrictBaseModel):
    """Datos temporales para visualizar degradacion por run."""

    available: bool
    x_axis: TemporalXAxis | None = None
    runs: list[TemporalRunSeries] = Field(default_factory=list)
    n_runs_total: NonNegativeInt = 0
    n_points_total: NonNegativeInt = 0
    warnings: list[str] = Field(default_factory=list)


class AgentOperationalRecommendation(StrictBaseModel):
    """Recomendacion agentica compacta para el panel operacional."""

    available: bool = False
    source_agent: str | None = None
    decision_id: str | None = None
    status: Literal[
        "approved",
        "caution",
        "needs_revision",
        "blocked",
        "unavailable",
    ] = "unavailable"
    title: str = Field(default="Sin recomendacion agentica disponible", min_length=1)
    summary: str = Field(default="No hay decision agentica persistida.", min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    next_action: str | None = None
    operational_assessment: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    debate_points: list[str] = Field(default_factory=list)
    guardrail_checks: list[str] = Field(default_factory=list)
    modeler_summary: str | None = None


class RunVisualizationData(StrictBaseModel):
    """Datos compactos para la pestaña de visualizacion."""

    run_id: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    supervision_profile: str | None = None
    label_source: str | None = None
    label_granularity: str | None = None
    model_name: str | None = None
    metric_families: list[str] = Field(default_factory=list)
    metrics: list[VisualizationMetric]
    primary_metrics: list[VisualizationMetric] = Field(default_factory=list)
    auxiliary_metrics: list[VisualizationMetric] = Field(default_factory=list)
    binary_metric_context: dict[str, str] = Field(default_factory=dict)
    projection_available: bool
    projection_points: list[ProjectionPoint] = Field(default_factory=list)
    projection_boundary: ProjectionBoundary | None = None
    projection_role: Literal["primary", "diagnostic"] = "diagnostic"
    projection_explanation: str = Field(
        default=(
            "La proyeccion PCA 2D es una vista diagnostica de features; "
            "no sustituye las metricas temporales ni la frontera real del modelo."
        ),
        min_length=1,
    )
    temporal_series: TemporalSeriesData | None = None
    agent_recommendation: AgentOperationalRecommendation | None = None
    n_points_total: NonNegativeInt = 0
    n_points_sampled: NonNegativeInt = 0
    source_paths: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
