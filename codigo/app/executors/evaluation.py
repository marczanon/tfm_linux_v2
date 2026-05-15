"""Evaluacion determinista de predicciones de anomalias CWRU."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
                name="cwru_evaluation_metrics",
                artifact_type="metrics",
                path=summary["metrics_path"],
                producer="evaluator",
                metadata={
                    "primary_split": primary_split,
                    "f1_score": summary["primary_metrics"]["f1_score"],
                },
            ),
            ArtifactRef(
                name="cwru_evaluation_summary",
                artifact_type="report",
                path=summary["report_fragment_path"],
                producer="evaluator",
                metadata={"n_predictions": summary["n_predictions"]},
            ),
        ]
        return EvaluationExecutorResult(
            executor_name="evaluation",
            status="success",
            message="CWRU evaluation metrics generated.",
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
            message="CWRU evaluation failed.",
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
    summary = {
        "predictions_path": str(predictions_path),
        "metrics_path": str(output / "metrics.json"),
        "report_fragment_path": str(output / "evaluation_summary.md"),
        "generated_at": datetime.now(UTC).isoformat(),
        "primary_split": primary_split,
        "primary_metrics": primary_metrics,
        "metrics_by_split": metrics_by_split,
        "n_predictions": int(len(data)),
        "split_counts": dict(Counter(data["split"])),
        "label_counts": dict(Counter(data["label"])),
    }
    Path(summary["metrics_path"]).write_text(json.dumps(summary, indent=2), encoding="utf-8")
    Path(summary["report_fragment_path"]).write_text(_report_markdown(summary), encoding="utf-8")
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


def _report_markdown(summary: dict[str, Any]) -> str:
    metrics = summary["primary_metrics"]
    matrix = metrics["confusion_matrix"]
    return "\n".join(
        [
            "# Evaluacion CWRU",
            "",
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
    )


def _format_optional(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"
