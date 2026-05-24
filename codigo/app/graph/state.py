"""Estado compartido por el grafo LangGraph."""

from __future__ import annotations

from typing import Any, TypedDict

from codigo.app.schemas.state import ProjectContext, TFMStateModel


class TFMState(TypedDict):
    """Vista ligera del estado que circulara por LangGraph."""

    thread_id: str
    run_id: str
    current_stage: str
    next_node: str | None

    project_context: dict[str, Any]

    raw_path: str
    manifest_path: str | None
    profile_path: str | None
    extracted_signals_path: str | None
    clean_path: str | None
    tensor_path: str | None
    splits_path: str | None
    report_path: str | None

    messages: list[dict[str, Any]]
    dataset_profile: dict[str, Any] | None

    cleaning_config: dict[str, Any] | None
    structuring_config: dict[str, Any] | None
    modeling_config: dict[str, Any] | None

    metrics: dict[str, Any] | None
    evaluation: dict[str, Any] | None
    errors: list[dict[str, Any]]
    human_approval: dict[str, Any] | None
    artifacts: list[dict[str, Any]]


def validate_state(state: dict[str, Any]) -> TFMStateModel:
    """Valida un estado procedente del grafo y devuelve el modelo canonico."""

    return TFMStateModel.model_validate(state)


def create_initial_cwru_state(
    *,
    thread_id: str,
    run_id: str,
    raw_path: str = "codigo/data/raw/cwru_bearing/mat",
) -> TFMState:
    """Crea el estado inicial del MVP sobre CWRU Bearing Dataset."""

    state = TFMStateModel(
        thread_id=thread_id,
        run_id=run_id,
        current_stage="dataset_manifest",
        next_node="manifest_executor",
        project_context=ProjectContext(
            dataset="cwru_bearing",
            machine_type="electric_motor_bearing",
            signal_type="vibration",
            objective="binary_anomaly_detection",
            target_sample_rate_hz=12000,
            main_channel="DE_time",
            label_mode="binary_anomaly",
        ),
        raw_path=raw_path,
        manifest_path=None,
        profile_path=None,
        extracted_signals_path=None,
        clean_path=None,
        tensor_path=None,
        splits_path=None,
        report_path=None,
        messages=[],
        dataset_profile=None,
        cleaning_config=None,
        structuring_config=None,
        modeling_config=None,
        metrics=None,
        evaluation=None,
        errors=[],
        human_approval=None,
        artifacts=[],
    )
    return TFMState(**state.to_langgraph_state())
