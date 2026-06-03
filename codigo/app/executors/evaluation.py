"""Evaluacion determinista de predicciones de anomalias."""

from __future__ import annotations

import json
import math
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from codigo.app.schemas.executor_results import EvaluationExecutorResult
from codigo.app.schemas.state import ArtifactRef, PipelineError


REQUIRED_COLUMNS = {
    "window_id",
    "split",
    "label",
    "target",
    "anomaly_score",
    "predicted_anomaly",
}

TEMPORAL_DEGRADATION_COLUMNS = {
    "relative_life",
    "anomaly_score",
    "predicted_anomaly",
}

TEMPORAL_NUMERIC_COLUMNS = [
    "relative_life",
    "time_since_start_seconds",
    "time_to_failure_seconds",
    "anomaly_score",
    "predicted_anomaly",
]

NOMINAL_RELATIVE_LIFE_LIMIT = 0.4
EARLY_RELATIVE_LIFE_LIMIT = 0.33
LATE_RELATIVE_LIFE_LIMIT = 0.67


def generate_evaluation_report(
    predictions_path: str | Path = "codigo/models/cwru_bearing/predictions.csv",
    output_dir: str | Path = "codigo/reports/cwru_bearing/evaluation",
    primary_split: str = "test",
) -> EvaluationExecutorResult:
    """Calcula metricas y devuelve un resultado estructurado."""

    started_at = datetime.now(UTC)
    output = Path(output_dir)
    metrics_path = output / "metrics.json"
    report_path = output / "evaluation_summary.md"
    try:
        summary = evaluate_predictions(predictions_path, output, primary_split)
        artifacts = [
            ArtifactRef(
                name="evaluation_metrics",
                artifact_type="metrics",
                path=summary["metrics_path"],
                producer="evaluator",
                metadata={
                    "primary_split": primary_split,
                    "f1_score": summary["primary_metrics"]["f1_score"],
                    "metric_families": ",".join(summary["metric_families"]),
                    "degradation_available": summary["degradation_metrics"][
                        "available"
                    ],
                },
            ),
            ArtifactRef(
                name="evaluation_summary",
                artifact_type="report",
                path=summary["report_fragment_path"],
                producer="evaluator",
                metadata={"n_predictions": summary["n_predictions"]},
            ),
        ]
        return EvaluationExecutorResult(
            executor_name="evaluation",
            status="success",
            message="Evaluation metrics generated.",
            artifacts=artifacts,
            errors=[],
            state_updates={"metrics_path": summary["metrics_path"]},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            metrics_path=summary["metrics_path"],
            report_fragment_path=summary["report_fragment_path"],
        )
    except Exception as exc:
        error = PipelineError(
            stage="evaluation",
            node="evaluator",
            message=str(exc),
            recoverable=True,
        )
        return EvaluationExecutorResult(
            executor_name="evaluation",
            status="failed",
            message="Evaluation failed.",
            artifacts=[],
            errors=[error],
            state_updates={},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            metrics_path=str(metrics_path),
            report_fragment_path=str(report_path),
        )


def evaluate_predictions(
    predictions_path: str | Path,
    output_dir: str | Path,
    primary_split: str = "test",
) -> dict[str, Any]:
    """Evalua las predicciones y guarda metricas reproducibles."""

    data = pd.read_csv(predictions_path)
    missing = REQUIRED_COLUMNS - set(data.columns)
    if missing:
        raise ValueError(f"missing prediction columns: {', '.join(sorted(missing))}")
    if primary_split not in set(data["split"]):
        raise ValueError(f"primary_split not found: {primary_split}")

    data["target"] = data["target"].astype(int)
    data["predicted_anomaly"] = data["predicted_anomaly"].astype(int)
    data["anomaly_score"] = data["anomaly_score"].astype(float)
    _validate_prediction_values(data)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    metrics_by_split = {
        split: _metrics_for_split(group)
        for split, group in data.groupby("split", sort=True)
    }
    primary_metrics = metrics_by_split[primary_split]
    degradation_metrics = _degradation_metrics(data)
    metric_families = ["binary_classification"]
    if degradation_metrics["available"]:
        metric_families.append("run_to_failure_degradation")
    summary = {
        "predictions_path": str(predictions_path),
        "metrics_path": str(output / "metrics.json"),
        "report_fragment_path": str(output / "evaluation_summary.md"),
        "generated_at": datetime.now(UTC).isoformat(),
        "primary_split": primary_split,
        "metric_families": metric_families,
        "binary_metric_context": _binary_metric_context(data),
        "primary_metrics": primary_metrics,
        "metrics_by_split": metrics_by_split,
        "degradation_metrics": degradation_metrics,
        "n_predictions": int(len(data)),
        "split_counts": dict(Counter(data["split"])),
        "label_counts": dict(Counter(data["label"])),
    }
    Path(summary["metrics_path"]).write_text(
        json.dumps(summary, indent=2),
        encoding="utf-8",
    )
    Path(summary["report_fragment_path"]).write_text(
        _report_markdown(summary),
        encoding="utf-8",
    )
    return summary


def _metrics_for_split(data: pd.DataFrame) -> dict[str, Any]:
    y_true = data["target"].to_numpy(dtype=int)
    y_pred = data["predicted_anomaly"].to_numpy(dtype=int)
    scores = data["anomaly_score"].to_numpy(dtype=float)
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    return {
        "n_samples": int(len(data)),
        "label_counts": dict(Counter(data["label"])),
        "predicted_counts": {str(key): value for key, value in Counter(y_pred).items()},
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1_score": float(f1_score(y_true, y_pred, zero_division=0)),
        "roc_auc": _score_if_defined(roc_auc_score, y_true, scores),
        "pr_auc": _score_if_defined(average_precision_score, y_true, scores),
        "false_positive_rate": None if (fp + tn) == 0 else float(fp / (fp + tn)),
        "confusion_matrix": {
            "tn": int(tn),
            "fp": int(fp),
            "fn": int(fn),
            "tp": int(tp),
        },
    }


def _degradation_metrics(data: pd.DataFrame) -> dict[str, Any]:
    """Calcula metricas temporales si las predicciones contienen una trayectoria."""

    missing = TEMPORAL_DEGRADATION_COLUMNS - set(data.columns)
    if missing:
        return _unavailable_degradation_metrics(
            f"missing temporal columns: {', '.join(sorted(missing))}"
        )

    temporal = data.copy()
    for column in TEMPORAL_NUMERIC_COLUMNS:
        if column in temporal.columns:
            temporal[column] = pd.to_numeric(temporal[column], errors="coerce")
    temporal = temporal.dropna(
        subset=["relative_life", "anomaly_score", "predicted_anomaly"]
    )
    if temporal.empty:
        return _unavailable_degradation_metrics(
            "temporal columns are present but contain no usable numeric values"
        )

    if "run_id" not in temporal.columns:
        temporal["run_id"] = "_single_run"
    temporal["run_id"] = temporal["run_id"].apply(_stable_run_id)
    temporal["predicted_anomaly"] = temporal["predicted_anomaly"].astype(int)

    run_metrics = [
        _degradation_metrics_for_run(str(run_id), group)
        for run_id, group in temporal.groupby("run_id", sort=True)
    ]
    detected_runs = [
        item for item in run_metrics if item["detected_before_failure"] is True
    ]
    missed_runs = [item for item in run_metrics if item["missed_failure"] is True]
    lead_times = [item["lead_time_to_failure"] for item in run_metrics]
    false_alarm_rates = [
        item["false_alarm_rate_nominal"] for item in run_metrics
    ]
    trend_values = [item["score_trend_spearman"] for item in run_metrics]
    separation_values = [
        item["initial_final_separation"] for item in run_metrics
    ]
    return {
        "available": True,
        "metric_type": "run_to_failure_degradation",
        "n_runs": int(len(run_metrics)),
        "n_windows": int(len(temporal)),
        "detected_runs": int(len(detected_runs)),
        "missed_runs": int(len(missed_runs)),
        "detected_before_failure_rate": _ratio(len(detected_runs), len(run_metrics)),
        "median_lead_time_to_failure": _median_defined(lead_times),
        "mean_lead_time_to_failure": _mean_defined(lead_times),
        "mean_false_alarm_rate_nominal": _mean_defined(false_alarm_rates),
        "mean_score_trend_spearman": _mean_defined(trend_values),
        "mean_initial_final_separation": _mean_defined(separation_values),
        "run_metrics": run_metrics,
        "notes": [
            "Temporal metrics use anomaly_score and alert chronology; binary "
            "classification metrics remain reported separately.",
            "Nominal false alarm rate uses label=normal when available; "
            f"otherwise relative_life <= {NOMINAL_RELATIVE_LIFE_LIMIT:.2f}.",
        ],
    }


def _degradation_metrics_for_run(run_id: str, group: pd.DataFrame) -> dict[str, Any]:
    ordered = _temporal_order(group)
    early = _relative_slice(ordered, upper=EARLY_RELATIVE_LIFE_LIMIT)
    late = _relative_slice(ordered, lower=LATE_RELATIVE_LIFE_LIMIT)
    early_mean = (
        _score_mean(early)
        if not early.empty
        else _score_mean(_head_third(ordered))
    )
    late_mean = (
        _score_mean(late)
        if not late.empty
        else _score_mean(_tail_third(ordered))
    )
    first_alert = _first_alert(ordered)
    lead_time = (
        None
        if first_alert is None
        else _safe_float(first_alert.get("time_to_failure_seconds"))
    )
    detected_before_failure = (
        False
        if first_alert is None
        else True if lead_time is None else lead_time >= 0.0
    )
    missed_failure = first_alert is None or detected_before_failure is False
    return {
        "run_id": run_id,
        "n_windows": int(len(ordered)),
        "first_alert_time": (
            None if first_alert is None else _first_alert_time(first_alert)
        ),
        "first_alert_relative_life": (
            None
            if first_alert is None
            else _safe_float(first_alert.get("relative_life"))
        ),
        "time_to_detection": (
            None
            if first_alert is None
            else _safe_float(first_alert.get("time_since_start_seconds"))
        ),
        "lead_time_to_failure": lead_time,
        "detected_before_failure": bool(detected_before_failure),
        "missed_failure": bool(missed_failure),
        "false_alarm_rate_nominal": _false_alarm_rate_nominal(ordered),
        "alert_persistence": _max_consecutive_alerts(ordered["predicted_anomaly"]),
        "score_trend_spearman": _spearman(
            ordered["relative_life"], ordered["anomaly_score"]
        ),
        "score_slope": _slope(ordered["relative_life"], ordered["anomaly_score"]),
        "initial_mean_score": early_mean,
        "final_mean_score": late_mean,
        "initial_final_separation": _difference(late_mean, early_mean),
        "initial_final_ratio": _ratio_float(late_mean, early_mean),
        "monotonicity": _monotonicity(ordered["anomaly_score"]),
    }


def _unavailable_degradation_metrics(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "metric_type": "run_to_failure_degradation",
        "reason": reason,
    }


def _validate_prediction_values(data: pd.DataFrame) -> None:
    if data.empty:
        raise ValueError("predictions file is empty")
    if data["window_id"].duplicated().any():
        raise ValueError("duplicated window_id values found")
    if data[["target", "predicted_anomaly", "anomaly_score"]].isna().any().any():
        raise ValueError("predictions contain null numeric values")
    if not set(data["target"]).issubset({0, 1}):
        raise ValueError("target must contain only 0/1 values")
    if not set(data["predicted_anomaly"]).issubset({0, 1}):
        raise ValueError("predicted_anomaly must contain only 0/1 values")


def _score_if_defined(metric_fn: Any, y_true: Any, scores: Any) -> float | None:
    if len(set(y_true)) < 2:
        return None
    return float(metric_fn(y_true, scores))


def _binary_metric_context(data: pd.DataFrame) -> dict[str, Any]:
    label_source = _single_optional_value(data, "label_source")
    label_granularity = _single_optional_value(data, "label_granularity")
    context = {
        "label_source": label_source,
        "label_granularity": label_granularity,
    }
    if label_source is None:
        context["warning"] = (
            "label_source is not present in predictions.csv; interpret binary "
            "metrics with the run dataset context."
        )
    return context


def _single_optional_value(data: pd.DataFrame, column: str) -> str | None:
    if column not in data.columns:
        return None
    values = sorted(
        {
            str(value)
            for value in data[column].dropna().unique()
            if str(value).strip()
        }
    )
    if not values:
        return None
    return values[0] if len(values) == 1 else "mixed"


def _stable_run_id(value: Any) -> str:
    if pd.isna(value) or str(value).strip() == "":
        return "_single_run"
    return str(value)


def _temporal_order(group: pd.DataFrame) -> pd.DataFrame:
    sort_columns = [
        column
        for column in ["relative_life", "time_since_start_seconds", "window_index"]
        if column in group.columns
    ]
    if not sort_columns:
        return group.reset_index(drop=True)
    return group.sort_values(sort_columns, kind="mergesort").reset_index(drop=True)


def _relative_slice(
    data: pd.DataFrame,
    *,
    lower: float | None = None,
    upper: float | None = None,
) -> pd.DataFrame:
    mask = pd.Series(True, index=data.index)
    if lower is not None:
        mask &= data["relative_life"] >= lower
    if upper is not None:
        mask &= data["relative_life"] <= upper
    return data.loc[mask]


def _head_third(data: pd.DataFrame) -> pd.DataFrame:
    size = max(1, math.ceil(len(data) / 3))
    return data.head(size)


def _tail_third(data: pd.DataFrame) -> pd.DataFrame:
    size = max(1, math.ceil(len(data) / 3))
    return data.tail(size)


def _score_mean(data: pd.DataFrame) -> float | None:
    if data.empty:
        return None
    return _safe_float(data["anomaly_score"].mean())


def _first_alert(data: pd.DataFrame) -> dict[str, Any] | None:
    alerts = data[data["predicted_anomaly"] == 1]
    if alerts.empty:
        return None
    return alerts.iloc[0].to_dict()


def _first_alert_time(row: dict[str, Any]) -> str | None:
    for column in ("timestamp_start", "timestamp_end"):
        value = row.get(column)
        if value is not None and not pd.isna(value) and str(value).strip():
            return str(value)
    return None


def _false_alarm_rate_nominal(data: pd.DataFrame) -> float | None:
    nominal = pd.DataFrame()
    if "label" in data.columns:
        nominal = data[data["label"].astype(str).str.lower() == "normal"]
    if nominal.empty:
        nominal = data[data["relative_life"] <= NOMINAL_RELATIVE_LIFE_LIMIT]
    if nominal.empty:
        return None
    return _safe_float(nominal["predicted_anomaly"].mean())


def _max_consecutive_alerts(values: pd.Series) -> int:
    best = 0
    current = 0
    for value in values.astype(int):
        if value == 1:
            current += 1
            best = max(best, current)
        else:
            current = 0
    return int(best)


def _spearman(x_values: pd.Series, y_values: pd.Series) -> float | None:
    data = pd.DataFrame({"x": x_values, "y": y_values}).dropna()
    if len(data) < 2 or data["x"].nunique() < 2 or data["y"].nunique() < 2:
        return None
    return _safe_float(data["x"].corr(data["y"], method="spearman"))


def _slope(x_values: pd.Series, y_values: pd.Series) -> float | None:
    data = pd.DataFrame({"x": x_values, "y": y_values}).dropna()
    if len(data) < 2 or data["x"].nunique() < 2:
        return None
    return _safe_float(
        np.polyfit(data["x"].to_numpy(), data["y"].to_numpy(), 1)[0]
    )


def _monotonicity(values: pd.Series) -> float | None:
    scores = values.dropna().to_numpy(dtype=float)
    if scores.size < 2:
        return None
    diffs = np.diff(scores)
    non_zero = diffs[diffs != 0.0]
    if non_zero.size == 0:
        return None
    return _safe_float(np.mean(non_zero > 0.0))


def _difference(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return _safe_float(left - right)


def _ratio(numerator: int, denominator: int) -> float | None:
    if denominator == 0:
        return None
    return float(numerator / denominator)


def _ratio_float(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or abs(denominator) < 1e-12:
        return None
    return _safe_float(numerator / denominator)


def _mean_defined(values: list[float | None]) -> float | None:
    defined = [value for value in values if value is not None]
    if not defined:
        return None
    return _safe_float(float(np.mean(defined)))


def _median_defined(values: list[float | None]) -> float | None:
    defined = [value for value in values if value is not None]
    if not defined:
        return None
    return _safe_float(float(np.median(defined)))


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(result):
        return None
    return result


def _report_markdown(summary: dict[str, Any]) -> str:
    metrics = summary["primary_metrics"]
    matrix = metrics["confusion_matrix"]
    lines = [
        "# Evaluacion de deteccion de anomalias",
        "",
        f"- Familias metricas: `{', '.join(summary['metric_families'])}`",
        f"- Split principal: `{summary['primary_split']}`",
        f"- Predicciones evaluadas: `{summary['n_predictions']}`",
        f"- Precision: `{metrics['precision']:.4f}`",
        f"- Recall: `{metrics['recall']:.4f}`",
        f"- F1-score: `{metrics['f1_score']:.4f}`",
        f"- ROC-AUC: `{_format_optional(metrics['roc_auc'])}`",
        f"- PR-AUC: `{_format_optional(metrics['pr_auc'])}`",
        f"- FPR: `{_format_optional(metrics['false_positive_rate'])}`",
        f"- Matriz de confusion: TN={matrix['tn']}, FP={matrix['fp']}, FN={matrix['fn']}, TP={matrix['tp']}",
        "",
    ]
    degradation = summary.get("degradation_metrics", {})
    if degradation.get("available") is True:
        lines.extend(_degradation_report_markdown(degradation))
    return "\n".join(lines)


def _degradation_report_markdown(metrics: dict[str, Any]) -> list[str]:
    lines = [
        "## Evaluacion temporal de degradacion",
        "",
        f"- Runs evaluados: `{metrics['n_runs']}`",
        f"- Ventanas temporales: `{metrics['n_windows']}`",
        f"- Runs detectados antes de fallo: `{metrics['detected_runs']}`",
        f"- Runs perdidos: `{metrics['missed_runs']}`",
        f"- Lead time medio a fallo: `{_format_optional(metrics['mean_lead_time_to_failure'])}`",
        f"- Falsa alarma nominal media: `{_format_optional(metrics['mean_false_alarm_rate_nominal'])}`",
        f"- Tendencia Spearman media: `{_format_optional(metrics['mean_score_trend_spearman'])}`",
        f"- Separacion inicial-final media: `{_format_optional(metrics['mean_initial_final_separation'])}`",
        "",
        "| run_id | first_alert | lead_time_to_failure | false_alarm_rate_nominal | trend_spearman | missed_failure |",
        "| --- | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in metrics["run_metrics"][:12]:
        lines.append(
            "| "
            f"{item['run_id']} | "
            f"{_format_optional(item['first_alert_relative_life'])} | "
            f"{_format_optional(item['lead_time_to_failure'])} | "
            f"{_format_optional(item['false_alarm_rate_nominal'])} | "
            f"{_format_optional(item['score_trend_spearman'])} | "
            f"{item['missed_failure']} |"
        )
    lines.append("")
    return lines


def _format_optional(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"
