"""Guardarrail para la vista causal que reciben los agentes online."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

from codigo.app.schemas.state import TFMStateModel


ONLINE_BLIND_DECISION_AGENTS = frozenset(
    {
        "supervisor",
        "cleaner",
        "structurer",
        "modeler",
        "researcher",
    }
)


ONLINE_BLIND_FORBIDDEN_EXACT_KEYS = {
    "end_of_life",
    "eol",
    "failure",
    "fault_type",
    "fault_types",
    "final_event",
    "label",
    "label_counts",
    "labels",
    "relative_life",
    "target",
    "targets",
    "temporal_order_count",
}

ONLINE_BLIND_FORBIDDEN_KEY_FRAGMENTS = {
    "failure_event",
    "failure_mode",
    "final_failure",
    "lead_time",
    "time_to_failure",
}


# Estas expresiones se aplican solo al caso oficial sin ground truth por snapshot.
# No prohíben explicar las limitaciones: bloquean formulaciones afirmativas que
# convertirían una alerta algorítmica retrospectiva en un hecho físico validado.
OFFICIAL_V2_UNSUPPORTED_CLAIM_PATTERNS: tuple[tuple[str, str], ...] = (
    (
        "confirmed_physical_onset",
        r"\bonset[ _]confirmado\b|\bconfirmed[ _]onset\b|\bonset[ _]confirmed\b",
    ),
    (
        "confirmed_degradation_start",
        r"\binicio (?:fisico )?(?:de la )?degradacion confirmado\b",
    ),
    (
        "confirmed_physical_degradation",
        r"\bdegradacion (?:fisica )?confirmada\b"
        r"|\bconfirmed (?:physical )?degradation\b",
    ),
    (
        "detected_physical_failure",
        r"\bfallo (?:detectado|confirmado|diagnosticado)\b"
        r"|\bfailure (?:detected|confirmed|diagnosed)\b",
    ),
    (
        "detection_before_failure",
        r"\b(?:deteccion|detected|detectado|detectada) (?:confirmada )?"
        r"(?:antes|before) (?:de |del |the )?(?:fallo|failure)\b",
    ),
    (
        "lead_time_to_failure",
        r"\blead[ _-]time(?:[ _-](?:persistente|medio|promedio|mean|average))?\b"
        r"|\blead[ _]time "
        r"(?:persistente )?(?:hasta|a|to) (?:el |the )?(?:fallo|failure)\b"
        r"|\blead_time[^\s,;:.]*failure\b"
        r"|\btiempo (?:restante )?(?:hasta|a) (?:el )?fallo\b",
    ),
    (
        "estimated_rul",
        r"\brul (?:esta |is )?estimad[oa]\b|\bestimated rul\b",
    ),
    (
        "validated_diagnosis",
        r"\bdiagnostico (?:confirmado|validado)\b"
        r"|\b(?:confirmed|validated) diagnosis\b",
    ),
    (
        "failure_prediction",
        r"\b(?:predice|predijo|predicts|predicted) (?:el |the )?"
        r"(?:fallo|failure)\b",
    ),
    ("approval_overclaim", r"\baprob(?:ada|ado)\b|\bapproved\b"),
    (
        "industrial_validation_overclaim",
        r"\b(?:deteccion|diagnostico) (?:industrial )?validada\b"
        r"|\bvalidated (?:industrial )?(?:detection|diagnosis)\b",
    ),
)


def uses_online_blind_view(state: TFMStateModel) -> bool:
    """Identifica el caso oficial run-to-failure sin etiquetas por snapshot."""

    context = state.project_context
    return (
        context.dataset == "nasa_ims_bearing"
        and context.supervision_profile == "run_to_failure_degradation"
        and context.data_provenance == "official"
        and context.label_source == "none"
    )


def is_online_blind_decision_agent(
    state: TFMStateModel,
    agent_name: str,
) -> bool:
    """Indica si una herramienta alimentaria una decision causal pre-evaluacion."""

    return uses_online_blind_view(state) and agent_name in ONLINE_BLIND_DECISION_AGENTS


def sanitize_online_blind_payload(payload: Any) -> Any:
    """Elimina campos retrospectivos de un payload destinado a un agente."""

    if isinstance(payload, dict):
        return {
            str(key): sanitize_online_blind_payload(value)
            for key, value in payload.items()
            if not is_online_blind_forbidden_key(str(key))
        }
    if isinstance(payload, list):
        return [sanitize_online_blind_payload(value) for value in payload]
    if isinstance(payload, tuple):
        return [sanitize_online_blind_payload(value) for value in payload]
    return payload


def online_blind_forbidden_paths(payload: Any, *, prefix: str = "") -> list[str]:
    """Localiza claves prohibidas de forma recursiva para auditoria y tests."""

    paths: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            text = str(key)
            path = f"{prefix}.{text}" if prefix else text
            if is_online_blind_forbidden_key(text):
                paths.append(path)
            paths.extend(online_blind_forbidden_paths(value, prefix=path))
    elif isinstance(payload, list | tuple):
        for index, value in enumerate(payload):
            path = f"{prefix}[{index}]" if prefix else f"[{index}]"
            paths.extend(online_blind_forbidden_paths(value, prefix=path))
    return sorted(set(paths))


def assert_online_blind_payload(payload: Any) -> None:
    """Falla de forma explicita si un expediente contiene claves futuras."""

    forbidden = online_blind_forbidden_paths(payload)
    if forbidden:
        raise ValueError(
            "online_blind payload contains retrospective keys: "
            + ", ".join(forbidden)
        )


def unsupported_official_v2_claims(texts: list[str] | tuple[str, ...]) -> list[str]:
    """Detecta afirmaciones físicas no respaldadas en narrativa oficial v2."""

    # Cada campo narrativo es una unidad independiente. El separador explicito
    # evita que una negacion al final de un campo pueda exonerar una afirmacion
    # positiva situada en el siguiente.
    normalized = _normalize_claim_text(". ".join(texts))
    unsupported: list[str] = []
    for claim_id, pattern in OFFICIAL_V2_UNSUPPORTED_CLAIM_PATTERNS:
        if any(
            not _is_explicitly_negated_or_scoped_claim(
                normalized,
                match.start(),
                match.end(),
                claim_id=claim_id,
            )
            for match in re.finditer(pattern, normalized)
        ):
            unsupported.append(claim_id)
    return unsupported


def assert_official_v2_claims_are_scoped(
    state: TFMStateModel,
    texts: list[str] | tuple[str, ...],
) -> None:
    """Impide convertir métricas retrospectivas en validación física oficial."""

    if not uses_online_blind_view(state):
        return
    unsupported = unsupported_official_v2_claims(texts)
    if unsupported:
        raise ValueError(
            "official NASA IMS causal v2 narrative contains unsupported physical "
            "claims: " + ", ".join(unsupported)
        )


def is_online_blind_forbidden_key(key: str) -> bool:
    """Aplica la lista versionada de familias de campos retrospectivos."""

    normalized = key.strip().lower()
    if normalized in ONLINE_BLIND_FORBIDDEN_EXACT_KEYS:
        return True
    if normalized.startswith("failure_") or normalized.endswith("_failure"):
        return True
    return any(
        fragment in normalized
        for fragment in ONLINE_BLIND_FORBIDDEN_KEY_FRAGMENTS
    )


def _normalize_claim_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_text = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return " ".join(ascii_text.lower().split())


def _is_explicitly_negated_or_scoped_claim(
    text: str,
    start: int,
    end: int,
    *,
    claim_id: str,
) -> bool:
    """Distingue una limitacion explicita de la afirmacion fisica positiva."""

    clause_start = max(
        text.rfind(separator, 0, start)
        for separator in (".", ";", ":", "!", "?")
    ) + 1
    following_boundaries = [
        position
        for separator in (".", ";", ":", "!", "?")
        if (position := text.find(separator, end)) >= 0
    ]
    clause_end = min(following_boundaries) if following_boundaries else len(text)
    prefix = text[clause_start:start][-140:]
    suffix = text[end:clause_end][:160]
    clause_prefix = text[clause_start:start][-240:]
    clause_suffix = text[end:clause_end][:240]

    explicit_prefixes = (
        r"\bno\s+(?:(?:se|es|son|esta|estan|queda|quedan|hay|ha|han|puede|"
        r"pueden|debe|deben|constituye|representa|implica|equivale|supone|"
        r"permite|demuestra|confirma|considera|considerarse|interpretarse|"
        r"presenta|presentarse|trata|tratarse|de|como|afirmar|afirma|afirman|"
        r"reporta|reportan|estima|estiman|calcula|calculan|valida|validan|"
        r"confirmado|confirmada|un|una|el|la|"
        r"ningun|ninguna)\s+){0,8}$",
        r"\bsin\s+(?:(?:un|una|el|la|ningun|ninguna)\s+)?$",
        r"\bni\s+$",
        r"\bcarece\s+de\s+(?:(?:un|una|el|la)\s+)?$",
    )
    if any(re.search(pattern, prefix) for pattern in explicit_prefixes):
        return True

    explicit_suffixes = (
        r"^\s*no\s+(?:(?:esta|estan|es|son|queda|se encuentra|se ha)\s+)?(?:disponible|"
        r"aplicable|valid[oa]s?|validad[oa]|respaldad[oa]|demostrad[oa]|"
        r"confirmad[oa])\b",
        r"^\s*(?:queda|esta|se encuentra)\s+fuera\s+del\s+alcance\b",
        r"^\s*,?\s*pero\s+no\s+(?:esta|es|queda)\s+(?:respaldad[oa]|"
        r"demostrad[oa]|confirmad[oa])\b",
    )
    if any(re.search(pattern, suffix) for pattern in explicit_suffixes):
        return True

    # El redactor puede citar una etiqueta rechazada para declarar que es
    # invalida o que debe eliminarse. Se exige un predicado de rechazo
    # explicito; mencionar la etiqueta sin ese alcance sigue bloqueado.
    if (
        re.search(r"\b(?:afirmaciones?|expresiones?|etiquetas?|terminos?)\b", clause_prefix)
        and re.search(
            r"\b(?:son|resultan|se consideran)\s+(?:invalid[oa]s?|"
            r"no\s+(?:valid[oa]s?|respaldad[oa]s?))\b",
            clause_suffix,
        )
    ):
        return True
    if re.search(
        r"\b(?:eliminar|evitar|retirar)\s+(?:las\s+)?(?:afirmaciones?|"
        r"expresiones?|etiquetas?|terminos?)?[^.;:!?]{0,140}$",
        clause_prefix,
    ):
        return True
    if (
        re.search(r"\b(?:ni|o)\s*['\"]?\s*$", prefix)
        and re.search(
            r"\bno\s+(?:se\s+)?(?:(?:puede|pueden|debe|deben)\s+)?"
            r"(?:afirmar|reportar|usar|presentar|estimar|calcular|validar)\b",
            clause_prefix,
        )
    ):
        return True

    if claim_id == "approval_overclaim" and re.search(
        r"^\s*(?:(?:solo|unicamente|exclusivamente)\s+)?(?:por|como)\s+"
        r"(?:los\s+)?controles?\s+(?:operativos?\s+)?internos?\b",
        suffix,
    ):
        return True
    return False
