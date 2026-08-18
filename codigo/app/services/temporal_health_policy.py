"""Politica compartida de salud temporal para evaluacion y visualizacion."""

from __future__ import annotations

import math
from collections import Counter
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from codigo.app.schemas.temporal_health import (
    DEFAULT_SNAPSHOT_AGGREGATION_POLICY,
    DEFAULT_TEMPORAL_GAP_POLICY,
    DEFAULT_TEMPORAL_HEALTH_INDICATOR_POLICY,
    DEFAULT_TEMPORAL_HEALTH_POLICY,
    HealthState,
    SnapshotAggregationPolicy,
    TemporalGapPolicy,
    TemporalHealthIndicatorPolicy,
    TemporalHealthPolicy,
)


def default_snapshot_aggregation_policy() -> SnapshotAggregationPolicy:
    """Devuelve una copia validada de la agregacion temporal por captura."""

    return SnapshotAggregationPolicy.model_validate(
        DEFAULT_SNAPSHOT_AGGREGATION_POLICY.model_dump(mode="json")
    )


def default_temporal_gap_policy() -> TemporalGapPolicy:
    """Devuelve una copia validada de la politica de continuidad temporal."""

    return TemporalGapPolicy.model_validate(
        DEFAULT_TEMPORAL_GAP_POLICY.model_dump(mode="json")
    )


def annotate_temporal_gaps(
    rows: list[Mapping[str, Any]],
    *,
    policy: TemporalGapPolicy | None = None,
) -> list[dict[str, Any]]:
    """Ordena por trayectoria y anota intervalos, gaps y segmentos causales."""

    active_policy = policy or DEFAULT_TEMPORAL_GAP_POLICY
    grouped: dict[str, list[tuple[int, Mapping[str, Any]]]] = {}
    for index, row in enumerate(rows):
        run_id = _stable_identifier(row.get("run_id"), "_single_run")
        grouped.setdefault(run_id, []).append((index, row))

    annotated: list[dict[str, Any]] = []
    for run_id, group in grouped.items():
        ordered = sorted(
            group,
            key=lambda item: _temporal_row_sort_key(item[1], item[0]),
        )
        previous_seconds: float | None = None
        segment_id = 0
        for original_index, row in ordered:
            current_seconds = _temporal_row_seconds(row)
            interval_seconds = (
                None
                if previous_seconds is None or current_seconds is None
                else current_seconds - previous_seconds
            )
            if interval_seconds is not None and interval_seconds < 0:
                raise ValueError(
                    f"temporal axis moves backwards for run {run_id} at row "
                    f"{original_index}"
                )
            gap_detected = bool(
                interval_seconds is not None
                and interval_seconds
                > active_policy.max_contiguous_interval_seconds
            )
            if gap_detected:
                segment_id += 1
            cadence_matches = (
                None
                if interval_seconds is None
                else abs(
                    interval_seconds - active_policy.expected_cadence_seconds
                )
                <= active_policy.cadence_match_tolerance_seconds
            )
            updated = dict(row)
            updated.update(
                {
                    "temporal_gap_policy_id": active_policy.policy_id,
                    "expected_cadence_seconds": (
                        active_policy.expected_cadence_seconds
                    ),
                    "interval_seconds": interval_seconds,
                    "gap_before_seconds": (
                        interval_seconds if gap_detected else None
                    ),
                    "gap_detected": gap_detected,
                    "cadence_matches_expected": cadence_matches,
                    "temporal_segment_id": segment_id,
                }
            )
            annotated.append(updated)
            if current_seconds is not None:
                previous_seconds = current_seconds
    return annotated


def default_temporal_health_policy() -> TemporalHealthPolicy:
    """Devuelve una copia validada de la politica temporal por defecto."""

    return TemporalHealthPolicy.model_validate(
        DEFAULT_TEMPORAL_HEALTH_POLICY.model_dump(mode="json")
    )


def aggregate_temporal_snapshots(
    rows: list[Mapping[str, Any]],
    *,
    policy: SnapshotAggregationPolicy | None = None,
) -> list[dict[str, Any]]:
    """Agrega ventanas de una misma captura antes del analisis longitudinal.

    La identidad temporal es ``run_id + file_id``. Cuando un CSV historico no
    contiene ``file_id``, cada ``window_id`` se conserva como una captura
    independiente para no fusionar observaciones sin evidencia.
    """

    active_policy = policy or DEFAULT_SNAPSHOT_AGGREGATION_POLICY
    grouped: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    identity_sources: dict[tuple[str, str], str] = {}
    for index, row in enumerate(rows):
        run_id = _stable_identifier(row.get("run_id"), "_single_run")
        file_id = _optional_identifier(row.get("file_id"))
        identity_source = "file_id"
        if file_id is None:
            file_id = _stable_identifier(row.get("window_id"), f"_window_{index}")
            identity_source = "window_id_fallback"
        key = (run_id, file_id)
        grouped.setdefault(key, []).append(row)
        identity_sources[key] = identity_source

    snapshots: list[dict[str, Any]] = []
    for (run_id, file_id), group in grouped.items():
        scores = _numeric_values(group, "anomaly_score")
        predictions = [
            value
            for value in (optional_int(row.get("predicted_anomaly")) for row in group)
            if value is not None
        ]
        if not scores or not predictions:
            continue
        score_median = _median(scores)
        alert_fraction = sum(1 for value in predictions if value == 1) / len(
            predictions
        )
        snapshot = dict(group[0])
        snapshot.update(
            {
                "snapshot_id": file_id,
                "window_id": f"snapshot:{run_id}:{file_id}",
                "file_id": file_id,
                "run_id": run_id,
                "temporal_unit": active_policy.temporal_unit,
                "snapshot_identity_source": identity_sources[(run_id, file_id)],
                "snapshot_aggregation_policy_id": active_policy.policy_id,
                "n_windows": len(group),
                "n_alerted_windows": sum(
                    1 for value in predictions if value == 1
                ),
                "window_alert_fraction": alert_fraction,
                "predicted_anomaly": int(
                    alert_fraction >= active_policy.alert_fraction_threshold
                ),
                "anomaly_score": score_median,
                "anomaly_score_median": score_median,
                "anomaly_score_p90": _linear_percentile(
                    scores,
                    active_policy.score_p90_quantile,
                ),
                "anomaly_score_mean": sum(scores) / len(scores),
                "anomaly_score_std": _population_standard_deviation(scores),
                "threshold": _median(_numeric_values(group, "threshold")),
            }
        )
        for column in (
            "relative_life",
            "time_since_start_seconds",
            "time_to_failure_seconds",
        ):
            snapshot[column] = _median(_numeric_values(group, column))
        window_indexes = _numeric_values(group, "window_index")
        if window_indexes:
            snapshot["window_index"] = int(min(window_indexes))
        timestamp_starts = _text_values(group, "timestamp_start")
        timestamp_ends = _text_values(group, "timestamp_end")
        snapshot["timestamp_start"] = (
            None if not timestamp_starts else min(timestamp_starts)
        )
        snapshot["timestamp_end"] = None if not timestamp_ends else max(timestamp_ends)
        snapshots.append(snapshot)
    return snapshots


def temporal_health_values(
    row: Mapping[str, Any],
    *,
    score_min: float | None,
    score_max: float | None,
    policy: TemporalHealthPolicy | None = None,
) -> dict[str, float | str | None]:
    """Convierte score, umbral y prediccion en indices y estado de salud."""

    active_policy = policy or DEFAULT_TEMPORAL_HEALTH_POLICY
    score = optional_float(row.get("anomaly_score"))
    threshold = optional_float(row.get("threshold"))
    predicted = optional_int(row.get("predicted_anomaly"))
    if score is None:
        return {
            "score_ratio": None,
            "risk_index": None,
            "health_index": None,
            "health_state": "nominal",
            "state_reason": "Sin anomaly_score numerico.",
            "health_policy_id": active_policy.policy_id,
            "alert_policy_id": active_policy.alert_policy.policy_id,
        }

    score_ratio: float | None = None
    if threshold is not None and threshold > 0:
        score_ratio = score / threshold
        risk_index = clamp(score_ratio * active_policy.warning_risk_threshold)
    elif score_min is not None and score_max is not None and score_max > score_min:
        risk_index = clamp(((score - score_min) / (score_max - score_min)) * 100.0)
    else:
        risk_index = 0.0

    if predicted == 1:
        risk_index = max(risk_index, active_policy.predicted_alert_min_risk)
    health_index = clamp(100.0 - risk_index)
    state = temporal_health_state(row, risk_index, predicted, policy=active_policy)
    return {
        "score_ratio": score_ratio,
        "risk_index": risk_index,
        "health_index": health_index,
        "health_state": state,
        "state_reason": temporal_health_state_reason(state, score_ratio, predicted),
        "health_policy_id": active_policy.policy_id,
        "alert_policy_id": active_policy.alert_policy.policy_id,
    }


def temporal_health_state(
    row: Mapping[str, Any],
    risk_index: float,
    predicted: int | None,
    *,
    policy: TemporalHealthPolicy | None = None,
) -> HealthState:
    """Clasifica el punto temporal segun la politica activa."""

    active_policy = policy or DEFAULT_TEMPORAL_HEALTH_POLICY
    if predicted == 1 and risk_index >= active_policy.critical_risk_threshold:
        return "critical"
    if predicted == 1 or risk_index >= active_policy.warning_risk_threshold:
        return "warning"
    if risk_index >= active_policy.watch_risk_threshold:
        return "watch"
    return "nominal"


def temporal_health_state_reason(
    state: HealthState,
    score_ratio: float | None,
    predicted: int | None,
) -> str:
    """Explica la razon operacional del estado temporal."""

    if state == "critical":
        return "Alerta activa con riesgo muy alto o extremo de la trayectoria."
    if state == "warning":
        return "El detector marca anomalia o el score supera el umbral operativo."
    if state == "watch":
        return "El score se aproxima al umbral; conviene vigilar tendencia."
    if score_ratio is not None and predicted == 0:
        return "Score por debajo del umbral operativo."
    return "Sin senales de degradacion relevantes."


def temporal_alert_flags(states: list[HealthState]) -> list[bool]:
    """Marca estados que cuentan como alerta operacional."""

    return [state in {"warning", "critical"} for state in states]


def true_runs(
    flags: list[bool],
    *,
    segment_ids: list[int] | None = None,
) -> list[dict[str, int]]:
    """Resume rachas consecutivas True como start/length."""

    if segment_ids is not None and len(segment_ids) != len(flags):
        raise ValueError("segment_ids must match flags length")
    runs: list[dict[str, int]] = []
    start: int | None = None
    for index, flag in enumerate(flags):
        segment_changed = (
            index > 0
            and segment_ids is not None
            and segment_ids[index] != segment_ids[index - 1]
        )
        if segment_changed and start is not None:
            runs.append({"start": start, "length": index - start})
            start = None
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            runs.append({"start": start, "length": index - start})
            start = None
    if start is not None:
        runs.append({"start": start, "length": len(flags) - start})
    return runs


def temporal_alert_summary(
    states: list[HealthState],
    *,
    policy: TemporalHealthPolicy | None = None,
    segment_ids: list[int] | None = None,
) -> dict[str, int | None]:
    """Calcula episodios, persistencia y primer onset confirmado."""

    active_policy = policy or DEFAULT_TEMPORAL_HEALTH_POLICY
    alert_runs = true_runs(
        temporal_alert_flags(states),
        segment_ids=segment_ids,
    )
    min_windows = active_policy.alert_policy.persistent_alert_min_windows
    persistent_runs = [item for item in alert_runs if item["length"] >= min_windows]
    first_persistent_index = None if not persistent_runs else persistent_runs[0]["start"]
    return {
        "alert_points": sum(1 for state in states if state in {"warning", "critical"}),
        "warning_points": sum(1 for state in states if state == "warning"),
        "critical_points": sum(1 for state in states if state == "critical"),
        "isolated_alert_points": sum(
            item["length"] for item in alert_runs if item["length"] < min_windows
        ),
        "alert_episodes": len(alert_runs),
        "longest_alert_streak": (
            0 if not alert_runs else max(item["length"] for item in alert_runs)
        ),
        "first_persistent_index": first_persistent_index,
    }


def temporal_health_indicator_series(
    rows: list[Mapping[str, Any]],
    *,
    score_min: float | None,
    score_max: float | None,
    health_policy: TemporalHealthPolicy | None = None,
    indicator_policy: TemporalHealthIndicatorPolicy | None = None,
    x_key: str = "relative_life",
) -> dict[str, Any]:
    """Deriva HI bruto/suavizado y metricas de calidad sin mirar al futuro."""

    active_health_policy = health_policy or DEFAULT_TEMPORAL_HEALTH_POLICY
    active_indicator_policy = (
        indicator_policy or DEFAULT_TEMPORAL_HEALTH_INDICATOR_POLICY
    )
    points = causal_temporal_health_points(
        rows,
        score_min=score_min,
        score_max=score_max,
        health_policy=active_health_policy,
        indicator_policy=active_indicator_policy,
    )
    metrics = health_indicator_metrics(
        rows,
        points,
        health_policy=active_health_policy,
        indicator_policy=active_indicator_policy,
        x_key=x_key,
    )
    return {
        "policy_id": active_indicator_policy.policy_id,
        "health_policy_id": active_health_policy.policy_id,
        "alert_policy_id": active_health_policy.alert_policy.policy_id,
        "points": points,
        "metrics": metrics,
    }


def causal_temporal_health_points(
    rows: list[Mapping[str, Any]],
    *,
    score_min: float | None,
    score_max: float | None,
    health_policy: TemporalHealthPolicy | None = None,
    indicator_policy: TemporalHealthIndicatorPolicy | None = None,
) -> list[dict[str, Any]]:
    """Proyecta estados/HI causales sin calcular resumenes retrospectivos.

    El resultado de cada posicion depende solo de esa fila y de su prefijo.
    Esta frontera permite al replay reutilizar exactamente la semantica del
    batch sin producir tendencia global, separacion inicial-final ni ningun
    otro dato que requiera observar el sufijo de la trayectoria.
    """

    active_health_policy = health_policy or DEFAULT_TEMPORAL_HEALTH_POLICY
    active_indicator_policy = (
        indicator_policy or DEFAULT_TEMPORAL_HEALTH_INDICATOR_POLICY
    )
    base_points = [
        temporal_health_values(
            row,
            score_min=score_min,
            score_max=score_max,
            policy=active_health_policy,
        )
        for row in rows
    ]
    raw_health = [optional_float(point.get("health_index")) for point in base_points]
    segment_ids = [
        int(optional_float(row.get("temporal_segment_id")) or 0)
        for row in rows
    ]
    smoothed_health = causal_moving_average(
        raw_health,
        active_indicator_policy.smoothing_window,
        segment_ids=segment_ids,
    )
    smoothed_risk = [
        None if value is None else clamp(100.0 - value)
        for value in smoothed_health
    ]
    trends = causal_differences(
        smoothed_health,
        active_indicator_policy.trend_window,
        segment_ids=segment_ids,
    )
    points = [
        {
            **base_point,
            "health_index_raw": raw_health[index],
            "health_index_smoothed": smoothed_health[index],
            "risk_index_smoothed": smoothed_risk[index],
            "health_trend": trends[index],
            "dominant_evidence": _point_dominant_evidence(
                rows[index],
                base_point,
                trends[index],
            ),
            "health_indicator_policy_id": active_indicator_policy.policy_id,
        }
        for index, base_point in enumerate(base_points)
    ]
    return points


def health_indicator_metrics(
    rows: list[Mapping[str, Any]],
    points: list[Mapping[str, Any]],
    *,
    health_policy: TemporalHealthPolicy | None = None,
    indicator_policy: TemporalHealthIndicatorPolicy | None = None,
    x_key: str = "relative_life",
) -> dict[str, Any]:
    """Resume calidad temporal del Health Indicator de una trayectoria."""

    active_health_policy = health_policy or DEFAULT_TEMPORAL_HEALTH_POLICY
    active_indicator_policy = (
        indicator_policy or DEFAULT_TEMPORAL_HEALTH_INDICATOR_POLICY
    )
    values = [optional_float(point.get("health_index_smoothed")) for point in points]
    raw_values = [optional_float(point.get("health_index_raw")) for point in points]
    x_values = [optional_float(row.get(x_key)) for row in rows]
    initial, final = _early_late_health_means(rows, values, active_health_policy)
    drop = _optional_difference(initial, final)
    drop_ratio = _optional_ratio(drop, initial)
    spearman = spearman_correlation(x_values, values)
    slope = linear_slope(x_values, values)
    trend_strength = None if spearman is None else max(0.0, -spearman)
    segment_ids = [
        int(optional_float(row.get("temporal_segment_id")) or 0)
        for row in rows
    ]
    monotonicity = decreasing_monotonicity(
        values,
        segment_ids=segment_ids,
    )
    robustness = health_robustness(raw_values, values)
    nominal_volatility = nominal_health_volatility(
        rows,
        raw_values,
        active_health_policy,
    )
    score = composite_health_indicator_score(
        drop=drop,
        monotonicity=monotonicity,
        robustness=robustness,
        trend_strength=trend_strength,
    )
    dominant_evidence = _dominant_evidence(points)
    return {
        "health_indicator_policy_id": active_indicator_policy.policy_id,
        "initial_health_index": initial,
        "final_health_index": final,
        "health_index_drop": drop,
        "health_index_drop_ratio": drop_ratio,
        "health_slope": slope,
        "health_trend_spearman": spearman,
        "health_degradation_trend_strength": trend_strength,
        "health_monotonicity": monotonicity,
        "health_robustness": robustness,
        "health_nominal_volatility": nominal_volatility,
        "health_indicator_score": score,
        "health_dominant_evidence": dominant_evidence,
        "health_indicator_status": _health_indicator_status(
            drop,
            trend_strength,
            active_indicator_policy,
        ),
    }


def temporal_health_population_metrics(
    run_metrics: list[Mapping[str, Any]],
) -> dict[str, float | None]:
    """Calcula trendability/prognosability cuando hay varias trayectorias."""

    slopes = [
        value
        for value in (
            optional_float(item.get("health_slope")) for item in run_metrics
        )
        if value is not None
    ]
    final_health = [
        value
        for value in (
            optional_float(item.get("final_health_index")) for item in run_metrics
        )
        if value is not None
    ]
    initial_health = [
        value
        for value in (
            optional_float(item.get("initial_health_index")) for item in run_metrics
        )
        if value is not None
    ]
    return {
        "health_trendability": trendability_from_slopes(slopes),
        "health_prognosability": prognosability_from_health(
            initial_health,
            final_health,
        ),
    }


def causal_moving_average(
    values: list[float | None],
    window: int,
    *,
    segment_ids: list[int] | None = None,
) -> list[float | None]:
    """Media movil trailing: usa solo presente y pasado."""

    if segment_ids is not None and len(segment_ids) != len(values):
        raise ValueError("segment_ids must match values length")
    bounded_window = max(1, window)
    smoothed: list[float | None] = []
    for index in range(len(values)):
        start = max(0, index - bounded_window + 1)
        if segment_ids is not None:
            while start < index and segment_ids[start] != segment_ids[index]:
                start += 1
        window_values = [
            value for value in values[start : index + 1] if value is not None
        ]
        smoothed.append(None if not window_values else sum(window_values) / len(window_values))
    return smoothed


def causal_differences(
    values: list[float | None],
    window: int,
    *,
    segment_ids: list[int] | None = None,
) -> list[float | None]:
    """Diferencia causal frente a un punto pasado dentro de la ventana."""

    if segment_ids is not None and len(segment_ids) != len(values):
        raise ValueError("segment_ids must match values length")
    bounded_window = max(1, window)
    diffs: list[float | None] = []
    for index, value in enumerate(values):
        previous_index = max(0, index - bounded_window + 1)
        if (
            segment_ids is not None
            and segment_ids[previous_index] != segment_ids[index]
        ):
            previous_index = index
        previous = values[previous_index]
        if index == previous_index or value is None or previous is None:
            diffs.append(None)
        else:
            diffs.append(value - previous)
    return diffs


def decreasing_monotonicity(
    values: list[float | None],
    *,
    segment_ids: list[int] | None = None,
) -> float | None:
    """Proporcion de cambios no positivos del HI suavizado."""

    if segment_ids is not None and len(segment_ids) != len(values):
        raise ValueError("segment_ids must match values length")
    diffs: list[float] = []
    previous_value: float | None = None
    previous_segment: int | None = None
    for index, value in enumerate(values):
        if value is None:
            continue
        segment = 0 if segment_ids is None else segment_ids[index]
        if previous_value is not None and previous_segment == segment:
            difference = value - previous_value
            if difference != 0.0:
                diffs.append(difference)
        previous_value = value
        previous_segment = segment
    if not diffs:
        return None
    return sum(1 for value in diffs if value <= 0.0) / len(diffs)


def health_robustness(
    raw_values: list[float | None],
    smoothed_values: list[float | None],
) -> float | None:
    """Mide estabilidad como cercania entre HI bruto y suavizado."""

    residuals = [
        abs(raw - smooth)
        for raw, smooth in zip(raw_values, smoothed_values, strict=False)
        if raw is not None and smooth is not None
    ]
    if not residuals:
        return None
    return clamp(1.0 - (sum(residuals) / len(residuals)) / 100.0, 0.0, 1.0)


def nominal_health_volatility(
    rows: list[Mapping[str, Any]],
    values: list[float | None],
    health_policy: TemporalHealthPolicy,
) -> float | None:
    nominal = [
        value
        for row, value in zip(rows, values, strict=False)
        if value is not None
        and (
            optional_float(row.get("relative_life")) is not None
            and optional_float(row.get("relative_life"))
            <= health_policy.alert_policy.nominal_relative_life_limit
        )
    ]
    if not nominal:
        fallback_size = max(1, math.ceil(len(values) / 3))
        nominal = [value for value in values[:fallback_size] if value is not None]
    return standard_deviation(nominal)


def spearman_correlation(
    x_values: list[float | None],
    y_values: list[float | None],
) -> float | None:
    pairs = [
        (x, y)
        for x, y in zip(x_values, y_values, strict=False)
        if x is not None and y is not None
    ]
    if len(pairs) < 2:
        return None
    x, y = zip(*pairs, strict=False)
    if len(set(x)) < 2 or len(set(y)) < 2:
        return None
    return pearson_correlation(rank_values(list(x)), rank_values(list(y)))


def linear_slope(
    x_values: list[float | None],
    y_values: list[float | None],
) -> float | None:
    pairs = [
        (x, y)
        for x, y in zip(x_values, y_values, strict=False)
        if x is not None and y is not None
    ]
    if len(pairs) < 2:
        return None
    x, y = zip(*pairs, strict=False)
    if len(set(x)) < 2:
        return None
    x_mean = sum(x) / len(x)
    y_mean = sum(y) / len(y)
    denominator = sum((value - x_mean) ** 2 for value in x)
    if denominator == 0:
        return None
    return sum((left - x_mean) * (right - y_mean) for left, right in pairs) / denominator


def pearson_correlation(
    x_values: list[float],
    y_values: list[float],
) -> float | None:
    if len(x_values) != len(y_values) or len(x_values) < 2:
        return None
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    x_dev = [value - x_mean for value in x_values]
    y_dev = [value - y_mean for value in y_values]
    denominator = math.sqrt(sum(value**2 for value in x_dev)) * math.sqrt(
        sum(value**2 for value in y_dev)
    )
    if denominator == 0:
        return None
    return sum(left * right for left, right in zip(x_dev, y_dev, strict=False)) / denominator


def rank_values(values: list[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        average_rank = (index + end - 1) / 2.0
        for original_index, _value in ordered[index:end]:
            ranks[original_index] = average_rank
        index = end
    return ranks


def standard_deviation(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def trendability_from_slopes(slopes: list[float]) -> float | None:
    if len(slopes) < 2:
        return None
    signs = [1 if slope > 0 else -1 if slope < 0 else 0 for slope in slopes]
    counts = Counter(signs)
    return max(counts.values()) / len(signs)


def prognosability_from_health(
    initial_health: list[float],
    final_health: list[float],
) -> float | None:
    if len(initial_health) < 2 or len(final_health) < 2:
        return None
    final_std = standard_deviation(final_health)
    if final_std is None:
        return None
    reference_range = max(initial_health) - min(final_health)
    if reference_range <= 0:
        return None
    return clamp(1.0 - final_std / reference_range, 0.0, 1.0)


def composite_health_indicator_score(
    *,
    drop: float | None,
    monotonicity: float | None,
    robustness: float | None,
    trend_strength: float | None,
) -> float | None:
    values = [
        value
        for value in [
            None if drop is None else clamp(drop / 100.0, 0.0, 1.0),
            monotonicity,
            robustness,
            trend_strength,
        ]
        if value is not None
    ]
    if not values:
        return None
    return sum(values) / len(values)


def _numeric_values(
    rows: list[Mapping[str, Any]],
    key: str,
) -> list[float]:
    return [
        value
        for value in (optional_float(row.get(key)) for row in rows)
        if value is not None
    ]


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _linear_percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower_index = math.floor(position)
    upper_index = math.ceil(position)
    if lower_index == upper_index:
        return ordered[lower_index]
    weight = position - lower_index
    return ordered[lower_index] + weight * (
        ordered[upper_index] - ordered[lower_index]
    )


def _population_standard_deviation(values: list[float]) -> float | None:
    if not values:
        return None
    mean = sum(values) / len(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def _optional_identifier(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, float) and not math.isfinite(value):
        return None
    text = str(value).strip()
    return None if not text else text


def _stable_identifier(value: Any, fallback: str) -> str:
    return _optional_identifier(value) or fallback


def _temporal_row_sort_key(
    row: Mapping[str, Any],
    original_index: int,
) -> tuple[int, float, int]:
    seconds = _temporal_row_seconds(row)
    return (
        1 if seconds is None else 0,
        float(original_index) if seconds is None else seconds,
        original_index,
    )


def _temporal_row_seconds(row: Mapping[str, Any]) -> float | None:
    timestamp = _optional_identifier(row.get("timestamp_start"))
    if timestamp is not None:
        try:
            return datetime.fromisoformat(
                timestamp.replace("Z", "+00:00")
            ).timestamp()
        except ValueError:
            pass
    for key in ("time_since_start_seconds", "window_index"):
        value = optional_float(row.get(key))
        if value is not None:
            return value
    return None


def _text_values(rows: list[Mapping[str, Any]], key: str) -> list[str]:
    return [
        value
        for value in (_optional_identifier(row.get(key)) for row in rows)
        if value is not None
    ]


def optional_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result


def clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, value))


def _early_late_health_means(
    rows: list[Mapping[str, Any]],
    values: list[float | None],
    health_policy: TemporalHealthPolicy,
) -> tuple[float | None, float | None]:
    early = [
        value
        for row, value in zip(rows, values, strict=False)
        if value is not None
        and (
            optional_float(row.get("relative_life")) is not None
            and optional_float(row.get("relative_life"))
            <= health_policy.alert_policy.early_relative_life_limit
        )
    ]
    late = [
        value
        for row, value in zip(rows, values, strict=False)
        if value is not None
        and (
            optional_float(row.get("relative_life")) is not None
            and optional_float(row.get("relative_life"))
            >= health_policy.alert_policy.late_relative_life_limit
        )
    ]
    if not early:
        head_size = max(1, math.ceil(len(values) / 3))
        early = [value for value in values[:head_size] if value is not None]
    if not late:
        tail_size = max(1, math.ceil(len(values) / 3))
        late = [value for value in values[-tail_size:] if value is not None]
    return _mean(early), _mean(late)


def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _optional_difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def _optional_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or abs(denominator) < 1e-12:
        return None
    return numerator / denominator


def _point_dominant_evidence(
    row: Mapping[str, Any],
    point: Mapping[str, Any],
    trend: float | None,
) -> str:
    predicted = optional_int(row.get("predicted_anomaly"))
    score_ratio = optional_float(point.get("score_ratio"))
    if predicted == 1 and score_ratio is not None and score_ratio >= 1.0:
        return "score_above_threshold"
    if predicted == 1:
        return "model_alert"
    if trend is not None and trend <= -5.0:
        return "health_decline"
    if score_ratio is not None and score_ratio >= 0.8:
        return "score_near_threshold"
    return "stable_health"


def _dominant_evidence(points: list[Mapping[str, Any]]) -> str | None:
    values = [
        str(point["dominant_evidence"])
        for point in points
        if point.get("dominant_evidence") is not None
    ]
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]


def _health_indicator_status(
    drop: float | None,
    trend_strength: float | None,
    policy: TemporalHealthIndicatorPolicy,
) -> str:
    if drop is None:
        return "insufficient_health_indicator"
    if drop >= policy.min_drop_for_degradation and (
        trend_strength is None or trend_strength > 0.0
    ):
        return "degrading_health_indicator"
    if abs(drop) < policy.min_drop_for_degradation:
        return "stable_or_inconclusive_health_indicator"
    return "non_degrading_health_indicator"
