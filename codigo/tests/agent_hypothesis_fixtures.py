"""Adaptadores de fixtures LLM al contrato comun de hipotesis.

Los payloads historicos de los tests siguen centrados en la regla concreta que
pretenden comprobar. Este helper hace que el cliente simulado represente una
respuesta LLM actual sin ocultar campos explicitamente puestos a ``None``.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def with_test_agent_hypothesis(payload: dict[str, Any]) -> dict[str, Any]:
    enriched = deepcopy(payload)
    if "hypothesis" in enriched:
        return enriched

    agent_name = str(enriched.get("agent_name") or "")
    if not agent_name and any(
        key in enriched
        for key in (
            "verification_status",
            "classification",
            "unsupported_claims",
            "misleading_claims",
            "missing_limitations",
            "issues",
        )
    ):
        agent_name = "report_verifier"
        enriched["agent_name"] = agent_name
    decision_kind = _decision_kind(enriched)
    kind = {
        "supervisor": "routing_readiness",
        "cleaner": "data_quality",
        "structurer": "temporal_representation",
        "modeler": "model_performance",
        "evaluator": "operational_acceptance",
        "report_writer": (
            "revision_effectiveness"
            if decision_kind == "report_revision"
            else "report_grounding"
        ),
        "report_verifier": "report_fidelity",
    }.get(agent_name)
    if kind is None:
        return enriched

    strategy = enriched.get("decision_strategy")
    strategy_data = strategy if isinstance(strategy, dict) else {}
    statement = strategy_data.get("hypothesis") or enriched.get("rationale")
    if not isinstance(statement, str) or not statement.strip():
        statement = "La accion propuesta producira el efecto operativo declarado."

    evidence_refs = _string_list(strategy_data.get("evidence_refs"))
    if not evidence_refs:
        evidence_refs = _string_list(enriched.get("evidence_refs"))
    if not evidence_refs:
        evidence_refs = {
            "routing_readiness": ["state:current_stage"],
            "data_quality": ["profile:dataset_summary"],
            "temporal_representation": ["artifact:clean_summary"],
            "model_performance": ["artifact:features"],
            "operational_acceptance": ["metrics:classification"],
            "report_grounding": ["evaluation:decision"],
            "revision_effectiveness": ["verification:structured_issues"],
            "report_fidelity": ["report:final_report"],
        }[kind]

    enriched["hypothesis"] = {
        "kind": kind,
        "statement": statement,
        "scope": f"Fixture contractual para {decision_kind}.",
        "evidence_cutoff": "Solo evidencia incluida en el payload simulado antes de decidir.",
        "expected_observation": (
            "La observacion posterior satisface el efecto esperado de la decision."
        ),
        "falsification_criterion": (
            "La observacion posterior contradice el efecto esperado o revela una infraccion del protocolo."
        ),
        "evidence_refs": evidence_refs,
        "risk_notes": [
            "Una ejecucion tecnica correcta no confirma por si sola la hipotesis."
        ],
        "assumptions": [],
    }
    return enriched


def _decision_kind(payload: dict[str, Any]) -> str:
    explicit = payload.get("decision_kind")
    if isinstance(explicit, str) and explicit:
        return explicit
    agent_name = payload.get("agent_name")
    if agent_name == "report_writer":
        return "report_revision" if "revision_round" in payload else "report_draft"
    if agent_name == "modeler":
        return "modeling_retry" if "attempt_number" in payload else "modeling"
    return {
        "supervisor": "routing",
        "cleaner": "cleaning",
        "structurer": "structuring",
        "evaluator": "evaluation",
        "report_verifier": "report_verification",
    }.get(str(agent_name), "unknown")


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]
