"""Sintesis determinista y consultiva de una revision de monitorizacion.

El servicio no interpreta texto libre, no inventa parametros de politica y no
aplica cambios. Se limita a proyectar el catalogo cerrado ya elegido por los
siete roles y a conservar sus bindings causales.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

from codigo.app.schemas.monitoring_replay import (
    MONITORING_POLICY_PROPOSAL_EFFECTS,
    MONITORING_REVIEW_ROLES,
    CausalEvidenceCatalog,
    CausalEvidenceCatalogEntry,
    MonitoringPolicyProposal,
    MonitoringReviewDecision,
    MonitoringReviewRequest,
    PolicyProposalContribution,
)


def build_monitoring_policy_proposal(
    *,
    request: MonitoringReviewRequest,
    decisions: Sequence[MonitoringReviewDecision],
    evidence_catalog: CausalEvidenceCatalog,
) -> MonitoringPolicyProposal:
    """Construye una propuesta no aplicable a partir de siete decisiones selladas."""

    ordered_decisions = tuple(decisions)
    _validate_source_bindings(
        request=request,
        decisions=ordered_decisions,
        evidence_catalog=evidence_catalog,
    )
    entries_by_support_ref = {
        entry.support_ref: entry for entry in evidence_catalog.entries
    }
    contributions = tuple(
        _contribution_for_decision(
            decision,
            entries_by_support_ref=entries_by_support_ref,
        )
        for decision in ordered_decisions
    )

    invalid_review = any(
        item.generation_origin != "llm" for item in contributions
    )
    actions = {item.recommended_action for item in contributions}
    if invalid_review:
        agreement_status = "invalid_review"
        aggregate_action = None
        aggregate_kind = None
    elif len(actions) == 1:
        agreement_status = "unanimous"
        aggregate_action = next(iter(actions))
        aggregate_kind = MONITORING_POLICY_PROPOSAL_EFFECTS[
            aggregate_action
        ][0]
    else:
        agreement_status = "disagreement"
        aggregate_action = None
        aggregate_kind = None

    payload: dict[str, Any] = {
        "proposal_id": _proposal_id(
            request,
            ordered_decisions,
            evidence_catalog,
        ),
        "request_id": request.request_id,
        "request_sha256": request.request_sha256,
        "child_run_id": request.child_run_id,
        "session_id": request.session_id,
        "trigger_id": request.trigger_id,
        "trigger_event_id": request.trigger_event_id,
        "origin_tick_id": request.origin_tick_id,
        "cutoff_snapshot_id": request.cutoff_snapshot_id,
        "cutoff_cursor": request.cutoff_cursor,
        "cutoff_source_time": request.cutoff_source_time,
        "active_policy_refs": request.active_policy_refs,
        "causal_view_sha256": request.causal_view_sha256,
        "evidence_catalog_sha256": evidence_catalog.catalog_sha256,
        "proposal_origin": "deterministic_server",
        "status": "advisory_not_applied",
        "application_status": "not_applied",
        "policy_validation_eligible": False,
        "agreement_status": agreement_status,
        "aggregate_action": aggregate_action,
        "aggregate_kind": aggregate_kind,
        "contributions": contributions,
        "human_review_recommended": any(
            item.requires_human_review for item in contributions
        ),
        # Tiempo derivado de decisiones ya selladas; no introduce un nuevo reloj
        # no reproducible en la identidad de la propuesta.
        "created_at": max(item.created_at for item in ordered_decisions),
    }
    payload["proposal_sha256"] = MonitoringPolicyProposal.canonical_sha256(
        payload
    )
    return MonitoringPolicyProposal.model_validate(payload)


def validate_monitoring_policy_proposal(
    proposal: MonitoringPolicyProposal,
    *,
    request: MonitoringReviewRequest,
    decisions: Sequence[MonitoringReviewDecision],
    evidence_catalog: CausalEvidenceCatalog,
) -> None:
    """Exige que una propuesta sea la proyeccion exacta de sus fuentes."""

    if (
        MonitoringPolicyProposal.canonical_sha256(proposal)
        != proposal.proposal_sha256
    ):
        raise ValueError("monitoring policy proposal hash mismatch")
    expected = build_monitoring_policy_proposal(
        request=request,
        decisions=decisions,
        evidence_catalog=evidence_catalog,
    )
    if proposal != expected:
        raise ValueError(
            "monitoring policy proposal differs from its deterministic projection"
        )


def _contribution_for_decision(
    decision: MonitoringReviewDecision,
    *,
    entries_by_support_ref: dict[str, CausalEvidenceCatalogEntry],
) -> PolicyProposalContribution:
    effect = MONITORING_POLICY_PROPOSAL_EFFECTS[decision.recommended_action]
    handles = tuple(
        entries_by_support_ref[reference].handle
        for reference in decision.evidence_refs
    )
    return PolicyProposalContribution(
        agent_name=decision.agent_name,
        decision_id=decision.decision_id,
        decision_sha256=decision.decision_sha256,
        generation_origin=decision.generation_trace.origin,
        recommended_action=decision.recommended_action,
        proposal_kind=effect[0],
        advisory_subject=effect[1],
        current_state=effect[2],
        proposed_state=effect[3],
        action_rationale=decision.action_rationale,
        risk_notes=tuple(decision.hypothesis.risk_notes),
        evidence_handles=handles,
        evidence_support_refs=tuple(decision.evidence_refs),
        requires_human_review=decision.requires_human_review,
    )


def _validate_source_bindings(
    *,
    request: MonitoringReviewRequest,
    decisions: tuple[MonitoringReviewDecision, ...],
    evidence_catalog: CausalEvidenceCatalog,
) -> None:
    if MonitoringReviewRequest.canonical_sha256(request) != request.request_sha256:
        raise ValueError("monitoring review request hash mismatch")
    if (
        CausalEvidenceCatalog.canonical_sha256(evidence_catalog)
        != evidence_catalog.catalog_sha256
    ):
        raise ValueError("causal evidence catalog hash mismatch")
    if evidence_catalog.causal_view_sha256 != request.causal_view_sha256:
        raise ValueError("evidence catalog does not bind the review causal view")
    if tuple(item.agent_name for item in decisions) != MONITORING_REVIEW_ROLES:
        raise ValueError(
            "policy proposal requires the seven canonical decisions in order"
        )

    allowed_support_refs = {
        entry.support_ref for entry in evidence_catalog.entries
    }
    for decision in decisions:
        if (
            MonitoringReviewDecision.canonical_sha256(decision)
            != decision.decision_sha256
        ):
            raise ValueError("monitoring review decision hash mismatch")
        if (
            decision.child_run_id != request.child_run_id
            or decision.trigger_event_id != request.trigger_event_id
            or decision.cutoff_snapshot_id != request.cutoff_snapshot_id
            or decision.cutoff_cursor != request.cutoff_cursor
            or decision.cutoff_source_time != request.cutoff_source_time
            or decision.causal_view_sha256 != request.causal_view_sha256
        ):
            raise ValueError(
                "monitoring review decision does not bind the proposal request"
            )
        decision_refs = tuple(decision.evidence_refs)
        if (
            not decision_refs
            or not set(decision_refs).issubset(allowed_support_refs)
        ):
            raise ValueError(
                "monitoring review decision references evidence outside the catalog"
            )
        if tuple(decision.hypothesis.evidence_refs) != decision_refs:
            raise ValueError(
                "monitoring review hypothesis evidence must match decision evidence"
            )


def _proposal_id(
    request: MonitoringReviewRequest,
    decisions: tuple[MonitoringReviewDecision, ...],
    evidence_catalog: CausalEvidenceCatalog,
) -> str:
    identity = "\x00".join(
        (
            request.request_sha256,
            evidence_catalog.catalog_sha256,
            *(item.decision_sha256 for item in decisions),
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return f"monitoring-policy-proposal:{digest}"


__all__ = [
    "build_monitoring_policy_proposal",
    "validate_monitoring_policy_proposal",
]
