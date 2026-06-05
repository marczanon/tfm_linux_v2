"""Readiness determinista para autoencoder y RUL experimental."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import pandas as pd

from codigo.app.schemas.temporal_readiness import (
    DEFAULT_TEMPORAL_MODEL_READINESS_POLICY,
    TemporalModelReadinessAssessment,
    TemporalModelReadinessPolicy,
)


METADATA_COLUMNS = {
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
    "anomaly_score",
    "threshold",
    "predicted_anomaly",
}


def assess_temporal_model_readiness(
    *,
    features_path: str | None,
    predictions_path: str | None = None,
    splits_path: str | None = None,
    policy: TemporalModelReadinessPolicy | None = None,
) -> TemporalModelReadinessAssessment:
    """Evalua si procede usar autoencoder denso o RUL experimental."""

    active_policy = policy or DEFAULT_TEMPORAL_MODEL_READINESS_POLICY
    if not features_path or not Path(features_path).exists():
        return _unavailable_assessment(
            active_policy,
            features_path=features_path,
            predictions_path=predictions_path,
            splits_path=splits_path,
            reason="features artifact is missing",
        )

    features = pd.read_csv(features_path)
    data = _merge_predictions_if_available(features, predictions_path)
    if data.empty:
        return _unavailable_assessment(
            active_policy,
            features_path=features_path,
            predictions_path=predictions_path,
            splits_path=splits_path,
            reason="features artifact is empty",
        )

    feature_columns = _numeric_feature_columns(features)
    finite_ratio = _finite_feature_ratio(features, feature_columns)
    n_windows = int(len(data))
    n_train_windows = _split_count(data, "train")
    n_train_nominal_windows = _train_nominal_count(data)
    n_runs = _run_count(data)
    temporal_continuity_ok = _temporal_continuity_ok(data)
    time_to_failure_coverage = _time_to_failure_coverage(data)
    split_quality_ok = _split_quality_ok(data)
    train_degradation_fraction = _train_degradation_fraction(data)
    leakage_risk = _leakage_risk(train_degradation_fraction, split_quality_ok)

    blocked: list[str] = []
    caution: list[str] = []
    if len(feature_columns) < active_policy.min_autoencoder_feature_columns:
        blocked.append("insufficient_feature_columns")
    if finite_ratio is None or finite_ratio < active_policy.min_finite_feature_ratio:
        blocked.append("insufficient_finite_feature_ratio")
    if n_train_nominal_windows < active_policy.min_autoencoder_train_nominal_windows:
        blocked.append("insufficient_train_nominal_windows")
    if not split_quality_ok:
        blocked.append("invalid_or_missing_splits")
    if leakage_risk == "blocked":
        blocked.append("high_train_degradation_leakage_risk")
    elif leakage_risk == "caution":
        caution.append("train_contains_degradation_candidates")
    if n_windows < active_policy.min_temporal_windows:
        caution.append("short_temporal_sequence")
    if not temporal_continuity_ok:
        caution.append("temporal_continuity_not_verified")

    autoencoder_ready = not blocked
    rul_blockers = []
    if n_runs < active_policy.min_rul_runs:
        rul_blockers.append("insufficient_run_count_for_rul")
    if (
        time_to_failure_coverage is None
        or time_to_failure_coverage < active_policy.min_time_to_failure_coverage
    ):
        rul_blockers.append("insufficient_time_to_failure_coverage")
    if not temporal_continuity_ok:
        rul_blockers.append("temporal_continuity_not_verified_for_rul")
    rul_ready = autoencoder_ready and not rul_blockers
    caution.extend(reason for reason in rul_blockers if reason not in caution)

    readiness_level = (
        "blocked"
        if blocked
        else "ready"
        if autoencoder_ready and rul_ready
        else "caution"
    )
    return TemporalModelReadinessAssessment(
        policy_id=active_policy.policy_id,
        available=True,
        readiness_level=readiness_level,
        autoencoder_ready=autoencoder_ready,
        rul_ready=rul_ready,
        blocked_reasons=blocked,
        caution_reasons=list(dict.fromkeys(caution)),
        recommended_next_experiment=_recommended_next_experiment(
            autoencoder_ready,
            rul_ready,
            blocked,
        ),
        estimated_cost_level=_estimated_cost_level(n_windows, len(feature_columns)),
        n_windows=n_windows,
        n_train_windows=n_train_windows,
        n_train_nominal_windows=n_train_nominal_windows,
        n_feature_columns=len(feature_columns),
        n_runs=n_runs,
        temporal_continuity_ok=temporal_continuity_ok,
        time_to_failure_coverage=time_to_failure_coverage,
        split_quality_ok=split_quality_ok,
        leakage_risk=leakage_risk,
        finite_feature_ratio=finite_ratio,
        features_path=features_path,
        predictions_path=predictions_path,
        splits_path=splits_path,
    )


def _unavailable_assessment(
    policy: TemporalModelReadinessPolicy,
    *,
    features_path: str | None,
    predictions_path: str | None,
    splits_path: str | None,
    reason: str,
) -> TemporalModelReadinessAssessment:
    return TemporalModelReadinessAssessment(
        policy_id=policy.policy_id,
        available=False,
        readiness_level="blocked",
        autoencoder_ready=False,
        rul_ready=False,
        blocked_reasons=[reason],
        recommended_next_experiment="generate_temporal_features_before_advanced_models",
        estimated_cost_level="unknown",
        n_windows=0,
        n_train_windows=0,
        n_train_nominal_windows=0,
        n_feature_columns=0,
        n_runs=0,
        temporal_continuity_ok=False,
        time_to_failure_coverage=None,
        split_quality_ok=False,
        leakage_risk="blocked",
        finite_feature_ratio=None,
        features_path=features_path,
        predictions_path=predictions_path,
        splits_path=splits_path,
    )


def _merge_predictions_if_available(
    features: pd.DataFrame,
    predictions_path: str | None,
) -> pd.DataFrame:
    if not predictions_path or not Path(predictions_path).exists():
        return features.copy()
    predictions = pd.read_csv(predictions_path)
    if "window_id" not in features.columns or "window_id" not in predictions.columns:
        return features.copy()
    metadata = [
        column
        for column in predictions.columns
        if column in METADATA_COLUMNS and column != "window_id"
    ]
    return features.merge(
        predictions[["window_id", *metadata]],
        on="window_id",
        how="left",
        suffixes=("", "_prediction"),
    )


def _numeric_feature_columns(features: pd.DataFrame) -> list[str]:
    return [
        column
        for column in features.columns
        if column not in METADATA_COLUMNS
        and pd.api.types.is_numeric_dtype(features[column])
    ]


def _finite_feature_ratio(
    features: pd.DataFrame,
    columns: list[str],
) -> float | None:
    if not columns:
        return None
    matrix = features[columns].apply(pd.to_numeric, errors="coerce")
    total = int(matrix.size)
    if total == 0:
        return None
    return float(matrix.notna().sum().sum() / total)


def _split_count(data: pd.DataFrame, split: str) -> int:
    if "split" not in data.columns:
        return 0
    return int((data["split"].astype(str).str.lower() == split).sum())


def _train_nominal_count(data: pd.DataFrame) -> int:
    if "split" not in data.columns:
        return 0
    train = data[data["split"].astype(str).str.lower() == "train"]
    if train.empty:
        return 0
    return int(_nominal_mask(train).sum())


def _train_degradation_fraction(data: pd.DataFrame) -> float | None:
    if "split" not in data.columns:
        return None
    train = data[data["split"].astype(str).str.lower() == "train"]
    if train.empty:
        return None
    nominal = int(_nominal_mask(train).sum())
    return float(1.0 - nominal / len(train))


def _nominal_mask(data: pd.DataFrame) -> pd.Series:
    if "target" in data.columns:
        target = pd.to_numeric(data["target"], errors="coerce")
        if target.notna().any():
            return target.fillna(1).astype(int) == 0
    if "label" in data.columns:
        return data["label"].astype(str).str.lower().isin(
            {"normal", "nominal", "healthy", "baseline"}
        )
    if "relative_life" in data.columns:
        relative_life = pd.to_numeric(data["relative_life"], errors="coerce")
        return relative_life <= 0.4
    return pd.Series(False, index=data.index)


def _run_count(data: pd.DataFrame) -> int:
    if "run_id" not in data.columns:
        return 1 if not data.empty else 0
    values = {
        str(value)
        for value in data["run_id"].dropna().unique()
        if str(value).strip()
    }
    return len(values) if values else 1


def _temporal_continuity_ok(data: pd.DataFrame) -> bool:
    axis = _temporal_axis(data)
    if axis is None:
        return False
    groups = (
        data.groupby("run_id", sort=False)
        if "run_id" in data.columns
        else [("_single_run", data)]
    )
    checked = 0
    for _run_id, group in groups:
        values = pd.to_numeric(group[axis], errors="coerce").dropna().to_numpy()
        if values.size < 2:
            continue
        checked += 1
        diffs = values[1:] - values[:-1]
        if (diffs < 0).any():
            return False
    return checked > 0


def _temporal_axis(data: pd.DataFrame) -> str | None:
    for column in ["relative_life", "time_since_start_seconds", "window_index"]:
        if column in data.columns and pd.to_numeric(data[column], errors="coerce").notna().sum() >= 2:
            return column
    return None


def _time_to_failure_coverage(data: pd.DataFrame) -> float | None:
    if "time_to_failure_seconds" not in data.columns or data.empty:
        return None
    values = pd.to_numeric(data["time_to_failure_seconds"], errors="coerce")
    return float(values.notna().sum() / len(data))


def _split_quality_ok(data: pd.DataFrame) -> bool:
    if "split" not in data.columns:
        return False
    splits = {str(value).lower() for value in data["split"].dropna().unique()}
    return "train" in splits and bool(splits & {"validation", "test"})


def _leakage_risk(
    train_degradation_fraction: float | None,
    split_quality_ok: bool,
) -> str:
    if train_degradation_fraction is None or not split_quality_ok:
        return "blocked"
    if train_degradation_fraction > 0.20:
        return "blocked"
    if train_degradation_fraction > 0.05:
        return "caution"
    return "ready"


def _estimated_cost_level(n_windows: int, n_features: int) -> str:
    if n_windows <= 0 or n_features <= 0:
        return "unknown"
    footprint = n_windows * n_features
    if footprint < 50_000:
        return "low"
    if footprint < 1_000_000:
        return "moderate"
    return "high"


def _recommended_next_experiment(
    autoencoder_ready: bool,
    rul_ready: bool,
    blocked: list[str],
) -> str:
    if autoencoder_ready and rul_ready:
        return "compare_autoencoder_dense_against_pca_before_rul_experiment"
    if autoencoder_ready:
        return "run_autoencoder_dense_cpu_smoke_before_rul"
    if "insufficient_train_nominal_windows" in blocked:
        return "increase_or_validate_nominal_train_windows"
    if "invalid_or_missing_splits" in blocked:
        return "fix_temporal_splits_before_advanced_models"
    return "use_pca_or_isolation_forest_until_readiness_improves"
