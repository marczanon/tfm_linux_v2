"""Failure summaries for bounded agentic retry loops."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd

from codigo.app.schemas.common import StrictBaseModel


class FailureAnalysisArtifacts(StrictBaseModel):
    """Artefactos escritos para explicar por que se reintenta una run."""

    analysis_path: str
    report_path: str
    analysis: dict[str, Any]


def generate_prediction_failure_analysis(
    predictions_path: str | Path,
    output_dir: str | Path,
    *,
    metrics_path: str | Path | None = None,
    modeling_summary_path: str | Path | None = None,
    primary_split: str = "test",
    min_recall_required: float = 0.90,
    max_false_positive_rate: float = 0.10,
    attempt_number: int = 1,
    max_attempts: int = 2,
) -> FailureAnalysisArtifacts:
    """Builds and persists a compact failure analysis for an agent."""

    analysis = build_prediction_failure_analysis(
        predictions_path,
        metrics_path=metrics_path,
        modeling_summary_path=modeling_summary_path,
        primary_split=primary_split,
        min_recall_required=min_recall_required,
        max_false_positive_rate=max_false_positive_rate,
        attempt_number=attempt_number,
        max_attempts=max_attempts,
    )
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    analysis_path = output / "failure_analysis.json"
    report_path = output / "failure_analysis.md"
    analysis_path.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    report_path.write_text(_analysis_markdown(analysis), encoding="utf-8")
    return FailureAnalysisArtifacts(
        analysis_path=analysis_path.as_posix(),
        report_path=report_path.as_posix(),
        analysis=analysis,
    )


def build_prediction_failure_analysis(
    predictions_path: str | Path,
    *,
    metrics_path: str | Path | None = None,
    modeling_summary_path: str | Path | None = None,
    primary_split: str = "test",
    min_recall_required: float = 0.90,
    max_false_positive_rate: float = 0.10,
    attempt_number: int = 1,
    max_attempts: int = 2,
) -> dict[str, Any]:
    """Summarises false negatives, false positives and retry boundaries."""

    predictions = pd.read_csv(predictions_path)
    required = {"split", "target", "predicted_anomaly", "anomaly_score", "threshold"}
    missing = required - set(predictions.columns)
    if missing:
        raise ValueError(f"missing prediction columns: {', '.join(sorted(missing))}")
    split = predictions[predictions["split"] == primary_split].copy()
    if split.empty:
        raise ValueError(f"primary split not found or empty: {primary_split}")

    split["target"] = split["target"].astype(int)
    split["predicted_anomaly"] = split["predicted_anomaly"].astype(int)
    split["anomaly_score"] = split["anomaly_score"].astype(float)
    threshold = float(split["threshold"].iloc[0])
    metrics = _load_metrics(metrics_path)
    modeling_summary = _load_json(modeling_summary_path)
    matrix = _confusion_counts(split)
    false_negatives = split[(split["target"] == 1) & (split["predicted_anomaly"] == 0)]
    false_positives = split[(split["target"] == 0) & (split["predicted_anomaly"] == 1)]

    recall = _metric_value(metrics, "recall")
    fpr = _metric_value(metrics, "false_positive_rate")
    failure_modes = _failure_modes(
        recall=recall,
        fpr=fpr,
        min_recall_required=min_recall_required,
        max_false_positive_rate=max_false_positive_rate,
    )
    return {
        "available": True,
        "primary_split": primary_split,
        "attempt_number": attempt_number,
        "max_attempts": max_attempts,
        "remaining_attempts_after_this_decision": max(0, max_attempts - attempt_number),
        "metrics": metrics,
        "threshold": threshold,
        "modeling_summary": modeling_summary,
        "confusion_matrix": matrix,
        "failure_modes": failure_modes,
        "false_negative_summary": _error_group_summary(false_negatives, threshold),
        "false_positive_summary": _error_group_summary(false_positives, threshold),
        "score_summary_by_outcome": _score_summary_by_outcome(split),
        "label_counts": dict(Counter(split["label"])),
        "prediction_counts": {
            str(key): int(value)
            for key, value in Counter(split["predicted_anomaly"]).items()
        },
        "decision_guidance": {
            "goal": (
                "Propose one retry only if the evidence suggests a plausible "
                "configuration change within supported executors."
            ),
            "no_infinite_loops": (
                "Stop when max_attempts is reached or when further changes are "
                "unlikely to improve recall/FPR trade-off."
            ),
            "attempt_budget": (
                "The current decision is "
                f"{attempt_number}/{max_attempts}; "
                "remaining_attempts_after_this_decision is "
                f"{max(0, max_attempts - attempt_number)}."
            ),
            "scoring_convention": (
                "predicted_anomaly = 1 when anomaly_score > threshold. Lowering "
                "the effective threshold usually catches more anomalies and may "
                "increase false positives; raising it is more conservative."
            ),
            "agent_must_explain": (
                "The retry decision must explicitly cite false negatives, false "
                "positives, threshold behavior and the expected trade-off."
            ),
        },
        "supported_retry_space": {
            "models": ["isolation_forest", "pca_reconstruction_error"],
            "shared_rules": {
                "random_state": 42,
                "train_split": "train",
                "validation_split": "validation",
                "n_jobs": 1,
            },
            "isolation_forest_knobs": [
                "threshold_quantile",
                "n_estimators",
                "max_samples",
                "max_features",
                "bootstrap",
            ],
            "pca_reconstruction_error_knobs": [
                "threshold_quantile",
                "n_components",
                "svd_solver",
                "whiten",
            ],
        },
    }


def _load_metrics(metrics_path: str | Path | None) -> dict[str, Any]:
    if metrics_path is None:
        return {}
    payload = _load_json(metrics_path)
    if not isinstance(payload, dict):
        return {}
    primary = payload.get("primary_metrics")
    if isinstance(primary, dict):
        return primary
    return payload


def _load_json(path: str | Path | None) -> Any:
    if path is None:
        return None
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _metric_value(metrics: dict[str, Any], name: str) -> float | None:
    value = metrics.get(name)
    return None if value is None else float(value)


def _failure_modes(
    *,
    recall: float | None,
    fpr: float | None,
    min_recall_required: float,
    max_false_positive_rate: float,
) -> list[str]:
    modes: list[str] = []
    if recall is None or recall < min_recall_required:
        modes.append("low_recall_many_missed_anomalies")
    if fpr is None or fpr > max_false_positive_rate:
        modes.append("high_false_positive_rate")
    return modes or ["metrics_within_thresholds"]


def _confusion_counts(split: pd.DataFrame) -> dict[str, int]:
    y_true = split["target"]
    y_pred = split["predicted_anomaly"]
    return {
        "tn": int(((y_true == 0) & (y_pred == 0)).sum()),
        "fp": int(((y_true == 0) & (y_pred == 1)).sum()),
        "fn": int(((y_true == 1) & (y_pred == 0)).sum()),
        "tp": int(((y_true == 1) & (y_pred == 1)).sum()),
    }


def _error_group_summary(group: pd.DataFrame, threshold: float) -> dict[str, Any]:
    if group.empty:
        return {
            "count": 0,
            "score_min": None,
            "score_median": None,
            "score_max": None,
            "median_margin_to_threshold": None,
            "example_window_ids": [],
        }
    scores = group["anomaly_score"].astype(float)
    return {
        "count": int(len(group)),
        "score_min": float(scores.min()),
        "score_median": float(scores.median()),
        "score_max": float(scores.max()),
        "median_margin_to_threshold": float(scores.median() - threshold),
        "example_window_ids": [str(value) for value in group["window_id"].head(5)],
    }


def _score_summary_by_outcome(split: pd.DataFrame) -> dict[str, dict[str, Any]]:
    groups = {
        "true_negative": split[(split["target"] == 0) & (split["predicted_anomaly"] == 0)],
        "false_positive": split[(split["target"] == 0) & (split["predicted_anomaly"] == 1)],
        "false_negative": split[(split["target"] == 1) & (split["predicted_anomaly"] == 0)],
        "true_positive": split[(split["target"] == 1) & (split["predicted_anomaly"] == 1)],
    }
    return {
        name: _score_stats(group)
        for name, group in groups.items()
    }


def _score_stats(group: pd.DataFrame) -> dict[str, Any]:
    if group.empty:
        return {"count": 0, "mean": None, "median": None, "min": None, "max": None}
    scores = group["anomaly_score"].astype(float)
    return {
        "count": int(len(group)),
        "mean": float(scores.mean()),
        "median": float(scores.median()),
        "min": float(scores.min()),
        "max": float(scores.max()),
    }


def _analysis_markdown(analysis: dict[str, Any]) -> str:
    metrics = analysis.get("metrics", {})
    matrix = analysis["confusion_matrix"]
    fn = analysis["false_negative_summary"]
    fp = analysis["false_positive_summary"]
    return "\n".join(
        [
            "# Analisis de fallo para reintento agentico",
            "",
            f"- Split principal: `{analysis['primary_split']}`",
            f"- Intento: `{analysis['attempt_number']}/{analysis['max_attempts']}`",
            (
                "- Reintentos restantes despues de esta decision: "
                f"`{analysis['remaining_attempts_after_this_decision']}`"
            ),
            f"- Failure modes: `{', '.join(analysis['failure_modes'])}`",
            f"- Recall: `{_format_metric(metrics.get('recall'))}`",
            f"- FPR: `{_format_metric(metrics.get('false_positive_rate'))}`",
            f"- F1-score: `{_format_metric(metrics.get('f1_score'))}`",
            f"- Threshold: `{analysis['threshold']:.6f}`",
            (
                "- Matriz de confusion: "
                f"TN={matrix['tn']}, FP={matrix['fp']}, "
                f"FN={matrix['fn']}, TP={matrix['tp']}"
            ),
            f"- Falsos negativos: `{fn['count']}`",
            f"- Falsos positivos: `{fp['count']}`",
            "",
            "Convencion: una ventana es anomala si `anomaly_score > threshold`.",
            "Bajar el umbral suele capturar mas anomalias, con riesgo de mas falsos positivos.",
            "Subirlo suele reducir falsas alarmas, con riesgo de menor recall.",
            "",
        ]
    )


def _format_metric(value: object) -> str:
    return "n/a" if value is None else f"{float(value):.4f}"
