"""Supervisor LLM con fallback determinista y salida Pydantic."""

from __future__ import annotations

import json
import os
from typing import Any

from pydantic import ValidationError

from codigo.app.schemas.agent_decisions import (
    AgentHypothesis,
    DecisionGenerationTrace,
    SupervisorDecision,
    require_agent_hypothesis,
)
from codigo.app.schemas.state import TFMStateModel
from codigo.app.services.llm import (
    JSONLLMClient,
    LLMCallError,
    LLMMessage,
    get_default_json_llm_client,
)


STAGE_PLAN = {
    "initialized": ("dataset_manifest", "manifest_executor", ["raw_path"]),
    "dataset_manifest": ("dataset_manifest", "manifest_executor", ["raw_path"]),
    "profiling": ("profiling", "profiler_executor", ["manifest_path"]),
    "evaluation": ("evaluation", "evaluator", ["predictions_artifact"]),
}


def decide_supervisor_action(
    state: TFMStateModel,
    *,
    llm_client: JSONLLMClient | None = None,
    use_llm: bool | None = None,
) -> SupervisorDecision:
    """Decide el siguiente nodo usando LLM cuando este habilitado."""

    should_use_llm = _should_use_llm(llm_client, use_llm)
    if should_use_llm:
        attempt_tracker = [0]
        try:
            client = llm_client or get_default_json_llm_client()
            return decide_supervisor_action_with_llm(
                state,
                client,
                _attempt_tracker=attempt_tracker,
            )
        except (ValidationError, ValueError) as exc:
            fallback = decide_supervisor_action_deterministic(state)
            fallback.rationale = (
                f"{fallback.rationale} Guardrail correction after invalid "
                f"LLM supervisor decision: {exc}"
            )
            fallback.confidence = min(fallback.confidence, 0.82)
            failed_attempt_index = max(attempt_tracker[0], 1)
            fallback.generation_trace = DecisionGenerationTrace.for_decision(
                fallback.decision_id,
                origin="guardrail_fallback",
                attempt_index=failed_attempt_index + 1,
                validation_status="fallback_applied",
                fallback_cause=f"{type(exc).__name__}: {exc}",
                fallback_from_attempt_index=failed_attempt_index,
            )
            return fallback
        except LLMCallError as exc:
            fallback = decide_supervisor_action_deterministic(state)
            fallback.rationale = f"{fallback.rationale} Fallback after LLM failure: {exc}"
            fallback.confidence = min(fallback.confidence, 0.7)
            failed_attempt_index = max(attempt_tracker[0], 1)
            fallback.generation_trace = DecisionGenerationTrace.for_decision(
                fallback.decision_id,
                origin="guardrail_fallback",
                attempt_index=failed_attempt_index + 1,
                validation_status="fallback_applied",
                fallback_cause=f"{type(exc).__name__}: {exc}",
                fallback_from_attempt_index=failed_attempt_index,
            )
            return fallback

    return decide_supervisor_action_deterministic(state)


def decide_supervisor_action_with_llm(
    state: TFMStateModel,
    llm_client: JSONLLMClient,
    *,
    _attempt_tracker: list[int] | None = None,
) -> SupervisorDecision:
    """Solicita una decision al LLM y la valida contra el contrato."""

    attempt_tracker = _attempt_tracker if _attempt_tracker is not None else [0]
    messages = _supervisor_messages(state)
    schema = SupervisorDecision.model_json_schema()
    attempt_tracker[0] = 1
    payload = llm_client.complete_json(
        messages,
        json_schema=schema,
    )
    try:
        decision = _validated_supervisor_decision_from_payload(state, payload)
    except (ValidationError, ValueError) as exc:
        attempt_tracker[0] = 2
        repaired_payload = llm_client.complete_json(
            _supervisor_contract_repair_messages(
                state,
                messages,
                invalid_payload=payload,
                validation_error=exc,
            ),
            json_schema=schema,
        )
        decision = _validated_supervisor_decision_from_payload(state, repaired_payload)
        decision.generation_trace = DecisionGenerationTrace.for_decision(
            decision.decision_id,
            origin="llm",
            attempt_index=2,
            validation_status="repaired",
        )
        return decision
    decision.generation_trace = DecisionGenerationTrace.for_decision(
        decision.decision_id,
        origin="llm",
    )
    return decision


def decide_supervisor_action_deterministic(state: TFMStateModel) -> SupervisorDecision:
    """Fallback reproducible para enrutar el MVP si el LLM no esta disponible."""

    decision_id = f"{state.run_id}:supervisor:{_supervisor_turn(state):03d}"
    if state.current_stage == "completed":
        return _terminal_decision(
            state,
            decision_id,
            next_stage="completed",
            rationale="Pipeline already completed.",
            stop_reason="completed",
            confidence=1.0,
        )
    if state.current_stage == "failed":
        return _terminal_decision(
            state,
            decision_id,
            next_stage="failed",
            rationale="Pipeline is in failed stage; execution must stop.",
            stop_reason=_last_error_message(state) or "failed",
            confidence=1.0,
        )
    if state.current_stage == "reporting" and state.report_path is not None:
        return _terminal_decision(
            state,
            decision_id,
            next_stage="completed",
            rationale="Final technical report has been generated.",
            stop_reason=f"report generated: {state.report_path}",
            confidence=1.0,
        )

    plan = _plan_for_state(state)
    if plan is None:
        return _terminal_decision(
            state,
            decision_id,
            next_stage="failed",
            rationale=f"Stage {state.current_stage!r} is not implemented by the MVP supervisor.",
            stop_reason=f"unsupported stage: {state.current_stage}",
            confidence=0.95,
        )

    next_stage, next_node, required_inputs = plan
    missing = _missing_inputs(state, required_inputs)
    if missing:
        return _terminal_decision(
            state,
            decision_id,
            next_stage="failed",
            rationale=f"Supervisor cannot continue because required inputs are missing: {', '.join(missing)}.",
            stop_reason=f"missing required inputs: {', '.join(missing)}",
            confidence=1.0,
        )

    return SupervisorDecision(
        decision_id=decision_id,
        current_stage=state.current_stage,
        next_stage=next_stage,
        next_node=next_node,
        requires_human_review=False,
        stop_reason=None,
        rationale=f"Stage {state.current_stage!r} is ready; routing to {next_node}.",
        confidence=1.0,
        hypothesis=_supervisor_hypothesis(
            state,
            next_stage=next_stage,
            next_node=next_node,
            stop_reason=None,
        ),
        generation_trace=DecisionGenerationTrace.for_decision(
            decision_id,
            origin="deterministic",
        ),
    )


def _validated_supervisor_decision_from_payload(
    state: TFMStateModel,
    payload: dict[str, Any],
) -> SupervisorDecision:
    trusted_payload = dict(payload)
    trusted_payload.pop("generation_trace", None)
    decision = SupervisorDecision.model_validate(trusted_payload)
    _validate_supervisor_decision_bounds(state, decision)
    return decision


def _supervisor_contract_repair_messages(
    state: TFMStateModel,
    original_messages: list[LLMMessage],
    *,
    invalid_payload: dict[str, Any],
    validation_error: Exception,
) -> list[LLMMessage]:
    return [
        *original_messages,
        LLMMessage(
            role="assistant",
            content=json.dumps(invalid_payload, indent=2, ensure_ascii=True),
        ),
        LLMMessage(
            role="user",
            content="\n".join(
                [
                    "La transicion anterior no valida contra el supervisor.",
                    f"Error de validacion: {validation_error}",
                    (
                        "Corrige solo la hipotesis operativa, next_stage, next_node, "
                        "stop_reason y rationale si procede."
                    ),
                    "No cambies decision_id ni current_stage.",
                    "Transicion obligatoria:",
                    _allowed_transition_text(state),
                    "Reemite exclusivamente un unico objeto JSON valido.",
                ]
            ),
        ),
    ]


def _should_use_llm(
    llm_client: JSONLLMClient | None,
    use_llm: bool | None,
) -> bool:
    if use_llm is not None:
        return use_llm
    if llm_client is not None:
        return True
    return os.getenv("TFM_SUPERVISOR_MODE", "").strip().lower() == "llm"


def _supervisor_messages(state: TFMStateModel) -> list[LLMMessage]:
    state_summary = _state_summary_for_llm(state)
    allowed = _allowed_transition_text(state)
    return [
        LLMMessage(
            role="system",
            content=(
                "Eres el supervisor de un pipeline multiagente industrial. "
                "Tu tarea es decidir la siguiente fase, no ejecutar codigo ni "
                "transformar datos. Debes devolver exclusivamente un objeto JSON "
                "valido compatible con el esquema SupervisorDecision."
            ),
        ),
        LLMMessage(
            role="user",
            content="\n".join(
                [
                    "Estado ligero del pipeline:",
                    json.dumps(state_summary, indent=2, ensure_ascii=True),
                    "",
                    "Transicion permitida para este estado:",
                    allowed,
                    "",
                    "Formato JSON esperado:",
                    json.dumps(_supervisor_json_template(state), indent=2, ensure_ascii=True),
                    "",
                    "Reglas:",
                    "- No incluyas texto fuera del JSON.",
                    "- No inventes nodos ni fases.",
                    "- Si la decision no es terminal, next_node no puede ser null.",
                    "- Si la decision es terminal, stop_reason no puede ser null.",
                    "- requires_human_review debe ser false en este MVP local.",
                    f"- decision_id debe ser: {state.run_id}:supervisor:{_supervisor_turn(state):03d}",
                ]
            ),
        ),
    ]


def _supervisor_json_template(state: TFMStateModel) -> dict[str, Any]:
    transition = decide_supervisor_action_deterministic(state)
    return {
        "agent_name": "supervisor",
        "decision_id": f"{state.run_id}:supervisor:{_supervisor_turn(state):03d}",
        "rationale": "Motivo breve y tecnico de la decision.",
        "confidence": 0.9,
        "hypothesis": transition.hypothesis.model_dump(mode="json"),
        "current_stage": state.current_stage,
        "next_stage": transition.next_stage,
        "next_node": transition.next_node,
        "requires_human_review": False,
        "stop_reason": transition.stop_reason,
    }


def _state_summary_for_llm(state: TFMStateModel) -> dict[str, Any]:
    return {
        "thread_id": state.thread_id,
        "run_id": state.run_id,
        "current_stage": state.current_stage,
        "next_node": state.next_node,
        "project_context": state.project_context.model_dump(mode="json"),
        "paths_present": {
            "raw_path": bool(state.raw_path),
            "manifest_path": bool(state.manifest_path),
            "profile_path": bool(state.profile_path),
            "clean_path": bool(state.clean_path),
            "tensor_path": bool(state.tensor_path),
            "splits_path": bool(state.splits_path),
            "report_path": bool(state.report_path),
        },
        "artifact_types": [artifact.artifact_type for artifact in state.artifacts],
        "error_count": len(state.errors),
        "last_error": _last_error_message(state),
        "metrics": None if state.metrics is None else state.metrics.model_dump(mode="json"),
    }


def _allowed_transition_text(state: TFMStateModel) -> str:
    if state.current_stage in {"completed", "failed"}:
        return (
            f"Decision terminal obligatoria: next_stage='{state.current_stage}', "
            "next_node=null y stop_reason no nulo."
        )
    if state.current_stage == "reporting" and state.report_path is not None:
        return (
            "Decision terminal obligatoria: next_stage='completed', "
            "next_node=null y stop_reason debe mencionar el informe generado."
        )
    plan = _plan_for_state(state)
    if plan is None:
        return "Decision terminal obligatoria: next_stage='failed' por fase no soportada."
    next_stage, next_node, required_inputs = plan
    missing = _missing_inputs(state, required_inputs)
    if missing:
        return (
            "Decision terminal obligatoria: next_stage='failed', next_node=null, "
            f"stop_reason debe mencionar entradas ausentes: {', '.join(missing)}."
        )
    return (
        f"Decision no terminal obligatoria: next_stage='{next_stage}', "
        f"next_node='{next_node}', stop_reason=null."
    )


def _validate_supervisor_decision_bounds(
    state: TFMStateModel,
    decision: SupervisorDecision,
) -> None:
    require_agent_hypothesis(
        decision,
        allowed_kinds={"routing_readiness"},
    )
    if decision.current_stage != state.current_stage:
        raise ValueError("LLM supervisor decision current_stage does not match state")
    if decision.requires_human_review:
        raise ValueError("human review is not enabled in the local MVP")

    if state.current_stage in {"completed", "failed"}:
        if decision.next_stage != state.current_stage or decision.next_node is not None:
            raise ValueError("terminal stage must remain terminal")
        return
    if state.current_stage == "reporting" and state.report_path is not None:
        if decision.next_stage != "completed" or decision.next_node is not None:
            raise ValueError("completed report must route to completed")
        return

    plan = _plan_for_state(state)
    if plan is None:
        if decision.next_stage != "failed" or decision.next_node is not None:
            raise ValueError("unsupported stage must route to failed")
        return

    next_stage, next_node, required_inputs = plan
    missing = _missing_inputs(state, required_inputs)
    if missing:
        if decision.next_stage != "failed" or decision.next_node is not None:
            raise ValueError("missing inputs must route to failed")
        return

    if decision.next_stage != next_stage or decision.next_node != next_node:
        raise ValueError(
            f"invalid transition for stage {state.current_stage}: "
            f"{decision.next_stage}/{decision.next_node}"
        )


def _plan_for_state(state: TFMStateModel) -> tuple[str, str, list[str]] | None:
    if state.current_stage == "cleaning":
        if state.cleaning_config is None:
            return ("cleaning", "cleaner_agent", ["manifest_path", "profile_path"])
        return ("cleaning", "cleaning_executor", ["manifest_path", "profile_path"])
    if state.current_stage == "structuring":
        if state.structuring_config is None:
            return ("structuring", "structuring_agent", ["clean_path"])
        return ("structuring", "structuring_executor", ["clean_path"])
    if state.current_stage == "modeling":
        if state.modeling_config is None:
            return ("modeling", "modeling_agent", ["features_artifact"])
        return ("modeling", "modeling_executor", ["features_artifact"])
    if state.current_stage == "evaluation":
        if state.metrics is None:
            return ("evaluation", "evaluator", ["predictions_artifact"])
        if state.evaluation is None:
            return ("evaluation", "evaluation_agent", ["metrics"])
        return ("reporting", "report_writer", ["evaluation"])
    if state.current_stage == "reporting":
        if state.report_path is None:
            return ("reporting", "report_writer", ["evaluation"])
        return None
    return STAGE_PLAN.get(state.current_stage)


def _terminal_decision(
    state: TFMStateModel,
    decision_id: str,
    *,
    next_stage: str,
    rationale: str,
    stop_reason: str,
    confidence: float,
) -> SupervisorDecision:
    return SupervisorDecision(
        decision_id=decision_id,
        current_stage=state.current_stage,
        next_stage=next_stage,
        next_node=None,
        requires_human_review=False,
        stop_reason=stop_reason,
        rationale=rationale,
        confidence=confidence,
        hypothesis=_supervisor_hypothesis(
            state,
            next_stage=next_stage,
            next_node=None,
            stop_reason=stop_reason,
        ),
        generation_trace=DecisionGenerationTrace.for_decision(
            decision_id,
            origin="deterministic",
        ),
    )


def _supervisor_hypothesis(
    state: TFMStateModel,
    *,
    next_stage: str,
    next_node: str | None,
    stop_reason: str | None,
) -> AgentHypothesis:
    target = next_node or next_stage
    terminal = next_node is None
    return AgentHypothesis(
        kind="routing_readiness",
        statement=(
            f"El estado actual permite cerrar el flujo como {next_stage!r} de "
            "forma coherente con sus evidencias persistidas."
            if terminal
            else (
                f"El estado actual contiene los prerrequisitos para enrutar a "
                f"{target!r} sin una transicion invalida."
            )
        ),
        scope=(
            f"Run {state.run_id}; etapa {state.current_stage}; decision de "
            "enrutamiento, no resultado interno del nodo siguiente."
        ),
        evidence_cutoff=(
            "Estado y artefactos persistidos antes de ejecutar la transicion propuesta."
        ),
        expected_observation=(
            f"El flujo permanece terminal en {next_stage!r} con motivo trazable."
            if terminal
            else (
                f"El nodo {target!r} acepta el estado y produce la siguiente "
                "transicion o artefacto previsto."
            )
        ),
        falsification_criterion=(
            "El cierre contradice el estado o carece de una causa terminal verificable."
            if terminal
            else (
                "La transicion es rechazada, faltaba un prerrequisito detectable "
                "o el flujo entra en un ciclo sin progreso."
            )
        ),
        evidence_refs=[
            "state:current_stage",
            "state:available_artifacts",
            *(["state:stop_reason"] if stop_reason else []),
        ],
        risk_notes=[
            "La ruta esta acotada por el grafo y no demuestra autonomia abierta del supervisor."
        ],
        assumptions=[
            "Un fallo interno imprevisible del ejecutor no refuta por si solo una ruta valida."
        ],
    )


def _missing_inputs(state: TFMStateModel, required_inputs: list[str]) -> list[str]:
    missing: list[str] = []
    for item in required_inputs:
        if item == "features_artifact":
            if not _has_artifact(state, "features") and not state.tensor_path:
                missing.append(item)
            continue
        if item == "predictions_artifact":
            if not _has_artifact(state, "predictions"):
                missing.append(item)
            continue
        if item == "metrics":
            if state.metrics is None:
                missing.append(item)
            continue
        if item == "evaluation":
            if state.evaluation is None:
                missing.append(item)
            continue
        if getattr(state, item) is None:
            missing.append(item)
    return missing


def _has_artifact(state: TFMStateModel, artifact_type: str) -> bool:
    return any(artifact.artifact_type == artifact_type for artifact in state.artifacts)


def _last_error_message(state: TFMStateModel) -> str | None:
    if not state.errors:
        return None
    return state.errors[-1].message


def _supervisor_turn(state: TFMStateModel) -> int:
    return 1 + sum(message.role == "supervisor" for message in state.messages)
