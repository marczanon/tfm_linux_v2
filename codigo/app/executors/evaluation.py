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
from codigo.app.schemas.temporal_health import (
    DEFAULT_SNAPSHOT_AGGREGATION_POLICY,
    DEFAULT_TEMPORAL_GAP_POLICY,
    DEFAULT_TEMPORAL_HEALTH_INDICATOR_POLICY,
    DEFAULT_TEMPORAL_HEALTH_POLICY,
    HealthState,
)
from codigo.app.services.temporal_health_policy import (
    aggregate_temporal_snapshots,
    annotate_temporal_gaps,
    temporal_alert_summary,
    temporal_health_indicator_series,
    temporal_health_population_metrics,
)


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

RUN_TO_FAILURE_V2_PARTITIONS = {
    "baseline_train",
    "calibration",
    "monitoring",
}

NOMINAL_RELATIVE_LIFE_LIMIT = (
    DEFAULT_TEMPORAL_HEALTH_POLICY.alert_policy.nominal_relative_life_limit
)
EARLY_RELATIVE_LIFE_LIMIT = (
    DEFAULT_TEMPORAL_HEALTH_POLICY.alert_policy.early_relative_life_limit
)
LATE_RELATIVE_LIFE_LIMIT = (
    DEFAULT_TEMPORAL_HEALTH_POLICY.alert_policy.late_relative_life_limit
)


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
                    "f1_score": summary["primary_metrics"].get("f1_score"),
                    "binary_metrics_available": summary[
                        "binary_metric_context"
                    ]["available"],
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
        snapshot_trajectory_path = summary["degradation_metrics"].get(
            "snapshot_trajectory_path"
        )
        if snapshot_trajectory_path:
            artifacts.append(
                ArtifactRef(
                    name="evaluation_snapshot_trajectory",
                    artifact_type="metrics",
                    path=str(snapshot_trajectory_path),
                    producer="evaluator",
                    description=(
                        "Trayectoria longitudinal agregada a una fila por captura."
                    ),
                    metadata={
                        "temporal_unit": "snapshot",
                        "n_windows": summary["degradation_metrics"]["n_windows"],
                        "n_snapshots": summary["degradation_metrics"][
                            "n_snapshots"
                        ],
                        "aggregation_policy_id": summary["degradation_metrics"][
                            "snapshot_aggregation_policy_id"
                        ],
                        "temporal_gap_policy_id": summary[
                            "degradation_metrics"
                        ]["temporal_gap_policy_id"],
                        "n_detected_gaps": summary["degradation_metrics"][
                            "n_detected_gaps"
                        ],
                        "n_temporal_segments": summary[
                            "degradation_metrics"
                        ]["n_temporal_segments"],
                    },
                )
            )
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

    causal_v2_unlabeled = _is_causal_v2_unlabeled(data)
    binary_metric_context = _binary_metric_context(data)
    binary_metrics_available = bool(binary_metric_context["available"])
    data["target"] = pd.to_numeric(data["target"], errors="coerce")
    data["predicted_anomaly"] = data["predicted_anomaly"].astype(int)
    data["anomaly_score"] = data["anomaly_score"].astype(float)
    _validate_prediction_values(
        data,
        require_binary_target=binary_metrics_available,
    )

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    metrics_by_split = {
        split: (
            _metrics_for_split(group)
            if binary_metrics_available
            else _descriptive_metrics_for_split(group)
        )
        for split, group in data.groupby("split", sort=True)
    }
    primary_metrics = metrics_by_split[primary_split]
    degradation_metrics = _degradation_metrics(
        data,
        snapshot_trajectory_path=output / "snapshot_trajectory.csv",
        causal_v2_unlabeled=causal_v2_unlabeled,
    )
    metric_families = (
        ["binary_classification"] if binary_metrics_available else []
    )
    if degradation_metrics["available"]:
        metric_families.append("run_to_failure_degradation")
    summary = {
        "predictions_path": str(predictions_path),
        "metrics_path": str(output / "metrics.json"),
        "report_fragment_path": str(output / "evaluation_summary.md"),
        "generated_at": datetime.now(UTC).isoformat(),
        "primary_split": primary_split,
        "metric_families": metric_families,
        "binary_metric_context": binary_metric_context,
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


def _descriptive_metrics_for_split(data: pd.DataFrame) -> dict[str, Any]:
    """Resume un split sin fabricar metricas supervisadas sin ground truth."""

    predictions = data["predicted_anomaly"].to_numpy(dtype=int)
    return {
        "n_samples": int(len(data)),
        "label_counts": dict(Counter(data["label"])),
        "predicted_counts": {
            str(key): value for key, value in Counter(predictions).items()
        },
        "binary_metrics_available": False,
    }


def _degradation_metrics(
    data: pd.DataFrame,
    *,
    snapshot_trajectory_path: Path | None = None,
    causal_v2_unlabeled: bool = False,
) -> dict[str, Any]:
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

    snapshot_rows = annotate_temporal_gaps(
        aggregate_temporal_snapshots(
            temporal.to_dict("records"),
            policy=DEFAULT_SNAPSHOT_AGGREGATION_POLICY,
        ),
        policy=DEFAULT_TEMPORAL_GAP_POLICY,
    )
    if not snapshot_rows:
        return _unavailable_degradation_metrics(
            "temporal windows could not be aggregated into usable snapshots"
        )
    snapshots = pd.DataFrame(snapshot_rows)
    analyses = [
        _degradation_analysis_for_run(str(run_id), group)
        for run_id, group in snapshots.groupby("run_id", sort=True)
    ]
    run_metrics = [item[0] for item in analyses]
    trajectory_rows = [row for item in analyses for row in item[1]]
    trajectory = pd.DataFrame(trajectory_rows)
    if snapshot_trajectory_path is not None:
        trajectory.to_csv(snapshot_trajectory_path, index=False)

    n_detected_gaps = int(snapshots["gap_detected"].fillna(False).astype(bool).sum())
    n_temporal_segments = int(
        sum(
            group["temporal_segment_id"].nunique()
            for _, group in snapshots.groupby("run_id", sort=True)
        )
    )
    cadence_intervals = snapshots["cadence_matches_expected"].dropna()
    n_cadence_matches = int(cadence_intervals.astype(bool).sum())
    detected_runs = [
        item for item in run_metrics if item["detected_before_failure"] is True
    ]
    confirmed_runs = [
        item
        for item in run_metrics
        if item["confirmed_degradation_before_failure"] is True
    ]
    missed_runs = [item for item in run_metrics if item["missed_failure"] is True]
    missed_confirmed_runs = [
        item for item in run_metrics if item["missed_confirmed_degradation"] is True
    ]
    lead_times = [item["lead_time_to_failure"] for item in run_metrics]
    persistent_lead_times = [
        item["persistent_lead_time_to_failure"] for item in run_metrics
    ]
    false_alarm_rates = [
        item["false_alarm_rate_nominal"] for item in run_metrics
    ]
    trend_values = [item["score_trend_spearman"] for item in run_metrics]
    separation_values = [
        item["initial_final_separation"] for item in run_metrics
    ]
    isolated_alert_points = [item["isolated_alert_points"] for item in run_metrics]
    alert_episodes = [item["alert_episodes"] for item in run_metrics]
    longest_alert_streaks = [item["longest_alert_streak"] for item in run_metrics]
    health_index_drops = [item["health_index_drop"] for item in run_metrics]
    health_monotonicity = [item["health_monotonicity"] for item in run_metrics]
    health_robustness = [item["health_robustness"] for item in run_metrics]
    health_nominal_volatility = [
        item["health_nominal_volatility"] for item in run_metrics
    ]
    health_trend_strength = [
        item["health_degradation_trend_strength"] for item in run_metrics
    ]
    health_indicator_scores = [
        item["health_indicator_score"] for item in run_metrics
    ]
    health_population = temporal_health_population_metrics(run_metrics)
    metrics = {
        "available": True,
        "metric_type": "run_to_failure_degradation",
        "temporal_unit": DEFAULT_SNAPSHOT_AGGREGATION_POLICY.temporal_unit,
        "binary_metrics_unit": "window",
        "snapshot_aggregation_policy_id": (
            DEFAULT_SNAPSHOT_AGGREGATION_POLICY.policy_id
        ),
        "snapshot_aggregation_policy": (
            DEFAULT_SNAPSHOT_AGGREGATION_POLICY.model_dump(mode="json")
        ),
        "snapshot_alert_fraction_threshold": (
            DEFAULT_SNAPSHOT_AGGREGATION_POLICY.alert_fraction_threshold
        ),
        "temporal_gap_policy_id": DEFAULT_TEMPORAL_GAP_POLICY.policy_id,
        "temporal_gap_policy": DEFAULT_TEMPORAL_GAP_POLICY.model_dump(mode="json"),
        "expected_cadence_seconds": (
            DEFAULT_TEMPORAL_GAP_POLICY.expected_cadence_seconds
        ),
        "max_contiguous_interval_seconds": (
            DEFAULT_TEMPORAL_GAP_POLICY.max_contiguous_interval_seconds
        ),
        "n_detected_gaps": n_detected_gaps,
        "n_temporal_segments": n_temporal_segments,
        "n_cadence_intervals": int(len(cadence_intervals)),
        "n_cadence_matches": n_cadence_matches,
        "cadence_match_rate": _ratio(n_cadence_matches, len(cadence_intervals)),
        "health_policy_id": DEFAULT_TEMPORAL_HEALTH_POLICY.policy_id,
        "alert_policy_id": DEFAULT_TEMPORAL_HEALTH_POLICY.alert_policy.policy_id,
        "health_indicator_policy_id": (
            DEFAULT_TEMPORAL_HEALTH_INDICATOR_POLICY.policy_id
        ),
        "persistent_alert_min_windows": (
            DEFAULT_TEMPORAL_HEALTH_POLICY.alert_policy.persistent_alert_min_windows
        ),
        "persistent_alert_min_snapshots": (
            DEFAULT_TEMPORAL_HEALTH_POLICY.alert_policy.persistent_alert_min_windows
        ),
        "n_runs": int(len(run_metrics)),
        "n_windows": int(len(temporal)),
        "n_snapshots": int(len(snapshots)),
        "snapshot_trajectory_path": (
            None
            if snapshot_trajectory_path is None
            else str(snapshot_trajectory_path)
        ),
        "detected_runs": int(len(detected_runs)),
        "confirmed_degradation_runs": int(len(confirmed_runs)),
        "missed_runs": int(len(missed_runs)),
        "missed_confirmed_degradation_runs": int(len(missed_confirmed_runs)),
        "detected_before_failure_rate": _ratio(len(detected_runs), len(run_metrics)),
        "confirmed_degradation_before_failure_rate": _ratio(
            len(confirmed_runs),
            len(run_metrics),
        ),
        "median_lead_time_to_failure": _median_defined(lead_times),
        "mean_lead_time_to_failure": _mean_defined(lead_times),
        "median_persistent_lead_time_to_failure": _median_defined(
            persistent_lead_times
        ),
        "mean_persistent_lead_time_to_failure": _mean_defined(
            persistent_lead_times
        ),
        "mean_false_alarm_rate_nominal": _mean_defined(false_alarm_rates),
        "mean_score_trend_spearman": _mean_defined(trend_values),
        "mean_initial_final_separation": _mean_defined(separation_values),
        "mean_isolated_alert_points": _mean_defined(isolated_alert_points),
        "mean_isolated_alert_snapshots": _mean_defined(isolated_alert_points),
        "mean_alert_episodes": _mean_defined(alert_episodes),
        "mean_longest_alert_streak": _mean_defined(longest_alert_streaks),
        "mean_longest_alert_snapshot_streak": _mean_defined(
            longest_alert_streaks
        ),
        "mean_health_index_drop": _mean_defined(health_index_drops),
        "mean_health_monotonicity": _mean_defined(health_monotonicity),
        "mean_health_robustness": _mean_defined(health_robustness),
        "mean_health_nominal_volatility": _mean_defined(health_nominal_volatility),
        "mean_health_degradation_trend_strength": _mean_defined(
            health_trend_strength
        ),
        "mean_health_indicator_score": _mean_defined(health_indicator_scores),
        "health_trendability": health_population["health_trendability"],
        "health_prognosability": health_population["health_prognosability"],
        "run_metrics": run_metrics,
        "notes": [
            "Temporal metrics use anomaly_score and alert chronology; binary "
            "classification metrics remain reported separately per window.",
            "Longitudinal metrics aggregate windows by run_id + file_id using "
            f"{DEFAULT_SNAPSHOT_AGGREGATION_POLICY.policy_id}; persistence, "
            "onset, false alarms and lead time count snapshots, not overlapping "
            "windows.",
            f"Temporal continuity uses {DEFAULT_TEMPORAL_GAP_POLICY.policy_id}; "
            "alert persistence and causal Health Indicator smoothing restart "
            "after every detected gap.",
            "For causal v2 partitions, the pre-monitoring baseline and "
            "calibration partitions define the false-alarm reference; legacy "
            "runs retain the label=normal/relative-life fallback.",
            "Confirmed degradation requires a warning/critical streak with "
            f"{DEFAULT_TEMPORAL_HEALTH_POLICY.alert_policy.persistent_alert_min_windows} "
            "consecutive snapshots under the declared temporal health policy.",
        ],
    }
    if causal_v2_unlabeled:
        _add_causal_v2_interpretation(metrics)
    return metrics


def _add_causal_v2_interpretation(metrics: dict[str, Any]) -> None:
    """Añade aliases no supervisados sin romper contratos temporales legacy.

    Los nombres historicos ``*_before_failure`` se conservan para poder leer
    runs anteriores, pero no constituyen ground truth de onset o fallo fisico en
    el protocolo causal v2. Los consumidores nuevos deben usar estos campos.
    """

    metrics.update(
        {
            "interpretation_mode": "causal_v2_unlabeled",
            "acceptance_scope": "descriptive_operational_protocol_only",
            "binary_ground_truth_available": False,
            "physical_onset_ground_truth_available": False,
            "retrospective_endpoint_interpretation": (
                "end_of_recorded_trajectory"
            ),
            "persistent_alert_runs": metrics.get(
                "confirmed_degradation_runs"
            ),
            "persistent_alert_run_rate": metrics.get(
                "confirmed_degradation_before_failure_rate"
            ),
            "mean_first_persistent_alert_time_to_trajectory_end": metrics.get(
                "mean_persistent_lead_time_to_failure"
            ),
            "mean_pre_monitoring_alert_rate": metrics.get(
                "mean_false_alarm_rate_nominal"
            ),
        }
    )
    for run_metric in metrics.get("run_metrics", []):
        run_metric.update(
            {
                "persistent_alert_observed": not bool(
                    run_metric.get("missed_confirmed_degradation", True)
                ),
                "first_persistent_alert_time_to_trajectory_end": (
                    run_metric.get("persistent_lead_time_to_failure")
                ),
                "pre_monitoring_alert_rate": run_metric.get(
                    "false_alarm_rate_nominal"
                ),
                "physical_onset_confirmed": None,
                "physical_failure_detected": None,
            }
        )
    metrics["notes"].append(
        "Causal v2 has no physical-onset or per-window failure ground truth; "
        "persistent alerts are algorithmic events and retrospective times are "
        "measured to the end of the recorded trajectory."
    )


def _degradation_metrics_for_run(run_id: str, group: pd.DataFrame) -> dict[str, Any]:
    return _degradation_analysis_for_run(run_id, group)[0]


def _degradation_analysis_for_run(
    run_id: str,
    group: pd.DataFrame,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Calcula una run y devuelve tambien su trayectoria cientifica enriquecida."""

    ordered = _temporal_order(group)
    n_windows = (
        int(pd.to_numeric(ordered["n_windows"], errors="coerce").fillna(0).sum())
        if "n_windows" in ordered.columns
        else int(len(ordered))
    )
    scores = ordered["anomaly_score"].dropna()
    score_min = None if scores.empty else _safe_float(scores.min())
    score_max = None if scores.empty else _safe_float(scores.max())
    health_indicator = temporal_health_indicator_series(
        ordered.to_dict("records"),
        score_min=score_min,
        score_max=score_max,
        health_policy=DEFAULT_TEMPORAL_HEALTH_POLICY,
        indicator_policy=DEFAULT_TEMPORAL_HEALTH_INDICATOR_POLICY,
    )
    health_points = health_indicator["points"]
    health_metrics = health_indicator["metrics"]
    health_states: list[HealthState] = [
        str(point["health_state"])  # type: ignore[list-item]
        for point in health_points
    ]
    segment_ids = _temporal_segment_ids(ordered)
    alert_summary = temporal_alert_summary(
        health_states,
        policy=DEFAULT_TEMPORAL_HEALTH_POLICY,
        segment_ids=segment_ids,
    )
    first_persistent_index = alert_summary["first_persistent_index"]
    first_persistent_alert = (
        None
        if first_persistent_index is None
        else ordered.iloc[int(first_persistent_index)].to_dict()
    )
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
    persistent_lead_time = (
        None
        if first_persistent_alert is None
        else _safe_float(first_persistent_alert.get("time_to_failure_seconds"))
    )
    confirmed_degradation_before_failure = (
        False
        if first_persistent_alert is None
        else True if persistent_lead_time is None else persistent_lead_time >= 0.0
    )
    missed_failure = first_alert is None or detected_before_failure is False
    missed_confirmed_degradation = (
        first_persistent_alert is None
        or confirmed_degradation_before_failure is False
    )
    false_alarm_rate, false_alarm_reference, false_alarm_reference_snapshots = (
        _false_alarm_rate_nominal(ordered)
    )
    run_metrics = {
        "run_id": run_id,
        "temporal_unit": DEFAULT_SNAPSHOT_AGGREGATION_POLICY.temporal_unit,
        "snapshot_aggregation_policy_id": (
            DEFAULT_SNAPSHOT_AGGREGATION_POLICY.policy_id
        ),
        "snapshot_alert_fraction_threshold": (
            DEFAULT_SNAPSHOT_AGGREGATION_POLICY.alert_fraction_threshold
        ),
        "temporal_gap_policy_id": DEFAULT_TEMPORAL_GAP_POLICY.policy_id,
        "n_detected_gaps": int(
            ordered["gap_detected"].fillna(False).astype(bool).sum()
        ),
        "n_temporal_segments": int(ordered["temporal_segment_id"].nunique()),
        "health_policy_id": DEFAULT_TEMPORAL_HEALTH_POLICY.policy_id,
        "alert_policy_id": DEFAULT_TEMPORAL_HEALTH_POLICY.alert_policy.policy_id,
        "health_indicator_policy_id": health_indicator["policy_id"],
        "persistent_alert_min_windows": (
            DEFAULT_TEMPORAL_HEALTH_POLICY.alert_policy.persistent_alert_min_windows
        ),
        "persistent_alert_min_snapshots": (
            DEFAULT_TEMPORAL_HEALTH_POLICY.alert_policy.persistent_alert_min_windows
        ),
        "n_windows": n_windows,
        "n_snapshots": int(len(ordered)),
        "first_alert_snapshot_id": (
            None if first_alert is None else str(first_alert.get("file_id"))
        ),
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
        "first_persistent_alert_time": (
            None
            if first_persistent_alert is None
            else _first_alert_time(first_persistent_alert)
        ),
        "first_persistent_alert_snapshot_id": (
            None
            if first_persistent_alert is None
            else str(first_persistent_alert.get("file_id"))
        ),
        "first_persistent_alert_relative_life": (
            None
            if first_persistent_alert is None
            else _safe_float(first_persistent_alert.get("relative_life"))
        ),
        "time_to_confirmed_degradation": (
            None
            if first_persistent_alert is None
            else _safe_float(first_persistent_alert.get("time_since_start_seconds"))
        ),
        "persistent_lead_time_to_failure": persistent_lead_time,
        "confirmed_degradation_before_failure": bool(
            confirmed_degradation_before_failure
        ),
        "missed_confirmed_degradation": bool(missed_confirmed_degradation),
        "false_alarm_rate_nominal": false_alarm_rate,
        "false_alarm_reference": false_alarm_reference,
        "false_alarm_reference_snapshots": false_alarm_reference_snapshots,
        "alert_persistence": _max_consecutive_alerts(
            ordered["predicted_anomaly"],
            segment_ids=segment_ids,
        ),
        "isolated_alert_points": int(alert_summary["isolated_alert_points"] or 0),
        "isolated_alert_snapshots": int(
            alert_summary["isolated_alert_points"] or 0
        ),
        "alert_episodes": int(alert_summary["alert_episodes"] or 0),
        "longest_alert_streak": int(alert_summary["longest_alert_streak"] or 0),
        "longest_alert_snapshot_streak": int(
            alert_summary["longest_alert_streak"] or 0
        ),
        "initial_health_index": health_metrics["initial_health_index"],
        "final_health_index": health_metrics["final_health_index"],
        "health_index_drop": health_metrics["health_index_drop"],
        "health_index_drop_ratio": health_metrics["health_index_drop_ratio"],
        "health_slope": health_metrics["health_slope"],
        "health_trend_spearman": health_metrics["health_trend_spearman"],
        "health_degradation_trend_strength": health_metrics[
            "health_degradation_trend_strength"
        ],
        "health_monotonicity": health_metrics["health_monotonicity"],
        "health_robustness": health_metrics["health_robustness"],
        "health_nominal_volatility": health_metrics["health_nominal_volatility"],
        "health_indicator_score": health_metrics["health_indicator_score"],
        "health_dominant_evidence": health_metrics["health_dominant_evidence"],
        "health_indicator_status": health_metrics["health_indicator_status"],
        "score_trend_spearman": _spearman(
            ordered["relative_life"], ordered["anomaly_score"]
        ),
        "score_slope": _slope(ordered["relative_life"], ordered["anomaly_score"]),
        "initial_mean_score": early_mean,
        "final_mean_score": late_mean,
        "initial_final_separation": _difference(late_mean, early_mean),
        "initial_final_ratio": _ratio_float(late_mean, early_mean),
        "monotonicity": _monotonicity(
            ordered["anomaly_score"],
            segment_ids=segment_ids,
        ),
    }
    trajectory_rows = [
        _enriched_trajectory_row(row, point)
        for row, point in zip(
            ordered.to_dict("records"),
            health_points,
            strict=True,
        )
    ]
    return run_metrics, trajectory_rows


def _unavailable_degradation_metrics(reason: str) -> dict[str, Any]:
    return {
        "available": False,
        "metric_type": "run_to_failure_degradation",
        "reason": reason,
    }


def _validate_prediction_values(
    data: pd.DataFrame,
    *,
    require_binary_target: bool = True,
) -> None:
    if data.empty:
        raise ValueError("predictions file is empty")
    if data["window_id"].duplicated().any():
        raise ValueError("duplicated window_id values found")
    numeric_columns = ["predicted_anomaly", "anomaly_score"]
    if require_binary_target:
        numeric_columns.append("target")
    if data[numeric_columns].isna().any().any():
        raise ValueError("predictions contain null numeric values")
    if require_binary_target and not set(data["target"]).issubset({0, 1}):
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
    partitions = _normalized_column_values(data, "temporal_partition")
    causal_v2_unlabeled = _is_causal_v2_unlabeled(data)
    context = {
        "available": not causal_v2_unlabeled,
        "label_source": label_source,
        "label_granularity": label_granularity,
        "temporal_partitions": sorted(partitions),
    }
    if causal_v2_unlabeled:
        context.update(
            {
                "reason": (
                    "The official causal run-to-failure v2 protocol has no "
                    "window-level ground truth in calibration/monitoring."
                ),
                "target_interpretation": "not_ground_truth",
                "warning": (
                    "Precision, recall, F1, ROC-AUC and PR-AUC are not "
                    "published: unknown monitoring observations are not fault "
                    "labels."
                ),
            }
        )
        return context
    if label_source is None:
        context["warning"] = (
            "label_source is not present in predictions.csv; interpret binary "
            "metrics with the run dataset context."
        )
    return context


def _is_causal_v2_unlabeled(data: pd.DataFrame) -> bool:
    partitions = _normalized_column_values(data, "temporal_partition")
    if not partitions or not partitions.issubset(RUN_TO_FAILURE_V2_PARTITIONS):
        return False
    if "monitoring" not in partitions:
        return False

    policy_ids = (
        _normalized_column_values(data, "dataset_policy_id")
        | _normalized_column_values(data, "partition_policy_id")
    )
    explicit_v2 = "nasa_ims_run_to_failure_v2" in policy_ids
    held_out = data[
        data["temporal_partition"].astype(str).str.strip().str.lower().isin(
            {"calibration", "monitoring"}
        )
    ]
    held_out_labels = _normalized_column_values(held_out, "label")
    unlabeled_held_out = not held_out_labels or held_out_labels.issubset(
        {"unknown", "none"}
    )
    held_out_sources = _normalized_column_values(held_out, "label_source")
    no_official_sources = not held_out_sources or held_out_sources.issubset(
        {"none", "unknown"}
    )
    return bool(explicit_v2 or (unlabeled_held_out and no_official_sources))


def _normalized_column_values(data: pd.DataFrame, column: str) -> set[str]:
    if column not in data.columns:
        return set()
    return {
        str(value).strip().lower()
        for value in data[column].dropna().unique()
        if str(value).strip()
    }


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
        for column in [
            "timestamp_start",
            "time_since_start_seconds",
            "window_index",
            "relative_life",
        ]
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


def _temporal_segment_ids(data: pd.DataFrame) -> list[int]:
    if "temporal_segment_id" not in data.columns:
        return [0] * len(data)
    return (
        pd.to_numeric(data["temporal_segment_id"], errors="coerce")
        .fillna(0)
        .astype(int)
        .tolist()
    )


def _enriched_trajectory_row(
    row: dict[str, Any],
    health_point: dict[str, Any],
) -> dict[str, Any]:
    enriched = dict(row)
    for key in (
        "score_ratio",
        "risk_index",
        "risk_index_smoothed",
        "health_index",
        "health_index_raw",
        "health_index_smoothed",
        "health_trend",
        "health_state",
        "state_reason",
        "dominant_evidence",
        "health_policy_id",
        "alert_policy_id",
        "health_indicator_policy_id",
    ):
        enriched[key] = health_point.get(key)
    return enriched


def _false_alarm_rate_nominal(
    data: pd.DataFrame,
) -> tuple[float | None, str | None, int]:
    nominal = pd.DataFrame()
    source: str | None = None
    causal_v2_reference = False
    if "temporal_partition" in data.columns:
        partitions = data["temporal_partition"].astype(str).str.strip().str.lower()
        if partitions.isin(RUN_TO_FAILURE_V2_PARTITIONS).any():
            causal_v2_reference = True
            nominal = data[
                partitions.isin({"baseline_train", "calibration"})
            ]
            source = "causal_v2_pre_monitoring_partitions"
    if causal_v2_reference and nominal.empty:
        return None, source, 0
    if "label" in data.columns:
        if nominal.empty and source is None:
            nominal = data[data["label"].astype(str).str.lower() == "normal"]
            source = "label_normal"
    if nominal.empty:
        nominal = data[data["relative_life"] <= NOMINAL_RELATIVE_LIFE_LIMIT]
        source = "legacy_relative_life_fallback"
    if nominal.empty:
        return None, source, 0
    return (
        _safe_float(nominal["predicted_anomaly"].mean()),
        source,
        int(len(nominal)),
    )


def _max_consecutive_alerts(
    values: pd.Series,
    *,
    segment_ids: list[int] | None = None,
) -> int:
    if segment_ids is not None and len(segment_ids) != len(values):
        raise ValueError("segment_ids must match alert values length")
    best = 0
    current = 0
    previous_segment: int | None = None
    for index, value in enumerate(values.astype(int)):
        current_segment = 0 if segment_ids is None else segment_ids[index]
        if previous_segment is not None and current_segment != previous_segment:
            current = 0
        if value == 1:
            current += 1
            best = max(best, current)
        else:
            current = 0
        previous_segment = current_segment
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


def _monotonicity(
    values: pd.Series,
    *,
    segment_ids: list[int] | None = None,
) -> float | None:
    if segment_ids is not None and len(segment_ids) != len(values):
        raise ValueError("segment_ids must match score values length")
    scores = pd.to_numeric(values, errors="coerce").tolist()
    diffs: list[float] = []
    previous: float | None = None
    previous_segment: int | None = None
    for index, score in enumerate(scores):
        segment = 0 if segment_ids is None else segment_ids[index]
        if score is None or pd.isna(score):
            continue
        numeric_score = float(score)
        if previous is not None and previous_segment == segment:
            difference = numeric_score - previous
            if difference != 0.0:
                diffs.append(difference)
        previous = numeric_score
        previous_segment = segment
    if not diffs:
        return None
    return _safe_float(np.mean(np.asarray(diffs) > 0.0))


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
    lines = [
        "# Evaluacion de deteccion de anomalias",
        "",
        f"- Familias metricas: `{', '.join(summary['metric_families'])}`",
        f"- Split principal: `{summary['primary_split']}`",
        f"- Predicciones evaluadas: `{summary['n_predictions']}`",
    ]
    binary_context = summary.get("binary_metric_context", {})
    if binary_context.get("available") is False:
        lines.extend(
            [
                "- Metricas binarias supervisadas: `no publicadas`",
                f"- Motivo: {binary_context.get('reason', 'ground truth no disponible')}",
                "- Las observaciones `unknown` no se interpretan como anomalías reales.",
                "",
            ]
        )
    else:
        matrix = metrics["confusion_matrix"]
        lines.extend(
            [
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
    degradation = summary.get("degradation_metrics", {})
    if degradation.get("available") is True:
        lines.extend(_degradation_report_markdown(degradation))
    return "\n".join(lines)


def _degradation_report_markdown(metrics: dict[str, Any]) -> list[str]:
    if metrics.get("interpretation_mode") == "causal_v2_unlabeled":
        return _causal_v2_degradation_report_markdown(metrics)

    lines = [
        "## Evaluacion temporal de degradacion",
        "",
        f"- Runs evaluados: `{metrics['n_runs']}`",
        f"- Ventanas evaluadas por las metricas binarias: `{metrics['n_windows']}`",
        f"- Capturas de la trayectoria temporal: `{metrics['n_snapshots']}`",
        f"- Unidad longitudinal: `{metrics['temporal_unit']}`",
        f"- Politica de agregacion: `{metrics['snapshot_aggregation_policy_id']}` "
        f"(fraccion de alerta >= {metrics['snapshot_alert_fraction_threshold']:.2f})",
        f"- Politica de gaps: `{metrics['temporal_gap_policy_id']}` "
        f"({metrics['n_detected_gaps']} gaps; {metrics['n_temporal_segments']} segmentos)",
        f"- Cadencia esperada: `{metrics['expected_cadence_seconds']:.0f}` s; "
        f"coincidencia: `{_format_optional(metrics['cadence_match_rate'])}`",
        f"- Politica de salud temporal: `{metrics['health_policy_id']}`",
        f"- Politica de Health Indicator: `{metrics['health_indicator_policy_id']}`",
        f"- Politica de persistencia: `{metrics['alert_policy_id']}` "
        f"({metrics['persistent_alert_min_snapshots']} capturas)",
        f"- Runs detectados antes de fallo: `{metrics['detected_runs']}`",
        f"- Runs con degradacion confirmada antes de fallo: `{metrics['confirmed_degradation_runs']}`",
        f"- Runs perdidos: `{metrics['missed_runs']}`",
        f"- Lead time medio a fallo: `{_format_optional(metrics['mean_lead_time_to_failure'])}`",
        f"- Lead time medio persistente a fallo: `{_format_optional(metrics['mean_persistent_lead_time_to_failure'])}`",
        f"- Falsa alarma nominal media: `{_format_optional(metrics['mean_false_alarm_rate_nominal'])}`",
        f"- Tendencia Spearman media: `{_format_optional(metrics['mean_score_trend_spearman'])}`",
        f"- Separacion inicial-final media: `{_format_optional(metrics['mean_initial_final_separation'])}`",
        f"- Caida media del Health Index: `{_format_optional(metrics['mean_health_index_drop'])}`",
        f"- Monotonicidad media del Health Index: `{_format_optional(metrics['mean_health_monotonicity'])}`",
        f"- Robustez media del Health Index: `{_format_optional(metrics['mean_health_robustness'])}`",
        f"- Volatilidad nominal media del Health Index: `{_format_optional(metrics['mean_health_nominal_volatility'])}`",
        "",
        "| run_id | windows | snapshots | first_alert | first_persistent | persistent_lead_time | health_drop | health_monotonicity | health_robustness | false_alarm_rate_nominal | missed_confirmed |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    for item in metrics["run_metrics"][:12]:
        lines.append(
            "| "
            f"{item['run_id']} | "
            f"{item['n_windows']} | "
            f"{item['n_snapshots']} | "
            f"{_format_optional(item['first_alert_relative_life'])} | "
            f"{_format_optional(item['first_persistent_alert_relative_life'])} | "
            f"{_format_optional(item['persistent_lead_time_to_failure'])} | "
            f"{_format_optional(item['health_index_drop'])} | "
            f"{_format_optional(item['health_monotonicity'])} | "
            f"{_format_optional(item['health_robustness'])} | "
            f"{_format_optional(item['false_alarm_rate_nominal'])} | "
            f"{item['missed_confirmed_degradation']} |"
        )
    lines.append("")
    return lines


def _causal_v2_degradation_report_markdown(
    metrics: dict[str, Any],
) -> list[str]:
    """Renderiza el protocolo oficial ciego sin afirmaciones supervisadas."""

    lines = [
        "## Evaluacion temporal causal sin ground truth fisico",
        "",
        "- Alcance: `descriptivo y operativo interno`; no valida deteccion, diagnostico ni onset fisico.",
        "- Ground truth de onset fisico: `no disponible`",
        "- RUL estimado: `no disponible`",
        f"- Runs evaluados: `{metrics['n_runs']}`",
        f"- Ventanas procesadas: `{metrics['n_windows']}`",
        f"- Capturas de la trayectoria temporal: `{metrics['n_snapshots']}`",
        f"- Unidad longitudinal: `{metrics['temporal_unit']}`",
        f"- Politica de agregacion: `{metrics['snapshot_aggregation_policy_id']}` "
        f"(fraccion de alerta >= {metrics['snapshot_alert_fraction_threshold']:.2f})",
        f"- Politica de gaps: `{metrics['temporal_gap_policy_id']}` "
        f"({metrics['n_detected_gaps']} gaps; {metrics['n_temporal_segments']} segmentos)",
        f"- Cadencia esperada: `{metrics['expected_cadence_seconds']:.0f}` s; "
        f"coincidencia: `{_format_optional(metrics['cadence_match_rate'])}`",
        f"- Politica de persistencia: `{metrics['alert_policy_id']}` "
        f"({metrics['persistent_alert_min_snapshots']} capturas)",
        f"- Runs con alerta algoritmica persistente: `{metrics['persistent_alert_runs']}`",
        "- Tasa de runs con alerta persistente: "
        f"`{_format_optional(metrics['persistent_alert_run_rate'])}`",
        "- Tiempo retrospectivo medio desde la primera alerta persistente "
        "hasta el final registrado: "
        f"`{_format_optional(metrics['mean_first_persistent_alert_time_to_trajectory_end'])}` s",
        "- Tasa media de alertas de snapshot en baseline+calibracion: "
        f"`{_format_optional(metrics['mean_pre_monitoring_alert_rate'])}`",
        f"- Tendencia Spearman media del score: `{_format_optional(metrics['mean_score_trend_spearman'])}`",
        f"- Caida media del Health Index: `{_format_optional(metrics['mean_health_index_drop'])}`",
        f"- Monotonicidad media del Health Index: `{_format_optional(metrics['mean_health_monotonicity'])}`",
        f"- Robustez media del Health Index: `{_format_optional(metrics['mean_health_robustness'])}`",
        "",
        "| run_id | windows | snapshots | primera alerta persistente | tiempo hasta final registrado (s) | HI drop | HI monotonicidad | HI robustez | tasa alertas pre-monitorizacion |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for item in metrics["run_metrics"][:12]:
        lines.append(
            "| "
            f"{item['run_id']} | "
            f"{item['n_windows']} | "
            f"{item['n_snapshots']} | "
            f"{_format_optional(item['first_persistent_alert_relative_life'])} | "
            f"{_format_optional(item['first_persistent_alert_time_to_trajectory_end'])} | "
            f"{_format_optional(item['health_index_drop'])} | "
            f"{_format_optional(item['health_monotonicity'])} | "
            f"{_format_optional(item['health_robustness'])} | "
            f"{_format_optional(item['pre_monitoring_alert_rate'])} |"
        )
    lines.extend(
        [
            "",
            "Los campos temporales historicos con sufijo `before_failure` se "
            "conservan solo por compatibilidad; en esta politica significan "
            "presencia de una alerta antes del final registrado, no confirmacion "
            "de un fallo fisico.",
            "",
        ]
    )
    return lines


def _format_optional(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"
