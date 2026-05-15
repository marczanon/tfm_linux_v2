"""Modelado determinista de anomalias sobre features CWRU."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

from codigo.app.schemas.executor_results import ModelingResult
from codigo.app.schemas.state import ArtifactRef, ModelingConfig, PipelineError


DEFAULT_MODELING_CONFIG = ModelingConfig(
    model_name="isolation_forest",
    random_state=42,
    hyperparameters={
        "n_estimators": 200,
        "max_samples": "auto",
        "contamination": "auto",
        "max_features": 1.0,
        "bootstrap": False,
        "n_jobs": 1,
        "threshold_quantile": 0.99,
    },
)

METADATA_COLUMNS = {
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

PREDICTION_FIELDS = [
    "window_id",
    "file_id",
    "split",
    "label",
    "target",
    "fault_type",
    "anomaly_score",
    "threshold",
    "predicted_anomaly",
]

SKLEARN_IFOREST_PARAMS = {
    "n_estimators",
    "max_samples",
    "contamination",
    "max_features",
    "bootstrap",
    "n_jobs",
}


def generate_model_outputs(
    features_path: str | Path = "codigo/data/tensors/cwru_bearing/windows_features.csv",
    output_dir: str | Path = "codigo/models/cwru_bearing",
    config: ModelingConfig | None = None,
) -> ModelingResult:
    """Entrena un modelo base y devuelve un resultado estructurado."""

    started_at = datetime.now(UTC)
    output = Path(output_dir)
    model_path = output / "isolation_forest.joblib"
    predictions_path = output / "predictions.csv"
    try:
        summary = train_anomaly_model(features_path, output, config or DEFAULT_MODELING_CONFIG)
        artifacts = [
            ArtifactRef(
                name="cwru_isolation_forest",
                artifact_type="model",
                path=summary["model_path"],
                producer="modeling_executor",
                metadata={
                    "model_name": summary["model_name"],
                    "n_train_windows": summary["n_train_windows"],
                    "n_features": len(summary["feature_columns"]),
                },
            ),
            ArtifactRef(
                name="cwru_model_predictions",
                artifact_type="predictions",
                path=summary["predictions_path"],
                producer="modeling_executor",
                metadata={"n_predictions": summary["n_predictions"]},
            ),
            ArtifactRef(
                name="cwru_modeling_summary",
                artifact_type="log",
                path=summary["summary_path"],
                producer="modeling_executor",
                metadata={"threshold": summary["threshold"]},
            ),
        ]
        return ModelingResult(
            executor_name="modeling",
            status="success",
            message="CWRU anomaly model generated.",
            artifacts=artifacts,
            errors=[],
            state_updates={},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            model_path=summary["model_path"],
            predictions_path=summary["predictions_path"],
        )
    except Exception as exc:
        error = PipelineError(
            stage="modeling",
            node="modeling_executor",
            message=str(exc),
            recoverable=True,
        )
        return ModelingResult(
            executor_name="modeling",
            status="failed",
            message="CWRU anomaly modeling failed.",
            artifacts=[],
            errors=[error],
            state_updates={},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            model_path=str(model_path),
            predictions_path=str(predictions_path),
        )


def train_anomaly_model(
    features_path: str | Path,
    output_dir: str | Path,
    config: ModelingConfig = DEFAULT_MODELING_CONFIG,
) -> dict[str, Any]:
    """Entrena Isolation Forest con ventanas normales de train."""

    if config.model_name != "isolation_forest":
        raise ValueError(f"unsupported model_name for MVP: {config.model_name}")

    data = pd.read_csv(features_path)
    feature_columns = _feature_columns(data)
    train = data[(data["split"] == "train") & (data["label"] == "normal")]
    if train.empty:
        raise ValueError("training requires normal windows in split=train")

    params, threshold_quantile = _isolation_forest_params(config)
    model = IsolationForest(random_state=config.random_state, **params)
    model.fit(train[feature_columns].to_numpy(dtype=float))

    scores = -model.score_samples(data[feature_columns].to_numpy(dtype=float))
    threshold = _threshold(scores, data["split"].to_numpy(), threshold_quantile)
    predictions = _prediction_rows(data, scores, threshold)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    model_path = output / "isolation_forest.joblib"
    predictions_path = output / "predictions.csv"
    summary_path = output / "modeling_summary.json"
    joblib.dump(
        {
            "model": model,
            "feature_columns": feature_columns,
            "threshold": threshold,
            "config": config.model_dump(mode="json"),
        },
        model_path,
    )
    _write_predictions(predictions_path, predictions)
    summary = _summary(
        config,
        feature_columns,
        train,
        data,
        predictions,
        model_path,
        predictions_path,
        summary_path,
        threshold,
        threshold_quantile,
    )
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _feature_columns(data: pd.DataFrame) -> list[str]:
    columns = [column for column in data.columns if column not in METADATA_COLUMNS]
    if not columns:
        raise ValueError("no feature columns found")
    return columns


def _isolation_forest_params(config: ModelingConfig) -> tuple[dict[str, Any], float]:
    unsupported = set(config.hyperparameters) - SKLEARN_IFOREST_PARAMS - {"threshold_quantile"}
    if unsupported:
        raise ValueError(f"unsupported isolation_forest hyperparameters: {', '.join(sorted(unsupported))}")
    threshold_quantile = float(config.hyperparameters.get("threshold_quantile", 0.99))
    if not 0.0 < threshold_quantile <= 1.0:
        raise ValueError("threshold_quantile must be in (0, 1]")
    params = {
        key: value
        for key, value in config.hyperparameters.items()
        if key in SKLEARN_IFOREST_PARAMS
    }
    return params, threshold_quantile


def _threshold(scores: np.ndarray, splits: np.ndarray, quantile: float) -> float:
    validation_scores = scores[splits == "validation"]
    source = validation_scores if validation_scores.size else scores[splits == "train"]
    return float(np.quantile(source, quantile))


def _prediction_rows(
    data: pd.DataFrame,
    scores: np.ndarray,
    threshold: float,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row, score in zip(data.to_dict("records"), scores, strict=True):
        rows.append(
            {
                "window_id": row["window_id"],
                "file_id": row["file_id"],
                "split": row["split"],
                "label": row["label"],
                "target": row["target"],
                "fault_type": _optional_text(row.get("fault_type", "")),
                "anomaly_score": float(score),
                "threshold": threshold,
                "predicted_anomaly": int(score > threshold),
            }
        )
    return rows


def _optional_text(value: Any) -> str:
    return "" if pd.isna(value) else str(value)


def _write_predictions(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=PREDICTION_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _summary(
    config: ModelingConfig,
    feature_columns: list[str],
    train: pd.DataFrame,
    data: pd.DataFrame,
    predictions: list[dict[str, Any]],
    model_path: Path,
    predictions_path: Path,
    summary_path: Path,
    threshold: float,
    threshold_quantile: float,
) -> dict[str, Any]:
    prediction_counts = Counter(row["predicted_anomaly"] for row in predictions)
    return {
        "model_name": config.model_name,
        "model_path": str(model_path),
        "predictions_path": str(predictions_path),
        "summary_path": str(summary_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "config": config.model_dump(mode="json"),
        "feature_columns": feature_columns,
        "threshold": threshold,
        "threshold_quantile": threshold_quantile,
        "n_train_windows": int(len(train)),
        "n_predictions": int(len(predictions)),
        "split_counts": dict(Counter(data["split"])),
        "label_counts": dict(Counter(data["label"])),
        "predicted_anomaly_counts": {str(key): value for key, value in prediction_counts.items()},
    }
