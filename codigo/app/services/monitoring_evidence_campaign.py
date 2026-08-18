"""Campaña auditable de replay NASA con ventana agentiva de unas dos jornadas.

No implementa otro replay ni otro grafo. Prerregistra y resume una única
ejecución del ciclo P3 existente, separando el cierre operativo del veredicto
agentivo. Las decisiones completas siguen viviendo en sus runs hijas.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import uuid
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import AwareDatetime, ConfigDict, Field, model_validator

from codigo.app.schemas.agent_decisions import AgentName
from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.monitoring_replay import (
    MONITORING_REVIEW_ROLES,
    MonitoringTriggerReasonCode,
    MonitoringTriggerType,
)
from codigo.app.services.agent_reliability import (
    AgentReliabilityAttempt,
    AgentReliabilityModelConfig,
)
from codigo.app.services.monitoring_replay import DEFAULT_SCENARIO_ID
from codigo.app.services.monitoring_review_reliability import (
    EXPECTED_NASA_P3_PRIMARY_CONTEXTS,
    MonitoringReviewReliabilityExpectedContext,
    MonitoringReviewReliabilityObservation,
    default_monitoring_review_reliability_plan,
)


DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_OUTPUT_DIR = Path(
    "codigo/reports/validation/monitoring_evidence_campaign"
)
DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_ID = "nasa-p3-agentic-window-56h-v1"
CAMPAIGN_SOURCE_TIMES: dict[int, str] = {
    353: "2004-02-16T22:32:39",
    498: "2004-02-17T22:42:39",
    499: "2004-02-17T22:52:39",
    688: "2004-02-19T06:22:39",
}
_PROJECT_ROOT = Path(__file__).resolve().parents[3]

CampaignStatus = Literal["planned", "running", "completed", "interrupted", "failed"]
CampaignPhase = Literal["planned", "pre_roll", "agentic_window", "completed"]
CampaignVerdict = Literal["pending", "passed", "blocked"]
CampaignReviewLifecycle = Literal[
    "pending", "running", "resolved", "failed", "interrupted"
]


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()


class _HashedCampaignModel(StrictBaseModel):
    model_config = ConfigDict(frozen=True)
    _hash_field: ClassVar[str]

    @classmethod
    def canonical_sha256(cls, value: Any) -> str:
        if isinstance(value, cls):
            instance = value
        else:
            payload = dict(value)
            payload.pop(cls._hash_field, None)
            instance = cls.model_construct(**payload)
        return _json_sha256(
            instance.model_dump(
                mode="json",
                exclude={cls._hash_field},
                warnings=False,
            )
        )

    @model_validator(mode="after")
    def verify_hash(self):
        if getattr(self, self._hash_field) != type(self).canonical_sha256(self):
            raise ValueError(f"{self._hash_field} does not match canonical payload")
        return self


class MonitoringEvidenceCampaignPlan(_HashedCampaignModel):
    """Plan congelado antes de crear sesión o llamar a Qwen."""

    _hash_field = "plan_sha256"
    schema_version: Literal["monitoring_evidence_campaign_plan_v1"] = (
        "monitoring_evidence_campaign_plan_v1"
    )
    campaign_id: str = Field(min_length=1, max_length=140)
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    session_id: str = Field(min_length=1, max_length=160)
    dataset_id: Literal["nasa_ims_bearing"] = "nasa_ims_bearing"
    scenario_id: Literal["NASA-RTF-HYB-01"] = DEFAULT_SCENARIO_ID
    activation_policy_kind: Literal["P3"] = "P3"
    experiment_mode: Literal["frozen_benchmark"] = "frozen_benchmark"
    execution_mode: Literal["historical_replay_accelerated"] = (
        "historical_replay_accelerated"
    )
    memory_mode: Literal["off"] = "off"
    policy_application_status: Literal["not_applied"] = "not_applied"
    source_timezone_status: Literal["not_declared"] = "not_declared"
    expected_total_monitoring_ticks: Literal[689] = 689
    pre_roll_start_cursor: Literal[0] = 0
    pre_roll_end_cursor: Literal[352] = 352
    pre_roll_tick_count: Literal[353] = 353
    agentic_window_start_cursor: Literal[353] = 353
    agentic_window_end_cursor: Literal[688] = 688
    agentic_window_tick_count: Literal[336] = 336
    agentic_window_source_start: Literal["2004-02-16T22:32:39"] = (
        "2004-02-16T22:32:39"
    )
    agentic_window_source_end: Literal["2004-02-19T06:22:39"] = (
        "2004-02-19T06:22:39"
    )
    agentic_window_source_duration_seconds: Literal[201000] = 201000
    source_cadence_seconds: Literal[600] = 600
    speed_multiplier: float = Field(default=60.0, gt=0.0)
    step_interval_seconds: float = Field(default=10.0, gt=0.0)
    heartbeat_interval_seconds: float = Field(default=5.0, gt=0.0)
    expected_contexts: tuple[MonitoringReviewReliabilityExpectedContext, ...] = (
        EXPECTED_NASA_P3_PRIMARY_CONTEXTS
    )
    expected_roles: tuple[AgentName, ...] = MONITORING_REVIEW_ROLES
    expected_trigger_count: Literal[4] = 4
    expected_total_trigger_event_count: Literal[14] = 14
    expected_suppressed_trigger_count: Literal[10] = 10
    expected_variable_run_slots_reserved: Literal[3] = 3
    expected_child_run_count: Literal[4] = 4
    expected_decision_count: Literal[28] = 28
    expected_policy_proposal_count: Literal[4] = 4
    minimum_first_pass_rate: float = Field(default=0.90, ge=0.0, le=1.0)
    model_digest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    llm_config: AgentReliabilityModelConfig
    contract_fingerprints: dict[str, str]
    source_sha256s: dict[str, str]

    @model_validator(mode="after")
    def validate_closed_campaign(self):
        if self.expected_contexts != EXPECTED_NASA_P3_PRIMARY_CONTEXTS:
            raise ValueError("campaign contexts must match the frozen P3 pack")
        if self.expected_roles != MONITORING_REVIEW_ROLES:
            raise ValueError("campaign roles must use canonical order")
        reliability = default_monitoring_review_reliability_plan(
            plan_id=self.campaign_id
        )
        if (
            self.llm_config != reliability.llm_config
            or self.model_digest_sha256 != reliability.model_digest_sha256
            or self.contract_fingerprints != reliability.contract_fingerprints
        ):
            raise ValueError("campaign must use the frozen Qwen contract pack")
        expected_interval = self.source_cadence_seconds / self.speed_multiplier
        if abs(self.step_interval_seconds - expected_interval) > 1e-9:
            raise ValueError("step interval must be derived from source cadence and speed")
        if self.heartbeat_interval_seconds > self.step_interval_seconds:
            raise ValueError("heartbeat interval cannot exceed step interval")
        if not self.source_sha256s or any(
            not reference or not re.fullmatch(r"[0-9a-f]{64}", digest)
            for reference, digest in self.source_sha256s.items()
        ):
            raise ValueError("campaign source hashes must be complete")
        return self


class MonitoringEvidenceCampaignPreregistration(_HashedCampaignModel):
    _hash_field = "registration_sha256"
    schema_version: Literal["monitoring_evidence_campaign_preregistration_v1"] = (
        "monitoring_evidence_campaign_preregistration_v1"
    )
    campaign_id: str = Field(min_length=1, max_length=140)
    plan_ref: str = Field(min_length=1)
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registered_at: AwareDatetime


class MonitoringEvidenceCampaignReview(StrictBaseModel):
    context_id: str = Field(min_length=1)
    ordinal: int = Field(ge=1, le=4)
    trigger_type: MonitoringTriggerType
    reason_code: MonitoringTriggerReasonCode
    condition_start_cursor: int = Field(ge=0)
    cutoff_cursor: int = Field(ge=0)
    source_time: str = Field(min_length=1)
    lifecycle: CampaignReviewLifecycle = "pending"
    trigger_id: str | None = None
    trigger_event_id: str | None = None
    child_run_id: str | None = None
    job_status: str | None = None
    decision_count: int = Field(default=0, ge=0, le=7)
    llm_origin_count: int = Field(default=0, ge=0, le=7)
    repaired_count: int = Field(default=0, ge=0, le=7)
    fallback_count: int = Field(default=0, ge=0, le=7)
    proposal_id: str | None = None
    proposal_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    proposal_status: str | None = None
    proposal_application_status: str | None = None
    error: str | None = None


class MonitoringEvidenceCampaignState(_HashedCampaignModel):
    _hash_field = "state_sha256"
    schema_version: Literal["monitoring_evidence_campaign_state_v1"] = (
        "monitoring_evidence_campaign_state_v1"
    )
    campaign_id: str
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    session_id: str
    state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    status: CampaignStatus
    phase: CampaignPhase
    evidence_verdict: CampaignVerdict = "pending"
    operational_verdict: CampaignVerdict = "pending"
    agentic_verdict: CampaignVerdict = "pending"
    current_revision: int = Field(default=0, ge=0, le=689)
    execution_cursor: int | None = Field(default=None, ge=0, le=688)
    progress_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
    reviews: tuple[MonitoringEvidenceCampaignReview, ...]
    observed_trigger_count: int = Field(default=0, ge=0)
    terminal_child_run_count: int = Field(default=0, ge=0)
    resolved_child_run_count: int = Field(default=0, ge=0)
    observed_decision_count: int = Field(default=0, ge=0)
    physical_attempt_count: int = Field(default=0, ge=0)
    llm_origin_decision_count: int = Field(default=0, ge=0)
    repaired_decision_count: int = Field(default=0, ge=0)
    fallback_count: int = Field(default=0, ge=0)
    policy_proposal_count: int = Field(default=0, ge=0)
    blockers: tuple[str, ...] = ()
    started_at: AwareDatetime | None = None
    updated_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    runtime_elapsed_seconds: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def validate_review_order(self):
        if tuple(item.context_id for item in self.reviews) != tuple(
            item.context_id for item in EXPECTED_NASA_P3_PRIMARY_CONTEXTS
        ):
            raise ValueError("campaign reviews must use frozen context order")
        return self


class MonitoringEvidenceCampaignResult(_HashedCampaignModel):
    _hash_field = "result_sha256"
    schema_version: Literal["monitoring_evidence_campaign_result_v1"] = (
        "monitoring_evidence_campaign_result_v1"
    )
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preregistration_ref: str = Field(min_length=1)
    registration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registered_at: AwareDatetime
    plan: MonitoringEvidenceCampaignPlan
    final_state: MonitoringEvidenceCampaignState
    observations: tuple[MonitoringReviewReliabilityObservation, ...]
    physical_attempts: tuple[AgentReliabilityAttempt, ...]
    operational_verdict: Literal["passed", "blocked"]
    agentic_verdict: Literal["passed", "blocked"]
    evidence_verdict: Literal["passed", "blocked"]
    blockers: tuple[str, ...]
    first_pass_count: int = Field(ge=0)
    repaired_count: int = Field(ge=0)
    fallback_count: int = Field(ge=0)
    non_agentic_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    structural_check_pass_count: int = Field(ge=0)
    total_trigger_event_count: int = Field(ge=0)
    suppressed_trigger_count: int = Field(ge=0)
    variable_run_slots_reserved: int = Field(ge=0)
    steps_applied_this_invocation: int = Field(ge=0)
    pacing_wait_count: int = Field(ge=0)
    pacing_elapsed_seconds: float = Field(ge=0.0)
    heartbeat_count: int = Field(ge=0)
    started_at: AwareDatetime
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_result_bindings(self):
        if (
            self.final_state.campaign_id != self.plan.campaign_id
            or self.final_state.plan_sha256 != self.plan.plan_sha256
            or Path(self.preregistration_ref).name != "preregistration.json"
        ):
            raise ValueError("campaign result identity binding is invalid")
        if self.registered_at > self.started_at or self.started_at > self.completed_at:
            raise ValueError("campaign result timestamps are not causal")
        attempt_indices = tuple(item.attempt_index for item in self.physical_attempts)
        if attempt_indices and attempt_indices != tuple(
            range(1, len(attempt_indices) + 1)
        ):
            raise ValueError("campaign physical attempts must be globally contiguous")
        if any(item.response_payload is not None for item in self.physical_attempts):
            raise ValueError("campaign cannot persist physical response payloads")
        expected_evidence = (
            "passed"
            if self.operational_verdict == self.agentic_verdict == "passed"
            else "blocked"
        )
        if (
            self.evidence_verdict != expected_evidence
            or self.final_state.operational_verdict != self.operational_verdict
            or self.final_state.agentic_verdict != self.agentic_verdict
            or self.final_state.evidence_verdict != self.evidence_verdict
            or self.final_state.blockers != self.blockers
            or self.final_state.physical_attempt_count != len(self.physical_attempts)
        ):
            raise ValueError("campaign result verdict binding is invalid")
        if self.operational_verdict == "passed" and (
            self.final_state.status != "completed"
            or self.final_state.current_revision
            != self.plan.expected_total_monitoring_ticks
            or self.total_trigger_event_count
            != self.plan.expected_total_trigger_event_count
            or self.suppressed_trigger_count
            != self.plan.expected_suppressed_trigger_count
            or self.variable_run_slots_reserved
            != self.plan.expected_variable_run_slots_reserved
        ):
            raise ValueError("passed operational result contradicts its evidence")
        if self.agentic_verdict == "passed":
            attempts_from_observations: dict[int, AgentReliabilityAttempt] = {}
            for observation in self.observations:
                for attempt in observation.physical_attempts:
                    if attempt.attempt_index in attempts_from_observations:
                        raise ValueError(
                            "passed campaign cannot reuse one physical attempt"
                        )
                    attempts_from_observations[attempt.attempt_index] = attempt
            if (
                len(self.observations) != self.plan.expected_decision_count
                or attempts_from_observations
                != {item.attempt_index: item for item in self.physical_attempts}
            ):
                raise ValueError(
                    "passed campaign physical ledger does not bind observations"
                )
        return self


class MonitoringEvidenceCampaignArtifacts(StrictBaseModel):
    output_dir: str
    plan_path: str
    preregistration_path: str
    state_path: str
    result_path: str
    observations_path: str
    report_path: str


class MonitoringEvidenceCampaignPublication(_HashedCampaignModel):
    _hash_field = "publication_sha256"
    schema_version: Literal["monitoring_evidence_campaign_publication_v1"] = (
        "monitoring_evidence_campaign_publication_v1"
    )
    campaign_id: str
    preregistration_ref: str = Field(min_length=1)
    registration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_ref: str
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    state_ref: str
    state_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_ref: str | None = None
    result_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    publication_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    published_at: AwareDatetime

    @model_validator(mode="after")
    def validate_optional_result_pair(self):
        if (self.result_ref is None) != (self.result_sha256 is None):
            raise ValueError("published result ref and hash must appear together")
        return self


class MonitoringEvidenceCampaignPublished(StrictBaseModel):
    publication: MonitoringEvidenceCampaignPublication
    preregistration: MonitoringEvidenceCampaignPreregistration
    plan: MonitoringEvidenceCampaignPlan
    state: MonitoringEvidenceCampaignState
    result: MonitoringEvidenceCampaignResult | None = None


def _with_hash(model_cls, payload: Mapping[str, Any]):
    values = dict(payload)
    values[model_cls._hash_field] = model_cls.canonical_sha256(values)
    return model_cls.model_validate(values)


def _source_hashes() -> dict[str, str]:
    base = default_monitoring_review_reliability_plan(
        plan_id="campaign-source-profile"
    )
    hashes = dict(base.source_sha256s)
    for reference in (
        "codigo/app/api/routes.py",
        "codigo/app/graph/pipeline.py",
        "codigo/app/services/agent_reliability.py",
        "codigo/app/services/api_run_jobs.py",
        "codigo/app/services/llm.py",
        "codigo/app/services/monitoring_evidence_campaign.py",
        "codigo/app/services/monitoring_policy_proposal.py",
        "codigo/app/services/monitoring_replay.py",
        "codigo/app/services/monitoring_trigger_engine.py",
        "codigo/app/services/run_persistence.py",
        "codigo/app/services/temporal_health_policy.py",
        "codigo/scripts/run_monitoring_evidence_campaign.py",
    ):
        hashes[reference] = hashlib.sha256(
            (_PROJECT_ROOT / reference).read_bytes()
        ).hexdigest()
    return dict(sorted(hashes.items()))


def default_monitoring_evidence_campaign_plan(
    *,
    campaign_id: str = DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_ID,
    speed_multiplier: float = 60.0,
    heartbeat_interval_seconds: float = 5.0,
) -> MonitoringEvidenceCampaignPlan:
    base = default_monitoring_review_reliability_plan(plan_id=campaign_id)
    payload = {
        "campaign_id": campaign_id,
        "session_id": f"{campaign_id}-session",
        "speed_multiplier": speed_multiplier,
        "step_interval_seconds": 600.0 / speed_multiplier,
        "heartbeat_interval_seconds": heartbeat_interval_seconds,
        "model_digest_sha256": base.model_digest_sha256,
        "llm_config": base.llm_config,
        "contract_fingerprints": base.contract_fingerprints,
        "source_sha256s": _source_hashes(),
    }
    return _with_hash(MonitoringEvidenceCampaignPlan, payload)


def preregister_monitoring_evidence_campaign_plan(
    plan: MonitoringEvidenceCampaignPlan,
    *,
    output_root: Path | str = DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_OUTPUT_DIR,
) -> MonitoringEvidenceCampaignPreregistration:
    destination = _campaign_dir(output_root, plan.campaign_id)
    destination.mkdir(parents=True, exist_ok=True)
    plan_path = destination / "plan.json"
    registration_path = destination / "preregistration.json"
    with (destination / ".campaign.lock").open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        _write_immutable_json(plan_path, plan.model_dump(mode="json"))
        if registration_path.is_file():
            registration = MonitoringEvidenceCampaignPreregistration.model_validate(
                _read_json(registration_path)
            )
            if registration.plan_sha256 != plan.plan_sha256:
                raise ValueError("campaign preregistration plan conflict")
            return registration
        registration = _with_hash(
            MonitoringEvidenceCampaignPreregistration,
            {
                "campaign_id": plan.campaign_id,
                "plan_ref": plan_path.as_posix(),
                "plan_sha256": plan.plan_sha256,
                "registered_at": datetime.now(UTC),
            },
        )
        _write_json_atomic(registration_path, registration.model_dump(mode="json"))
        return registration


def validate_monitoring_evidence_campaign_sources(
    plan: MonitoringEvidenceCampaignPlan,
) -> None:
    """Impide ejecutar si cambió una fuente congelada tras el prerregistro."""

    for reference, expected_sha256 in plan.source_sha256s.items():
        path = _PROJECT_ROOT / reference
        if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != expected_sha256:
            raise ValueError(f"campaign source changed after preregistration: {reference}")


def start_monitoring_evidence_campaign_state(
    plan: MonitoringEvidenceCampaignPlan,
    *,
    started_at: datetime | None = None,
) -> MonitoringEvidenceCampaignState:
    now = started_at or datetime.now(UTC)
    reviews = tuple(
        MonitoringEvidenceCampaignReview(
            context_id=context.context_id,
            ordinal=context.ordinal,
            trigger_type=context.trigger_type,
            reason_code=context.reason_code,
            condition_start_cursor=context.condition_start_cursor,
            cutoff_cursor=context.cutoff_cursor,
            source_time=CAMPAIGN_SOURCE_TIMES[context.cutoff_cursor],
        )
        for context in plan.expected_contexts
    )
    return _with_hash(
        MonitoringEvidenceCampaignState,
        {
            "campaign_id": plan.campaign_id,
            "plan_sha256": plan.plan_sha256,
            "session_id": plan.session_id,
            "status": "planned",
            "phase": "planned",
            "reviews": reviews,
            "updated_at": now,
        },
    )


def update_monitoring_evidence_campaign_state(
    plan: MonitoringEvidenceCampaignPlan,
    state: MonitoringEvidenceCampaignState,
    event: Mapping[str, Any],
    *,
    recorded_at: datetime | None = None,
) -> MonitoringEvidenceCampaignState:
    if state.plan_sha256 != plan.plan_sha256:
        raise ValueError("campaign state does not bind the plan")
    now = recorded_at or datetime.now(UTC)
    revision = int(event.get("revision", state.current_revision))
    cursor = None if revision == 0 else revision - 1
    reviews = list(state.reviews)
    cutoff = event.get("cutoff_cursor")
    if cutoff is not None:
        revision = max(revision, int(cutoff) + 1)
        cursor = max(cursor if cursor is not None else -1, int(cutoff))
        index = next(
            (i for i, item in enumerate(reviews) if item.cutoff_cursor == int(cutoff)),
            None,
        )
        if index is not None:
            item = reviews[index]
            lifecycle = item.lifecycle
            if event.get("kind") == "review_dispatching":
                lifecycle = "running"
            elif event.get("kind") == "review_terminal":
                candidate = str(event.get("child_lifecycle") or "failed")
                lifecycle = candidate if candidate in {
                    "resolved", "failed", "interrupted"
                } else "failed"
            reviews[index] = item.model_copy(
                update={
                    "lifecycle": lifecycle,
                    "trigger_id": event.get("trigger_id") or item.trigger_id,
                    "trigger_event_id": (
                        event.get("trigger_event_id") or item.trigger_event_id
                    ),
                    "child_run_id": event.get("child_run_id") or item.child_run_id,
                    "job_status": event.get("job_status") or item.job_status,
                    "decision_count": int(event.get("decision_count", item.decision_count)),
                    "llm_origin_count": int(event.get("llm_origin_count", item.llm_origin_count)),
                    "repaired_count": int(event.get("repaired_count", item.repaired_count)),
                    "fallback_count": int(event.get("fallback_count", item.fallback_count)),
                    "proposal_id": event.get("proposal_id") or item.proposal_id,
                    "proposal_sha256": (
                        event.get("proposal_sha256") or item.proposal_sha256
                    ),
                    "proposal_status": event.get("proposal_status") or item.proposal_status,
                    "proposal_application_status": (
                        event.get("proposal_application_status")
                        or item.proposal_application_status
                    ),
                    "error": event.get("error") or item.error,
                }
            )
    if revision < state.current_revision:
        raise ValueError("campaign progress revision cannot move backwards")
    if event.get("kind") == "campaign_failed":
        status: CampaignStatus = "failed"
    elif event.get("kind") == "campaign_interrupted":
        status = "interrupted"
    else:
        status = "running"
    phase: CampaignPhase
    if cursor is None:
        phase = "planned"
    elif cursor < plan.agentic_window_start_cursor:
        phase = "pre_roll"
    else:
        phase = "agentic_window"
    payload = state.model_dump(mode="python", exclude={"state_sha256"})
    payload.update(
        {
            "status": status,
            "phase": phase,
            "current_revision": revision,
            "execution_cursor": cursor,
            "progress_ratio": revision / plan.expected_total_monitoring_ticks,
            "reviews": tuple(reviews),
            "observed_trigger_count": sum(item.trigger_id is not None for item in reviews),
            "terminal_child_run_count": sum(
                item.lifecycle in {"resolved", "failed", "interrupted"}
                for item in reviews
            ),
            "resolved_child_run_count": sum(item.lifecycle == "resolved" for item in reviews),
            "observed_decision_count": sum(item.decision_count for item in reviews),
            "physical_attempt_count": int(
                event.get("physical_attempt_count", state.physical_attempt_count)
            ),
            "llm_origin_decision_count": sum(item.llm_origin_count for item in reviews),
            "repaired_decision_count": sum(item.repaired_count for item in reviews),
            "fallback_count": sum(item.fallback_count for item in reviews),
            "policy_proposal_count": sum(
                item.proposal_status == "advisory_not_applied" for item in reviews
            ),
            "started_at": state.started_at or now,
            "updated_at": now,
            "runtime_elapsed_seconds": float(
                event.get("runtime_elapsed_seconds", state.runtime_elapsed_seconds)
            ),
            "blockers": (
                tuple((*state.blockers, str(event.get("error") or "campaign failed")))
                if status in {"failed", "interrupted"}
                else state.blockers
            ),
        }
    )
    return _with_hash(MonitoringEvidenceCampaignState, payload)


def _campaign_observation_matrix_blockers(
    plan: MonitoringEvidenceCampaignPlan,
    *,
    observations: Sequence[MonitoringReviewReliabilityObservation],
    reviews: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    """Comprueba que la evidencia es exactamente 4 contextos por 7 roles."""

    review_by_cutoff: dict[int, Mapping[str, Any]] = {}
    for review in reviews:
        cutoff = int(review.get("cutoff_cursor", -1))
        if cutoff in review_by_cutoff:
            return ("duplicate_review_context",)
        review_by_cutoff[cutoff] = review

    expected_by_context = {item.context_id: item for item in plan.expected_contexts}
    observed_keys: set[tuple[str, AgentName]] = set()
    blockers: list[str] = []
    for observation in observations:
        key = (observation.context_id, observation.agent_name)
        if key in observed_keys:
            blockers.append("duplicate_context_role_observation")
        observed_keys.add(key)
        expected = expected_by_context.get(observation.context_id)
        review = review_by_cutoff.get(observation.cutoff_cursor)
        if expected is None or review is None:
            blockers.append("unknown_observation_context")
            continue
        expected_identity = (
            plan.campaign_id,
            1,
            plan.session_id,
            expected.ordinal,
            expected.trigger_type,
            expected.reason_code,
            expected.condition_start_cursor,
            expected.cutoff_cursor,
            review.get("trigger_id"),
            review.get("trigger_event_id"),
            review.get("child_run_id"),
        )
        observed_identity = (
            observation.plan_id,
            observation.repetition,
            observation.session_id,
            observation.context_ordinal,
            observation.trigger_type,
            observation.reason_code,
            observation.condition_start_cursor,
            observation.cutoff_cursor,
            observation.trigger_id,
            observation.trigger_event_id,
            observation.child_run_id,
        )
        if observed_identity != expected_identity:
            blockers.append("observation_binding_mismatch")

    expected_keys = {
        (context.context_id, role)
        for context in plan.expected_contexts
        for role in plan.expected_roles
    }
    if observed_keys != expected_keys:
        blockers.append("context_role_matrix_incomplete")
    return tuple(dict.fromkeys(blockers))


def finalize_monitoring_evidence_campaign(
    plan: MonitoringEvidenceCampaignPlan,
    state: MonitoringEvidenceCampaignState,
    *,
    preregistration: MonitoringEvidenceCampaignPreregistration,
    cycle: Mapping[str, Any],
    observations: Sequence[MonitoringReviewReliabilityObservation],
    physical_attempts: Sequence[AgentReliabilityAttempt] | None = None,
    completed_at: datetime | None = None,
) -> MonitoringEvidenceCampaignResult:
    if (
        preregistration.campaign_id != plan.campaign_id
        or preregistration.plan_sha256 != plan.plan_sha256
    ):
        raise ValueError("campaign preregistration does not bind the final plan")
    now = completed_at or datetime.now(UTC)
    reviews = cycle.get("reviews", ())
    working_state = state
    for review in reviews:
        working_state = update_monitoring_evidence_campaign_state(
            plan,
            working_state,
            {"kind": "review_terminal", **dict(review)},
            recorded_at=now,
        )
    expected_trigger_pack = tuple(
        (
            item.trigger_type,
            item.reason_code,
            item.condition_start_cursor,
            item.cutoff_cursor,
        )
        for item in plan.expected_contexts
    )
    observed_trigger_pack = tuple(
        (
            item.get("trigger_type"),
            item.get("reason_code"),
            int(item.get("condition_start_cursor", -1)),
            int(item.get("cutoff_cursor", -1)),
        )
        for item in reviews
    )
    operational_blockers: list[str] = []
    if cycle.get("session_id") != plan.session_id:
        operational_blockers.append("campaign_session_mismatch")
    if (
        cycle.get("memory_mode") != plan.memory_mode
        or cycle.get("policy_application_status")
        != plan.policy_application_status
    ):
        operational_blockers.append("campaign_safety_mode_mismatch")
    if cycle.get("session_status") != "completed":
        operational_blockers.append("session_not_completed")
    if int(cycle.get("final_revision", -1)) != plan.expected_total_monitoring_ticks:
        operational_blockers.append("monitoring_tick_count_mismatch")
    if observed_trigger_pack != expected_trigger_pack:
        operational_blockers.append("primary_trigger_pack_mismatch")
    if len(reviews) != plan.expected_child_run_count:
        operational_blockers.append("child_run_count_mismatch")
    if any(
        item.get("child_lifecycle") not in {"resolved", "failed", "interrupted"}
        for item in reviews
    ):
        operational_blockers.append("non_terminal_child_run")
    if (
        len({item.get("trigger_id") for item in reviews}) != len(reviews)
        or len({item.get("child_run_id") for item in reviews}) != len(reviews)
        or any(
            not item.get("trigger_id") or not item.get("child_run_id")
            for item in reviews
        )
    ):
        operational_blockers.append("review_identity_collision")
    total_trigger_events = int(cycle.get("total_trigger_event_count", -1))
    suppressed_triggers = int(cycle.get("suppressed_trigger_count", -1))
    variable_slots = int(cycle.get("variable_run_slots_reserved", -1))
    if total_trigger_events != plan.expected_total_trigger_event_count:
        operational_blockers.append("trigger_event_count_mismatch")
    if suppressed_triggers != plan.expected_suppressed_trigger_count:
        operational_blockers.append("suppressed_trigger_count_mismatch")
    if variable_slots != plan.expected_variable_run_slots_reserved:
        operational_blockers.append("variable_budget_usage_mismatch")

    observations = tuple(observations)
    observed_attempts_by_index: dict[int, AgentReliabilityAttempt] = {}
    observed_attempt_owners: dict[int, str] = {}
    duplicate_attempt_ownership = False
    for observation in observations:
        for attempt in observation.physical_attempts:
            previous = observed_attempts_by_index.get(attempt.attempt_index)
            if previous is not None and previous != attempt:
                raise ValueError("conflicting campaign physical attempt index")
            previous_owner = observed_attempt_owners.get(attempt.attempt_index)
            if previous_owner is not None:
                duplicate_attempt_ownership = True
            observed_attempts_by_index[attempt.attempt_index] = attempt
            observed_attempt_owners[attempt.attempt_index] = observation.observation_id
    if physical_attempts is None:
        sealed_physical_attempts = tuple(
            observed_attempts_by_index[index]
            for index in sorted(observed_attempts_by_index)
        )
    else:
        sealed_physical_attempts = tuple(physical_attempts)
    sealed_attempts_by_index = {
        attempt.attempt_index: attempt for attempt in sealed_physical_attempts
    }
    physical_attempt_binding_valid = all(
        sealed_attempts_by_index.get(index) == attempt
        for index, attempt in observed_attempts_by_index.items()
    )
    unbound_physical_attempts = set(sealed_attempts_by_index).difference(
        observed_attempts_by_index
    )
    observation_matrix_blockers = _campaign_observation_matrix_blockers(
        plan,
        observations=observations,
        reviews=reviews,
    )
    first_pass = sum(item.outcome == "first_pass" for item in observations)
    repaired = sum(item.outcome == "llm_repaired" for item in observations)
    fallbacks = sum(item.outcome == "fallback" for item in observations)
    non_agentic = sum(item.outcome == "non_agentic" for item in observations)
    errors = sum(item.outcome == "error" for item in observations)
    check_fields = (
        "trace_valid", "physical_trace_valid", "binding_valid", "grounding_valid",
        "hypothesis_structural_valid", "claims_scoped", "action_catalog_valid",
        "memory_mode_valid", "policy_application_valid",
    )
    structural = sum(
        all(bool(getattr(item.checks, field)) for field in check_fields)
        for item in observations
    )
    resolved = sum(item.get("child_lifecycle") == "resolved" for item in reviews)
    proposals = sum(
        item.get("proposal_status") == "advisory_not_applied"
        and item.get("proposal_application_status") == "not_applied"
        and bool(item.get("proposal_id"))
        and bool(re.fullmatch(r"[0-9a-f]{64}", str(item.get("proposal_sha256") or "")))
        for item in reviews
    )
    agentic_blockers: list[str] = []
    agentic_blockers.extend(observation_matrix_blockers)
    if duplicate_attempt_ownership:
        agentic_blockers.append("duplicate_physical_attempt_ownership")
    if not physical_attempt_binding_valid:
        agentic_blockers.append("physical_attempt_ledger_mismatch")
    if len(observations) != plan.expected_decision_count:
        agentic_blockers.append("decision_count_mismatch")
    if resolved != plan.expected_child_run_count:
        agentic_blockers.append("not_all_children_resolved")
    if fallbacks:
        agentic_blockers.append(f"fallback_count:{fallbacks}")
    if non_agentic or errors:
        agentic_blockers.append("non_agentic_or_error_observed")
    if structural != plan.expected_decision_count:
        agentic_blockers.append("contract_check_coverage_incomplete")
    if proposals != plan.expected_policy_proposal_count:
        agentic_blockers.append("policy_proposal_count_mismatch")
    if len({item.get("proposal_id") for item in reviews}) != len(reviews):
        agentic_blockers.append("policy_proposal_identity_collision")
    if len(observations) and first_pass / len(observations) < plan.minimum_first_pass_rate:
        agentic_blockers.append("first_pass_rate_below_plan")
    if unbound_physical_attempts and errors == 0:
        agentic_blockers.append("unbound_physical_attempts")

    operational = "passed" if not operational_blockers else "blocked"
    agentic = "passed" if not agentic_blockers else "blocked"
    evidence = "passed" if operational == agentic == "passed" else "blocked"
    execution_started_at = working_state.started_at or now
    if preregistration.registered_at > execution_started_at:
        raise ValueError("campaign execution predates its preregistration")
    final_payload = working_state.model_dump(
        mode="python", exclude={"state_sha256"}
    )
    final_payload.update(
        {
            "status": "completed" if operational == "passed" else "failed",
            "phase": "completed",
            "evidence_verdict": evidence,
            "operational_verdict": operational,
            "agentic_verdict": agentic,
            "current_revision": int(cycle.get("final_revision", state.current_revision)),
            "execution_cursor": plan.agentic_window_end_cursor,
            "progress_ratio": 1.0,
            "blockers": tuple((*operational_blockers, *agentic_blockers)),
            "physical_attempt_count": len(sealed_physical_attempts),
            "completed_at": now,
            "updated_at": now,
            "runtime_elapsed_seconds": float(cycle.get("runtime_elapsed_seconds", 0.0)),
        }
    )
    final_state = _with_hash(MonitoringEvidenceCampaignState, final_payload)
    result_payload = {
        "preregistration_ref": Path(preregistration.plan_ref)
        .with_name("preregistration.json")
        .as_posix(),
        "registration_sha256": preregistration.registration_sha256,
        "registered_at": preregistration.registered_at,
        "plan": plan,
        "final_state": final_state,
        "observations": observations,
        "physical_attempts": sealed_physical_attempts,
        "operational_verdict": operational,
        "agentic_verdict": agentic,
        "evidence_verdict": evidence,
        "blockers": final_state.blockers,
        "first_pass_count": first_pass,
        "repaired_count": repaired,
        "fallback_count": fallbacks,
        "non_agentic_count": non_agentic,
        "error_count": errors,
        "structural_check_pass_count": structural,
        "total_trigger_event_count": max(total_trigger_events, 0),
        "suppressed_trigger_count": max(suppressed_triggers, 0),
        "variable_run_slots_reserved": max(variable_slots, 0),
        "steps_applied_this_invocation": int(cycle.get("steps_applied", 0)),
        "pacing_wait_count": int(cycle.get("pacing_wait_count", 0)),
        "pacing_elapsed_seconds": float(cycle.get("pacing_elapsed_seconds", 0.0)),
        "heartbeat_count": int(cycle.get("heartbeat_count", 0)),
        "started_at": execution_started_at,
        "completed_at": now,
    }
    return _with_hash(MonitoringEvidenceCampaignResult, result_payload)


def write_monitoring_evidence_campaign_artifacts(
    result: MonitoringEvidenceCampaignResult,
    preregistration: MonitoringEvidenceCampaignPreregistration,
    *,
    output_root: Path | str = DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_OUTPUT_DIR,
) -> MonitoringEvidenceCampaignArtifacts:
    if (
        preregistration.campaign_id != result.plan.campaign_id
        or preregistration.plan_sha256 != result.plan.plan_sha256
        or preregistration.registration_sha256 != result.registration_sha256
        or preregistration.registered_at != result.registered_at
        or preregistration.registered_at > result.started_at
    ):
        raise ValueError("campaign preregistration does not bind the result plan")
    destination = _campaign_dir(output_root, result.plan.campaign_id)
    if Path(result.preregistration_ref).resolve() != (
        destination / "preregistration.json"
    ).resolve():
        raise ValueError("campaign result preregistration_ref is not canonical")
    paths = {
        "plan": destination / "plan.json",
        "preregistration": destination / "preregistration.json",
        "state": destination / "final_state.json",
        "result": destination / "result.json",
        "observations": destination / "observations.jsonl",
        "report": destination / "report.md",
    }
    _write_immutable_json(paths["plan"], result.plan.model_dump(mode="json"))
    _write_immutable_json(
        paths["preregistration"], preregistration.model_dump(mode="json")
    )
    _write_immutable_json(
        paths["state"], result.final_state.model_dump(mode="json")
    )
    _write_immutable_json(paths["result"], result.model_dump(mode="json"))
    observation_text = "".join(
        json.dumps(item.model_dump(mode="json"), ensure_ascii=True, sort_keys=True)
        + "\n"
        for item in result.observations
    )
    _write_immutable_text(paths["observations"], observation_text)
    _write_immutable_text(paths["report"], _render_report(result))
    return MonitoringEvidenceCampaignArtifacts(
        output_dir=destination.as_posix(),
        plan_path=paths["plan"].as_posix(),
        preregistration_path=paths["preregistration"].as_posix(),
        state_path=paths["state"].as_posix(),
        result_path=paths["result"].as_posix(),
        observations_path=paths["observations"].as_posix(),
        report_path=paths["report"].as_posix(),
    )


def publish_monitoring_evidence_campaign(
    plan: MonitoringEvidenceCampaignPlan,
    state: MonitoringEvidenceCampaignState,
    *,
    preregistration: MonitoringEvidenceCampaignPreregistration,
    result: MonitoringEvidenceCampaignResult | None = None,
    output_root: Path | str = DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_OUTPUT_DIR,
) -> MonitoringEvidenceCampaignPublication:
    if (
        preregistration.campaign_id != plan.campaign_id
        or preregistration.plan_sha256 != plan.plan_sha256
    ):
        raise ValueError("campaign preregistration does not bind the published plan")
    if state.campaign_id != plan.campaign_id or state.plan_sha256 != plan.plan_sha256:
        raise ValueError("campaign state does not bind the published plan")
    if state.started_at is not None and preregistration.registered_at > state.started_at:
        raise ValueError("campaign must be preregistered before execution starts")
    if result is not None and (
        result.plan != plan or result.final_state != state
    ):
        raise ValueError("campaign result does not bind the published state")
    if result is not None and (
        result.registration_sha256 != preregistration.registration_sha256
        or result.registered_at != preregistration.registered_at
    ):
        raise ValueError("campaign result does not bind the preregistration")
    root = Path(output_root)
    destination = _campaign_dir(root, plan.campaign_id)
    destination.mkdir(parents=True, exist_ok=True)
    plan_path = destination / "plan.json"
    preregistration_path = destination / "preregistration.json"
    state_path = destination / "states" / f"{state.state_sha256}.json"
    result_path = destination / "result.json"
    if Path(preregistration.plan_ref).resolve() != plan_path.resolve():
        raise ValueError("campaign preregistration plan_ref is not canonical")
    if result is not None and Path(result.preregistration_ref).resolve() != (
        preregistration_path.resolve()
    ):
        raise ValueError("campaign result preregistration_ref is not canonical")
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".publication.lock").open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        campaign_publication_path = destination / "publication.json"
        current = _load_publication_if_present(campaign_publication_path)
        if current is not None and current.campaign_id == plan.campaign_id:
            if (
                current.plan_sha256 != plan.plan_sha256
                or current.registration_sha256
                != preregistration.registration_sha256
            ):
                raise ValueError("published campaign identity is immutable")
            current_state = MonitoringEvidenceCampaignState.model_validate(
                _read_json(_contained_path(root.resolve(), current.state_ref))
            )
            if current.result_ref is not None:
                if result is not None and current.result_sha256 != result.result_sha256:
                    raise ValueError("completed campaign result is immutable")
                return current
            if _campaign_state_precedes(state, current_state):
                return current

        _write_immutable_json(plan_path, plan.model_dump(mode="json"))
        _write_immutable_json(
            preregistration_path,
            preregistration.model_dump(mode="json"),
        )
        _write_immutable_json(state_path, state.model_dump(mode="json"))
        if result is not None:
            _write_immutable_json(result_path, result.model_dump(mode="json"))
        publication = _with_hash(
            MonitoringEvidenceCampaignPublication,
            {
                "campaign_id": plan.campaign_id,
                "preregistration_ref": preregistration_path.as_posix(),
                "registration_sha256": preregistration.registration_sha256,
                "plan_ref": plan_path.as_posix(),
                "plan_sha256": plan.plan_sha256,
                "state_ref": state_path.as_posix(),
                "state_sha256": state.state_sha256,
                "result_ref": result_path.as_posix() if result is not None else None,
                "result_sha256": result.result_sha256 if result is not None else None,
                "published_at": datetime.now(UTC),
            },
        )
        _write_json_atomic(
            campaign_publication_path,
            publication.model_dump(mode="json"),
        )
        _write_json_atomic(root / "current.json", publication.model_dump(mode="json"))
        return publication


def load_published_monitoring_evidence_campaign(
    *,
    output_root: Path | str = DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_OUTPUT_DIR,
    campaign_id: str | None = None,
) -> MonitoringEvidenceCampaignPublished:
    root = Path(output_root).resolve()
    publication_path = (
        root / "current.json"
        if campaign_id is None
        else _campaign_dir(root, campaign_id) / "publication.json"
    )
    publication = MonitoringEvidenceCampaignPublication.model_validate(
        _read_json(publication_path)
    )
    if campaign_id is not None and publication.campaign_id != campaign_id:
        raise ValueError("campaign publication identity mismatch")
    preregistration_path = _contained_path(root, publication.preregistration_ref)
    plan_path = _contained_path(root, publication.plan_ref)
    state_path = _contained_path(root, publication.state_ref)
    preregistration = MonitoringEvidenceCampaignPreregistration.model_validate(
        _read_json(preregistration_path)
    )
    plan = MonitoringEvidenceCampaignPlan.model_validate(_read_json(plan_path))
    state = MonitoringEvidenceCampaignState.model_validate(_read_json(state_path))
    if plan.plan_sha256 != publication.plan_sha256:
        raise ValueError("published campaign plan hash mismatch")
    if (
        preregistration.registration_sha256 != publication.registration_sha256
        or preregistration.campaign_id != publication.campaign_id
        or preregistration.plan_sha256 != publication.plan_sha256
        or plan.campaign_id != publication.campaign_id
        or Path(preregistration.plan_ref).resolve() != plan_path
    ):
        raise ValueError("published campaign preregistration binding mismatch")
    if state.state_sha256 != publication.state_sha256:
        raise ValueError("published campaign state hash mismatch")
    result = None
    if publication.result_ref is not None:
        result_path = _contained_path(root, publication.result_ref)
        result = MonitoringEvidenceCampaignResult.model_validate(
            _read_json(result_path)
        )
        if result.result_sha256 != publication.result_sha256:
            raise ValueError("published campaign result hash mismatch")
        if result.plan != plan or result.final_state != state:
            raise ValueError("published campaign result binding mismatch")
        if (
            result.preregistration_ref != publication.preregistration_ref
            or result.registration_sha256 != preregistration.registration_sha256
            or result.registered_at != preregistration.registered_at
        ):
            raise ValueError("published campaign result preregistration mismatch")
    if state.plan_sha256 != plan.plan_sha256 or state.campaign_id != plan.campaign_id:
        raise ValueError("published campaign state binding mismatch")
    if state.started_at is not None and preregistration.registered_at > state.started_at:
        raise ValueError("published campaign started before preregistration")
    return MonitoringEvidenceCampaignPublished(
        publication=publication,
        preregistration=preregistration,
        plan=plan,
        state=state,
        result=result,
    )


def _load_publication_if_present(
    publication_path: Path,
) -> MonitoringEvidenceCampaignPublication | None:
    if not publication_path.exists():
        return None
    if publication_path.is_symlink() or not publication_path.is_file():
        raise ValueError("campaign publication pointer must be a regular file")
    return MonitoringEvidenceCampaignPublication.model_validate(
        _read_json(publication_path)
    )


def _campaign_state_precedes(
    candidate: MonitoringEvidenceCampaignState,
    current: MonitoringEvidenceCampaignState,
) -> bool:
    """True cuando publicar ``candidate`` degradaría el estado visible."""

    if candidate.current_revision < current.current_revision:
        return True
    revision_advanced = candidate.current_revision > current.current_revision
    rank = {
        "planned": 0,
        "running": 1,
        "completed": 2,
        "interrupted": 2,
        "failed": 2,
    }
    if rank[candidate.status] < rank[current.status]:
        return True
    status_advanced = rank[candidate.status] > rank[current.status]
    if current.status in {"completed", "interrupted", "failed"} and (
        candidate.status != current.status
    ):
        return True
    monotonic_counts = (
        "observed_trigger_count",
        "terminal_child_run_count",
        "resolved_child_run_count",
        "observed_decision_count",
        "physical_attempt_count",
        "llm_origin_decision_count",
        "repaired_decision_count",
        "fallback_count",
        "policy_proposal_count",
    )
    if any(
        getattr(candidate, field) < getattr(current, field)
        for field in monotonic_counts
    ):
        return True
    lifecycle_rank = {
        "pending": 0,
        "running": 1,
        "resolved": 2,
        "failed": 2,
        "interrupted": 2,
    }
    for candidate_review, current_review in zip(
        candidate.reviews,
        current.reviews,
        strict=True,
    ):
        if lifecycle_rank[candidate_review.lifecycle] < lifecycle_rank[
            current_review.lifecycle
        ]:
            return True
        if current_review.lifecycle in {"resolved", "failed", "interrupted"} and (
            candidate_review.lifecycle != current_review.lifecycle
        ):
            return True
        if current_review.lifecycle in {"resolved", "failed", "interrupted"} and (
            candidate_review != current_review
        ):
            return True
        for field in ("trigger_id", "trigger_event_id", "child_run_id"):
            current_value = getattr(current_review, field)
            candidate_value = getattr(candidate_review, field)
            if current_value is not None and candidate_value != current_value:
                return True
    candidate_progress = candidate.model_dump(
        mode="json",
        exclude={"state_sha256", "updated_at"},
    )
    current_progress = current.model_dump(
        mode="json",
        exclude={"state_sha256", "updated_at"},
    )
    if candidate_progress == current_progress:
        return True
    if revision_advanced or status_advanced:
        return False
    return candidate.updated_at <= current.updated_at


def _campaign_dir(output_root: Path | str, campaign_id: str) -> Path:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", campaign_id):
        raise ValueError("campaign_id must be a plain safe name")
    return Path(output_root) / campaign_id


def _contained_path(root: Path, reference: str) -> Path:
    path = Path(reference).resolve()
    if path.is_symlink() or not path.is_file() or root not in path.parents:
        raise ValueError("published campaign reference leaves output root")
    return path


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, payload: Any) -> None:
    _write_text_atomic(
        path,
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
    )


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_immutable_json(path: Path, payload: Any) -> None:
    if path.exists():
        if _json_sha256(_read_json(path)) != _json_sha256(payload):
            raise ValueError(f"immutable campaign artifact conflict: {path}")
        return
    _write_json_atomic(path, payload)


def _write_immutable_text(path: Path, text: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"immutable campaign artifact conflict: {path}")
        return
    _write_text_atomic(path, text)


def _render_report(result: MonitoringEvidenceCampaignResult) -> str:
    plan = result.plan
    return "\n".join(
        [
            f"# Campaña {plan.campaign_id}",
            "",
            "## Ventana",
            "",
            (
                f"Replay histórico acelerado con pre-roll causal 0--352 y ventana "
                f"agentiva 353--688: {plan.agentic_window_source_duration_seconds} "
                "segundos de tiempo NASA sin zona declarada."
            ),
            "",
            "## Resultado",
            "",
            f"- Motor operativo: `{result.operational_verdict}`.",
            f"- Comportamiento agentivo: `{result.agentic_verdict}`.",
            f"- Evidencia conjunta: `{result.evidence_verdict}`.",
            f"- Decisiones observadas: `{len(result.observations)}/28`.",
            f"- Llamadas físicas selladas: `{len(result.physical_attempts)}`.",
            f"- Fallbacks: `{result.fallback_count}`.",
            f"- Eventos P3: `{result.total_trigger_event_count}/14`.",
            f"- Suprimidos: `{result.suppressed_trigger_count}/10`.",
            f"- Slots variables: `{result.variable_run_slots_reserved}/3`.",
            "- Memoria: `off`.",
            "- Políticas aplicadas: `no`.",
            "",
            "No constituye streaming, validación física, RUL ni evidencia industrial.",
            "",
        ]
    )


__all__ = [
    "DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_ID",
    "DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_OUTPUT_DIR",
    "MonitoringEvidenceCampaignArtifacts",
    "MonitoringEvidenceCampaignPlan",
    "MonitoringEvidenceCampaignPreregistration",
    "MonitoringEvidenceCampaignPublication",
    "MonitoringEvidenceCampaignPublished",
    "MonitoringEvidenceCampaignResult",
    "MonitoringEvidenceCampaignReview",
    "MonitoringEvidenceCampaignState",
    "default_monitoring_evidence_campaign_plan",
    "finalize_monitoring_evidence_campaign",
    "load_published_monitoring_evidence_campaign",
    "preregister_monitoring_evidence_campaign_plan",
    "publish_monitoring_evidence_campaign",
    "start_monitoring_evidence_campaign_state",
    "update_monitoring_evidence_campaign_state",
    "validate_monitoring_evidence_campaign_sources",
    "write_monitoring_evidence_campaign_artifacts",
]
