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
from codigo.app.schemas.state import ModelingConfig, TFMStateModel
from codigo.app.services.llm import (
    JSONLLMClient,
    LLMCallError,
    LLMMessage,
    get_default_json_llm_client,
)


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
        ),
        json_schema=ModelingRetryDecision.model_json_schema(),
    )
    decision = ModelingRetryDecision.model_validate(payload)
    _validate_modeling_retry_decision_bounds(state, decision)
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
                    "Formato JSON esperado:",
                    json.dumps(
                        _modeler_retry_json_template(
                            state,
                            source_run_id=source_run_id,
                            attempt_number=attempt_number,
                            max_attempts=max_attempts,
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
                        "reintento permitido; si falla, el sistema debe detenerse."
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
) -> dict[str, Any]:
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
        "retry_config": _retry_template_config(state),
        "expected_effect": "Efecto esperado sobre recall, FPR y F1.",
        "stop_reason": None,
        "evidence_used": [
            "primary_metrics",
            "confusion_matrix",
            "false_negative_summary",
            "false_positive_summary",
            "threshold_convention",
        ],
        "comparison_candidates": [],
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
) -> None:
    if decision.agent_name != "modeler":
        raise ValueError("retry decision must come from modeler")
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


def _retry_template_config(state: TFMStateModel) -> dict[str, Any] | None:
    if state.modeling_config is None:
        return DEFAULT_MODELING_CONFIG.model_dump(mode="json")
    return state.modeling_config.model_dump(mode="json")


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
