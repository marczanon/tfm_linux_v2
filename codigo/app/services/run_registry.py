"""Registro consultable de ejecuciones persistidas."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.services.run_persistence import (
    DEFAULT_RUNS_DIR,
    RunEvidencePack,
    RunIndexEntry,
    RunSnapshot,
    load_run_index,
    load_run_snapshot,
    render_run_audit_report,
)


MetricName = str
MetricFamily = Literal["binary_classification", "run_to_failure_degradation"]


DEGRADATION_METRIC_NAMES = [
    "degradation_detected_before_failure_rate",
    "degradation_mean_lead_time_to_failure",
    "degradation_mean_false_alarm_rate_nominal",
    "degradation_mean_score_trend_spearman",
    "degradation_missed_runs",
    "degradation_mean_initial_final_separation",
]


class RunComparisonRow(StrictBaseModel):
    """Fila compacta para comparar una ejecucion."""

    run_id: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    current_stage: str = Field(min_length=1)
    approved: bool | None = None
    supervision_profile: str | None = None
    label_source: str | None = None
    label_granularity: str | None = None
    model_name: str | None = None
    metric_families: list[str] = Field(default_factory=list)
    precision: float | None = None
    recall: float | None = None
    f1_score: float | None = None
    false_positive_rate: float | None = None
    degradation_available: bool | None = None
    degradation_n_runs: int | None = None
    degradation_detected_before_failure_rate: float | None = None
    degradation_mean_lead_time_to_failure: float | None = None
    degradation_mean_false_alarm_rate_nominal: float | None = None
    degradation_mean_score_trend_spearman: float | None = None
    degradation_missed_runs: int | None = None
    degradation_mean_initial_final_separation: float | None = None
    report_path: str | None = None
    snapshot_path: str = Field(min_length=1)


class MetricComparison(StrictBaseModel):
    """Resumen de mejor y peor ejecucion para una metrica."""

    metric: MetricName
    metric_family: MetricFamily = "binary_classification"
    higher_is_better: bool
    best_run_id: str | None = None
    best_value: float | None = None
    worst_run_id: str | None = None
    worst_value: float | None = None
    spread: float | None = None


class RunComparison(StrictBaseModel):
    """Comparacion de metricas entre ejecuciones persistidas."""

    generated_at: datetime
    run_ids: list[str] = Field(min_length=2)
    rows: list[RunComparisonRow] = Field(min_length=2)
    metrics: list[MetricComparison]
    degradation_metrics: list[MetricComparison] = Field(default_factory=list)


def list_runs(
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
    *,
    dataset: str | None = None,
    current_stage: str | None = None,
    approved: bool | None = None,
) -> list[RunIndexEntry]:
    """Lista ejecuciones persistidas, con filtros exactos opcionales."""

    runs = load_run_index(runs_dir).runs
    if dataset is not None:
        runs = [run for run in runs if run.dataset == dataset]
    if current_stage is not None:
        runs = [run for run in runs if run.current_stage == current_stage]
    if approved is not None:
        runs = [run for run in runs if run.approved == approved]
    return runs


def get_run(
    run_id: str,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
) -> RunSnapshot:
    """Carga la metadata de una ejecucion por `run_id`."""

    return load_run_snapshot(run_id, runs_dir)


def get_run_artifacts(
    run_id: str,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
) -> list[dict[str, Any]]:
    """Devuelve los artefactos persistidos de una ejecucion."""

    snapshot = get_run(run_id, runs_dir)
    payload = json.loads(Path(snapshot.artifacts_path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"artifacts payload must be a list for run {run_id}")
    return [item for item in payload if isinstance(item, dict)]


def get_run_evidence_pack(
    run_id: str,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
) -> RunEvidencePack:
    """Carga el evidence pack estructurado de una ejecucion."""

    snapshot = get_run(run_id, runs_dir)
    evidence_path = _snapshot_optional_path(
        snapshot.evidence_pack_path,
        snapshot.snapshot_dir,
        "evidence_pack.json",
    )
    if not evidence_path.exists():
        raise FileNotFoundError(f"evidence pack not found for run: {run_id}")
    payload = json.loads(evidence_path.read_text(encoding="utf-8"))
    return RunEvidencePack.model_validate(payload)


def get_run_audit_report(
    run_id: str,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
) -> str:
    """Devuelve la auditoria humana de ejecucion de una run."""

    snapshot = get_run(run_id, runs_dir)
    audit_path = _snapshot_optional_path(
        snapshot.audit_report_path,
        snapshot.snapshot_dir,
        "execution_audit.md",
    )
    if audit_path.exists():
        return audit_path.read_text(encoding="utf-8")
    return render_run_audit_report(get_run_evidence_pack(run_id, runs_dir))


def get_run_report_debate(
    run_id: str,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
) -> str:
    """Devuelve el debate humano del informe de una run."""

    artifacts = get_run_artifacts(run_id, runs_dir)
    report_path = _artifact_path_by_name(artifacts, "report_debate_report")
    if report_path is not None and report_path.exists():
        return report_path.read_text(encoding="utf-8")
    debate_path = _artifact_path_by_name(artifacts, "report_debate")
    if debate_path is not None and debate_path.exists():
        payload = json.loads(debate_path.read_text(encoding="utf-8"))
        return _render_report_debate_fallback(payload)
    raise FileNotFoundError(f"report debate not found for run: {run_id}")


def compare_runs(
    run_ids: list[str],
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
) -> RunComparison:
    """Compara metricas principales entre dos o mas ejecuciones."""

    if len(run_ids) < 2:
        raise ValueError("compare_runs requires at least two run_ids")

    entries = _entries_by_id(runs_dir)
    missing = [run_id for run_id in run_ids if run_id not in entries]
    if missing:
        raise FileNotFoundError(f"run ids not found in index: {', '.join(missing)}")

    snapshots = [load_run_snapshot(run_id, runs_dir) for run_id in run_ids]
    rows = [
        _comparison_row(entries[snapshot.run_id], snapshot)
        for snapshot in snapshots
    ]
    degradation_metrics = _degradation_metric_comparisons(rows)
    return RunComparison(
        generated_at=datetime.now(UTC),
        run_ids=run_ids,
        rows=rows,
        metrics=[
            _metric_comparison(rows, "precision", higher_is_better=True),
            _metric_comparison(rows, "recall", higher_is_better=True),
            _metric_comparison(rows, "f1_score", higher_is_better=True),
            _metric_comparison(
                rows,
                "false_positive_rate",
                higher_is_better=False,
            ),
        ],
        degradation_metrics=degradation_metrics,
    )


def _entries_by_id(runs_dir: Path | str) -> dict[str, RunIndexEntry]:
    return {entry.run_id: entry for entry in load_run_index(runs_dir).runs}


def _snapshot_optional_path(
    path_value: str | None,
    snapshot_dir: str,
    fallback_name: str,
) -> Path:
    if path_value:
        return Path(path_value)
    return Path(snapshot_dir) / fallback_name


def _artifact_path_by_name(
    artifacts: list[dict[str, Any]],
    name: str,
) -> Path | None:
    for artifact in artifacts:
        if artifact.get("name") == name and isinstance(artifact.get("path"), str):
            return Path(artifact["path"])
    return None


def _render_report_debate_fallback(payload: dict[str, Any]) -> str:
    lines = [
        f"# Debate controlado del informe {payload.get('run_id', 'n/a')}",
        "",
        "## Resultado",
        "",
        f"- Estado: `{payload.get('status', 'n/a')}`",
        f"- Rondas usadas: `{payload.get('rounds_used', 'n/a')}/{payload.get('max_rounds', 'n/a')}`",
        f"- Resumen: {payload.get('final_summary', 'n/a')}",
        "",
        "## Conversacion resumida",
        "",
    ]
    turns = payload.get("turns") or []
    if isinstance(turns, list):
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            lines.extend(
                [
                    f"### {turn.get('round_index', '-')} | {turn.get('speaker_agent', 'agente')}",
                    "",
                    f"- Resumen humano: {turn.get('human_summary', 'sin resumen')}",
                    "",
                ]
            )
    return "\n".join(lines).rstrip() + "\n"


def _comparison_row(entry: RunIndexEntry, snapshot: RunSnapshot) -> RunComparisonRow:
    state_payload = _safe_read_json(Path(snapshot.state_path))
    state = state_payload if isinstance(state_payload, dict) else {}
    metrics_payload = _safe_read_json(Path(snapshot.metrics_path))
    metrics = metrics_payload if isinstance(metrics_payload, dict) else {}
    extra = metrics.get("extra") if isinstance(metrics.get("extra"), dict) else {}
    evaluation_metrics = _safe_evaluation_metrics(metrics)
    degradation = (
        evaluation_metrics.get("degradation_metrics")
        if isinstance(evaluation_metrics.get("degradation_metrics"), dict)
        else {}
    )
    project_context = (
        state.get("project_context")
        if isinstance(state.get("project_context"), dict)
        else {}
    )
    modeling_config = (
        state.get("modeling_config")
        if isinstance(state.get("modeling_config"), dict)
        else {}
    )
    return RunComparisonRow(
        run_id=entry.run_id,
        dataset=entry.dataset,
        current_stage=entry.current_stage,
        approved=entry.approved,
        supervision_profile=_optional_text(project_context.get("supervision_profile")),
        label_source=_optional_text(project_context.get("label_source")),
        label_granularity=_optional_text(project_context.get("label_granularity")),
        model_name=_optional_text(modeling_config.get("model_name")),
        metric_families=_metric_families(extra, evaluation_metrics),
        precision=entry.precision,
        recall=entry.recall,
        f1_score=entry.f1_score,
        false_positive_rate=entry.false_positive_rate,
        degradation_available=_optional_bool(
            extra.get("degradation_available", degradation.get("available"))
        ),
        degradation_n_runs=_optional_int(
            extra.get("degradation_n_runs", degradation.get("n_runs"))
        ),
        degradation_detected_before_failure_rate=_optional_float(
            extra.get(
                "degradation_detected_before_failure_rate",
                degradation.get("detected_before_failure_rate"),
            )
        ),
        degradation_mean_lead_time_to_failure=_optional_float(
            extra.get(
                "degradation_mean_lead_time_to_failure",
                degradation.get("mean_lead_time_to_failure"),
            )
        ),
        degradation_mean_false_alarm_rate_nominal=_optional_float(
            extra.get(
                "degradation_mean_false_alarm_rate_nominal",
                degradation.get("mean_false_alarm_rate_nominal"),
            )
        ),
        degradation_mean_score_trend_spearman=_optional_float(
            extra.get(
                "degradation_mean_score_trend_spearman",
                degradation.get("mean_score_trend_spearman"),
            )
        ),
        degradation_missed_runs=_optional_int(
            extra.get("degradation_missed_runs", degradation.get("missed_runs"))
        ),
        degradation_mean_initial_final_separation=_optional_float(
            extra.get(
                "degradation_mean_initial_final_separation",
                degradation.get("mean_initial_final_separation"),
            )
        ),
        report_path=entry.report_path,
        snapshot_path=entry.snapshot_path,
    )


def _metric_comparison(
    rows: list[RunComparisonRow],
    metric: MetricName,
    *,
    higher_is_better: bool,
    metric_family: MetricFamily = "binary_classification",
) -> MetricComparison:
    values = [
        (row.run_id, getattr(row, metric))
        for row in rows
        if getattr(row, metric) is not None
    ]
    if not values:
        return MetricComparison(
            metric=metric,
            metric_family=metric_family,
            higher_is_better=higher_is_better,
        )

    key = lambda item: item[1]
    best_run_id, best_value = (
        max(values, key=key) if higher_is_better else min(values, key=key)
    )
    worst_run_id, worst_value = (
        min(values, key=key) if higher_is_better else max(values, key=key)
    )
    return MetricComparison(
        metric=metric,
        metric_family=metric_family,
        higher_is_better=higher_is_better,
        best_run_id=best_run_id,
        best_value=best_value,
        worst_run_id=worst_run_id,
        worst_value=worst_value,
        spread=abs(best_value - worst_value),
    )


def _degradation_metric_comparisons(
    rows: list[RunComparisonRow],
) -> list[MetricComparison]:
    if not any(row.degradation_available is True for row in rows):
        return []
    higher_is_better = {
        "degradation_detected_before_failure_rate": True,
        "degradation_mean_lead_time_to_failure": True,
        "degradation_mean_false_alarm_rate_nominal": False,
        "degradation_mean_score_trend_spearman": True,
        "degradation_missed_runs": False,
        "degradation_mean_initial_final_separation": True,
    }
    return [
        _metric_comparison(
            rows,
            metric,
            higher_is_better=higher_is_better[metric],
            metric_family="run_to_failure_degradation",
        )
        for metric in DEGRADATION_METRIC_NAMES
        if any(getattr(row, metric) is not None for row in rows)
    ]


def _safe_read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _safe_evaluation_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    metrics_path = metrics.get("metrics_path")
    if not isinstance(metrics_path, str) or not metrics_path:
        return {}
    payload = _safe_read_json(Path(metrics_path))
    return payload if isinstance(payload, dict) else {}


def _metric_families(
    extra: dict[str, Any],
    evaluation_metrics: dict[str, Any],
) -> list[str]:
    raw = extra.get("metric_families")
    if isinstance(raw, str):
        return [item.strip() for item in raw.split(",") if item.strip()]
    raw = evaluation_metrics.get("metric_families")
    if isinstance(raw, list):
        return [str(item) for item in raw if str(item)]
    return []


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) and value else None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None
