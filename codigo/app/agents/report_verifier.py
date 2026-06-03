"""Agente verificador del informe final con herramientas deterministas."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from codigo.app.schemas.agent_decisions import (
    ReportVerificationDecision,
    ReportVerificationIssue,
)
from codigo.app.schemas.state import TFMStateModel
from codigo.app.services.llm import (
    JSONLLMClient,
    LLMCallError,
    LLMMessage,
    get_default_json_llm_client,
)
from codigo.app.services.agent_tools import build_state_evidence_catalog


MAX_REPORT_CHARS_FOR_LLM = 14000
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
        try:
            client = llm_client or get_default_json_llm_client()
            return decide_report_verification_action_with_llm(
                state,
                report_text,
                client,
            )
        except (LLMCallError, ValidationError, ValueError, OSError) as exc:
            fallback = decide_report_verification_action_deterministic(
                state,
                report_markdown=report_text,
            )
            fallback.rationale = f"{fallback.rationale} {_fallback_reason(exc)}"
            fallback.confidence = min(fallback.confidence, 0.65)
            return fallback

    return decide_report_verification_action_deterministic(
        state,
        report_markdown=report_text,
    )


def decide_report_verification_action_with_llm(
    state: TFMStateModel,
    report_markdown: str,
    llm_client: JSONLLMClient,
) -> ReportVerificationDecision:
    """Solicita al LLM una verificacion factual validada."""

    payload = llm_client.complete_json(
        _report_verifier_messages(state, report_markdown),
        json_schema=ReportVerificationDecision.model_json_schema(),
    )
    payload = _coerce_verification_payload(state, payload)
    decision = ReportVerificationDecision.model_validate(payload)
    _validate_verification_decision_bounds(state, decision)
    return decision


def decide_report_verification_action_deterministic(
    state: TFMStateModel,
    *,
    report_markdown: str | None = None,
) -> ReportVerificationDecision:
    """Fallback reproducible: detecta riesgos evidentes sin reescribir el informe."""

    report_text = report_markdown if report_markdown is not None else _read_report(state)
    issues = _deterministic_issues(state, report_text)
    status = _status_from_issues(issues)
    return ReportVerificationDecision(
        decision_id=f"{state.run_id}:report_verifier:{_verifier_turn(state):03d}",
        rationale=(
            "Fallback verifier policy: check obvious unsupported industrial claims, "
            "dataset policy risks and missing critical limitations. Style choices are "
            "accepted when they do not change factual meaning."
        ),
        confidence=0.72 if issues else 0.78,
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


def evidence_catalog_for_report_verifier(state: TFMStateModel) -> dict[str, Any]:
    """Construye el catalogo cerrado de evidencias que puede citar el verificador."""

    return build_state_evidence_catalog(state)


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
    return [
        LLMMessage(
            role="system",
            content=(
                "Eres report_verifier, un agente auditor de informes de deteccion "
                "de anomalias industriales. Debes ser tolerante con estilo, orden "
                "y enfasis, pero estricto con afirmaciones falsas, exageradas o "
                "sin evidencia. No exijas coincidencia literal con un informe "
                "esperado. No ejecutes codigo ni inventes evidencias. Devuelve "
                "solo JSON compatible con ReportVerificationDecision."
            ),
        ),
        LLMMessage(
            role="user",
            content="\n".join(
                [
                    "Informe final Markdown:",
                    _truncate_report(report_markdown),
                    "",
                    "Catalogo cerrado de evidencias permitidas:",
                    json.dumps(
                        evidence_catalog_for_report_verifier(state),
                        indent=2,
                        ensure_ascii=True,
                    ),
                    "",
                    "Reglas de verificacion:",
                    "- Marca approved si el informe es factual aunque cambie estilo u orden.",
                    "- Marca needs_revision si hay problemas corregibles.",
                    "- Marca blocked solo si el informe contiene una afirmacion grave "
                    "o una violacion metodologica critica.",
                    "- No penalices que el informe no use exactamente las mismas palabras.",
                    "- Cada issue debe citar evidence_refs del catalogo o missing:evidence.",
                    "- No aceptes validacion industrial, etiquetas oficiales o aprobacion "
                    "si la evidencia no lo respalda.",
                    (
                        "- Si label_source no es official, cualquier frase que "
                        "atribuya etiquetas oficiales o ground truth oficial "
                        "debe marcarse como policy_violation."
                    ),
                    f"- report_path debe ser: {_expected_report_path(state)}.",
                    f"- decision_id debe ser: {state.run_id}:report_verifier:{_verifier_turn(state):03d}.",
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
    return os.getenv(REPORT_VERIFIER_MODE_ENV, "").strip().lower() == "llm"


def _validate_verification_decision_bounds(
    state: TFMStateModel,
    decision: ReportVerificationDecision,
) -> None:
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


def _coerce_verification_payload(
    state: TFMStateModel,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Normaliza alias frecuentes antes de validar el contrato estricto."""

    allowed = {
        "agent_name",
        "decision_id",
        "rationale",
        "confidence",
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
    normalized = {
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
    normalized.setdefault(
        "verification_status",
        _status_alias(payload.get("decision") or payload.get("status")),
    )
    normalized.setdefault(
        "summary",
        _string_or_none(payload.get("summary"))
        or _string_or_none(payload.get("notes"))
        or "Verificacion factual del informe completada.",
    )
    normalized.setdefault(
        "rationale",
        _string_or_none(payload.get("rationale"))
        or _string_or_none(payload.get("notes"))
        or "LLM verifier output normalized to the strict report verification schema.",
    )
    normalized.setdefault("confidence", _float_or_default(payload.get("confidence"), 0.74))
    normalized.setdefault("unsupported_claims", [])
    normalized.setdefault("misleading_claims", [])
    normalized.setdefault("missing_limitations", [])
    normalized.setdefault("required_corrections", [])
    normalized.setdefault("acceptable_style_notes", [])
    if "evidence_refs" not in normalized:
        normalized["evidence_refs"] = payload.get("evidence_references") or [
            "report:final_report"
        ]
    return normalized


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


def _deterministic_issues(
    state: TFMStateModel,
    report_markdown: str,
) -> list[ReportVerificationIssue]:
    text = _normalize(report_markdown)
    issues: list[ReportVerificationIssue] = []
    if _contains_industrial_validation_claim(text):
        issues.append(
            ReportVerificationIssue(
                issue_id="unsupported_industrial_validation",
                issue_type="unsupported_claim",
                severity="high",
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
        if not _mentions_not_approved(text):
            issues.append(
                ReportVerificationIssue(
                    issue_id="missing_not_approved_limitation",
                    issue_type="missing_limitation",
                    severity="high",
                    claim_text="El informe no deja clara la no aprobacion de la run.",
                    reason="El evaluador estructurado marco la ejecucion como no aprobada.",
                    evidence_refs=["report:final_report", "evaluation:not_approved"],
                    suggested_fix=(
                        "Anadir una limitacion explicita indicando que la run no "
                        "queda aprobada por el evaluador."
                    ),
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


def _truncate_report(report_markdown: str) -> str:
    if len(report_markdown) <= MAX_REPORT_CHARS_FOR_LLM:
        return report_markdown
    return (
        report_markdown[:MAX_REPORT_CHARS_FOR_LLM]
        + "\n\n[TRUNCATED: informe recortado para verificacion LLM]\n"
    )


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _contains_industrial_validation_claim(text: str) -> bool:
    patterns = [
        r"validaci[oó]n industrial",
        r"validado industrialmente",
        r"listo para producci[oó]n",
        r"garantiza la detecci[oó]n",
        r"garantiza.*anomalias",
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


def _mentions_limitations(text: str) -> bool:
    return "limitacion" in text or "limitaciones" in text or "limitada" in text


def _verifier_turn(state: TFMStateModel) -> int:
    return 1 + sum(
        message.role == "agent" and message.name == "report_verifier"
        for message in state.messages
    )
