"""Quality gate determinista para recuerdos RAG recuperados."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.dataset import SupervisionProfile
from codigo.app.schemas.reasoning import (
    RetrievedMemoryContext,
    RetrievedMemoryItem,
)

MemoryQualityAction = Literal["pass", "caution", "exclude_candidate"]


RUN_TO_FAILURE_PROFILE_TAGS = {
    "run_to_failure",
    "run_to_failure_degradation",
    "degradation",
    "temporal",
    "temporal_proxy",
    "lead_time",
    "rul",
    "sustained_alert",
    "sustained_alert_required",
    "isolated_spike_not_failure",
    "mean_lead_time_to_failure",
    "mean_false_alarm_rate_nominal",
}

BINARY_PROFILE_TAGS = {
    "binary",
    "binary_anomaly",
    "binary_fault_classification",
    "fault_classification",
    "cwru",
    "cwru_bearing",
}

MANUAL_EXCLUDE_TAGS = {
    "manual_exclude",
    "exclude_candidate",
    "benchmark_contaminated",
    "low_value_memory",
    "conflicting_memory",
}


class MemoryQualityGatePolicy(StrictBaseModel):
    """Politica configurable para revisar recuerdos antes de usarlos."""

    min_pass_similarity: float = Field(default=0.2, ge=0.0, le=1.0)
    min_caution_similarity: float = Field(default=0.05, ge=0.0, le=1.0)
    require_dataset_match: bool = True
    supervision_profile: SupervisionProfile | None = None
    benchmark_mode: bool = False

    @model_validator(mode="after")
    def validate_similarity_order(self) -> "MemoryQualityGatePolicy":
        if self.min_caution_similarity > self.min_pass_similarity:
            raise ValueError("min_caution_similarity cannot exceed min_pass_similarity")
        return self


class MemoryQualityGateItem(StrictBaseModel):
    """Resultado del quality gate para un recuerdo recuperado."""

    memory_record_id: str = Field(min_length=1)
    rank: int = Field(ge=1)
    similarity: float = Field(ge=0.0, le=1.0)
    recommendation: MemoryQualityAction
    reason_codes: list[str] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)
    pass_to_agent: bool


class MemoryQualityGateReport(StrictBaseModel):
    """Informe compacto de calidad para un contexto RAG recuperado."""

    context_id: str = Field(min_length=1)
    query_id: str = Field(min_length=1)
    target_agent: str = Field(min_length=1)
    dataset: str | None = None
    supervision_profile: SupervisionProfile | None = None
    total_items: int = Field(ge=0)
    pass_count: int = Field(ge=0)
    caution_count: int = Field(ge=0)
    exclude_candidate_count: int = Field(ge=0)
    items: list[MemoryQualityGateItem] = Field(default_factory=list)


def evaluate_memory_quality(
    context: RetrievedMemoryContext,
    *,
    policy: MemoryQualityGatePolicy | None = None,
    supervision_profile: SupervisionProfile | None = None,
) -> MemoryQualityGateReport:
    """Evalua un contexto recuperado sin consolidar ni reescribir recuerdos."""

    effective_policy = policy or MemoryQualityGatePolicy(
        supervision_profile=supervision_profile
    )
    if supervision_profile is not None and effective_policy.supervision_profile is None:
        effective_policy = effective_policy.model_copy(
            update={"supervision_profile": supervision_profile}
        )
    items = [
        _quality_item(item, context=context, policy=effective_policy)
        for item in context.items
    ]
    return MemoryQualityGateReport(
        context_id=context.context_id,
        query_id=context.query.query_id,
        target_agent=context.query.target_agent,
        dataset=context.query.dataset,
        supervision_profile=effective_policy.supervision_profile,
        total_items=len(items),
        pass_count=sum(item.recommendation == "pass" for item in items),
        caution_count=sum(item.recommendation == "caution" for item in items),
        exclude_candidate_count=sum(
            item.recommendation == "exclude_candidate" for item in items
        ),
        items=items,
    )


def filter_memory_context_by_quality(
    context: RetrievedMemoryContext,
    report: MemoryQualityGateReport | None = None,
    *,
    keep_caution: bool = True,
) -> RetrievedMemoryContext:
    """Devuelve un contexto filtrado, conservando cautelas salvo que se pida."""

    quality_report = report or evaluate_memory_quality(context)
    recommendations = {
        item.memory_record_id: item.recommendation
        for item in quality_report.items
    }
    kept_items = [
        item
        for item in context.items
        if recommendations.get(item.record.memory_record_id) == "pass"
        or (
            keep_caution
            and recommendations.get(item.record.memory_record_id) == "caution"
        )
    ]
    ranked = [
        item.model_copy(update={"rank": index})
        for index, item in enumerate(kept_items, start=1)
    ]
    return context.model_copy(update={"items": ranked})


def _quality_item(
    item: RetrievedMemoryItem,
    *,
    context: RetrievedMemoryContext,
    policy: MemoryQualityGatePolicy,
) -> MemoryQualityGateItem:
    record = item.record
    reason_codes: list[str] = []
    risk_notes: list[str] = []
    recommendation: MemoryQualityAction = "pass"

    if item.similarity < policy.min_caution_similarity:
        recommendation = "exclude_candidate"
        reason_codes.append("very_low_similarity")
        risk_notes.append("Similarity is below the minimum caution threshold.")
    elif item.similarity < policy.min_pass_similarity:
        recommendation = "caution"
        reason_codes.append("low_similarity")

    if record.target_agent == "shared_methodology":
        reason_codes.append("shared_methodology")
    elif record.target_agent == context.query.target_agent:
        reason_codes.append("target_agent_match")
    else:
        recommendation = "exclude_candidate"
        reason_codes.append("target_agent_mismatch")

    if _has_manual_exclude_tag(record.tags):
        recommendation = "exclude_candidate"
        reason_codes.append("manual_or_benchmark_exclusion_tag")
        risk_notes.append("Record carries a manual or benchmark exclusion tag.")

    if (
        policy.require_dataset_match
        and record.target_agent != "shared_methodology"
        and record.dataset is not None
        and context.query.dataset is not None
        and record.dataset != context.query.dataset
    ):
        recommendation = "exclude_candidate"
        reason_codes.append("dataset_mismatch")
        risk_notes.append("Record dataset differs from the query dataset.")
    elif record.dataset == context.query.dataset and record.dataset is not None:
        reason_codes.append("dataset_match")
    elif record.dataset is None:
        reason_codes.append("dataset_unspecified")

    profile_reason = _profile_reason(record.tags, policy.supervision_profile)
    if profile_reason == "profile_conflict":
        recommendation = "exclude_candidate"
        reason_codes.append(profile_reason)
        risk_notes.append("Record tags suggest a different supervision profile.")
    elif profile_reason is not None:
        reason_codes.append(profile_reason)

    if record.memory_role in {"warning", "negative_example"}:
        recommendation = _max_recommendation(recommendation, "caution")
        reason_codes.append(f"{record.memory_role}_role")
        risk_notes.append("Record is intended as warning, not as positive evidence.")
    elif record.memory_role == "boundary_case":
        recommendation = _max_recommendation(recommendation, "caution")
        reason_codes.append("boundary_case_role")
        risk_notes.append("Boundary cases require explicit risk mitigation.")

    if record.source_type == "memory_usage_audit":
        recommendation = _max_recommendation(recommendation, "caution")
        reason_codes.append("memory_usage_audit_source")

    if record.human_verdict in {"partially_correct", "needs_more_evidence"}:
        recommendation = _max_recommendation(recommendation, "caution")
        reason_codes.append(f"human_verdict_{record.human_verdict}")
    elif record.human_verdict == "incorrect":
        recommendation = "exclude_candidate"
        reason_codes.append("human_verdict_incorrect")
    elif record.human_verdict == "unsafe":
        recommendation = "exclude_candidate"
        reason_codes.append("human_verdict_unsafe")

    return MemoryQualityGateItem(
        memory_record_id=record.memory_record_id,
        rank=item.rank,
        similarity=item.similarity,
        recommendation=recommendation,
        reason_codes=sorted(set(reason_codes)),
        risk_notes=risk_notes,
        pass_to_agent=recommendation != "exclude_candidate",
    )


def _max_recommendation(
    current: MemoryQualityAction,
    candidate: MemoryQualityAction,
) -> MemoryQualityAction:
    order = {"pass": 0, "caution": 1, "exclude_candidate": 2}
    return candidate if order[candidate] > order[current] else current


def _has_manual_exclude_tag(tags: list[str]) -> bool:
    normalized = {tag.strip().lower() for tag in tags}
    return bool(normalized & MANUAL_EXCLUDE_TAGS)


def _profile_reason(
    tags: list[str],
    supervision_profile: SupervisionProfile | None,
) -> str | None:
    if supervision_profile is None:
        return None
    normalized = {tag.strip().lower() for tag in tags}
    if not normalized:
        return "profile_unknown"
    if supervision_profile == "run_to_failure_degradation":
        if normalized & BINARY_PROFILE_TAGS and not normalized & RUN_TO_FAILURE_PROFILE_TAGS:
            return "profile_conflict"
        if normalized & RUN_TO_FAILURE_PROFILE_TAGS:
            return "profile_compatible"
        return "profile_unknown"
    if supervision_profile == "binary_fault_classification":
        if normalized & RUN_TO_FAILURE_PROFILE_TAGS and not normalized & BINARY_PROFILE_TAGS:
            return "profile_conflict"
        if normalized & BINARY_PROFILE_TAGS:
            return "profile_compatible"
        return "profile_unknown"
    return "profile_unknown"
