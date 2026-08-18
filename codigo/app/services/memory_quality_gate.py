"""Quality gate determinista para recuerdos RAG recuperados."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.dataset import DataProvenance, SupervisionProfile
from codigo.app.schemas.reasoning import (
    MemoryApplicability,
    ReasoningMemoryRecord,
    RetrievedMemoryContext,
    RetrievedMemoryItem,
)
from codigo.app.services.vector_memory import memory_provenance_status

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

BINARY_PROFILE_METRIC_KEYS = {
    "accuracy",
    "precision",
    "recall",
    "f1",
    "f1_score",
    "roc_auc",
    "pr_auc",
    "false_positive_rate",
}

MANUAL_EXCLUDE_TAGS = {
    "manual_exclude",
    "exclude_candidate",
    "benchmark_contaminated",
    "low_value_memory",
    "conflicting_memory",
}

KNOWN_SUPERVISION_PROFILES = {
    "binary_fault_classification",
    "run_to_failure_degradation",
    "unlabeled_diagnostic",
}

KNOWN_LABEL_SOURCES = {
    "official",
    "curated",
    "temporal_proxy",
    "synthetic",
    "none",
}

KNOWN_LABEL_GRANULARITIES = {
    "window",
    "file",
    "run",
    "event",
    "none",
    "proxy_temporal",
}


class MemoryQualityGatePolicy(StrictBaseModel):
    """Politica configurable para revisar recuerdos antes de usarlos."""

    min_pass_similarity: float = Field(default=0.2, ge=0.0, le=1.0)
    min_caution_similarity: float = Field(default=0.05, ge=0.0, le=1.0)
    require_dataset_match: bool = True
    supervision_profile: SupervisionProfile | None = None
    benchmark_mode: bool = False
    sample_rate_relative_tolerance: float = Field(default=0.05, ge=0.0, le=1.0)
    exclude_incompatible_sample_rate: bool = False

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
    data_provenance: DataProvenance = "unknown"
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
        data_provenance=context.query.data_provenance,
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

    (
        applicability_recommendation,
        applicability_reasons,
        applicability_risks,
    ) = _applicability_quality(record, context=context, policy=policy)
    recommendation = _max_recommendation(
        recommendation,
        applicability_recommendation,
    )
    reason_codes.extend(applicability_reasons)
    risk_notes.extend(applicability_risks)

    provenance_status = memory_provenance_status(record, context.query)
    reason_codes.append(f"provenance_{provenance_status}")
    if provenance_status == "unknown":
        recommendation = _max_recommendation(recommendation, "caution")
        risk_notes.append(
            "Record provenance is unknown; use only as explicit caution, not evidence."
        )
    elif provenance_status == "conflict":
        recommendation = "exclude_candidate"
        risk_notes.append(
            "Record provenance conflicts with the run or is dataset-specific shared memory."
        )

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
        risk_notes=list(dict.fromkeys(risk_notes)),
        pass_to_agent=recommendation != "exclude_candidate",
    )


def _applicability_quality(
    record: ReasoningMemoryRecord,
    *,
    context: RetrievedMemoryContext,
    policy: MemoryQualityGatePolicy,
) -> tuple[MemoryQualityAction, list[str], list[str]]:
    applicability = record.applicability
    query_context = context.query.decision_context
    query_profile = _known_context_text(
        query_context.get("supervision_profile"),
        KNOWN_SUPERVISION_PROFILES,
    )
    if query_profile is None and policy.supervision_profile is not None:
        query_profile = policy.supervision_profile

    if applicability is None:
        return _legacy_applicability_quality(
            record,
            supervision_profile=query_profile,  # type: ignore[arg-type]
            benchmark_mode=policy.benchmark_mode,
        )

    recommendation: MemoryQualityAction = "pass"
    reason_codes = ["typed_applicability"]
    risk_notes: list[str] = []

    recommendation = _compare_typed_dimension(
        dimension="supervision_profile",
        record_value=applicability.supervision_profile,
        query_value=query_profile,
        current=recommendation,
        reason_codes=reason_codes,
        risk_notes=risk_notes,
    )
    recommendation = _compare_typed_dimension(
        dimension="label_source",
        record_value=applicability.label_source,
        query_value=_known_context_text(
            query_context.get("label_source"),
            KNOWN_LABEL_SOURCES,
        ),
        current=recommendation,
        reason_codes=reason_codes,
        risk_notes=risk_notes,
    )
    recommendation = _compare_typed_dimension(
        dimension="label_granularity",
        record_value=applicability.label_granularity,
        query_value=_known_context_text(
            query_context.get("label_granularity"),
            KNOWN_LABEL_GRANULARITIES,
        ),
        current=recommendation,
        reason_codes=reason_codes,
        risk_notes=risk_notes,
    )

    recommendation = _compare_sample_rate(
        applicability,
        query_context.get("target_sample_rate_hz"),
        policy=policy,
        current=recommendation,
        reason_codes=reason_codes,
        risk_notes=risk_notes,
    )
    recommendation = _apply_transfer_scope(
        applicability,
        query_context,
        record=record,
        current=recommendation,
        reason_codes=reason_codes,
        risk_notes=risk_notes,
    )
    if policy.benchmark_mode:
        recommendation = _apply_benchmark_group_isolation(
            applicability,
            query_context,
            current=recommendation,
            reason_codes=reason_codes,
            risk_notes=risk_notes,
        )
    return recommendation, reason_codes, risk_notes


def _legacy_applicability_quality(
    record: ReasoningMemoryRecord,
    *,
    supervision_profile: SupervisionProfile | None,
    benchmark_mode: bool,
) -> tuple[MemoryQualityAction, list[str], list[str]]:
    reason_codes = ["legacy_applicability_fallback"]
    risk_notes: list[str] = []
    profile_reason = _profile_reason(
        record.tags,
        record.metrics,
        supervision_profile,
    )
    if profile_reason == "profile_conflict":
        recommendation: MemoryQualityAction = "exclude_candidate"
        reason_codes.append(profile_reason)
        risk_notes.append(
            "Legacy record tags suggest a different supervision profile."
        )
    elif profile_reason == "profile_compatible":
        recommendation = "pass"
        reason_codes.append(profile_reason)
    else:
        recommendation = "caution"
        reason_codes.append("profile_unknown")
        risk_notes.append(
            "Legacy record has no typed applicability and its profile is unknown."
        )
    if benchmark_mode:
        recommendation = _max_recommendation(recommendation, "caution")
        reason_codes.append("evaluation_group_unknown")
        risk_notes.append(
            "Legacy record cannot prove evaluation-group separation for a benchmark."
        )
    return recommendation, reason_codes, risk_notes


def _compare_typed_dimension(
    *,
    dimension: str,
    record_value: str | None,
    query_value: str | None,
    current: MemoryQualityAction,
    reason_codes: list[str],
    risk_notes: list[str],
) -> MemoryQualityAction:
    if record_value in {None, "unknown"} or query_value in {None, "unknown"}:
        reason_codes.append(f"{dimension}_unknown")
        risk_notes.append(
            f"Typed applicability cannot prove a compatible {dimension}."
        )
        return _max_recommendation(current, "caution")
    if record_value != query_value:
        reason_codes.append(f"{dimension}_conflict")
        risk_notes.append(
            f"Record {dimension}={record_value} conflicts with query "
            f"{dimension}={query_value}."
        )
        return "exclude_candidate"
    reason_codes.append(f"{dimension}_match")
    return current


def _compare_sample_rate(
    applicability: MemoryApplicability,
    query_value: object,
    *,
    policy: MemoryQualityGatePolicy,
    current: MemoryQualityAction,
    reason_codes: list[str],
    risk_notes: list[str],
) -> MemoryQualityAction:
    record_rate = applicability.target_sample_rate_hz
    query_rate = _positive_number(query_value)
    if record_rate is None or query_rate is None:
        reason_codes.append("sample_rate_unknown")
        risk_notes.append(
            "Target sample rate is missing from the record or query applicability."
        )
        return _max_recommendation(current, "caution")
    relative_delta = abs(float(record_rate) - query_rate) / query_rate
    if relative_delta <= policy.sample_rate_relative_tolerance:
        reason_codes.append("sample_rate_compatible")
        return current
    risk_notes.append(
        "Target sample rates are incompatible: "
        f"record={record_rate} Hz, query={query_rate:g} Hz, "
        f"relative_delta={relative_delta:.3f}."
    )
    if policy.exclude_incompatible_sample_rate:
        reason_codes.append("sample_rate_incompatible_excluded")
        return "exclude_candidate"
    reason_codes.append("sample_rate_incompatible_caution")
    return _max_recommendation(current, "caution")


def _apply_transfer_scope(
    applicability: MemoryApplicability,
    query_context: dict[str, str | int | float | bool | None],
    *,
    record: ReasoningMemoryRecord,
    current: MemoryQualityAction,
    reason_codes: list[str],
    risk_notes: list[str],
) -> MemoryQualityAction:
    scope = applicability.transfer_scope
    reason_codes.append(f"transfer_scope_{scope}")
    if scope == "unknown":
        risk_notes.append("Memory transfer scope is unknown.")
        return _max_recommendation(current, "caution")
    if scope == "same_trajectory":
        record_group = _known_group_id(applicability.trajectory_group_id)
        query_group = _known_group_id(query_context.get("trajectory_group_id"))
        if record_group is None or query_group is None:
            reason_codes.append("trajectory_group_unknown")
            risk_notes.append(
                "Same-trajectory memory lacks a trajectory group on one side."
            )
            return _max_recommendation(current, "caution")
        if record_group != query_group:
            reason_codes.append("trajectory_scope_mismatch")
            risk_notes.append(
                "Record is restricted to its source trajectory and cannot transfer."
            )
            return "exclude_candidate"
        reason_codes.append("trajectory_scope_match")
    elif scope == "shared_methodology" and record.target_agent != "shared_methodology":
        reason_codes.append("shared_scope_non_methodology_target")
        risk_notes.append(
            "A non-methodology collection declares shared-methodology transfer scope."
        )
        return _max_recommendation(current, "caution")
    return current


def _apply_benchmark_group_isolation(
    applicability: MemoryApplicability,
    query_context: dict[str, str | int | float | bool | None],
    *,
    current: MemoryQualityAction,
    reason_codes: list[str],
    risk_notes: list[str],
) -> MemoryQualityAction:
    recommendation = current
    record_evaluation_group = _known_group_id(applicability.evaluation_group_id)
    query_evaluation_group = _known_group_id(
        query_context.get("evaluation_group_id")
    )
    if record_evaluation_group is None or query_evaluation_group is None:
        reason_codes.append("evaluation_group_unknown")
        risk_notes.append(
            "Benchmark group separation cannot be proven for this memory."
        )
        recommendation = _max_recommendation(recommendation, "caution")
    elif record_evaluation_group == query_evaluation_group:
        reason_codes.append("evaluation_group_leakage")
        risk_notes.append(
            "Record and query belong to the same evaluation group in benchmark mode."
        )
        recommendation = "exclude_candidate"
    else:
        reason_codes.append("evaluation_group_separated")

    record_trajectory_group = _known_group_id(applicability.trajectory_group_id)
    query_trajectory_group = _known_group_id(
        query_context.get("trajectory_group_id")
    )
    if record_trajectory_group is None or query_trajectory_group is None:
        reason_codes.append("trajectory_group_unknown")
        risk_notes.append(
            "Benchmark trajectory separation cannot be proven for this memory."
        )
        recommendation = _max_recommendation(recommendation, "caution")
    elif record_trajectory_group == query_trajectory_group:
        reason_codes.append("trajectory_group_leakage")
        risk_notes.append(
            "Record and query share a trajectory group in benchmark mode."
        )
        recommendation = "exclude_candidate"
    else:
        reason_codes.append("trajectory_group_separated")
    return recommendation


def _known_context_text(value: object, allowed: set[str]) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized if normalized in allowed else None


def _known_group_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or normalized.lower() == "unknown":
        return None
    return normalized


def _positive_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    return numeric if numeric > 0.0 else None


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
    metrics: dict[str, float | None],
    supervision_profile: SupervisionProfile | None,
) -> str | None:
    if supervision_profile is None:
        return None
    normalized = {tag.strip().lower() for tag in tags}
    metric_keys = {key.strip().lower() for key in metrics}
    has_binary_evidence = bool(
        normalized & BINARY_PROFILE_TAGS
        or metric_keys & BINARY_PROFILE_METRIC_KEYS
    )
    has_run_to_failure_evidence = bool(normalized & RUN_TO_FAILURE_PROFILE_TAGS)
    if not normalized:
        return "profile_conflict" if has_binary_evidence else "profile_unknown"
    if supervision_profile == "run_to_failure_degradation":
        if has_binary_evidence and not has_run_to_failure_evidence:
            return "profile_conflict"
        if has_run_to_failure_evidence:
            return "profile_compatible"
        return "profile_unknown"
    if supervision_profile == "binary_fault_classification":
        if has_run_to_failure_evidence and not has_binary_evidence:
            return "profile_conflict"
        if has_binary_evidence:
            return "profile_compatible"
        return "profile_unknown"
    return "profile_unknown"
