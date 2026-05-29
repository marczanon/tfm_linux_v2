"""Puerta reutilizable de Human-in-the-loop para planificacion y ejecucion."""

from __future__ import annotations

from dataclasses import dataclass

from codigo.app.schemas.pipeline_run import DatasetPipelinePlan
from codigo.app.schemas.reasoning import HumanReviewSettings
from codigo.app.schemas.state import HumanApproval


@dataclass(frozen=True)
class HumanReviewGate:
    """Resultado compacto de aplicar la politica de revision humana."""

    approval: HumanApproval | None
    reasons: list[str]
    execution_allowed: bool
    blocking_reason: str | None = None


def human_review_gate_for_plan(
    plan: DatasetPipelinePlan,
    settings: HumanReviewSettings | None = None,
    approval: HumanApproval | None = None,
) -> HumanReviewGate:
    """Evalua si una run requiere revision humana antes de ejecutarse."""

    cfg = settings or HumanReviewSettings()
    if cfg.mode == "off":
        return HumanReviewGate(
            approval=approval,
            reasons=[],
            execution_allowed=True,
        )

    reasons = _human_review_reasons(plan, cfg)
    if not reasons:
        return HumanReviewGate(
            approval=approval,
            reasons=[],
            execution_allowed=True,
        )

    record = _approval_record(cfg, approval, required=cfg.mode == "required", reasons=reasons)
    if cfg.mode == "passive":
        return HumanReviewGate(
            approval=record,
            reasons=reasons,
            execution_allowed=True,
        )
    if record.approved is True:
        return HumanReviewGate(
            approval=record,
            reasons=reasons,
            execution_allowed=True,
        )
    return HumanReviewGate(
        approval=record,
        reasons=reasons,
        execution_allowed=False,
        blocking_reason="human review approval is required before execution",
    )


def _human_review_reasons(
    plan: DatasetPipelinePlan,
    settings: HumanReviewSettings,
) -> list[str]:
    reasons: list[str] = []
    configured_points = set(settings.required_decision_points)
    for stage in plan.effective_stages:
        if stage in configured_points:
            reasons.append(f"{stage}: configured human review decision point")
    for capability in plan.policy.capabilities:
        if capability.stage not in plan.effective_stages:
            continue
        if capability.requires_human_review:
            reason = capability.reason or "dataset policy requires human review"
            reasons.append(f"{capability.stage}: {reason}")
    return _deduplicate(reasons)


def _approval_record(
    settings: HumanReviewSettings,
    approval: HumanApproval | None,
    *,
    required: bool,
    reasons: list[str],
) -> HumanApproval:
    reason = "; ".join(reasons)
    if approval is None:
        return HumanApproval(
            required=required,
            approved=None,
            reviewer=settings.reviewer,
            reason=reason,
        )
    return approval.model_copy(
        update={
            "required": required,
            "reason": approval.reason or reason,
        }
    )


def _deduplicate(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
