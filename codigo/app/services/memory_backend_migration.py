"""Migracion y comparacion de backends de memoria vectorial."""

from __future__ import annotations

import json
import re
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from pydantic import Field, NonNegativeInt

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.reasoning import (
    AgentMemoryQuery,
    AgentMemoryTarget,
    ReasoningMemoryRecord,
)
from codigo.app.services.reasoning_memory_index import DEFAULT_MEMORY_DIR
from codigo.app.services.vector_memory import (
    DEFAULT_QDRANT_HOST,
    EmbeddingProvider,
    LocalJsonVectorMemoryStore,
    QdrantVectorMemoryStore,
    VectorMemoryStore,
    get_default_embedding_provider,
)


class MemoryBackendQueryComparison(StrictBaseModel):
    """Comparacion de una consulta entre dos backends de memoria."""

    query_id: str = Field(min_length=1)
    target_agent: AgentMemoryTarget
    dataset: str | None = None
    query_text: str = Field(min_length=1)
    source_backend: str = Field(min_length=1)
    target_backend: str = Field(min_length=1)
    source_record_ids: list[str] = Field(default_factory=list)
    target_record_ids: list[str] = Field(default_factory=list)
    overlap_count: NonNegativeInt
    overlap_ratio: float = Field(ge=0.0, le=1.0)
    exact_order_match: bool
    missing_in_target: list[str] = Field(default_factory=list)
    extra_in_target: list[str] = Field(default_factory=list)
    similarity_delta_by_record_id: dict[str, float] = Field(default_factory=dict)


class MemoryBackendComparisonReport(StrictBaseModel):
    """Informe agregado de equivalencia aproximada entre backends."""

    report_id: str = Field(min_length=1)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_backend: str = Field(min_length=1)
    target_backend: str = Field(min_length=1)
    query_count: NonNegativeInt
    exact_match_count: NonNegativeInt
    average_overlap_ratio: float = Field(ge=0.0, le=1.0)
    comparisons: list[MemoryBackendQueryComparison] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class MemoryBackendMigrationReport(StrictBaseModel):
    """Resultado trazable de una migracion entre stores vectoriales."""

    report_id: str = Field(min_length=1)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_backend: str = Field(min_length=1)
    target_backend: str = Field(min_length=1)
    source_memory_dir: str | None = None
    target_host: str | None = None
    embedding_model: str | None = None
    clear_existing: bool
    migrated_record_count: NonNegativeInt
    collection_counts: dict[str, int] = Field(default_factory=dict)
    migrated_record_ids: list[str] = Field(default_factory=list)
    comparison: MemoryBackendComparisonReport | None = None


class MemoryBackendMigrationArtifacts(StrictBaseModel):
    """Artefactos escritos para una migracion de memoria."""

    migration_path: str
    report_path: str
    report: MemoryBackendMigrationReport


def migrate_memory_records_between_stores(
    *,
    source_store: VectorMemoryStore,
    target_store: VectorMemoryStore,
    comparison_source_store: VectorMemoryStore | None = None,
    clear_existing: bool = True,
    verification_queries: list[AgentMemoryQuery] | None = None,
    source_memory_dir: str | Path | None = None,
    target_host: str | None = None,
) -> MemoryBackendMigrationReport:
    """Copia recuerdos de un store a otro y compara retrieval si hay queries."""

    records = source_store.list_records()
    migrated = target_store.rebuild(records, clear_existing=clear_existing)
    effective_source_store = comparison_source_store or source_store
    if comparison_source_store is not None:
        comparison_source_store.rebuild(records, clear_existing=True)
    queries = (
        verification_queries
        if verification_queries is not None
        else build_memory_migration_verification_queries(migrated)
    )
    comparison = (
        compare_memory_backends(
            source_store=effective_source_store,
            target_store=target_store,
            queries=queries,
        )
        if queries
        else None
    )
    return MemoryBackendMigrationReport(
        report_id=(
            "memory_backend_migration:"
            f"{_backend_name(source_store)}:to:{_backend_name(target_store)}"
        ),
        source_backend=_backend_name(source_store),
        target_backend=_backend_name(target_store),
        source_memory_dir=(
            None if source_memory_dir is None else Path(source_memory_dir).as_posix()
        ),
        target_host=target_host,
        embedding_model=_embedding_identifier(target_store),
        clear_existing=clear_existing,
        migrated_record_count=len(migrated),
        collection_counts=dict(
            sorted(Counter(record.collection_name for record in migrated).items())
        ),
        migrated_record_ids=[
            record.memory_record_id
            for record in sorted(migrated, key=lambda item: item.memory_record_id)
        ],
        comparison=comparison,
    )


def migrate_local_json_memory_to_qdrant(
    *,
    memory_dir: str | Path = DEFAULT_MEMORY_DIR,
    qdrant_host: str = DEFAULT_QDRANT_HOST,
    qdrant_api_key: str | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    clear_existing: bool = True,
    qdrant_timeout_seconds: float = 10.0,
    qdrant_distance: str = "Cosine",
    verification_queries: list[AgentMemoryQuery] | None = None,
    output_dir: str | Path | None = None,
) -> MemoryBackendMigrationArtifacts:
    """Migra la memoria JSON local a Qdrant y escribe un informe."""

    provider = embedding_provider or get_default_embedding_provider()
    source_store = LocalJsonVectorMemoryStore(memory_dir, embedding_model=provider)
    target_store = QdrantVectorMemoryStore(
        host=qdrant_host,
        api_key=qdrant_api_key,
        embedding_model=provider,
        timeout_seconds=qdrant_timeout_seconds,
        distance=qdrant_distance,
    )
    with tempfile.TemporaryDirectory() as tmp:
        comparison_source_store = LocalJsonVectorMemoryStore(
            Path(tmp) / "comparison_source",
            embedding_model=provider,
        )
        report = migrate_memory_records_between_stores(
            source_store=source_store,
            target_store=target_store,
            comparison_source_store=comparison_source_store,
            clear_existing=clear_existing,
            verification_queries=verification_queries,
            source_memory_dir=memory_dir,
            target_host=qdrant_host,
        )
    target_dir = (
        Path(output_dir)
        if output_dir is not None
        else Path("codigo/reports")
        / "memory_backend_migrations"
        / _safe_report_dir_name(report.report_id)
    )
    return write_memory_backend_migration_report(report, target_dir)


def compare_memory_backends(
    *,
    source_store: VectorMemoryStore,
    target_store: VectorMemoryStore,
    queries: list[AgentMemoryQuery],
) -> MemoryBackendComparisonReport:
    """Compara IDs recuperados por dos backends ante las mismas consultas."""

    comparisons: list[MemoryBackendQueryComparison] = []
    for query in queries:
        source_context = source_store.query(query)
        target_context = target_store.query(query)
        source_ids = [item.record.memory_record_id for item in source_context.items]
        target_ids = [item.record.memory_record_id for item in target_context.items]
        source_id_set = set(source_ids)
        target_id_set = set(target_ids)
        overlap = source_id_set & target_id_set
        overlap_ratio = 1.0 if not source_ids and not target_ids else (
            len(overlap) / max(len(source_id_set), 1)
        )
        source_similarity = {
            item.record.memory_record_id: item.similarity
            for item in source_context.items
        }
        target_similarity = {
            item.record.memory_record_id: item.similarity
            for item in target_context.items
        }
        comparisons.append(
            MemoryBackendQueryComparison(
                query_id=query.query_id,
                target_agent=query.target_agent,
                dataset=query.dataset,
                query_text=query.query_text,
                source_backend=source_context.retrieval_backend
                or _backend_name(source_store),
                target_backend=target_context.retrieval_backend
                or _backend_name(target_store),
                source_record_ids=source_ids,
                target_record_ids=target_ids,
                overlap_count=len(overlap),
                overlap_ratio=round(overlap_ratio, 6),
                exact_order_match=source_ids == target_ids,
                missing_in_target=[
                    record_id
                    for record_id in source_ids
                    if record_id not in target_id_set
                ],
                extra_in_target=[
                    record_id
                    for record_id in target_ids
                    if record_id not in source_id_set
                ],
                similarity_delta_by_record_id={
                    record_id: round(
                        target_similarity[record_id] - source_similarity[record_id],
                        6,
                    )
                    for record_id in sorted(overlap)
                },
            )
        )
    exact_match_count = sum(item.exact_order_match for item in comparisons)
    average_overlap = (
        sum(item.overlap_ratio for item in comparisons) / len(comparisons)
        if comparisons
        else 1.0
    )
    return MemoryBackendComparisonReport(
        report_id=(
            "memory_backend_comparison:"
            f"{_backend_name(source_store)}:vs:{_backend_name(target_store)}"
        ),
        source_backend=_backend_name(source_store),
        target_backend=_backend_name(target_store),
        query_count=len(comparisons),
        exact_match_count=exact_match_count,
        average_overlap_ratio=round(average_overlap, 6),
        comparisons=comparisons,
        limitations=[
            (
                "La comparacion mide solapamiento de IDs recuperados, no prueba "
                "equivalencia semantica completa ni mejora de rendimiento."
            ),
            (
                "Diferencias pequenas de score pueden aparecer por cambios de "
                "normalizacion, API de busqueda o configuracion de distancia."
            ),
        ],
    )


def build_memory_migration_verification_queries(
    records: list[ReasoningMemoryRecord],
    *,
    max_queries: int = 8,
    top_k: int = 5,
) -> list[AgentMemoryQuery]:
    """Genera consultas de smoke a partir de recuerdos migrados."""

    queries: list[AgentMemoryQuery] = []
    seen: set[tuple[str, str | None]] = set()
    candidates = [
        record
        for record in sorted(records, key=lambda item: item.memory_record_id)
        if record.reusable_as_context and not record.exclude_from_context
    ]
    for record in candidates:
        key = (record.target_agent, record.dataset)
        if key in seen:
            continue
        seen.add(key)
        queries.append(
            AgentMemoryQuery(
                query_id=(
                    "memory-migration-verification:"
                    f"{record.target_agent}:{len(queries) + 1}"
                ),
                target_agent=record.target_agent,
                query_text=_verification_query_text(record),
                dataset=record.dataset,
                top_k=top_k,
                min_similarity=0.0,
                decision_context={
                    "source_type": record.source_type,
                    "memory_role": record.memory_role,
                },
            )
        )
        if len(queries) >= max_queries:
            break
    return queries


def write_memory_backend_migration_report(
    report: MemoryBackendMigrationReport,
    output_dir: str | Path,
) -> MemoryBackendMigrationArtifacts:
    """Escribe el informe JSON y Markdown de una migracion."""

    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    migration_path = target_dir / "memory_backend_migration.json"
    report_path = target_dir / "memory_backend_migration.md"
    migration_path.write_text(
        json.dumps(report.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    report_path.write_text(_migration_markdown(report), encoding="utf-8")
    return MemoryBackendMigrationArtifacts(
        migration_path=migration_path.as_posix(),
        report_path=report_path.as_posix(),
        report=report,
    )


def _verification_query_text(record: ReasoningMemoryRecord) -> str:
    content = record.content.replace("\n", " ")
    text = f"{record.summary} {content}"
    return text[:600]


def _migration_markdown(report: MemoryBackendMigrationReport) -> str:
    lines = [
        "# Migracion de memoria vectorial",
        "",
        f"- Origen: `{report.source_backend}`",
        f"- Destino: `{report.target_backend}`",
        f"- Registros migrados: `{report.migrated_record_count}`",
        f"- Clear existing: `{report.clear_existing}`",
    ]
    if report.source_memory_dir:
        lines.append(f"- Directorio origen: `{report.source_memory_dir}`")
    if report.target_host:
        lines.append(f"- Host destino: `{report.target_host}`")
    if report.embedding_model:
        lines.append(f"- Embedding: `{report.embedding_model}`")
    lines.extend(["", "## Colecciones", ""])
    if report.collection_counts:
        for collection_name, count in sorted(report.collection_counts.items()):
            lines.append(f"- `{collection_name}`: {count}")
    else:
        lines.append("- Sin registros migrados.")
    if report.comparison is not None:
        lines.extend(
            [
                "",
                "## Comparacion de retrieval",
                "",
                f"- Queries: `{report.comparison.query_count}`",
                f"- Orden exacto: `{report.comparison.exact_match_count}`",
                (
                    "- Solapamiento medio: "
                    f"`{report.comparison.average_overlap_ratio:.3f}`"
                ),
                "",
            ]
        )
        for item in report.comparison.comparisons:
            lines.extend(
                [
                    f"### {item.query_id}",
                    "",
                    f"- Agente: `{item.target_agent}`",
                    f"- Dataset: `{item.dataset or 'n/a'}`",
                    f"- Source IDs: `{', '.join(item.source_record_ids) or 'none'}`",
                    f"- Target IDs: `{', '.join(item.target_record_ids) or 'none'}`",
                    f"- Solapamiento: `{item.overlap_ratio:.3f}`",
                    f"- Orden exacto: `{item.exact_order_match}`",
                    "",
                ]
            )
    lines.extend(
        [
            "## Limitaciones",
            "",
            (
                "- Este informe valida migracion y recuperacion aproximada; no "
                "demuestra por si solo mejora operacional de los agentes."
            ),
        ]
    )
    return "\n".join(lines) + "\n"


def _backend_name(store: VectorMemoryStore) -> str:
    value = getattr(store, "backend_name", None)
    if isinstance(value, str) and value:
        return value
    return store.__class__.__name__


def _embedding_identifier(store: VectorMemoryStore) -> str | None:
    provider = getattr(store, "embedding_model", None)
    identifier = getattr(provider, "identifier", None)
    return identifier if isinstance(identifier, str) else None


def _safe_report_dir_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return safe[:140] or "memory-backend-migration"
