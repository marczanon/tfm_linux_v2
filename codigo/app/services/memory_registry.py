"""Consulta de memoria agentica persistida para la API local."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import uuid

from codigo.app.schemas.api_memory import (
    MemoryBackendStatus,
    MemoryCandidateDecisionResponse,
    MemoryCandidateQueueItem,
    MemoryCandidateQueueResponse,
    MemoryCandidateQueueSummary,
    MemoryCurationResponse,
    MemoryCollectionSummary,
    MemoryCorpusStatus,
    MemoryGovernanceApplication,
    MemoryGovernanceEvent,
    MemoryGovernanceLedger,
    MemoryGovernanceOverride,
    MemoryRecordSummary,
    MemoryScientificReadiness,
    MemoryScientificReadinessBlocker,
    MemoryStatusResponse,
)
from codigo.app.schemas.reasoning import (
    AgentMemoryCollection,
    AgentMemoryTarget,
    MemoryCandidate,
    MemoryRole,
    ReasoningMemoryRecord,
)
from codigo.app.services.vector_memory import (
    COLLECTION_BY_AGENT,
    LocalJsonVectorMemoryStore,
    VectorMemoryStore,
    memory_record_from_candidate,
)

MEMORY_GOVERNANCE_DIRNAME = "governance"
MEMORY_GOVERNANCE_LEDGER_FILENAME = "memory_curation_overrides.json"


class DuplicateMemoryCandidateError(ValueError):
    """Indica que un ID ambiguo aparece en mas de un artefacto candidato."""


class UnsafeMemoryCandidatePathError(ValueError):
    """Indica que un candidato resuelve fuera del reports root permitido."""


@dataclass(frozen=True)
class MemoryCandidateArtifact:
    """Candidato validado junto con su procedencia segura e inmutable."""

    candidate: MemoryCandidate
    path: Path
    relative_path: str
    source_hash: str


def get_memory_status(
    memory_dir: Path | str,
    reports_root: Path | str,
    *,
    memory_store: VectorMemoryStore | None = None,
    configured_backend: str | None = None,
    backend_initialization_error: Exception | None = None,
) -> MemoryStatusResponse:
    """Comprueba backend, corpus y precondiciones sin modificar la memoria."""

    records: list[ReasoningMemoryRecord] = []
    store = memory_store
    backend_error = backend_initialization_error
    if store is None and backend_error is None:
        try:
            store = _resolve_memory_store(memory_dir, None)
        except Exception as exc:  # pragma: no cover - defensa para stores futuros
            backend_error = exc

    backend_name = _memory_backend_name(store, configured_backend)
    configured_name = configured_backend or _configured_backend_name(backend_name)
    embedding_model = _memory_embedding_identifier(store)
    if backend_error is None and store is not None:
        try:
            records = [
                ReasoningMemoryRecord.model_validate(record)
                for record in store.list_records()
            ]
        except Exception as exc:
            backend_error = exc

    backend_operational = backend_error is None and store is not None
    backend_status = MemoryBackendStatus(
        configured_backend=configured_name,
        backend_name=backend_name,
        operational=backend_operational,
        embedding_model=embedding_model,
        error_type=(None if backend_error is None else type(backend_error).__name__),
        diagnostic=(None if backend_error is None else _safe_diagnostic(backend_error)),
    )

    governance_ledger: MemoryGovernanceLedger | None = None
    try:
        governance_ledger = load_memory_governance_ledger(memory_dir)
    except Exception:
        # La misma corrupcion queda expuesta al cargar la cola; el endpoint de
        # estado no debe ocultarla ni convertirla en un 500.
        governance_ledger = None

    candidate_queue_error: Exception | None = None
    pending_candidates = 0
    try:
        candidate_queue = list_memory_candidate_queue(reports_root, memory_dir)
        pending_candidates = candidate_queue.summary.n_pending
    except Exception as exc:
        candidate_queue_error = exc

    reusable_records = [
        record
        for record in records
        if record.reusable_as_context and not record.exclude_from_context
    ]
    reusable_datasets = sorted(
        {record.dataset for record in reusable_records if record.dataset}
    )
    reusable_agents = sorted(
        {
            record.target_agent
            for record in reusable_records
            if record.target_agent != "shared_methodology"
        }
    )
    corpus_fingerprint = (
        _corpus_fingerprint(records, governance_ledger)
        if backend_operational and governance_ledger is not None
        else None
    )
    corpus_status = MemoryCorpusStatus(
        available=backend_operational,
        total_records=len(records),
        reusable_records=len(reusable_records),
        official_records=sum(
            record.data_provenance == "official" for record in records
        ),
        official_reusable_records=sum(
            record.data_provenance == "official" for record in reusable_records
        ),
        shared_methodology_records=sum(
            record.target_agent == "shared_methodology" for record in records
        ),
        shared_methodology_reusable_records=sum(
            record.target_agent == "shared_methodology"
            for record in reusable_records
        ),
        corpus_fingerprint=corpus_fingerprint,
        frozen_manifest_available=False,
        reusable_dataset_coverage=reusable_datasets,
        reusable_agent_coverage=reusable_agents,
        n_reusable_datasets=len(reusable_datasets),
        n_reusable_agents=len(reusable_agents),
        candidate_queue_available=candidate_queue_error is None,
        pending_candidates=pending_candidates,
        candidate_queue_error_type=(
            None
            if candidate_queue_error is None
            else type(candidate_queue_error).__name__
        ),
        candidate_queue_diagnostic=(
            None
            if candidate_queue_error is None
            else _safe_diagnostic(candidate_queue_error)
        ),
    )
    blockers = _memory_readiness_blockers(backend_status, corpus_status)
    return MemoryStatusResponse(
        backend=backend_status,
        corpus=corpus_status,
        scientific_readiness=MemoryScientificReadiness(
            ready_for_memory_effect_benchmark=not blockers,
            blockers=blockers,
        ),
    )


def list_memory_collections(
    memory_dir: Path | str,
    *,
    memory_store: VectorMemoryStore | None = None,
) -> list[MemoryCollectionSummary]:
    """Resume las colecciones canonicas de memoria persistida."""

    store = _resolve_memory_store(memory_dir, memory_store)
    records = store.list_records()
    records_by_collection: dict[str, list[ReasoningMemoryRecord]] = {}
    for record in records:
        records_by_collection.setdefault(record.collection_name, []).append(record)

    summaries: list[MemoryCollectionSummary] = []
    for target_agent, collection_name in COLLECTION_BY_AGENT.items():
        collection_records = records_by_collection.get(collection_name, [])
        summaries.append(_collection_summary(target_agent, collection_name, collection_records))
    return summaries


def list_memory_records(
    memory_dir: Path | str,
    *,
    collection_name: AgentMemoryCollection | None = None,
    target_agent: AgentMemoryTarget | None = None,
    dataset: str | None = None,
    memory_role: MemoryRole | None = None,
    reusable_only: bool = False,
    search_text: str | None = None,
    memory_store: VectorMemoryStore | None = None,
) -> list[MemoryRecordSummary]:
    """Lista recuerdos filtrados sin recalcular ni reindexar memoria."""

    store = _resolve_memory_store(memory_dir, memory_store)
    records = store.list_records(collection_name=collection_name)
    filtered = [
        record
        for record in records
        if _matches_filters(
            record,
            target_agent=target_agent,
            dataset=dataset,
            memory_role=memory_role,
            reusable_only=reusable_only,
            search_text=search_text,
        )
    ]
    filtered.sort(key=lambda record: (record.created_at, record.memory_record_id), reverse=True)
    return [_record_summary(record) for record in filtered]


def get_memory_record(
    memory_dir: Path | str,
    memory_record_id: str,
    *,
    memory_store: VectorMemoryStore | None = None,
) -> ReasoningMemoryRecord:
    """Devuelve un recuerdo completo por identificador."""

    store = _resolve_memory_store(memory_dir, memory_store)
    for record in store.list_records():
        if record.memory_record_id == memory_record_id:
            return record
    raise FileNotFoundError(f"memory record not found: {memory_record_id}")


def load_memory_candidate_artifacts(
    reports_root: Path | str,
) -> list[MemoryCandidateArtifact]:
    """Descubre candidatos bajo un root fijo y rechaza rutas o IDs ambiguos."""

    root = Path(reports_root)
    resolved_root = root.resolve()
    if not root.exists():
        return []
    artifacts: list[MemoryCandidateArtifact] = []
    paths_by_candidate_id: dict[str, str] = {}
    for candidate_path in sorted(root.rglob("memory_candidate.json")):
        resolved_path = candidate_path.resolve()
        try:
            relative_path = resolved_path.relative_to(resolved_root).as_posix()
        except ValueError as exc:
            raise UnsafeMemoryCandidatePathError(
                "memory candidate resolves outside configured reports_root: "
                f"{candidate_path.as_posix()}"
            ) from exc
        source_bytes = resolved_path.read_bytes()
        candidate = MemoryCandidate.model_validate_json(source_bytes)
        previous_path = paths_by_candidate_id.get(candidate.candidate_id)
        if previous_path is not None:
            raise DuplicateMemoryCandidateError(
                "duplicate memory candidate_id found in reports_root: "
                f"{candidate.candidate_id} ({previous_path}, {relative_path})"
            )
        paths_by_candidate_id[candidate.candidate_id] = relative_path
        artifacts.append(
            MemoryCandidateArtifact(
                candidate=candidate,
                path=resolved_path,
                relative_path=relative_path,
                source_hash=hashlib.sha256(source_bytes).hexdigest(),
            )
        )
    return artifacts


def list_memory_candidate_queue(
    reports_root: Path | str,
    memory_dir: Path | str,
) -> MemoryCandidateQueueResponse:
    """Lista el estado derivado de candidatos y del ledger de gobierno."""

    ledger = load_memory_governance_ledger(memory_dir)
    candidates = [
        _candidate_queue_item(artifact, ledger)
        for artifact in load_memory_candidate_artifacts(reports_root)
    ]
    candidates.sort(key=lambda item: (item.created_at, item.candidate_id), reverse=True)
    return MemoryCandidateQueueResponse(
        summary=MemoryCandidateQueueSummary(
            n_candidates=len(candidates),
            n_pending=sum(item.status == "pending" for item in candidates),
            n_promoted=sum(item.status == "promoted" for item in candidates),
            n_stale_promotions=sum(
                item.status == "stale_promotion" for item in candidates
            ),
            n_excluded=sum(item.status == "excluded" for item in candidates),
            n_deleted=sum(item.status == "deleted" for item in candidates),
            n_reusable=sum(item.status == "reusable" for item in candidates),
        ),
        candidates=candidates,
    )


def decide_memory_candidate(
    reports_root: Path | str,
    memory_dir: Path | str,
    candidate_id: str,
    *,
    action: str,
    reason: str,
    reviewer: str,
    memory_store: VectorMemoryStore | None = None,
) -> MemoryCandidateDecisionResponse:
    """Promueve o excluye un candidato mediante overlay, sin mutar su JSON."""

    if action not in {"promote", "exclude"}:
        raise ValueError(f"unsupported memory candidate action: {action}")
    if not reason.strip() or not reviewer.strip():
        raise ValueError("memory candidate decisions require reason and reviewer")
    artifacts = load_memory_candidate_artifacts(reports_root)
    artifact = next(
        (item for item in artifacts if item.candidate.candidate_id == candidate_id),
        None,
    )
    if artifact is None:
        raise FileNotFoundError(f"memory candidate not found: {candidate_id}")
    record = _record_from_candidate_artifact(artifact)
    if action == "promote" and record.memory_role == "excluded":
        raise ValueError("memory candidates with role=excluded cannot be promoted")

    store = _resolve_memory_store(memory_dir, memory_store)
    if action == "exclude":
        # Fail closed: desactiva tambien una promocion anterior antes de
        # persistir el evento, sin escribir sobre el artefacto fuente.
        stored = store.upsert(
            record.model_copy(
                update={
                    "reusable_as_context": False,
                    "exclude_from_context": True,
                    "tags": _curation_tags(
                        record.tags,
                        action="exclude",
                        reviewer=reviewer,
                    ),
                }
            )
        )
        event = append_memory_governance_event(
            memory_dir,
            record.memory_record_id,
            action=action,
            reason=reason,
            reviewer=reviewer,
        )
    else:
        # La autorizacion manual queda registrada antes de activar el recuerdo.
        event = append_memory_governance_event(
            memory_dir,
            record.memory_record_id,
            action=action,
            reason=reason,
            reviewer=reviewer,
            source_hash=artifact.source_hash,
        )
        governed, _ = apply_memory_governance_override(
            record,
            load_memory_governance_ledger(memory_dir),
        )
        if governed is None:  # pragma: no cover - el evento promote lo impide
            raise ValueError("promoted memory candidate cannot be tombstoned")
        stored = store.upsert(governed)

    item = _candidate_queue_item(
        artifact,
        load_memory_governance_ledger(memory_dir),
    )
    return MemoryCandidateDecisionResponse(
        candidate=item,
        action=action,  # type: ignore[arg-type]
        reason=reason,
        record=stored,
        governance_event=event,
    )


def curate_memory_record(
    memory_dir: Path | str,
    memory_record_id: str,
    *,
    action: str,
    reason: str,
    reviewer: str | None = None,
    memory_store: VectorMemoryStore | None = None,
) -> MemoryCurationResponse:
    """Excluye o restaura un recuerdo sin borrar su trazabilidad."""

    store = _resolve_memory_store(memory_dir, memory_store)
    record = get_memory_record(
        memory_dir,
        memory_record_id,
        memory_store=store,
    )
    tags = _curation_tags(record.tags, action=action, reviewer=reviewer)
    if action == "exclude":
        updated = record.model_copy(
            update={
                "reusable_as_context": False,
                "exclude_from_context": True,
                "tags": tags,
            }
        )
    elif action == "restore":
        if record.source_type in {"memory_candidate", "decision_episode"}:
            raise ValueError(
                "memory candidates must be activated through a source-bound promote decision"
            )
        if record.source_type == "memory_usage_audit":
            raise ValueError(
                "memory usage audits are observations and cannot become retrieval context"
            )
        if record.memory_role == "excluded":
            raise ValueError(
                "memory records with role=excluded cannot be restored without reindexing"
            )
        updated = record.model_copy(
            update={
                "reusable_as_context": True,
                "exclude_from_context": False,
                "tags": tags,
            }
        )
    else:
        raise ValueError(f"unsupported memory curation action: {action}")
    if action == "exclude":
        # Fail closed: aunque el ledger no pudiera escribirse, el indice vivo
        # deja de exponer el recuerdo durante esta operacion.
        stored = store.upsert(updated)
        governance_event = append_memory_governance_event(
            memory_dir,
            memory_record_id,
            action=action,
            reason=reason,
            reviewer=reviewer,
        )
    else:
        # Una restauracion solo se activa tras dejar primero evidencia canonica.
        governance_event = append_memory_governance_event(
            memory_dir,
            memory_record_id,
            action=action,
            reason=reason,
            reviewer=reviewer,
        )
        stored = store.upsert(updated)
    return MemoryCurationResponse(
        memory_record_id=stored.memory_record_id,
        action=action,  # type: ignore[arg-type]
        reason=reason,
        record=stored,
        governance_event=governance_event,
    )


def delete_memory_record(
    memory_dir: Path | str,
    memory_record_id: str,
    *,
    reason: str,
    reviewer: str | None = None,
    memory_store: VectorMemoryStore | None = None,
) -> MemoryCurationResponse:
    """Borra un recuerdo y persiste un tombstone contra resurrecciones."""

    store = _resolve_memory_store(memory_dir, memory_store)
    record = get_memory_record(memory_dir, memory_record_id, memory_store=store)
    safe_record = record.model_copy(
        update={
            "reusable_as_context": False,
            "exclude_from_context": True,
            "tags": _curation_tags(
                record.tags,
                action="exclude",
                reviewer=reviewer,
            ),
        }
    )
    store.upsert(safe_record)
    governance_event = append_memory_governance_event(
        memory_dir,
        memory_record_id,
        action="delete",
        reason=reason,
        reviewer=reviewer,
    )
    deleted = store.delete(memory_record_id)
    return MemoryCurationResponse(
        memory_record_id=deleted.memory_record_id,
        action="delete",
        reason=reason,
        record=deleted,
        governance_event=governance_event,
    )


def memory_governance_ledger_path(memory_dir: Path | str) -> Path:
    """Devuelve la ruta fija del overlay sin interpolar IDs de usuario."""

    return (
        Path(memory_dir)
        / MEMORY_GOVERNANCE_DIRNAME
        / MEMORY_GOVERNANCE_LEDGER_FILENAME
    )


def load_memory_governance_ledger(
    memory_dir: Path | str,
) -> MemoryGovernanceLedger:
    """Carga el ledger; un indice historico sin overlay equivale a ledger vacio."""

    path = memory_governance_ledger_path(memory_dir)
    if not path.exists():
        return MemoryGovernanceLedger()
    return MemoryGovernanceLedger.model_validate_json(path.read_text(encoding="utf-8"))


def append_memory_governance_event(
    memory_dir: Path | str,
    memory_record_id: str,
    *,
    action: str,
    reason: str | None,
    reviewer: str | None,
    source_hash: str | None = None,
) -> MemoryGovernanceEvent:
    """Anade un evento atomico y conserva todo el historial del recuerdo."""

    if action not in {"exclude", "restore", "delete", "promote"}:
        raise ValueError(f"unsupported memory governance action: {action}")
    if action == "promote" and (
        reason is None
        or not reason.strip()
        or reviewer is None
        or not reviewer.strip()
    ):
        raise ValueError("manual promotion requires reason and reviewer")
    if action == "promote" and source_hash is None:
        raise ValueError("manual promotion requires the candidate source_hash")
    event = MemoryGovernanceEvent(
        event_id=f"memory-governance-{uuid.uuid4().hex}",
        memory_record_id=memory_record_id,
        action=action,  # type: ignore[arg-type]
        reason=reason,
        reviewer=reviewer,
        source_hash=source_hash,
    )
    ledger = load_memory_governance_ledger(memory_dir)
    overrides_by_id = {
        override.memory_record_id: override
        for override in ledger.overrides
    }
    previous = overrides_by_id.get(memory_record_id)
    history = [] if previous is None else [*previous.history]
    history.append(event)
    overrides_by_id[memory_record_id] = MemoryGovernanceOverride(
        memory_record_id=memory_record_id,
        current_action=event.action,
        updated_at=event.occurred_at,
        history=history,
    )
    updated_ledger = ledger.model_copy(
        update={
            "overrides": [
                overrides_by_id[key]
                for key in sorted(overrides_by_id)
            ]
        }
    )
    _write_memory_governance_ledger(memory_dir, updated_ledger)
    return event


def apply_memory_governance_override(
    record: ReasoningMemoryRecord,
    ledger: MemoryGovernanceLedger,
) -> tuple[ReasoningMemoryRecord | None, MemoryGovernanceApplication | None]:
    """Aplica el estado manual vigente antes de decidir omision o upsert."""

    override = next(
        (
            item
            for item in ledger.overrides
            if item.memory_record_id == record.memory_record_id
        ),
        None,
    )
    if override is None:
        return record, None
    latest_event = override.history[-1]
    if override.current_action == "delete":
        return None, _governance_application(latest_event, effect="tombstoned")
    if override.current_action == "exclude":
        updated = record.model_copy(
            update={
                "reusable_as_context": False,
                "exclude_from_context": True,
                "tags": _curation_tags(
                    record.tags,
                    action="exclude",
                    reviewer=latest_event.reviewer,
                ),
            }
        )
        return updated, _governance_application(latest_event, effect="excluded")
    if override.current_action == "promote" and (
        latest_event.source_hash is None
        or record.source_hash != latest_event.source_hash
    ):
        updated = record.model_copy(
            update={
                "reusable_as_context": False,
                "exclude_from_context": True,
                "tags": sorted(
                    dict.fromkeys(
                        [
                            *record.tags,
                            "manual_curation",
                            "manual_promote_source_hash_mismatch",
                        ]
                    )
                ),
            }
        )
        return updated, _governance_application(
            latest_event,
            effect="source_hash_mismatch",
        )
    if record.memory_role == "excluded":
        return record, _governance_application(
            latest_event,
            effect="restore_blocked_role_excluded",
        )
    action = "promote" if override.current_action == "promote" else "restore"
    updated = record.model_copy(
        update={
            "reusable_as_context": True,
            "exclude_from_context": False,
            "promotion_source_hash": (
                latest_event.source_hash
                if override.current_action == "promote"
                else record.promotion_source_hash
            ),
            "tags": _curation_tags(
                record.tags,
                action=action,
                reviewer=latest_event.reviewer,
            ),
        }
    )
    effect = "promoted" if override.current_action == "promote" else "restored"
    return updated, _governance_application(latest_event, effect=effect)


def _write_memory_governance_ledger(
    memory_dir: Path | str,
    ledger: MemoryGovernanceLedger,
) -> None:
    path = memory_governance_ledger_path(memory_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(
        json.dumps(ledger.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    tmp_path.replace(path)


def _governance_application(
    event: MemoryGovernanceEvent,
    *,
    effect: str,
) -> MemoryGovernanceApplication:
    return MemoryGovernanceApplication(
        memory_record_id=event.memory_record_id,
        action=event.action,
        effect=effect,  # type: ignore[arg-type]
        event_id=event.event_id,
        occurred_at=event.occurred_at,
    )


def _resolve_memory_store(
    memory_dir: Path | str,
    memory_store: VectorMemoryStore | None,
) -> VectorMemoryStore:
    """Mantiene compatibilidad local y permite consultar el backend configurado."""

    return memory_store or LocalJsonVectorMemoryStore(memory_dir)


def _memory_backend_name(
    memory_store: VectorMemoryStore | None,
    configured_backend: str | None,
) -> str:
    if memory_store is not None:
        backend_name = getattr(memory_store, "backend_name", None)
        if isinstance(backend_name, str) and backend_name.strip():
            return backend_name.strip()
        return type(memory_store).__name__
    selector = (
        configured_backend
        or os.getenv("TFM_MEMORY_BACKEND", "json").strip().lower()
        or "json"
    )
    if selector in {"json", "local_json", "local"}:
        return "local_json_vector_memory_store"
    if selector == "qdrant":
        return "qdrant_vector_memory_store"
    if selector in {"pgvector", "pg_vector"}:
        return "pgvector_vector_memory_store"
    return selector


def _configured_backend_name(backend_name: str) -> str:
    normalized = backend_name.strip().lower()
    if "qdrant" in normalized:
        return "qdrant"
    if "pgvector" in normalized or "pg_vector" in normalized:
        return "pgvector"
    if "json" in normalized:
        return "json"
    return normalized


def _memory_embedding_identifier(
    memory_store: VectorMemoryStore | None,
) -> str | None:
    provider = getattr(memory_store, "embedding_model", None)
    identifier = getattr(provider, "identifier", None)
    return identifier if isinstance(identifier, str) and identifier.strip() else None


def _safe_diagnostic(error: Exception) -> str:
    message = str(error).strip() or "memory status probe failed"
    return message[:500]


def _corpus_fingerprint(
    records: list[ReasoningMemoryRecord],
    ledger: MemoryGovernanceLedger,
) -> str:
    """Firma semantica estable, independiente del backend vectorial concreto."""

    record_entries: list[dict[str, object]] = []
    for record in sorted(records, key=lambda item: item.memory_record_id):
        semantic_payload = record.model_dump(
            mode="json",
            exclude={
                "embedding_model",
                "embedding_version",
                "embedding_dimension",
                "vector_id",
            },
        )
        semantic_hash = hashlib.sha256(
            json.dumps(
                semantic_payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        record_entries.append(
            {
                "memory_record_id": record.memory_record_id,
                "source_hash": record.source_hash,
                "promotion_source_hash": record.promotion_source_hash,
                "semantic_hash": semantic_hash,
                "reusable_as_context": record.reusable_as_context,
                "exclude_from_context": record.exclude_from_context,
            }
        )
    governance_entries = [
        {
            "memory_record_id": override.memory_record_id,
            "current_action": override.current_action,
            "latest_event_id": override.history[-1].event_id,
            "latest_source_hash": override.history[-1].source_hash,
        }
        for override in sorted(
            ledger.overrides,
            key=lambda item: item.memory_record_id,
        )
    ]
    canonical = json.dumps(
        {
            "records": record_entries,
            "governance": governance_entries,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _memory_readiness_blockers(
    backend: MemoryBackendStatus,
    corpus: MemoryCorpusStatus,
) -> list[MemoryScientificReadinessBlocker]:
    blockers: list[MemoryScientificReadinessBlocker] = []
    if not backend.operational:
        blockers.append(
            MemoryScientificReadinessBlocker(
                code="backend_unavailable",
                message=(
                    "El backend configurado no supera una lectura real; "
                    "el contenido del corpus no puede auditarse."
                ),
            )
        )
    else:
        if corpus.total_records == 0:
            blockers.append(
                MemoryScientificReadinessBlocker(
                    code="empty_corpus",
                    message="El corpus de memoria esta vacio.",
                )
            )
        if corpus.reusable_records == 0:
            blockers.append(
                MemoryScientificReadinessBlocker(
                    code="no_reusable_memory",
                    message=(
                        "No hay recuerdos aprobados que puedan entrar en el contexto RAG."
                    ),
                )
            )
        if corpus.official_reusable_records == 0:
            blockers.append(
                MemoryScientificReadinessBlocker(
                    code="no_official_provenance",
                    message=(
                        "No hay memoria reutilizable con procedencia oficial; "
                        "cambiar de motor vectorial no corrige esta carencia."
                    ),
                )
            )
        if corpus.n_reusable_datasets < 2:
            blockers.append(
                MemoryScientificReadinessBlocker(
                    code="insufficient_dataset_coverage",
                    message=(
                        "La memoria reutilizable debe cubrir al menos dos datasets "
                        "para evaluar transferencia y evitar sobreajuste al caso principal."
                    ),
                )
            )
        if corpus.n_reusable_agents < 2:
            blockers.append(
                MemoryScientificReadinessBlocker(
                    code="insufficient_agent_coverage",
                    message=(
                        "La memoria reutilizable debe cubrir al menos dos agentes de decision."
                    ),
                )
            )
    if not corpus.candidate_queue_available:
        blockers.append(
            MemoryScientificReadinessBlocker(
                code="candidate_queue_unavailable",
                message=(
                    "La cola de candidatos no puede auditarse; no es seguro asumir "
                    "que el corpus gobernado esta completo."
                ),
            )
        )
    elif corpus.pending_candidates:
        blockers.append(
            MemoryScientificReadinessBlocker(
                code="pending_candidates",
                message=(
                    f"Quedan {corpus.pending_candidates} candidatos pendientes de "
                    "revision o promocion."
                ),
            )
        )
    if not corpus.frozen_manifest_available:
        blockers.append(
            MemoryScientificReadinessBlocker(
                code="frozen_manifest_unavailable",
                message=(
                    "Existe una huella viva del corpus, pero aun no hay un manifiesto "
                    "congelado que fije el grupo experimental."
                ),
            )
        )
    return blockers


def _record_from_candidate_artifact(
    artifact: MemoryCandidateArtifact,
) -> ReasoningMemoryRecord:
    return memory_record_from_candidate(
        artifact.candidate,
        source_path=artifact.path.as_posix(),
        source_hash=artifact.source_hash,
    )


def _candidate_queue_item(
    artifact: MemoryCandidateArtifact,
    ledger: MemoryGovernanceLedger,
) -> MemoryCandidateQueueItem:
    record = _record_from_candidate_artifact(artifact)
    override = next(
        (
            item
            for item in ledger.overrides
            if item.memory_record_id == record.memory_record_id
        ),
        None,
    )
    current_action = None if override is None else override.current_action
    governed_record, governance_application = apply_memory_governance_override(
        record,
        ledger,
    )
    if (
        governance_application is not None
        and governance_application.effect == "source_hash_mismatch"
    ):
        queue_status = "stale_promotion"
    elif current_action == "delete" or governed_record is None:
        queue_status = "deleted"
    elif (
        governance_application is not None
        and governance_application.effect
        in {"excluded", "restore_blocked_role_excluded"}
    ):
        queue_status = "excluded"
    elif current_action == "promote" and governed_record.reusable_as_context:
        queue_status = "promoted"
    elif current_action == "restore" and governed_record.reusable_as_context:
        queue_status = "reusable"
    else:
        queue_status = "pending"
    return MemoryCandidateQueueItem(
        candidate_id=artifact.candidate.candidate_id,
        memory_record_id=record.memory_record_id,
        target_agent=record.target_agent,
        dataset=record.dataset,
        data_provenance=record.data_provenance,
        memory_role=record.memory_role,
        human_verdict=record.human_verdict,
        status=queue_status,  # type: ignore[arg-type]
        current_governance_action=current_action,
        summary=record.summary,
        source_path=artifact.relative_path,
        created_at=artifact.candidate.created_at,
    )


def _collection_summary(
    target_agent: AgentMemoryTarget,
    collection_name: AgentMemoryCollection,
    records: list[ReasoningMemoryRecord],
) -> MemoryCollectionSummary:
    datasets = sorted({record.dataset for record in records if record.dataset})
    roles = Counter(record.memory_role for record in records)
    source_types = Counter(record.source_type for record in records)
    verdicts = Counter(
        record.human_verdict
        for record in records
        if record.human_verdict is not None
    )
    latest = max((record.created_at for record in records), default=None)
    return MemoryCollectionSummary(
        collection_name=collection_name,
        target_agent=target_agent,
        n_records=len(records),
        n_reusable=sum(record.reusable_as_context for record in records),
        n_excluded=sum(record.exclude_from_context for record in records),
        datasets=datasets,
        memory_roles=dict(sorted(roles.items())),
        source_types=dict(sorted(source_types.items())),
        human_verdicts=dict(sorted(verdicts.items())),
        latest_created_at=latest,
    )


def _matches_filters(
    record: ReasoningMemoryRecord,
    *,
    target_agent: AgentMemoryTarget | None,
    dataset: str | None,
    memory_role: MemoryRole | None,
    reusable_only: bool,
    search_text: str | None,
) -> bool:
    if target_agent is not None and record.target_agent != target_agent:
        return False
    if dataset is not None and record.dataset != dataset:
        return False
    if memory_role is not None and record.memory_role != memory_role:
        return False
    if reusable_only and not record.reusable_as_context:
        return False
    if search_text and search_text.strip():
        haystack = "\n".join(
            [
                record.memory_record_id,
                record.summary,
                record.content,
                record.dataset or "",
                record.run_id or "",
                record.decision_id or "",
                " ".join(record.tags),
            ]
        ).lower()
        if search_text.strip().lower() not in haystack:
            return False
    return True


def _curation_tags(
    tags: list[str],
    *,
    action: str,
    reviewer: str | None,
) -> list[str]:
    next_tags = [tag for tag in tags if not tag.startswith("manual_")]
    next_tags.extend(["manual_curation", f"manual_{action}"])
    if reviewer:
        safe_reviewer = "".join(
            char.lower() if char.isalnum() else "_"
            for char in reviewer.strip()
        ).strip("_")
        if safe_reviewer:
            next_tags.append(f"curated_by_{safe_reviewer[:40]}")
    return sorted(dict.fromkeys(next_tags))


def _record_summary(record: ReasoningMemoryRecord) -> MemoryRecordSummary:
    return MemoryRecordSummary(
        memory_record_id=record.memory_record_id,
        collection_name=record.collection_name,
        target_agent=record.target_agent,
        source_type=record.source_type,
        run_id=record.run_id,
        decision_id=record.decision_id,
        dataset=record.dataset,
        data_provenance=record.data_provenance,
        source_agent_name=record.source_agent_name,
        outcome=record.outcome,
        human_verdict=record.human_verdict,
        memory_role=record.memory_role,
        reusable_as_context=record.reusable_as_context,
        exclude_from_context=record.exclude_from_context,
        summary=record.summary,
        source_path=record.source_path,
        tags=record.tags,
        created_at=record.created_at,
    )
