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


class RunVisualizationData(StrictBaseModel):
    """Datos compactos para la pestaña de visualizacion."""

    run_id: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    metrics: list[VisualizationMetric]
    projection_available: bool
    projection_points: list[ProjectionPoint] = Field(default_factory=list)
    projection_boundary: ProjectionBoundary | None = None
    n_points_total: NonNegativeInt = 0
    n_points_sampled: NonNegativeInt = 0
    source_paths: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
