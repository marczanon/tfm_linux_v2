"""Agente comun para revisiones causales de monitorizacion.

Los siete roles comparten un contrato estrecho en este modo. El backend fija
identidad, cutoff, capacidades y ausencia de memoria; el LLM solo formula una
hipotesis observable y recomienda una accion del catalogo permitido.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from codigo.app.schemas.agent_decisions import AgentName, DecisionGenerationTrace
from codigo.app.schemas.monitoring_replay import (
    CausalEvidenceCatalog,
    CausalInputView,
    MonitoringReviewDecision,
    MonitoringReviewRecommendedAction,
    MonitoringReviewRequest,
)
from codigo.app.schemas.reasoning import AgentHypothesis, AgentHypothesisKind
from codigo.app.services.llm import (
    JSONLLMClient,
    LLMCallError,
    LLMMessage,
    get_default_json_llm_client,
)
from codigo.app.services.nasa_ims_temporal_policy import (
    NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
)
from codigo.app.services.online_blind import unsupported_official_v2_claims
from codigo.app.services.monitoring_review_store import (
    build_causal_evidence_catalog,
    validate_causal_evidence_catalog,
)
from codigo.app.services.monitoring_replay import MonitoringReplayConflictError


ROLE_HYPOTHESIS_KIND: dict[AgentName, AgentHypothesisKind] = {
    "supervisor": "routing_readiness",
    "cleaner": "data_quality",
    "structurer": "temporal_representation",
    "modeler": "model_performance",
    "evaluator": "operational_acceptance",
    "report_writer": "report_grounding",
    "report_verifier": "report_fidelity",
}

ROLE_MISSION: dict[AgentName, str] = {
    "supervisor": (
        "encuadrar el trigger, priorizar la revision y comprobar si la evidencia "
        "permite continuar"
    ),
    "cleaner": (
        "revisar calidad sensorial, magnitudes, faltantes, discontinuidades y ruido"
    ),
    "structurer": (
        "revisar orden temporal, segmentos, gaps, persistencia y representacion"
    ),
    "modeler": (
        "juzgar score, umbral y comportamiento del modelo congelado sin reentrenar"
    ),
    "evaluator": (
        "interpretar riesgo, degradacion algoritimica e incertidumbre sin inventar "
        "un fallo fisico"
    ),
    "report_writer": (
        "sintetizar el episodio de forma breve, trazable y util para una persona"
    ),
    "report_verifier": (
        "contrastar los claims previos, sus evidencias y los limites metodologicos"
    ),
}

ALLOWED_ACTIONS: tuple[MonitoringReviewRecommendedAction, ...] = (
    "maintain_policy",
    "intensify_observation",
    "request_human_review",
    "pause_replay",
    "insufficient_evidence",
)

MONITORING_REVIEW_PROMPT_TEMPLATE_ID = "monitoring_review_prompt_v3"
MONITORING_REVIEW_RESPONSE_SCHEMA_ID = "monitoring_review_llm_response_v3"
MONITORING_REVIEW_ALLOWED_OPTIONS_ID = "monitoring_review_actions_v1"
MONITORING_REVIEW_DEFAULT_EVIDENCE_HANDLES = tuple(
    f"E{index:02d}" for index in range(1, 13)
)
MONITORING_REVIEW_SYSTEM_PROMPT = (
    "Eres el rol {agent_name} de una revision multiagente de monitorizacion "
    "industrial. Debes {role_mission}. Solo observas una vista causal hasta el "
    "cutoff. No puedes leer raw, ajustar, entrenar, ejecutar codigo, aplicar "
    "politicas ni usar memoria. Devuelve solo JSON compatible con el schema "
    "cerrado. Una ejecucion correcta no confirma por si sola la hipotesis."
)
MONITORING_REVIEW_RULE_TEMPLATES: tuple[str, ...] = (
    "hypothesis.kind debe ser {hypothesis_kind}.",
    "hypothesis.evidence_cutoff debe coincidir con {cutoff_snapshot_id}.",
    "Selecciona uno o mas handles exactos de {evidence_handles}.",
    (
        "Usa la misma lista ordenada de handles en decision.evidence_refs y "
        "hypothesis.evidence_refs; el servidor resolvera solo esa seleccion."
    ),
    "record_id, snapshot_id y causal_scope_ref no son referencias citables.",
    "recommended_action pertenece a {allowed_actions}.",
    "alternatives no repite la accion recomendada.",
    "memory_mode=off y policy_application_status=not_applied.",
    "No afirmes fallo fisico, onset, RUL ni tiempo real.",
    (
        "En todos los textos libres, incluido hypothesis.scope, describe solo "
        "evidencia, score, estado o alerta algoritmica del replay; no declares "
        "deteccion, diagnostico, degradacion u aprobacion fisica confirmada."
    ),
    "No incluyas Markdown ni texto fuera del JSON.",
)


def monitoring_review_contract_fingerprints(
    evidence_catalog: CausalEvidenceCatalog | None = None,
) -> dict[str, str]:
    """Devuelve los identificadores y hashes del protocolo efectivo del revisor.

    El despacho los fija en ``MonitoringReviewRequest`` para que una run no
    pueda aparentar que uso otro prompt, otro esquema o un catalogo de acciones
    distinto. El hash del prompt cubre las misiones y guardarrailes estables;
    los valores variables de sesion/cutoff pertenecen al request hasheado.
    """

    prompt_payload = {
        "template_id": MONITORING_REVIEW_PROMPT_TEMPLATE_ID,
        "roles": list(ROLE_MISSION),
        "role_missions": ROLE_MISSION,
        "hypothesis_kinds": ROLE_HYPOTHESIS_KIND,
        "system_prompt": MONITORING_REVIEW_SYSTEM_PROMPT,
        "rule_templates": MONITORING_REVIEW_RULE_TEMPLATES,
        "prompt_sections": (
            "Contexto cerrado",
            "Catalogo causal por registro",
            "Aportes previos",
            "Plantilla orientativa",
            "Reglas",
        ),
        "guardrails": [
            "causal_view_only",
            "no_raw_scan",
            "no_fit",
            "no_retrain",
            "no_code_execution",
            "memory_off",
            "policy_not_applied",
            "no_physical_failure_or_rul_claim",
            "official_v2_claims_scoped_in_all_free_text",
            "server_resolves_exact_selected_record_handles",
            "record_ids_hidden_from_generation",
        ],
        "catalog_schema_version": "causal_evidence_catalog_v1",
    }
    schema_payload = monitoring_review_llm_response_schema(evidence_catalog)
    options_payload = {
        "catalog_id": MONITORING_REVIEW_ALLOWED_OPTIONS_ID,
        "actions": list(ALLOWED_ACTIONS),
    }
    return {
        "prompt_template_id": MONITORING_REVIEW_PROMPT_TEMPLATE_ID,
        "prompt_template_sha256": _canonical_json_sha256(prompt_payload),
        "response_schema_id": MONITORING_REVIEW_RESPONSE_SCHEMA_ID,
        "response_schema_sha256": _canonical_json_sha256(schema_payload),
        "allowed_options_id": MONITORING_REVIEW_ALLOWED_OPTIONS_ID,
        "allowed_options_sha256": _canonical_json_sha256(options_payload),
    }


def monitoring_review_llm_response_schema(
    evidence_catalog: CausalEvidenceCatalog | None = None,
) -> dict[str, Any]:
    """Cierra las citas generativas al vocabulario E01..EN de la vista."""

    schema = copy.deepcopy(MonitoringReviewDecision.model_json_schema())
    handles = (
        tuple(entry.handle for entry in evidence_catalog.entries)
        if evidence_catalog is not None
        else MONITORING_REVIEW_DEFAULT_EVIDENCE_HANDLES
    )
    closed_refs = {
        "items": {
            "enum": list(handles),
            "type": "string",
        },
        "maxItems": len(handles),
        "minItems": 1,
        "title": "Evidence Refs",
        "type": "array",
        "uniqueItems": True,
    }
    schema["properties"]["evidence_refs"] = copy.deepcopy(closed_refs)
    schema["$defs"]["AgentHypothesis"]["properties"]["evidence_refs"] = (
        copy.deepcopy(closed_refs)
    )
    return schema


def _canonical_json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def decide_monitoring_review_action(
    *,
    agent_name: AgentName,
    request: MonitoringReviewRequest,
    causal_view: CausalInputView,
    evidence_records: list[dict[str, Any]],
    evidence_catalog: CausalEvidenceCatalog | None = None,
    allowed_evidence_refs: tuple[str, ...] | None = None,
    prior_decisions: tuple[MonitoringReviewDecision, ...] = (),
    llm_client: JSONLLMClient | None = None,
    use_llm: bool = True,
) -> MonitoringReviewDecision:
    """Emite una decision del rol sin leer raw, ejecutar codigo ni usar RAG."""

    _validate_review_envelope(request, causal_view, agent_name)
    try:
        effective_catalog = evidence_catalog or build_causal_evidence_catalog(
            causal_view,
            evidence_records,
        )
    except MonitoringReplayConflictError as exc:
        raise ValueError(str(exc)) from exc
    if allowed_evidence_refs is not None and allowed_evidence_refs != tuple(
        item.evidence_id for item in causal_view.evidence
    ):
        raise ValueError(
            "legacy allowed evidence refs must match the causal view exactly"
        )
    _validate_evidence_inputs(
        causal_view=causal_view,
        evidence_records=evidence_records,
        evidence_catalog=effective_catalog,
    )
    _validate_prior_decisions(
        request=request,
        causal_view=causal_view,
        prior_decisions=prior_decisions,
        evidence_catalog=effective_catalog,
    )
    fallback_ref = _fallback_support_ref(
        effective_catalog,
        evidence_records,
        cutoff_source_time=request.cutoff_source_time,
    )

    decision_id = _decision_id(request.child_run_id, agent_name)
    if not use_llm:
        return _deterministic_decision(
            agent_name=agent_name,
            request=request,
            evidence_ref=fallback_ref,
            origin="protocol_restricted",
        )

    client = llm_client or get_default_json_llm_client()
    attempt_index = 1
    messages = _review_messages(
        agent_name=agent_name,
        request=request,
        causal_view=causal_view,
        evidence_records=evidence_records,
        evidence_catalog=effective_catalog,
        prior_decisions=prior_decisions,
    )
    schema = monitoring_review_llm_response_schema(effective_catalog)
    try:
        payload = client.complete_json(messages, json_schema=schema)
        try:
            return _validated_llm_decision(
                payload,
                agent_name=agent_name,
                request=request,
                evidence_catalog=effective_catalog,
                partition_policy_id=causal_view.partition_policy_id,
                attempt_index=attempt_index,
                validation_status="validated",
            )
        except (ValidationError, ValueError) as exc:
            attempt_index = 2
            repaired = client.complete_json(
                _repair_messages(
                    messages,
                    payload,
                    error=exc,
                    decision_id=decision_id,
                    request=request,
                    evidence_catalog=effective_catalog,
                    agent_name=agent_name,
                ),
                json_schema=schema,
            )
            return _validated_llm_decision(
                repaired,
                agent_name=agent_name,
                request=request,
                evidence_catalog=effective_catalog,
                partition_policy_id=causal_view.partition_policy_id,
                attempt_index=attempt_index,
                validation_status="repaired",
            )
    except (LLMCallError, ValidationError, ValueError) as exc:
        return _fallback_decision(
            agent_name=agent_name,
            request=request,
            evidence_ref=fallback_ref,
            failed_attempt_index=attempt_index,
            cause=f"{type(exc).__name__}: {exc}",
        )


def _validated_llm_decision(
    payload: dict[str, Any],
    *,
    agent_name: AgentName,
    request: MonitoringReviewRequest,
    evidence_catalog: CausalEvidenceCatalog,
    partition_policy_id: str,
    attempt_index: int,
    validation_status: str,
) -> MonitoringReviewDecision:
    trusted = dict(payload)
    trusted.pop("decision_sha256", None)
    trusted.pop("created_at", None)
    trusted.pop("generation_trace", None)
    trusted.update(
        {
            "decision_id": _decision_id(request.child_run_id, agent_name),
            "agent_name": agent_name,
            "decision_kind": "monitoring_review",
            "child_run_id": request.child_run_id,
            "trigger_event_id": request.trigger_event_id,
            "cutoff_snapshot_id": request.cutoff_snapshot_id,
            "cutoff_cursor": request.cutoff_cursor,
            "cutoff_source_time": request.cutoff_source_time,
            "causal_view_sha256": request.causal_view_sha256,
            "generation_trace": DecisionGenerationTrace.for_decision(
                _decision_id(request.child_run_id, agent_name),
                origin="llm",
                attempt_index=attempt_index,
                validation_status=validation_status,
            ).model_dump(mode="json"),
            "memory_mode": "off",
            "policy_application_status": "not_applied",
            "created_at": datetime.now(UTC),
        }
    )
    hypothesis = trusted.get("hypothesis")
    if isinstance(hypothesis, dict):
        hypothesis = dict(hypothesis)
        hypothesis["kind"] = ROLE_HYPOTHESIS_KIND[agent_name]
        hypothesis["evidence_cutoff"] = request.cutoff_snapshot_id
        trusted["hypothesis"] = hypothesis
    proposed_decision_refs = _closed_evidence_handles(
        trusted.get("evidence_refs"),
        field_name="decision evidence_refs",
        evidence_catalog=evidence_catalog,
    )
    proposed_hypothesis_refs = _closed_evidence_handles(
        hypothesis.get("evidence_refs") if isinstance(hypothesis, dict) else None,
        field_name="hypothesis evidence_refs",
        evidence_catalog=evidence_catalog,
    )
    if proposed_hypothesis_refs != proposed_decision_refs:
        raise ValueError(
            "hypothesis evidence_refs must match decision evidence_refs"
        )

    # El modelo elige handles cortos. El servidor materializa exactamente esa
    # seleccion como referencias por registro, sin completar ni normalizar.
    by_handle = {
        entry.handle: entry.support_ref for entry in evidence_catalog.entries
    }
    canonical_refs = [by_handle[handle] for handle in proposed_decision_refs]
    trusted["evidence_refs"] = canonical_refs
    if isinstance(hypothesis, dict):
        hypothesis["evidence_refs"] = canonical_refs
        trusted["hypothesis"] = hypothesis
    action = trusted.get("recommended_action")
    if action not in ALLOWED_ACTIONS:
        raise ValueError("recommended_action is outside the closed catalog")
    if trusted.get("memory_mode") != "off":
        raise ValueError("monitoring review memory must remain disabled")
    trusted["decision_sha256"] = MonitoringReviewDecision.canonical_sha256(trusted)
    decision = MonitoringReviewDecision.model_validate(trusted)
    _validate_monitoring_review_claims(
        decision,
        partition_policy_id=partition_policy_id,
    )
    return decision


def _closed_evidence_handles(
    value: Any,
    *,
    field_name: str,
    evidence_catalog: CausalEvidenceCatalog,
) -> tuple[str, ...]:
    """Valida IDs opacos sin normalizacion, fuzzy matching ni coercion."""

    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be an array")
    if not value:
        raise ValueError(f"{field_name} must contain at least one handle")
    if any(not isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must contain only string handles")
    handles = tuple(value)
    if len(handles) != len(set(handles)):
        raise ValueError(f"{field_name} cannot contain duplicate handles")
    allowed = {entry.handle for entry in evidence_catalog.entries}
    if any(handle not in allowed for handle in handles):
        raise ValueError(f"{field_name} contains an unknown evidence handle")
    return handles


def _validate_monitoring_review_claims(
    decision: MonitoringReviewDecision,
    *,
    partition_policy_id: str,
) -> None:
    """Bloquea claims fisicos NASA v2 antes de aceptar la generacion LLM."""

    if partition_policy_id != NASA_IMS_RUN_TO_FAILURE_POLICY_V2:
        return
    hypothesis = decision.hypothesis
    unsupported = unsupported_official_v2_claims(
        (
            decision.rationale,
            decision.observation_summary,
            decision.action_rationale,
            hypothesis.statement,
            hypothesis.scope,
            hypothesis.expected_observation,
            hypothesis.falsification_criterion,
            *hypothesis.risk_notes,
            *hypothesis.assumptions,
        )
    )
    if unsupported:
        raise ValueError(
            "official NASA IMS causal v2 monitoring review contains unsupported "
            "physical claims: " + ", ".join(unsupported)
        )


def _review_messages(
    *,
    agent_name: AgentName,
    request: MonitoringReviewRequest,
    causal_view: CausalInputView,
    evidence_records: list[dict[str, Any]],
    evidence_catalog: CausalEvidenceCatalog,
    prior_decisions: tuple[MonitoringReviewDecision, ...],
) -> list[LLMMessage]:
    handle_by_ref = {
        entry.support_ref: entry.handle for entry in evidence_catalog.entries
    }
    prior_summary = [
        {
            "agent_name": item.agent_name,
            "observation_summary": item.observation_summary,
            "recommended_action": item.recommended_action,
            "support_handles": [
                handle_by_ref[ref] for ref in item.evidence_refs
            ],
        }
        for item in prior_decisions
    ]
    compact_catalog = [
        {
            "handle": entry.handle,
            "record": {
                key: value
                for key, value in evidence_records[entry.record_index].items()
                if key != "record_id"
            },
        }
        for entry in evidence_catalog.entries
    ]
    handles = tuple(entry.handle for entry in evidence_catalog.entries)
    context = {
        "session_id": request.session_id,
        "trigger_id": request.trigger_id,
        "trigger_event_id": request.trigger_event_id,
        "cutoff_cursor": request.cutoff_cursor,
        "cutoff_snapshot_id": request.cutoff_snapshot_id,
        "cutoff_source_time": request.cutoff_source_time.isoformat(),
        "active_policy_refs": request.active_policy_refs.model_dump(mode="json"),
        "capabilities": list(request.capabilities),
        "memory_mode": request.memory_mode,
        "visible_partitions": list(causal_view.visible_partitions),
        "evidence_binding": {
            "mode": "server_record_catalog",
            "catalog_sha256": evidence_catalog.catalog_sha256,
            "available_handles": list(handles),
        },
    }
    template = _decision_template(
        agent_name=agent_name,
        request=request,
        evidence_ref=handles[-1],
    )
    rules = [
        template_text.format(
            hypothesis_kind=ROLE_HYPOTHESIS_KIND[agent_name],
            cutoff_snapshot_id=request.cutoff_snapshot_id,
            evidence_handles=list(handles),
            allowed_actions=list(ALLOWED_ACTIONS),
        )
        for template_text in MONITORING_REVIEW_RULE_TEMPLATES
    ]
    return [
        LLMMessage(
            role="system",
            content=MONITORING_REVIEW_SYSTEM_PROMPT.format(
                agent_name=agent_name,
                role_mission=ROLE_MISSION[agent_name],
            ),
        ),
        LLMMessage(
            role="user",
            content="\n".join(
                [
                    "Contexto cerrado:",
                    json.dumps(context, ensure_ascii=True, indent=2),
                    "",
                    "Catalogo causal por registro:",
                    json.dumps(compact_catalog, ensure_ascii=True, indent=2),
                    "",
                    "Aportes previos (no son verdad de referencia):",
                    json.dumps(prior_summary, ensure_ascii=True, indent=2),
                    "",
                    "Plantilla orientativa:",
                    json.dumps(template, ensure_ascii=True, indent=2),
                    "",
                    "Reglas:",
                    *(f"- {rule}" for rule in rules),
                ]
            ),
        ),
    ]


def _repair_messages(
    original: list[LLMMessage],
    invalid_payload: dict[str, Any],
    *,
    error: Exception,
    decision_id: str,
    request: MonitoringReviewRequest,
    evidence_catalog: CausalEvidenceCatalog,
    agent_name: AgentName,
) -> list[LLMMessage]:
    return [
        *original,
        LLMMessage(
            role="assistant",
            content=json.dumps(invalid_payload, ensure_ascii=True),
        ),
        LLMMessage(
            role="user",
            content="\n".join(
                [
                    "La respuesta no valida contra el contrato cerrado.",
                    f"Error: {error}",
                    f"decision_id efectivo: {decision_id}",
                    f"agent_name efectivo: {agent_name}",
                    f"cutoff efectivo: {request.cutoff_snapshot_id}",
                    (
                        "handles de evidencia permitidos: "
                        + json.dumps(
                            [entry.handle for entry in evidence_catalog.entries]
                        )
                    ),
                    (
                        "Usa exactamente la misma lista ordenada en decision e "
                        "hypothesis; no uses record_id ni identificadores largos."
                    ),
                    (
                        "Elimina cualquier claim fisico NASA v2 no respaldado de "
                        "todos los textos libres, incluido hypothesis.scope; usa "
                        "una formulacion algoritmica y retrospectiva."
                    ),
                    "Corrige el contenido y reemite solo un objeto JSON.",
                ]
            ),
        ),
    ]


def _decision_template(
    *,
    agent_name: AgentName,
    request: MonitoringReviewRequest,
    evidence_ref: str,
) -> dict[str, Any]:
    return {
        "rationale": "Justificacion breve basada solo en el prefijo visible.",
        "confidence": 0.7,
        "hypothesis": {
            "kind": ROLE_HYPOTHESIS_KIND[agent_name],
            "statement": "Hipotesis observable y falsable del rol.",
            "scope": f"trigger {request.trigger_id}",
            "evidence_cutoff": request.cutoff_snapshot_id,
            "expected_observation": "Observacion futura que apoyaria la hipotesis.",
            "falsification_criterion": "Observacion que la refutaria.",
            "evidence_refs": [evidence_ref],
            "risk_notes": ["La evidencia procede de un replay historico causal."],
            "assumptions": [],
        },
        "observation_summary": "Lectura sintetica de la evidencia disponible.",
        "recommended_action": "maintain_policy",
        "action_rationale": "No aplicar cambios hasta disponer de mas evidencia.",
        "evidence_refs": [evidence_ref],
        "alternatives": ["intensify_observation"],
        "requires_human_review": False,
        "memory_mode": "off",
        "policy_application_status": "not_applied",
    }


def _deterministic_decision(
    *,
    agent_name: AgentName,
    request: MonitoringReviewRequest,
    evidence_ref: str,
    origin: str,
) -> MonitoringReviewDecision:
    decision_id = _decision_id(request.child_run_id, agent_name)
    payload: dict[str, Any] = {
        "decision_id": decision_id,
        "agent_name": agent_name,
        "child_run_id": request.child_run_id,
        "trigger_event_id": request.trigger_event_id,
        "cutoff_snapshot_id": request.cutoff_snapshot_id,
        "cutoff_cursor": request.cutoff_cursor,
        "cutoff_source_time": request.cutoff_source_time,
        "causal_view_sha256": request.causal_view_sha256,
        "rationale": (
            "Decision protocolaria segura: conservar la politica y registrar la "
            "evidencia sin aplicar cambios."
        ),
        "confidence": 0.5,
        "hypothesis": AgentHypothesis(
            kind=ROLE_HYPOTHESIS_KIND[agent_name],
            statement=(
                f"La evidencia visible requiere contraste adicional por el rol "
                f"{agent_name} antes de modificar la monitorizacion."
            ),
            scope=f"trigger {request.trigger_id}",
            evidence_cutoff=request.cutoff_snapshot_id,
            expected_observation=(
                "Nuevos snapshots causales mantienen o deshacen el patron observado."
            ),
            falsification_criterion=(
                "El patron desaparece en observaciones posteriores sin nueva alerta."
            ),
            evidence_refs=[evidence_ref],
            risk_notes=["No constituye evidencia de fallo fisico."],
            assumptions=[],
        ).model_dump(mode="json"),
        "generation_trace": DecisionGenerationTrace.for_decision(
            decision_id,
            origin=origin,
        ).model_dump(mode="json"),
        "observation_summary": "Evidencia registrada; contraste aun pendiente.",
        "recommended_action": "maintain_policy",
        "action_rationale": "El modo frozen_benchmark es exclusivamente propose-only.",
        "evidence_refs": (evidence_ref,),
        "alternatives": ("intensify_observation",),
        "requires_human_review": False,
        "memory_mode": "off",
        "policy_application_status": "not_applied",
        "created_at": datetime.now(UTC),
    }
    payload["decision_sha256"] = MonitoringReviewDecision.canonical_sha256(payload)
    return MonitoringReviewDecision.model_validate(payload)


def _fallback_decision(
    *,
    agent_name: AgentName,
    request: MonitoringReviewRequest,
    evidence_ref: str,
    failed_attempt_index: int,
    cause: str,
) -> MonitoringReviewDecision:
    decision = _deterministic_decision(
        agent_name=agent_name,
        request=request,
        evidence_ref=evidence_ref,
        origin="protocol_restricted",
    )
    payload = decision.model_dump(mode="python", exclude={"decision_sha256"})
    payload["rationale"] = f"{decision.rationale} Fallback controlado: {cause}"
    payload["generation_trace"] = DecisionGenerationTrace.for_decision(
        decision.decision_id,
        origin="guardrail_fallback",
        attempt_index=failed_attempt_index + 1,
        validation_status="fallback_applied",
        fallback_cause=cause,
        fallback_from_attempt_index=failed_attempt_index,
    )
    payload["decision_sha256"] = MonitoringReviewDecision.canonical_sha256(payload)
    return MonitoringReviewDecision.model_validate(payload)


def _validate_review_envelope(
    request: MonitoringReviewRequest,
    causal_view: CausalInputView,
    agent_name: AgentName,
) -> None:
    if agent_name not in request.required_roles:
        raise ValueError(f"role is not required by monitoring review: {agent_name}")
    if (
        request.session_id != causal_view.session_id
        or request.trigger_id != causal_view.trigger_id
        or request.trigger_event_id != causal_view.trigger_event_id
        or request.origin_tick_id != causal_view.origin_tick_id
        or request.cutoff_snapshot_id != causal_view.cutoff_snapshot_id
        or request.cutoff_cursor != causal_view.cursor
        or request.cutoff_source_time != causal_view.cutoff_source_time
        or request.active_policy_refs != causal_view.active_policy_refs
        or request.causal_view_sha256 != causal_view.view_sha256
    ):
        raise ValueError("monitoring review request and causal view do not match")
    if request.memory_mode != "off":
        raise ValueError("monitoring review v1 requires memory_mode=off")


def _validate_evidence_inputs(
    *,
    causal_view: CausalInputView,
    evidence_records: list[dict[str, Any]],
    evidence_catalog: CausalEvidenceCatalog,
) -> None:
    try:
        validate_causal_evidence_catalog(
            causal_view,
            evidence_records,
            evidence_catalog,
        )
    except MonitoringReplayConflictError as exc:
        raise ValueError(str(exc)) from exc


def _validate_prior_decisions(
    *,
    request: MonitoringReviewRequest,
    causal_view: CausalInputView,
    prior_decisions: tuple[MonitoringReviewDecision, ...],
    evidence_catalog: CausalEvidenceCatalog,
) -> None:
    """Impide introducir aportes previos de otra hija, vista o cutoff."""

    seen_agents: set[AgentName] = set()
    allowed = {entry.support_ref for entry in evidence_catalog.entries}
    for decision in prior_decisions:
        if decision.agent_name in seen_agents:
            raise ValueError("prior monitoring decisions cannot repeat an agent")
        seen_agents.add(decision.agent_name)
        if (
            decision.child_run_id != request.child_run_id
            or decision.trigger_event_id != request.trigger_event_id
            or decision.cutoff_snapshot_id != request.cutoff_snapshot_id
            or decision.cutoff_cursor != request.cutoff_cursor
            or decision.cutoff_source_time != request.cutoff_source_time
            or decision.causal_view_sha256 != causal_view.view_sha256
        ):
            raise ValueError(
                "prior monitoring decisions must belong to the same causal review"
            )
        if (
            not set(decision.evidence_refs).issubset(allowed)
            or not set(decision.hypothesis.evidence_refs).issubset(allowed)
        ):
            raise ValueError(
                "prior monitoring decisions must reference the same causal view"
            )


def _fallback_support_ref(
    evidence_catalog: CausalEvidenceCatalog,
    evidence_records: list[dict[str, Any]],
    *,
    cutoff_source_time: datetime,
) -> str:
    """Elige soporte determinista sin atribuir la seleccion al modelo."""

    pairs = list(zip(evidence_catalog.entries, evidence_records, strict=True))
    at_cutoff = [
        (entry, record)
        for entry, record in pairs
        if _record_source_time(record) == cutoff_source_time
    ]
    modeled_at_cutoff = [
        entry
        for entry, record in at_cutoff
        if record.get("analysis_status") == "modeled"
    ]
    if modeled_at_cutoff:
        return modeled_at_cutoff[-1].support_ref
    if at_cutoff:
        return at_cutoff[-1][0].support_ref
    modeled = [
        entry
        for entry, record in pairs
        if record.get("analysis_status") == "modeled"
    ]
    return (modeled[-1] if modeled else evidence_catalog.entries[-1]).support_ref


def _record_source_time(record: dict[str, Any]) -> datetime | None:
    value = record.get("source_time")
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _decision_id(child_run_id: str, agent_name: AgentName) -> str:
    return f"{child_run_id}:{agent_name}:001"
