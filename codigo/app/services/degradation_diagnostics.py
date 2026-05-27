"""Diagnosticos no supervisados para series run-to-failure."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DEFAULT_DEGRADATION_FEATURES = [
    "rms",
    "energy",
    "peak_to_peak",
    "std",
    "crest_factor",
    "kurtosis",
]


def generate_degradation_diagnostics(
    features_path: str | Path,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Calcula indicadores temporales sin usar etiquetas supervisadas."""

    features = pd.read_csv(features_path)
    if "file_id" not in features.columns:
        raise ValueError("degradation diagnostics require file_id column")

    score_columns = [
        column for column in DEFAULT_DEGRADATION_FEATURES if column in features.columns
    ]
    if not score_columns:
        raise ValueError("no supported degradation feature columns found")

    scored = features.copy()
    scored["degradation_score"] = _row_scores(scored, score_columns)
    per_file = _per_file_scores(scored)
    summary = _diagnostics_summary(features_path, score_columns, per_file)

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "degradation_diagnostics.json"
    markdown_path = output / "degradation_diagnostics.md"
    summary["diagnostics_path"] = str(json_path)
    summary["report_path"] = str(markdown_path)
    json_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    markdown_path.write_text(_markdown_report(summary), encoding="utf-8")
    return summary


def _row_scores(data: pd.DataFrame, columns: list[str]) -> np.ndarray:
    normalized: list[np.ndarray] = []
    for column in columns:
        values = data[column].to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        if finite.size == 0:
            continue
        low = float(np.min(finite))
        high = float(np.max(finite))
        if high == low:
            normalized.append(np.zeros_like(values, dtype=float))
            continue
        normalized.append((values - low) / (high - low))
    if not normalized:
        return np.zeros(len(data), dtype=float)
    return np.mean(np.vstack(normalized), axis=0)


def _per_file_scores(data: pd.DataFrame) -> list[dict[str, Any]]:
    grouped = (
        data.groupby("file_id", sort=True)["degradation_score"]
        .agg(["mean", "max", "count"])
        .reset_index()
        .sort_values("file_id")
    )
    rows: list[dict[str, Any]] = []
    for index, row in grouped.iterrows():
        rows.append(
            {
                "sequence_index": int(index),
                "file_id": str(row["file_id"]),
                "mean_score": float(row["mean"]),
                "max_score": float(row["max"]),
                "n_windows": int(row["count"]),
            }
        )
    return rows


def _diagnostics_summary(
    features_path: str | Path,
    score_columns: list[str],
    per_file: list[dict[str, Any]],
) -> dict[str, Any]:
    mean_scores = np.asarray([row["mean_score"] for row in per_file], dtype=float)
    n_files = int(mean_scores.size)
    early, late = _early_late_means(mean_scores)
    slope = _trend_slope(mean_scores)
    rank_correlation = _rank_correlation(mean_scores)
    late_early_ratio = None if early == 0 else float(late / early)
    status = _trend_status(late_early_ratio, slope)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "features_path": str(features_path),
        "metric_type": "unsupervised_degradation_diagnostics",
        "score_columns": score_columns,
        "n_files": n_files,
        "n_windows": int(sum(row["n_windows"] for row in per_file)),
        "early_mean_score": float(early),
        "late_mean_score": float(late),
        "late_minus_early": float(late - early),
        "late_early_ratio": late_early_ratio,
        "trend_slope_per_file": slope,
        "rank_correlation_with_time": rank_correlation,
        "trend_status": status,
        "label_warning": (
            "No se calcula recall/F1 porque el diagnostico no usa etiquetas por ventana."
        ),
        "per_file": per_file,
    }


def _early_late_means(values: np.ndarray) -> tuple[float, float]:
    if values.size == 0:
        return 0.0, 0.0
    chunk = max(1, values.size // 3)
    return float(np.mean(values[:chunk])), float(np.mean(values[-chunk:]))


def _trend_slope(values: np.ndarray) -> float | None:
    if values.size < 2:
        return None
    indexes = np.arange(values.size, dtype=float)
    return float(np.polyfit(indexes, values, 1)[0])


def _rank_correlation(values: np.ndarray) -> float | None:
    if values.size < 2:
        return None
    indexes = pd.Series(np.arange(values.size, dtype=float))
    ranked = pd.Series(values).rank(method="average")
    correlation = indexes.corr(ranked)
    return None if pd.isna(correlation) else float(correlation)


def _trend_status(ratio: float | None, slope: float | None) -> str:
    if ratio is None or slope is None:
        return "insufficient_sequence"
    if ratio >= 1.10 and slope > 0:
        return "increasing_degradation_signal"
    if ratio <= 0.90 and slope < 0:
        return "decreasing_degradation_signal"
    return "stable_or_inconclusive"


def _markdown_report(summary: dict[str, Any]) -> str:
    ratio = summary["late_early_ratio"]
    ratio_text = "n/a" if ratio is None else f"{ratio:.4f}"
    lines = [
        "# Diagnostico no supervisado de degradacion",
        "",
        f"- Tipo: `{summary['metric_type']}`",
        f"- Ficheros: `{summary['n_files']}`",
        f"- Ventanas: `{summary['n_windows']}`",
        f"- Estado de tendencia: `{summary['trend_status']}`",
        f"- Media inicial: `{summary['early_mean_score']:.4f}`",
        f"- Media final: `{summary['late_mean_score']:.4f}`",
        f"- Ratio final/inicial: `{ratio_text}`",
        f"- Pendiente temporal: `{summary['trend_slope_per_file']}`",
        "",
        summary["label_warning"],
        "",
        "| Orden | File ID | Media | Max | Ventanas |",
        "| ---: | --- | ---: | ---: | ---: |",
    ]
    for row in summary["per_file"]:
        lines.append(
            " | ".join(
                [
                    f"| {row['sequence_index']}",
                    row["file_id"],
                    f"{row['mean_score']:.4f}",
                    f"{row['max_score']:.4f}",
                    f"{row['n_windows']} |",
                ]
            )
        )
    return "\n".join(lines).rstrip() + "\n"
