"""Memoria vectorial local para recuerdos agenticos supervisados."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import uuid
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, Protocol, runtime_checkable

from pydantic import Field

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.dataset import DataProvenance
from codigo.app.schemas.reasoning import (
    AgentMemoryCollection,
    AgentMemoryQuery,
    AgentReasoningPostmortem,
    AgentMemoryTarget,
    DecisionEpisode,
    HumanReasoningReview,
    HumanReasoningVerdict,
    MemoryCandidate,
    MemoryRetrievalUse,
    MemoryRole,
    MemoryUsageAudit,
    ReasoningMemoryRecord,
    RetrievedMemoryContext,
    RetrievedMemoryItem,
)

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+")
DEFAULT_OLLAMA_EMBEDDING_MODEL = "qwen3-embedding:0.6b"
DEFAULT_VECTOR_MEMORY_DIR = Path("codigo/reports/reasoning_memory")
DEFAULT_QDRANT_HOST = "http://127.0.0.1:6333"

COLLECTION_BY_AGENT: dict[AgentMemoryTarget, AgentMemoryCollection] = {
    "cleaner": "cleaner_memory",
    "structurer": "structurer_memory",
    "modeler": "modeler_memory",
    "evaluator": "evaluator_memory",
    "report_writer": "report_writer_memory",
    "researcher": "researcher_memory",
    "shared_methodology": "shared_methodology_memory",
}

RETRIEVAL_USE_BY_ROLE: dict[MemoryRole, MemoryRetrievalUse] = {
    "positive_example": "positive_context",
    "negative_example": "negative_warning",
    "boundary_case": "boundary_context",
    "warning": "negative_warning",
    "methodology": "methodology_context",
    "evidence": "evidence_context",
    "excluded": "negative_warning",
}

QDRANT_MEMORY_PAYLOAD_INDEXES: tuple[tuple[str, str], ...] = (
    ("target_agent", "keyword"),
    ("dataset", "keyword"),
    ("data_provenance", "keyword"),
    ("source_type", "keyword"),
    ("memory_role", "keyword"),
    ("human_verdict", "keyword"),
    ("reusable_as_context", "bool"),
    ("exclude_from_context", "bool"),
    ("promotion_source_hash", "keyword"),
    ("record.embedding_model", "keyword"),
    ("record.embedding_version", "keyword"),
)


class LocalHashEmbeddingModel(StrictBaseModel):
    """Embedding local determinista, suficiente para un backend reproducible."""

    model_name: str = "local_hash_embedding"
    version: str = "v1"
    dimension: int = Field(default=128, ge=8)

    def embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimension
        for token in _tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return _normalize(vector)

    @property
    def identifier(self) -> str:
        return f"{self.model_name}:{self.version}"


class EmbeddingCallError(RuntimeError):
    """Error controlado durante la generacion de embeddings."""


class QdrantMemoryError(RuntimeError):
    """Error controlado durante llamadas al backend Qdrant."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class VectorMemoryConfigError(RuntimeError):
    """Error de configuracion del backend de memoria vectorial."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Interfaz comun para modelos que transforman texto en vectores."""

    @property
    def model_name(self) -> str:
        ...

    @property
    def version(self) -> str:
        ...

    @property
    def identifier(self) -> str:
        ...

    def embed(self, text: str) -> list[float]:
        ...


@dataclass(frozen=True)
class OllamaEmbeddingProvider:
    """Proveedor de embeddings reales mediante Ollama `/api/embed`."""

    model: str = DEFAULT_OLLAMA_EMBEDDING_MODEL
    host: str = "http://127.0.0.1:11434"
    timeout_seconds: float = 60.0

    @property
    def model_name(self) -> str:
        return self.model.split(":", maxsplit=1)[0]

    @property
    def version(self) -> str:
        parts = self.model.split(":", maxsplit=1)
        return parts[1] if len(parts) == 2 else "latest"

    @property
    def identifier(self) -> str:
        return f"ollama:{self.model}"

    def embed(self, text: str) -> list[float]:
        payload = {
            "model": self.model,
            "input": text,
        }
        request = urllib.request.Request(
            f"{self.host.rstrip('/')}/api/embed",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw_response = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise EmbeddingCallError(f"ollama embedding call failed: {exc}") from exc

        embeddings = raw_response.get("embeddings")
        if not isinstance(embeddings, list) or not embeddings:
            raise EmbeddingCallError("ollama response did not include embeddings")
        first = embeddings[0]
        if not isinstance(first, list) or not first:
            raise EmbeddingCallError("ollama response included an invalid embedding")
        try:
            return [float(value) for value in first]
        except (TypeError, ValueError) as exc:
            raise EmbeddingCallError("ollama embedding contains non-numeric values") from exc


class StoredMemoryVector(StrictBaseModel):
    """Entrada persistida: contrato de memoria mas vector asociado."""

    record: ReasoningMemoryRecord
    vector: list[float] = Field(min_length=1)


@runtime_checkable
class VectorMemoryStore(Protocol):
    """Interfaz minima para backends de memoria vectorial agentica."""

    def upsert(self, record: ReasoningMemoryRecord) -> ReasoningMemoryRecord:
        ...

    def rebuild(
        self,
        records: list[ReasoningMemoryRecord],
        *,
        clear_existing: bool = True,
    ) -> list[ReasoningMemoryRecord]:
        ...

    def list_records(
        self,
        collection_name: AgentMemoryCollection | None = None,
    ) -> list[ReasoningMemoryRecord]:
        ...

    def delete(self, memory_record_id: str) -> ReasoningMemoryRecord:
        ...

    def query(self, query: AgentMemoryQuery) -> RetrievedMemoryContext:
        ...


class LocalJsonVectorMemoryStore:
    """Backend vectorial local basado en JSON y similitud coseno."""

    backend_name = "local_json_vector_memory_store"

    def __init__(
        self,
        root_dir: str | Path,
        *,
        embedding_model: EmbeddingProvider | None = None,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.embedding_model = embedding_model or LocalHashEmbeddingModel()

    def upsert(self, record: ReasoningMemoryRecord) -> ReasoningMemoryRecord:
        vector = self.embedding_model.embed(_record_text(record))
        enriched = self._with_embedding_metadata(record, embedding_dimension=len(vector))
        entry = StoredMemoryVector(record=enriched, vector=vector)
        entries = self._load_entries(
            enriched.collection_name,
            expected_embedding_dimension=len(vector),
        )
        entries[enriched.memory_record_id] = entry
        self._write_entries(enriched.collection_name, entries)
        return enriched

    def rebuild(
        self,
        records: list[ReasoningMemoryRecord],
        *,
        clear_existing: bool = True,
    ) -> list[ReasoningMemoryRecord]:
        if clear_existing:
            for path in self.root_dir.glob("*.json"):
                path.unlink()
        return [self.upsert(record) for record in records]

    def list_records(
        self,
        collection_name: AgentMemoryCollection | None = None,
    ) -> list[ReasoningMemoryRecord]:
        if collection_name is not None:
            entries = self._load_entries(collection_name)
            return [entry.record for entry in _sorted_entries(entries)]
        records: list[ReasoningMemoryRecord] = []
        for collection in sorted(set(COLLECTION_BY_AGENT.values())):
            entries = self._load_entries(collection)
            records.extend(entry.record for entry in _sorted_entries(entries))
        return records

    def delete(self, memory_record_id: str) -> ReasoningMemoryRecord:
        """Elimina un recuerdo del indice local por identificador."""

        for collection_name in sorted(set(COLLECTION_BY_AGENT.values())):
            entries = self._load_entries(collection_name)
            entry = entries.pop(memory_record_id, None)
            if entry is None:
                continue
            self._write_entries(collection_name, entries)
            return entry.record
        raise FileNotFoundError(f"memory record not found: {memory_record_id}")

    def query(self, query: AgentMemoryQuery) -> RetrievedMemoryContext:
        query_vector = self.embedding_model.embed(_query_text(query))
        retrieved: list[RetrievedMemoryItem] = []
        for entry in self._candidate_entries(
            query,
            expected_embedding_dimension=len(query_vector),
        ):
            record = entry.record
            if not _record_matches_query(record, query):
                continue
            similarity = _cosine_similarity(query_vector, entry.vector)
            if similarity < query.min_similarity:
                continue
            retrieved.append(
                RetrievedMemoryItem(
                    record=record,
                    similarity=similarity,
                    retrieval_use=RETRIEVAL_USE_BY_ROLE[record.memory_role],
                    rank=1,
                )
            )
        retrieved.sort(
            key=lambda item: (-item.similarity, item.record.memory_record_id)
        )
        ranked = [
            item.model_copy(update={"rank": index})
            for index, item in enumerate(retrieved[: query.top_k], start=1)
        ]
        return RetrievedMemoryContext(
            context_id=f"{query.query_id}:retrieved_memory_context",
            query=query,
            items=ranked,
            retrieval_backend=self.backend_name,
            embedding_model=self.embedding_model.identifier,
        )

    def _candidate_entries(
        self,
        query: AgentMemoryQuery,
        *,
        expected_embedding_dimension: int,
    ) -> list[StoredMemoryVector]:
        collection_names = [COLLECTION_BY_AGENT[query.target_agent]]
        if query.target_agent != "shared_methodology":
            collection_names.append("shared_methodology_memory")
        entries: list[StoredMemoryVector] = []
        for collection_name in collection_names:
            entries.extend(
                _sorted_entries(
                    self._load_entries(
                        collection_name,
                        expected_embedding_dimension=expected_embedding_dimension,
                    )
                )
            )
        return entries

    def _with_embedding_metadata(
        self,
        record: ReasoningMemoryRecord,
        *,
        embedding_dimension: int,
    ) -> ReasoningMemoryRecord:
        vector_id = record.vector_id or f"{record.collection_name}:{record.memory_record_id}"
        return record.model_copy(
            update={
                "embedding_model": self.embedding_model.model_name,
                "embedding_version": self.embedding_model.version,
                "embedding_dimension": embedding_dimension,
                "vector_id": vector_id,
            }
        )

    def _collection_path(self, collection_name: AgentMemoryCollection | str) -> Path:
        return self.root_dir / f"{collection_name}.json"

    def _load_entries(
        self,
        collection_name: AgentMemoryCollection | str,
        *,
        expected_embedding_dimension: int | None = None,
    ) -> dict[str, StoredMemoryVector]:
        path = self._collection_path(collection_name)
        if not path.exists():
            return {}
        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = [
            StoredMemoryVector.model_validate(raw_entry)
            for raw_entry in payload.get("entries", [])
        ]
        _validate_local_embedding_compatibility(
            payload,
            entries,
            provider=self.embedding_model,
            expected_dimension=expected_embedding_dimension,
            collection_name=str(collection_name),
        )
        return {entry.record.memory_record_id: entry for entry in entries}

    def _write_entries(
        self,
        collection_name: AgentMemoryCollection | str,
        entries: dict[str, StoredMemoryVector],
    ) -> None:
        payload = {
            "backend": self.backend_name,
            "collection_name": collection_name,
            "embedding_model": _embedding_provider_metadata(self.embedding_model),
            "entries": [
                entry.model_dump(mode="json")
                for entry in _sorted_entries(entries)
            ],
        }
        path = self._collection_path(collection_name)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp_path.replace(path)


class QdrantVectorMemoryStore:
    """Backend Qdrant opcional compatible con `VectorMemoryStore`."""

    backend_name = "qdrant_vector_memory_store"

    def __init__(
        self,
        *,
        host: str = "http://127.0.0.1:6333",
        api_key: str | None = None,
        embedding_model: EmbeddingProvider | None = None,
        timeout_seconds: float = 10.0,
        distance: str = "Cosine",
    ) -> None:
        self.host = host.rstrip("/")
        self.api_key = api_key
        self.embedding_model = embedding_model or LocalHashEmbeddingModel()
        self.timeout_seconds = timeout_seconds
        self.distance = distance

    def upsert(self, record: ReasoningMemoryRecord) -> ReasoningMemoryRecord:
        vector = self.embedding_model.embed(_record_text(record))
        self._ensure_collection(record.collection_name, len(vector))
        enriched = self._with_embedding_metadata(record, embedding_dimension=len(vector))
        self._request_json(
            "PUT",
            f"/collections/{_url_part(enriched.collection_name)}/points?wait=true",
            {
                "points": [
                    {
                        "id": _qdrant_point_id(enriched.memory_record_id),
                        "vector": vector,
                        "payload": _qdrant_payload(enriched),
                    }
                ]
            },
        )
        return enriched

    def rebuild(
        self,
        records: list[ReasoningMemoryRecord],
        *,
        clear_existing: bool = True,
    ) -> list[ReasoningMemoryRecord]:
        if clear_existing:
            collection_names = {
                *COLLECTION_BY_AGENT.values(),
                *(record.collection_name for record in records),
            }
            for collection_name in sorted(collection_names):
                self._delete_collection_if_exists(collection_name)
        return [self.upsert(record) for record in records]

    def list_records(
        self,
        collection_name: AgentMemoryCollection | None = None,
    ) -> list[ReasoningMemoryRecord]:
        collection_names = (
            [collection_name]
            if collection_name is not None
            else sorted(set(COLLECTION_BY_AGENT.values()))
        )
        records: list[ReasoningMemoryRecord] = []
        for name in collection_names:
            records.extend(self._scroll_collection(name))
        records.sort(key=lambda record: (record.created_at, record.memory_record_id), reverse=True)
        return records

    def delete(self, memory_record_id: str) -> ReasoningMemoryRecord:
        point_id = _qdrant_point_id(memory_record_id)
        for collection_name in sorted(set(COLLECTION_BY_AGENT.values())):
            records = self._scroll_collection(collection_name)
            match = next(
                (
                    record
                    for record in records
                    if record.memory_record_id == memory_record_id
                ),
                None,
            )
            if match is None:
                continue
            self._request_json(
                "POST",
                f"/collections/{_url_part(collection_name)}/points/delete?wait=true",
                {"points": [point_id]},
            )
            return match
        raise FileNotFoundError(f"memory record not found: {memory_record_id}")

    def query(self, query: AgentMemoryQuery) -> RetrievedMemoryContext:
        query_vector = self.embedding_model.embed(_query_text(query))
        retrieved: list[RetrievedMemoryItem] = []
        for collection_name in self._candidate_collection_names(query):
            collection_info = self._collection_info(collection_name)
            if collection_info is None:
                continue
            _validate_qdrant_collection_compatibility(
                collection_info,
                collection_name=str(collection_name),
                expected_dimension=len(query_vector),
                expected_distance=self.distance,
            )
            query_payload = {
                "query": query_vector,
                "filter": _qdrant_query_filter(
                    query,
                    embedding_model=self.embedding_model.model_name,
                    embedding_version=self.embedding_model.version,
                ),
                "limit": max(query.top_k * 10, 20),
                "with_payload": True,
                "with_vector": False,
            }
            response = self._query_collection(collection_name, query_payload)
            if response is None:
                continue
            for raw_point in _qdrant_result_list(response):
                record = _record_from_qdrant_payload(raw_point.get("payload"))
                if (
                    record is None
                    or not _record_matches_query(record, query)
                    or not _record_embedding_matches_provider(
                        record,
                        self.embedding_model,
                        expected_dimension=len(query_vector),
                    )
                ):
                    continue
                similarity = _qdrant_similarity(raw_point.get("score"))
                if similarity < query.min_similarity:
                    continue
                retrieved.append(
                    RetrievedMemoryItem(
                        record=record,
                        similarity=similarity,
                        retrieval_use=RETRIEVAL_USE_BY_ROLE[record.memory_role],
                        rank=1,
                    )
                )
        retrieved.sort(
            key=lambda item: (-item.similarity, item.record.memory_record_id)
        )
        ranked = [
            item.model_copy(update={"rank": index})
            for index, item in enumerate(retrieved[: query.top_k], start=1)
        ]
        return RetrievedMemoryContext(
            context_id=f"{query.query_id}:retrieved_memory_context",
            query=query,
            items=ranked,
            retrieval_backend=self.backend_name,
            embedding_model=self.embedding_model.identifier,
        )

    def _candidate_collection_names(
        self,
        query: AgentMemoryQuery,
    ) -> list[AgentMemoryCollection]:
        collection_names = [COLLECTION_BY_AGENT[query.target_agent]]
        if query.target_agent != "shared_methodology":
            collection_names.append("shared_methodology_memory")
        return collection_names

    def _query_collection(
        self,
        collection_name: AgentMemoryCollection | str,
        query_payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        try:
            return self._request_json(
                "POST",
                f"/collections/{_url_part(collection_name)}/points/query",
                query_payload,
            )
        except QdrantMemoryError as exc:
            if exc.status_code == 404:
                return None
            if exc.status_code not in {400, 405}:
                raise

        legacy_payload = {
            **query_payload,
            "vector": query_payload["query"],
        }
        legacy_payload.pop("query", None)
        try:
            return self._request_json(
                "POST",
                f"/collections/{_url_part(collection_name)}/points/search",
                legacy_payload,
            )
        except QdrantMemoryError as exc:
            if exc.status_code == 404:
                return None
            raise

    def _scroll_collection(
        self,
        collection_name: AgentMemoryCollection | str,
    ) -> list[ReasoningMemoryRecord]:
        records: list[ReasoningMemoryRecord] = []
        offset: str | int | None = None
        while True:
            payload: dict[str, Any] = {
                "limit": 128,
                "with_payload": True,
                "with_vector": False,
            }
            if offset is not None:
                payload["offset"] = offset
            try:
                response = self._request_json(
                    "POST",
                    f"/collections/{_url_part(collection_name)}/points/scroll",
                    payload,
                )
            except QdrantMemoryError as exc:
                if exc.status_code == 404:
                    return []
                raise
            result = response.get("result") if isinstance(response, dict) else None
            if not isinstance(result, dict):
                return records
            raw_points = result.get("points", [])
            if not isinstance(raw_points, list):
                return records
            for raw_point in raw_points:
                if not isinstance(raw_point, dict):
                    continue
                record = _record_from_qdrant_payload(raw_point.get("payload"))
                if record is not None:
                    records.append(record)
            next_offset = result.get("next_page_offset")
            if next_offset in {None, offset}:
                return records
            offset = next_offset

    def _ensure_collection(
        self,
        collection_name: AgentMemoryCollection | str,
        vector_size: int,
    ) -> None:
        collection_info = self._collection_info(collection_name)
        if collection_info is None:
            self._request_json(
                "PUT",
                f"/collections/{_url_part(collection_name)}",
                {
                    "vectors": {
                        "size": vector_size,
                        "distance": self.distance,
                    }
                },
            )
            existing_payload_indexes: set[str] = set()
        else:
            _validate_qdrant_collection_compatibility(
                collection_info,
                collection_name=str(collection_name),
                expected_dimension=vector_size,
                expected_distance=self.distance,
            )
            existing_payload_indexes = _qdrant_payload_index_fields(collection_info)
        self._ensure_payload_indexes(
            collection_name,
            existing_payload_indexes=existing_payload_indexes,
        )

    def _collection_info(
        self,
        collection_name: AgentMemoryCollection | str,
    ) -> dict[str, Any] | None:
        try:
            return self._request_json(
                "GET",
                f"/collections/{_url_part(collection_name)}",
            )
        except QdrantMemoryError as exc:
            if exc.status_code == 404:
                return None
            raise

    def _ensure_payload_indexes(
        self,
        collection_name: AgentMemoryCollection | str,
        *,
        existing_payload_indexes: set[str],
    ) -> None:
        for field_name, field_schema in QDRANT_MEMORY_PAYLOAD_INDEXES:
            if field_name in existing_payload_indexes:
                continue
            self._request_json(
                "PUT",
                f"/collections/{_url_part(collection_name)}/index?wait=true",
                {
                    "field_name": field_name,
                    "field_schema": field_schema,
                },
            )
            existing_payload_indexes.add(field_name)

    def _delete_collection_if_exists(
        self,
        collection_name: AgentMemoryCollection | str,
    ) -> None:
        try:
            self._request_json("DELETE", f"/collections/{_url_part(collection_name)}")
        except QdrantMemoryError as exc:
            if exc.status_code != 404:
                raise

    def _with_embedding_metadata(
        self,
        record: ReasoningMemoryRecord,
        *,
        embedding_dimension: int,
    ) -> ReasoningMemoryRecord:
        vector_id = record.vector_id or f"{record.collection_name}:{record.memory_record_id}"
        return record.model_copy(
            update={
                "embedding_model": self.embedding_model.model_name,
                "embedding_version": self.embedding_model.version,
                "embedding_dimension": embedding_dimension,
                "vector_id": vector_id,
            }
        )

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["api-key"] = self.api_key
        request = urllib.request.Request(
            f"{self.host}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise QdrantMemoryError(
                f"qdrant call failed with HTTP {exc.code}: {exc.reason}",
                status_code=exc.code,
            ) from exc
        except (OSError, urllib.error.URLError) as exc:
            raise QdrantMemoryError(f"qdrant call failed: {exc}") from exc
        if not raw:
            return {}
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise QdrantMemoryError("qdrant response is not valid JSON") from exc
        if not isinstance(parsed, dict):
            raise QdrantMemoryError("qdrant response must be a JSON object")
        return parsed


def memory_record_from_postmortem(
    postmortem: AgentReasoningPostmortem,
    *,
    review: HumanReasoningReview | None = None,
    dataset: str | None = None,
    data_provenance: DataProvenance = "unknown",
    source_path: str | None = None,
    source_hash: str | None = None,
) -> ReasoningMemoryRecord:
    """Convierte un post-mortem auditado en memoria candidate reutilizable."""

    target_agent = _target_agent_from_name(postmortem.agent_name)
    role = _memory_role_from_postmortem(postmortem, review)
    reusable_as_context = False if review is None else review.reusable_as_context
    exclude_from_context = False if review is None else review.exclude_from_context
    return ReasoningMemoryRecord(
        memory_record_id=f"{postmortem.postmortem_id}:memory:{target_agent}",
        collection_name=collection_for_agent(target_agent),
        target_agent=target_agent,
        source_type="human_review" if review is not None else "reasoning_postmortem",
        source_path=source_path,
        source_hash=source_hash,
        run_id=postmortem.run_id,
        postmortem_id=postmortem.postmortem_id,
        decision_id=postmortem.decision_id,
        dataset=dataset,
        data_provenance=data_provenance,
        source_agent_name=postmortem.agent_name,
        outcome=postmortem.outcome,
        human_verdict=None if review is None else review.verdict,
        memory_role=role,
        reusable_as_context=reusable_as_context,
        exclude_from_context=exclude_from_context,
        summary=_memory_summary(postmortem, review),
        content=_memory_content(postmortem, review),
        metrics=postmortem.after_metrics,
        tags=_memory_tags(postmortem, review),
    )


def memory_record_from_memory_usage_audit(
    audit: MemoryUsageAudit,
    *,
    target_agent: AgentMemoryTarget,
    dataset: str | None = None,
    data_provenance: DataProvenance = "unknown",
    source_path: str | None = None,
    source_hash: str | None = None,
) -> ReasoningMemoryRecord:
    """Conserva una auditoria RAG como observacion no reutilizable.

    Una auditoria describe el uso de memoria, no valida por si misma una
    leccion. Mantenerla fuera del contexto evita bucles autorreferenciales.
    """

    role = _memory_role_from_usage_audit(audit)
    return ReasoningMemoryRecord(
        memory_record_id=f"{audit.audit_id}:memory:{target_agent}",
        collection_name=collection_for_agent(target_agent),
        target_agent=target_agent,
        source_type="memory_usage_audit",
        source_path=source_path,
        source_hash=source_hash,
        run_id=audit.run_id,
        decision_id=audit.decision_id,
        dataset=dataset,
        data_provenance=data_provenance,
        source_agent_name=target_agent,
        outcome=None,
        human_verdict=None,
        memory_role=role,
        reusable_as_context=False,
        exclude_from_context=role == "excluded",
        summary=_memory_usage_audit_summary(audit),
        content=_memory_usage_audit_content(audit),
        metrics=audit.after_metrics,
        tags=sorted(
            dict.fromkeys(
                [
                    *_memory_usage_audit_tags(audit, target_agent),
                    "non_reusable_memory_observation",
                ]
            )
        ),
    )


def memory_candidate_from_decision_episode(
    episode: DecisionEpisode,
    *,
    human_verdict: HumanReasoningVerdict | None = None,
    reusable_as_context: bool = False,
    exclude_from_context: bool = False,
    memory_role: MemoryRole | None = None,
) -> MemoryCandidate:
    """Destila un episodio de decision en una leccion candidata a memoria."""

    role = memory_role or _memory_role_from_episode(episode, human_verdict)
    resolved_reusable = reusable_as_context or (
        human_verdict == "correct" and not exclude_from_context
    )
    return MemoryCandidate(
        candidate_id=f"{episode.episode_id}:candidate:{episode.target_agent}",
        source_episode_id=episode.episode_id,
        target_agent=episode.target_agent,
        source_type="decision_episode",
        run_id=episode.run_id,
        decision_id=episode.decision_id,
        dataset=episode.dataset,
        data_provenance=episode.data_provenance,
        applicability=episode.applicability,
        source_agent_name=episode.agent_name,
        outcome=episode.outcome,
        human_verdict=human_verdict,
        memory_role=role,
        reusable_as_context=resolved_reusable,
        exclude_from_context=exclude_from_context,
        summary=_episode_candidate_summary(episode, human_verdict),
        content=_episode_candidate_content(episode),
        when_to_reuse=episode.when_to_reuse,
        when_not_to_reuse=episode.when_not_to_reuse,
        risk_if_misused=episode.risk_if_misused,
        metrics=episode.after_metrics,
        tags=_episode_candidate_tags(episode, human_verdict),
    )


def memory_record_from_candidate(
    candidate: MemoryCandidate,
    *,
    source_path: str | None = None,
    source_hash: str | None = None,
) -> ReasoningMemoryRecord:
    """Convierte una leccion destilada en registro vectorial persistible."""

    return ReasoningMemoryRecord(
        memory_record_id=f"{candidate.candidate_id}:memory:{candidate.target_agent}",
        collection_name=collection_for_agent(candidate.target_agent),
        target_agent=candidate.target_agent,
        source_type=candidate.source_type,
        source_path=source_path,
        source_hash=source_hash,
        run_id=candidate.run_id,
        decision_id=candidate.decision_id,
        dataset=candidate.dataset,
        data_provenance=candidate.data_provenance,
        applicability=candidate.applicability,
        source_agent_name=candidate.source_agent_name,
        outcome=candidate.outcome,
        human_verdict=candidate.human_verdict,
        memory_role=candidate.memory_role,
        reusable_as_context=candidate.reusable_as_context,
        exclude_from_context=candidate.exclude_from_context,
        summary=candidate.summary,
        content=_candidate_record_content(candidate),
        metrics=candidate.metrics,
        tags=_candidate_record_tags(candidate),
    )


def get_default_embedding_provider() -> EmbeddingProvider:
    """Crea el proveedor de embeddings configurado por variables de entorno."""

    provider = os.getenv("TFM_EMBEDDING_PROVIDER", "ollama").strip().lower()
    if provider == "local_hash":
        dimension = int(os.getenv("TFM_EMBEDDING_DIMENSION", "128"))
        return LocalHashEmbeddingModel(dimension=dimension)
    if provider != "ollama":
        raise EmbeddingCallError(f"unsupported TFM_EMBEDDING_PROVIDER: {provider}")

    model = os.getenv("TFM_EMBEDDING_MODEL", DEFAULT_OLLAMA_EMBEDDING_MODEL)
    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    timeout = float(os.getenv("TFM_EMBEDDING_TIMEOUT_SECONDS", "60"))
    return OllamaEmbeddingProvider(
        model=model,
        host=host,
        timeout_seconds=timeout,
    )


def get_default_vector_memory_store(
    root_dir: str | Path = DEFAULT_VECTOR_MEMORY_DIR,
    *,
    embedding_model: EmbeddingProvider | None = None,
) -> VectorMemoryStore:
    """Crea el backend de memoria configurado sin acoplar agentes al store."""

    backend = os.getenv("TFM_MEMORY_BACKEND", "json").strip().lower()
    provider = embedding_model or get_default_embedding_provider()
    if backend in {"json", "local_json", "local"}:
        return LocalJsonVectorMemoryStore(root_dir, embedding_model=provider)
    if backend == "qdrant":
        host = (
            os.getenv("TFM_QDRANT_HOST")
            or os.getenv("QDRANT_URL")
            or DEFAULT_QDRANT_HOST
        )
        api_key = os.getenv("TFM_QDRANT_API_KEY") or os.getenv("QDRANT_API_KEY")
        timeout = float(os.getenv("TFM_QDRANT_TIMEOUT_SECONDS", "10"))
        distance = os.getenv("TFM_QDRANT_DISTANCE", "Cosine")
        return QdrantVectorMemoryStore(
            host=host,
            api_key=api_key,
            embedding_model=provider,
            timeout_seconds=timeout,
            distance=distance,
        )
    raise VectorMemoryConfigError(f"unsupported TFM_MEMORY_BACKEND: {backend}")


def collection_for_agent(target_agent: AgentMemoryTarget) -> AgentMemoryCollection:
    """Devuelve la coleccion vectorial canonica de un agente."""

    return COLLECTION_BY_AGENT[target_agent]


def _target_agent_from_name(agent_name: str) -> AgentMemoryTarget:
    if agent_name in COLLECTION_BY_AGENT:
        return agent_name  # type: ignore[return-value]
    return "shared_methodology"


def _memory_role_from_postmortem(
    postmortem: AgentReasoningPostmortem,
    review: HumanReasoningReview | None,
) -> MemoryRole:
    if review is not None:
        if review.exclude_from_context:
            return "excluded"
        if review.verdict == "correct":
            return "positive_example"
        if review.verdict == "partially_correct":
            return "boundary_case"
        if review.verdict == "incorrect":
            return "negative_example"
        if review.verdict == "unsafe":
            return "warning"
        return "boundary_case"
    if postmortem.outcome == "validated":
        return "boundary_case"
    if postmortem.outcome == "overcorrected":
        return "boundary_case"
    if postmortem.outcome == "contradicted":
        return "negative_example"
    return "boundary_case"


def _memory_role_from_usage_audit(audit: MemoryUsageAudit) -> MemoryRole:
    if audit.outcome == "memory_aligned":
        return "evidence"
    if audit.outcome in {
        "memory_repeated_boundary_failure",
        "memory_reasoning_inconsistent",
        "memory_ignored",
        "memory_contradicted",
    }:
        return "warning"
    if audit.outcome == "inconclusive":
        return "boundary_case"
    return "excluded"


def _memory_role_from_episode(
    episode: DecisionEpisode,
    human_verdict: HumanReasoningVerdict | None,
) -> MemoryRole:
    if human_verdict == "correct":
        return "positive_example"
    if human_verdict == "incorrect":
        return "negative_example"
    if human_verdict == "unsafe":
        return "warning"
    if human_verdict in {"partially_correct", "needs_more_evidence"}:
        return "boundary_case"
    if episode.outcome in {"validated", "supported"}:
        return "evidence"
    if episode.outcome == "contradicted":
        return "negative_example"
    if episode.outcome == "overcorrected":
        return "warning"
    return "boundary_case"


def _memory_summary(
    postmortem: AgentReasoningPostmortem,
    review: HumanReasoningReview | None,
) -> str:
    verdict = "" if review is None else f" Human verdict: {review.verdict}."
    return f"{postmortem.outcome}: {postmortem.automatic_critique}{verdict}"


def _memory_usage_audit_summary(audit: MemoryUsageAudit) -> str:
    return f"{audit.outcome}: {audit.summary}"


def _episode_candidate_summary(
    episode: DecisionEpisode,
    human_verdict: HumanReasoningVerdict | None,
) -> str:
    verdict = "" if human_verdict is None else f" Human verdict: {human_verdict}."
    return f"{episode.decision_type}/{episode.outcome}: {episode.lesson_learned}{verdict}"


def _memory_content(
    postmortem: AgentReasoningPostmortem,
    review: HumanReasoningReview | None,
) -> str:
    parts = [
        f"Hypothesis: {postmortem.hypothesis}",
        f"Action: {postmortem.action_taken}",
        f"Expected effect: {postmortem.expected_effect or 'n/a'}",
        f"Automatic critique: {postmortem.automatic_critique}",
        "Reusable lessons: " + ", ".join(postmortem.reusable_lessons),
    ]
    if review is not None:
        parts.extend(
            [
                f"Human verdict: {review.verdict}",
                f"Human rationale: {review.rationale}",
            ]
        )
    return "\n".join(parts)


def _episode_candidate_content(episode: DecisionEpisode) -> str:
    parts = [
        f"Context: {episode.context_summary}",
        f"Chosen action: {episode.chosen_action}",
        f"Expected effect: {episode.expected_effect or 'n/a'}",
        f"Execution result: {episode.execution_result_summary or 'n/a'}",
        f"Before metrics: {json.dumps(episode.before_metrics, sort_keys=True)}",
        f"After metrics: {json.dumps(episode.after_metrics, sort_keys=True)}",
        "Evidence used: " + ", ".join(episode.evidence_used),
        "Retrieved memory ids: " + ", ".join(episode.retrieved_memory_record_ids),
        "Tradeoffs observed: " + ", ".join(episode.tradeoffs_observed),
        "Failure modes: " + ", ".join(episode.failure_modes),
        f"Lesson learned: {episode.lesson_learned}",
        "Reusable lessons: " + ", ".join(episode.reusable_lessons),
    ]
    if episode.hypothesis is not None:
        hypothesis = episode.hypothesis
        parts[1:1] = [
            f"Ex-ante hypothesis kind: {hypothesis.kind}",
            f"Ex-ante hypothesis: {hypothesis.statement}",
            f"Hypothesis scope: {hypothesis.scope}",
            f"Evidence cutoff: {hypothesis.evidence_cutoff}",
            f"Expected observation: {hypothesis.expected_observation}",
            f"Falsification criterion: {hypothesis.falsification_criterion}",
            "Hypothesis evidence refs: " + ", ".join(hypothesis.evidence_refs),
            "Hypothesis risks: " + ", ".join(hypothesis.risk_notes),
            "Hypothesis assumptions: " + ", ".join(hypothesis.assumptions),
            (
                "Hypothesis assessment: not recorded here; episode outcome is "
                "not by itself a confirmation of the hypothesis."
            ),
        ]
    if episode.options_considered:
        parts.append("Options considered:")
        for option in episode.options_considered:
            selected = "selected" if option.selected else "not_selected"
            parts.append(
                "- "
                f"{option.option_id} ({option.option_type}, {selected}): "
                f"{option.description}; params={json.dumps(option.parameters, sort_keys=True)}; "
                f"expected={option.expected_effect or 'n/a'}; "
                f"risks={', '.join(option.risk_notes)}"
            )
    return "\n".join(parts)


def _memory_usage_audit_content(audit: MemoryUsageAudit) -> str:
    parts = [
        f"Memory usage summary: {audit.memory_usage_summary or 'n/a'}",
        "Retrieved memory ids: " + ", ".join(audit.retrieved_memory_record_ids),
        "Cited memory ids: " + ", ".join(audit.cited_memory_record_ids),
        "Uncited retrieved ids: " + ", ".join(audit.uncited_retrieved_record_ids),
        "Cited without retrieval: " + ", ".join(audit.cited_without_retrieval),
        f"Before metrics: {json.dumps(audit.before_metrics, sort_keys=True)}",
        f"After metrics: {json.dumps(audit.after_metrics, sort_keys=True)}",
    ]
    if audit.items:
        parts.append("Item assessments:")
        for item in audit.items:
            parts.append(
                "- "
                f"{item.memory_record_id}: assessment={item.assessment}; "
                f"declared_usage={item.declared_usage or 'n/a'}; "
                f"risk_mitigation={item.risk_mitigation or 'n/a'}; "
                f"reason={item.assessment_reason}"
            )
    return "\n".join(parts)


def _candidate_record_content(candidate: MemoryCandidate) -> str:
    parts = [
        candidate.content,
        "When to reuse: " + "; ".join(candidate.when_to_reuse),
        "When not to reuse: " + "; ".join(candidate.when_not_to_reuse),
        f"Risk if misused: {candidate.risk_if_misused or 'n/a'}",
    ]
    return "\n".join(part for part in parts if part)


def _memory_tags(
    postmortem: AgentReasoningPostmortem,
    review: HumanReasoningReview | None,
) -> list[str]:
    tags = [
        postmortem.agent_name,
        postmortem.outcome,
        *postmortem.reusable_lessons,
    ]
    if review is not None:
        tags.extend([review.verdict, *review.tags])
    return sorted(set(tags))


def _episode_candidate_tags(
    episode: DecisionEpisode,
    human_verdict: HumanReasoningVerdict | None,
) -> list[str]:
    tags = [
        episode.target_agent,
        episode.agent_name,
        episode.decision_type,
        episode.outcome,
        f"data_provenance:{episode.data_provenance}",
        *episode.failure_modes,
        *episode.tradeoffs_observed,
        *episode.reusable_lessons,
    ]
    if episode.dataset is not None:
        tags.append(episode.dataset)
    if episode.hypothesis is not None:
        tags.append(f"hypothesis_kind:{episode.hypothesis.kind}")
    if human_verdict is not None:
        tags.append(human_verdict)
    return sorted(set(tags))


def _candidate_record_tags(candidate: MemoryCandidate) -> list[str]:
    tags = [
        candidate.target_agent,
        candidate.memory_role,
        candidate.source_type,
        f"data_provenance:{candidate.data_provenance}",
        *candidate.tags,
    ]
    if candidate.dataset is not None:
        tags.append(candidate.dataset)
    if candidate.outcome is not None:
        tags.append(candidate.outcome)
    if candidate.human_verdict is not None:
        tags.append(candidate.human_verdict)
    return sorted(set(tags))


def _memory_usage_audit_tags(
    audit: MemoryUsageAudit,
    target_agent: AgentMemoryTarget,
) -> list[str]:
    tags = [
        target_agent,
        audit.outcome,
        "memory_usage_audit",
        *audit.retrieved_memory_record_ids,
        *audit.cited_memory_record_ids,
    ]
    tags.extend(item.assessment for item in audit.items)
    tags.extend(
        item.memory_role
        for item in audit.items
        if item.memory_role is not None
    )
    return sorted(set(tags))


def _record_matches_query(
    record: ReasoningMemoryRecord,
    query: AgentMemoryQuery,
) -> bool:
    if record.exclude_from_context or not record.reusable_as_context:
        return False
    if record.source_type == "memory_usage_audit":
        return False
    if record.source_type in {"decision_episode", "memory_candidate"} and (
        record.promotion_source_hash is None
        or record.source_hash != record.promotion_source_hash
    ):
        return False
    if record.memory_role not in query.allowed_memory_roles:
        return False
    if record.human_verdict is not None and record.human_verdict in query.excluded_verdicts:
        return False
    if record.target_agent not in {query.target_agent, "shared_methodology"}:
        return False
    if memory_provenance_status(record, query) == "conflict":
        return False
    if query.dataset is not None and record.dataset not in {None, query.dataset}:
        return False
    return True


def memory_provenance_status(
    record: ReasoningMemoryRecord,
    query: AgentMemoryQuery,
) -> Literal["match", "unknown", "conflict"]:
    """Clasifica compatibilidad sin convertir ``unknown`` en evidencia positiva."""

    if record.target_agent == "shared_methodology":
        return "unknown" if record.data_provenance == "unknown" else "conflict"
    if query.data_provenance == "unknown":
        return "unknown" if record.data_provenance == "unknown" else "conflict"
    if record.data_provenance == query.data_provenance:
        return "match"
    if record.data_provenance == "unknown":
        return "unknown"
    return "conflict"


def _qdrant_query_filter(
    query: AgentMemoryQuery,
    *,
    embedding_model: str,
    embedding_version: str,
) -> dict[str, Any]:
    target_agents = sorted({query.target_agent, "shared_methodology"})
    must: list[dict[str, Any]] = [
        {
            "key": "target_agent",
            "match": {"any": target_agents},
        },
        {
            "key": "memory_role",
            "match": {"any": sorted(set(query.allowed_memory_roles))},
        },
        {
            "key": "reusable_as_context",
            "match": {"value": True},
        },
        {
            "key": "exclude_from_context",
            "match": {"value": False},
        },
        {
            "key": "record.embedding_model",
            "match": {"value": embedding_model},
        },
        {
            "key": "record.embedding_version",
            "match": {"value": embedding_version},
        },
        _qdrant_provenance_scope(query),
        _qdrant_governed_source_scope(),
    ]
    if query.dataset is not None:
        must.append(
            {
                "should": [
                    {
                        "key": "dataset",
                        "match": {"value": query.dataset},
                    },
                    {"is_null": {"key": "dataset"}},
                ]
            }
        )

    query_filter: dict[str, Any] = {"must": must}
    if query.excluded_verdicts:
        query_filter["must_not"] = [
            {
                "key": "human_verdict",
                "match": {"any": sorted(set(query.excluded_verdicts))},
            }
        ]
    return query_filter


def _qdrant_governed_source_scope() -> dict[str, Any]:
    """Descarta auditorias y candidatos sin promocion en el propio servidor."""

    candidate_source = {
        "key": "source_type",
        "match": {"any": ["decision_episode", "memory_candidate"]},
    }
    return {
        "must_not": [
            {
                "key": "source_type",
                "match": {"value": "memory_usage_audit"},
            }
        ],
        "should": [
            {"must_not": [candidate_source]},
            {
                "must": [candidate_source],
                "must_not": [
                    {"is_empty": {"key": "promotion_source_hash"}},
                ],
            },
        ],
    }


def _qdrant_provenance_scope(query: AgentMemoryQuery) -> dict[str, Any]:
    unknown = _qdrant_unknown_provenance_condition()
    if query.target_agent == "shared_methodology":
        return unknown

    allowed_specific: list[dict[str, Any]] = [unknown]
    if query.data_provenance != "unknown":
        allowed_specific.insert(
            0,
            {
                "key": "data_provenance",
                "match": {"value": query.data_provenance},
            },
        )
    return {
        "should": [
            {
                "must": [
                    {
                        "key": "target_agent",
                        "match": {"value": query.target_agent},
                    },
                    {"should": allowed_specific},
                ]
            },
            {
                "must": [
                    {
                        "key": "target_agent",
                        "match": {"value": "shared_methodology"},
                    },
                    unknown,
                ]
            },
        ]
    }


def _qdrant_unknown_provenance_condition() -> dict[str, Any]:
    return {
        "should": [
            {
                "key": "data_provenance",
                "match": {"value": "unknown"},
            },
            {"is_empty": {"key": "data_provenance"}},
        ]
    }


def _record_text(record: ReasoningMemoryRecord) -> str:
    parts = [
        record.summary,
        record.content,
        record.dataset or "",
        f"data_provenance={record.data_provenance}",
        record.outcome or "",
        record.human_verdict or "",
        record.memory_role,
        " ".join(record.tags),
    ]
    return "\n".join(part for part in parts if part)


def _query_text(query: AgentMemoryQuery) -> str:
    context = " ".join(f"{key}={value}" for key, value in sorted(query.decision_context.items()))
    return (
        f"{query.query_text}\n{query.dataset or ''}\n"
        f"data_provenance={query.data_provenance}\n{context}"
    )


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in TOKEN_PATTERN.finditer(text)]


def _normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return vector
    return [value / norm for value in vector]


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True))


def _validate_local_embedding_compatibility(
    payload: dict[str, Any],
    entries: list[StoredMemoryVector],
    *,
    provider: EmbeddingProvider,
    expected_dimension: int | None,
    collection_name: str,
) -> None:
    """Evita consultar o mezclar vectores creados con otro embedding."""

    metadata = payload.get("embedding_model")
    if entries and not isinstance(metadata, dict):
        raise VectorMemoryConfigError(
            f"memory collection {collection_name} has no embedding metadata; "
            "rebuild it explicitly before querying"
        )
    if isinstance(metadata, dict):
        stored_identifier = metadata.get("identifier")
        if not isinstance(stored_identifier, str):
            model_name = metadata.get("model_name")
            version = metadata.get("version")
            if isinstance(model_name, str) and isinstance(version, str):
                stored_identifier = f"{model_name}:{version}"
        if stored_identifier != provider.identifier:
            raise VectorMemoryConfigError(
                "embedding mismatch for memory collection "
                f"{collection_name}: stored={stored_identifier!r}, "
                f"configured={provider.identifier!r}; select the original provider "
                "or rebuild the derived index explicitly"
            )
        stored_dimension = metadata.get("dimension")
        if (
            expected_dimension is not None
            and isinstance(stored_dimension, int)
            and stored_dimension != expected_dimension
        ):
            raise VectorMemoryConfigError(
                "embedding dimension mismatch for memory collection "
                f"{collection_name}: stored={stored_dimension}, "
                f"configured={expected_dimension}"
            )

    for entry in entries:
        if expected_dimension is not None and len(entry.vector) != expected_dimension:
            raise VectorMemoryConfigError(
                "embedding dimension mismatch for memory record "
                f"{entry.record.memory_record_id}: stored={len(entry.vector)}, "
                f"configured={expected_dimension}; rebuild the derived index"
            )
        if not _record_embedding_matches_provider(
            entry.record,
            provider,
            expected_dimension=expected_dimension,
        ):
            raise VectorMemoryConfigError(
                "embedding metadata mismatch for memory record "
                f"{entry.record.memory_record_id}; rebuild the derived index"
            )


def _record_embedding_matches_provider(
    record: ReasoningMemoryRecord,
    provider: EmbeddingProvider,
    *,
    expected_dimension: int | None,
) -> bool:
    if record.embedding_model != provider.model_name:
        return False
    if record.embedding_version != provider.version:
        return False
    return (
        expected_dimension is None
        or record.embedding_dimension == expected_dimension
    )


def _validate_qdrant_collection_compatibility(
    collection_info: dict[str, Any],
    *,
    collection_name: str,
    expected_dimension: int,
    expected_distance: str,
) -> None:
    dimension, distance = _qdrant_vector_config(collection_info)
    if dimension is None or distance is None:
        raise VectorMemoryConfigError(
            f"Qdrant collection {collection_name} does not expose a single-vector "
            "configuration; explicit migration is required"
        )
    if dimension != expected_dimension:
        raise VectorMemoryConfigError(
            f"Qdrant collection {collection_name} uses dimension {dimension}, "
            f"but the configured embedding produces {expected_dimension}; rebuild "
            "or select a compatible collection"
        )
    if distance.lower() != expected_distance.lower():
        raise VectorMemoryConfigError(
            f"Qdrant collection {collection_name} uses distance {distance}, "
            f"but {expected_distance} is configured"
        )


def _qdrant_vector_config(
    collection_info: dict[str, Any],
) -> tuple[int | None, str | None]:
    result = collection_info.get("result")
    if not isinstance(result, dict):
        return None, None
    config = result.get("config")
    if not isinstance(config, dict):
        return None, None
    params = config.get("params")
    if not isinstance(params, dict):
        return None, None
    vectors = params.get("vectors")
    if not isinstance(vectors, dict):
        return None, None
    size = vectors.get("size")
    distance = vectors.get("distance")
    if not isinstance(size, int) or not isinstance(distance, str):
        return None, None
    return size, distance


def _embedding_provider_metadata(provider: EmbeddingProvider) -> dict[str, str | int]:
    metadata: dict[str, str | int] = {
        "model_name": provider.model_name,
        "version": provider.version,
        "identifier": provider.identifier,
    }
    dimension = getattr(provider, "dimension", None)
    if isinstance(dimension, int):
        metadata["dimension"] = dimension
    return metadata


def _qdrant_point_id(memory_record_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"tfm-memory:{memory_record_id}"))


def _qdrant_payload_index_fields(collection_info: dict[str, Any]) -> set[str]:
    result = collection_info.get("result")
    if not isinstance(result, dict):
        return set()
    payload_schema = result.get("payload_schema")
    if not isinstance(payload_schema, dict):
        return set()
    return {field_name for field_name in payload_schema if isinstance(field_name, str)}


def _qdrant_payload(record: ReasoningMemoryRecord) -> dict[str, Any]:
    return {
        "memory_record_id": record.memory_record_id,
        "collection_name": record.collection_name,
        "target_agent": record.target_agent,
        "dataset": record.dataset,
        "data_provenance": record.data_provenance,
        "source_type": record.source_type,
        "memory_role": record.memory_role,
        "human_verdict": record.human_verdict,
        "reusable_as_context": record.reusable_as_context,
        "exclude_from_context": record.exclude_from_context,
        "promotion_source_hash": record.promotion_source_hash,
        "run_id": record.run_id,
        "decision_id": record.decision_id,
        "tags": record.tags,
        "record": record.model_dump(mode="json"),
        "text": _record_text(record),
    }


def _record_from_qdrant_payload(payload: Any) -> ReasoningMemoryRecord | None:
    if not isinstance(payload, dict):
        return None
    record_payload = payload.get("record")
    if not isinstance(record_payload, dict):
        return None
    return ReasoningMemoryRecord.model_validate(record_payload)


def _qdrant_result_list(response: dict[str, Any]) -> list[dict[str, Any]]:
    result = response.get("result")
    if isinstance(result, dict):
        points = result.get("points")
        if not isinstance(points, list):
            return []
        return [item for item in points if isinstance(item, dict)]
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    return []


def _qdrant_similarity(score: Any) -> float:
    if not isinstance(score, (int, float)) or isinstance(score, bool):
        return 0.0
    return max(0.0, min(1.0, float(score)))


def _url_part(value: str) -> str:
    return urllib.parse.quote(value, safe="")


def _sorted_entries(
    entries: dict[str, StoredMemoryVector],
) -> list[StoredMemoryVector]:
    return [entries[key] for key in sorted(entries)]
