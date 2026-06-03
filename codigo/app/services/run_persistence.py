"""Persistencia local de ejecuciones del pipeline."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

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
    evidence_pack_path: str | None = None
    evidence_pack_markdown_path: str | None = None
    audit_report_path: str | None = None
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


class EvidenceArtifact(StrictBaseModel):
    """Artefacto incluido en el paquete de evidencia de una run."""

    name: str = Field(min_length=1)
    artifact_type: str = Field(min_length=1)
    path: str = Field(min_length=1)
    producer: str = Field(min_length=1)
    exists: bool
    is_file: bool
    size_bytes: int | None = None
    sha256: str | None = None
    checksum_status: Literal[
        "computed",
        "missing",
        "directory",
        "unreadable",
    ]
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvidenceDecision(StrictBaseModel):
    """Decision agentica normalizada para auditoria humana."""

    role: str = Field(min_length=1)
    message_index: int = Field(ge=0)
    created_at: datetime
    name: str | None = None
    agent_name: str | None = None
    decision_id: str | None = None
    rationale: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    output_path: str | None = None
    source_paths: list[str] = Field(default_factory=list)
    verification_status: str | None = None
    required_corrections: list[str] = Field(default_factory=list)
    issue_counts: dict[str, int] = Field(default_factory=dict)


class RunEvidencePack(StrictBaseModel):
    """Paquete de evidencia auditable asociado a un snapshot persistido."""

    schema_version: Literal["tfm.run_evidence_pack.v1"] = "tfm.run_evidence_pack.v1"
    run_id: str = Field(min_length=1)
    thread_id: str = Field(min_length=1)
    dataset: str = Field(min_length=1)
    current_stage: str = Field(min_length=1)
    approved: bool | None = None
    raw_path: str = Field(min_length=1)
    report_path: str | None = None
    project_context: dict[str, Any]
    configs: dict[str, Any]
    metrics: dict[str, Any] | None = None
    evaluation: dict[str, Any] | None = None
    human_approval: dict[str, Any] | None = None
    decisions: list[EvidenceDecision] = Field(default_factory=list)
    artifacts: list[EvidenceArtifact] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    pipeline_request: dict[str, Any] | None = None
    pipeline_plan: dict[str, Any] | None = None
    report_debate: dict[str, Any] | None = None
    created_at: datetime


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
    evidence_pack = build_run_evidence_pack(state, decisions, created_at=created_at)
    _write_json(files["evidence_pack"], evidence_pack.model_dump(mode="json"))
    _write_evidence_pack_markdown(files["evidence_pack_markdown"], evidence_pack)
    files["audit_report"].write_text(
        render_run_audit_report(evidence_pack),
        encoding="utf-8",
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
        evidence_pack_path=str(files["evidence_pack"]),
        evidence_pack_markdown_path=str(files["evidence_pack_markdown"]),
        audit_report_path=str(files["audit_report"]),
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


def build_run_evidence_pack(
    state: TFMStateModel,
    decisions: list[dict[str, Any]] | None = None,
    *,
    created_at: datetime | None = None,
) -> RunEvidencePack:
    """Construye el paquete de evidencia sin crear un nuevo sistema paralelo."""

    normalized_decisions = _evidence_decisions(
        decisions if decisions is not None else extract_decisions(state)
    )
    artifacts = [_evidence_artifact(artifact) for artifact in state.artifacts]
    return RunEvidencePack(
        run_id=state.run_id,
        thread_id=state.thread_id,
        dataset=state.project_context.dataset,
        current_stage=state.current_stage,
        approved=None if state.evaluation is None else state.evaluation.approved,
        raw_path=state.raw_path,
        report_path=state.report_path,
        project_context=state.project_context.model_dump(mode="json"),
        configs={
            "cleaning": _model_dump_or_none(state.cleaning_config),
            "structuring": _model_dump_or_none(state.structuring_config),
            "modeling": _model_dump_or_none(state.modeling_config),
        },
        metrics=_model_dump_or_none(state.metrics),
        evaluation=_model_dump_or_none(state.evaluation),
        human_approval=_model_dump_or_none(state.human_approval),
        decisions=normalized_decisions,
        artifacts=artifacts,
        errors=[error.model_dump(mode="json") for error in state.errors],
        pipeline_request=_read_named_artifact_json(state, "pipeline_request"),
        pipeline_plan=_read_named_artifact_json(state, "pipeline_plan"),
        report_debate=_read_named_artifact_json(state, "report_debate"),
        created_at=created_at or datetime.now(UTC),
    )


def render_run_audit_report(evidence: RunEvidencePack) -> str:
    """Renderiza una auditoria humana de ejecucion a partir del evidence pack."""

    lines = [
        f"# Auditoria de ejecucion {evidence.run_id}",
        "",
        "## Lectura rapida",
        "",
        *_audit_quick_read_lines(evidence),
        "",
        "## Solicitud y plan aplicado",
        "",
        *_audit_request_plan_lines(evidence),
        "",
        "## Cronologia de agentes",
        "",
        *_audit_decision_lines(evidence),
        "",
        "## Verificacion del informe",
        "",
        *_audit_report_verification_lines(evidence),
        "",
        "## Debate del informe",
        "",
        *_audit_report_debate_lines(evidence),
        "",
        "## Resultado tecnico",
        "",
        *_audit_result_lines(evidence),
        "",
        "## Artefactos y evidencias",
        "",
        *_audit_artifact_lines(evidence),
        "",
        "## Incidencias y bloqueos",
        "",
        *_audit_error_lines(evidence),
        "",
        "## Lectura para evaluador humano",
        "",
        *_audit_human_review_lines(evidence),
    ]
    return "\n".join(lines).rstrip() + "\n"


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
        "evidence_pack": run_dir / "evidence_pack.json",
        "evidence_pack_markdown": run_dir / "evidence_pack.md",
        "audit_report": run_dir / "execution_audit.md",
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


def _evidence_decisions(decisions: list[dict[str, Any]]) -> list[EvidenceDecision]:
    return [_evidence_decision(decision) for decision in decisions]


def _evidence_decision(decision: dict[str, Any]) -> EvidenceDecision:
    payload = decision.get("payload")
    payload_data = payload if isinstance(payload, dict) else {}
    return EvidenceDecision(
        role=str(decision.get("role") or "unknown"),
        message_index=int(decision.get("message_index") or 0),
        created_at=_parse_datetime(decision.get("created_at")),
        name=_optional_string(decision.get("name")),
        agent_name=_optional_string(
            decision.get("agent_name") or payload_data.get("agent_name")
        ),
        decision_id=_optional_string(
            decision.get("decision_id") or payload_data.get("decision_id")
        ),
        rationale=_optional_string(payload_data.get("rationale")),
        confidence=_optional_float(payload_data.get("confidence")),
        output_path=_optional_string(
            payload_data.get("output_path") or payload_data.get("report_path")
        ),
        source_paths=_decision_source_paths(payload_data),
        verification_status=_optional_string(payload_data.get("verification_status")),
        required_corrections=_string_list(payload_data.get("required_corrections")),
        issue_counts=_verification_issue_counts(payload_data),
    )


def _decision_source_paths(payload: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for key in ["source_paths", "evidence_used", "evidence_refs"]:
        values = payload.get(key)
        if isinstance(values, list):
            paths.extend(str(item) for item in values if isinstance(item, str))
    for key in ["unsupported_claims", "misleading_claims", "missing_limitations"]:
        issues = payload.get(key)
        if not isinstance(issues, list):
            continue
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            refs = issue.get("evidence_refs")
            if isinstance(refs, list):
                paths.extend(str(item) for item in refs if isinstance(item, str))
    sections = payload.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            values = section.get("source_paths")
            if isinstance(values, list):
                paths.extend(str(item) for item in values if isinstance(item, str))
            refs = section.get("evidence_refs")
            if isinstance(refs, list):
                paths.extend(str(item) for item in refs if isinstance(item, str))
    return sorted(set(paths))


def _evidence_artifact(artifact) -> EvidenceArtifact:
    path = Path(artifact.path)
    exists = path.exists()
    is_file = path.is_file()
    size_bytes: int | None = None
    sha256: str | None = None
    status: Literal["computed", "missing", "directory", "unreadable"]
    if not exists:
        status = "missing"
    elif not is_file:
        status = "directory"
    else:
        try:
            size_bytes = path.stat().st_size
            sha256 = _sha256(path)
            status = "computed"
        except OSError:
            status = "unreadable"
    return EvidenceArtifact(
        name=artifact.name,
        artifact_type=artifact.artifact_type,
        path=artifact.path,
        producer=str(artifact.producer),
        exists=exists,
        is_file=is_file,
        size_bytes=size_bytes,
        sha256=sha256,
        checksum_status=status,
        description=artifact.description,
        metadata=dict(artifact.metadata),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_named_artifact_json(
    state: TFMStateModel,
    artifact_name: str,
) -> dict[str, Any] | None:
    for artifact in state.artifacts:
        if artifact.name != artifact_name:
            continue
        payload = _safe_read_json(Path(artifact.path))
        return payload if isinstance(payload, dict) else None
    return None


def _model_dump_or_none(value) -> dict[str, Any] | None:
    if value is None:
        return None
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return None


def _optional_string(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, (float, int)):
        return float(value)
    return None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item.strip()]


def _verification_issue_counts(payload: dict[str, Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key in ["unsupported_claims", "misleading_claims", "missing_limitations"]:
        value = payload.get(key)
        if isinstance(value, list):
            counts[key] = len(value)
    return counts


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return datetime.now(UTC)
    return datetime.now(UTC)


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
        f"- Evidence pack: `{snapshot.evidence_pack_path}`",
        f"- Auditoria de ejecucion: `{snapshot.audit_report_path}`",
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
        f"- Evidence pack JSON: `{snapshot.evidence_pack_path}`",
        f"- Evidence pack Markdown: `{snapshot.evidence_pack_markdown_path}`",
        f"- Auditoria de ejecucion: `{snapshot.audit_report_path}`",
    ]
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _write_evidence_pack_markdown(path: Path, evidence: RunEvidencePack) -> None:
    lines = [
        f"# Evidence pack {evidence.run_id}",
        "",
        "## Identificacion",
        "",
        f"- Run ID: `{evidence.run_id}`",
        f"- Thread ID: `{evidence.thread_id}`",
        f"- Dataset: `{evidence.dataset}`",
        f"- Estado final: `{evidence.current_stage}`",
        f"- Aprobada: `{evidence.approved}`",
        f"- Informe final: `{evidence.report_path}`",
        f"- Generado: `{evidence.created_at.isoformat()}`",
        "",
        "## Decisionabilidad",
        "",
        f"- Decisiones agenticas registradas: `{len(evidence.decisions)}`",
        f"- Artefactos trazados: `{len(evidence.artifacts)}`",
        f"- Errores capturados: `{len(evidence.errors)}`",
        "",
        "## Metricas clave",
        "",
        *_evidence_metric_lines(evidence),
        "",
        "## Decisiones agenticas",
        "",
        *_evidence_decision_lines(evidence),
        "",
        "## Artefactos y checksums",
        "",
        *_evidence_artifact_lines(evidence),
    ]
    if evidence.pipeline_request is not None:
        lines.extend(["", "## Solicitud de ejecucion", "", "- Incluida en JSON."])
    if evidence.pipeline_plan is not None:
        lines.extend(["", "## Plan de ejecucion", "", "- Incluido en JSON."])
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def _evidence_metric_lines(evidence: RunEvidencePack) -> list[str]:
    metrics = evidence.metrics or {}
    if not metrics:
        return ["No hay metricas agregadas en esta ejecucion."]
    keys = [
        "precision",
        "recall",
        "f1_score",
        "roc_auc",
        "pr_auc",
        "false_positive_rate",
    ]
    return [f"- {key}: `{metrics.get(key)}`" for key in keys if key in metrics]


def _evidence_decision_lines(evidence: RunEvidencePack) -> list[str]:
    if not evidence.decisions:
        return ["No hay decisiones agenticas persistidas."]
    return [
        (
            f"- `{item.message_index}` | `{item.agent_name or item.name or item.role}` "
            f"| `{item.decision_id}` | confianza `{item.confidence}`"
        )
        for item in evidence.decisions
    ]


def _evidence_artifact_lines(evidence: RunEvidencePack) -> list[str]:
    if not evidence.artifacts:
        return ["No hay artefactos registrados."]
    return [
        (
            f"- `{artifact.artifact_type}` | `{artifact.name}` | "
            f"`{artifact.path}` | `{artifact.checksum_status}` | "
            f"`{artifact.sha256 or 'n/a'}`"
        )
        for artifact in evidence.artifacts
    ]


def _audit_quick_read_lines(evidence: RunEvidencePack) -> list[str]:
    status = _audit_status_text(evidence)
    return [
        (
            f"La ejecucion `{evidence.run_id}` sobre `{evidence.dataset}` termino "
            f"en estado `{evidence.current_stage}` y queda {status}."
        ),
        (
            f"Durante la run se registraron `{len(evidence.decisions)}` decisiones "
            f"agenticas, `{len(evidence.artifacts)}` artefactos y "
            f"`{len(evidence.errors)}` incidencias."
        ),
        (
            "Este documento resume lo ocurrido de forma operativa. El informe "
            "final del agente redactor se mantiene como documento separado de "
            "conclusiones; esta auditoria explica el proceso que lo soporta."
        ),
    ]


def _audit_request_plan_lines(evidence: RunEvidencePack) -> list[str]:
    request = evidence.pipeline_request or {}
    plan = evidence.pipeline_plan or {}
    if not request and not plan:
        return [
            (
                "No se conserva una solicitud o plan preflight estructurado para "
                "esta run. Puede tratarse de una ejecucion anterior al registro "
                "de evidence pack o de una ejecucion creada por un wrapper local."
            )
        ]

    lines: list[str] = []
    if request:
        lines.extend(
            [
                f"- Dataset solicitado: `{request.get('dataset_id', evidence.dataset)}`.",
                f"- Modo de ejecucion: `{request.get('execution_mode', 'n/a')}`.",
                f"- LLM activado: `{request.get('use_llm', False)}`.",
                f"- Memoria activada: `{request.get('use_memory', False)}`.",
                f"- Politica de dataset: `{request.get('dataset_policy_id') or 'no declarada'}`.",
                f"- Etiquetas sinteticas/controladas: `{request.get('allow_synthetic_labels', False)}`.",
            ]
        )
    if plan:
        lines.extend(
            [
                f"- Fases efectivas: `{', '.join(plan.get('effective_stages', [])) or 'n/a'}`.",
                (
                    "- Preflight ejecutable: "
                    f"`{plan.get('can_execute_requested_stages', 'n/a')}`."
                ),
            ]
        )
        blocking_reasons = plan.get("blocking_reasons") or []
        if blocking_reasons:
            lines.append("Bloqueos metodologicos detectados:")
            lines.extend([f"- {reason}" for reason in blocking_reasons])
        else:
            lines.append(
                "No se registraron bloqueos metodologicos en el plan aplicado."
            )
    return lines


def _audit_decision_lines(evidence: RunEvidencePack) -> list[str]:
    if not evidence.decisions:
        return ["No hay decisiones agenticas persistidas para esta ejecucion."]
    lines = [
        (
            "La cronologia muestra que agentes participaron y que rastro dejaron. "
            "La confianza es la declarada por el contrato del agente cuando existe."
        )
    ]
    for decision in evidence.decisions:
        actor = decision.agent_name or decision.name or decision.role
        confidence = (
            "n/a"
            if decision.confidence is None
            else f"{round(decision.confidence * 100)}%"
        )
        decision_id = decision.decision_id or "sin decision_id"
        rationale = decision.rationale or "sin rationale textual persistido"
        lines.append(
            f"- Paso `{decision.message_index}`: `{actor}` registra `{decision_id}` "
            f"con confianza `{confidence}`. {rationale}"
        )
    return lines


def _audit_report_verification_lines(evidence: RunEvidencePack) -> list[str]:
    verifications = [
        decision
        for decision in evidence.decisions
        if decision.agent_name == "report_verifier"
    ]
    if not verifications:
        return [
            "No hay verificacion agentica del informe final en esta ejecucion."
        ]
    latest = verifications[-1]
    lines = [
        f"- Estado de verificacion: `{latest.verification_status or 'n/a'}`.",
        f"- Decision: `{latest.decision_id or 'sin decision_id'}`.",
    ]
    if latest.issue_counts:
        lines.append("Incidencias agrupadas:")
        for key, count in sorted(latest.issue_counts.items()):
            lines.append(f"- `{key}`: `{count}`.")
    else:
        lines.append("No se registraron incidencias estructuradas.")
    if latest.required_corrections:
        lines.append("Correcciones requeridas:")
        lines.extend([f"- {item}" for item in latest.required_corrections])
    else:
        lines.append("No hay correcciones obligatorias registradas.")
    if latest.source_paths:
        lines.append("Referencias de evidencia citadas por el verificador:")
        lines.extend([f"- `{item}`" for item in latest.source_paths[:12]])
    return lines


def _audit_report_debate_lines(evidence: RunEvidencePack) -> list[str]:
    debate = evidence.report_debate or {}
    if not debate:
        return ["No hay debate controlado del informe en esta ejecucion."]
    lines = [
        f"- Estado del debate: `{debate.get('status', 'n/a')}`.",
        f"- Rondas usadas: `{debate.get('rounds_used', 'n/a')}/{debate.get('max_rounds', 'n/a')}`.",
        (
            "- Revision humana recomendada: "
            f"`{debate.get('human_review_recommended', 'n/a')}`."
        ),
        f"- Resumen: {debate.get('final_summary', 'n/a')}",
    ]
    turns = debate.get("turns") or []
    if isinstance(turns, list) and turns:
        lines.append("Conversacion resumida:")
        for turn in turns[:8]:
            if not isinstance(turn, dict):
                continue
            speaker = turn.get("speaker_agent", "agente")
            intent = turn.get("intent", "turno")
            summary = turn.get("human_summary", "sin resumen")
            lines.append(f"- `{speaker}` / `{intent}`: {summary}")
    unresolved = debate.get("unresolved_issues") or []
    if isinstance(unresolved, list) and unresolved:
        lines.append("Incidencias no resueltas:")
        lines.extend([f"- {item}" for item in unresolved if isinstance(item, str)])
    return lines


def _audit_result_lines(evidence: RunEvidencePack) -> list[str]:
    lines: list[str] = []
    evaluation = evidence.evaluation or {}
    if evaluation:
        lines.extend(
            [
                f"- Juicio del evaluador: {evaluation.get('summary', 'n/a')}",
                f"- Aprobacion: `{evaluation.get('approved')}`.",
                f"- Siguiente accion: `{evaluation.get('next_action', 'n/a')}`.",
            ]
        )
        limitations = evaluation.get("limitations") or []
        if limitations:
            lines.append("Limitaciones declaradas:")
            lines.extend([f"- {item}" for item in limitations])
    else:
        lines.append("No hay evaluacion estructurada en esta ejecucion.")

    metrics = evidence.metrics or {}
    if metrics:
        lines.extend(
            [
                f"- Precision: `{_fmt_evidence_metric(metrics.get('precision'))}`.",
                f"- Recall: `{_fmt_evidence_metric(metrics.get('recall'))}`.",
                f"- F1-score: `{_fmt_evidence_metric(metrics.get('f1_score'))}`.",
                f"- ROC-AUC: `{_fmt_evidence_metric(metrics.get('roc_auc'))}`.",
                f"- PR-AUC: `{_fmt_evidence_metric(metrics.get('pr_auc'))}`.",
                (
                    "- Tasa de falsos positivos: "
                    f"`{_fmt_evidence_metric(metrics.get('false_positive_rate'))}`."
                ),
            ]
        )
    else:
        lines.append("No hay metricas agregadas persistidas.")
    return lines


def _audit_artifact_lines(evidence: RunEvidencePack) -> list[str]:
    if not evidence.artifacts:
        return ["No hay artefactos registrados en el evidence pack."]

    counts = Counter(artifact.artifact_type for artifact in evidence.artifacts)
    lines = [
        "Resumen por tipo de artefacto:",
        *[f"- `{artifact_type}`: `{count}`." for artifact_type, count in sorted(counts.items())],
        "",
        "Artefactos clave:",
    ]
    for artifact in evidence.artifacts:
        digest = _short_hash(artifact.sha256)
        lines.append(
            f"- `{artifact.name}` producido por `{artifact.producer}` "
            f"como `{artifact.artifact_type}`. Estado: `{artifact.checksum_status}`; "
            f"hash: `{digest}`."
        )
    return lines


def _audit_error_lines(evidence: RunEvidencePack) -> list[str]:
    if not evidence.errors:
        return [
            "No se registraron errores tecnicos en el estado final de la run.",
            (
                "Si hubo bloqueos metodologicos, deben leerse como decisiones de "
                "control del pipeline y no como fallos de infraestructura."
            ),
        ]
    lines = ["La run conserva las siguientes incidencias:"]
    for error in evidence.errors:
        stage = error.get("stage", "n/a")
        node = error.get("node") or "nodo no declarado"
        recoverable = error.get("recoverable")
        message = error.get("message", "sin mensaje")
        lines.append(
            f"- `{stage}` / `{node}`: {message} Recuperable: `{recoverable}`."
        )
    return lines


def _audit_human_review_lines(evidence: RunEvidencePack) -> list[str]:
    lines = [
        (
            "La ejecucion mantiene separadas las decisiones de agentes y las "
            "transformaciones deterministas. Los agentes no ejecutan codigo "
            "arbitrario sobre los datos; proponen decisiones dentro de contratos."
        ),
        (
            "Para revisar esta run, conviene contrastar este informe de auditoria "
            "con el informe final del agente redactor, las metricas y los "
            "artefactos listados en el evidence pack."
        ),
    ]
    if evidence.human_approval:
        approval = evidence.human_approval
        lines.append(
            f"Revision humana registrada: required=`{approval.get('required')}`, "
            f"approved=`{approval.get('approved')}`, reviewer=`{approval.get('reviewer') or 'n/a'}`."
        )
        if approval.get("reason"):
            lines.append(f"Motivo de revision: {approval['reason']}")
    else:
        lines.append("No se registro una decision explicita de revision humana.")
    return lines


def _audit_status_text(evidence: RunEvidencePack) -> str:
    if evidence.approved is True:
        return "aprobada por el evaluador"
    if evidence.approved is False:
        return "no aprobada por el evaluador"
    return "sin aprobacion final declarada"


def _fmt_evidence_metric(value: Any) -> str:
    if isinstance(value, (float, int)):
        return f"{float(value):.4f}"
    return "n/a"


def _short_hash(value: str | None) -> str:
    if not value:
        return "n/a"
    return value[:12]


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
