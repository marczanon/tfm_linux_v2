"""Gate repetido de fiabilidad para revisiones causales de monitorizacion.

Este modulo no ejecuta el replay, Ollama ni LangGraph. Su frontera es:

* prerregistrar, antes de inferir, los cuatro contextos P3 seleccionados;
* proyectar los contratos ya sellados de cada run hija a observaciones pequenas;
* agregar fiabilidad de generacion, grounding y alcance narrativo;
* emitir un gate determinista y artefactos separados de las runs canonicas.

Las decisiones completas permanecen exclusivamente en ``codigo/reports/runs``.
Aqui solo se conservan identidades, hashes, acciones y checks reproducibles.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import unicodedata
import uuid
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import AwareDatetime, Field, model_validator

from codigo.app.agents.monitoring_reviewer import (
    ALLOWED_ACTIONS,
    ROLE_HYPOTHESIS_KIND,
    monitoring_review_contract_fingerprints,
)
from codigo.app.schemas.agent_decisions import (
    AgentName,
    DecisionGenerationOrigin,
    DecisionValidationStatus,
)
from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.monitoring_replay import (
    MONITORING_REVIEW_ROLES,
    CausalEvidenceCatalog,
    CausalInputView,
    MonitoringChildRunStatus,
    MonitoringReviewDecision,
    MonitoringReviewRecommendedAction,
    MonitoringReviewRequest,
    MonitoringReviewResult,
    MonitoringReviewStatus,
    MonitoringTriggerEvent,
    MonitoringTriggerReasonCode,
    MonitoringTriggerType,
)
from codigo.app.services.agent_reliability import (
    AgentReliabilityAttempt,
    AgentReliabilityModelConfig,
)
from codigo.app.services.monitoring_replay import DEFAULT_SCENARIO_ID
from codigo.app.services.online_blind import unsupported_official_v2_claims


MONITORING_REVIEW_RELIABILITY_PROTOCOL_ID = "monitoring_review_reliability_v1"
DEFAULT_MONITORING_REVIEW_RELIABILITY_OUTPUT_DIR = Path(
    "codigo/reports/validation/monitoring_review_reliability"
)
DEFAULT_MONITORING_REVIEW_RELIABILITY_PLAN_ID = (
    "nasa-p3-monitoring-review-qwen35-v1"
)
DEFAULT_MONITORING_REVIEW_MODEL_DIGEST_SHA256 = (
    "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd"
)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]


def _default_monitoring_review_reliability_llm_config(
) -> AgentReliabilityModelConfig:
    """Configuracion Qwen congelada por el protocolo nominal de este gate."""

    return AgentReliabilityModelConfig(
        provider="ollama",
        model="qwen3.5:4b",
        think=False,
        timeout_seconds=180.0,
        temperature=0.0,
        num_ctx=8192,
        num_predict=4096,
        max_json_repair_attempts=0,
        transport_trace_scope="physical_ollama_chat",
    )


def _source_sha256s() -> dict[str, str]:
    """Huella fuentes criticas con refs estables, independiente del cwd."""

    references = (
        "codigo/app/services/monitoring_review_reliability.py",
        "codigo/app/agents/monitoring_reviewer.py",
        "codigo/app/services/monitoring_review_store.py",
        "codigo/app/services/pipeline_runner.py",
        "codigo/app/schemas/monitoring_replay.py",
        "codigo/app/services/online_blind.py",
        "codigo/scripts/run_monitoring_review_reliability.py",
        "codigo/scripts/run_nasa_monitoring_trigger_review_smoke.py",
    )
    return {
        reference: hashlib.sha256((_PROJECT_ROOT / reference).read_bytes()).hexdigest()
        for reference in references
    }

MonitoringReviewReliabilityOutcome = Literal[
    "first_pass",
    "llm_repaired",
    "fallback",
    "non_agentic",
    "error",
]
MonitoringReviewReliabilityVerdict = Literal["passed", "blocked"]


class MonitoringReviewReliabilityExpectedContext(StrictBaseModel):
    """Trigger primario exacto que debe formar parte de cada repeticion."""

    context_id: str = Field(min_length=1, max_length=160)
    ordinal: int = Field(ge=1, le=4)
    trigger_type: MonitoringTriggerType
    reason_code: MonitoringTriggerReasonCode
    condition_start_cursor: int = Field(ge=0)
    cutoff_cursor: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_causal_interval(self) -> "MonitoringReviewReliabilityExpectedContext":
        if self.condition_start_cursor > self.cutoff_cursor:
            raise ValueError("condition_start_cursor cannot exceed cutoff_cursor")
        return self


EXPECTED_NASA_P3_PRIMARY_CONTEXTS: tuple[
    MonitoringReviewReliabilityExpectedContext, ...
] = (
    MonitoringReviewReliabilityExpectedContext(
        context_id="state_transition_353",
        ordinal=1,
        trigger_type="state_transition",
        reason_code="health_state_escalation",
        condition_start_cursor=353,
        cutoff_cursor=353,
    ),
    MonitoringReviewReliabilityExpectedContext(
        context_id="persistent_alert_498_from_496",
        ordinal=2,
        trigger_type="persistent_alert",
        reason_code="persistent_confirmation",
        condition_start_cursor=496,
        cutoff_cursor=498,
    ),
    MonitoringReviewReliabilityExpectedContext(
        context_id="state_transition_499",
        ordinal=3,
        trigger_type="state_transition",
        reason_code="health_state_escalation",
        condition_start_cursor=499,
        cutoff_cursor=499,
    ),
    MonitoringReviewReliabilityExpectedContext(
        context_id="session_close_688",
        ordinal=4,
        trigger_type="session_close",
        reason_code="session_completed",
        condition_start_cursor=688,
        cutoff_cursor=688,
    ),
)


class MonitoringReviewReliabilityAcceptancePolicy(StrictBaseModel):
    """Criterios congelados del gate; la consistencia no bloquea."""

    minimum_repetitions: Literal[3] = 3
    minimum_first_pass_rate: float = Field(default=0.90, ge=0.0, le=1.0)
    require_all_expected_contexts: Literal[True] = True
    require_all_roles: Literal[True] = True
    require_all_children_resolved: Literal[True] = True
    require_llm_origin_rate: Literal[1.0] = 1.0
    require_trace_coverage_rate: Literal[1.0] = 1.0
    require_physical_trace_rate: Literal[1.0] = 1.0
    require_grounding_rate: Literal[1.0] = 1.0
    require_hypothesis_structural_rate: Literal[1.0] = 1.0
    require_claims_scoped_rate: Literal[1.0] = 1.0
    require_binding_rate: Literal[1.0] = 1.0
    require_action_catalog_rate: Literal[1.0] = 1.0
    require_memory_off_rate: Literal[1.0] = 1.0
    require_policy_not_applied_rate: Literal[1.0] = 1.0
    require_zero_fallbacks: Literal[True] = True
    require_zero_non_agentic: Literal[True] = True
    require_zero_errors: Literal[True] = True


class MonitoringReviewReliabilityPlan(StrictBaseModel):
    """Plan cerrado que debe escribirse antes de cualquier llamada a Qwen."""

    schema_version: Literal["monitoring_review_reliability_plan_v1"] = (
        "monitoring_review_reliability_plan_v1"
    )
    protocol_id: Literal["monitoring_review_reliability_v1"] = (
        MONITORING_REVIEW_RELIABILITY_PROTOCOL_ID
    )
    plan_id: str = Field(
        default=DEFAULT_MONITORING_REVIEW_RELIABILITY_PLAN_ID,
        min_length=1,
        max_length=160,
    )
    dataset_id: Literal["nasa_ims_bearing"] = "nasa_ims_bearing"
    scenario_id: Literal["NASA-RTF-HYB-01"] = DEFAULT_SCENARIO_ID
    activation_policy_kind: Literal["P3"] = "P3"
    experiment_mode: Literal["frozen_benchmark"] = "frozen_benchmark"
    selector: Literal["all_primary_emitted"] = "all_primary_emitted"
    repetitions: Literal[3] = 3
    memory_enabled: Literal[False] = False
    policy_application_enabled: Literal[False] = False
    model_digest_sha256: Literal[
        "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd"
    ] = DEFAULT_MONITORING_REVIEW_MODEL_DIGEST_SHA256
    llm_config: AgentReliabilityModelConfig = Field(
        default_factory=_default_monitoring_review_reliability_llm_config
    )
    contract_fingerprints: dict[str, str] = Field(
        default_factory=monitoring_review_contract_fingerprints
    )
    source_sha256s: dict[str, str] = Field(default_factory=_source_sha256s)
    expected_contexts: tuple[
        MonitoringReviewReliabilityExpectedContext, ...
    ] = EXPECTED_NASA_P3_PRIMARY_CONTEXTS
    expected_roles: tuple[AgentName, ...] = MONITORING_REVIEW_ROLES
    acceptance: MonitoringReviewReliabilityAcceptancePolicy = Field(
        default_factory=MonitoringReviewReliabilityAcceptancePolicy
    )

    @model_validator(mode="after")
    def validate_frozen_pack(self) -> "MonitoringReviewReliabilityPlan":
        if self.expected_contexts != EXPECTED_NASA_P3_PRIMARY_CONTEXTS:
            raise ValueError("expected_contexts must match the frozen NASA P3 pack")
        if self.expected_roles != MONITORING_REVIEW_ROLES:
            raise ValueError("expected_roles must contain the seven canonical roles")
        if self.llm_config != _default_monitoring_review_reliability_llm_config():
            raise ValueError("llm_config must match the frozen Qwen 3.5 gate pack")
        expected_contracts = monitoring_review_contract_fingerprints()
        if set(self.contract_fingerprints) != set(expected_contracts) or any(
            not _is_sha256(value)
            for key, value in self.contract_fingerprints.items()
            if key.endswith("_sha256")
        ):
            raise ValueError("contract_fingerprints must contain the closed contract pack")
        if not self.source_sha256s or any(
            not reference or not _is_sha256(value)
            for reference, value in self.source_sha256s.items()
        ):
            raise ValueError("source_sha256s must contain valid source fingerprints")
        return self

    @property
    def expected_child_run_count(self) -> int:
        return self.repetitions * len(self.expected_contexts)

    @property
    def expected_observation_count(self) -> int:
        return self.expected_child_run_count * len(self.expected_roles)


class MonitoringReviewReliabilityPreregistration(StrictBaseModel):
    """Prueba de que el plan existia antes de comenzar la bateria."""

    schema_version: Literal["monitoring_review_reliability_preregistration_v1"] = (
        "monitoring_review_reliability_preregistration_v1"
    )
    plan_id: str = Field(min_length=1)
    plan_path: str = Field(min_length=1)
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registration_path: str = Field(min_length=1)
    registration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registered_at: AwareDatetime

    @model_validator(mode="after")
    def validate_registration_hash(
        self,
    ) -> "MonitoringReviewReliabilityPreregistration":
        expected = _json_sha256(
            self.model_dump(mode="json", exclude={"registration_sha256"})
        )
        if self.registration_sha256 != expected:
            raise ValueError("registration_sha256 does not match preregistration")
        return self


class MonitoringReviewReliabilityRoleChecks(StrictBaseModel):
    """Checks cerrados calculados sin juzgar la verdad de la hipotesis."""

    trace_valid: bool
    physical_trace_valid: bool
    binding_valid: bool
    grounding_valid: bool
    hypothesis_structural_valid: bool
    claims_scoped: bool
    action_catalog_valid: bool
    memory_mode_valid: bool
    policy_application_valid: bool
    unsupported_claim_ids: tuple[str, ...] = ()
    details: tuple[str, ...] = ()


class MonitoringReviewReliabilityObservation(StrictBaseModel):
    """Proyeccion por rol que referencia, pero no copia, la decision sellada."""

    schema_version: Literal["monitoring_review_reliability_observation_v1"] = (
        "monitoring_review_reliability_observation_v1"
    )
    observation_id: str = Field(min_length=1, max_length=400)
    plan_id: str = Field(min_length=1, max_length=160)
    repetition: int = Field(ge=1)
    context_id: str = Field(min_length=1, max_length=160)
    context_ordinal: int = Field(ge=1, le=4)
    trigger_type: MonitoringTriggerType
    reason_code: MonitoringTriggerReasonCode
    condition_start_cursor: int = Field(ge=0)
    cutoff_cursor: int = Field(ge=0)
    session_id: str = Field(min_length=1, max_length=160)
    trigger_id: str = Field(min_length=1, max_length=240)
    trigger_event_id: str = Field(min_length=1, max_length=240)
    child_run_id: str = Field(min_length=1, max_length=240)
    run_ref: str = Field(min_length=1)
    request_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    causal_view_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    child_lifecycle_status: MonitoringChildRunStatus
    review_status: MonitoringReviewStatus | None = None
    agent_name: AgentName
    outcome: MonitoringReviewReliabilityOutcome
    decision_id: str | None = Field(default=None, min_length=1, max_length=240)
    decision_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    generation_origin: DecisionGenerationOrigin | None = None
    generation_validation_status: DecisionValidationStatus | None = None
    generation_attempt_index: int | None = Field(default=None, ge=1)
    hypothesis_kind: str | None = Field(default=None, min_length=1)
    hypothesis_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    recommended_action: MonitoringReviewRecommendedAction | None = None
    evidence_refs: tuple[str, ...] = ()
    physical_attempts: tuple[AgentReliabilityAttempt, ...] = ()
    checks: MonitoringReviewReliabilityRoleChecks
    error_type: str | None = Field(default=None, min_length=1)
    error_message: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_outcome_payload(self) -> "MonitoringReviewReliabilityObservation":
        decision_fields = (
            self.decision_id,
            self.decision_sha256,
            self.generation_origin,
            self.generation_validation_status,
            self.generation_attempt_index,
            self.hypothesis_kind,
            self.hypothesis_sha256,
            self.recommended_action,
        )
        if self.outcome == "error":
            if self.error_type is None or self.error_message is None:
                raise ValueError("error observations require error_type and error_message")
            if any(value is not None for value in decision_fields):
                raise ValueError("error observations cannot declare a sealed decision")
        elif any(value is None for value in decision_fields):
            raise ValueError("non-error observations require decision references")
        if self.outcome != "error" and (
            self.error_type is not None or self.error_message is not None
        ):
            raise ValueError("only error observations can declare error details")
        if any(item.response_payload is not None for item in self.physical_attempts):
            raise ValueError(
                "physical attempts cannot duplicate an LLM response payload"
            )
        if Path(self.run_ref).name != self.child_run_id:
            raise ValueError("run_ref must identify the exact child_run_id")
        expected_observation_id = (
            f"{self.plan_id}:rep:{self.repetition:03d}:"
            f"{self.context_id}:{self.agent_name}"
        )
        if self.observation_id != expected_observation_id:
            raise ValueError("observation_id does not match its declared identity")
        if self.outcome != "error":
            if self.decision_id != (
                f"{self.child_run_id}:{self.agent_name}:001"
            ):
                raise ValueError("decision_id does not bind child_run_id and agent")
            expected_outcome = _outcome_from_observation_trace(
                origin=self.generation_origin,
                validation_status=self.generation_validation_status,
                attempt_index=self.generation_attempt_index,
                physical_attempts=self.physical_attempts,
            )
            if self.outcome != expected_outcome:
                raise ValueError(
                    "observation outcome does not match generation/physical trace"
                )
            expected_physical_trace = _physical_trace_is_complete(
                origin=self.generation_origin,
                attempt_index=self.generation_attempt_index,
                physical_attempts=self.physical_attempts,
            )
            if self.checks.physical_trace_valid != expected_physical_trace:
                raise ValueError(
                    "physical_trace_valid does not match the observed calls"
                )
        elif self.checks.trace_valid or self.checks.physical_trace_valid:
            raise ValueError("error observations cannot declare a valid trace")
        return self


class MonitoringReviewReliabilityActionConsistency(StrictBaseModel):
    """Estabilidad descriptiva; nunca forma parte de los blockers."""

    context_id: str = Field(min_length=1)
    agent_name: AgentName
    observation_count: int = Field(ge=0)
    actions: tuple[MonitoringReviewRecommendedAction, ...] = ()
    modal_action: MonitoringReviewRecommendedAction | None = None
    agreement_rate: float = Field(ge=0.0, le=1.0)


class MonitoringReviewReliabilitySummary(StrictBaseModel):
    """Agregado global de las doce hijas y ochenta y cuatro roles esperados."""

    expected_repetition_count: int = Field(ge=0)
    expected_context_count: int = Field(ge=0)
    expected_child_run_count: int = Field(ge=0)
    expected_observation_count: int = Field(ge=0)
    observed_repetition_count: int = Field(ge=0)
    session_count: int = Field(ge=0)
    complete_repetition_count: int = Field(ge=0)
    complete_context_count: int = Field(ge=0)
    child_run_count: int = Field(ge=0)
    resolved_child_run_count: int = Field(ge=0)
    observation_count: int = Field(ge=0)
    first_pass_count: int = Field(ge=0)
    repaired_count: int = Field(ge=0)
    physical_call_count: int = Field(ge=0)
    unique_physical_call_index_count: int = Field(ge=0)
    physical_json_repair_call_count: int = Field(ge=0)
    fallback_count: int = Field(ge=0)
    non_agentic_count: int = Field(ge=0)
    error_count: int = Field(ge=0)
    llm_origin_rate: float = Field(ge=0.0, le=1.0)
    first_pass_rate: float = Field(ge=0.0, le=1.0)
    trace_coverage_rate: float = Field(ge=0.0, le=1.0)
    physical_trace_rate: float = Field(ge=0.0, le=1.0)
    binding_rate: float = Field(ge=0.0, le=1.0)
    grounding_rate: float = Field(ge=0.0, le=1.0)
    hypothesis_structural_rate: float = Field(ge=0.0, le=1.0)
    claims_scoped_rate: float = Field(ge=0.0, le=1.0)
    action_catalog_rate: float = Field(ge=0.0, le=1.0)
    memory_off_rate: float = Field(ge=0.0, le=1.0)
    policy_not_applied_rate: float = Field(ge=0.0, le=1.0)
    action_consistency: tuple[MonitoringReviewReliabilityActionConsistency, ...] = ()


class MonitoringReviewReliabilityGate(StrictBaseModel):
    """Dictamen bloqueante anterior a cualquier ablacion RAG."""

    verdict: MonitoringReviewReliabilityVerdict
    blockers: tuple[str, ...] = ()
    detail: str = Field(min_length=1)


class MonitoringReviewReliabilityManifest(StrictBaseModel):
    """Identidad de plan, modelo y contratos sin persistir el host de Ollama."""

    schema_version: Literal["monitoring_review_reliability_manifest_v1"] = (
        "monitoring_review_reliability_manifest_v1"
    )
    protocol_id: Literal["monitoring_review_reliability_v1"] = (
        MONITORING_REVIEW_RELIABILITY_PROTOCOL_ID
    )
    plan_id: str = Field(min_length=1)
    plan_path: str = Field(min_length=1)
    plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preregistration_path: str = Field(min_length=1)
    preregistration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    preregistered_at: AwareDatetime
    llm_config: AgentReliabilityModelConfig
    model_digest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    contract_fingerprints: dict[str, str]
    source_sha256s: dict[str, str]
    memory_enabled: Literal[False] = False
    policy_application_enabled: Literal[False] = False
    started_at: AwareDatetime
    completed_at: AwareDatetime
    trace_limitation: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_temporal_order(self) -> "MonitoringReviewReliabilityManifest":
        if self.preregistered_at > self.started_at:
            raise ValueError("plan must be preregistered before execution starts")
        if self.completed_at < self.started_at:
            raise ValueError("completed_at cannot precede started_at")
        return self


class MonitoringReviewReliabilityResult(StrictBaseModel):
    """Resultado autocontenido del gate, sin copiar decisiones de las runs."""

    manifest: MonitoringReviewReliabilityManifest
    plan: MonitoringReviewReliabilityPlan
    observations: tuple[MonitoringReviewReliabilityObservation, ...]
    summary: MonitoringReviewReliabilitySummary
    gate: MonitoringReviewReliabilityGate


class MonitoringReviewReliabilityArtifacts(StrictBaseModel):
    """Rutas de la evidencia separada de las runs hijas."""

    output_dir: str = Field(min_length=1)
    plan_path: str = Field(min_length=1)
    preregistration_path: str = Field(min_length=1)
    manifest_path: str = Field(min_length=1)
    observations_path: str = Field(min_length=1)
    summary_path: str = Field(min_length=1)
    report_path: str = Field(min_length=1)


def default_monitoring_review_reliability_plan(
    *,
    plan_id: str = DEFAULT_MONITORING_REVIEW_RELIABILITY_PLAN_ID,
    minimum_first_pass_rate: float = 0.90,
) -> MonitoringReviewReliabilityPlan:
    """Devuelve el pack NASA P3 exacto de 3 x 4 x 7 observaciones."""

    return MonitoringReviewReliabilityPlan(
        plan_id=plan_id,
        acceptance=MonitoringReviewReliabilityAcceptancePolicy(
            minimum_first_pass_rate=minimum_first_pass_rate,
        ),
    )


def preregister_monitoring_review_reliability_plan(
    plan: MonitoringReviewReliabilityPlan,
    *,
    output_root: Path | str = DEFAULT_MONITORING_REVIEW_RELIABILITY_OUTPUT_DIR,
) -> MonitoringReviewReliabilityPreregistration:
    """Escribe ``plan.json`` de forma atomica e inmutable antes de ejecutar.

    Repetir el registro con bytes semanticamente identicos es idempotente. Un
    plan diferente bajo el mismo ``plan_id`` se rechaza para impedir seleccionar
    contextos o criterios despues de observar respuestas del modelo.
    """

    _ensure_plain_name(plan.plan_id)
    destination = (Path(output_root) / plan.plan_id).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    path = destination / "plan.json"
    registration_path = destination / "preregistration.json"
    payload = plan.model_dump(mode="json")
    plan_sha256 = _json_sha256(payload)
    lock_path = destination / ".plan.lock"
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        if path.exists():
            persisted = MonitoringReviewReliabilityPlan.model_validate(
                _read_json(path)
            )
            if _json_sha256(persisted.model_dump(mode="json")) != plan_sha256:
                raise ValueError(
                    "monitoring review reliability plan idempotency conflict"
                )
        else:
            _write_json_atomic(path, payload)
        if registration_path.exists():
            registration = MonitoringReviewReliabilityPreregistration.model_validate(
                _read_json(registration_path)
            )
            if (
                registration.plan_id != plan.plan_id
                or Path(registration.plan_path).resolve() != path
                or registration.plan_sha256 != plan_sha256
                or Path(registration.registration_path).resolve()
                != registration_path
            ):
                raise ValueError(
                    "monitoring review preregistration binding conflict"
                )
        else:
            registration_payload: dict[str, Any] = {
                "schema_version": (
                    "monitoring_review_reliability_preregistration_v1"
                ),
                "plan_id": plan.plan_id,
                "plan_path": path.as_posix(),
                "plan_sha256": plan_sha256,
                "registration_path": registration_path.as_posix(),
                "registered_at": datetime.now(UTC),
            }
            draft = MonitoringReviewReliabilityPreregistration.model_construct(
                registration_sha256="0" * 64,
                **registration_payload,
            )
            registration_payload["registration_sha256"] = _json_sha256(
                draft.model_dump(
                    mode="json",
                    exclude={"registration_sha256"},
                )
            )
            registration = (
                MonitoringReviewReliabilityPreregistration.model_validate(
                    registration_payload
                )
            )
            _write_json_atomic(
                registration_path,
                registration.model_dump(mode="json"),
            )
    return registration


def observe_monitoring_review_result(
    plan: MonitoringReviewReliabilityPlan,
    *,
    repetition: int,
    context_id: str,
    trigger: MonitoringTriggerEvent,
    causal_view: CausalInputView,
    evidence_catalog: CausalEvidenceCatalog | None = None,
    request: MonitoringReviewRequest,
    result: MonitoringReviewResult,
    child_lifecycle_status: MonitoringChildRunStatus,
    run_ref: str | None = None,
    physical_attempts_by_role: Mapping[
        AgentName, Sequence[AgentReliabilityAttempt]
    ]
    | None = None,
) -> tuple[MonitoringReviewReliabilityObservation, ...]:
    """Proyecta una run sellada a siete observaciones sin copiar su narrativa."""

    if repetition < 1 or repetition > plan.repetitions:
        raise ValueError("repetition is outside the preregistered plan")
    expected = next(
        (item for item in plan.expected_contexts if item.context_id == context_id),
        None,
    )
    if expected is None:
        raise ValueError(f"unknown preregistered context_id: {context_id}")

    actual_run_ref = run_ref or (
        Path("codigo/reports/runs") / request.child_run_id
    ).as_posix()
    physical_by_role = physical_attempts_by_role or {}
    common_binding, common_details = _common_binding_check(
        plan=plan,
        expected=expected,
        trigger=trigger,
        causal_view=causal_view,
        request=request,
        result=result,
    )
    observations: list[MonitoringReviewReliabilityObservation] = []
    for role_result in result.role_results:
        role = role_result.agent_name
        decision = role_result.decision
        physical_attempts = tuple(physical_by_role.get(role, ()))
        if decision is None:
            observations.append(
                _error_observation(
                    plan=plan,
                    repetition=repetition,
                    expected=expected,
                    trigger=trigger,
                    request=request,
                    result=result,
                    child_lifecycle_status=child_lifecycle_status,
                    run_ref=actual_run_ref,
                    agent_name=role,
                    physical_attempts=physical_attempts,
                    error_type="MonitoringReviewRoleMissingDecision",
                    error_message=(
                        role_result.failure_reason
                        or f"role status {role_result.status} has no decision"
                    ),
                    common_binding=common_binding,
                    common_details=common_details,
                )
            )
            continue

        checks = _role_checks(
            expected=expected,
            trigger=trigger,
            causal_view=causal_view,
            evidence_catalog=evidence_catalog,
            request=request,
            result=result,
            decision=decision,
            physical_attempts=physical_attempts,
            common_binding=common_binding,
            common_details=common_details,
        )
        trace = decision.generation_trace
        outcome = _decision_outcome(decision, physical_attempts)
        observations.append(
            MonitoringReviewReliabilityObservation(
                observation_id=(
                    f"{plan.plan_id}:rep:{repetition:03d}:"
                    f"{expected.context_id}:{role}"
                ),
                plan_id=plan.plan_id,
                repetition=repetition,
                context_id=expected.context_id,
                context_ordinal=expected.ordinal,
                trigger_type=trigger.trigger_type,
                reason_code=trigger.reason_code,
                condition_start_cursor=int(trigger.condition_start_cursor or 0),
                cutoff_cursor=int(trigger.cutoff_cursor or 0),
                session_id=request.session_id,
                trigger_id=request.trigger_id,
                trigger_event_id=request.trigger_event_id,
                child_run_id=request.child_run_id,
                run_ref=actual_run_ref,
                request_sha256=request.request_sha256,
                result_sha256=result.result_sha256,
                causal_view_sha256=causal_view.view_sha256,
                child_lifecycle_status=child_lifecycle_status,
                review_status=result.status,
                agent_name=role,
                outcome=outcome,
                decision_id=decision.decision_id,
                decision_sha256=decision.decision_sha256,
                generation_origin=trace.origin,
                generation_validation_status=trace.validation_status,
                generation_attempt_index=trace.attempt_index,
                hypothesis_kind=decision.hypothesis.kind,
                hypothesis_sha256=_json_sha256(
                    decision.hypothesis.model_dump(mode="json")
                ),
                recommended_action=decision.recommended_action,
                evidence_refs=decision.evidence_refs,
                physical_attempts=physical_attempts,
                checks=checks,
            )
        )
    return tuple(observations)


def monitoring_review_error_observations(
    plan: MonitoringReviewReliabilityPlan,
    *,
    repetition: int,
    context_id: str,
    session_id: str,
    trigger_id: str,
    trigger_event_id: str,
    child_run_id: str,
    request_sha256: str,
    causal_view_sha256: str,
    trigger_type: MonitoringTriggerType,
    reason_code: MonitoringTriggerReasonCode,
    condition_start_cursor: int,
    cutoff_cursor: int,
    child_lifecycle_status: MonitoringChildRunStatus,
    error: Exception | str,
    run_ref: str | None = None,
) -> tuple[MonitoringReviewReliabilityObservation, ...]:
    """Representa una hija sin resultado mediante siete errores explicitos."""

    expected = next(
        (item for item in plan.expected_contexts if item.context_id == context_id),
        None,
    )
    if expected is None:
        raise ValueError(f"unknown preregistered context_id: {context_id}")
    if repetition < 1 or repetition > plan.repetitions:
        raise ValueError("repetition is outside the preregistered plan")
    message = str(error)
    error_type = type(error).__name__ if isinstance(error, Exception) else "ExecutionError"
    actual_run_ref = run_ref or (
        Path("codigo/reports/runs") / child_run_id
    ).as_posix()
    context_binding = (
        trigger_type == expected.trigger_type
        and reason_code == expected.reason_code
        and condition_start_cursor == expected.condition_start_cursor
        and cutoff_cursor == expected.cutoff_cursor
    )
    details = () if context_binding else ("trigger does not match expected context",)
    return tuple(
        MonitoringReviewReliabilityObservation(
            observation_id=(
                f"{plan.plan_id}:rep:{repetition:03d}:"
                f"{expected.context_id}:{role}"
            ),
            plan_id=plan.plan_id,
            repetition=repetition,
            context_id=expected.context_id,
            context_ordinal=expected.ordinal,
            trigger_type=trigger_type,
            reason_code=reason_code,
            condition_start_cursor=condition_start_cursor,
            cutoff_cursor=cutoff_cursor,
            session_id=session_id,
            trigger_id=trigger_id,
            trigger_event_id=trigger_event_id,
            child_run_id=child_run_id,
            run_ref=actual_run_ref,
            request_sha256=request_sha256,
            causal_view_sha256=causal_view_sha256,
            child_lifecycle_status=child_lifecycle_status,
            agent_name=role,
            outcome="error",
            checks=MonitoringReviewReliabilityRoleChecks(
                trace_valid=False,
                physical_trace_valid=False,
                binding_valid=context_binding,
                grounding_valid=False,
                hypothesis_structural_valid=False,
                claims_scoped=False,
                action_catalog_valid=False,
                memory_mode_valid=False,
                policy_application_valid=False,
                details=details,
            ),
            error_type=error_type,
            error_message=message or "monitoring review execution failed",
        )
        for role in plan.expected_roles
    )


def summarize_monitoring_review_reliability(
    plan: MonitoringReviewReliabilityPlan,
    observations: Sequence[MonitoringReviewReliabilityObservation],
) -> MonitoringReviewReliabilitySummary:
    """Agrega completitud y checks; una repair no se cuenta como first-pass."""

    items = list(observations)
    expected_roles = set(plan.expected_roles)
    contexts: dict[tuple[int, str], list[MonitoringReviewReliabilityObservation]] = (
        defaultdict(list)
    )
    repetitions: dict[int, list[MonitoringReviewReliabilityObservation]] = (
        defaultdict(list)
    )
    children: dict[str, list[MonitoringReviewReliabilityObservation]] = defaultdict(list)
    for item in items:
        contexts[(item.repetition, item.context_id)].append(item)
        repetitions[item.repetition].append(item)
        children[item.child_run_id].append(item)

    complete_context_keys: set[tuple[int, str]] = set()
    for key, context_items in contexts.items():
        repetition, context_id = key
        expected_context = next(
            (
                context
                for context in plan.expected_contexts
                if context.context_id == context_id
            ),
            None,
        )
        if (
            repetition in range(1, plan.repetitions + 1)
            and expected_context is not None
            and len(context_items) == len(plan.expected_roles)
            and {item.agent_name for item in context_items} == expected_roles
            and len({item.child_run_id for item in context_items}) == 1
            and len({item.session_id for item in context_items}) == 1
            and len({item.trigger_id for item in context_items}) == 1
            and len({item.trigger_event_id for item in context_items}) == 1
            and len({item.request_sha256 for item in context_items}) == 1
            and len({item.result_sha256 for item in context_items}) == 1
            and len({item.causal_view_sha256 for item in context_items}) == 1
            and all(
                item.context_ordinal == expected_context.ordinal
                and item.trigger_type == expected_context.trigger_type
                and item.reason_code == expected_context.reason_code
                and item.condition_start_cursor
                == expected_context.condition_start_cursor
                and item.cutoff_cursor == expected_context.cutoff_cursor
                and item.observation_id
                == (
                    f"{plan.plan_id}:rep:{repetition:03d}:"
                    f"{expected_context.context_id}:{item.agent_name}"
                )
                for item in context_items
            )
        ):
            complete_context_keys.add(key)

    complete_repetitions = 0
    for repetition in range(1, plan.repetitions + 1):
        expected_keys = {
            (repetition, context.context_id) for context in plan.expected_contexts
        }
        repetition_items = repetitions.get(repetition, [])
        if (
            expected_keys.issubset(complete_context_keys)
            and len(repetition_items) == (
                len(plan.expected_contexts) * len(plan.expected_roles)
            )
            and len({item.session_id for item in repetition_items}) == 1
            and len({item.trigger_id for item in repetition_items})
            == len(plan.expected_contexts)
            and len({item.trigger_event_id for item in repetition_items})
            == len(plan.expected_contexts)
            and len({item.child_run_id for item in repetition_items})
            == len(plan.expected_contexts)
        ):
            complete_repetitions += 1

    resolved_children = sum(
        bool(child_items)
        and len(child_items) == len(plan.expected_roles)
        and all(
            item.child_lifecycle_status == "resolved"
            and item.review_status == "completed"
            for item in child_items
        )
        for child_items in children.values()
    )
    count = len(items)
    first_pass_count = _count_outcome(items, "first_pass")
    repaired_count = _count_outcome(items, "llm_repaired")
    return MonitoringReviewReliabilitySummary(
        expected_repetition_count=plan.repetitions,
        expected_context_count=len(plan.expected_contexts),
        expected_child_run_count=plan.expected_child_run_count,
        expected_observation_count=plan.expected_observation_count,
        observed_repetition_count=len(repetitions),
        session_count=len({item.session_id for item in items}),
        complete_repetition_count=complete_repetitions,
        complete_context_count=len(complete_context_keys),
        child_run_count=len(children),
        resolved_child_run_count=resolved_children,
        observation_count=count,
        first_pass_count=first_pass_count,
        repaired_count=repaired_count,
        physical_call_count=sum(len(item.physical_attempts) for item in items),
        unique_physical_call_index_count=len(
            {
                attempt.attempt_index
                for item in items
                for attempt in item.physical_attempts
            }
        ),
        physical_json_repair_call_count=sum(
            attempt.kind == "json_repair"
            for item in items
            for attempt in item.physical_attempts
        ),
        fallback_count=_count_outcome(items, "fallback"),
        non_agentic_count=_count_outcome(items, "non_agentic"),
        error_count=_count_outcome(items, "error"),
        llm_origin_rate=_rate(
            sum(item.generation_origin == "llm" for item in items), count
        ),
        first_pass_rate=_rate(first_pass_count, count),
        trace_coverage_rate=_check_rate(items, "trace_valid"),
        physical_trace_rate=_check_rate(items, "physical_trace_valid"),
        binding_rate=_check_rate(items, "binding_valid"),
        grounding_rate=_check_rate(items, "grounding_valid"),
        hypothesis_structural_rate=_check_rate(
            items, "hypothesis_structural_valid"
        ),
        claims_scoped_rate=_check_rate(items, "claims_scoped"),
        action_catalog_rate=_check_rate(items, "action_catalog_valid"),
        memory_off_rate=_check_rate(items, "memory_mode_valid"),
        policy_not_applied_rate=_check_rate(
            items, "policy_application_valid"
        ),
        action_consistency=_action_consistency(plan, items),
    )


def assess_monitoring_review_reliability_gate(
    plan: MonitoringReviewReliabilityPlan,
    summary: MonitoringReviewReliabilitySummary,
) -> MonitoringReviewReliabilityGate:
    """Bloquea huecos, fallbacks, claims fisicos y cualquier enlace invalido."""

    policy = plan.acceptance
    blockers: list[str] = []
    exact_counts = (
        ("observation_count", summary.observation_count, plan.expected_observation_count),
        ("child_run_count", summary.child_run_count, plan.expected_child_run_count),
        ("session_count", summary.session_count, plan.repetitions),
        (
            "complete_context_count",
            summary.complete_context_count,
            plan.expected_child_run_count,
        ),
        (
            "complete_repetition_count",
            summary.complete_repetition_count,
            plan.repetitions,
        ),
        (
            "resolved_child_run_count",
            summary.resolved_child_run_count,
            plan.expected_child_run_count,
        ),
    )
    for name, observed, expected in exact_counts:
        if observed != expected:
            blockers.append(f"{name}:{observed}!={expected}")
    if summary.unique_physical_call_index_count != summary.physical_call_count:
        blockers.append(
            "unique_physical_call_index_count:"
            f"{summary.unique_physical_call_index_count}!="
            f"{summary.physical_call_count}"
        )

    zero_counts = (
        ("fallback_count", summary.fallback_count),
        ("non_agentic_count", summary.non_agentic_count),
        ("error_count", summary.error_count),
        (
            "physical_json_repair_call_count",
            summary.physical_json_repair_call_count,
        ),
    )
    for name, observed in zero_counts:
        if observed:
            blockers.append(f"{name}:{observed}")

    required_rates = (
        ("llm_origin_rate", summary.llm_origin_rate, policy.require_llm_origin_rate),
        (
            "trace_coverage_rate",
            summary.trace_coverage_rate,
            policy.require_trace_coverage_rate,
        ),
        (
            "physical_trace_rate",
            summary.physical_trace_rate,
            policy.require_physical_trace_rate,
        ),
        ("binding_rate", summary.binding_rate, policy.require_binding_rate),
        ("grounding_rate", summary.grounding_rate, policy.require_grounding_rate),
        (
            "hypothesis_structural_rate",
            summary.hypothesis_structural_rate,
            policy.require_hypothesis_structural_rate,
        ),
        (
            "claims_scoped_rate",
            summary.claims_scoped_rate,
            policy.require_claims_scoped_rate,
        ),
        (
            "action_catalog_rate",
            summary.action_catalog_rate,
            policy.require_action_catalog_rate,
        ),
        ("memory_off_rate", summary.memory_off_rate, policy.require_memory_off_rate),
        (
            "policy_not_applied_rate",
            summary.policy_not_applied_rate,
            policy.require_policy_not_applied_rate,
        ),
    )
    for name, observed, required in required_rates:
        if observed < required:
            blockers.append(f"{name}:{observed:.6f}<{required:.6f}")
    if summary.first_pass_rate < policy.minimum_first_pass_rate:
        blockers.append(
            "first_pass_rate:"
            f"{summary.first_pass_rate:.6f}<"
            f"{policy.minimum_first_pass_rate:.6f}"
        )

    if blockers:
        return MonitoringReviewReliabilityGate(
            verdict="blocked",
            blockers=tuple(blockers),
            detail=(
                "La bateria trigger-agentes no supera el gate; no autoriza una "
                "ablacion RAG ni confirma hipotesis fisicas."
            ),
        )
    return MonitoringReviewReliabilityGate(
        verdict="passed",
        blockers=(),
        detail=(
            "Las doce revisiones conservaron los siete roles en LLM, con "
            "grounding y alcance estructural completos. El dictamen no valida "
            "la verdad de las hipotesis."
        ),
    )


def build_monitoring_review_reliability_result(
    plan: MonitoringReviewReliabilityPlan,
    observations: Sequence[MonitoringReviewReliabilityObservation],
    *,
    preregistration: MonitoringReviewReliabilityPreregistration,
    llm_config: AgentReliabilityModelConfig,
    started_at: datetime,
    completed_at: datetime,
) -> MonitoringReviewReliabilityResult:
    """Cierra manifiesto, resumen y gate contra el plan ya prerregistrado."""

    _validate_preregistration(plan, preregistration)
    if llm_config != plan.llm_config:
        raise ValueError("runtime llm_config differs from the preregistered plan")
    if monitoring_review_contract_fingerprints() != plan.contract_fingerprints:
        raise ValueError("monitoring review contracts changed after preregistration")
    if _source_sha256s() != plan.source_sha256s:
        raise ValueError("reliability source files changed after preregistration")
    if any(item.plan_id != plan.plan_id for item in observations):
        raise ValueError("all observations must reference the preregistered plan")
    summary = summarize_monitoring_review_reliability(plan, observations)
    gate = assess_monitoring_review_reliability_gate(plan, summary)
    manifest = MonitoringReviewReliabilityManifest(
        plan_id=plan.plan_id,
        plan_path=preregistration.plan_path,
        plan_sha256=preregistration.plan_sha256,
        preregistration_path=preregistration.registration_path,
        preregistration_sha256=preregistration.registration_sha256,
        preregistered_at=preregistration.registered_at,
        llm_config=plan.llm_config,
        model_digest_sha256=plan.model_digest_sha256,
        contract_fingerprints=plan.contract_fingerprints,
        source_sha256s=plan.source_sha256s,
        started_at=started_at,
        completed_at=completed_at,
        trace_limitation=(
            "generation_trace mide el intento contractual efectivo y cada rol "
            "debe enlazar todas sus llamadas fisicas observadas. El plan fija "
            "max_json_repair_attempts=0: cualquier repair interno bloquea el "
            "gate. Ningun check confirma la verdad fisica de una hipotesis."
        ),
    )
    return MonitoringReviewReliabilityResult(
        manifest=manifest,
        plan=plan,
        observations=tuple(observations),
        summary=summary,
        gate=gate,
    )


def write_monitoring_review_reliability_artifacts(
    result: MonitoringReviewReliabilityResult,
    *,
    output_root: Path | str = DEFAULT_MONITORING_REVIEW_RELIABILITY_OUTPUT_DIR,
) -> MonitoringReviewReliabilityArtifacts:
    """Persiste manifiesto, observaciones, resumen e informe de forma atomica."""

    _ensure_plain_name(result.plan.plan_id)
    destination = Path(output_root) / result.plan.plan_id
    destination.mkdir(parents=True, exist_ok=True)
    plan_path = destination / "plan.json"
    if Path(result.manifest.plan_path).resolve() != plan_path.resolve():
        raise ValueError("result manifest does not reference this output plan")
    persisted_plan = MonitoringReviewReliabilityPlan.model_validate(
        _read_json(plan_path)
    )
    preregistration_path = destination / "preregistration.json"
    if (
        Path(result.manifest.preregistration_path).resolve()
        != preregistration_path.resolve()
    ):
        raise ValueError("result manifest does not reference this preregistration")
    persisted_preregistration = (
        MonitoringReviewReliabilityPreregistration.model_validate(
            _read_json(preregistration_path)
        )
    )
    persisted_plan_sha = _json_sha256(persisted_plan.model_dump(mode="json"))
    if (
        persisted_plan != result.plan
        or persisted_plan_sha != result.manifest.plan_sha256
        or persisted_preregistration.plan_sha256
        != result.manifest.plan_sha256
        or persisted_preregistration.registration_sha256
        != result.manifest.preregistration_sha256
    ):
        raise ValueError("persisted preregistered plan does not match result")

    manifest_path = destination / "manifest.json"
    observations_path = destination / "observations.jsonl"
    summary_path = destination / "summary.json"
    report_path = destination / "report.md"
    _write_immutable_json(manifest_path, result.manifest.model_dump(mode="json"))
    _write_immutable_text(
        observations_path,
        "".join(
            json.dumps(
                item.model_dump(mode="json"),
                ensure_ascii=True,
                sort_keys=True,
            )
            + "\n"
            for item in result.observations
        ),
    )
    _write_immutable_json(
        summary_path,
        {
            "summary": result.summary.model_dump(mode="json"),
            "gate": result.gate.model_dump(mode="json"),
        },
    )
    _write_immutable_text(report_path, _render_report(result))
    return MonitoringReviewReliabilityArtifacts(
        output_dir=destination.as_posix(),
        plan_path=plan_path.as_posix(),
        preregistration_path=preregistration_path.as_posix(),
        manifest_path=manifest_path.as_posix(),
        observations_path=observations_path.as_posix(),
        summary_path=summary_path.as_posix(),
        report_path=report_path.as_posix(),
    )


class MonitoringReviewReliabilityPublication(StrictBaseModel):
    """Puntero explicito y hasheado al resultado publicado actualmente."""

    schema_version: Literal["monitoring_review_reliability_current_v1"] = (
        "monitoring_review_reliability_current_v1"
    )
    protocol_id: Literal["monitoring_review_reliability_v1"] = (
        MONITORING_REVIEW_RELIABILITY_PROTOCOL_ID
    )
    publication_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    plan_id: str = Field(min_length=1)
    result_ref: str = Field(min_length=1)
    result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    artifact_sha256s: dict[str, str]
    published_at: AwareDatetime

    @model_validator(mode="after")
    def validate_publication_hash(self) -> "MonitoringReviewReliabilityPublication":
        expected = _json_sha256(
            self.model_dump(mode="json", exclude={"publication_sha256"})
        )
        if self.publication_sha256 != expected:
            raise ValueError("publication_sha256 does not match current pointer")
        return self


def publish_monitoring_review_reliability(
    result: MonitoringReviewReliabilityResult,
    artifacts: MonitoringReviewReliabilityArtifacts,
    *,
    output_root: Path | str = DEFAULT_MONITORING_REVIEW_RELIABILITY_OUTPUT_DIR,
) -> MonitoringReviewReliabilityPublication:
    """Publica ``current.json``; nunca selecciona el resultado por mtime."""

    root = Path(output_root).resolve()
    destination = (root / result.plan.plan_id).resolve()
    if Path(artifacts.output_dir).resolve() != destination:
        raise ValueError("artifacts do not belong to the result plan directory")
    artifact_paths = {
        "plan": Path(artifacts.plan_path),
        "preregistration": Path(artifacts.preregistration_path),
        "manifest": Path(artifacts.manifest_path),
        "observations": Path(artifacts.observations_path),
        "summary": Path(artifacts.summary_path),
        "report": Path(artifacts.report_path),
    }
    for path in artifact_paths.values():
        _require_contained(root, path.resolve())
        if not path.is_file():
            raise FileNotFoundError(f"reliability artifact not found: {path}")
    _validate_artifacts_for_result(result, artifact_paths)

    result_path = destination / "result.json"
    result_payload = result.model_dump(mode="json")
    _write_immutable_json(result_path, result_payload)
    result_sha256 = _file_sha256(result_path)
    artifact_sha256s = {
        path.resolve().relative_to(root).as_posix(): _file_sha256(path)
        for path in artifact_paths.values()
    }
    payload: dict[str, Any] = {
        "schema_version": "monitoring_review_reliability_current_v1",
        "protocol_id": MONITORING_REVIEW_RELIABILITY_PROTOCOL_ID,
        "plan_id": result.plan.plan_id,
        "result_ref": result_path.relative_to(root).as_posix(),
        "result_sha256": result_sha256,
        "artifact_sha256s": artifact_sha256s,
        "published_at": datetime.now(UTC),
    }
    draft = MonitoringReviewReliabilityPublication.model_construct(
        publication_sha256="0" * 64,
        **payload,
    )
    payload["publication_sha256"] = _json_sha256(
        draft.model_dump(mode="json", exclude={"publication_sha256"})
    )
    publication = MonitoringReviewReliabilityPublication.model_validate(payload)
    root.mkdir(parents=True, exist_ok=True)
    lock_path = root / ".current.lock"
    with lock_path.open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        _write_json_atomic(root / "current.json", publication.model_dump(mode="json"))
    return publication


def load_published_monitoring_review_reliability(
    *,
    output_root: Path | str = DEFAULT_MONITORING_REVIEW_RELIABILITY_OUTPUT_DIR,
) -> MonitoringReviewReliabilityResult:
    """Carga exclusivamente el puntero ``current.json`` y verifica todos sus hashes."""

    root = Path(output_root).resolve()
    publication = MonitoringReviewReliabilityPublication.model_validate(
        _read_json(root / "current.json")
    )
    result_path = _require_contained(root, (root / publication.result_ref).resolve())
    if _file_sha256(result_path) != publication.result_sha256:
        raise ValueError("published reliability result SHA-256 changed")
    for relative_ref, expected_sha in publication.artifact_sha256s.items():
        path = _require_contained(root, (root / relative_ref).resolve())
        if _file_sha256(path) != expected_sha:
            raise ValueError(f"published reliability artifact changed: {relative_ref}")
    result = MonitoringReviewReliabilityResult.model_validate(_read_json(result_path))
    if result.plan.plan_id != publication.plan_id:
        raise ValueError("published reliability pointer/result plan mismatch")
    return result


def _common_binding_check(
    *,
    plan: MonitoringReviewReliabilityPlan,
    expected: MonitoringReviewReliabilityExpectedContext,
    trigger: MonitoringTriggerEvent,
    causal_view: CausalInputView,
    request: MonitoringReviewRequest,
    result: MonitoringReviewResult,
) -> tuple[bool, tuple[str, ...]]:
    checks = {
        "expected_trigger_context": (
            trigger.trigger_type == expected.trigger_type
            and trigger.reason_code == expected.reason_code
            and trigger.condition_start_cursor == expected.condition_start_cursor
            and trigger.cutoff_cursor == expected.cutoff_cursor
        ),
        "primary_emitted_trigger": (
            trigger.lifecycle_status == "emitted"
            and trigger.suppression_reason is None
            and trigger.coalesced_into_trigger_id is None
            and trigger.requested_roles == MONITORING_REVIEW_ROLES
        ),
        "trigger_view_binding": (
            trigger.session_id == causal_view.session_id
            and trigger.trigger_id == causal_view.trigger_id
            and trigger.event_id == causal_view.trigger_event_id
            and trigger.origin_tick_id == causal_view.origin_tick_id
            and trigger.cutoff_cursor == causal_view.cursor
            and trigger.cutoff_source_time == causal_view.cutoff_source_time
        ),
        "request_view_binding": (
            request.session_id == causal_view.session_id
            and request.trigger_id == causal_view.trigger_id
            and request.trigger_event_id == causal_view.trigger_event_id
            and request.origin_tick_id == causal_view.origin_tick_id
            and request.cutoff_snapshot_id == causal_view.cutoff_snapshot_id
            and request.cutoff_cursor == causal_view.cursor
            and request.cutoff_source_time == causal_view.cutoff_source_time
            and request.active_policy_refs == causal_view.active_policy_refs
            and request.causal_view_sha256 == causal_view.view_sha256
        ),
        "request_contract_binding": all(
            getattr(request, key) == value
            for key, value in plan.contract_fingerprints.items()
        ),
        "result_request_binding": (
            result.request_id == request.request_id
            and result.request_sha256 == request.request_sha256
            and result.child_run_id == request.child_run_id
            and result.session_id == request.session_id
            and result.trigger_id == request.trigger_id
            and result.trigger_event_id == request.trigger_event_id
            and result.origin_tick_id == request.origin_tick_id
            and result.cutoff_snapshot_id == request.cutoff_snapshot_id
            and result.cutoff_cursor == request.cutoff_cursor
            and result.cutoff_source_time == request.cutoff_source_time
            and result.active_policy_refs == request.active_policy_refs
            and result.causal_view_ref == request.causal_view_ref
            and result.causal_view_sha256 == request.causal_view_sha256
        ),
        "canonical_hashes": (
            CausalInputView.canonical_sha256(causal_view) == causal_view.view_sha256
            and MonitoringReviewRequest.canonical_sha256(request)
            == request.request_sha256
            and MonitoringReviewResult.canonical_sha256(result)
            == result.result_sha256
        ),
    }
    failed = tuple(name for name, passed in checks.items() if not passed)
    return not failed, failed


def _role_checks(
    *,
    expected: MonitoringReviewReliabilityExpectedContext,
    trigger: MonitoringTriggerEvent,
    causal_view: CausalInputView,
    evidence_catalog: CausalEvidenceCatalog | None,
    request: MonitoringReviewRequest,
    result: MonitoringReviewResult,
    decision: MonitoringReviewDecision,
    physical_attempts: Sequence[AgentReliabilityAttempt],
    common_binding: bool,
    common_details: tuple[str, ...],
) -> MonitoringReviewReliabilityRoleChecks:
    del expected, trigger
    trace = decision.generation_trace
    trace_valid = (
        trace.attempt_id
        == type(trace).attempt_id_for(decision.decision_id, trace.attempt_index)
        and (
            trace.fallback_from_attempt_id is None
            or trace.fallback_from_attempt_id.startswith(f"{decision.decision_id}:")
        )
    )
    physical_trace_valid = _physical_trace_is_complete(
        origin=trace.origin,
        attempt_index=trace.attempt_index,
        physical_attempts=physical_attempts,
    )
    role_binding = (
        decision.child_run_id == result.child_run_id == request.child_run_id
        and decision.trigger_event_id == request.trigger_event_id
        and decision.cutoff_snapshot_id == request.cutoff_snapshot_id
        and decision.cutoff_cursor == request.cutoff_cursor
        and decision.cutoff_source_time == request.cutoff_source_time
        and decision.causal_view_sha256 == causal_view.view_sha256
        and MonitoringReviewDecision.canonical_sha256(decision)
        == decision.decision_sha256
    )
    binding_valid = common_binding and role_binding

    if evidence_catalog is None:
        allowed_refs = {item.evidence_id for item in causal_view.evidence}
        catalog_binding = True
    else:
        allowed_refs = {
            item.support_ref for item in evidence_catalog.entries
        }
        catalog_binding = (
            evidence_catalog.causal_view_sha256 == causal_view.view_sha256
            and evidence_catalog.causal_scope_refs
            == tuple(item.evidence_id for item in causal_view.evidence)
        )
    decision_refs = set(decision.evidence_refs)
    hypothesis_refs = set(decision.hypothesis.evidence_refs)
    grounding_valid = (
        catalog_binding
        and bool(decision_refs)
        and bool(hypothesis_refs)
        and decision_refs.issubset(allowed_refs)
        and tuple(decision.hypothesis.evidence_refs) == decision.evidence_refs
    )
    hypothesis = decision.hypothesis
    hypothesis_structural_valid = (
        hypothesis.kind == ROLE_HYPOTHESIS_KIND[decision.agent_name]
        and hypothesis.evidence_cutoff == request.cutoff_snapshot_id
        and all(
            bool(value.strip())
            for value in (
                hypothesis.statement,
                hypothesis.scope,
                hypothesis.expected_observation,
                hypothesis.falsification_criterion,
            )
        )
        and bool(hypothesis.evidence_refs)
        and bool(hypothesis.risk_notes)
    )
    claim_texts = [
        decision.rationale,
        decision.observation_summary,
        decision.action_rationale,
        hypothesis.statement,
        hypothesis.scope,
        hypothesis.expected_observation,
        hypothesis.falsification_criterion,
        *hypothesis.risk_notes,
        *hypothesis.assumptions,
    ]
    unsupported_claim_ids = tuple(_unsupported_monitoring_review_claims(claim_texts))
    claims_scoped = not unsupported_claim_ids
    action_catalog_valid = decision.recommended_action in ALLOWED_ACTIONS
    memory_mode_valid = (
        request.memory_mode == "off"
        and result.memory_mode == "off"
        and decision.memory_mode == "off"
    )
    policy_application_valid = (
        result.policy_application_status == "not_applied"
        and decision.policy_application_status == "not_applied"
    )
    details = list(common_details)
    if not role_binding:
        details.append("role_decision_binding")
    if not trace_valid:
        details.append("generation_trace")
    if not physical_trace_valid:
        details.append("physical_trace")
    if not grounding_valid:
        details.append("evidence_grounding")
    if not hypothesis_structural_valid:
        details.append("hypothesis_structure")
    if unsupported_claim_ids:
        details.append("unsupported_claims:" + ",".join(unsupported_claim_ids))
    if not action_catalog_valid:
        details.append("action_catalog")
    if not memory_mode_valid:
        details.append("memory_mode")
    if not policy_application_valid:
        details.append("policy_application")
    return MonitoringReviewReliabilityRoleChecks(
        trace_valid=trace_valid,
        physical_trace_valid=physical_trace_valid,
        binding_valid=binding_valid,
        grounding_valid=grounding_valid,
        hypothesis_structural_valid=hypothesis_structural_valid,
        claims_scoped=claims_scoped,
        action_catalog_valid=action_catalog_valid,
        memory_mode_valid=memory_mode_valid,
        policy_application_valid=policy_application_valid,
        unsupported_claim_ids=unsupported_claim_ids,
        details=tuple(details),
    )


def _decision_outcome(
    decision: MonitoringReviewDecision,
    physical_attempts: Sequence[AgentReliabilityAttempt],
) -> MonitoringReviewReliabilityOutcome:
    trace = decision.generation_trace
    return _outcome_from_observation_trace(
        origin=trace.origin,
        validation_status=trace.validation_status,
        attempt_index=trace.attempt_index,
        physical_attempts=physical_attempts,
    )


def _outcome_from_observation_trace(
    *,
    origin: DecisionGenerationOrigin | None,
    validation_status: DecisionValidationStatus | None,
    attempt_index: int | None,
    physical_attempts: Sequence[AgentReliabilityAttempt],
) -> MonitoringReviewReliabilityOutcome:
    if origin is None or validation_status is None or attempt_index is None:
        raise ValueError("a non-error outcome requires a complete generation trace")
    if origin == "guardrail_fallback":
        return "fallback"
    if origin != "llm":
        return "non_agentic"
    if (
        validation_status == "repaired"
        or attempt_index > 1
        or len(physical_attempts) > 1
        or any(item.kind == "json_repair" for item in physical_attempts)
    ):
        return "llm_repaired"
    return "first_pass"


def _physical_trace_is_complete(
    *,
    origin: DecisionGenerationOrigin,
    attempt_index: int,
    physical_attempts: Sequence[AgentReliabilityAttempt],
) -> bool:
    """Exige una llamada observada por intento contractual, sin repair oculto."""

    expected_count = (
        max(attempt_index - 1, 0)
        if origin == "guardrail_fallback"
        else attempt_index if origin == "llm" else 0
    )
    indexes = [item.attempt_index for item in physical_attempts]
    return (
        len(physical_attempts) == expected_count
        and len(indexes) == len(set(indexes))
        and indexes == sorted(indexes)
        and all(item.kind == "initial" for item in physical_attempts)
        and (
            origin != "llm"
            or all(item.status == "success" for item in physical_attempts)
        )
    )


def _unsupported_monitoring_review_claims(
    texts: Sequence[str],
) -> list[str]:
    """Reutiliza el guardarrail NASA y permite solo aprobacion interna explicita.

    Una revision puede decir que un *contrato* o *trigger* supero controles
    estructurales internos. Eso no equivale a aprobar una politica, diagnostico
    o resultado fisico. El resto de usos afirmativos de ``approved/aprobado``
    conserva el bloqueo del guardarrail canonico.
    """

    unsupported = unsupported_official_v2_claims(tuple(texts))
    if "approval_overclaim" not in unsupported:
        return unsupported
    normalized = _normalize_claim_text(". ".join(texts))
    approval_matches = tuple(
        re.finditer(r"\baprob(?:ada|ado)\b|\bapproved\b", normalized)
    )
    if approval_matches and all(
        _is_internal_structural_approval(normalized, match.start(), match.end())
        for match in approval_matches
    ):
        return [item for item in unsupported if item != "approval_overclaim"]
    return unsupported


def _is_internal_structural_approval(text: str, start: int, end: int) -> bool:
    boundaries_before = [text.rfind(mark, 0, start) for mark in ".;:!?" ]
    clause_start = max(boundaries_before) + 1
    boundaries_after = [
        position
        for mark in ".;:!?"
        if (position := text.find(mark, end)) >= 0
    ]
    clause_end = min(boundaries_after) if boundaries_after else len(text)
    clause = text[clause_start:clause_end]
    internal_scope = re.search(
        r"\b(?:contrato|contract|trigger|solicitud de revision|review request)\b",
        clause,
    ) and re.search(
        r"\b(?:intern[oa]s?|internal|estructural(?:es)?|structural)\b",
        clause,
    )
    forbidden_scope = re.search(
        r"\b(?:politica|policy|diagnostico|diagnosis|fisic[oa]|physical|"
        r"fallo|failure|degradacion|degradation|deteccion|detection)\b",
        clause,
    )
    return bool(internal_scope and not forbidden_scope)


def _normalize_claim_text(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return " ".join(
        "".join(
            character
            for character in decomposed
            if not unicodedata.combining(character)
        )
        .lower()
        .split()
    )


def _error_observation(
    *,
    plan: MonitoringReviewReliabilityPlan,
    repetition: int,
    expected: MonitoringReviewReliabilityExpectedContext,
    trigger: MonitoringTriggerEvent,
    request: MonitoringReviewRequest,
    result: MonitoringReviewResult,
    child_lifecycle_status: MonitoringChildRunStatus,
    run_ref: str,
    agent_name: AgentName,
    physical_attempts: tuple[AgentReliabilityAttempt, ...],
    error_type: str,
    error_message: str,
    common_binding: bool,
    common_details: tuple[str, ...],
) -> MonitoringReviewReliabilityObservation:
    return MonitoringReviewReliabilityObservation(
        observation_id=(
            f"{plan.plan_id}:rep:{repetition:03d}:{expected.context_id}:{agent_name}"
        ),
        plan_id=plan.plan_id,
        repetition=repetition,
        context_id=expected.context_id,
        context_ordinal=expected.ordinal,
        trigger_type=trigger.trigger_type,
        reason_code=trigger.reason_code,
        condition_start_cursor=int(trigger.condition_start_cursor or 0),
        cutoff_cursor=int(trigger.cutoff_cursor or 0),
        session_id=request.session_id,
        trigger_id=request.trigger_id,
        trigger_event_id=request.trigger_event_id,
        child_run_id=request.child_run_id,
        run_ref=run_ref,
        request_sha256=request.request_sha256,
        result_sha256=result.result_sha256,
        causal_view_sha256=request.causal_view_sha256,
        child_lifecycle_status=child_lifecycle_status,
        review_status=result.status,
        agent_name=agent_name,
        outcome="error",
        physical_attempts=physical_attempts,
        checks=MonitoringReviewReliabilityRoleChecks(
            trace_valid=False,
            physical_trace_valid=False,
            binding_valid=common_binding,
            grounding_valid=False,
            hypothesis_structural_valid=False,
            claims_scoped=False,
            action_catalog_valid=False,
            memory_mode_valid=False,
            policy_application_valid=False,
            details=common_details,
        ),
        error_type=error_type,
        error_message=error_message,
    )


def _action_consistency(
    plan: MonitoringReviewReliabilityPlan,
    observations: Sequence[MonitoringReviewReliabilityObservation],
) -> tuple[MonitoringReviewReliabilityActionConsistency, ...]:
    by_key: dict[
        tuple[str, AgentName], list[MonitoringReviewReliabilityObservation]
    ] = defaultdict(list)
    for item in observations:
        by_key[(item.context_id, item.agent_name)].append(item)
    summaries: list[MonitoringReviewReliabilityActionConsistency] = []
    for context in plan.expected_contexts:
        for role in plan.expected_roles:
            items = by_key.get((context.context_id, role), [])
            actions = [
                item.recommended_action
                for item in items
                if item.recommended_action is not None
            ]
            counts = Counter(actions)
            modal = next(
                (
                    action
                    for action in ALLOWED_ACTIONS
                    if counts.get(action, 0) == max(counts.values(), default=0)
                    and counts.get(action, 0) > 0
                ),
                None,
            )
            summaries.append(
                MonitoringReviewReliabilityActionConsistency(
                    context_id=context.context_id,
                    agent_name=role,
                    observation_count=len(items),
                    actions=tuple(
                        action for action in ALLOWED_ACTIONS if action in counts
                    ),
                    modal_action=modal,
                    agreement_rate=_rate(
                        max(counts.values(), default=0),
                        len(items),
                    ),
                )
            )
    return tuple(summaries)


def _validate_preregistration(
    plan: MonitoringReviewReliabilityPlan,
    preregistration: MonitoringReviewReliabilityPreregistration,
) -> None:
    if preregistration.plan_id != plan.plan_id:
        raise ValueError("preregistration belongs to another plan")
    path = Path(preregistration.plan_path)
    registration_path = Path(preregistration.registration_path)
    persisted = MonitoringReviewReliabilityPlan.model_validate(_read_json(path))
    persisted_registration = MonitoringReviewReliabilityPreregistration.model_validate(
        _read_json(registration_path)
    )
    actual_sha = _json_sha256(persisted.model_dump(mode="json"))
    if (
        persisted != plan
        or actual_sha != preregistration.plan_sha256
        or persisted_registration != preregistration
        or Path(persisted_registration.plan_path).resolve() != path.resolve()
        or Path(persisted_registration.registration_path).resolve()
        != registration_path.resolve()
    ):
        raise ValueError("preregistered plan changed before result construction")


def _render_report(result: MonitoringReviewReliabilityResult) -> str:
    summary = result.summary
    consistency_rates = [
        item.agreement_rate for item in summary.action_consistency
    ]
    mean_consistency = _rate(sum(consistency_rates), len(consistency_rates))
    lines = [
        f"# Fiabilidad trigger-agentes — {result.plan.plan_id}",
        "",
        "## Dictamen",
        "",
        f"- Gate: `{result.gate.verdict}`",
        f"- Bloqueos: {', '.join(result.gate.blockers) or 'ninguno'}",
        f"- Detalle: {result.gate.detail}",
        "",
        "## Cobertura",
        "",
        (
            f"- Repeticiones completas: `{summary.complete_repetition_count}/"
            f"{summary.expected_repetition_count}`"
        ),
        (
            f"- Runs hijas resueltas: `{summary.resolved_child_run_count}/"
            f"{summary.expected_child_run_count}`"
        ),
        (
            f"- Roles observados: `{summary.observation_count}/"
            f"{summary.expected_observation_count}`"
        ),
        "",
        "## Fiabilidad LLM",
        "",
        f"- First-pass: `{summary.first_pass_count}` ({summary.first_pass_rate:.2%})",
        f"- Reparadas por LLM: `{summary.repaired_count}`",
        f"- Fallbacks: `{summary.fallback_count}`",
        f"- No agenticas: `{summary.non_agentic_count}`",
        f"- Errores: `{summary.error_count}`",
        f"- Origen LLM: `{summary.llm_origin_rate:.2%}`",
        "",
        "## Integridad",
        "",
        f"- Traza: `{summary.trace_coverage_rate:.2%}`",
        f"- Binding causal: `{summary.binding_rate:.2%}`",
        f"- Grounding: `{summary.grounding_rate:.2%}`",
        (
            "- Hipotesis estructural: "
            f"`{summary.hypothesis_structural_rate:.2%}`"
        ),
        f"- Claims acotados: `{summary.claims_scoped_rate:.2%}`",
        f"- Memoria OFF: `{summary.memory_off_rate:.2%}`",
        (
            "- Politica no aplicada: "
            f"`{summary.policy_not_applied_rate:.2%}`"
        ),
        "",
        "## Consistencia descriptiva",
        "",
        (
            "La coincidencia media de acciones por contexto y rol es "
            f"`{mean_consistency:.2%}`. Esta magnitud no bloquea el gate: una "
            "respuesta repetida no es necesariamente correcta."
        ),
        "",
        "## Alcance",
        "",
        (
            "El gate mide cumplimiento del flujo agentico, referencias causales, "
            "estructura falsable y prudencia narrativa. No confirma diagnostico, "
            "degradacion fisica, onset, RUL ni utilidad de memoria RAG."
        ),
        "",
    ]
    return "\n".join(lines)


def _count_outcome(
    observations: Sequence[MonitoringReviewReliabilityObservation],
    outcome: MonitoringReviewReliabilityOutcome,
) -> int:
    return sum(item.outcome == outcome for item in observations)


def _check_rate(
    observations: Sequence[MonitoringReviewReliabilityObservation],
    field_name: str,
) -> float:
    return _rate(
        sum(bool(getattr(item.checks, field_name)) for item in observations),
        len(observations),
    )


def _rate(numerator: int | float, denominator: int) -> float:
    return 0.0 if denominator == 0 else float(numerator) / denominator


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


def _is_sha256(value: str) -> bool:
    return bool(re.fullmatch(r"[0-9a-f]{64}", value))


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
            raise ValueError(f"immutable reliability artifact conflict: {path}")
        return
    _write_json_atomic(path, payload)


def _write_immutable_text(path: Path, text: str) -> None:
    if path.exists():
        if path.read_text(encoding="utf-8") != text:
            raise ValueError(f"immutable reliability artifact conflict: {path}")
        return
    _write_text_atomic(path, text)


def _validate_artifacts_for_result(
    result: MonitoringReviewReliabilityResult,
    artifact_paths: Mapping[str, Path],
) -> None:
    plan = MonitoringReviewReliabilityPlan.model_validate(
        _read_json(artifact_paths["plan"])
    )
    preregistration = MonitoringReviewReliabilityPreregistration.model_validate(
        _read_json(artifact_paths["preregistration"])
    )
    manifest = MonitoringReviewReliabilityManifest.model_validate(
        _read_json(artifact_paths["manifest"])
    )
    summary_payload = _read_json(artifact_paths["summary"])
    observation_lines = artifact_paths["observations"].read_text(
        encoding="utf-8"
    ).splitlines()
    observations = tuple(
        MonitoringReviewReliabilityObservation.model_validate(json.loads(line))
        for line in observation_lines
        if line.strip()
    )
    if (
        plan != result.plan
        or preregistration.plan_id != result.plan.plan_id
        or preregistration.plan_sha256 != result.manifest.plan_sha256
        or preregistration.registration_sha256
        != result.manifest.preregistration_sha256
        or manifest != result.manifest
        or observations != result.observations
        or summary_payload
        != {
            "summary": result.summary.model_dump(mode="json"),
            "gate": result.gate.model_dump(mode="json"),
        }
        or artifact_paths["report"].read_text(encoding="utf-8")
        != _render_report(result)
    ):
        raise ValueError("reliability artifacts do not match the result")


def _require_contained(root: Path, path: Path) -> Path:
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("published reliability path escapes output root") from exc
    return path


def _ensure_plain_name(value: str) -> None:
    if not value or value in {".", ".."} or any(
        separator in value for separator in ("/", "\\")
    ):
        raise ValueError("plan_id must be a plain directory name")
