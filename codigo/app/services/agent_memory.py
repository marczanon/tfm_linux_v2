"""Utilidades comunes para inyectar memoria RAG en agentes."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from codigo.app.schemas.agent_decisions import MemoryRecordUse
from codigo.app.schemas.reasoning import RetrievedMemoryContext
from codigo.app.schemas.state import TFMStateModel


# En una decision ``online_blind`` no se proyecta texto libre procedente de
# ejecuciones previas. Solo estas etiquetas metodologicas se convierten en
# instrucciones cerradas que no revelan resultados post-hoc ni valores de la
# trayectoria monitorizada.
ONLINE_BLIND_MEMORY_GUIDANCE_BY_TAG = {
    "calibration_only": (
        "Ajustar umbrales solo con baseline y calibracion, nunca con monitoring."
    ),
    "causal_partition": (
        "Mantener el orden temporal y la separacion causal entre particiones."
    ),
    "compare_model_family_after_partial_threshold_gain": (
        "Comparar familias de modelo si mover solo el umbral no resuelve el riesgo."
    ),
    "isolated_spike_not_failure": (
        "Separar picos aislados de alertas sostenidas sin atribuir causa fisica."
    ),
    "leakage_prevention": (
        "No usar etiquetas, metricas ni conocimiento del tramo de monitoring."
    ),
    "rul_not_estimated": (
        "No presentar RUL como estimacion cuando no existe supervision causal."
    ),
    "sustained_alert": (
        "Evaluar persistencia temporal antes de elevar una alerta."
    ),
    "sustained_alert_required": (
        "Exigir persistencia temporal y no reaccionar a un unico pico."
    ),
}


def call_agent_with_optional_memory(
    agent: Callable[..., Any],
    state: TFMStateModel,
    memory_context: RetrievedMemoryContext | None,
) -> Any:
    """Inyecta memoria solo cuando el contrato del agente la admite."""

    if memory_context is None or not _accepts_memory_context(agent):
        return agent(state)
    return agent(state, memory_context=memory_context)


def _accepts_memory_context(agent: Callable[..., Any]) -> bool:
    try:
        signature = inspect.signature(agent)
    except (TypeError, ValueError):
        return False
    return "memory_context" in signature.parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )


def memory_context_for_llm(
    memory_context: RetrievedMemoryContext | None,
    *,
    content_excerpt_chars: int = 900,
    online_blind: bool = False,
) -> dict[str, object]:
    """Convierte memoria recuperada en contexto compacto para un prompt."""

    if memory_context is None:
        return {
            "available": False,
            "reason": "memory retrieval disabled for this decision",
        }
    if online_blind:
        return _online_blind_memory_context_for_llm(memory_context)
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
                "data_provenance": item.record.data_provenance,
                "provenance_caution": item.record.data_provenance == "unknown",
                "summary": item.record.summary,
                "content_excerpt": item.record.content[:content_excerpt_chars],
                "metrics": item.record.metrics,
                "tags": item.record.tags[:12],
            }
            for item in memory_context.items
        ],
    }


def _online_blind_memory_context_for_llm(
    memory_context: RetrievedMemoryContext,
) -> dict[str, object]:
    """Proyecta solo metodologia cerrada, nunca resultados retrospectivos."""

    items: list[dict[str, object]] = []
    for item in memory_context.items:
        safe_tags = sorted(
            set(item.record.tags) & set(ONLINE_BLIND_MEMORY_GUIDANCE_BY_TAG)
        )
        applicability = item.record.applicability
        items.append(
            {
                "rank": item.rank,
                "similarity": round(item.similarity, 6),
                "retrieval_use": item.retrieval_use,
                "memory_record_id": item.record.memory_record_id,
                "source_type": item.record.source_type,
                "memory_role": item.record.memory_role,
                "data_provenance": item.record.data_provenance,
                "provenance_caution": item.record.data_provenance == "unknown",
                "applicability": (
                    None
                    if applicability is None
                    else applicability.model_dump(mode="json")
                ),
                "safe_methodology_tags": safe_tags,
                "methodological_guidance": [
                    ONLINE_BLIND_MEMORY_GUIDANCE_BY_TAG[tag] for tag in safe_tags
                ],
            }
        )
    return {
        "available": True,
        "context_id": memory_context.context_id,
        "query_id": memory_context.query.query_id,
        "retrieval_backend": memory_context.retrieval_backend,
        "embedding_model": memory_context.embedding_model,
        "evidence_view": "online_blind_causal_projection_v1",
        "retrospective_fields_omitted": [
            "summary",
            "content",
            "metrics",
            "outcome",
            "run_id",
            "source_path",
        ],
        "items": items,
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

    # Los IDs disponibles se muestran en ``memory_context_for_llm``. No se
    # incluyen como campos extra del objeto de salida porque el contrato es
    # estricto y, sobre todo, porque no deben parecer citas preseleccionadas.
    _ = max_records
    return {
        "memory_context_id": None if memory_context is None else memory_context.context_id,
        # El esquema parte de no uso para evitar anclar al LLM a copiar o citar
        # todos los recuerdos recuperados. Los IDs disponibles ya aparecen en
        # ``memory_context_for_llm`` y solo deben copiarse tras una decision
        # explicita y justificable del agente.
        "used_memory_context": False,
        "memory_record_ids": [],
        "memory_usage_summary": None,
        "memory_record_uses": [],
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
