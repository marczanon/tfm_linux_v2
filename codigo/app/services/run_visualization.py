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
    AgentOperationalRecommendation,
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


METRIC_LABELS: dict[str, tuple[str, bool, str, str | None]] = {
    "precision": ("Precision", True, "ratio", None),
    "recall": ("Recall", True, "ratio", None),
    "f1_score": ("F1", True, "ratio", None),
    "false_positive_rate": ("FPR", False, "ratio", None),
    "roc_auc": ("ROC-AUC", True, "ratio", None),
    "pr_auc": ("PR-AUC", True, "ratio", None),
}

DEGRADATION_METRIC_LABELS: dict[str, tuple[str, bool, str, str | None]] = {
    "detected_before_failure_rate": (
        "Deteccion antes de fallo",
        True,
        "ratio",
        "Proporcion de trayectorias detectadas antes del fallo historico.",
    ),
    "mean_lead_time_to_failure": (
        "Lead time medio",
        True,
        "seconds",
        "Tiempo medio disponible entre primer aviso y fallo historico.",
    ),
    "mean_false_alarm_rate_nominal": (
        "Falsas alarmas nominales",
        False,
        "ratio",
        "Alertas durante el tramo nominal o temprano de la trayectoria.",
    ),
    "mean_score_trend_spearman": (
        "Tendencia del score",
        True,
        "score",
        "Correlacion entre score de anomalia y avance de vida relativa.",
    ),
    "missed_runs": (
        "Fallos perdidos",
        False,
        "count",
        "Trayectorias que llegaron a fallo sin alerta previa.",
    ),
    "mean_initial_final_separation": (
        "Separacion inicio-final",
        True,
        "score",
        "Diferencia media entre score inicial y score final.",
    ),
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
PERSISTENT_ALERT_MIN_WINDOWS = 3


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
    summary_metrics = _safe_dict(_read_json(Path(snapshot.metrics_path)))
    full_metrics = _full_metrics(summary_metrics, source_paths)
    run_context = _run_context(snapshot.state_path, summary_metrics, full_metrics)
    metrics = _binary_metrics(summary_metrics)
    primary_metrics, auxiliary_metrics = _visualization_metric_groups(
        run_context["supervision_profile"],
        run_context["metric_families"],
        metrics,
        full_metrics,
    )
    warnings: list[str] = []
    common_payload = {
        "run_id": snapshot.run_id,
        "dataset": snapshot.dataset,
        "supervision_profile": run_context["supervision_profile"],
        "label_source": run_context["label_source"],
        "label_granularity": run_context["label_granularity"],
        "model_name": run_context["model_name"],
        "metric_families": run_context["metric_families"],
        "metrics": metrics,
        "primary_metrics": primary_metrics,
        "auxiliary_metrics": auxiliary_metrics,
        "binary_metric_context": run_context["binary_metric_context"],
        "projection_role": _projection_role(run_context["supervision_profile"]),
        "projection_explanation": _projection_explanation(
            run_context["supervision_profile"]
        ),
        "agent_recommendation": _agent_recommendation(
            snapshot.state_path,
            run_context["supervision_profile"],
        ),
    }

    features_path = source_paths.get("features")
    predictions_path = source_paths.get("predictions")
    temporal_series = _safe_temporal_series(predictions_path, bounded_max_points)
    if features_path is None:
        warnings.append(
            "La proyeccion 2D requiere al menos el artefacto de features."
        )
        return RunVisualizationData(
            **common_payload,
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
            **common_payload,
            projection_available=False,
            temporal_series=temporal_series,
            source_paths=source_paths,
            warnings=warnings,
        )

    return RunVisualizationData(
        **common_payload,
        projection_available=True,
        projection_points=projection["points"],
        projection_boundary=projection["boundary"],
        temporal_series=temporal_series,
        n_points_total=projection["n_total"],
        n_points_sampled=len(projection["points"]),
        source_paths=source_paths,
        warnings=warnings,
    )


def build_temporal_series_from_predictions(
    predictions_path: str | None,
    *,
    max_points: int = 900,
) -> TemporalSeriesData:
    """Construye la serie temporal reutilizable por UI y herramientas agenticas."""

    bounded_max_points = max(50, min(max_points, 2500))
    return _safe_temporal_series(predictions_path, bounded_max_points)


def _binary_metrics(data: dict[str, Any]) -> list[VisualizationMetric]:
    metrics: list[VisualizationMetric] = []
    for name, (label, higher_is_better, value_kind, note) in METRIC_LABELS.items():
        value = data.get(name)
        metrics.append(
            VisualizationMetric(
                name=name,
                label=label,
                value=None if value is None else float(value),
                higher_is_better=higher_is_better,
                metric_family="binary_classification",
                value_kind=value_kind,
                note=note,
            )
        )
    return metrics


def _visualization_metric_groups(
    supervision_profile: str | None,
    metric_families: list[str],
    binary_metrics: list[VisualizationMetric],
    full_metrics: dict[str, Any],
) -> tuple[list[VisualizationMetric], list[VisualizationMetric]]:
    degradation_metrics = _degradation_metrics(full_metrics)
    is_run_to_failure = (
        supervision_profile == "run_to_failure_degradation"
        or "run_to_failure_degradation" in metric_families
    )
    if is_run_to_failure:
        return degradation_metrics, binary_metrics
    return binary_metrics, degradation_metrics


def _degradation_metrics(full_metrics: dict[str, Any]) -> list[VisualizationMetric]:
    payload = full_metrics.get("degradation_metrics")
    data = payload if isinstance(payload, dict) else {}
    if data.get("available") is False:
        return []

    metrics: list[VisualizationMetric] = []
    for name, (
        label,
        higher_is_better,
        value_kind,
        note,
    ) in DEGRADATION_METRIC_LABELS.items():
        value = data.get(name)
        if value is None:
            continue
        metrics.append(
            VisualizationMetric(
                name=name,
                label=label,
                value=float(value),
                higher_is_better=higher_is_better,
                metric_family="run_to_failure_degradation",
                value_kind=value_kind,
                note=note,
            )
        )
    return metrics


def _full_metrics(
    summary_metrics: dict[str, Any],
    source_paths: dict[str, str],
) -> dict[str, Any]:
    candidates = [
        source_paths.get("metrics"),
        summary_metrics.get("metrics_path"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str) and candidate:
            payload = _read_json(Path(candidate))
            if isinstance(payload, dict):
                return payload
    return {}


def _run_context(
    state_path: str,
    summary_metrics: dict[str, Any],
    full_metrics: dict[str, Any],
) -> dict[str, Any]:
    state = _safe_dict(_read_json(Path(state_path)))
    project_context = _safe_dict(state.get("project_context"))
    modeling_config = _safe_dict(state.get("modeling_config"))
    binary_context = _safe_dict(full_metrics.get("binary_metric_context"))
    metric_families = _metric_families(summary_metrics, full_metrics)

    return {
        "supervision_profile": _optional_str(
            project_context.get("supervision_profile")
        ),
        "label_source": _optional_str(
            project_context.get("label_source") or binary_context.get("label_source")
        ),
        "label_granularity": _optional_str(
            project_context.get("label_granularity")
            or binary_context.get("label_granularity")
        ),
        "model_name": _optional_str(modeling_config.get("model_name")),
        "metric_families": metric_families,
        "binary_metric_context": {
            str(key): str(value)
            for key, value in binary_context.items()
            if value is not None
        },
    }


def _metric_families(
    summary_metrics: dict[str, Any],
    full_metrics: dict[str, Any],
) -> list[str]:
    full_value = full_metrics.get("metric_families")
    if isinstance(full_value, list):
        return [str(item) for item in full_value if str(item).strip()]

    extra = _safe_dict(summary_metrics.get("extra"))
    summary_value = extra.get("metric_families")
    if isinstance(summary_value, str):
        return [
            item.strip()
            for item in summary_value.split(",")
            if item.strip()
        ]
    if isinstance(summary_value, list):
        return [str(item) for item in summary_value if str(item).strip()]
    return []


def _projection_role(supervision_profile: str | None) -> str:
    if supervision_profile == "binary_fault_classification":
        return "primary"
    return "diagnostic"


def _projection_explanation(supervision_profile: str | None) -> str:
    if supervision_profile == "run_to_failure_degradation":
        return (
            "Mapa PCA diagnostico: proyecta las ventanas de NASA/run-to-failure "
            "desde sus features y colorea predicciones. La elipse no es la "
            "frontera real del modelo ni la metrica principal; el criterio "
            "principal en este perfil es temporal."
        )
    return (
        "Mapa PCA 2D de ventanas/features. La frontera es una aproximacion "
        "visual sobre predicciones normales; el umbral real se aplica en el "
        "espacio original del modelo."
    )


def _agent_recommendation(
    state_path: str | None,
    supervision_profile: str | None,
) -> AgentOperationalRecommendation:
    state = _safe_dict(_read_json(Path(state_path))) if state_path else {}
    decisions = _agent_decisions_from_state(state)
    evaluator = _latest_decision(decisions, "evaluator")
    modeler = _latest_decision(decisions, "modeler")
    if evaluator is None:
        return AgentOperationalRecommendation(
            available=False,
            status="unavailable",
            title="Sin recomendacion agentica",
            summary=(
                "La run aun no contiene una decision persistida del evaluador."
            ),
            modeler_summary=_modeler_strategy_summary(modeler),
        )

    evaluation = _safe_dict(evaluator.get("evaluation"))
    approved = evaluation.get("approved")
    next_action = _optional_str(evaluation.get("next_action"))
    limitations = [
        str(item)
        for item in evaluation.get("limitations", [])
        if item is not None
    ]
    operational_assessment = _optional_str(evaluator.get("operational_assessment"))
    summary = (
        operational_assessment
        or _optional_str(evaluation.get("summary"))
        or _optional_str(evaluator.get("rationale"))
        or "Decision agentica persistida sin resumen textual."
    )
    is_temporal = supervision_profile == "run_to_failure_degradation"
    status = _recommendation_status(
        approved=approved,
        next_action=next_action,
        is_temporal=is_temporal,
        guardrails=evaluator.get("temporal_guardrail_checks"),
        limitations=limitations,
    )
    return AgentOperationalRecommendation(
        available=True,
        source_agent="evaluator",
        decision_id=_optional_str(evaluator.get("decision_id")),
        status=status,
        title=_recommendation_title(status, is_temporal=is_temporal),
        summary=summary,
        confidence=_optional_float(evaluator.get("confidence")),
        next_action=next_action,
        operational_assessment=operational_assessment,
        evidence_refs=_string_list(evaluator.get("evidence_refs"))[:8],
        tool_names=_string_list(evaluator.get("tool_names"))[:6],
        limitations=limitations[:4],
        debate_points=_string_list(evaluator.get("temporal_debate_points"))[:5],
        guardrail_checks=_string_list(evaluator.get("temporal_guardrail_checks"))[:8],
        modeler_summary=_modeler_strategy_summary(modeler),
    )


def _agent_decisions_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    messages = state.get("messages")
    if not isinstance(messages, list):
        return []
    decisions: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            continue
        if message.get("role") not in {"agent", "supervisor"}:
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            decisions.append(payload)
    return decisions


def _latest_decision(
    decisions: list[dict[str, Any]],
    agent_name: str,
) -> dict[str, Any] | None:
    for decision in reversed(decisions):
        if decision.get("agent_name") == agent_name:
            return decision
    return None


def _recommendation_status(
    *,
    approved: Any,
    next_action: str | None,
    is_temporal: bool,
    guardrails: Any,
    limitations: list[str],
) -> str:
    if next_action in {"retry_with_new_config", "request_human_review"}:
        return "needs_revision"
    if next_action == "stop":
        return "blocked"
    if approved is False:
        return "needs_revision"
    if approved is True:
        if limitations:
            return "caution"
        if is_temporal and not _string_list(guardrails):
            return "caution"
        return "approved"
    return "caution"


def _recommendation_title(status: str, *, is_temporal: bool) -> str:
    if status == "approved":
        return (
            "Operacion defendible con cautelas"
            if is_temporal
            else "Run aprobada por el evaluador"
        )
    if status == "needs_revision":
        return "Requiere nueva estrategia"
    if status == "blocked":
        return "Bloqueada por criterio agentico"
    if status == "caution":
        return "Interpretacion con cautela"
    return "Sin recomendacion agentica"


def _modeler_strategy_summary(modeler: dict[str, Any] | None) -> str | None:
    if modeler is None:
        return None
    strategy = _safe_dict(modeler.get("decision_strategy"))
    model_config = _safe_dict(modeler.get("modeling_config"))
    model_name = _optional_str(model_config.get("model_name"))
    hypothesis = _optional_str(strategy.get("hypothesis"))
    alert_policy = _optional_str(strategy.get("alert_policy"))
    parts = []
    if model_name:
        parts.append(f"Modelo: {model_name}.")
    if hypothesis:
        parts.append(hypothesis)
    if alert_policy:
        parts.append(f"Politica: {alert_policy}")
    return " ".join(parts) if parts else _optional_str(modeler.get("rationale"))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None and str(item).strip()]


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
    first_persistent_alert = state_counts["first_persistent_alert"]
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
        first_persistent_alert_x=(
            None
            if first_persistent_alert is None
            else _optional_float(first_persistent_alert[x_axis])
        ),
        first_persistent_alert_time=(
            None if first_persistent_alert is None else _row_time(first_persistent_alert)
        ),
        first_persistent_alert_time_to_failure_seconds=(
            None
            if first_persistent_alert is None
            else _optional_float(first_persistent_alert.get("time_to_failure_seconds"))
        ),
        persistent_alert_min_windows=PERSISTENT_ALERT_MIN_WINDOWS,
        failure_x=failure["x"],
        failure_time=failure["time"],
        failure_reference=failure["reference"],
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
        isolated_alert_points=state_counts["isolated_alert_points"],
        alert_episodes=state_counts["alert_episodes"],
        longest_alert_streak=state_counts["longest_alert_streak"],
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
) -> dict[str, int | pd.Series | None]:
    states = [
        _health_values(row, score_min, score_max)["health_state"]
        for _, row in data.iterrows()
    ]
    alert_flags = [state in {"warning", "critical"} for state in states]
    alert_runs = _true_runs(alert_flags)
    persistent_runs = [
        item
        for item in alert_runs
        if item["length"] >= PERSISTENT_ALERT_MIN_WINDOWS
    ]
    first_persistent_index = (
        None if not persistent_runs else persistent_runs[0]["start"]
    )
    return {
        "alert_points": sum(1 for state in states if state in {"warning", "critical"}),
        "warning_points": sum(1 for state in states if state == "warning"),
        "critical_points": sum(1 for state in states if state == "critical"),
        "isolated_alert_points": sum(
            item["length"]
            for item in alert_runs
            if item["length"] < PERSISTENT_ALERT_MIN_WINDOWS
        ),
        "alert_episodes": len(alert_runs),
        "longest_alert_streak": (
            0 if not alert_runs else max(item["length"] for item in alert_runs)
        ),
        "first_persistent_alert": (
            None if first_persistent_index is None else data.iloc[first_persistent_index]
        ),
    }


def _true_runs(flags: list[bool]) -> list[dict[str, int]]:
    runs: list[dict[str, int]] = []
    start: int | None = None
    for index, flag in enumerate(flags):
        if flag and start is None:
            start = index
        elif not flag and start is not None:
            runs.append({"start": start, "length": index - start})
            start = None
    if start is not None:
        runs.append({"start": start, "length": len(flags) - start})
    return runs


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
        return {"x": None, "time": None, "reference": "unavailable"}
    times = data["time_to_failure_seconds"].dropna()
    if times.empty:
        return {"x": None, "time": None, "reference": "unavailable"}
    closest = data.loc[times.abs().idxmin()]
    if x_axis == "relative_life":
        return {"x": 1.0, "time": _row_time(closest), "reference": "historic_replay"}
    if x_axis == "time_since_start_seconds":
        starts = pd.to_numeric(
            data.get("time_since_start_seconds"),
            errors="coerce",
        )
        failures = starts + data["time_to_failure_seconds"]
        failures = failures.dropna()
        if not failures.empty:
            return {
                "x": float(failures.median()),
                "time": _row_time(closest),
                "reference": "historic_replay",
            }
    return {
        "x": _optional_float(closest.get(x_axis)),
        "time": _row_time(closest),
        "reference": "historic_replay",
    }


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


def _safe_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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
