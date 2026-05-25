"""Persistencia local de ejecuciones del pipeline."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import Field, NonNegativeInt

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.state import TFMStateModel


DEFAULT_RUNS_DIR = Path("codigo/reports/runs")
INDEX_FILENAME = "index.json"


class RunIndexEntry(StrictBaseModel):
    """Entrada ligera de una ejecucion persistida."""

    run_id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    current_stage: str = Field(min_length=1)
    approved: bool | None = None
    report_path: str | None = None
    snapshot_path: str = Field(min_length=1)
    created_at: datetime
    precision: float | None = None
    recall: float | None = None
    f1_score: float | None = None
    false_positive_rate: float | None = None
    n_artifacts: NonNegativeInt = 0
    n_decisions: NonNegativeInt = 0
    n_errors: NonNegativeInt = 0


class RunIndex(StrictBaseModel):
    """Indice local de ejecuciones persistidas."""

    generated_at: datetime
    runs: list[RunIndexEntry] = Field(default_factory=list)


class RunSnapshot(StrictBaseModel):
    """Resumen de una ejecucion guardada en disco."""

    run_id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    current_stage: str = Field(min_length=1)
    approved: bool | None = None
    report_path: str | None = None
    snapshot_dir: str = Field(min_length=1)
    state_path: str = Field(min_length=1)
    decisions_path: str = Field(min_length=1)
    artifacts_path: str = Field(min_length=1)
    metrics_path: str = Field(min_length=1)
    evaluation_path: str = Field(min_length=1)
    summary_path: str = Field(min_length=1)
    metadata_path: str = Field(min_length=1)
    created_at: datetime
    n_artifacts: NonNegativeInt = 0
    n_decisions: NonNegativeInt = 0
    n_errors: NonNegativeInt = 0

    def to_index_entry(self) -> RunIndexEntry:
        """Devuelve la vista compacta que se guarda en `index.json`."""

        metrics = _safe_read_json(Path(self.metrics_path))
        metrics_data = metrics if isinstance(metrics, dict) else {}
        return RunIndexEntry(
            run_id=self.run_id,
            thread_id=self.thread_id,
            dataset=self.dataset,
            current_stage=self.current_stage,
            approved=self.approved,
            report_path=self.report_path,
            snapshot_path=self.snapshot_dir,
            created_at=self.created_at,
            precision=metrics_data.get("precision"),
            recall=metrics_data.get("recall"),
            f1_score=metrics_data.get("f1_score"),
            false_positive_rate=metrics_data.get("false_positive_rate"),
            n_artifacts=self.n_artifacts,
            n_decisions=self.n_decisions,
            n_errors=self.n_errors,
        )


def save_run_snapshot(
    state: TFMStateModel,
    output_dir: Path | str = DEFAULT_RUNS_DIR,
) -> RunSnapshot:
    """Guarda una ejecucion completa en una carpeta local por `run_id`."""

    runs_dir = Path(output_dir)
    run_dir = _run_dir_for_id(runs_dir, state.run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    created_at = datetime.now(UTC)
    decisions = extract_decisions(state)
    files = _snapshot_files(run_dir)

    _write_json(files["state"], state.model_dump(mode="json"))
    _write_json(files["decisions"], decisions)
    _write_json(
        files["artifacts"],
        [artifact.model_dump(mode="json") for artifact in state.artifacts],
    )
    _write_json(
        files["metrics"],
        None if state.metrics is None else state.metrics.model_dump(mode="json"),
    )
    _write_json(
        files["evaluation"],
        None if state.evaluation is None else state.evaluation.model_dump(mode="json"),
    )

    snapshot = RunSnapshot(
        run_id=state.run_id,
        thread_id=state.thread_id,
        dataset=state.project_context.dataset,
        current_stage=state.current_stage,
        approved=None if state.evaluation is None else state.evaluation.approved,
        report_path=state.report_path,
        snapshot_dir=str(run_dir),
        state_path=str(files["state"]),
        decisions_path=str(files["decisions"]),
        artifacts_path=str(files["artifacts"]),
        metrics_path=str(files["metrics"]),
        evaluation_path=str(files["evaluation"]),
        summary_path=str(files["summary"]),
        metadata_path=str(files["metadata"]),
        created_at=created_at,
        n_artifacts=len(state.artifacts),
        n_decisions=len(decisions),
        n_errors=len(state.errors),
    )
    _write_summary(files["summary"], state, snapshot, decisions)
    _write_json(files["metadata"], snapshot.model_dump(mode="json"))
    update_run_index(snapshot, runs_dir)
    return snapshot


def load_run_snapshot(
    run_id: str,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
) -> RunSnapshot:
    """Carga el resumen de una ejecucion persistida."""

    run_dir = _run_dir_for_id(Path(runs_dir), run_id)
    metadata_path = run_dir / "snapshot.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"run snapshot metadata not found: {metadata_path}")
    return RunSnapshot.model_validate(_read_json(metadata_path))


def update_run_index(
    snapshot: RunSnapshot,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
) -> None:
    """Crea o actualiza `index.json` sustituyendo la entrada del mismo run."""

    root = Path(runs_dir)
    root.mkdir(parents=True, exist_ok=True)
    index_path = root / INDEX_FILENAME
    current = _load_index(index_path)
    entry = snapshot.to_index_entry()
    entries = [
        existing
        for existing in current.runs
        if existing.run_id != snapshot.run_id
    ]
    entries.append(entry)
    entries.sort(key=lambda item: item.created_at, reverse=True)
    updated = RunIndex(generated_at=datetime.now(UTC), runs=entries)
    _write_json(index_path, updated.model_dump(mode="json"))


def load_run_index(runs_dir: Path | str = DEFAULT_RUNS_DIR) -> RunIndex:
    """Carga el indice local de ejecuciones."""

    return _load_index(Path(runs_dir) / INDEX_FILENAME)


def extract_decisions(state: TFMStateModel) -> list[dict[str, Any]]:
    """Extrae decisiones JSON desde los mensajes del grafo."""

    decisions: list[dict[str, Any]] = []
    for index, message in enumerate(state.messages):
        if message.role not in {"agent", "supervisor"}:
            continue
        payload = _parse_message_payload(message.content)
        decisions.append(
            {
                "message_index": index,
                "role": message.role,
                "name": message.name,
                "created_at": message.created_at.isoformat(),
                "agent_name": payload.get("agent_name"),
                "decision_id": payload.get("decision_id"),
                "payload": payload,
            }
        )
    return decisions


def _snapshot_files(run_dir: Path) -> dict[str, Path]:
    return {
        "state": run_dir / "state_final.json",
        "decisions": run_dir / "decisions.json",
        "artifacts": run_dir / "artifacts.json",
        "metrics": run_dir / "metrics.json",
        "evaluation": run_dir / "evaluation.json",
        "summary": run_dir / "summary.md",
        "metadata": run_dir / "snapshot.json",
    }


def _run_dir_for_id(runs_dir: Path, run_id: str) -> Path:
    if not run_id.strip():
        raise ValueError("run_id cannot be empty")
    path = Path(run_id)
    if path.name != run_id or path.is_absolute():
        raise ValueError("run_id must be a plain directory name")
    return runs_dir / run_id


def _parse_message_payload(content: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return {"raw_content": content}
    if isinstance(payload, dict):
        return payload
    return {"raw_content": content}


def _load_index(index_path: Path) -> RunIndex:
    if not index_path.exists():
        return RunIndex(generated_at=datetime.now(UTC), runs=[])
    return RunIndex.model_validate(_read_json(index_path))


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_read_json(path: Path) -> Any:
    try:
        return _read_json(path)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_summary(
    path: Path,
    state: TFMStateModel,
    snapshot: RunSnapshot,
    decisions: list[dict[str, Any]],
) -> None:
    counts = Counter(
        str(decision.get("agent_name") or decision.get("name") or "unknown")
        for decision in decisions
    )
    lines = [
        f"# Run {state.run_id}",
        "",
        f"- Thread ID: `{state.thread_id}`",
        f"- Dataset: `{state.project_context.dataset}`",
        f"- Estado final: `{state.current_stage}`",
        f"- Aprobada: `{snapshot.approved}`",
        f"- Informe: `{state.report_path}`",
        f"- Artefactos: `{snapshot.n_artifacts}`",
        f"- Decisiones: `{snapshot.n_decisions}`",
        f"- Errores: `{snapshot.n_errors}`",
        "",
        "## Metricas",
        "",
        *(_metrics_lines(state)),
        "",
        "## Decisiones",
        "",
        *[f"- `{name}`: `{count}`" for name, count in sorted(counts.items())],
        "",
        "## Artefactos",
        "",
        *[
            f"- `{artifact.artifact_type}` | `{artifact.name}` | `{artifact.path}`"
            for artifact in state.artifacts
        ],
        "",
        "## Ficheros persistidos",
        "",
        f"- Estado final: `{snapshot.state_path}`",
        f"- Decisiones: `{snapshot.decisions_path}`",
        f"- Artefactos: `{snapshot.artifacts_path}`",
        f"- Metricas: `{snapshot.metrics_path}`",
        f"- Evaluacion: `{snapshot.evaluation_path}`",
    ]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _metrics_lines(state: TFMStateModel) -> list[str]:
    if state.metrics is None:
        return ["No hay metricas persistidas."]
    return [
        f"- Precision: `{_format_metric(state.metrics.precision)}`",
        f"- Recall: `{_format_metric(state.metrics.recall)}`",
        f"- F1-score: `{_format_metric(state.metrics.f1_score)}`",
        f"- ROC-AUC: `{_format_metric(state.metrics.roc_auc)}`",
        f"- PR-AUC: `{_format_metric(state.metrics.pr_auc)}`",
        f"- FPR: `{_format_metric(state.metrics.false_positive_rate)}`",
    ]


def _format_metric(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"
