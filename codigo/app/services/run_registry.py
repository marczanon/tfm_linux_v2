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
    RunIndexEntry,
    RunSnapshot,
    load_run_index,
    load_run_snapshot,
)


MetricName = Literal["precision", "recall", "f1_score", "false_positive_rate"]


class RunComparisonRow(StrictBaseModel):
    """Fila compacta para comparar una ejecucion."""

    run_id: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    current_stage: str = Field(min_length=1)
    approved: bool | None = None
    precision: float | None = None
    recall: float | None = None
    f1_score: float | None = None
    false_positive_rate: float | None = None
    report_path: str | None = None
    snapshot_path: str = Field(min_length=1)


class MetricComparison(StrictBaseModel):
    """Resumen de mejor y peor ejecucion para una metrica."""

    metric: MetricName
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

    rows = [_comparison_row(entries[run_id]) for run_id in run_ids]
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
    )


def _entries_by_id(runs_dir: Path | str) -> dict[str, RunIndexEntry]:
    return {entry.run_id: entry for entry in load_run_index(runs_dir).runs}


def _comparison_row(entry: RunIndexEntry) -> RunComparisonRow:
    return RunComparisonRow(
        run_id=entry.run_id,
        dataset=entry.dataset,
        current_stage=entry.current_stage,
        approved=entry.approved,
        precision=entry.precision,
        recall=entry.recall,
        f1_score=entry.f1_score,
        false_positive_rate=entry.false_positive_rate,
        report_path=entry.report_path,
        snapshot_path=entry.snapshot_path,
    )


def _metric_comparison(
    rows: list[RunComparisonRow],
    metric: MetricName,
    *,
    higher_is_better: bool,
) -> MetricComparison:
    values = [
        (row.run_id, getattr(row, metric))
        for row in rows
        if getattr(row, metric) is not None
    ]
    if not values:
        return MetricComparison(metric=metric, higher_is_better=higher_is_better)

    key = lambda item: item[1]
    best_run_id, best_value = (
        max(values, key=key) if higher_is_better else min(values, key=key)
    )
    worst_run_id, worst_value = (
        min(values, key=key) if higher_is_better else max(values, key=key)
    )
    return MetricComparison(
        metric=metric,
        higher_is_better=higher_is_better,
        best_run_id=best_run_id,
        best_value=best_value,
        worst_run_id=worst_run_id,
        worst_value=worst_value,
        spread=abs(best_value - worst_value),
    )
