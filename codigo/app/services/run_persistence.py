"""Persistencia local de ejecuciones del pipeline."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections import Counter
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import fcntl

from pydantic import Field, NonNegativeInt, ValidationError

from codigo.app.schemas.agent_runtime import AgentRuntimeEvent
from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.monitoring_replay import (
    CausalEvidenceCatalog,
    MonitoringPolicyProposal,
    MonitoringReviewDecision,
    MonitoringReviewRequest,
    MonitoringReviewResult,
)
from codigo.app.schemas.state import TFMStateModel
from codigo.app.services.monitoring_policy_proposal import (
    validate_monitoring_policy_proposal,
)


DEFAULT_RUNS_DIR = Path("codigo/reports/runs")
INDEX_FILENAME = "index.json"

# Expedientes creados antes del catalogo causal por registro. La lectura
# compatible se limita a estas huellas publicadas y nunca se usa al escribir.
_HISTORICAL_MONITORING_REVIEW_V1_FINGERPRINTS = frozenset(
    {
        (
            "monitoring_review_prompt_v1",
            "4c3a82722ffdda407d5b173277f3ef33e0ad1099f43c9fa91a00ee832ae788b4",
            "monitoring_review_decision_v1",
            "5be26add584c3ba383fbf6a834fa1a1854bd5c86058361a980b5048a9303241a",
            "monitoring_review_actions_v1",
            "d5819de71dcbfcf6502bbfd9287354e2b0ec3dea5f65d411bd5f812655e36586",
        ),
        (
            "monitoring_review_prompt_v1",
            "6935b3f9438e31e5fd06c2b7bdec11c933fa32ef7a2d1a732c129c5de1874ffa",
            "monitoring_review_decision_v1",
            "5be26add584c3ba383fbf6a834fa1a1854bd5c86058361a980b5048a9303241a",
            "monitoring_review_actions_v1",
            "d5819de71dcbfcf6502bbfd9287354e2b0ec3dea5f65d411bd5f812655e36586",
        ),
    }
)


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
    runtime_events_path: str | None = None
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
    generation_origin: str | None = None
    generation_attempt_index: int | None = Field(default=None, ge=1)
    generation_validation_status: str | None = None
    fallback_cause: str | None = None
    proposal_generation_origin: str | None = None
    proposal_validation_status: str | None = None
    proposal_fallback_cause: str | None = None
    hypothesis: str | None = None
    hypothesis_kind: str | None = None
    hypothesis_scope: str | None = None
    hypothesis_evidence_cutoff: str | None = None
    hypothesis_expected_observation: str | None = None
    hypothesis_falsification_criterion: str | None = None
    hypothesis_risk_notes: list[str] = Field(default_factory=list)
    hypothesis_assumptions: list[str] = Field(default_factory=list)
    hypothesis_evidence_refs: list[str] = Field(default_factory=list)
    alternatives: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    protocol_constraint_kind: str | None = None
    protocol_restriction_reason: str | None = None
    policy_overlay_applied: bool = False
    policy_overlay_issue_ids: list[str] = Field(default_factory=list)


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
        runtime_events_path=(
            str(files["runtime_events"])
            if files["runtime_events"].exists()
            else None
        ),
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


def save_monitoring_review_snapshot(
    *,
    request: MonitoringReviewRequest,
    result: MonitoringReviewResult,
    decisions: list[MonitoringReviewDecision],
    runtime_events: list[AgentRuntimeEvent],
    evidence_catalog: CausalEvidenceCatalog | None = None,
    policy_proposal: MonitoringPolicyProposal | None = None,
    output_dir: Path | str = DEFAULT_RUNS_DIR,
) -> RunSnapshot:
    """Persiste una revision propose-only usando la superficie comun de runs.

    No fabrica un ``TFMStateModel`` ni una ruta raw. La fuente cientifica es la
    ``CausalInputView`` hasheada del request y el snapshot conserva el mismo
    contrato HTTP que el resto de ejecuciones para reutilizar la sala Agentes.
    """

    if request.child_run_id != result.child_run_id:
        raise ValueError("monitoring review request/result child run mismatch")
    if request.request_id != result.request_id:
        raise ValueError("monitoring review request/result identity mismatch")
    if tuple(item.agent_name for item in decisions) != result.required_roles:
        raise ValueError("monitoring review decisions do not cover required roles")

    runs_dir = Path(output_dir)
    run_dir = _run_dir_for_id(runs_dir, request.child_run_id)
    runtime_events_ref = run_dir / "monitoring_review_events.json"
    evidence_catalog_ref = run_dir / "monitoring_review_evidence_catalog.json"
    policy_proposal_ref = run_dir / "monitoring_policy_proposal.json"
    _validate_monitoring_review_snapshot_inputs(
        request=request,
        result=result,
        decisions=decisions,
        runtime_events=runtime_events,
        runtime_events_ref=runtime_events_ref,
        evidence_catalog=evidence_catalog,
        policy_proposal=policy_proposal,
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    lock_path = run_dir / ".snapshot.lock"
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            metadata_path = run_dir / "snapshot.json"
            if metadata_path.exists():
                existing = RunSnapshot.model_validate(_read_json(metadata_path))
                if existing.run_id != request.child_run_id:
                    raise ValueError("monitoring child run snapshot identity mismatch")
                try:
                    existing_request = MonitoringReviewRequest.model_validate(
                        _read_json(run_dir / "monitoring_review_request.json")
                    )
                    existing_result = MonitoringReviewResult.model_validate(
                        _read_json(run_dir / "monitoring_review_result.json")
                    )
                except (OSError, ValueError) as exc:
                    raise ValueError(
                        "monitoring review snapshot idempotency conflict: "
                        "existing contract is missing or invalid"
                    ) from exc
                if (
                    existing_request.request_sha256 != request.request_sha256
                    or existing_result.result_sha256 != result.result_sha256
                ):
                    raise ValueError(
                        "monitoring review snapshot idempotency conflict: "
                        "existing request/result hashes differ"
                    )
                _validate_existing_monitoring_review_catalog(
                    evidence_catalog_ref,
                    evidence_catalog,
                )
                _validate_existing_monitoring_policy_proposal(
                    policy_proposal_ref,
                    policy_proposal,
                )
                return existing

            if evidence_catalog is None and any(
                _runtime_evidence_binding_mode(item)
                == "server_record_catalog"
                for item in runtime_events
            ):
                raise ValueError(
                    "monitoring review record-catalog events require an "
                    "evidence catalog"
                )

            created_at = datetime.now(UTC)
            files = _snapshot_files(run_dir)
            request_path = run_dir / "monitoring_review_request.json"
            result_path = run_dir / "monitoring_review_result.json"
            immutable_events_path = runtime_events_ref
            report_path = run_dir / "monitoring_review.md"
            decision_payloads = [
                {
                    "message_index": index,
                    "role": (
                        "supervisor" if item.agent_name == "supervisor" else "agent"
                    ),
                    "name": item.agent_name,
                    "created_at": item.created_at.isoformat(),
                    "agent_name": item.agent_name,
                    "decision_id": item.decision_id,
                    "payload": item.model_dump(mode="json"),
                }
                for index, item in enumerate(decisions)
            ]
            artifacts = [
                {
                    "name": "causal_input_view",
                    "artifact_type": "config",
                    "path": request.causal_view_ref,
                    "producer": "monitoring_replay",
                    "description": "Vista causal por whitelist usada por los agentes.",
                    "metadata": {
                        "sha256": request.causal_view_sha256,
                        "cutoff_cursor": request.cutoff_cursor,
                    },
                },
                {
                    "name": "monitoring_review_request",
                    "artifact_type": "config",
                    "path": request_path.as_posix(),
                    "producer": "pipeline_runner",
                    "description": "Contrato cerrado de la revision multiagente.",
                    "metadata": {"sha256": request.request_sha256},
                },
                {
                    "name": "monitoring_review_result",
                    "artifact_type": "log",
                    "path": result_path.as_posix(),
                    "producer": "pipeline_runner",
                    "description": "Resultado propose-only; ninguna politica fue aplicada.",
                    "metadata": {"sha256": result.result_sha256},
                },
                {
                    "name": "monitoring_review_events",
                    "artifact_type": "log",
                    "path": immutable_events_path.as_posix(),
                    "producer": "agent_runtime",
                    "description": "Traza inmutable usada por el resultado de revision.",
                    "metadata": {"sha256": result.runtime_events_sha256},
                },
            ]
            if evidence_catalog is not None:
                artifacts.append(
                    {
                        "name": "monitoring_review_evidence_catalog",
                        "artifact_type": "config",
                        "path": evidence_catalog_ref.as_posix(),
                        "producer": "monitoring_review_store",
                        "description": (
                            "Catalogo sellado de handles cortos y referencias "
                            "de soporte por registro."
                        ),
                        "metadata": {
                            "sha256": evidence_catalog.catalog_sha256,
                            "causal_view_sha256": (
                                evidence_catalog.causal_view_sha256
                            ),
                            "entry_count": len(evidence_catalog.entries),
                        },
                    }
                )
            if policy_proposal is not None:
                artifacts.append(
                    {
                        "name": "monitoring_policy_proposal",
                        "artifact_type": "config",
                        "path": policy_proposal_ref.as_posix(),
                        "producer": "monitoring_policy_proposal",
                        "description": (
                            "Sintesis consultiva de siete recomendaciones; "
                            "no aplicada ni validada como politica."
                        ),
                        "metadata": {
                            "sha256": policy_proposal.proposal_sha256,
                            "agreement_status": policy_proposal.agreement_status,
                            "application_status": "not_applied",
                        },
                    }
                )
            _write_json(request_path, request.model_dump(mode="json"))
            _write_json(result_path, result.model_dump(mode="json"))
            if evidence_catalog is not None:
                _write_json(
                    evidence_catalog_ref,
                    evidence_catalog.model_dump(mode="json"),
                )
            if policy_proposal is not None:
                _write_json(
                    policy_proposal_ref,
                    policy_proposal.model_dump(mode="json"),
                )
            _write_json(
                immutable_events_path,
                [item.model_dump(mode="json") for item in runtime_events],
            )
            _write_json(
                files["runtime_events"],
                [item.model_dump(mode="json") for item in runtime_events],
            )
            _write_json(
                files["state"],
                {
                    "schema_version": "monitoring_review_state_v1",
                    "review_kind": "monitoring_review",
                    "run_id": request.child_run_id,
                    "session_id": request.session_id,
                    "trigger_id": request.trigger_id,
                    "cutoff_cursor": request.cutoff_cursor,
                    "causal_view_sha256": request.causal_view_sha256,
                    "evidence_catalog_sha256": (
                        evidence_catalog.catalog_sha256
                        if evidence_catalog is not None
                        else None
                    ),
                    "policy_proposal_sha256": (
                        policy_proposal.proposal_sha256
                        if policy_proposal is not None
                        else None
                    ),
                    "memory_mode": "off",
                    "policy_application_status": "not_applied",
                    "status": result.status,
                },
            )
            _write_json(files["decisions"], decision_payloads)
            _write_json(files["artifacts"], artifacts)
            _write_json(files["metrics"], None)
            _write_json(files["evaluation"], None)
            _write_json(
                files["evidence_pack"],
                {
                    "schema_version": "monitoring_review_evidence_pack_v1",
                    "run_id": request.child_run_id,
                    "session_id": request.session_id,
                    "trigger_id": request.trigger_id,
                    "trigger_event_id": request.trigger_event_id,
                    "cutoff_snapshot_id": request.cutoff_snapshot_id,
                    "cutoff_cursor": request.cutoff_cursor,
                    "causal_view_ref": request.causal_view_ref,
                    "causal_view_sha256": request.causal_view_sha256,
                    "request_sha256": request.request_sha256,
                    "result_sha256": result.result_sha256,
                    "evidence_catalog": (
                        {
                            "ref": evidence_catalog_ref.as_posix(),
                            "sha256": evidence_catalog.catalog_sha256,
                            "entry_count": len(evidence_catalog.entries),
                        }
                        if evidence_catalog is not None
                        else None
                    ),
                    "policy_proposal": (
                        {
                            "ref": policy_proposal_ref.as_posix(),
                            "sha256": policy_proposal.proposal_sha256,
                            "agreement_status": policy_proposal.agreement_status,
                            "application_status": "not_applied",
                        }
                        if policy_proposal is not None
                        else None
                    ),
                    "memory_mode": "off",
                    "policy_application_status": "not_applied",
                    "decisions": decision_payloads,
                    "artifacts": artifacts,
                    "created_at": created_at.isoformat(),
                },
            )
            report = _render_monitoring_review_report(request, result, decisions)
            report_path.write_text(report, encoding="utf-8")
            files["evidence_pack_markdown"].write_text(report, encoding="utf-8")
            files["audit_report"].write_text(
                _render_monitoring_review_audit(request, result, decisions),
                encoding="utf-8",
            )
            snapshot = RunSnapshot(
                run_id=request.child_run_id,
                thread_id=f"monitoring:{request.session_id}:{request.trigger_id}",
                dataset="nasa_ims_bearing",
                current_stage=("completed" if result.status == "completed" else "failed"),
                approved=None,
                report_path=report_path.as_posix(),
                snapshot_dir=run_dir.as_posix(),
                state_path=files["state"].as_posix(),
                decisions_path=files["decisions"].as_posix(),
                artifacts_path=files["artifacts"].as_posix(),
                metrics_path=files["metrics"].as_posix(),
                evaluation_path=files["evaluation"].as_posix(),
                evidence_pack_path=files["evidence_pack"].as_posix(),
                evidence_pack_markdown_path=files[
                    "evidence_pack_markdown"
                ].as_posix(),
                audit_report_path=files["audit_report"].as_posix(),
                runtime_events_path=(run_dir / "runtime_events.json").as_posix(),
                summary_path=files["summary"].as_posix(),
                metadata_path=files["metadata"].as_posix(),
                created_at=created_at,
                n_artifacts=len(artifacts),
                n_decisions=len(decisions),
                n_errors=0 if result.status == "completed" else 1,
            )
            files["summary"].write_text(report, encoding="utf-8")
            _write_json(files["metadata"], snapshot.model_dump(mode="json"))
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
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
        "## Estado operativo y estado agentico",
        "",
        *_audit_agentic_status_lines(evidence),
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
    if metadata_path.is_symlink() or not metadata_path.is_file():
        raise FileNotFoundError(f"run snapshot metadata not found: {metadata_path}")
    snapshot = RunSnapshot.model_validate(_read_json(metadata_path))
    if snapshot.run_id != run_id:
        raise ValueError("run snapshot identity does not match the requested run")
    if Path(snapshot.snapshot_dir).resolve() != run_dir.resolve():
        raise ValueError("run snapshot directory does not match the requested run")
    return snapshot


def load_run_runtime_events(
    run_id: str,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
    *,
    reconstruct_if_missing: bool = True,
) -> list[AgentRuntimeEvent]:
    """Carga la traza persistida o reconstruye una vista auditada de decisiones."""

    snapshot = load_run_snapshot(run_id, runs_dir)
    path = Path(snapshot.runtime_events_path or Path(snapshot.snapshot_dir) / "runtime_events.json")
    review_result_path = Path(snapshot.snapshot_dir) / "monitoring_review_result.json"
    review_request_path = Path(snapshot.snapshot_dir) / "monitoring_review_request.json"
    review_events_sha256: str | None = None
    if review_result_path.is_file():
        path, review_events_sha256 = _load_monitoring_review_runtime_event_seal(
            review_result_path=review_result_path,
            snapshot=snapshot,
        )
    elif review_request_path.exists() or review_request_path.is_symlink():
        raise ValueError("monitoring review result is unavailable")
    if path.exists():
        if review_events_sha256 is None:
            payload = _read_json(path)
        else:
            encoded_payload = path.read_bytes()
            if hashlib.sha256(encoded_payload).hexdigest() != review_events_sha256:
                raise ValueError(
                    "monitoring review runtime events do not match their sealed result"
                )
            payload = json.loads(encoded_payload)
        if not isinstance(payload, list):
            raise ValueError(f"runtime events payload must be a list: {path}")
        events = [
            AgentRuntimeEvent.model_validate(item) for item in payload
        ]
        if review_events_sha256 is not None:
            _validate_loaded_monitoring_policy_proposal(
                Path(snapshot.snapshot_dir),
                events,
            )
        return [
            event.model_copy(
                update={
                    "payload": {
                        **event.payload,
                        "trace_origin": "persisted_runtime",
                    }
                }
            )
            for event in events
        ]
    if not reconstruct_if_missing:
        return []
    return _reconstruct_run_runtime_events(snapshot)


def _load_monitoring_review_runtime_event_seal(
    *,
    review_result_path: Path,
    snapshot: RunSnapshot,
) -> tuple[Path, str]:
    """Lee el sello de eventos sin reinterpretar un resultado historico.

    Los resultados nuevos se validan de forma estricta antes de persistirse. En
    lectura, sin embargo, no se deben aplicar retroactivamente invariantes
    Pydantic incorporados despues de crear un expediente. Esta frontera valida
    el JSON historico por su SHA canonico y limita la referencia al artefacto de
    eventos de la propia run.
    """

    raw_result = _read_json(review_result_path)
    if not isinstance(raw_result, dict):
        raise ValueError("monitoring review result payload must be an object")
    claimed_result_sha256 = raw_result.get("result_sha256")
    if not _is_sha256_string(claimed_result_sha256):
        raise ValueError("monitoring review result has no valid SHA-256 seal")
    canonical_result = {
        key: value
        for key, value in raw_result.items()
        if key != "result_sha256"
    }
    if _canonical_payload_sha256(canonical_result) != claimed_result_sha256:
        raise ValueError("monitoring review result does not match its SHA-256 seal")
    try:
        MonitoringReviewResult.model_validate(raw_result)
    except ValidationError as exc:
        _validate_historical_monitoring_review_v1_result(
            raw_result=raw_result,
            snapshot=snapshot,
            validation_error=exc,
        )
    if raw_result.get("child_run_id") != snapshot.run_id:
        raise ValueError("monitoring review result belongs to another run")

    claimed_events_sha256 = raw_result.get("runtime_events_sha256")
    events_ref_value = raw_result.get("runtime_events_ref")
    if (
        not _is_sha256_string(claimed_events_sha256)
        or not isinstance(events_ref_value, str)
        or not events_ref_value
    ):
        raise ValueError("monitoring review result has no valid runtime event seal")

    events_path = Path(events_ref_value)
    expected_events_path = (
        Path(snapshot.snapshot_dir) / "monitoring_review_events.json"
    ).resolve()
    if (
        events_path.is_symlink()
        or not events_path.is_file()
        or events_path.resolve() != expected_events_path
    ):
        raise ValueError(
            "monitoring review runtime events reference leaves the run directory"
        )
    return events_path, claimed_events_sha256


def _validate_loaded_monitoring_policy_proposal(
    run_dir: Path,
    runtime_events: list[AgentRuntimeEvent],
) -> None:
    """Liga la proyeccion runtime consultiva a su artefacto canonico."""

    proposal_path = run_dir / "monitoring_policy_proposal.json"
    proposal_events = [
        event for event in runtime_events if event.kind == "policy_proposal"
    ]
    if not proposal_events:
        state_payload = _safe_read_json(run_dir / "state_final.json")
        evidence_pack = _safe_read_json(run_dir / "evidence_pack.json")
        artifacts_payload = _safe_read_json(run_dir / "artifacts.json")
        declared_sha = (
            state_payload.get("policy_proposal_sha256")
            if isinstance(state_payload, dict)
            else None
        )
        declared_pack = (
            evidence_pack.get("policy_proposal")
            if isinstance(evidence_pack, dict)
            else None
        )
        declared_artifact = (
            any(
                isinstance(item, dict)
                and item.get("name") == "monitoring_policy_proposal"
                for item in artifacts_payload
            )
            if isinstance(artifacts_payload, list)
            else False
        )
        if (
            proposal_path.exists()
            or proposal_path.is_symlink()
            or _is_sha256_string(declared_sha)
            or isinstance(declared_pack, dict)
            or declared_artifact
        ):
            raise ValueError(
                "monitoring policy proposal artifact lacks its sealed runtime event"
            )
        return
    if len(proposal_events) != 1:
        raise ValueError(
            "monitoring review contains multiple policy proposal events"
        )
    if not proposal_path.is_file() or proposal_path.is_symlink():
        raise ValueError("monitoring policy proposal artifact is unavailable")
    try:
        proposal = MonitoringPolicyProposal.model_validate(
            _read_json(proposal_path)
        )
    except (OSError, ValueError) as exc:
        raise ValueError("monitoring policy proposal artifact is invalid") from exc
    request_path = run_dir / "monitoring_review_request.json"
    catalog_path = run_dir / "monitoring_review_evidence_catalog.json"
    decisions_path = run_dir / "decisions.json"
    result_path = run_dir / "monitoring_review_result.json"
    for source_path in (
        request_path,
        catalog_path,
        decisions_path,
        result_path,
    ):
        if source_path.is_symlink() or not source_path.is_file():
            raise ValueError(
                "monitoring policy proposal source artifact is unavailable"
            )
    try:
        request = MonitoringReviewRequest.model_validate(_read_json(request_path))
        catalog = CausalEvidenceCatalog.model_validate(_read_json(catalog_path))
        result = MonitoringReviewResult.model_validate(_read_json(result_path))
        decisions_payload = _read_json(decisions_path)
        if not isinstance(decisions_payload, list):
            raise ValueError("monitoring review decisions payload must be a list")
        decisions: list[MonitoringReviewDecision] = []
        for item in decisions_payload:
            if not isinstance(item, dict) or not isinstance(item.get("payload"), dict):
                raise ValueError(
                    "monitoring review decision entry must contain a payload"
                )
            decision = MonitoringReviewDecision.model_validate(item["payload"])
            if (
                item.get("decision_id") != decision.decision_id
                or item.get("agent_name") != decision.agent_name
            ):
                raise ValueError(
                    "monitoring review decision wrapper does not match its payload"
                )
            decisions.append(decision)
    except (OSError, ValueError) as exc:
        raise ValueError(
            "monitoring policy proposal source artifacts are invalid"
        ) from exc
    sealed_result_decisions = tuple(
        role_result.decision
        for role_result in result.role_results
        if role_result.decision is not None
    )
    if tuple(item.decision_sha256 for item in decisions) != tuple(
        item.decision_sha256 for item in sealed_result_decisions
    ):
        raise ValueError(
            "monitoring policy proposal decisions do not match the sealed result"
        )
    request_binding = (
        request.request_id,
        request.request_sha256,
        request.child_run_id,
        request.session_id,
        request.trigger_id,
        request.trigger_event_id,
        request.origin_tick_id,
        request.cutoff_snapshot_id,
        request.cutoff_cursor,
        request.cutoff_source_time,
        request.active_policy_refs,
        request.causal_view_ref,
        request.causal_view_sha256,
        request.requested_roles,
        request.required_roles,
        request.capabilities,
        request.memory_mode,
    )
    result_binding = (
        result.request_id,
        result.request_sha256,
        result.child_run_id,
        result.session_id,
        result.trigger_id,
        result.trigger_event_id,
        result.origin_tick_id,
        result.cutoff_snapshot_id,
        result.cutoff_cursor,
        result.cutoff_source_time,
        result.active_policy_refs,
        result.causal_view_ref,
        result.causal_view_sha256,
        result.requested_roles,
        result.required_roles,
        result.capabilities,
        result.memory_mode,
    )
    if request_binding != result_binding:
        raise ValueError(
            "monitoring policy proposal request/result binding mismatch"
        )
    try:
        validate_monitoring_policy_proposal(
            proposal,
            request=request,
            decisions=decisions,
            evidence_catalog=catalog,
        )
    except ValueError as exc:
        raise ValueError(
            "monitoring policy proposal does not match its sealed sources"
        ) from exc
    event = proposal_events[0]
    if (
        event.run_id != proposal.child_run_id
        or event.source != "system"
        or event.stage != "monitoring_review"
        or event.node != "monitoring_policy_proposal"
        or event.sequence != max(item.sequence for item in runtime_events)
        or event.payload.get("trace_origin") != "deterministic_server"
        or event.payload.get("review_kind") != request.review_kind
        or event.payload.get("session_id") != proposal.session_id
        or event.payload.get("trigger_id") != proposal.trigger_id
        or event.payload.get("trigger_event_id") != proposal.trigger_event_id
        or event.payload.get("cutoff_cursor") != proposal.cutoff_cursor
        or event.payload.get("cutoff_snapshot_id")
        != proposal.cutoff_snapshot_id
        or event.payload.get("causal_view_sha256")
        != proposal.causal_view_sha256
        or event.payload.get("memory_mode") != "off"
        or event.payload.get("policy_application_status") != "not_applied"
        or event.payload.get("policy_proposal")
        != proposal.model_dump(mode="json")
    ):
        raise ValueError(
            "monitoring policy proposal event does not match its sealed artifact"
        )


def _validate_historical_monitoring_review_v1_result(
    *,
    raw_result: dict[str, Any],
    snapshot: RunSnapshot,
    validation_error: ValidationError,
) -> None:
    """Admite solo el sobre V1 conocido, sellado y anterior al catalogo."""

    run_dir = Path(snapshot.snapshot_dir)
    request_path = run_dir / "monitoring_review_request.json"
    catalog_path = run_dir / "monitoring_review_evidence_catalog.json"
    if (
        request_path.is_symlink()
        or not request_path.is_file()
        or catalog_path.exists()
        or catalog_path.is_symlink()
    ):
        raise ValueError(
            "invalid current monitoring review result cannot use legacy compatibility"
        ) from validation_error
    try:
        request = MonitoringReviewRequest.model_validate(_read_json(request_path))
    except ValidationError as exc:
        raise ValueError("historical monitoring review request is invalid") from exc
    fingerprints = (
        request.prompt_template_id,
        request.prompt_template_sha256,
        request.response_schema_id,
        request.response_schema_sha256,
        request.allowed_options_id,
        request.allowed_options_sha256,
    )
    if fingerprints not in _HISTORICAL_MONITORING_REVIEW_V1_FINGERPRINTS:
        raise ValueError(
            "invalid current monitoring review result cannot use legacy compatibility"
        ) from validation_error
    request_binding = (
        request.request_sha256,
        request.child_run_id,
        request.session_id,
        request.trigger_id,
        request.trigger_event_id,
        request.causal_view_sha256,
    )
    result_binding = (
        raw_result.get("request_sha256"),
        raw_result.get("child_run_id"),
        raw_result.get("session_id"),
        raw_result.get("trigger_id"),
        raw_result.get("trigger_event_id"),
        raw_result.get("causal_view_sha256"),
    )
    if request_binding != result_binding:
        raise ValueError(
            "historical monitoring review request and result binding changed"
        ) from validation_error


def update_run_index(
    snapshot: RunSnapshot,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
) -> None:
    """Crea o actualiza `index.json` sustituyendo la entrada del mismo run."""

    root = Path(runs_dir)
    root.mkdir(parents=True, exist_ok=True)
    with _run_index_lock(root):
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
        "runtime_events": run_dir / "runtime_events.json",
        "summary": run_dir / "summary.md",
        "metadata": run_dir / "snapshot.json",
    }


def _reconstruct_run_runtime_events(snapshot: RunSnapshot) -> list[AgentRuntimeEvent]:
    """Crea una cronologia limitada y explicitamente reconstruida."""

    decisions_payload = _safe_read_json(Path(snapshot.decisions_path))
    decisions = decisions_payload if isinstance(decisions_payload, list) else []
    contexts = _reconstructed_memory_contexts(snapshot)
    events: list[AgentRuntimeEvent] = []

    def append_event(**values: Any) -> None:
        sequence = len(events) + 1
        events.append(
            AgentRuntimeEvent(
                event_id=f"{snapshot.run_id}:reconstructed:{sequence:04d}",
                run_id=snapshot.run_id,
                sequence=sequence,
                **values,
            )
        )

    append_event(
        kind="job_status",
        source="job",
        title="Traza historica reconstruida",
        summary=(
            "Vista derivada de decisiones y contextos persistidos; no conserva "
            "todos los eventos ni los tiempos del runtime original."
        ),
        stage=snapshot.current_stage,
        node="run_persistence",
        created_at=snapshot.created_at,
        payload={
            "trace_origin": "reconstructed_from_decisions",
            "audit_limitations": [
                "executor runtime events unavailable",
                "rejected payloads unavailable",
                "event timing reconstructed from persisted decisions",
            ],
        },
    )

    for raw_decision in decisions:
        if not isinstance(raw_decision, dict):
            continue
        decision = raw_decision.get("payload")
        if not isinstance(decision, dict):
            continue
        agent_name = _optional_string(
            raw_decision.get("agent_name")
            or decision.get("agent_name")
            or raw_decision.get("name")
        )
        decision_id = _optional_string(
            raw_decision.get("decision_id") or decision.get("decision_id")
        )
        created_at = _parse_datetime(raw_decision.get("created_at"))
        context = _matching_reconstructed_context(
            contexts,
            decision_id=decision_id,
            agent_name=agent_name,
            memory_context_id=_optional_string(decision.get("memory_context_id")),
        )
        if context is not None:
            raw_context = context.get("_raw_context")
            raw_context_data = raw_context if isinstance(raw_context, dict) else context
            query = raw_context_data.get("query")
            query_data = query if isinstance(query, dict) else {}
            artifact_paths = context.get("_artifact_paths")
            artifact_path_data = (
                artifact_paths if isinstance(artifact_paths, dict) else {}
            )
            append_event(
                kind="memory_retrieval",
                source="memory",
                title=f"Consulta RAG para {agent_name or 'agente'}",
                summary=(
                    f"Consulta persistida con pool={query_data.get('top_k', 'n/d')} "
                    f"y similitud minima={query_data.get('min_similarity', 'n/d')}."
                ),
                stage=agent_name,
                node=f"{agent_name or 'agent'}_memory",
                agent_name=agent_name,
                decision_id=decision_id,
                memory_context_id=_optional_string(context.get("context_id")),
                created_at=created_at,
                payload={
                    "trace_origin": "reconstructed_from_decisions",
                    "retrieval_event": "retrieval_requested",
                    "available": True,
                    "query": query_data,
                    "candidate_pool_size": query_data.get("top_k"),
                    "query_artifact_path": artifact_path_data.get("query_path"),
                },
            )

            items = context.get("items")
            context_items = items if isinstance(items, list) else []
            raw_items = raw_context_data.get("items")
            raw_context_items = raw_items if isinstance(raw_items, list) else []
            quality_gate = context.get("_quality_gate")
            quality_gate_data = (
                quality_gate if isinstance(quality_gate, dict) else None
            )
            memory_ids = [
                memory_id
                for item in context_items
                if isinstance(item, dict)
                for memory_id in [_memory_record_id_from_context_item(item)]
                if memory_id is not None
            ]
            append_event(
                kind="memory_retrieval",
                source="memory",
                title=f"Memoria recuperada para {agent_name or 'agente'}",
                summary=(
                    f"{len(memory_ids)} recuerdos efectivos de "
                    f"{len(raw_context_items)} candidatos recuperados."
                ),
                stage=agent_name,
                node=f"{agent_name or 'agent'}_memory",
                agent_name=agent_name,
                decision_id=decision_id,
                memory_context_id=_optional_string(context.get("context_id")),
                memory_record_ids=memory_ids,
                created_at=created_at,
                payload={
                    "trace_origin": "reconstructed_from_decisions",
                    "retrieval_event": "retrieval_returned",
                    "available": True,
                    "retrieval_backend": context.get("retrieval_backend"),
                    "embedding_model": context.get("embedding_model"),
                    "query": query_data,
                    "raw_count": len(raw_context_items),
                    "effective_count": len(context_items),
                    "filtered_count": max(
                        0,
                        len(raw_context_items) - len(context_items),
                    ),
                    "quality_gate": _compact_reconstructed_quality_gate(
                        quality_gate_data
                    ),
                    "retrieved_memory_record_ids": memory_ids,
                    "context_artifact_path": artifact_path_data.get("context_path"),
                    "raw_context_artifact_path": artifact_path_data.get(
                        "raw_context_path"
                    ),
                    "quality_gate_artifact_path": artifact_path_data.get(
                        "quality_gate_path"
                    ),
                    "items": [_compact_reconstructed_context_item(item) for item in context_items if isinstance(item, dict)],
                },
            )

        role = str(raw_decision.get("role") or "agent")
        append_event(
            kind="supervisor_decision" if role == "supervisor" else "agent_decision",
            source="supervisor" if role == "supervisor" else "agent",
            title=f"Decision persistida de {agent_name or role}",
            summary=_optional_string(decision.get("rationale")) or "Decision contractual persistida.",
            stage=agent_name,
            node=agent_name,
            agent_name=agent_name,
            decision_id=decision_id,
            rationale=_optional_string(decision.get("rationale")),
            confidence=_optional_float(decision.get("confidence")),
            next_stage=_optional_string(decision.get("next_stage")),
            next_node=_optional_string(decision.get("next_node")),
            memory_context_id=_optional_string(decision.get("memory_context_id")),
            memory_record_ids=_string_list(decision.get("memory_record_ids")),
            created_at=created_at,
            payload={
                "trace_origin": "reconstructed_from_decisions",
                "decision": decision,
            },
        )

        if context is not None:
            retrieved_ids = [
                memory_id
                for item in (context.get("items") if isinstance(context.get("items"), list) else [])
                if isinstance(item, dict)
                for memory_id in [_memory_record_id_from_context_item(item)]
                if memory_id is not None
            ]
            cited_ids = _string_list(decision.get("memory_record_ids"))
            used_memory = bool(decision.get("used_memory_context", False))
            append_event(
                kind="memory_retrieval",
                source="memory",
                title=(
                    f"Memoria usada por {agent_name or 'agente'}"
                    if used_memory
                    else f"Memoria no usada por {agent_name or 'agente'}"
                ),
                summary=(
                    f"{len(cited_ids)} de {len(retrieved_ids)} recuerdos fueron citados."
                    if used_memory
                    else "El contexto fue recuperado, pero no consta uso efectivo."
                ),
                stage=agent_name,
                node=f"{agent_name or 'agent'}_memory",
                agent_name=agent_name,
                decision_id=decision_id,
                memory_context_id=_optional_string(context.get("context_id")),
                memory_record_ids=cited_ids,
                created_at=created_at,
                payload={
                    "trace_origin": "reconstructed_from_decisions",
                    "retrieval_event": (
                        "retrieval_used" if used_memory else "retrieval_rejected_by_agent"
                    ),
                    "used_memory_context": used_memory,
                    "retrieved_memory_record_ids": retrieved_ids,
                    "cited_memory_record_ids": cited_ids,
                    "ignored_memory_record_ids": sorted(set(retrieved_ids) - set(cited_ids)),
                    "memory_usage_summary": decision.get("memory_usage_summary"),
                    "memory_record_uses": decision.get("memory_record_uses") or [],
                },
            )
    return events


def _reconstructed_memory_contexts(snapshot: RunSnapshot) -> list[dict[str, Any]]:
    artifacts_payload = _safe_read_json(Path(snapshot.artifacts_path))
    artifacts = artifacts_payload if isinstance(artifacts_payload, list) else []
    artifacts_by_name = {
        str(artifact.get("name")): artifact
        for artifact in artifacts
        if isinstance(artifact, dict) and artifact.get("name")
    }
    contexts: list[dict[str, Any]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict):
            continue
        name = str(artifact.get("name") or "")
        if not name.endswith("_retrieved_memory_context"):
            continue
        raw_path = artifact.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            continue
        payload = _safe_read_json(Path(raw_path))
        if isinstance(payload, dict):
            agent_prefix = name.removesuffix("_retrieved_memory_context")
            raw_artifact = artifacts_by_name.get(
                f"{agent_prefix}_retrieved_memory_context_raw"
            )
            quality_artifact = artifacts_by_name.get(
                f"{agent_prefix}_memory_quality_gate"
            )
            raw_context = _payload_from_artifact(raw_artifact)
            quality_gate = _payload_from_artifact(quality_artifact)
            enriched = dict(payload)
            enriched["_raw_context"] = raw_context or payload
            enriched["_quality_gate"] = quality_gate
            enriched["_artifact_paths"] = {
                "context_path": raw_path,
                "raw_context_path": _artifact_path(raw_artifact),
                "quality_gate_path": _artifact_path(quality_artifact),
            }
            contexts.append(enriched)
    return contexts


def _artifact_path(artifact: Any) -> str | None:
    if not isinstance(artifact, dict):
        return None
    return _optional_string(artifact.get("path"))


def _payload_from_artifact(artifact: Any) -> dict[str, Any] | None:
    path = _artifact_path(artifact)
    if path is None:
        return None
    payload = _safe_read_json(Path(path))
    return payload if isinstance(payload, dict) else None


def _matching_reconstructed_context(
    contexts: list[dict[str, Any]],
    *,
    decision_id: str | None,
    agent_name: str | None,
    memory_context_id: str | None,
) -> dict[str, Any] | None:
    for context in contexts:
        if memory_context_id is not None and context.get("context_id") == memory_context_id:
            return context
    for context in contexts:
        query = context.get("query")
        if not isinstance(query, dict):
            continue
        if decision_id is not None and query.get("decision_id") == decision_id:
            return context
    for context in contexts:
        query = context.get("query")
        if isinstance(query, dict) and agent_name is not None and query.get("target_agent") == agent_name:
            return context
    return None


def _memory_record_id_from_context_item(item: dict[str, Any]) -> str | None:
    record = item.get("record")
    if not isinstance(record, dict):
        return None
    return _optional_string(record.get("memory_record_id"))


def _compact_reconstructed_context_item(item: dict[str, Any]) -> dict[str, Any]:
    record = item.get("record")
    record_data = record if isinstance(record, dict) else {}
    return {
        "rank": item.get("rank"),
        "similarity": item.get("similarity"),
        "retrieval_use": item.get("retrieval_use"),
        "memory_record_id": record_data.get("memory_record_id"),
        "collection_name": record_data.get("collection_name"),
        "target_agent": record_data.get("target_agent"),
        "source_type": record_data.get("source_type"),
        "dataset": record_data.get("dataset"),
        "memory_role": record_data.get("memory_role"),
        "human_verdict": record_data.get("human_verdict"),
        "outcome": record_data.get("outcome"),
        "summary": record_data.get("summary"),
        "tags": record_data.get("tags") or [],
    }


def _compact_reconstructed_quality_gate(
    quality_gate: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if quality_gate is None:
        return None
    items = quality_gate.get("items")
    gate_items = items if isinstance(items, list) else []
    return {
        "pass_count": quality_gate.get("pass_count"),
        "caution_count": quality_gate.get("caution_count"),
        "exclude_candidate_count": quality_gate.get("exclude_candidate_count"),
        "excluded": [
            {
                "memory_record_id": item.get("memory_record_id"),
                "reason_codes": item.get("reason_codes") or [],
            }
            for item in gate_items
            if isinstance(item, dict)
            and item.get("recommendation") == "exclude_candidate"
        ],
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
    generation_trace = _dict_or_empty(payload_data.get("generation_trace"))
    protocol_trace = _dict_or_empty(payload_data.get("protocol_trace"))
    proposal = _dict_or_empty(protocol_trace.get("agent_proposal"))
    proposal_generation_trace = _dict_or_empty(proposal.get("generation_trace"))
    hypothesis_payload = _decision_hypothesis_payload(payload_data)
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
        generation_origin=_optional_string(generation_trace.get("origin")),
        generation_attempt_index=_optional_positive_int(
            generation_trace.get("attempt_index")
        ),
        generation_validation_status=_optional_string(
            generation_trace.get("validation_status")
        ),
        fallback_cause=_optional_string(generation_trace.get("fallback_cause")),
        proposal_generation_origin=_optional_string(
            proposal_generation_trace.get("origin")
        ),
        proposal_validation_status=_optional_string(
            proposal_generation_trace.get("validation_status")
        ),
        proposal_fallback_cause=_optional_string(
            proposal_generation_trace.get("fallback_cause")
        ),
        hypothesis=_decision_hypothesis(payload_data),
        hypothesis_kind=_optional_string(hypothesis_payload.get("kind")),
        hypothesis_scope=_optional_string(hypothesis_payload.get("scope")),
        hypothesis_evidence_cutoff=_optional_string(
            hypothesis_payload.get("evidence_cutoff")
        ),
        hypothesis_expected_observation=_optional_string(
            hypothesis_payload.get("expected_observation")
        ),
        hypothesis_falsification_criterion=_optional_string(
            hypothesis_payload.get("falsification_criterion")
        ),
        hypothesis_risk_notes=_string_list(hypothesis_payload.get("risk_notes")),
        hypothesis_assumptions=_string_list(hypothesis_payload.get("assumptions")),
        hypothesis_evidence_refs=_string_list(
            hypothesis_payload.get("evidence_refs")
        ),
        alternatives=_decision_alternatives(payload_data),
        evidence_refs=_decision_evidence_refs(payload_data),
        protocol_constraint_kind=_optional_string(
            protocol_trace.get("constraint_kind")
        ),
        protocol_restriction_reason=_optional_string(
            protocol_trace.get("restriction_reason")
        ),
        policy_overlay_applied=bool(
            payload_data.get("policy_overlay_applied", False)
        ),
        policy_overlay_issue_ids=_string_list(
            payload_data.get("policy_overlay_issue_ids")
        ),
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


def _decision_hypothesis(payload: dict[str, Any]) -> str | None:
    """Extrae solo la hipotesis estructurada; nunca una cadena de pensamiento."""

    for candidate in _decision_payload_variants(payload):
        hypothesis_payload = _dict_or_empty(candidate.get("hypothesis"))
        statement = _optional_string(hypothesis_payload.get("statement"))
        if statement is not None:
            return statement
        strategy = _dict_or_empty(candidate.get("decision_strategy"))
        hypothesis = _optional_string(strategy.get("hypothesis"))
        if hypothesis is not None:
            return hypothesis
    return None


def _decision_hypothesis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Prefiere el contrato comun y deja el extractor legacy como compatibilidad."""

    for candidate in _decision_payload_variants(payload):
        hypothesis = _dict_or_empty(candidate.get("hypothesis"))
        if _optional_string(hypothesis.get("statement")) is not None:
            return hypothesis
    return {}


def _decision_alternatives(payload: dict[str, Any]) -> list[str]:
    alternatives: set[str] = set()
    for candidate in _decision_payload_variants(payload):
        for key in ("comparison_candidates", "alternatives", "options_considered"):
            values = candidate.get(key)
            if not isinstance(values, list):
                continue
            for index, value in enumerate(values, start=1):
                if isinstance(value, str) and value.strip():
                    alternatives.add(value.strip())
                    continue
                item = _dict_or_empty(value)
                identity = _optional_string(
                    item.get("alternative_id")
                    or item.get("model_name")
                    or item.get("name")
                )
                alternatives.add(identity or f"alternative_{index}")
    return sorted(alternatives)


def _decision_evidence_refs(payload: dict[str, Any]) -> list[str]:
    """Separa referencias declaradas de nombres de herramientas o rutas fuente."""

    refs: set[str] = set()
    for candidate in _decision_payload_variants(payload):
        strategy = _dict_or_empty(candidate.get("decision_strategy"))
        hypothesis = _dict_or_empty(candidate.get("hypothesis"))
        for value in (
            candidate.get("evidence_refs"),
            candidate.get("evidence_used"),
            strategy.get("evidence_refs"),
            hypothesis.get("evidence_refs"),
        ):
            refs.update(_string_list(value))
        for key in (
            "unsupported_claims",
            "misleading_claims",
            "missing_limitations",
        ):
            issues = candidate.get(key)
            if not isinstance(issues, list):
                continue
            for issue in issues:
                refs.update(
                    _string_list(_dict_or_empty(issue).get("evidence_refs"))
                )
        sections = candidate.get("sections")
        if isinstance(sections, list):
            for section in sections:
                refs.update(
                    _string_list(_dict_or_empty(section).get("evidence_refs"))
                )
    return sorted(refs)


def _decision_payload_variants(payload: dict[str, Any]) -> list[dict[str, Any]]:
    variants = [payload]
    protocol_trace = _dict_or_empty(payload.get("protocol_trace"))
    proposal = _dict_or_empty(protocol_trace.get("agent_proposal"))
    if proposal:
        variants.append(proposal)
    return variants


def _dict_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


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


def _optional_positive_int(value: Any) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool) and value >= 1:
        return value
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


def serialized_json_sha256(payload: Any) -> str:
    """Huella exacta de la serializacion usada por ``_write_json``."""

    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_monitoring_review_snapshot_inputs(
    *,
    request: MonitoringReviewRequest,
    result: MonitoringReviewResult,
    decisions: list[MonitoringReviewDecision],
    runtime_events: list[AgentRuntimeEvent],
    runtime_events_ref: Path,
    evidence_catalog: CausalEvidenceCatalog | None,
    policy_proposal: MonitoringPolicyProposal | None,
) -> None:
    request_binding = (
        request.request_id,
        request.request_sha256,
        request.child_run_id,
        request.session_id,
        request.trigger_id,
        request.trigger_event_id,
        request.origin_tick_id,
        request.cutoff_snapshot_id,
        request.cutoff_cursor,
        request.cutoff_source_time,
        request.active_policy_refs,
        request.causal_view_ref,
        request.causal_view_sha256,
        request.requested_roles,
        request.required_roles,
        request.capabilities,
        request.memory_mode,
    )
    result_binding = (
        result.request_id,
        result.request_sha256,
        result.child_run_id,
        result.session_id,
        result.trigger_id,
        result.trigger_event_id,
        result.origin_tick_id,
        result.cutoff_snapshot_id,
        result.cutoff_cursor,
        result.cutoff_source_time,
        result.active_policy_refs,
        result.causal_view_ref,
        result.causal_view_sha256,
        result.requested_roles,
        result.required_roles,
        result.capabilities,
        result.memory_mode,
    )
    if request_binding != result_binding:
        raise ValueError("monitoring review request/result causal binding mismatch")

    result_decisions = tuple(
        role_result.decision
        for role_result in result.role_results
        if role_result.decision is not None
    )
    if tuple(item.decision_sha256 for item in decisions) != tuple(
        item.decision_sha256 for item in result_decisions
    ):
        raise ValueError("monitoring review decisions do not match sealed result")

    if evidence_catalog is not None:
        _validate_monitoring_review_catalog_binding(
            request=request,
            decisions=decisions,
            evidence_catalog=evidence_catalog,
        )
    if policy_proposal is not None:
        if evidence_catalog is None:
            raise ValueError(
                "monitoring policy proposal requires an evidence catalog"
            )
        validate_monitoring_policy_proposal(
            policy_proposal,
            request=request,
            decisions=decisions,
            evidence_catalog=evidence_catalog,
        )

    events_payload = [item.model_dump(mode="json") for item in runtime_events]
    if serialized_json_sha256(events_payload) != result.runtime_events_sha256:
        raise ValueError("monitoring review runtime events do not match sealed hash")
    if any(item.run_id != request.child_run_id for item in runtime_events):
        raise ValueError("monitoring review runtime event run_id mismatch")
    events_by_id = {item.event_id: item for item in runtime_events}
    if len(events_by_id) != len(runtime_events):
        raise ValueError("monitoring review runtime event ids must be unique")
    event_ids = set(events_by_id)
    required_event_ids = {
        event_id
        for role_result in result.role_results
        for event_id in role_result.runtime_event_ids
    }
    if not required_event_ids.issubset(event_ids):
        raise ValueError("monitoring review result references missing runtime events")
    if evidence_catalog is not None:
        _validate_monitoring_review_runtime_catalog_bindings(
            request=request,
            result=result,
            events_by_id=events_by_id,
            evidence_catalog=evidence_catalog,
        )
    proposal_events = [
        event for event in runtime_events if event.kind == "policy_proposal"
    ]
    if policy_proposal is None:
        if proposal_events:
            raise ValueError(
                "monitoring policy proposal event requires its sealed artifact"
            )
    else:
        if len(proposal_events) != 1:
            raise ValueError(
                "monitoring policy proposal requires exactly one runtime event"
            )
        event = proposal_events[0]
        if (
            event.run_id != policy_proposal.child_run_id
            or event.source != "system"
            or event.stage != "monitoring_review"
            or event.node != "monitoring_policy_proposal"
            or event.sequence != max(item.sequence for item in runtime_events)
            or event.payload.get("trace_origin") != "deterministic_server"
            or event.payload.get("review_kind") != request.review_kind
            or event.payload.get("session_id") != policy_proposal.session_id
            or event.payload.get("trigger_id") != policy_proposal.trigger_id
            or event.payload.get("trigger_event_id")
            != policy_proposal.trigger_event_id
            or event.payload.get("cutoff_cursor")
            != policy_proposal.cutoff_cursor
            or event.payload.get("cutoff_snapshot_id")
            != policy_proposal.cutoff_snapshot_id
            or event.payload.get("causal_view_sha256")
            != policy_proposal.causal_view_sha256
            or event.payload.get("memory_mode") != "off"
            or event.payload.get("policy_application_status") != "not_applied"
            or event.payload.get("policy_proposal")
            != policy_proposal.model_dump(mode="json")
        ):
            raise ValueError(
                "monitoring policy proposal runtime event does not match artifact"
            )
    if Path(result.runtime_events_ref) != runtime_events_ref:
        raise ValueError("monitoring review runtime events ref does not match output")


def _validate_monitoring_review_catalog_binding(
    *,
    request: MonitoringReviewRequest,
    decisions: list[MonitoringReviewDecision],
    evidence_catalog: CausalEvidenceCatalog,
) -> None:
    if (
        CausalEvidenceCatalog.canonical_sha256(evidence_catalog)
        != evidence_catalog.catalog_sha256
    ):
        raise ValueError("monitoring review evidence catalog hash mismatch")
    if evidence_catalog.causal_view_sha256 != request.causal_view_sha256:
        raise ValueError(
            "monitoring review evidence catalog does not bind the causal view"
        )

    allowed_support_refs = {
        entry.support_ref for entry in evidence_catalog.entries
    }
    for decision in decisions:
        decision_refs = tuple(decision.evidence_refs)
        hypothesis_refs = tuple(decision.hypothesis.evidence_refs)
        if (
            not decision_refs
            or len(decision_refs) != len(set(decision_refs))
            or not set(decision_refs).issubset(
                allowed_support_refs
            )
        ):
            raise ValueError(
                "monitoring review decision references support outside the catalog"
            )
        if hypothesis_refs != decision_refs:
            raise ValueError(
                "monitoring review hypothesis refs must match decision support refs"
            )


def _validate_monitoring_review_runtime_catalog_bindings(
    *,
    request: MonitoringReviewRequest,
    result: MonitoringReviewResult,
    events_by_id: dict[str, AgentRuntimeEvent],
    evidence_catalog: CausalEvidenceCatalog,
) -> None:
    entries_by_handle = {
        entry.handle: entry for entry in evidence_catalog.entries
    }
    available_handles = tuple(entries_by_handle)

    for role_result in result.role_results:
        decision = role_result.decision
        if decision is None:
            continue
        linked_events = [
            events_by_id[event_id]
            for event_id in role_result.runtime_event_ids
            if event_id in events_by_id
        ]
        decision_events = [
            event for event in linked_events
            if event.decision_id == decision.decision_id
        ]
        if len(decision_events) != 1:
            raise ValueError(
                "monitoring review decision requires one linked runtime event"
            )
        event = decision_events[0]
        if event.agent_name != decision.agent_name:
            raise ValueError(
                "monitoring review runtime event agent does not match decision"
            )
        if event.payload.get("causal_view_sha256") != request.causal_view_sha256:
            raise ValueError(
                "monitoring review runtime event does not bind the causal view"
            )

        nested_decision = event.payload.get("decision")
        if not isinstance(nested_decision, dict):
            raise ValueError(
                "monitoring review runtime event requires its sealed decision"
            )
        try:
            event_decision = MonitoringReviewDecision.model_validate(
                nested_decision
            )
        except ValueError as exc:
            raise ValueError(
                "monitoring review runtime event contains an invalid decision"
            ) from exc
        if event_decision != decision:
            raise ValueError(
                "monitoring review runtime event decision does not match result"
            )

        binding = event.payload.get("evidence_binding")
        if not isinstance(binding, dict):
            raise ValueError(
                "monitoring review runtime event requires evidence binding"
            )
        if binding.get("mode") != "server_record_catalog":
            raise ValueError(
                "monitoring review runtime evidence binding mode mismatch"
            )
        expected_selection_origin = (
            "agent"
            if decision.generation_trace.origin == "llm"
            else (
                "server_fallback"
                if decision.generation_trace.origin == "guardrail_fallback"
                else "server_protocol"
            )
        )
        if binding.get("selection_origin") != expected_selection_origin:
            raise ValueError(
                "monitoring review evidence selection origin is inconsistent"
            )
        if binding.get("catalog_sha256") != evidence_catalog.catalog_sha256:
            raise ValueError(
                "monitoring review runtime evidence catalog hash mismatch"
            )

        selected_handles = _strict_string_tuple(
            binding.get("selected_handles"),
            field_name="selected_handles",
        )
        support_refs = _strict_string_tuple(
            binding.get("support_refs"),
            field_name="support_refs",
        )
        if len(selected_handles) != len(set(selected_handles)):
            raise ValueError(
                "monitoring review selected_handles cannot contain duplicates"
            )
        if len(support_refs) != len(set(support_refs)):
            raise ValueError(
                "monitoring review support_refs cannot contain duplicates"
            )
        try:
            resolved_support_refs = tuple(
                entries_by_handle[handle].support_ref
                for handle in selected_handles
            )
        except KeyError as exc:
            raise ValueError(
                "monitoring review selected handle is outside the catalog"
            ) from exc
        if support_refs != resolved_support_refs:
            raise ValueError(
                "monitoring review selected handles do not resolve to support refs"
            )
        if support_refs != tuple(decision.evidence_refs):
            raise ValueError(
                "monitoring review runtime support refs do not match decision"
            )

        declared_available = binding.get("available_handles")
        if declared_available is not None and _strict_string_tuple(
            declared_available,
            field_name="available_handles",
        ) != available_handles:
            raise ValueError(
                "monitoring review available handles do not match the catalog"
            )
        if binding.get("available_count") != len(evidence_catalog.entries):
            raise ValueError(
                "monitoring review available evidence count does not match catalog"
            )
        selected_records = binding.get("selected_records")
        if not isinstance(selected_records, list) or len(selected_records) != len(
            selected_handles
        ):
            raise ValueError(
                "monitoring review selected record projection is incomplete"
            )
        for handle, record_projection in zip(
            selected_handles,
            selected_records,
            strict=True,
        ):
            if not isinstance(record_projection, dict):
                raise ValueError(
                    "monitoring review selected record projection must be an object"
                )
            entry = entries_by_handle[handle]
            if (
                record_projection.get("handle") != handle
                or record_projection.get("record_sha256") != entry.record_sha256
                or _canonical_payload_sha256(record_projection)
                != entry.display_projection_sha256
            ):
                raise ValueError(
                    "monitoring review selected record projection does not bind catalog"
                )
        declared_scope = binding.get("causal_scope_refs")
        if declared_scope is not None and _strict_string_tuple(
            declared_scope,
            field_name="causal_scope_refs",
        ) != tuple(evidence_catalog.causal_scope_refs):
            raise ValueError(
                "monitoring review runtime causal scope does not match catalog"
            )


def _strict_string_tuple(value: Any, *, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or not value:
        raise ValueError(
            f"monitoring review {field_name} must be a non-empty array"
        )
    if any(not isinstance(item, str) or not item for item in value):
        raise ValueError(
            f"monitoring review {field_name} must contain non-empty strings"
        )
    return tuple(value)


def _canonical_payload_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _is_sha256_string(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _runtime_evidence_binding_mode(event: AgentRuntimeEvent) -> str | None:
    binding = event.payload.get("evidence_binding")
    if not isinstance(binding, dict):
        return None
    mode = binding.get("mode")
    return mode if isinstance(mode, str) else None


def _validate_existing_monitoring_review_catalog(
    path: Path,
    evidence_catalog: CausalEvidenceCatalog | None,
) -> None:
    if evidence_catalog is None:
        return
    if not path.is_file():
        raise ValueError(
            "monitoring review snapshot idempotency conflict: "
            "existing evidence catalog is missing"
        )
    try:
        existing = CausalEvidenceCatalog.model_validate(_read_json(path))
    except (OSError, ValueError) as exc:
        raise ValueError(
            "monitoring review snapshot idempotency conflict: "
            "existing evidence catalog is invalid"
        ) from exc
    if (
        CausalEvidenceCatalog.canonical_sha256(existing)
        != existing.catalog_sha256
        or existing != evidence_catalog
    ):
        raise ValueError(
            "monitoring review snapshot idempotency conflict: "
            "existing evidence catalog differs"
        )


def _validate_existing_monitoring_policy_proposal(
    path: Path,
    policy_proposal: MonitoringPolicyProposal | None,
) -> None:
    if policy_proposal is None:
        if path.exists() or path.is_symlink():
            raise ValueError(
                "monitoring review snapshot idempotency conflict: "
                "existing policy proposal was omitted"
            )
        return
    if not path.is_file() or path.is_symlink():
        raise ValueError(
            "monitoring review snapshot idempotency conflict: "
            "existing policy proposal is missing"
        )
    try:
        existing = MonitoringPolicyProposal.model_validate(_read_json(path))
    except (OSError, ValueError) as exc:
        raise ValueError(
            "monitoring review snapshot idempotency conflict: "
            "existing policy proposal is invalid"
        ) from exc
    if existing != policy_proposal:
        raise ValueError(
            "monitoring review snapshot idempotency conflict: "
            "existing policy proposal differs"
        )


def _safe_read_json(path: Path) -> Any:
    try:
        return _read_json(path)
    except (OSError, json.JSONDecodeError):
        return None


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


@contextmanager
def _run_index_lock(root: Path):
    """Serializa el read-modify-write del indice entre procesos locales."""

    lock_path = root / ".index.lock"
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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


def _render_monitoring_review_report(
    request: MonitoringReviewRequest,
    result: MonitoringReviewResult,
    decisions: list[MonitoringReviewDecision],
) -> str:
    lines = [
        "# Revisión multiagente de monitorización",
        "",
        "## Alcance",
        "",
        (
            f"Revisión causal del trigger `{request.trigger_id}` en el snapshot "
            f"`{request.cutoff_snapshot_id}` (cursor `{request.cutoff_cursor}`)."
        ),
        (
            "La memoria estuvo desactivada y el modo fue `propose_only`: "
            "ninguna recomendación modificó el detector ni la política activa."
        ),
        "",
        "## Lectura por agente",
        "",
    ]
    for decision in decisions:
        lines.extend(
            [
                f"### {decision.agent_name}",
                "",
                f"- Hipótesis: {decision.hypothesis.statement}",
                f"- Observación: {decision.observation_summary}",
                f"- Recomendación: `{decision.recommended_action}`.",
                f"- Confianza declarada: `{decision.confidence:.2f}`.",
                "",
            ]
        )
    lines.extend(
        [
            "## Resultado contractual",
            "",
            f"- Estado de la revisión: `{result.status}`.",
            "- Aplicación de política: `not_applied`.",
            "- Uso de memoria: `off`.",
            "",
            (
                "Estas hipótesis quedan pendientes de contraste posterior; el éxito "
                "de la ejecución no las confirma."
            ),
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _render_monitoring_review_audit(
    request: MonitoringReviewRequest,
    result: MonitoringReviewResult,
    decisions: list[MonitoringReviewDecision],
) -> str:
    origins = Counter(item.generation_trace.origin for item in decisions)
    return "\n".join(
        [
            f"# Auditoría de la run {request.child_run_id}",
            "",
            "## Cadena causal",
            "",
            f"- Sesión: `{request.session_id}`.",
            f"- Trigger: `{request.trigger_id}` / `{request.trigger_event_id}`.",
            f"- Tick: `{request.origin_tick_id}`.",
            f"- Cutoff: `{request.cutoff_snapshot_id}` / cursor `{request.cutoff_cursor}`.",
            f"- Vista causal SHA-256: `{request.causal_view_sha256}`.",
            f"- Request SHA-256: `{request.request_sha256}`.",
            f"- Result SHA-256: `{result.result_sha256}`.",
            "",
            "## Fiabilidad agentiva observada",
            "",
            f"- Roles completados: `{sum(item.status == 'completed' for item in result.role_results)}/7`.",
            f"- Origen LLM: `{origins.get('llm', 0)}`.",
            f"- Fallbacks: `{origins.get('guardrail_fallback', 0)}`.",
            f"- Decisiones protocolarias: `{origins.get('protocol_restricted', 0)}`.",
            "- Memoria RAG: `off`.",
            "- Política aplicada: `no`.",
            "",
            "## Límite",
            "",
            (
                "La run acredita que siete contratos se ejecutaron sobre un prefijo "
                "hasheado. No acredita fallo físico, RUL, tiempo real ni apoyo de "
                "las hipótesis."
            ),
            "",
        ]
    )


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
            f"| `{item.decision_id}` | confianza `{item.confidence}` | "
            f"origen `{item.generation_origin or 'desconocido'}` | "
            f"validacion `{item.generation_validation_status or 'no registrada'}` | "
            f"overlay de politica `{item.policy_overlay_applied}`"
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


def _audit_agentic_status_lines(evidence: RunEvidencePack) -> list[str]:
    """Separa finalizacion tecnica de calidad demostrada de la capa LLM."""

    decisions = evidence.decisions
    exact = [item for item in decisions if item.generation_origin is not None]
    unknown = len(decisions) - len(exact)
    origin_counts = Counter(
        item.generation_origin or "unknown" for item in decisions
    )
    repaired = sum(
        item.generation_validation_status == "repaired"
        or item.proposal_validation_status == "repaired"
        for item in decisions
    )
    fallbacks = sum(
        item.generation_origin == "guardrail_fallback"
        or item.proposal_generation_origin == "guardrail_fallback"
        for item in decisions
    )
    restricted = sum(
        item.generation_origin == "protocol_restricted"
        or item.protocol_constraint_kind is not None
        for item in decisions
    )
    policy_overlays = sum(item.policy_overlay_applied for item in decisions)
    supervisor_count = sum(
        (item.agent_name or item.name) == "supervisor" for item in decisions
    )
    role_count = len(decisions) - supervisor_count
    verifications = [
        item for item in decisions if item.agent_name == "report_verifier"
    ]
    final_verification = (
        verifications[-1].verification_status if verifications else None
    )
    operational_status = (
        "completado" if evidence.current_stage == "completed" else evidence.current_stage
    )
    lines = [
        (
            f"- Estado operativo: `{operational_status}`. Este valor indica si el "
            "pipeline alcanzo su estado final; no demuestra por si solo que las "
            "decisiones LLM fueran validas."
        ),
        (
            f"- Composicion: `{supervisor_count}` decisiones de enrutamiento y "
            f"`{role_count}` decisiones de roles tecnicos."
        ),
        (
            f"- Procedencia exacta: `{len(exact)}/{len(decisions)}` decisiones; "
            f"origen desconocido: `{unknown}`."
        ),
        (
            "- Origen efectivo registrado: "
            f"LLM=`{origin_counts['llm']}`, determinista=`{origin_counts['deterministic']}`, "
            f"fallback=`{origin_counts['guardrail_fallback']}`, "
            f"protocolo fijo=`{origin_counts['protocol_restricted']}`."
        ),
        (
            f"- Reparaciones LLM observadas: `{repaired}`; fallbacks observados: "
            f"`{fallbacks}`; propuestas sustituidas o restringidas por protocolo: "
            f"`{restricted}`; decisiones modificadas por overlay de politica: "
            f"`{policy_overlays}`."
        ),
        (
            "- Verificacion final del informe: "
            f"`{final_verification or 'no registrada'}`."
        ),
    ]
    if unknown:
        lines.append(
            "- Dictamen agentico: `evidencia incompleta`; una run historica sin "
            "generation_trace no permite distinguir LLM, reparacion y fallback con certeza."
        )
    elif fallbacks:
        lines.append(
            "- Dictamen agentico: `degradado pero operativo`; hubo al menos una "
            "decision resuelta por fallback determinista."
        )
    elif policy_overlays:
        lines.append(
            "- Dictamen agentico: `requiere revision semantica`; al menos una "
            "salida LLM fue completada o endurecida por un guardarrail "
            "determinista, aunque no se sustituyera por fallback."
        )
    elif final_verification not in {None, "approved"}:
        lines.append(
            "- Dictamen agentico: `no cerrado`; el verificador conserva incidencias "
            "aunque el pipeline haya terminado."
        )
    else:
        lines.append(
            "- Dictamen agentico: `sin fallback observado en la traza`; la correccion "
            "cientifica aun debe contrastarse con evidencias y resultados."
        )
    return lines


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
        origin = decision.generation_origin or "desconocido"
        validation = decision.generation_validation_status or "no registrada"
        attempt = decision.generation_attempt_index or "n/a"
        lines.append(
            f"- Paso `{decision.message_index}`: `{actor}` registra `{decision_id}` "
            f"con confianza `{confidence}`, origen `{origin}`, intento `{attempt}` y "
            f"validacion `{validation}`. {rationale}"
        )
        if decision.hypothesis:
            lines.append(f"  Hipotesis estructurada: {decision.hypothesis}")
        if decision.hypothesis_expected_observation:
            lines.append(
                "  Observacion esperada: "
                + decision.hypothesis_expected_observation
            )
        if decision.hypothesis_falsification_criterion:
            lines.append(
                "  Criterio de refutacion: "
                + decision.hypothesis_falsification_criterion
            )
        if decision.hypothesis_evidence_cutoff:
            lines.append(
                "  Corte de evidencia: "
                + decision.hypothesis_evidence_cutoff
            )
        if decision.hypothesis_risk_notes:
            lines.append(
                "  Riesgos declarados: "
                + "; ".join(decision.hypothesis_risk_notes)
            )
        if decision.alternatives:
            lines.append(
                "  Alternativas declaradas: "
                + ", ".join(f"`{item}`" for item in decision.alternatives)
                + "."
            )
        if decision.evidence_refs:
            lines.append(
                f"  Evidencias referenciadas: `{len(decision.evidence_refs)}`."
            )
        if decision.protocol_constraint_kind:
            lines.append(
                f"  Restriccion: `{decision.protocol_constraint_kind}`. "
                f"{decision.protocol_restriction_reason or 'Sin motivo persistido.'}"
            )
        if decision.policy_overlay_applied:
            overlay_ids = ", ".join(decision.policy_overlay_issue_ids) or "sin IDs"
            lines.append(
                "  Overlay determinista aplicado a la salida LLM: "
                f"`{overlay_ids}`."
            )
        fallback_cause = decision.fallback_cause or decision.proposal_fallback_cause
        if fallback_cause:
            lines.append(f"  Causa del fallback: {fallback_cause}")
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
