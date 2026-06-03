"""Consulta de memoria agentica persistida para la API local."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

from codigo.app.schemas.api_memory import (
    MemoryCurationResponse,
    MemoryCollectionSummary,
    MemoryRecordSummary,
)
from codigo.app.schemas.reasoning import (
    AgentMemoryCollection,
    AgentMemoryTarget,
    MemoryRole,
    ReasoningMemoryRecord,
)
from codigo.app.services.vector_memory import (
    COLLECTION_BY_AGENT,
    LocalJsonVectorMemoryStore,
)


def list_memory_collections(
    memory_dir: Path | str,
) -> list[MemoryCollectionSummary]:
    """Resume las colecciones canonicas de memoria persistida."""

    store = LocalJsonVectorMemoryStore(memory_dir)
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
) -> list[MemoryRecordSummary]:
    """Lista recuerdos filtrados sin recalcular ni reindexar memoria."""

    store = LocalJsonVectorMemoryStore(memory_dir)
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
) -> ReasoningMemoryRecord:
    """Devuelve un recuerdo completo por identificador."""

    store = LocalJsonVectorMemoryStore(memory_dir)
    for record in store.list_records():
        if record.memory_record_id == memory_record_id:
            return record
    raise FileNotFoundError(f"memory record not found: {memory_record_id}")


def curate_memory_record(
    memory_dir: Path | str,
    memory_record_id: str,
    *,
    action: str,
    reason: str,
    reviewer: str | None = None,
) -> MemoryCurationResponse:
    """Excluye o restaura un recuerdo sin borrar su trazabilidad."""

    store = LocalJsonVectorMemoryStore(memory_dir)
    record = get_memory_record(memory_dir, memory_record_id)
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
    stored = store.upsert(updated)
    return MemoryCurationResponse(
        memory_record_id=stored.memory_record_id,
        action=action,  # type: ignore[arg-type]
        reason=reason,
        record=stored,
    )


def delete_memory_record(
    memory_dir: Path | str,
    memory_record_id: str,
    *,
    reason: str | None = None,
) -> MemoryCurationResponse:
    """Borra un recuerdo del indice local."""

    store = LocalJsonVectorMemoryStore(memory_dir)
    deleted = store.delete(memory_record_id)
    return MemoryCurationResponse(
        memory_record_id=deleted.memory_record_id,
        action="delete",
        reason=reason,
        record=deleted,
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
