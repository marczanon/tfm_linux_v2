"""Agente modelador LLM con fallback seguro."""

from __future__ import annotations

import csv
import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from codigo.app.executors.modeling import (
    DEFAULT_MODELING_CONFIG,
    DEFAULT_PCA_MODELING_CONFIG,
    METADATA_COLUMNS,
    SKLEARN_IFOREST_PARAMS,
    SKLEARN_PCA_PARAMS,
)
from codigo.app.schemas.agent_decisions import ModelingRetryDecision
from codigo.app.schemas.agent_decisions import ModelingDecision
from codigo.app.schemas.reasoning import AgentMemoryQuery, RetrievedMemoryContext
from codigo.app.schemas.state import ModelingConfig, TFMStateModel
from codigo.app.services.llm import (
    JSONLLMClient,
    LLMCallError,
    LLMMessage,
    get_default_json_llm_client,
)
from codigo.app.services.vector_memory import VectorMemoryStore


SUPPORTED_MODEL_NAMES = {"isolation_forest", "pca_reconstruction_error"}
SUPPORTED_HYPERPARAMETERS_BY_MODEL = {
    "isolation_forest": SKLEARN_IFOREST_PARAMS | {"threshold_quantile"},
    "pca_reconstruction_error": SKLEARN_PCA_PARAMS | {"threshold_quantile"},
}


def decide_modeling_action(
    state: TFMStateModel,
    *,
    llm_client: JSONLLMClient | None = None,
    use_llm: bool | None = None,
) -> ModelingDecision:
    """Decide modelo e hiperparametros usando LLM cuando este habilitado."""

    should_use_llm = _should_use_llm(llm_client, use_llm)
    if should_use_llm:
        try:
            client = llm_client or get_default_json_llm_client()
            return decide_modeling_action_with_llm(state, client)
        except (LLMCallError, ValidationError, ValueError) as exc:
            fallback = decide_modeling_action_deterministic(state)
            fallback.rationale = f"{fallback.rationale} Fallback after LLM failure: {exc}"
            fallback.confidence = min(fallback.confidence, 0.7)
            return fallback

    return decide_modeling_action_deterministic(state)


def decide_modeling_action_with_llm(
    state: TFMStateModel,
    llm_client: JSONLLMClient,
) -> ModelingDecision:
    """Solicita al LLM una ModelingDecision y valida sus limites."""

    payload = llm_client.complete_json(
        _modeler_messages(state),
        json_schema=ModelingDecision.model_json_schema(),
    )
    decision = ModelingDecision.model_validate(payload)
    _validate_modeling_decision_bounds(state, decision)
    return decision


def decide_modeling_action_deterministic(state: TFMStateModel) -> ModelingDecision:
    """Fallback reproducible para el MVP CWRU."""

    return ModelingDecision(
        decision_id=f"{state.run_id}:modeler:{_modeler_turn(state):03d}",
        rationale=(
            "Fallback CWRU modeling policy: use Isolation Forest over the "
            "time-domain feature table, train only with normal train windows "
            "and derive the anomaly threshold from the validation split."
        ),
        confidence=1.0,
        modeling_config=DEFAULT_MODELING_CONFIG,
        train_split="train",
        validation_split="validation",
        expected_model_path=_expected_model_path(state, DEFAULT_MODELING_CONFIG),
    )


def decide_modeling_retry_action(
    state: TFMStateModel,
    *,
    failure_analysis: dict[str, Any],
    source_run_id: str,
    attempt_number: int,
    max_attempts: int,
    memory_context: RetrievedMemoryContext | None = None,
    llm_client: JSONLLMClient | None = None,
    use_llm: bool | None = None,
) -> ModelingRetryDecision:
    """Decide si conviene reintentar una ejecucion fallida de modelado."""

    should_use_llm = _should_use_llm(llm_client, use_llm)
    if should_use_llm:
        try:
            client = llm_client or get_default_json_llm_client()
            return decide_modeling_retry_action_with_llm(
                state,
                failure_analysis=failure_analysis,
                source_run_id=source_run_id,
                attempt_number=attempt_number,
                max_attempts=max_attempts,
                memory_context=memory_context,
                llm_client=client,
            )
        except (LLMCallError, ValidationError, ValueError) as exc:
            fallback = decide_modeling_retry_action_deterministic(
                state,
                failure_analysis=failure_analysis,
                source_run_id=source_run_id,
                attempt_number=attempt_number,
                max_attempts=max_attempts,
            )
            fallback.rationale = f"{fallback.rationale} Fallback after LLM failure: {exc}"
            fallback.confidence = min(fallback.confidence, 0.7)
            return fallback

    return decide_modeling_retry_action_deterministic(
        state,
        failure_analysis=failure_analysis,
        source_run_id=source_run_id,
        attempt_number=attempt_number,
        max_attempts=max_attempts,
    )


def decide_modeling_retry_action_with_llm(
    state: TFMStateModel,
    *,
    failure_analysis: dict[str, Any],
    source_run_id: str,
    attempt_number: int,
    max_attempts: int,
    memory_context: RetrievedMemoryContext | None = None,
    llm_client: JSONLLMClient,
) -> ModelingRetryDecision:
    """Solicita al LLM una decision de reintento y valida sus limites."""

    payload = llm_client.complete_json(
        _modeler_retry_messages(
            state,
            failure_analysis=failure_analysis,
            source_run_id=source_run_id,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            memory_context=memory_context,
        ),
        json_schema=ModelingRetryDecision.model_json_schema(),
    )
    decision = ModelingRetryDecision.model_validate(payload)
    _validate_modeling_retry_decision_bounds(
        state,
        decision,
        memory_context=memory_context,
    )
    return decision


def decide_modeling_retry_action_deterministic(
    state: TFMStateModel,
    *,
    failure_analysis: dict[str, Any],
    source_run_id: str,
    attempt_number: int,
    max_attempts: int,
) -> ModelingRetryDecision:
    """Fallback conservador: no inventa una mejora si no hay LLM disponible."""

    return ModelingRetryDecision(
        decision_id=f"{state.run_id}:modeler_retry:{attempt_number:03d}",
        rationale=(
            "Fallback retry policy: stop instead of inventing a new modeling "
            "configuration without an agent decision."
        ),
        confidence=1.0,
        source_run_id=source_run_id,
        attempt_number=attempt_number,
        max_attempts=max_attempts,
        should_retry=False,
        learning_summary=_fallback_learning_summary(failure_analysis),
        stop_reason="No LLM retry decision available; avoiding blind retry loop.",
        evidence_used=["failure_analysis"],
    )


def build_modeler_retry_memory_query(
    state: TFMStateModel,
    *,
    failure_analysis: dict[str, Any],
    source_run_id: str,
    attempt_number: int,
    max_attempts: int,
    top_k: int = 3,
    min_similarity: float = 0.0,
) -> AgentMemoryQuery:
    """Construye la consulta RAG para el reintento del modelador."""

    failure_modes = failure_analysis.get("failure_modes", [])
    query_text = "\n".join(
        [
            "Modeler retry decision for industrial anomaly detection.",
            f"Dataset: {state.project_context.dataset}",
            f"Objective: {state.project_context.objective}",
            f"Failure modes: {json.dumps(failure_modes, ensure_ascii=True)}",
            f"Failure analysis: {json.dumps(failure_analysis, ensure_ascii=True)}",
            f"Current modeling config: {json.dumps(_current_modeling_config_json(state), ensure_ascii=True)}",
        ]
    )
    return AgentMemoryQuery(
        query_id=f"{state.run_id}:modeler_retry:{attempt_number:03d}:memory_query",
        target_agent="modeler",
        query_text=query_text,
        dataset=state.project_context.dataset,
        run_id=state.run_id,
        decision_id=f"{state.run_id}:modeler_retry:{attempt_number:03d}",
        decision_context={
            "source_run_id": source_run_id,
            "attempt_number": attempt_number,
            "max_attempts": max_attempts,
            "precision": None if state.metrics is None else state.metrics.precision,
            "recall": None if state.metrics is None else state.metrics.recall,
            "f1_score": None if state.metrics is None else state.metrics.f1_score,
            "false_positive_rate": (
                None if state.metrics is None else state.metrics.false_positive_rate
            ),
        },
        allowed_memory_roles=[
            "positive_example",
            "negative_example",
            "boundary_case",
            "warning",
            "methodology",
            "evidence",
        ],
        top_k=top_k,
        min_similarity=min_similarity,
    )


def retrieve_modeler_retry_memory_context(
    state: TFMStateModel,
    *,
    failure_analysis: dict[str, Any],
    source_run_id: str,
    attempt_number: int,
    max_attempts: int,
    memory_store: VectorMemoryStore,
    top_k: int = 3,
    min_similarity: float = 0.0,
) -> RetrievedMemoryContext:
    """Recupera recuerdos supervisados para el reintento del modelador."""

    query = build_modeler_retry_memory_query(
        state,
        failure_analysis=failure_analysis,
        source_run_id=source_run_id,
        attempt_number=attempt_number,
        max_attempts=max_attempts,
        top_k=top_k,
        min_similarity=min_similarity,
    )
    return memory_store.query(query)


def _should_use_llm(
    llm_client: JSONLLMClient | None,
    use_llm: bool | None,
) -> bool:
    if use_llm is not None:
        return use_llm
    if llm_client is not None:
        return True
    return os.getenv("TFM_MODELER_MODE", "").strip().lower() == "llm"


def _modeler_messages(state: TFMStateModel) -> list[LLMMessage]:
    features_path = _features_path_for_state(state)
    return [
        LLMMessage(
            role="system",
            content=(
                "Eres el agente modelador de un pipeline industrial de "
                "deteccion de anomalias. Tu tarea es seleccionar el algoritmo "
                "e hiperparametros dentro de las capacidades del MVP. No puedes "
                "entrenar modelos, ejecutar codigo ni leer datasets completos. "
                "Debes devolver exclusivamente un objeto JSON compatible con "
                "ModelingDecision."
            ),
        ),
        LLMMessage(
            role="user",
            content="\n".join(
                [
                    "Contexto ligero:",
                    json.dumps(_state_summary_for_llm(state), indent=2, ensure_ascii=True),
                    "",
                    "Resumen de features:",
                    json.dumps(_features_summary_for_llm(features_path), indent=2, ensure_ascii=True),
                    "",
                    "Formato JSON esperado:",
                    json.dumps(_modeler_json_template(state), indent=2, ensure_ascii=True),
                    "",
                    "Reglas:",
                    "- No incluyas texto fuera del JSON.",
                    "- modeling_config debe validar contra ModelingConfig.",
                    (
                        "- model_name debe estar soportado: isolation_forest "
                        "o pca_reconstruction_error."
                    ),
                    "- random_state debe ser 42.",
                    "- train_split debe ser train.",
                    "- validation_split debe ser validation o null.",
                    "- Solo puedes usar hiperparametros soportados por el ejecutor.",
                    "- n_jobs debe ser 1 si se incluye.",
                    "- threshold_quantile debe estar en (0, 1].",
                    (
                        "- Incluye comparison_candidates con 1 a 3 alternativas "
                        "comparables cuando haya mas de un modelo soportado."
                    ),
                    (
                        "- No inventes modelos: cada comparison_candidate debe "
                        "usar un model_name soportado."
                    ),
                    (
                        "- expected_model_path debe ser la ruta esperada para "
                        "el model_name elegido."
                    ),
                    f"- decision_id debe ser: {state.run_id}:modeler:{_modeler_turn(state):03d}",
                ]
            ),
        ),
    ]


def _modeler_retry_messages(
    state: TFMStateModel,
    *,
    failure_analysis: dict[str, Any],
    source_run_id: str,
    attempt_number: int,
    max_attempts: int,
    memory_context: RetrievedMemoryContext | None = None,
) -> list[LLMMessage]:
    return [
        LLMMessage(
            role="system",
            content=(
                "Eres el agente modelador de un pipeline industrial. Debes "
                "aprender de una ejecucion fallida y decidir si merece la pena "
                "un reintento acotado. No entrenas modelos ni ejecutas codigo. "
                "Debes devolver exclusivamente un JSON compatible con "
                "ModelingRetryDecision."
            ),
        ),
        LLMMessage(
            role="user",
            content="\n".join(
                [
                    "Contexto de la run fallida:",
                    json.dumps(_state_summary_for_llm(state), indent=2, ensure_ascii=True),
                    "",
                    "Analisis de fallo calculado por el sistema:",
                    json.dumps(failure_analysis, indent=2, ensure_ascii=True),
                    "",
                    "Configuracion de modelado previa:",
                    json.dumps(_current_modeling_config_json(state), indent=2, ensure_ascii=True),
                    "",
                    "Memoria recuperada para el modelador:",
                    json.dumps(
                        _memory_context_for_llm(memory_context),
                        indent=2,
                        ensure_ascii=True,
                    ),
                    "",
                    "Guia derivada de la memoria recuperada:",
                    json.dumps(
                        _memory_retry_guidance_for_llm(memory_context),
                        indent=2,
                        ensure_ascii=True,
                    ),
                    "",
                    "Formato JSON esperado:",
                    json.dumps(
                        _modeler_retry_json_template(
                            state,
                            source_run_id=source_run_id,
                            attempt_number=attempt_number,
                            max_attempts=max_attempts,
                            memory_context=memory_context,
                        ),
                        indent=2,
                        ensure_ascii=True,
                    ),
                    "",
                    "Reglas:",
                    "- No incluyas texto fuera del JSON.",
                    "- should_retry debe ser false si no queda margen real de mejora.",
                    "- attempt_number y max_attempts deben coincidir con el formato esperado.",
                    (
                        "- Si attempt_number == max_attempts, este es el ultimo "
                        "reintento permitido; si decides ejecutarlo y falla, "
                        "el sistema debe detenerse."
                    ),
                    (
                        "- attempt_number == max_attempts no obliga a poner "
                        "should_retry=false antes de probar una hipotesis nueva; "
                        "solo indica que no habra mas intentos despues."
                    ),
                    "- Si should_retry=false, retry_config debe ser null y stop_reason no puede ser null.",
                    "- Si should_retry=true, retry_config debe validar contra ModelingConfig.",
                    "- retry_config debe cambiar algo respecto a la configuracion previa.",
                    "- Solo puedes usar modelos soportados: isolation_forest o pca_reconstruction_error.",
                    "- random_state debe ser 42.",
                    "- n_jobs debe ser 1 si se incluye.",
                    "- threshold_quantile debe estar en (0, 1].",
                    (
                        "- Recuerda la convencion: predicted_anomaly=1 si "
                        "anomaly_score > threshold. Bajar el umbral suele "
                        "capturar mas anomalias y subirlo suele ser mas conservador."
                    ),
                    (
                        "- Explica en learning_summary que aprendiste de falsos "
                        "negativos, falsos positivos y comportamiento del umbral."
                    ),
                    (
                        "- La memoria recuperada es solo contexto; no puede "
                        "saltarse modelos soportados, validaciones ni metricas."
                    ),
                    (
                        "- Si usas una memoria recuperada, pon "
                        "used_memory_context=true y cita sus memory_record_id en "
                        "memory_record_ids."
                    ),
                    (
                        "- Para cada recuerdo citado, rellena memory_record_uses "
                        "indicando si lo sigues, adaptas, contradices o ignoras."
                    ),
                    (
                        "- Si un recuerdo es boundary_case o warning, explica "
                        "en risk_mitigation como evitas repetir exactamente su "
                        "fallo."
                    ),
                    (
                        "- Si propones una accion parecida a un caso frontera, "
                        "debes justificar por que la magnitud del cambio no "
                        "repite la sobrecorreccion."
                    ),
                    (
                        "- Si la memoria recuperada contiene source_type="
                        "decision_episode o tags como "
                        "compare_model_family_after_partial_threshold_gain, "
                        "no limites el analisis al umbral: considera cambiar "
                        "de familia de modelo dentro de los modelos soportados."
                    ),
                    (
                        "- Cuando el ajuste de threshold_quantile haya dado "
                        "solo una mejora parcial, rellena comparison_candidates "
                        "con alternativas soportadas para dejar evidencia de "
                        "la comparacion razonada."
                    ),
                    (
                        "- Si esa memoria de mejora parcial aparece y la "
                        "configuracion previa usa isolation_forest, trata "
                        "pca_reconstruction_error como retry_config preferente; "
                        "si no la eliges, explica por que en rationale y "
                        "learning_summary."
                    ),
                    (
                        "- Si memory_retry_guidance.model_family_shift_recommended "
                        "es true, la decision debe ser una de estas dos: ejecutar "
                        "pca_reconstruction_error como retry_config, o parar con "
                        "should_retry=false. No repitas otro retry basado solo en "
                        "threshold_quantile de isolation_forest."
                    ),
                    (
                        "- Revisa con cuidado la direccion numerica de los "
                        "cuantiles: 0.95 es menor que 0.99. No afirmes que "
                        "0.95 es mayor que 0.99 ni que un quantile 0.99 es bajo."
                    ),
                    (
                        "- Si la memoria no aporta evidencia util, pon "
                        "used_memory_context=false y deja memory_record_ids vacio."
                    ),
                    f"- decision_id debe ser: {state.run_id}:modeler_retry:{attempt_number:03d}",
                ]
            ),
        ),
    ]


def _modeler_json_template(state: TFMStateModel) -> dict[str, Any]:
    return {
        "agent_name": "modeler",
        "decision_id": f"{state.run_id}:modeler:{_modeler_turn(state):03d}",
        "rationale": "Motivo tecnico breve del modelo propuesto.",
        "confidence": 0.9,
        "modeling_config": DEFAULT_MODELING_CONFIG.model_dump(mode="json"),
        "train_split": "train",
        "validation_split": "validation",
        "expected_model_path": _expected_model_path(state, DEFAULT_MODELING_CONFIG),
        "comparison_candidates": [
            {
                "alternative_id": "pca_reconstruction_error",
                "modeling_config": DEFAULT_PCA_MODELING_CONFIG.model_dump(mode="json"),
                "rationale": "Baseline lineal por error de reconstruccion.",
                "expected_effect": (
                    "Comparar un detector interpretable y sensible a cambios "
                    "globales frente a Isolation Forest."
                ),
            },
            {
                "alternative_id": "iforest_conservative_threshold",
                "modeling_config": _modeling_config_with_updates(
                    DEFAULT_MODELING_CONFIG,
                    {"threshold_quantile": 1.0},
                ).model_dump(mode="json"),
                "rationale": "Variante mas conservadora del modelo base.",
                "expected_effect": "Reducir falsos positivos si se mantiene recall.",
            },
        ],
    }


def _modeler_retry_json_template(
    state: TFMStateModel,
    *,
    source_run_id: str,
    attempt_number: int,
    max_attempts: int,
    memory_context: RetrievedMemoryContext | None = None,
) -> dict[str, Any]:
    memory_ids = [
        item.record.memory_record_id
        for item in ([] if memory_context is None else memory_context.items)
    ]
    return {
        "agent_name": "modeler",
        "decision_id": f"{state.run_id}:modeler_retry:{attempt_number:03d}",
        "rationale": "Motivo tecnico para reintentar o parar.",
        "confidence": 0.85,
        "source_run_id": source_run_id,
        "attempt_number": attempt_number,
        "max_attempts": max_attempts,
        "should_retry": True,
        "learning_summary": (
            "Resumen de lo aprendido: tipo de fallo, causa probable y cambio "
            "propuesto."
        ),
        "retry_config": _retry_template_config(
            state,
            memory_context=memory_context,
        ),
        "expected_effect": "Efecto esperado sobre recall, FPR y F1.",
        "stop_reason": None,
        "memory_context_id": None if memory_context is None else memory_context.context_id,
        "used_memory_context": bool(memory_ids),
        "memory_record_ids": memory_ids[:3],
        "memory_usage_summary": (
            None
            if not memory_ids
            else "Como se usa la memoria recuperada para evitar repetir errores previos."
        ),
        "memory_record_uses": [
            {
                "memory_record_id": memory_id,
                "usage": "adapted",
                "influence_summary": (
                    "Que aprendizaje concreto aporta este recuerdo a la decision."
                ),
                "risk_mitigation": (
                    "Como se evita repetir el fallo descrito si el recuerdo es "
                    "un caso frontera o advertencia."
                ),
            }
            for memory_id in memory_ids[:3]
        ],
        "evidence_used": [
            "primary_metrics",
            "confusion_matrix",
            "false_negative_summary",
            "false_positive_summary",
            "threshold_convention",
        ],
        "comparison_candidates": _retry_comparison_candidates_template(state),
    }


def _retry_comparison_candidates_template(state: TFMStateModel) -> list[dict[str, Any]]:
    """Ejemplos comparables para que el LLM no razone solo sobre el umbral."""

    baseline = (
        state.modeling_config
        if state.modeling_config is not None
        and state.modeling_config.model_name == "isolation_forest"
        else DEFAULT_MODELING_CONFIG
    )
    return [
        {
            "alternative_id": "pca_reconstruction_error_candidate",
            "modeling_config": DEFAULT_PCA_MODELING_CONFIG.model_dump(mode="json"),
            "rationale": (
                "Comparar una familia lineal por error de reconstruccion cuando "
                "los cambios de umbral en Isolation Forest solo han dado una "
                "mejora parcial."
            ),
            "expected_effect": (
                "Comprobar si una geometria distinta reduce falsos positivos "
                "sin perder demasiadas anomalias."
            ),
        },
        {
            "alternative_id": "iforest_moderate_threshold_candidate",
            "modeling_config": _modeling_config_with_updates(
                baseline,
                {"threshold_quantile": 0.95},
            ).model_dump(mode="json"),
            "rationale": (
                "Mantener la familia actual con un ajuste moderado del umbral "
                "como punto de comparacion frente al cambio de modelo."
            ),
            "expected_effect": (
                "Aumentar recall respecto a un umbral muy conservador, "
                "vigilando el coste en FPR."
            ),
        },
    ]


def _state_summary_for_llm(state: TFMStateModel) -> dict[str, Any]:
    return {
        "thread_id": state.thread_id,
        "run_id": state.run_id,
        "current_stage": state.current_stage,
        "dataset": state.project_context.dataset,
        "objective": state.project_context.objective,
        "label_mode": state.project_context.label_mode,
        "main_channel": state.project_context.main_channel,
        "tensor_path": state.tensor_path,
        "splits_path": state.splits_path,
        "features_path": _features_path_for_state(state),
        "structuring_config": (
            None
            if state.structuring_config is None
            else state.structuring_config.model_dump(mode="json")
        ),
        "dataset_profile": (
            None
            if state.dataset_profile is None
            else state.dataset_profile.model_dump(mode="json")
        ),
        "artifact_types": [artifact.artifact_type for artifact in state.artifacts],
    }


def _features_path_for_state(state: TFMStateModel) -> str | None:
    for artifact in reversed(state.artifacts):
        if artifact.artifact_type == "features":
            return artifact.path
    if state.tensor_path:
        return str(Path(state.tensor_path).with_name("windows_features.csv"))
    return None


def _features_summary_for_llm(features_path: str | None) -> dict[str, Any]:
    if not features_path:
        return {"available": False}
    path = Path(features_path)
    if not path.exists():
        return {"available": False, "path": features_path}

    try:
        with path.open(newline="", encoding="utf-8") as file:
            reader = csv.DictReader(file)
            columns = reader.fieldnames or []
            split_counts: Counter[str] = Counter()
            label_counts: Counter[str] = Counter()
            sample_rows: list[dict[str, str]] = []
            n_rows = 0
            for row in reader:
                n_rows += 1
                split = row.get("split")
                label = row.get("label")
                if split:
                    split_counts[split] += 1
                if label:
                    label_counts[label] += 1
                if len(sample_rows) < 3:
                    sample_rows.append(
                        {
                            key: value
                            for key, value in row.items()
                            if key in {"window_id", "split", "label", "target"}
                        }
                    )
    except (OSError, csv.Error) as exc:
        return {"available": False, "path": features_path, "error": str(exc)}

    feature_columns = [column for column in columns if column not in METADATA_COLUMNS]
    return {
        "available": True,
        "path": features_path,
        "n_rows": n_rows,
        "n_columns": len(columns),
        "feature_columns": feature_columns,
        "split_counts": dict(split_counts),
        "label_counts": dict(label_counts),
        "sample_rows": sample_rows,
    }


def _memory_context_for_llm(
    memory_context: RetrievedMemoryContext | None,
) -> dict[str, Any]:
    if memory_context is None:
        return {
            "available": False,
            "reason": "memory retrieval disabled for this retry decision",
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
                "content_excerpt": item.record.content[:900],
                "metrics": item.record.metrics,
                "tags": item.record.tags[:12],
            }
            for item in memory_context.items
        ],
    }


def _memory_retry_guidance_for_llm(
    memory_context: RetrievedMemoryContext | None,
) -> dict[str, Any]:
    model_family_shift = _memory_suggests_model_family_retry(memory_context)
    if not model_family_shift:
        return {
            "model_family_shift_recommended": False,
            "preferred_retry_config": None,
            "avoid_threshold_only_isolation_forest_retry": False,
            "reason": (
                "No retrieved memory indicates that threshold-only tuning has "
                "already produced a rejected partial improvement."
            ),
            "source_memory_record_ids": [],
        }
    source_ids = [
        item.record.memory_record_id
        for item in ([] if memory_context is None else memory_context.items)
        if _record_suggests_model_family_retry(item.record)
    ]
    return {
        "model_family_shift_recommended": True,
        "preferred_retry_config": DEFAULT_PCA_MODELING_CONFIG.model_dump(mode="json"),
        "avoid_threshold_only_isolation_forest_retry": True,
        "reason": (
            "Retrieved memory shows that threshold-only Isolation Forest tuning "
            "already produced only a partial improvement and remained rejected. "
            "The next executable hypothesis should test the supported PCA "
            "reconstruction-error family, or stop if the agent judges that no "
            "real improvement margin remains."
        ),
        "source_memory_record_ids": source_ids,
    }


def _validate_modeling_decision_bounds(
    state: TFMStateModel,
    decision: ModelingDecision,
) -> None:
    _validate_single_modeling_decision(state, decision)
    for candidate in decision.comparison_candidates:
        _validate_supported_modeling_config(candidate.modeling_config)


def _validate_single_modeling_decision(
    state: TFMStateModel,
    decision: ModelingDecision,
) -> None:
    config = decision.modeling_config
    if config.model_name not in SUPPORTED_MODEL_NAMES:
        raise ValueError(
            "model_name must be one of "
            f"{', '.join(sorted(SUPPORTED_MODEL_NAMES))}"
        )
    if config.random_state != 42:
        raise ValueError("random_state must be 42 for reproducible MVP runs")
    if decision.train_split != "train":
        raise ValueError("train_split must be train")
    if decision.validation_split not in {None, "validation"}:
        raise ValueError("validation_split must be validation or null")
    expected_model_path = _expected_model_path(state, config)
    if decision.expected_model_path != expected_model_path:
        raise ValueError(f"expected_model_path must be {expected_model_path}")
    _validate_supported_modeling_config(config)


def _validate_modeling_retry_decision_bounds(
    state: TFMStateModel,
    decision: ModelingRetryDecision,
    *,
    memory_context: RetrievedMemoryContext | None = None,
) -> None:
    if decision.agent_name != "modeler":
        raise ValueError("retry decision must come from modeler")
    if decision.memory_context_id is not None:
        if memory_context is None:
            raise ValueError("memory_context_id was declared but no memory was provided")
        if decision.memory_context_id != memory_context.context_id:
            raise ValueError("memory_context_id does not match retrieved context")
    if decision.used_memory_context:
        if memory_context is None or not memory_context.items:
            raise ValueError("used_memory_context=true requires retrieved memory")
        available_record_ids = {
            item.record.memory_record_id for item in memory_context.items
        }
        unknown_ids = sorted(set(decision.memory_record_ids) - available_record_ids)
        if unknown_ids:
            raise ValueError(
                "memory_record_ids were not retrieved: " + ", ".join(unknown_ids)
            )
        if not decision.memory_usage_summary:
            raise ValueError("used memory requires memory_usage_summary")
        declared_use_ids = {item.memory_record_id for item in decision.memory_record_uses}
        if declared_use_ids != set(decision.memory_record_ids):
            raise ValueError(
                "memory_record_uses must describe exactly the cited memory_record_ids"
            )
        records_by_id = {
            item.record.memory_record_id: item.record for item in memory_context.items
        }
        for use in decision.memory_record_uses:
            record = records_by_id[use.memory_record_id]
            if record.memory_role in {"boundary_case", "warning"}:
                if not use.risk_mitigation:
                    raise ValueError(
                        "boundary or warning memory requires risk_mitigation"
                    )
    if decision.should_retry:
        if decision.retry_config is None:
            raise ValueError("retry_config is required when should_retry=true")
        _validate_supported_modeling_config(decision.retry_config)
        if decision.retry_config.random_state != 42:
            raise ValueError("random_state must be 42 for retry runs")
        if _modeling_config_key(decision.retry_config) == _modeling_config_key(
            state.modeling_config
        ):
            raise ValueError("retry_config must differ from the failed config")
    for candidate in decision.comparison_candidates:
        _validate_supported_modeling_config(candidate.modeling_config)


def _validate_supported_modeling_config(config: ModelingConfig) -> None:
    if config.model_name not in SUPPORTED_MODEL_NAMES:
        raise ValueError(
            "unsupported model_name: "
            f"{config.model_name}; supported: {', '.join(sorted(SUPPORTED_MODEL_NAMES))}"
        )
    supported_hyperparameters = SUPPORTED_HYPERPARAMETERS_BY_MODEL[config.model_name]
    unsupported = sorted(set(config.hyperparameters) - supported_hyperparameters)
    if unsupported:
        raise ValueError(f"unsupported hyperparameters: {', '.join(unsupported)}")

    threshold_quantile = config.hyperparameters.get("threshold_quantile")
    if threshold_quantile is not None:
        threshold = float(threshold_quantile)
        if not 0.0 < threshold <= 1.0:
            raise ValueError("threshold_quantile must be in (0, 1]")

    n_jobs = config.hyperparameters.get("n_jobs")
    if n_jobs is not None and n_jobs != 1:
        raise ValueError("n_jobs must be 1 for the local MVP")

    n_estimators = config.hyperparameters.get("n_estimators")
    if n_estimators is not None:
        if isinstance(n_estimators, bool) or not isinstance(n_estimators, int):
            raise ValueError("n_estimators must be an integer")
        if not 10 <= n_estimators <= 500:
            raise ValueError("n_estimators must be between 10 and 500")

    if config.model_name == "pca_reconstruction_error":
        n_components = config.hyperparameters.get("n_components")
        if n_components is not None:
            if isinstance(n_components, bool):
                raise ValueError("n_components must be numeric")
            if isinstance(n_components, int):
                if n_components < 1:
                    raise ValueError("n_components integer must be >= 1")
            elif isinstance(n_components, float):
                if not 0.0 < n_components <= 1.0:
                    raise ValueError("n_components float must be in (0, 1]")
            else:
                raise ValueError("n_components must be numeric")


def _expected_model_path(state: TFMStateModel, config: ModelingConfig) -> str:
    return f"codigo/models/{state.project_context.dataset}/{config.model_name}.joblib"


def _retry_template_config(
    state: TFMStateModel,
    *,
    memory_context: RetrievedMemoryContext | None = None,
) -> dict[str, Any] | None:
    if (
        _memory_suggests_model_family_retry(memory_context)
        and (
            state.modeling_config is None
            or state.modeling_config.model_name == "isolation_forest"
        )
    ):
        return DEFAULT_PCA_MODELING_CONFIG.model_dump(mode="json")
    if state.modeling_config is None:
        return DEFAULT_MODELING_CONFIG.model_dump(mode="json")
    return state.modeling_config.model_dump(mode="json")


def _memory_suggests_model_family_retry(
    memory_context: RetrievedMemoryContext | None,
) -> bool:
    if memory_context is None:
        return False
    for item in memory_context.items:
        if _record_suggests_model_family_retry(item.record):
            return True
    return False


def _record_suggests_model_family_retry(record: Any) -> bool:
    tags = set(record.tags)
    if "compare_model_family_after_partial_threshold_gain" in tags:
        return True
    if (
        record.source_type == "decision_episode"
        and record.outcome == "partially_supported"
        and (
            "recall_below_target" in tags
            or "false_positive_rate_above_target" in tags
        )
    ):
        return True
    return {
        "threshold_adjustment_can_reduce_false_negatives",
        "recall_gain_must_be_checked_against_fpr",
    }.issubset(tags)


def _current_modeling_config_json(state: TFMStateModel) -> dict[str, Any] | None:
    if state.modeling_config is None:
        return None
    return state.modeling_config.model_dump(mode="json")


def _modeling_config_key(config: ModelingConfig | None) -> str | None:
    if config is None:
        return None
    return json.dumps(config.model_dump(mode="json"), sort_keys=True)


def _fallback_learning_summary(failure_analysis: dict[str, Any]) -> str:
    failure_modes = failure_analysis.get("failure_modes") or ["unknown_failure"]
    return (
        "Failure analysis found "
        f"{', '.join(str(item) for item in failure_modes)}, but no validated "
        "LLM retry decision was available."
    )


def _modeling_config_with_updates(
    config: ModelingConfig,
    updates: dict[str, Any],
) -> ModelingConfig:
    payload = config.model_dump(mode="json")
    hyperparameters = dict(payload["hyperparameters"])
    hyperparameters.update(updates)
    return ModelingConfig(
        model_name=payload["model_name"],
        random_state=payload["random_state"],
        hyperparameters=hyperparameters,
    )


def _modeler_turn(state: TFMStateModel) -> int:
    return 1 + sum(message.name == "modeler" for message in state.messages)
