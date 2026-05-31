"""Datos derivados para visualizaciones read-only de runs persistidas."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from codigo.app.schemas.api_visualization import (
    ProjectionBoundary,
    ProjectionPoint,
    RunVisualizationData,
    VisualizationMetric,
)
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR, load_run_snapshot
from codigo.app.services.run_registry import get_run_artifacts


METRIC_LABELS: dict[str, tuple[str, bool]] = {
    "precision": ("Precision", True),
    "recall": ("Recall", True),
    "f1_score": ("F1", True),
    "false_positive_rate": ("FPR", False),
    "roc_auc": ("ROC-AUC", True),
    "pr_auc": ("PR-AUC", True),
}

FEATURE_METADATA_COLUMNS = {
    "window_id",
    "file_id",
    "window_index",
    "start",
    "end",
    "split",
    "label",
    "target",
    "fault_type",
    "sample_rate_hz",
    "channel",
}

PREDICTION_COLUMNS = [
    "window_id",
    "split",
    "label",
    "target",
    "fault_type",
    "anomaly_score",
    "threshold",
    "predicted_anomaly",
]


def build_run_visualization(
    run_id: str,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
    *,
    max_points: int = 900,
) -> RunVisualizationData:
    """Construye una vista compacta de metricas y proyeccion 2D."""

    bounded_max_points = max(50, min(max_points, 2500))
    snapshot = load_run_snapshot(run_id, runs_dir)
    artifacts = get_run_artifacts(run_id, runs_dir)
    source_paths = _artifact_paths(artifacts)
    metrics = _metrics(snapshot.metrics_path)
    warnings: list[str] = []

    features_path = source_paths.get("features")
    predictions_path = source_paths.get("predictions")
    if features_path is None or predictions_path is None:
        warnings.append(
            "La proyeccion 2D requiere artefactos de features y predicciones."
        )
        return RunVisualizationData(
            run_id=snapshot.run_id,
            dataset=snapshot.dataset,
            metrics=metrics,
            projection_available=False,
            source_paths=source_paths,
            warnings=warnings,
        )

    try:
        projection = _projection(features_path, predictions_path, bounded_max_points)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        warnings.append(f"No se pudo construir la proyeccion 2D: {exc}")
        return RunVisualizationData(
            run_id=snapshot.run_id,
            dataset=snapshot.dataset,
            metrics=metrics,
            projection_available=False,
            source_paths=source_paths,
            warnings=warnings,
        )

    return RunVisualizationData(
        run_id=snapshot.run_id,
        dataset=snapshot.dataset,
        metrics=metrics,
        projection_available=True,
        projection_points=projection["points"],
        projection_boundary=projection["boundary"],
        n_points_total=projection["n_total"],
        n_points_sampled=len(projection["points"]),
        source_paths=source_paths,
        warnings=warnings,
    )


def _metrics(metrics_path: str) -> list[VisualizationMetric]:
    payload = _read_json(Path(metrics_path))
    data = payload if isinstance(payload, dict) else {}
    metrics: list[VisualizationMetric] = []
    for name, (label, higher_is_better) in METRIC_LABELS.items():
        value = data.get(name)
        metrics.append(
            VisualizationMetric(
                name=name,
                label=label,
                value=None if value is None else float(value),
                higher_is_better=higher_is_better,
            )
        )
    return metrics


def _artifact_paths(artifacts: list[dict[str, Any]]) -> dict[str, str]:
    paths: dict[str, str] = {}
    for artifact in artifacts:
        artifact_type = artifact.get("artifact_type")
        path = artifact.get("path")
        if isinstance(artifact_type, str) and isinstance(path, str):
            paths.setdefault(artifact_type, path)
    return paths


def _projection(
    features_path: str,
    predictions_path: str,
    max_points: int,
) -> dict[str, Any]:
    features = pd.read_csv(features_path)
    predictions = pd.read_csv(predictions_path)
    if features.empty or predictions.empty:
        raise ValueError("features or predictions file is empty")
    if "window_id" not in features.columns or "window_id" not in predictions.columns:
        raise ValueError("features and predictions must include window_id")

    prediction_view = predictions[
        [column for column in PREDICTION_COLUMNS if column in predictions.columns]
    ]
    data = features.merge(
        prediction_view,
        on="window_id",
        how="inner",
        suffixes=("", "_prediction"),
    )
    if data.empty:
        raise ValueError("features and predictions have no matching window_id")

    feature_columns = _feature_columns(features)
    matrix = data[feature_columns].apply(pd.to_numeric, errors="coerce")
    matrix = matrix.fillna(matrix.median(numeric_only=True)).fillna(0.0)
    coordinates = _pca_coordinates(matrix.to_numpy(dtype=float))

    sampled = _sample_indices(data, max_points)
    points = [
        _point(data.iloc[index], coordinates[index])
        for index in sampled
    ]
    boundary = _boundary(data, coordinates)
    return {
        "points": points,
        "boundary": boundary,
        "n_total": int(len(data)),
    }


def _feature_columns(features: pd.DataFrame) -> list[str]:
    columns = [
        column
        for column in features.columns
        if column not in FEATURE_METADATA_COLUMNS
        and pd.api.types.is_numeric_dtype(features[column])
    ]
    if not columns:
        raise ValueError("no numeric feature columns found")
    return columns


def _pca_coordinates(matrix: np.ndarray) -> np.ndarray:
    scaled = StandardScaler().fit_transform(matrix)
    if scaled.shape[1] == 1:
        return np.column_stack([scaled[:, 0], np.zeros(scaled.shape[0])])
    return PCA(n_components=2, random_state=42).fit_transform(scaled)


def _sample_indices(data: pd.DataFrame, max_points: int) -> list[int]:
    if len(data) <= max_points:
        return list(range(len(data)))

    if "predicted_anomaly" not in data.columns:
        return sorted(_choice(np.random.default_rng(42), list(range(len(data))), max_points))

    anomalies = data.index[data["predicted_anomaly"].astype(int) == 1].tolist()
    normal = data.index.difference(anomalies).tolist()
    rng = np.random.default_rng(42)
    anomaly_budget = min(len(anomalies), max(1, max_points // 3))
    normal_budget = max_points - anomaly_budget
    selected_anomalies = _choice(rng, anomalies, anomaly_budget)
    selected_normal = _choice(rng, normal, normal_budget)
    return sorted(selected_anomalies + selected_normal)


def _choice(rng: np.random.Generator, values: list[int], n_items: int) -> list[int]:
    if not values or n_items <= 0:
        return []
    if len(values) <= n_items:
        return values
    return rng.choice(values, size=n_items, replace=False).tolist()


def _point(row: pd.Series, xy: np.ndarray) -> ProjectionPoint:
    return ProjectionPoint(
        window_id=str(row["window_id"]),
        x=float(xy[0]),
        y=float(xy[1]),
        split=_optional_str(row.get("split")),
        label=_optional_str(row.get("label")),
        target=_optional_int(row.get("target")),
        fault_type=_optional_str(row.get("fault_type")),
        anomaly_score=_optional_float(row.get("anomaly_score")),
        threshold=_optional_float(row.get("threshold")),
        predicted_anomaly=_optional_int(row.get("predicted_anomaly")),
    )


def _boundary(data: pd.DataFrame, coordinates: np.ndarray) -> ProjectionBoundary | None:
    predicted = data.get("predicted_anomaly")
    if predicted is None:
        return None

    normal_mask = predicted.astype(int).to_numpy() == 0
    normal_points = coordinates[normal_mask]
    if normal_points.size == 0:
        return None

    center = np.median(normal_points, axis=0)
    deviations = np.abs(normal_points - center)
    radii = np.quantile(deviations, 0.95, axis=0)
    radii = np.maximum(radii, 0.1)
    threshold = _threshold(data)
    return ProjectionBoundary(
        center_x=float(center[0]),
        center_y=float(center[1]),
        radius_x=float(radii[0]),
        radius_y=float(radii[1]),
        threshold=threshold,
        note=(
            "Frontera visual aproximada sobre la proyeccion PCA 2D; "
            "el umbral real se aplica en el espacio original del modelo."
        ),
    )


def _threshold(data: pd.DataFrame) -> float | None:
    if "threshold" not in data.columns:
        return None
    values = pd.to_numeric(data["threshold"], errors="coerce").dropna()
    if values.empty:
        return None
    return float(values.iloc[0])


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _optional_str(value: Any) -> str | None:
    if value is None or pd.isna(value) or value == "":
        return None
    return str(value)


def _optional_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _optional_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    return int(value)
