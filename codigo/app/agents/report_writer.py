"""Agente redactor LLM con fallback seguro."""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import ValidationError

from codigo.app.schemas.agent_decisions import ReportDecision, ReportSection
from codigo.app.schemas.state import TFMStateModel
from codigo.app.services.llm import (
    JSONLLMClient,
    LLMCallError,
    LLMMessage,
    get_default_json_llm_client,
)


DEFAULT_REPORT_FORMAT = "markdown"
REQUIRED_SECTION_TITLES = [
    "Resumen ejecutivo",
    "Contexto y datos",
    "Configuraciones del pipeline",
    "Metricas y evaluacion",
    "Artefactos generados",
    "Limitaciones y siguientes pasos",
]


def decide_report_action(
    state: TFMStateModel,
    *,
    llm_client: JSONLLMClient | None = None,
    use_llm: bool | None = None,
) -> ReportDecision:
    """Decide la estructura del informe usando LLM cuando este habilitado."""

    should_use_llm = _should_use_llm(llm_client, use_llm)
    if should_use_llm:
        try:
            client = llm_client or get_default_json_llm_client()
            return decide_report_action_with_llm(state, client)
        except (LLMCallError, ValidationError, ValueError) as exc:
            fallback = decide_report_action_deterministic(state)
            fallback.rationale = f"{fallback.rationale} Fallback after LLM failure: {exc}"
            fallback.confidence = min(fallback.confidence, 0.7)
            return fallback

    return decide_report_action_deterministic(state)


def decide_report_action_with_llm(
    state: TFMStateModel,
    llm_client: JSONLLMClient,
) -> ReportDecision:
    """Solicita al LLM una ReportDecision y valida sus limites."""

    payload = llm_client.complete_json(
        _report_writer_messages(state),
        json_schema=ReportDecision.model_json_schema(),
    )
    decision = ReportDecision.model_validate(payload)
    _validate_report_decision_bounds(state, decision)
    return decision


def decide_report_action_deterministic(state: TFMStateModel) -> ReportDecision:
    """Fallback reproducible para generar el informe final Markdown."""

    return ReportDecision(
        decision_id=f"{state.run_id}:report_writer:{_report_turn(state):03d}",
        rationale=(
            "Fallback report policy: generate a concise Markdown report with "
            "context, pipeline configuration, metrics, artifacts and limitations."
        ),
        confidence=1.0,
        output_path=_default_report_path(state),
        output_format=DEFAULT_REPORT_FORMAT,
        sections=_default_sections(state),
    )


def _should_use_llm(
    llm_client: JSONLLMClient | None,
    use_llm: bool | None,
) -> bool:
    if use_llm is not None:
        return use_llm
    if llm_client is not None:
        return True
    return os.getenv("TFM_REPORT_WRITER_MODE", "").strip().lower() == "llm"


def _report_writer_messages(state: TFMStateModel) -> list[LLMMessage]:
    return [
        LLMMessage(
            role="system",
            content=(
                "Eres el agente redactor de un pipeline industrial de "
                "deteccion de anomalias. Tu tarea es decidir la estructura del "
                "informe tecnico final. No puedes inventar rutas, ejecutar "
                "codigo ni escribir el informe directamente. Debes devolver "
                "exclusivamente un objeto JSON compatible con ReportDecision."
            ),
        ),
        LLMMessage(
            role="user",
            content="\n".join(
                [
                    "Contexto ligero:",
                    json.dumps(_state_summary_for_llm(state), indent=2, ensure_ascii=True),
                    "",
                    "Formato JSON esperado:",
                    json.dumps(_report_json_template(state), indent=2, ensure_ascii=True),
                    "",
                    "Reglas:",
                    "- No incluyas texto fuera del JSON.",
                    "- output_format debe ser markdown.",
                    f"- output_path debe ser {_default_report_path(state)}.",
                    "- Incluye todas las secciones obligatorias.",
                    "- source_paths solo puede contener rutas ya presentes en el estado.",
                    f"- decision_id debe ser: {state.run_id}:report_writer:{_report_turn(state):03d}",
                ]
            ),
        ),
    ]


def _report_json_template(state: TFMStateModel) -> dict[str, Any]:
    return {
        "agent_name": "report_writer",
        "decision_id": f"{state.run_id}:report_writer:{_report_turn(state):03d}",
        "rationale": "Motivo tecnico breve de la estructura propuesta.",
        "confidence": 0.9,
        "output_path": _default_report_path(state),
        "output_format": DEFAULT_REPORT_FORMAT,
        "sections": [section.model_dump(mode="json") for section in _default_sections(state)],
    }


def _state_summary_for_llm(state: TFMStateModel) -> dict[str, Any]:
    return {
        "thread_id": state.thread_id,
        "run_id": state.run_id,
        "dataset": state.project_context.dataset,
        "objective": state.project_context.objective,
        "metrics": None if state.metrics is None else state.metrics.model_dump(mode="json"),
        "evaluation": None if state.evaluation is None else state.evaluation.model_dump(mode="json"),
        "artifact_paths": [artifact.path for artifact in state.artifacts],
        "report_path": state.report_path,
    }


def _default_sections(state: TFMStateModel) -> list[ReportSection]:
    metrics_path = None if state.metrics is None else state.metrics.metrics_path
    artifact_paths = [artifact.path for artifact in state.artifacts]
    return [
        ReportSection(title="Resumen ejecutivo"),
        ReportSection(
            title="Contexto y datos",
            source_paths=[path for path in [state.manifest_path, state.profile_path] if path],
        ),
        ReportSection(title="Configuraciones del pipeline"),
        ReportSection(
            title="Metricas y evaluacion",
            include_metrics=True,
            source_paths=[path for path in [metrics_path] if path],
        ),
        ReportSection(
            title="Artefactos generados",
            include_artifacts=True,
            source_paths=artifact_paths,
        ),
        ReportSection(title="Limitaciones y siguientes pasos"),
    ]


def _validate_report_decision_bounds(
    state: TFMStateModel,
    decision: ReportDecision,
) -> None:
    if decision.output_format != DEFAULT_REPORT_FORMAT:
        raise ValueError("output_format must be markdown for the MVP")
    expected_path = _default_report_path(state)
    if decision.output_path != expected_path:
        raise ValueError(f"output_path must be {expected_path}")

    titles = [section.title for section in decision.sections]
    missing = [title for title in REQUIRED_SECTION_TITLES if title not in titles]
    if missing:
        raise ValueError(f"missing required report sections: {', '.join(missing)}")

    allowed_paths = _allowed_source_paths(state)
    for section in decision.sections:
        unsupported = sorted(set(section.source_paths) - allowed_paths)
        if unsupported:
            raise ValueError(
                f"unsupported source paths in section {section.title}: "
                f"{', '.join(unsupported)}"
            )


def _allowed_source_paths(state: TFMStateModel) -> set[str]:
    paths = {
        artifact.path
        for artifact in state.artifacts
    }
    for value in [
        state.manifest_path,
        state.profile_path,
        state.clean_path,
        state.tensor_path,
        state.splits_path,
        None if state.metrics is None else state.metrics.metrics_path,
    ]:
        if value:
            paths.add(value)
    return paths


def _default_report_path(state: TFMStateModel) -> str:
    return f"codigo/reports/{state.project_context.dataset}/{state.run_id}/final_report.md"


def _report_turn(state: TFMStateModel) -> int:
    return 1 + sum(
        message.role == "agent" and message.name == "report_writer"
        for message in state.messages
    )
