"""Agente verificador del informe final con herramientas deterministas."""

from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from codigo.app.schemas.agent_decisions import (
    AgentHypothesis,
    DecisionGenerationTrace,
    ReportVerificationDecision,
    ReportVerificationIssue,
    require_agent_hypothesis,
)
from codigo.app.schemas.state import TFMStateModel
from codigo.app.services.llm import (
    JSONLLMClient,
    LLMCallError,
    LLMMessage,
    get_default_json_llm_client,
)
from codigo.app.services.agent_tools import build_state_evidence_catalog
from codigo.app.services.online_blind import (
    unsupported_official_v2_claims,
    uses_online_blind_view,
)


MAX_REPORT_CHARS_FOR_LLM = 6000
MAX_VERIFIER_USER_PROMPT_CHARS = 16000
MAX_VERIFIER_EVIDENCE_REFS = 72
REPORT_VERIFIER_MODE_ENV = "TFM_REPORT_VERIFIER_MODE"


def decide_report_verification_action(
    state: TFMStateModel,
    *,
    report_markdown: str | None = None,
    llm_client: JSONLLMClient | None = None,
    use_llm: bool | None = None,
) -> ReportVerificationDecision:
    """Verifica el informe final usando LLM cuando esta habilitado."""

    report_text = report_markdown if report_markdown is not None else _read_report(state)
    should_use_llm = _should_use_llm(llm_client, use_llm)
    if should_use_llm:
        attempt_tracker = [0]
        try:
            client = llm_client or get_default_json_llm_client()
            return decide_report_verification_action_with_llm(
                state,
                report_text,
                client,
                _attempt_tracker=attempt_tracker,
            )
        except (ValidationError, ValueError) as exc:
            fallback = decide_report_verification_action_deterministic(
                state,
                report_markdown=report_text,
            )
            fallback.rationale = (
                f"{fallback.rationale} Guardrail correction after invalid "
                f"LLM report verification: {exc}"
            )
            fallback.confidence = min(fallback.confidence, 0.72)
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
        except (LLMCallError, OSError) as exc:
            fallback = decide_report_verification_action_deterministic(
                state,
                report_markdown=report_text,
            )
            fallback.rationale = f"{fallback.rationale} {_fallback_reason(exc)}"
            fallback.confidence = min(fallback.confidence, 0.65)
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

    return decide_report_verification_action_deterministic(
        state,
        report_markdown=report_text,
    )


def decide_report_verification_action_with_llm(
    state: TFMStateModel,
    report_markdown: str,
    llm_client: JSONLLMClient,
    *,
    _attempt_tracker: list[int] | None = None,
) -> ReportVerificationDecision:
    """Solicita al LLM una verificacion factual validada."""

    attempt_tracker = _attempt_tracker if _attempt_tracker is not None else [0]
    messages = _report_verifier_messages(state, report_markdown)
    schema = ReportVerificationDecision.model_json_schema()
    attempt_tracker[0] = 1
    payload = llm_client.complete_json(
        messages,
        json_schema=schema,
    )
    try:
        decision = _validated_report_verification_from_payload(state, payload)
    except (ValidationError, ValueError) as exc:
        attempt_tracker[0] = 2
        repaired_payload = llm_client.complete_json(
            _report_verifier_contract_repair_messages(
                state,
                messages,
                invalid_payload=payload,
                validation_error=exc,
            ),
            json_schema=schema,
        )
        decision = _validated_report_verification_from_payload(
            state,
            repaired_payload,
            hypothesis_fallback_payload=payload,
        )
        decision.generation_trace = DecisionGenerationTrace.for_decision(
            decision.decision_id,
            origin="llm",
            attempt_index=2,
            validation_status="repaired",
        )
    else:
        decision.generation_trace = DecisionGenerationTrace.for_decision(
            decision.decision_id,
            origin="llm",
        )
    return _merge_deterministic_guardrails(
        state,
        report_markdown,
        decision,
    )


def decide_report_verification_action_deterministic(
    state: TFMStateModel,
    *,
    report_markdown: str | None = None,
) -> ReportVerificationDecision:
    """Verificacion reproducible: detecta riesgos evidentes sin reescribir el informe."""

    report_text = report_markdown if report_markdown is not None else _read_report(state)
    issues = _deterministic_issues(state, report_text)
    status = _status_from_issues(issues)
    decision_id = f"{state.run_id}:report_verifier:{_verifier_turn(state):03d}"
    return ReportVerificationDecision(
        decision_id=decision_id,
        rationale=(
            "Deterministic verifier policy: check obvious unsupported industrial claims, "
            "dataset policy risks and missing critical limitations. Style choices are "
            "accepted when they do not change factual meaning."
        ),
        confidence=0.72 if issues else 0.78,
        hypothesis=_verifier_hypothesis(
            state,
            status=status,
            evidence_refs=_safe_evidence_refs(state),
        ),
        generation_trace=DecisionGenerationTrace.for_decision(
            decision_id,
            origin="deterministic",
        ),
        report_path=_expected_report_path(state),
        verification_status=status,
        summary=_summary_from_status(status, issues),
        unsupported_claims=[
            issue for issue in issues if issue.issue_type == "unsupported_claim"
        ],
        misleading_claims=[
            issue
            for issue in issues
            if issue.issue_type in {"misleading_claim", "policy_violation"}
        ],
        missing_limitations=[
            issue for issue in issues if issue.issue_type == "missing_limitation"
        ],
        required_corrections=[issue.suggested_fix for issue in issues],
        acceptable_style_notes=[
            "No se exige coincidencia literal con un texto esperado.",
            "Se aceptan cambios de orden, enfasis y redaccion si no inventan hechos.",
        ],
        evidence_refs=_safe_evidence_refs(state),
    )


def _verifier_hypothesis(
    state: TFMStateModel,
    *,
    status: str,
    evidence_refs: list[str],
) -> AgentHypothesis:
    scoped_refs = evidence_refs or ["report:final_report"]
    if status == "approved":
        statement = (
            "El informe puede aprobarse porque no presenta incidencias factuales "
            "o limitaciones materiales ausentes frente al catalogo cerrado de evidencia."
        )
        expected_observation = (
            "Una comprobacion independiente tampoco identifica incidencias materiales "
            "ni correcciones obligatorias."
        )
        falsification_criterion = (
            "Una comprobacion independiente encuentra una incidencia material, una "
            "referencia inexistente o un guardarrail obliga a revisar el veredicto."
        )
    elif status == "needs_revision":
        statement = (
            "El informe requiere revision porque contiene al menos una incidencia "
            "material corregible, sin alcanzar el bloqueo critico."
        )
        expected_observation = (
            "Una comprobacion independiente confirma las incidencias corregibles y "
            "que sus correcciones bastan sin bloquear el informe."
        )
        falsification_criterion = (
            "No existe ninguna incidencia material o aparece una incidencia critica "
            "que exige bloquear, en lugar de revisar, el informe."
        )
    elif status == "blocked":
        statement = (
            "El informe debe bloquearse porque contiene al menos una incidencia "
            "critica de evidencia o politica."
        )
        expected_observation = (
            "Una comprobacion independiente confirma al menos una incidencia critica "
            "que impide aprobar el informe en su estado actual."
        )
        falsification_criterion = (
            "La supuesta incidencia critica esta respaldada por evidencia valida o su "
            "severidad real solo requiere una revision no bloqueante."
        )
    else:
        raise ValueError(f"unsupported report verification status: {status}")
    return AgentHypothesis(
        kind="report_fidelity",
        statement=statement,
        scope=(
            f"Informe final de la run {state.run_id}; fidelidad factual, no estilo literario."
        ),
        evidence_cutoff=(
            "Informe generado y catalogo de evidencias persistidas antes de la verificacion."
        ),
        expected_observation=expected_observation,
        falsification_criterion=falsification_criterion,
        evidence_refs=scoped_refs,
        risk_notes=[
            "El propio veredicto del verificador no demuestra que su auditoria sea correcta."
        ],
        assumptions=[
            "Cambios de estilo son aceptables mientras no alteren el significado factual."
        ],
    )


def evidence_catalog_for_report_verifier(state: TFMStateModel) -> dict[str, Any]:
    """Construye el catalogo cerrado de evidencias que puede citar el verificador."""

    return build_state_evidence_catalog(state)


def _compact_evidence_catalog_for_llm(state: TFMStateModel) -> dict[str, Any]:
    """Prioriza evidencia factual sin enviar metadatos voluminosos al LLM."""

    catalog = evidence_catalog_for_report_verifier(state)
    project_context = catalog.get("project_context") or {}
    evaluation = catalog.get("evaluation")
    limitations = [
        _clip_prompt_text(value, 500)
        for key, value in sorted(catalog.items())
        if key.startswith("limitation:") and isinstance(value, str)
    ][:8]
    temporal = catalog.get("temporal_evidence") or {}
    primary_run = temporal.get("primary_run")
    artifacts = [
        {
            "ref": item.get("ref"),
            "name": item.get("name"),
            "artifact_type": item.get("artifact_type"),
            "producer": item.get("producer"),
            "description": _clip_prompt_text(item.get("description"), 240),
        }
        for item in (catalog.get("artifacts") or [])[:6]
        if isinstance(item, dict)
    ]
    errors = [
        {
            key: (
                _clip_prompt_text(value, 320)
                if isinstance(value, str)
                else value
            )
            for key, value in item.items()
            if key in {"stage", "node", "message", "recoverable"}
        }
        for item in (catalog.get("errors") or [])[:4]
        if isinstance(item, dict)
    ]
    raw_allowed_refs = set(catalog.get("allowed_evidence_refs") or []) | {
        "missing:evidence"
    }
    allowed_refs = sorted(
        (ref for ref in raw_allowed_refs if len(ref) <= 240),
        key=_evidence_ref_prompt_priority,
    )[:MAX_VERIFIER_EVIDENCE_REFS]
    return {
        "run_id": catalog.get("run_id"),
        "dataset": catalog.get("dataset"),
        "context": {
            key: _clip_prompt_text(project_context.get(key), 240)
            for key in (
                "objective",
                "supervision_profile",
                "label_mode",
                "label_source",
                "label_granularity",
                "data_provenance",
            )
        },
        "metrics": _compact_metrics_for_llm(catalog.get("metrics")),
        "evaluation": (
            None
            if not isinstance(evaluation, dict)
            else {
                "approved": evaluation.get("approved"),
                "summary": _clip_prompt_text(evaluation.get("summary"), 600),
                "next_action": evaluation.get("next_action"),
            }
        ),
        "limitations": limitations,
        "temporal_evidence": {
            "available": temporal.get("available"),
            "label_context": _bounded_prompt_value(temporal.get("label_context")),
            "metrics": _bounded_prompt_value(temporal.get("metrics")),
            "temporal_policy": _bounded_prompt_value(
                temporal.get("temporal_policy")
            ),
            "primary_run": _compact_temporal_run_for_llm(primary_run),
            "warnings": [
                _clip_prompt_text(value, 300)
                for value in (temporal.get("warnings") or [])[:5]
                if isinstance(value, str)
            ],
        },
        "dataset_policy": _bounded_prompt_value(catalog.get("dataset_policy")),
        "artifacts": artifacts,
        "errors": errors,
        "allowed_evidence_refs": allowed_refs,
        "omitted_counts": {
            "artifacts": max(0, len(catalog.get("artifacts") or []) - len(artifacts)),
            "errors": max(0, len(catalog.get("errors") or []) - len(errors)),
            "evidence_refs": max(
                0,
                len(raw_allowed_refs)
                - len(allowed_refs),
            ),
        },
    }


def _compact_metrics_for_llm(raw_metrics: Any) -> dict[str, Any] | None:
    if not isinstance(raw_metrics, dict):
        return None
    compact = {
        key: _bounded_prompt_value(value)
        for key, value in raw_metrics.items()
        if key != "extra" and value is not None
    }
    extra = raw_metrics.get("extra")
    if not isinstance(extra, dict):
        return compact
    prioritized_extra = sorted(
        (
            (key, _bounded_prompt_value(value))
            for key, value in extra.items()
            if value is not None
        ),
        key=lambda item: (_metric_prompt_priority(item[0]), item[0]),
    )[:24]
    compact["extra"] = dict(prioritized_extra)
    compact["omitted_extra_metric_count"] = max(
        0,
        len([value for value in extra.values() if value is not None])
        - len(prioritized_extra),
    )
    return compact


def _compact_temporal_run_for_llm(raw_run: Any) -> dict[str, Any] | None:
    if not isinstance(raw_run, dict):
        return None
    return {
        key: _bounded_prompt_value(raw_run.get(key))
        for key in (
            "run_id",
            "n_windows",
            "threshold",
            "first_persistent_alert",
            "longest_alert_streak",
            "false_alarm_rate_nominal",
            "score_trend_spearman",
            "policy",
        )
        if key in raw_run
    }


def _metric_prompt_priority(name: str) -> int:
    normalized = name.lower()
    if any(
        term in normalized
        for term in (
            "degradation",
            "lead_time",
            "false_alarm",
            "alert",
            "trend",
            "health",
            "recall",
            "f1",
        )
    ):
        return 0
    return 1


def _evidence_ref_prompt_priority(ref: str) -> tuple[int, str]:
    prefix_order = {
        "report:": 0,
        "dataset:": 1,
        "data_provenance:": 1,
        "label_source:": 1,
        "label_granularity:": 1,
        "objective:": 1,
        "supervision_profile:": 1,
        "evaluation:": 2,
        "limitation:": 2,
        "policy:": 2,
        "metric:": 3,
        "metric_extra:": 3,
        "temporal:": 3,
        "health:": 3,
        "config:": 4,
        "model:": 4,
        "artifact:": 5,
        "error:": 6,
        "missing:": 7,
    }
    rank = next(
        (value for prefix, value in prefix_order.items() if ref.startswith(prefix)),
        8,
    )
    return rank, ref


def _clip_prompt_text(value: Any, max_chars: int) -> Any:
    if not isinstance(value, str) or len(value) <= max_chars:
        return value
    clipped = value[: max_chars - 16].rsplit(" ", 1)[0].rstrip()
    return clipped + " [recortado]"


def _bounded_prompt_value(value: Any, *, depth: int = 0) -> Any:
    if isinstance(value, str):
        return _clip_prompt_text(value, 320)
    if depth >= 2:
        if isinstance(value, dict):
            return f"[{len(value)} campos omitidos]"
        if isinstance(value, list):
            return f"[{len(value)} elementos omitidos]"
        return value
    if isinstance(value, dict):
        return {
            str(key): _bounded_prompt_value(item, depth=depth + 1)
            for key, item in list(value.items())[:24]
        }
    if isinstance(value, list):
        return [
            _bounded_prompt_value(item, depth=depth + 1)
            for item in value[:12]
        ]
    return value


def render_report_verification_markdown(
    decision: ReportVerificationDecision,
) -> str:
    """Renderiza una vista humana compacta de la verificacion."""

    lines = [
        f"# Verificacion del informe {decision.report_path}",
        "",
        f"- Estado: `{decision.verification_status}`",
        f"- Decision: `{decision.decision_id}`",
        f"- Confianza: `{decision.confidence:.2f}`",
        "",
        "## Resumen",
        "",
        decision.summary,
        "",
    ]
    sections = [
        ("Afirmaciones sin soporte", decision.unsupported_claims),
        ("Afirmaciones enganosas o de politica", decision.misleading_claims),
        ("Limitaciones ausentes", decision.missing_limitations),
    ]
    for title, issues in sections:
        lines.extend([f"## {title}", ""])
        if not issues:
            lines.extend(["Sin incidencias.", ""])
            continue
        for issue in issues:
            lines.extend(
                [
                    f"- Severidad: `{issue.severity}`",
                    f"  Afirmacion: {issue.claim_text}",
                    f"  Motivo: {issue.reason}",
                    f"  Correccion sugerida: {issue.suggested_fix}",
                    "  Evidencia: "
                    + (
                        ", ".join(f"`{ref}`" for ref in issue.evidence_refs)
                        if issue.evidence_refs
                        else "`missing:evidence`"
                    ),
                    "",
                ]
            )
    if decision.required_corrections:
        lines.extend(["## Correcciones requeridas", ""])
        lines.extend([f"- {item}" for item in decision.required_corrections])
        lines.append("")
    if decision.acceptable_style_notes:
        lines.extend(["## Notas de tolerancia", ""])
        lines.extend([f"- {item}" for item in decision.acceptable_style_notes])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _report_verifier_messages(
    state: TFMStateModel,
    report_markdown: str,
) -> list[LLMMessage]:
    evidence_catalog = _compact_evidence_catalog_for_llm(state)
    evidence_json = json.dumps(
        evidence_catalog,
        ensure_ascii=True,
        separators=(",", ":"),
    )
    rules = [
        "Clave obligatoria verification_status (elige un unico valor):",
        (
            "- approved: cero incidencias estructuradas y cero "
            "required_corrections."
        ),
        (
            "- needs_revision: al menos una incidencia no critica y su "
            "suggested_fix; required_corrections recopila esas correcciones."
        ),
        (
            "- blocked: al menos una incidencia critical y su "
            "suggested_fix; required_corrections recopila esas correcciones."
        ),
        "Criterios:",
        "- Tolera estilo, orden y vocabulario equivalentes; audita hechos y metodo.",
        (
            "- hypothesis es obligatoria y usa exactamente kind, statement, "
            "scope, evidence_cutoff, expected_observation, "
            "falsification_criterion, evidence_refs, risk_notes y assumptions; "
            "los tres ultimos campos de lista son arrays JSON y no se admite "
            "hypothesis_id."
        ),
        (
            "- hypothesis.evidence_refs y hypothesis.risk_notes deben contener "
            "al menos un string no vacio; assumptions puede ser un array vacio. "
            "Un riesgo valido describe una limitacion del catalogo, una posible "
            "omision material o una condicion que haria inseguro el veredicto."
        ),
        (
            "- Cada issue usa exactamente issue_id, issue_type, severity, "
            "claim_text, reason, evidence_refs y suggested_fix; issue_type "
            "pertenece a unsupported_claim, misleading_claim, "
            "missing_limitation o policy_violation; severity pertenece a low, "
            "medium, high o critical; evidence_refs siempre es un array JSON."
        ),
        (
            "- RESPUESTA INVALIDA si un issue omite suggested_fix o lo deja "
            "vacio: cada incidencia debe proponer su propia correccion concreta, "
            "aunque reason ya explique el problema."
        ),
        "- Cada issue cita solo evidence_refs del catalogo o missing:evidence.",
        (
            "- No exijas evidencia para una afirmacion que el propio informe "
            "niega expresamente o declara fuera de alcance. Una limitacion no "
            "es una afirmacion positiva."
        ),
        (
            "- Si el informe se presenta como resultado local, limita de forma "
            "explicita su generalizacion y descarta validacion industrial o "
            "preparacion para produccion, apruebalo cuando no exista otra "
            "incidencia factual concreta."
        ),
        (
            "- En supervision_profile=binary_fault_classification, que no exista "
            "perfil run_to_failure, trayectoria temporal o artefacto longitudinal "
            "es una diferencia de alcance esperada, no una incidencia del informe. "
            "Si el texto ya declara benchmark local y niega generalizacion y "
            "preparacion industrial, NO exijas ademas evidencia temporal ni otra "
            "advertencia equivalente."
        ),
        (
            "- evaluation.approved significa aprobacion del protocolo local. No "
            "la conviertas en claim industrial ni en incidencia cuando el propio "
            "informe limita expresamente su alcance."
        ),
        (
            "- No aceptes validacion industrial, procedencia/etiquetas oficiales "
            "ni aprobacion si la evidencia no lo respalda."
        ),
        (
            "- Preparacion para produccion, validacion industrial completa o "
            "generalizacion garantizada son incidencias critical y exigen blocked."
        ),
        (
            "- Si el catalogo contiene limitaciones persistidas y el informe no "
            "incluye una limitacion clara, registra ademas una incidencia separada "
            "missing_limitation con issue_id missing_persisted_limitations; no la "
            "absorbas solo dentro de la correccion de otra incidencia."
        ),
        (
            "- Si data_provenance es synthetic o unknown, el informe debe "
            "declararlo; si label_source no es official, no hay ground truth "
            "oficial por ventana."
        ),
    ]
    if uses_online_blind_view(state):
        rules.extend(
            [
                (
                    "- NASA IMS oficial causal v2: bloquea como policy_violation "
                    "onset fisico, deteccion/diagnostico validados, evento fisico "
                    "predicho, RUL o aprobacion del detector."
                ),
                (
                    "- Solo son defendibles controles operativos internos, alerta "
                    "algoritmica persistente, tiempo retrospectivo al final "
                    "registrado y tasa de alertas pre-monitorizacion."
                ),
            ]
        )
    rules.extend(
        [
            f"- report_path exacto: {_expected_report_path(state)}.",
            (
                "- decision_id exacto: "
                f"{state.run_id}:report_verifier:{_verifier_turn(state):03d}."
            ),
        ]
    )
    suffix = "\n".join(
        [
            "",
            "Catalogo cerrado y compacto de evidencias:",
            evidence_json,
            "",
            *rules,
        ]
    )
    report_budget = min(
        MAX_REPORT_CHARS_FOR_LLM,
        max(
            1200,
            MAX_VERIFIER_USER_PROMPT_CHARS
            - len(suffix)
            - len("Informe final priorizado para auditoria:\n"),
        ),
    )
    report_excerpt = _truncate_report(report_markdown, max_chars=report_budget)
    user_content = "\n".join(
        [
            "Informe final priorizado para auditoria:",
            report_excerpt,
            suffix,
        ]
    )
    if len(user_content) > MAX_VERIFIER_USER_PROMPT_CHARS:
        overflow = len(user_content) - MAX_VERIFIER_USER_PROMPT_CHARS
        report_excerpt = _truncate_report(
            report_markdown,
            max_chars=max(600, report_budget - overflow - 32),
        )
        user_content = "\n".join(
            [
                "Informe final priorizado para auditoria:",
                report_excerpt,
                suffix,
            ]
        )
    return [
        LLMMessage(
            role="system",
            content=(
                "Eres report_verifier, un agente auditor de informes de deteccion "
                "de anomalias industriales. Debes ser tolerante con estilo, orden "
                "y enfasis, pero estricto con afirmaciones falsas, exageradas o "
                "sin evidencia. No exijas coincidencia literal con un informe "
                "esperado. No ejecutes codigo ni inventes evidencias. Devuelve "
                "solo JSON compatible con ReportVerificationDecision. Formula "
                "ademas una hypothesis de fidelidad contrastable con alcance, "
                "evidencia y criterio de refutacion. La hypothesis debe usar "
                "exactamente las claves kind, statement, scope, evidence_cutoff, "
                "expected_observation, falsification_criterion, evidence_refs, "
                "risk_notes y assumptions; evidence_refs, risk_notes y "
                "assumptions son arrays JSON. evidence_refs y risk_notes deben "
                "tener al menos un string no vacio; assumptions puede estar "
                "vacio. No incluyas hypothesis_id ni uses aliases como "
                "fidelity_claim, evidence o refutation_criteria."
            ),
        ),
        LLMMessage(
            role="user",
            content=user_content,
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
    return os.getenv(REPORT_VERIFIER_MODE_ENV, "").strip().lower() == "llm"


def _validated_report_verification_from_payload(
    state: TFMStateModel,
    payload: dict[str, Any],
    *,
    hypothesis_fallback_payload: dict[str, Any] | None = None,
) -> ReportVerificationDecision:
    trusted_payload = dict(payload)
    trusted_payload.pop("generation_trace", None)
    trusted_payload.pop("policy_overlay_applied", None)
    trusted_payload.pop("policy_overlay_issue_ids", None)
    normalized = _coerce_verification_payload(
        state,
        trusted_payload,
        hypothesis_fallback_payload=hypothesis_fallback_payload,
    )
    decision = ReportVerificationDecision.model_validate(normalized)
    _validate_verification_decision_bounds(state, decision)
    return decision


def _report_verifier_contract_repair_messages(
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
                    "La verificacion anterior no valida contra el contrato.",
                    f"Error de validacion: {validation_error}",
                    "Corrige solo lo necesario y reemite un unico objeto JSON valido.",
                    "No inventes evidencias ni cites refs fuera del catalogo.",
                    (
                        "Incluye hypothesis con exactamente estas claves: "
                        "kind, statement, scope, evidence_cutoff, "
                        "expected_observation, falsification_criterion, "
                        "evidence_refs, risk_notes y assumptions."
                    ),
                    (
                        "En hypothesis, kind debe ser report_fidelity; scope es "
                        "obligatorio; evidence_refs, risk_notes y assumptions "
                        "deben ser arrays JSON. evidence_refs y risk_notes deben "
                        "contener al menos un string no vacio; assumptions puede "
                        "ser un array vacio."
                    ),
                    (
                        "No incluyas hypothesis_id ni aliases como evidence, "
                        "fidelity_claim o refutation_criteria. Conserva cualquier "
                        "campo valido de la hypothesis anterior que siga siendo "
                        "aplicable y no inventes evidencia nueva."
                    ),
                    (
                        "Las hypothesis.evidence_refs tambien deben pertenecer "
                        "al catalogo cerrado o ser missing:evidence."
                    ),
                    (
                        "Cada incidencia debe usar exactamente issue_id, "
                        "issue_type, severity, claim_text, reason, evidence_refs "
                        "y suggested_fix. issue_type solo puede ser "
                        "unsupported_claim, misleading_claim, "
                        "missing_limitation o policy_violation; severity solo "
                        "low, medium, high o critical; evidence_refs debe ser "
                        "un array JSON. No uses statement, risk_notes, "
                        "expected_observation ni required_correction dentro de "
                        "una incidencia."
                    ),
                    (
                        "La respuesta seguira siendo invalida si cualquier issue "
                        "omite suggested_fix o lo deja vacio."
                    ),
                    (
                        "Mantén consistente verification_status con las listas: "
                        "sin incidencias ni correcciones usa approved; para "
                        "needs_revision o blocked incluye incidencias estructuradas "
                        "con suggested_fix y recopila esos mismos textos en "
                        "required_corrections; critical exige blocked."
                    ),
                    *(
                        [
                            "En NASA IMS oficial v2 no aceptes claims fisicos; limita el resultado a controles operativos internos y evidencia algoritmica retrospectiva."
                        ]
                        if uses_online_blind_view(state)
                        else []
                    ),
                    f"decision_id obligatorio: {state.run_id}:report_verifier:{_verifier_turn(state):03d}.",
                    f"report_path obligatorio: {_expected_report_path(state)}.",
                    "No incluyas texto fuera del JSON.",
                ]
            ),
        ),
    ]


def _validate_verification_decision_bounds(
    state: TFMStateModel,
    decision: ReportVerificationDecision,
) -> None:
    hypothesis = require_agent_hypothesis(
        decision,
        allowed_kinds={"report_fidelity"},
    )
    expected_id = f"{state.run_id}:report_verifier:{_verifier_turn(state):03d}"
    if decision.decision_id != expected_id:
        raise ValueError(f"decision_id must be {expected_id}")
    expected_path = _expected_report_path(state)
    if decision.report_path != expected_path:
        raise ValueError(f"report_path must be {expected_path}")
    allowed_refs = set(
        evidence_catalog_for_report_verifier(state)["allowed_evidence_refs"]
    )
    allowed_refs.add("missing:evidence")
    for ref in hypothesis.evidence_refs:
        if ref not in allowed_refs:
            raise ValueError(f"unsupported hypothesis evidence ref: {ref}")
    for ref in decision.evidence_refs:
        if ref not in allowed_refs:
            raise ValueError(f"unsupported evidence ref: {ref}")
    issue_groups = [
        ("unsupported_claim", decision.unsupported_claims),
        ("misleading_claim", decision.misleading_claims),
        ("missing_limitation", decision.missing_limitations),
    ]
    for expected_type, issues in issue_groups:
        for issue in issues:
            if expected_type == "misleading_claim":
                valid_types = {"misleading_claim", "policy_violation"}
            else:
                valid_types = {expected_type}
            if issue.issue_type not in valid_types:
                raise ValueError(
                    f"{expected_type} group contains {issue.issue_type}"
                )
            for ref in issue.evidence_refs:
                if ref not in allowed_refs:
                    raise ValueError(f"unsupported issue evidence ref: {ref}")

    all_issues = [
        *decision.unsupported_claims,
        *decision.misleading_claims,
        *decision.missing_limitations,
    ]
    if not all_issues:
        if decision.verification_status != "approved":
            raise ValueError(
                "needs_revision or blocked requires at least one structured issue"
            )
        if decision.required_corrections:
            raise ValueError(
                "approved verification cannot include required_corrections"
            )
        return

    if decision.verification_status == "approved":
        raise ValueError("approved verification cannot include structured issues")
    if not decision.required_corrections:
        raise ValueError(
            "verification with structured issues requires required_corrections"
        )
    if (
        any(issue.severity == "critical" for issue in all_issues)
        and decision.verification_status != "blocked"
    ):
        raise ValueError("critical verification issues require blocked status")


def _coerce_verification_payload(
    state: TFMStateModel,
    payload: dict[str, Any],
    *,
    hypothesis_fallback_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normaliza dialectos JSON frecuentes sin inventar evidencia factual."""

    allowed = {
        "agent_name",
        "decision_id",
        "rationale",
        "confidence",
        "hypothesis",
        "report_path",
        "verification_status",
        "summary",
        "unsupported_claims",
        "misleading_claims",
        "missing_limitations",
        "required_corrections",
        "acceptable_style_notes",
        "evidence_refs",
    }
    normalized: dict[str, Any] = {
        key: value
        for key, value in payload.items()
        if key in allowed
    }
    normalized.setdefault("agent_name", "report_verifier")
    normalized.setdefault(
        "decision_id",
        f"{state.run_id}:report_verifier:{_verifier_turn(state):03d}",
    )
    normalized.setdefault("report_path", _expected_report_path(state))
    status = _status_alias(
        normalized.get("verification_status")
        or payload.get("classification")
        or payload.get("decision")
        or payload.get("status")
    )
    normalized["verification_status"] = status
    normalized.setdefault(
        "summary",
        _string_or_none(payload.get("summary"))
        or _string_or_none(payload.get("notes"))
        or "Verificacion factual del informe completada.",
    )
    normalized.setdefault(
        "rationale",
        _string_or_none(payload.get("rationale"))
        or _reasoning_summary(payload.get("reasoning"))
        or _string_or_none(payload.get("notes"))
        or "LLM verifier output normalized to the strict report verification schema.",
    )
    normalized.setdefault("confidence", _float_or_default(payload.get("confidence"), 0.74))
    normalized_hypothesis = _coerce_verifier_hypothesis(
        state,
        payload.get("hypothesis"),
        missing_fields_from=(
            None
            if hypothesis_fallback_payload is None
            else hypothesis_fallback_payload.get("hypothesis")
        ),
    )
    if normalized_hypothesis is not None:
        normalized["hypothesis"] = normalized_hypothesis

    corrections = _string_list(payload.get("required_corrections"))
    structured_issues: list[dict[str, Any]] = []
    issue_sources = (
        (payload.get("unsupported_claims"), "unsupported_claim"),
        (payload.get("misleading_claims"), "misleading_claim"),
        (payload.get("missing_limitations"), "missing_limitation"),
        (payload.get("issues"), None),
    )
    raw_issue_entries = [
        (raw_issue, default_type)
        for raw_issues, default_type in issue_sources
        for raw_issue in _list_value(raw_issues)
    ]
    positional_corrections = (
        corrections
        if len(corrections) == len(raw_issue_entries)
        else []
    )
    for index, (raw_issue, default_type) in enumerate(raw_issue_entries):
        issue = _coerce_verification_issue(
            state,
            raw_issue,
            default_type=default_type,
            default_severity="critical" if status == "blocked" else "medium",
            positional_correction=(
                positional_corrections[index]
                if positional_corrections
                else None
            ),
        )
        if issue is not None:
            structured_issues.append(issue)

    if len(structured_issues) != len(raw_issue_entries):
        raise ValueError(
            "every emitted issue requires a claim, reason and suggested_fix; "
            "incomplete issues cannot be discarded"
        )

    reasoning_items = _string_list(payload.get("reasoning"))
    if not structured_issues and status != "approved" and reasoning_items:
        for index, reasoning in enumerate(reasoning_items):
            correction = _correction_for_reasoning(corrections, index)
            if correction is None:
                # Sin una correccion emitida por el LLM no se fabrica una. El
                # contrato fallara y activara el reintento generativo existente.
                continue
            issue = _coerce_verification_issue(
                state,
                {
                    "description": reasoning,
                    "severity": "critical" if status == "blocked" else "medium",
                    "evidence_refs": payload.get("evidence_references"),
                    "required_correction": correction,
                },
                default_type=None,
                default_severity="critical" if status == "blocked" else "medium",
            )
            if issue is not None:
                structured_issues.append(issue)

    unsupported_claims: list[dict[str, Any]] = []
    misleading_claims: list[dict[str, Any]] = []
    missing_limitations: list[dict[str, Any]] = []
    for issue in structured_issues:
        issue_type = issue["issue_type"]
        if issue_type == "unsupported_claim":
            unsupported_claims.append(issue)
        elif issue_type == "missing_limitation":
            missing_limitations.append(issue)
        else:
            misleading_claims.append(issue)
    normalized["unsupported_claims"] = unsupported_claims
    normalized["misleading_claims"] = misleading_claims
    normalized["missing_limitations"] = missing_limitations

    if structured_issues:
        corrections = list(
            dict.fromkeys(
                [
                    *corrections,
                    *[
                        issue["suggested_fix"]
                        for issue in structured_issues
                        if issue.get("suggested_fix")
                    ],
                ]
            )
        )
        issue_status = (
            "blocked"
            if any(issue["severity"] == "critical" for issue in structured_issues)
            else "needs_revision"
        )
        normalized["verification_status"] = _stronger_verification_status(
            status,
            issue_status,
        )
    normalized["required_corrections"] = corrections
    normalized["acceptable_style_notes"] = _string_list(
        payload.get("acceptable_style_notes")
    )

    raw_evidence_refs = (
        payload.get("evidence_refs")
        if "evidence_refs" in payload
        else payload.get("evidence_references")
    )
    if raw_evidence_refs is None:
        raw_evidence_refs = ["report:final_report"]
    normalized["evidence_refs"] = _coerce_evidence_refs(
        state,
        raw_evidence_refs,
    )
    return normalized


def _coerce_verifier_hypothesis(
    state: TFMStateModel,
    value: Any,
    *,
    missing_fields_from: Any = None,
) -> Any:
    """Normaliza solo forma y aliases emitidos por el verificador.

    No completa el juicio con plantillas ni crea referencias. Durante una
    reparacion puede recuperar un campo que el primer intento ya habia emitido
    y el segundo omitio, manteniendo siempre como preferente el valor reparado.
    """

    if not isinstance(value, dict):
        if isinstance(missing_fields_from, dict):
            return _coerce_verifier_hypothesis(state, missing_fields_from)
        return value

    normalized: dict[str, Any] = {}
    if "kind" in value:
        raw_kind = _normalized_alias(value["kind"])
        normalized["kind"] = (
            "report_fidelity"
            if raw_kind
            in {
                "report_fidelity",
                "fidelity_claim",
                "fidelity_contrast",
                "generalization_limitation",
                "report_fidelity_hypothesis",
            }
            else value["kind"]
        )

    text_aliases = {
        "statement": (
            "statement",
            "fidelity_claim",
            "fidelity_hypothesis",
            "hypothesis_statement",
        ),
        "scope": ("scope", "hypothesis_scope"),
        "evidence_cutoff": ("evidence_cutoff",),
        "expected_observation": (
            "expected_observation",
            "expected_observations",
        ),
        "falsification_criterion": (
            "falsification_criterion",
            "refutation_criterion",
            "refutation_criteria",
        ),
    }
    for target, aliases in text_aliases.items():
        for alias in aliases:
            if alias not in value:
                continue
            texts = _string_list(value.get(alias))
            if texts:
                normalized[target] = " ".join(texts)
            break

    evidence_value = None
    for alias in ("evidence_refs", "evidence_references", "evidence"):
        if alias in value:
            evidence_value = value.get(alias)
            break
    if evidence_value is not None:
        evidence_refs = _coerce_evidence_refs(
            state,
            evidence_value,
        )
        if evidence_refs:
            normalized["evidence_refs"] = evidence_refs

    for field_name in ("risk_notes", "assumptions"):
        if field_name in value:
            items = _string_list(value.get(field_name))
            if items:
                normalized[field_name] = items

    if isinstance(missing_fields_from, dict):
        fallback = _coerce_verifier_hypothesis(
            state,
            missing_fields_from,
        )
        if isinstance(fallback, dict):
            for field_name, field_value in fallback.items():
                normalized.setdefault(field_name, field_value)

    return normalized


def _coerce_verification_issue(
    state: TFMStateModel,
    raw_issue: Any,
    *,
    default_type: str | None,
    default_severity: str,
    positional_correction: str | None = None,
) -> dict[str, Any] | None:
    """Convierte una incidencia compacta al contrato cerrado del verificador."""

    if isinstance(raw_issue, str):
        issue_payload: dict[str, Any] = {"description": raw_issue}
    elif isinstance(raw_issue, dict):
        issue_payload = raw_issue
    else:
        return None

    description = (
        _string_or_none(issue_payload.get("description"))
        or _string_or_none(issue_payload.get("claim_text"))
        or _string_or_none(issue_payload.get("statement"))
        or _string_or_none(issue_payload.get("reason"))
        or _string_or_none(issue_payload.get("reasoning"))
    )
    reason = (
        _string_or_none(issue_payload.get("reason"))
        or _string_or_none(issue_payload.get("description"))
        or _string_or_none(issue_payload.get("refutation_criterion"))
        or _string_or_none(issue_payload.get("falsification_criterion"))
        or _joined_string_list(issue_payload.get("risk_notes"))
        or description
    )
    suggested_fix = (
        _issue_correction_text(issue_payload)
        or positional_correction
    )
    if description is None or reason is None or suggested_fix is None:
        return None

    issue_type = _issue_type_alias(
        issue_payload.get("issue_type") or issue_payload.get("type"),
        description=description,
        default=default_type,
    )
    severity = _severity_alias(
        issue_payload.get("severity"),
        default=default_severity,
    )
    raw_refs = (
        issue_payload.get("evidence_refs")
        if "evidence_refs" in issue_payload
        else issue_payload.get("evidence_references")
    )
    if raw_refs is None:
        raw_refs = issue_payload.get("evidence_ref")
    evidence_refs = _coerce_evidence_refs(state, raw_refs)
    if not evidence_refs:
        evidence_refs = ["missing:evidence"]

    # Los IDs son metadatos de trazabilidad, no una decisión semántica. Cuando
    # el contenido coincide con una política conocida usamos su ID canónico,
    # aunque el proveedor haya emitido un alias libre. Así el overlay puede
    # reconocer una incidencia ya detectada sin duplicarla.
    emitted_issue_id = _string_or_none(issue_payload.get("issue_id"))
    if issue_type == "missing_limitation" and _normalized_alias(
        emitted_issue_id
    ) in {"missing_limitation", "missing_persisted_limitations"}:
        issue_id = "missing_persisted_limitations"
    else:
        issue_id = _canonical_issue_id_from_text(
            description,
            issue_type=issue_type,
        )
    if issue_id is None:
        issue_id = emitted_issue_id
    return {
        "issue_id": issue_id,
        "issue_type": issue_type,
        "severity": severity,
        "claim_text": description,
        "reason": reason,
        "evidence_refs": evidence_refs,
        "suggested_fix": suggested_fix,
    }


def _issue_correction_text(issue_payload: dict[str, Any]) -> str | None:
    """Conserva correcciones emitidas con alias habituales del proveedor.

    El contrato canonico usa ``suggested_fix``, pero los modelos suelen reflejar
    la terminologia del prompt como ``required_correction`` o invertirla como
    ``correction_required``. Tambien pueden envolver la misma correccion en una
    lista ``required_corrections``. Solo se adapta forma: no se genera ninguna
    correccion que el modelo no haya emitido.
    """

    for key in (
        "suggested_fix",
        "required_correction",
        "correction_required",
        "correction",
        "required_corrections",
        "expected_observation",
    ):
        corrections = _string_list(issue_payload.get(key))
        if corrections:
            return " ".join(corrections)
    return None


def _joined_string_list(value: Any) -> str | None:
    """Une texto ya emitido por el proveedor sin completar su significado."""

    items = _string_list(value)
    return " ".join(items) if items else None


def _coerce_evidence_refs(state: TFMStateModel, value: Any) -> list[str]:
    """Conserva refs cerradas y marca las desconocidas sin aproximarlas."""

    allowed_refs = set(
        evidence_catalog_for_report_verifier(state)["allowed_evidence_refs"]
    )
    allowed_refs.add("missing:evidence")
    raw_refs = _string_list(value)
    return list(
        dict.fromkeys(
            _closed_evidence_ref_alias(ref, allowed_refs)
            for ref in raw_refs
        )
    )


def _closed_evidence_ref_alias(ref: str, allowed_refs: set[str]) -> str:
    """Admite solo alias mecanicos que resuelven a una ref cerrada existente."""

    if ref in allowed_refs:
        return ref
    if ref.startswith("limitations:"):
        candidate = "limitation:" + ref.removeprefix("limitations:")
        if candidate in allowed_refs:
            return candidate
    return "missing:evidence"


def _issue_type_alias(
    value: Any,
    *,
    description: str,
    default: str | None,
) -> str:
    raw = _normalized_alias(value)
    aliases = {
        "unsupported": "unsupported_claim",
        "unsupported_claim": "unsupported_claim",
        "factual_error": "unsupported_claim",
        "misleading": "misleading_claim",
        "misleading_claim": "misleading_claim",
        "missing_limitation": "missing_limitation",
        "missing_limitations": "missing_limitation",
        "missing_documentation": "missing_limitation",
        "omission": "missing_limitation",
        "policy": "policy_violation",
        "policy_violation": "policy_violation",
    }
    if raw in aliases:
        return aliases[raw]
    if default in {
        "unsupported_claim",
        "misleading_claim",
        "missing_limitation",
        "policy_violation",
    }:
        return default
    text = _normalized_alias(description)
    if any(term in text for term in ("limitacion", "omite", "ausente", "missing")):
        return "missing_limitation"
    if any(
        term in text
        for term in ("politica", "policy", "etiqueta_oficial", "procedencia_oficial")
    ):
        return "policy_violation"
    if any(term in text for term in ("enganos", "misleading", "exagera")):
        return "misleading_claim"
    return "unsupported_claim"


def _severity_alias(value: Any, *, default: str) -> str:
    raw = _normalized_alias(value)
    aliases = {
        "critical": "critical",
        "critica": "critical",
        "critico": "critical",
        "blocking": "critical",
        "high": "high",
        "alta": "high",
        "alto": "high",
        "medium": "medium",
        "media": "medium",
        "medio": "medium",
        "moderate": "medium",
        "non_critical": "medium",
        "noncritical": "medium",
        "no_critica": "medium",
        "no_critico": "medium",
        "low": "low",
        "baja": "low",
        "bajo": "low",
    }
    return aliases.get(raw, default)


def _canonical_issue_id_from_text(
    value: str,
    *,
    issue_type: str | None = None,
) -> str | None:
    normalized = _normalized_alias(value)
    missing_persisted_limitation = "limitacion" in normalized and any(
        term in normalized
        for term in (
            "omite",
            "ausente",
            "no_incluye",
            "falta",
            "sin_declar",
            "sin_incluir",
            "no_se_refleja",
        )
    )
    # El tipo estructurado expresa que la incidencia es una omision. Debe
    # prevalecer sobre menciones incidentales a "validacion industrial" dentro
    # de la explicacion de la limitacion que falta.
    if issue_type == "missing_limitation" and missing_persisted_limitation:
        return "missing_persisted_limitations"
    if any(
        term in normalized
        for term in (
            "validacion_industrial",
            "listo_para_produccion",
            "preparacion_para_produccion",
            "garantiza_su_generalizacion",
            "generalizacion_garantizada",
        )
    ):
        return "unsupported_industrial_validation"
    if "procedencia_oficial" in normalized or "datos_oficiales" in normalized:
        return "non_official_data_provenance_claim"
    if "etiquetas_oficiales" in normalized or "ground_truth_oficial" in normalized:
        return "non_official_labels_claim"
    if missing_persisted_limitation:
        return "missing_persisted_limitations"
    return None


def _normalized_alias(value: Any) -> str:
    raw = _string_or_none(value) or ""
    decomposed = unicodedata.normalize("NFKD", raw)
    ascii_text = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")


def _list_value(value: Any) -> list[Any]:
    if isinstance(value, list | tuple):
        return list(value)
    if value is None:
        return []
    return [value]


def _string_list(value: Any) -> list[str]:
    return [
        text
        for item in _list_value(value)
        if (text := _string_or_none(item)) is not None
    ]


def _reasoning_summary(value: Any) -> str | None:
    items = _string_list(value)
    return " ".join(items) if items else None


def _correction_for_reasoning(
    corrections: list[str],
    index: int,
) -> str | None:
    if not corrections:
        return None
    if index < len(corrections):
        return corrections[index]
    return corrections[-1]


def _status_alias(value: Any) -> str:
    raw = _string_or_none(value)
    if raw is None:
        return "needs_revision"
    normalized = raw.strip().lower()
    if normalized in {"approved", "approve", "ok", "aprobado"}:
        return "approved"
    if normalized in {"blocked", "block", "bloqueado", "critical"}:
        return "blocked"
    return "needs_revision"


def _fallback_reason(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return (
            "Fallback after verifier LLM failure: invalid structured output "
            "was ignored and deterministic verification was used."
        )
    return (
        "Fallback after verifier LLM failure: "
        f"{type(exc).__name__}; deterministic verification was used."
    )


def _string_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _float_or_default(value: Any, default: float) -> float:
    if isinstance(value, int | float):
        return float(value)
    return default


def _merge_deterministic_guardrails(
    state: TFMStateModel,
    report_markdown: str,
    decision: ReportVerificationDecision,
) -> ReportVerificationDecision:
    deterministic_issues = _deterministic_issues(state, report_markdown)
    existing_issues = [
        *decision.unsupported_claims,
        *decision.misleading_claims,
        *decision.missing_limitations,
    ]
    existing_keys = {_issue_key(issue) for issue in existing_issues}
    additions = [
        issue
        for issue in deterministic_issues
        if _issue_key(issue) not in existing_keys
    ]
    unsupported_claims = [
        *decision.unsupported_claims,
        *[issue for issue in additions if issue.issue_type == "unsupported_claim"],
    ]
    misleading_claims = [
        *decision.misleading_claims,
        *[
            issue
            for issue in additions
            if issue.issue_type in {"misleading_claim", "policy_violation"}
        ],
    ]
    missing_limitations = [
        *decision.missing_limitations,
        *[issue for issue in additions if issue.issue_type == "missing_limitation"],
    ]
    all_issues = [
        *unsupported_claims,
        *misleading_claims,
        *missing_limitations,
    ]
    deterministic_status = _status_from_issues(deterministic_issues)
    status = _stronger_verification_status(
        decision.verification_status,
        deterministic_status,
    )
    if not additions and status == decision.verification_status:
        return decision
    required_corrections = list(
        dict.fromkeys(
            [
                *decision.required_corrections,
                *[issue.suggested_fix for issue in additions],
            ]
        )
    )
    evidence_refs = sorted(
        {
            *decision.evidence_refs,
            *[
                ref
                for issue in additions
                for ref in issue.evidence_refs
            ],
        }
    )
    payload = decision.model_dump(mode="json")
    payload.update(
        {
            "rationale": (
                f"{decision.rationale} Deterministic policy guardrails were "
                "applied after the LLM verification."
            ),
            "verification_status": status,
            "summary": _summary_from_status(status, all_issues),
            "unsupported_claims": [
                issue.model_dump(mode="json") for issue in unsupported_claims
            ],
            "misleading_claims": [
                issue.model_dump(mode="json") for issue in misleading_claims
            ],
            "missing_limitations": [
                issue.model_dump(mode="json") for issue in missing_limitations
            ],
            "required_corrections": required_corrections,
            "evidence_refs": evidence_refs,
            "policy_overlay_applied": True,
            "policy_overlay_issue_ids": list(
                dict.fromkeys(
                    _issue_key(issue) for issue in additions
                )
            ),
        }
    )
    return ReportVerificationDecision.model_validate(payload)


def _issue_key(issue: ReportVerificationIssue) -> str:
    if issue.issue_id:
        return f"id:{issue.issue_id}"
    return f"content:{issue.issue_type}:{issue.claim_text}"


def _stronger_verification_status(current: str, required: str) -> str:
    rank = {"approved": 0, "needs_revision": 1, "blocked": 2}
    return current if rank[current] >= rank[required] else required


def _deterministic_issues(
    state: TFMStateModel,
    report_markdown: str,
) -> list[ReportVerificationIssue]:
    text = _normalize(report_markdown)
    issues: list[ReportVerificationIssue] = []
    if uses_online_blind_view(state):
        unsupported_claims = unsupported_official_v2_claims([report_markdown])
        if unsupported_claims:
            issues.append(
                ReportVerificationIssue(
                    issue_id="official_v2_physical_claim",
                    issue_type="policy_violation",
                    severity="high",
                    claim_text=(
                        "El informe atribuye significado fisico validado a evidencia "
                        "algoritmica retrospectiva."
                    ),
                    reason=(
                        "NASA IMS oficial v2 no aporta ground truth fisico por snapshot; "
                        "los controles internos no validan deteccion, diagnostico, "
                        "inicio fisico ni RUL. Guardarrails activados: "
                        + ", ".join(unsupported_claims)
                        + "."
                    ),
                    evidence_refs=[
                        "report:final_report",
                        f"dataset:{state.project_context.dataset}",
                        f"label_source:{state.project_context.label_source}",
                        f"data_provenance:{state.project_context.data_provenance}",
                    ],
                    suggested_fix=(
                        "Reformular como primera alerta algoritmica persistente, tiempo "
                        "retrospectivo hasta el final registrado, tasa de alertas "
                        "pre-monitorizacion y aceptacion por controles internos."
                    ),
                )
            )
    if _contains_industrial_validation_claim(text):
        issues.append(
                ReportVerificationIssue(
                    issue_id="unsupported_industrial_validation",
                    issue_type="unsupported_claim",
                    severity="critical",
                claim_text="El informe sugiere validacion industrial o uso productivo.",
                reason=(
                    "La evidencia disponible corresponde a una ejecucion local del TFM, "
                    "no a una validacion industrial en produccion."
                ),
                evidence_refs=[
                    "report:final_report",
                    "objective:" + state.project_context.objective,
                ],
                suggested_fix=(
                    "Reformular como resultado local/auditable del TFM y explicitar "
                    "que no equivale a validacion industrial final."
                ),
            )
        )
    if (
        state.project_context.data_provenance != "official"
        and _contains_official_data_claim(text)
    ):
        issues.append(
            ReportVerificationIssue(
                issue_id="non_official_data_provenance_claim",
                issue_type="policy_violation",
                severity="critical",
                claim_text=(
                    "El informe presenta datos, senales o mediciones como si su "
                    "procedencia oficial estuviera verificada."
                ),
                reason=(
                    "La procedencia de las senales es "
                    f"{state.project_context.data_provenance}; label_source no "
                    "demuestra el origen de las mediciones."
                ),
                evidence_refs=[
                    "report:final_report",
                    f"dataset:{state.project_context.dataset}",
                    f"data_provenance:{state.project_context.data_provenance}",
                ],
                suggested_fix=(
                    "Eliminar la atribucion de datos oficiales y declarar la "
                    "procedencia de las senales segun el estado validado."
                ),
            )
        )
    if not _mentions_required_data_provenance(
        text,
        state.project_context.data_provenance,
    ):
        issues.append(
            ReportVerificationIssue(
                issue_id="missing_data_provenance_disclosure",
                issue_type="missing_limitation",
                severity="high",
                claim_text="El informe omite la procedencia no oficial de las senales.",
                reason=(
                    "La politica exige declarar data_provenance="
                    f"{state.project_context.data_provenance} para evitar confundir "
                    "el nombre del adaptador con el origen de las mediciones."
                ),
                evidence_refs=[
                    "report:final_report",
                    f"data_provenance:{state.project_context.data_provenance}",
                ],
                suggested_fix=(
                    "Anadir una declaracion explicita de procedencia y, si es "
                    "synthetic o unknown, indicar que no son datos oficiales."
                ),
            )
        )
    if _requires_non_official_label_guardrail(state) and _contains_official_label_claim(text):
        issues.append(
            ReportVerificationIssue(
                issue_id="non_official_labels_claim",
                issue_type="policy_violation",
                severity="critical",
                claim_text=(
                    "El informe presenta etiquetas por ventana como si fueran oficiales."
                ),
                reason=(
                    "La politica del proyecto exige declarar etiquetas proxy, "
                    "sinteticas, temporales o ausentes cuando label_source no "
                    "es official."
                ),
                evidence_refs=[
                    "report:final_report",
                    f"dataset:{state.project_context.dataset}",
                    f"label_source:{state.project_context.label_source}",
                ],
                suggested_fix=(
                    "Indicar que las etiquetas por ventana no son oficiales y "
                    "proceden de la politica temporal/proxy/sintetica declarada."
                ),
            )
        )
    if state.evaluation is not None and not state.evaluation.approved:
        if uses_online_blind_view(state):
            missing_non_acceptance = not _mentions_failed_operational_controls(text)
        else:
            missing_non_acceptance = not _mentions_not_approved(text)
        if missing_non_acceptance:
            if uses_online_blind_view(state):
                claim_text = (
                    "El informe no deja claro que la run no supero los controles "
                    "operativos internos."
                )
                reason = (
                    "El resultado estructurado indica que los controles operativos "
                    "internos no fueron superados."
                )
                suggested_fix = (
                    "Anadir una limitacion explicita indicando que la run no supero "
                    "los controles operativos internos."
                )
            else:
                claim_text = "El informe no deja clara la no aprobacion de la run."
                reason = "El evaluador estructurado marco la ejecucion como no aprobada."
                suggested_fix = (
                    "Anadir una limitacion explicita indicando que la run no "
                    "queda aprobada por el evaluador."
                )
            issues.append(
                ReportVerificationIssue(
                    issue_id="missing_not_approved_limitation",
                    issue_type="missing_limitation",
                    severity="high",
                    claim_text=claim_text,
                    reason=reason,
                    evidence_refs=["report:final_report", "evaluation:not_approved"],
                    suggested_fix=suggested_fix,
                )
            )
    if state.evaluation is not None and state.evaluation.limitations:
        if not _mentions_limitations(text):
            issues.append(
                ReportVerificationIssue(
                    issue_id="missing_persisted_limitations",
                    issue_type="missing_limitation",
                    severity="medium",
                    claim_text="El informe no incluye una seccion o mencion clara de limitaciones.",
                    reason="La evaluacion contiene limitaciones persistidas.",
                    evidence_refs=["report:final_report", "limitation:1"],
                    suggested_fix=(
                        "Incluir las limitaciones declaradas por el evaluador o "
                        "una remision clara al bloque de limitaciones."
                    ),
                )
            )
    return issues


def _read_report(state: TFMStateModel) -> str:
    if not state.report_path:
        return ""
    path = Path(state.report_path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _expected_report_path(state: TFMStateModel) -> str:
    if state.report_path:
        return state.report_path
    return f"codigo/reports/{state.project_context.dataset}/{state.run_id}/final_report.md"


def _safe_evidence_refs(state: TFMStateModel) -> list[str]:
    return list(evidence_catalog_for_report_verifier(state)["allowed_evidence_refs"])


def _status_from_issues(
    issues: list[ReportVerificationIssue],
) -> str:
    if any(issue.severity == "critical" for issue in issues):
        return "blocked"
    if issues:
        return "needs_revision"
    return "approved"


def _summary_from_status(
    status: str,
    issues: list[ReportVerificationIssue],
) -> str:
    if status == "approved":
        return (
            "El informe no presenta afirmaciones falsas o no soportadas detectables "
            "por la verificacion minima."
        )
    if status == "blocked":
        return "El informe contiene al menos una incidencia critica de politica o evidencia."
    return (
        "El informe requiere revision antes de considerarse verificado: "
        f"{len(issues)} incidencia(s)."
    )


def _truncate_report(
    report_markdown: str,
    *,
    max_chars: int = MAX_REPORT_CHARS_FOR_LLM,
) -> str:
    """Extrae secciones relevantes sin privilegiar ciegamente inicio o final."""

    if len(report_markdown) <= max_chars:
        return report_markdown
    sections = _markdown_report_sections(report_markdown)
    ranked = sorted(
        sections,
        key=lambda item: (
            _report_section_priority(item[1], item[2]),
            item[0],
        ),
    )
    notice = (
        "[EXTRACTO SEMANTICO: se priorizan conclusiones, limitaciones, "
        "evidencias, resultados y evaluacion.]\n"
    )
    remaining = max_chars - len(notice)
    excerpts: list[str] = []
    for _index, heading, content in ranked:
        if remaining < 160:
            break
        priority = _report_section_priority(heading, content)
        section_cap = min(
            remaining,
            1900 if priority == 0 else 1250 if priority == 1 else 750,
        )
        excerpt = _semantic_section_excerpt(
            heading,
            content,
            max_chars=section_cap,
        )
        if not excerpt:
            continue
        excerpts.append(excerpt)
        remaining -= len(excerpt) + 2
    result = notice + "\n\n".join(excerpts)
    if len(result) <= max_chars:
        return result
    return _clip_report_fragment(result, max_chars)


def _markdown_report_sections(
    report_markdown: str,
) -> list[tuple[int, str, str]]:
    heading_pattern = re.compile(r"(?m)^(#{1,6}\s+[^\n]+)\s*$")
    matches = list(heading_pattern.finditer(report_markdown))
    if not matches:
        paragraphs = [
            paragraph.strip()
            for paragraph in re.split(r"\n\s*\n", report_markdown)
            if paragraph.strip()
        ]
        return [
            (index, "Bloque sin encabezado", paragraph)
            for index, paragraph in enumerate(paragraphs)
        ]
    sections: list[tuple[int, str, str]] = []
    prefix = report_markdown[: matches[0].start()].strip()
    if prefix:
        sections.append((0, "Preambulo", prefix))
    offset = len(sections)
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else None
        sections.append(
            (
                index + offset,
                match.group(1).strip(),
                report_markdown[match.end() : end].strip(),
            )
        )
    return sections


def _report_section_priority(heading: str, content: str) -> int:
    context = _normalize(f"{heading} {content[:600]}")
    if re.search(r"conclusi[oó]n|limitaci[oó]n|evidencia", context):
        return 0
    if re.search(
        r"resumen ejecutivo|resultado|m[eé]trica|evaluaci[oó]n|hallazgo|recomend",
        context,
    ):
        return 1
    return 2


def _semantic_section_excerpt(
    heading: str,
    content: str,
    *,
    max_chars: int,
) -> str:
    label = heading if heading.startswith("#") else f"## {heading}"
    if not content:
        return _clip_report_fragment(label, max_chars)
    full = f"{label}\n{content}"
    if len(full) <= max_chars:
        return full
    paragraphs = [
        paragraph.strip()
        for paragraph in re.split(r"\n\s*\n", content)
        if paragraph.strip()
    ]
    ranked = sorted(
        enumerate(paragraphs),
        key=lambda item: (
            _report_section_priority("", item[1]),
            item[0],
        ),
    )
    selected = [label]
    remaining = max_chars - len(label) - 1
    for _index, paragraph in ranked:
        if remaining < 80:
            break
        fragment = _clip_report_fragment(paragraph, remaining)
        selected.append(fragment)
        remaining -= len(fragment) + 2
    return "\n\n".join(selected)


def _clip_report_fragment(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    if max_chars <= 20:
        return text[:max_chars]
    clipped = text[: max_chars - 15].rsplit(" ", 1)[0].rstrip()
    if not clipped:
        clipped = text[: max_chars - 15].rstrip()
    return clipped + " [recortado]"


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _contains_industrial_validation_claim(text: str) -> bool:
    patterns = [
        r"validaci[oó]n industrial",
        r"validado industrialmente",
        r"listo para producci[oó]n",
        r"garantiza la detecci[oó]n",
        r"garantiza.*anomalias",
        r"garantiza (?:su |la )?generalizaci[oó]n",
        r"generalizaci[oó]n garantizada",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            if not _is_negated_or_limited_claim_context(
                text,
                match.start(),
                match.end(),
            ):
                return True
    return False


def _is_negated_or_limited_claim_context(
    text: str,
    start: int,
    end: int,
) -> bool:
    window = text[max(0, start - 90): min(len(text), end + 90)]
    disclaimer_patterns = [
        r"no\s+(?:equivale|es|representa|constituye|implica|garantiza)",
        r"no\s+a\s+una?\s+validaci[oó]n\s+industrial",
        r"no\s+como\s+validaci[oó]n\s+industrial",
        r"no\s+debe\s+interpretarse",
        r"sin\s+validaci[oó]n\s+industrial",
        r"requiere\s+validar",
        r"requiere\s+validaci[oó]n",
        r"requiere\s+validar\s+otros\s+datasets",
        r"baseline\s+local",
        r"resultado\s+local",
        r"protocolo\s+local",
        r"validaci[oó]n\s+limitada",
    ]
    return any(re.search(pattern, window) for pattern in disclaimer_patterns)


def _contains_official_label_claim(text: str) -> bool:
    patterns = [
        r"etiquetas oficiales",
        r"labels oficiales",
        r"etiquetado oficial",
        r"ground truth oficial",
        r"verdad oficial",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            window = text[max(0, match.start() - 80) : match.end() + 80]
            if not _negates_official_label_claim(window):
                return True
    return False


def _contains_official_data_claim(text: str) -> bool:
    patterns = [
        r"(?:datos|se[nñ]ales|mediciones)\s+oficiales(?:\s+(?:de|del))?\s+(?:la\s+)?nasa",
        r"(?:datos|se[nñ]ales|mediciones)\s+oficiales[^.]{0,60}\bnasa\b",
        r"dataset\s+oficial(?:\s+(?:de|del))?\s+(?:la\s+)?nasa",
        r"dataset(?:\s+(?:de|del))?\s+(?:la\s+)?nasa[^.]{0,40}\boficial\b",
        r"(?:datos|se[nñ]ales|mediciones)\s+(?:de|del)\s+(?:la\s+)?nasa[^.]{0,40}\boficiales\b",
        r"procedencia\s+(?:de\s+(?:datos|se[nñ]ales)\s+)?(?:es\s+)?official\b",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            window = text[max(0, match.start() - 100) : match.end() + 100]
            if not _negates_official_data_claim(window):
                return True
    return False


def _negates_official_data_claim(window: str) -> bool:
    patterns = [
        r"no\s+(?:son|es|proceden\s+de|corresponden\s+a)\s+[^.]{0,100}"
        r"(?:datos|se[nñ]ales|mediciones|dataset)\s+oficial",
        r"no\s+(?:debe[n]?|puede[n]?)\s+(?:presentarse|tratarse)\s+como\s+[^.]{0,80}"
        r"(?:datos|se[nñ]ales|mediciones|dataset)\s+oficial",
        r"sin\s+(?:datos|se[nñ]ales|mediciones)\s+oficiales",
        r"origen\s+no\s+verificado[^.]{0,100}(?:datos|se[nñ]ales|mediciones)\s+oficial",
    ]
    return any(re.search(pattern, window) for pattern in patterns)


def _mentions_required_data_provenance(text: str, data_provenance: str) -> bool:
    if data_provenance == "official":
        return True
    if data_provenance == "synthetic":
        patterns = [
            r"procedencia\s+(?:de\s+datos\s*:\s*)?`?synthetic`?",
            r"(?:datos|se[nñ]ales|mediciones)\s+sint[eé]tic",
            r"benchmark\s+[^.]{0,40}sint[eé]tic",
        ]
    else:
        patterns = [
            r"procedencia\s+(?:de\s+datos\s*:\s*)?`?unknown`?",
            r"procedencia\s+[^.]{0,40}no\s+(?:esta\s+)?verificad",
            r"origen\s+no\s+verificad",
        ]
    return any(re.search(pattern, text) for pattern in patterns)


def _negates_official_label_claim(window: str) -> bool:
    patterns = [
        r"no\s+(?:son|es|proceden\s+de|corresponden\s+a)\s+[^.]{0,80}"
        r"(?:etiquetas oficiales|labels oficiales|etiquetado oficial|ground truth oficial|verdad oficial)",
        r"(?:etiquetas oficiales|labels oficiales|etiquetado oficial|ground truth oficial|verdad oficial)"
        r"\s+[^.]{0,80}no\s+(?:existen|estan|son|se\s+usan|se\s+declaran|se\s+presentan)",
        r"no\s+como\s+(?:ground truth oficial|etiquetas oficiales|labels oficiales)",
        r"no\s+debe[n]?\s+tratarse\s+como\s+(?:ground truth oficial|etiquetas oficiales|labels oficiales)",
        r"sin\s+(?:etiquetas oficiales|labels oficiales|ground truth oficial)",
    ]
    return any(re.search(pattern, window) for pattern in patterns)


def _requires_non_official_label_guardrail(state: TFMStateModel) -> bool:
    return state.project_context.label_source != "official"


def _mentions_not_approved(text: str) -> bool:
    patterns = [
        r"no aprob",
        r"rechazad",
        r"no queda aprob",
        r"metricas insuficientes",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def _mentions_failed_operational_controls(text: str) -> bool:
    patterns = [
        r"no (?:supera|supero|ha superado) (?:los )?controles operativos internos",
        r"controles operativos internos[^.]{0,40}(?:no superados|incumplidos)",
        r"sin superar (?:los )?controles operativos internos",
    ]
    return any(re.search(pattern, text) for pattern in patterns)


def _mentions_limitations(text: str) -> bool:
    return "limitacion" in text or "limitaciones" in text or "limitada" in text


def _verifier_turn(state: TFMStateModel) -> int:
    return 1 + sum(
        message.role == "agent" and message.name == "report_verifier"
        for message in state.messages
    )
