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
    HealthState,
    ProjectionBoundary,
    ProjectionPoint,
    RunVisualizationData,
    TemporalRunSeries,
    TemporalSeriesData,
    TemporalSeriesPoint,
    TemporalXAxis,
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
    "source_path",
    "condition_id",
    "asset_id",
    "run_id",
    "window_index",
    "start",
    "end",
    "timestamp_start",
    "timestamp_end",
    "time_since_start_seconds",
    "time_to_failure_seconds",
    "relative_life",
    "split",
    "label",
    "target",
    "fault_type",
    "sample_rate_hz",
    "channel",
}

PREDICTION_COLUMNS = [
    "window_id",
    "condition_id",
    "asset_id",
    "run_id",
    "window_index",
    "timestamp_start",
    "timestamp_end",
    "time_since_start_seconds",
    "time_to_failure_seconds",
    "relative_life",
    "split",
    "label",
    "target",
    "fault_type",
    "anomaly_score",
    "threshold",
    "predicted_anomaly",
]

TEMPORAL_NUMERIC_COLUMNS = [
    "window_index",
    "time_since_start_seconds",
    "time_to_failure_seconds",
    "relative_life",
    "anomaly_score",
    "threshold",
    "predicted_anomaly",
]

TEMPORAL_AXIS_PRIORITY: list[TemporalXAxis] = [
    "relative_life",
    "time_since_start_seconds",
    "window_index",
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
    temporal_series = _safe_temporal_series(predictions_path, bounded_max_points)
    if features_path is None:
        warnings.append(
            "La proyeccion 2D requiere al menos el artefacto de features."
        )
        return RunVisualizationData(
            run_id=snapshot.run_id,
            dataset=snapshot.dataset,
            metrics=metrics,
            projection_available=False,
            temporal_series=temporal_series,
            source_paths=source_paths,
            warnings=warnings,
        )
    if predictions_path is None:
        warnings.append(
            "No hay predicciones; se muestra una proyeccion diagnostica de "
            "features sin anomalias predichas."
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
            temporal_series=temporal_series,
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
        temporal_series=temporal_series,
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


def _safe_temporal_series(
    predictions_path: str | None,
    max_points: int,
) -> TemporalSeriesData:
    try:
        return _temporal_series(predictions_path, max_points)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        return TemporalSeriesData(
            available=False,
            warnings=[f"No se pudo construir la serie temporal: {exc}"],
        )


def _temporal_series(
    predictions_path: str | None,
    max_points: int,
) -> TemporalSeriesData:
    if predictions_path is None:
        return TemporalSeriesData(
            available=False,
            warnings=["No hay predicciones para construir una serie temporal."],
        )
    data = pd.read_csv(predictions_path)
    if data.empty:
        return TemporalSeriesData(
            available=False,
            warnings=["El artefacto de predicciones esta vacio."],
        )
    missing = {"window_id", "anomaly_score"} - set(data.columns)
    if missing:
        return TemporalSeriesData(
            available=False,
            warnings=[
                "Las predicciones no incluyen columnas minimas temporales: "
                + ", ".join(sorted(missing))
                + "."
            ],
        )

    temporal = data.copy()
    for column in TEMPORAL_NUMERIC_COLUMNS:
        if column in temporal.columns:
            temporal[column] = pd.to_numeric(temporal[column], errors="coerce")
    temporal["anomaly_score"] = pd.to_numeric(
        temporal["anomaly_score"],
        errors="coerce",
    )
    temporal = temporal.dropna(subset=["anomaly_score"])
    if temporal.empty:
        return TemporalSeriesData(
            available=False,
            warnings=["Las predicciones no contienen anomaly_score numerico."],
        )

    x_axis = _temporal_x_axis(temporal)
    if x_axis is None:
        return TemporalSeriesData(
            available=False,
            warnings=[
                "No hay eje temporal usable en predicciones: se esperaba "
                "relative_life, time_since_start_seconds o window_index."
            ],
        )
    temporal = temporal.dropna(subset=[x_axis])
    if temporal.empty:
        return TemporalSeriesData(
            available=False,
            warnings=[f"La columna temporal {x_axis} no contiene valores numericos."],
        )
    if "run_id" not in temporal.columns:
        temporal["run_id"] = "_single_run"
    temporal["run_id"] = temporal["run_id"].apply(_stable_run_id)

    groups = list(temporal.groupby("run_id", sort=True))
    run_budget = max(1, max_points // max(1, len(groups)))
    runs = [
        _temporal_run_series(str(run_id), group, x_axis, run_budget)
        for run_id, group in groups
    ]
    return TemporalSeriesData(
        available=bool(runs),
        x_axis=x_axis,
        runs=runs,
        n_runs_total=len(runs),
        n_points_total=int(len(temporal)),
    )


def _temporal_x_axis(data: pd.DataFrame) -> TemporalXAxis | None:
    for column in TEMPORAL_AXIS_PRIORITY:
        if column in data.columns and data[column].notna().sum() >= 2:
            return column
    return None


def _temporal_run_series(
    run_id: str,
    group: pd.DataFrame,
    x_axis: TemporalXAxis,
    max_points: int,
) -> TemporalRunSeries:
    ordered = group.sort_values([x_axis, "window_id"], kind="mergesort").reset_index(
        drop=True
    )
    scores = ordered["anomaly_score"].dropna()
    score_min = None if scores.empty else float(scores.min())
    score_max = None if scores.empty else float(scores.max())
    sampled = _temporal_sample_indices(ordered, max_points)
    points = [
        _temporal_point(ordered.iloc[index], x_axis, score_min, score_max)
        for index in sampled
    ]
    first_alert = _first_temporal_alert(ordered)
    failure = _temporal_failure_marker(ordered, x_axis)
    latest = ordered.iloc[-1]
    current_health = _health_values(latest, score_min, score_max)
    state_counts = _health_state_counts(ordered, score_min, score_max)
    return TemporalRunSeries(
        run_id=run_id,
        x_axis=x_axis,
        points=points,
        n_points_total=int(len(ordered)),
        n_points_sampled=len(points),
        threshold=_threshold(ordered),
        first_alert_x=None if first_alert is None else _optional_float(first_alert[x_axis]),
        first_alert_time=None if first_alert is None else _row_time(first_alert),
        first_alert_time_to_failure_seconds=(
            None
            if first_alert is None
            else _optional_float(first_alert.get("time_to_failure_seconds"))
        ),
        failure_x=failure["x"],
        failure_time=failure["time"],
        score_min=score_min,
        score_max=score_max,
        current_x=_optional_float(latest.get(x_axis)),
        current_time=_row_time(latest),
        current_time_to_failure_seconds=_optional_float(
            latest.get("time_to_failure_seconds")
        ),
        current_risk_index=current_health["risk_index"],
        current_health_index=current_health["health_index"],
        current_health_state=current_health["health_state"],
        current_state_reason=current_health["state_reason"],
        alert_points=state_counts["alert_points"],
        warning_points=state_counts["warning_points"],
        critical_points=state_counts["critical_points"],
    )


def _temporal_sample_indices(data: pd.DataFrame, max_points: int) -> list[int]:
    if len(data) <= max_points:
        return list(range(len(data)))
    anchors = {0, len(data) - 1}
    if "predicted_anomaly" in data.columns:
        alerts = data.index[data["predicted_anomaly"].fillna(0).astype(int) == 1]
        if len(alerts):
            anchors.add(int(alerts[0]))
    if "time_to_failure_seconds" in data.columns:
        times = data["time_to_failure_seconds"].dropna()
        if not times.empty:
            anchors.add(int(times.abs().idxmin()))
    remaining_budget = max(0, max_points - len(anchors))
    evenly_spaced = np.linspace(0, len(data) - 1, remaining_budget, dtype=int)
    indices = sorted(anchors | set(evenly_spaced.tolist()))
    if len(indices) > max_points:
        indices = indices[:max_points]
    return indices


def _temporal_point(
    row: pd.Series,
    x_axis: TemporalXAxis,
    score_min: float | None,
    score_max: float | None,
) -> TemporalSeriesPoint:
    run_id = _stable_run_id(row.get("run_id"))
    health = _health_values(row, score_min, score_max)
    return TemporalSeriesPoint(
        window_id=str(row["window_id"]),
        run_id=run_id,
        x=float(row[x_axis]),
        timestamp_start=_optional_str(row.get("timestamp_start")),
        timestamp_end=_optional_str(row.get("timestamp_end")),
        relative_life=_optional_float(row.get("relative_life")),
        time_since_start_seconds=_optional_float(row.get("time_since_start_seconds")),
        time_to_failure_seconds=_optional_float(row.get("time_to_failure_seconds")),
        split=_optional_str(row.get("split")),
        label=_optional_str(row.get("label")),
        anomaly_score=float(row["anomaly_score"]),
        threshold=_optional_float(row.get("threshold")),
        predicted_anomaly=_optional_int(row.get("predicted_anomaly")),
        score_ratio=health["score_ratio"],
        risk_index=health["risk_index"],
        health_index=health["health_index"],
        health_state=health["health_state"],
        state_reason=health["state_reason"],
    )


def _health_state_counts(
    data: pd.DataFrame,
    score_min: float | None,
    score_max: float | None,
) -> dict[str, int]:
    states = [
        _health_values(row, score_min, score_max)["health_state"]
        for _, row in data.iterrows()
    ]
    return {
        "alert_points": sum(1 for state in states if state in {"warning", "critical"}),
        "warning_points": sum(1 for state in states if state == "warning"),
        "critical_points": sum(1 for state in states if state == "critical"),
    }


def _health_values(
    row: pd.Series,
    score_min: float | None,
    score_max: float | None,
) -> dict[str, float | str | None]:
    score = _optional_float(row.get("anomaly_score"))
    threshold = _optional_float(row.get("threshold"))
    predicted = _optional_int(row.get("predicted_anomaly"))
    if score is None:
        return {
            "score_ratio": None,
            "risk_index": None,
            "health_index": None,
            "health_state": "nominal",
            "state_reason": "Sin anomaly_score numerico.",
        }

    score_ratio: float | None = None
    if threshold is not None and threshold > 0:
        score_ratio = score / threshold
        risk_index = _clamp(score_ratio * 70.0, 0.0, 100.0)
    elif score_min is not None and score_max is not None and score_max > score_min:
        risk_index = _clamp(
            ((score - score_min) / (score_max - score_min)) * 100.0,
            0.0,
            100.0,
        )
    else:
        risk_index = 0.0

    if predicted == 1:
        risk_index = max(risk_index, 70.0)
    health_index = _clamp(100.0 - risk_index, 0.0, 100.0)
    state = _health_state(row, risk_index, predicted)
    return {
        "score_ratio": score_ratio,
        "risk_index": risk_index,
        "health_index": health_index,
        "health_state": state,
        "state_reason": _health_state_reason(state, score_ratio, predicted),
    }


def _health_state(
    row: pd.Series,
    risk_index: float,
    predicted: int | None,
) -> HealthState:
    relative_life = _optional_float(row.get("relative_life"))
    if predicted == 1 and (risk_index >= 95.0 or (relative_life or 0.0) >= 0.9):
        return "critical"
    if predicted == 1 or risk_index >= 70.0:
        return "warning"
    if risk_index >= 40.0:
        return "watch"
    return "nominal"


def _health_state_reason(
    state: HealthState,
    score_ratio: float | None,
    predicted: int | None,
) -> str:
    if state == "critical":
        return "Alerta activa con riesgo muy alto o tramo final de vida."
    if state == "warning":
        return "El detector marca anomalia o el score supera el umbral operativo."
    if state == "watch":
        return "El score se aproxima al umbral; conviene vigilar tendencia."
    if score_ratio is not None and predicted == 0:
        return "Score por debajo del umbral operativo."
    return "Sin senales de degradacion relevantes."


def _first_temporal_alert(data: pd.DataFrame) -> pd.Series | None:
    if "predicted_anomaly" not in data.columns:
        return None
    alerts = data[data["predicted_anomaly"].fillna(0).astype(int) == 1]
    if alerts.empty:
        return None
    return alerts.iloc[0]


def _temporal_failure_marker(
    data: pd.DataFrame,
    x_axis: TemporalXAxis,
) -> dict[str, float | str | None]:
    if "time_to_failure_seconds" not in data.columns:
        return {"x": None, "time": None}
    times = data["time_to_failure_seconds"].dropna()
    if times.empty:
        return {"x": None, "time": None}
    closest = data.loc[times.abs().idxmin()]
    if x_axis == "relative_life":
        return {"x": 1.0, "time": _row_time(closest)}
    if x_axis == "time_since_start_seconds":
        starts = pd.to_numeric(
            data.get("time_since_start_seconds"),
            errors="coerce",
        )
        failures = starts + data["time_to_failure_seconds"]
        failures = failures.dropna()
        if not failures.empty:
            return {"x": float(failures.median()), "time": _row_time(closest)}
    return {"x": _optional_float(closest.get(x_axis)), "time": _row_time(closest)}


def _row_time(row: pd.Series) -> str | None:
    for column in ("timestamp_end", "timestamp_start"):
        value = _optional_str(row.get(column))
        if value is not None:
            return value
    return None


def _stable_run_id(value: Any) -> str:
    if value is None or pd.isna(value) or str(value).strip() == "":
        return "_single_run"
    return str(value)


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
    predictions_path: str | None,
    max_points: int,
) -> dict[str, Any]:
    features = pd.read_csv(features_path)
    if features.empty:
        raise ValueError("features file is empty")
    if "window_id" not in features.columns:
        raise ValueError("features must include window_id")

    if predictions_path is None:
        data = features
    else:
        predictions = pd.read_csv(predictions_path)
        if predictions.empty:
            raise ValueError("predictions file is empty")
        if "window_id" not in predictions.columns:
            raise ValueError("predictions must include window_id")
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
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None or pd.isna(value):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, value))
