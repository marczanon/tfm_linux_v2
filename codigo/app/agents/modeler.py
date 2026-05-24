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
    METADATA_COLUMNS,
    SKLEARN_IFOREST_PARAMS,
)
from codigo.app.schemas.agent_decisions import ModelingDecision
from codigo.app.schemas.state import ModelingConfig, TFMStateModel
from codigo.app.services.llm import (
    JSONLLMClient,
    LLMCallError,
    LLMMessage,
    get_default_json_llm_client,
)


DEFAULT_MODEL_PATH = "codigo/models/cwru_bearing/isolation_forest.joblib"
SUPPORTED_MODEL_NAME = "isolation_forest"
SUPPORTED_HYPERPARAMETERS = SKLEARN_IFOREST_PARAMS | {"threshold_quantile"}


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
    _validate_modeling_decision_bounds(decision)
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
        expected_model_path=DEFAULT_MODEL_PATH,
    )


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
                    "- model_name debe ser isolation_forest para el MVP.",
                    "- random_state debe ser 42.",
                    "- train_split debe ser train.",
                    "- validation_split debe ser validation o null.",
                    "- Solo puedes usar hiperparametros soportados por el ejecutor.",
                    "- n_jobs debe ser 1 si se incluye.",
                    "- threshold_quantile debe estar en (0, 1].",
                    f"- expected_model_path debe ser: {DEFAULT_MODEL_PATH}",
                    f"- decision_id debe ser: {state.run_id}:modeler:{_modeler_turn(state):03d}",
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
        "expected_model_path": DEFAULT_MODEL_PATH,
    }


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


def _validate_modeling_decision_bounds(decision: ModelingDecision) -> None:
    config = decision.modeling_config
    if config.model_name != SUPPORTED_MODEL_NAME:
        raise ValueError(f"model_name must be {SUPPORTED_MODEL_NAME} for the MVP")
    if config.random_state != 42:
        raise ValueError("random_state must be 42 for reproducible MVP runs")
    if decision.train_split != "train":
        raise ValueError("train_split must be train")
    if decision.validation_split not in {None, "validation"}:
        raise ValueError("validation_split must be validation or null")
    if decision.expected_model_path != DEFAULT_MODEL_PATH:
        raise ValueError(f"expected_model_path must be {DEFAULT_MODEL_PATH}")
    _validate_supported_modeling_config(config)


def _validate_supported_modeling_config(config: ModelingConfig) -> None:
    unsupported = sorted(set(config.hyperparameters) - SUPPORTED_HYPERPARAMETERS)
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


def _modeler_turn(state: TFMStateModel) -> int:
    return 1 + sum(message.name == "modeler" for message in state.messages)
