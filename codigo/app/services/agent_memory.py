"""Utilidades comunes para inyectar memoria RAG en agentes."""

from __future__ import annotations

from codigo.app.schemas.agent_decisions import MemoryRecordUse
from codigo.app.schemas.reasoning import RetrievedMemoryContext


def memory_context_for_llm(
    memory_context: RetrievedMemoryContext | None,
    *,
    content_excerpt_chars: int = 900,
) -> dict[str, object]:
    """Convierte memoria recuperada en contexto compacto para un prompt."""

    if memory_context is None:
        return {
            "available": False,
            "reason": "memory retrieval disabled for this decision",
        }
    return {
        "available": True,
        "context_id": memory_context.context_id,
        "query_id": memory_context.query.query_id,
        "retrieval_backend": memory_context.retrieval_backend,
        "embedding_model": memory_context.embedding_model,
        "items": [
            {
                "rank": item.rank,
                "similarity": round(item.similarity, 6),
                "retrieval_use": item.retrieval_use,
                "memory_record_id": item.record.memory_record_id,
                "source_type": item.record.source_type,
                "memory_role": item.record.memory_role,
                "human_verdict": item.record.human_verdict,
                "outcome": item.record.outcome,
                "run_id": item.record.run_id,
                "source_path": item.record.source_path,
                "summary": item.record.summary,
                "content_excerpt": item.record.content[:content_excerpt_chars],
                "metrics": item.record.metrics,
                "tags": item.record.tags[:12],
            }
            for item in memory_context.items
        ],
    }


def memory_record_ids(memory_context: RetrievedMemoryContext | None) -> list[str]:
    """Devuelve los identificadores recuperados en orden de ranking."""

    if memory_context is None:
        return []
    return [item.record.memory_record_id for item in memory_context.items]


def memory_usage_json_template(
    memory_context: RetrievedMemoryContext | None,
    *,
    max_records: int = 3,
) -> dict[str, object]:
    """Campos JSON esperados para declarar uso de memoria en una decision."""

    memory_ids = memory_record_ids(memory_context)[:max_records]
    return {
        "memory_context_id": None if memory_context is None else memory_context.context_id,
        "used_memory_context": bool(memory_ids),
        "memory_record_ids": memory_ids,
        "memory_usage_summary": (
            None
            if not memory_ids
            else "Como influyen los recuerdos recuperados en esta decision."
        ),
        "memory_record_uses": [
            {
                "memory_record_id": memory_id,
                "usage": "adapted",
                "influence_summary": (
                    "Que aprendizaje concreto aporta este recuerdo a la decision."
                ),
                "risk_mitigation": (
                    "Como se evita reutilizar el recuerdo fuera de contexto."
                ),
            }
            for memory_id in memory_ids
        ],
    }


def validate_retrieved_memory_usage(
    *,
    memory_context: RetrievedMemoryContext | None,
    memory_context_id: str | None,
    used_memory_context: bool,
    memory_record_ids: list[str],
    memory_record_uses: list[MemoryRecordUse],
    require_declared_uses: bool = True,
) -> None:
    """Valida que una decision cite solo recuerdos realmente recuperados."""

    if memory_context_id is not None:
        if memory_context is None:
            raise ValueError("memory_context_id was declared but no memory was provided")
        if memory_context_id != memory_context.context_id:
            raise ValueError("memory_context_id does not match retrieved context")
    if not used_memory_context:
        return
    if memory_context is None or not memory_context.items:
        raise ValueError("used_memory_context=true requires retrieved memory")
    available_record_ids = set(memory_record_ids_from_context(memory_context))
    unknown_ids = sorted(set(memory_record_ids) - available_record_ids)
    if unknown_ids:
        raise ValueError(
            "memory_record_ids were not retrieved: " + ", ".join(unknown_ids)
        )
    declared_use_ids = {item.memory_record_id for item in memory_record_uses}
    unknown_use_ids = sorted(declared_use_ids - available_record_ids)
    if unknown_use_ids:
        raise ValueError(
            "memory_record_uses were not retrieved: " + ", ".join(unknown_use_ids)
        )
    if require_declared_uses:
        missing_use_ids = sorted(set(memory_record_ids) - declared_use_ids)
        if missing_use_ids:
            raise ValueError(
                "cited memory records require memory_record_uses: "
                + ", ".join(missing_use_ids)
            )


def memory_record_ids_from_context(
    memory_context: RetrievedMemoryContext,
) -> list[str]:
    """Alias explicito para validaciones internas."""

    return [item.record.memory_record_id for item in memory_context.items]
