"""Contratos cerrados para el replay causal de monitorizacion NASA IMS.

Este modulo solo describe datos. El reloj, la persistencia atomica, el control
de concurrencia y la ejecucion de triggers pertenecen a servicios posteriores.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, ClassVar, Literal, Mapping

from pydantic import (
    AwareDatetime,
    ConfigDict,
    Field,
    FiniteFloat,
    NonNegativeInt,
    PositiveInt,
    field_validator,
    model_validator,
)

from codigo.app.schemas.agent_decisions import (
    AgentName,
    DecisionGenerationOrigin,
    DecisionGenerationTrace,
)
from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.dataset import DATASET_ID_PATTERN, SHA256_PATTERN
from codigo.app.schemas.reasoning import AgentHypothesis
from codigo.app.schemas.temporal_health import HealthState


ReplayMode = Literal["manual", "accelerated"]
ReplayExperimentMode = Literal[
    "frozen_benchmark",
    "adaptive_replay_exploratory",
]
ReplaySessionStatus = Literal[
    "ready",
    "running",
    "paused",
    "completed",
    "failed",
]
MonitoringAnalysisStatus = Literal[
    "modeled",
    "telemetry_only",
    "unavailable",
]
AgentActivationPolicyKind = Literal["P0", "P1", "P2", "P3"]
MonitoringTriggerType = Literal[
    "preflight",
    "periodic_review",
    "persistent_alert",
    "state_transition",
    "continuity_gap",
    "session_close",
    "manual",
]
MonitoringTriggerLifecycle = Literal[
    "emitted",
    "suppressed",
    "coalesced",
    "dispatched",
    "running",
    "resolved",
    "failed",
]
MonitoringTriggerSuppressionReason = Literal[
    "cooldown",
    "budget",
    "not_rearmed",
    "episode_already_covered",
]
MonitoringTriggerReasonCode = Literal[
    "preflight_review",
    "periodic_schedule",
    "persistent_confirmation",
    "health_state_escalation",
    "continuity_gap",
    "session_completed",
    "manual_request",
]
TriggerRearmPolicy = Literal[
    "after_cooldown",
    "after_recovery",
    "once_per_session",
    "manual",
]
ReplayStepOutcome = Literal[
    "applied",
    "idempotent_replay",
    "revision_conflict",
    "rejected",
]
CausalPartition = Literal["baseline_train", "calibration", "monitoring"]
CausalEvidenceField = Literal[
    "record_id",
    "dataset_id",
    "trajectory_id",
    "asset_id",
    "channel_id",
    "snapshot_id",
    "source_time",
    "segment_id",
    "analysis_status",
    "signal_rms",
    "signal_peak_abs",
    "n_samples",
    "score",
    "threshold",
    "score_ratio",
    "health_index",
    "risk_index",
    "health_state",
    "gap_detected",
    "interval_seconds",
    "scoring_version",
    "activation_version",
]
CausalEvidenceHandle = str
MonitoringReviewCapability = Literal[
    "propose_only",
    "no_fit",
    "no_retrain",
    "no_raw_scan",
]
MonitoringReviewRecommendedAction = Literal[
    "maintain_policy",
    "intensify_observation",
    "request_human_review",
    "pause_replay",
    "insufficient_evidence",
]
MonitoringReviewRoleStatus = Literal["completed", "fallback", "failed", "not_run"]
MonitoringReviewStatus = Literal["completed", "failed"]
MonitoringPolicyApplicationStatus = Literal["not_applied"]
PolicyProposalKind = Literal[
    "no_change",
    "observation",
    "workflow",
    "abstain",
]
PolicyProposalAgreementStatus = Literal[
    "unanimous",
    "disagreement",
    "invalid_review",
]
PolicyProposalAdvisorySubject = Literal[
    "policy_configuration",
    "observation_cadence",
    "human_review",
    "replay_execution",
    "policy_change",
]
PolicyProposalAdvisoryState = Literal[
    "unchanged",
    "current_schedule",
    "intensification_requested",
    "not_requested",
    "requested",
    "current_execution",
    "pause_requested",
    "withheld",
]
MonitoringChildRunStatus = Literal[
    "dispatched",
    "running",
    "resolved",
    "failed",
    "interrupted",
]
MonitoringReviewDispatchOutcome = Literal[
    "dispatched",
    "idempotent_replay",
    "revision_conflict",
    "rejected",
]

MONITORING_REVIEW_ROLES: tuple[AgentName, ...] = (
    "supervisor",
    "cleaner",
    "structurer",
    "modeler",
    "evaluator",
    "report_writer",
    "report_verifier",
)
MONITORING_REVIEW_CAPABILITIES: tuple[MonitoringReviewCapability, ...] = (
    "propose_only",
    "no_fit",
    "no_retrain",
    "no_raw_scan",
)

# Catalogo semantico deliberadamente no parametrico. Describe la recomendacion
# de cada decision sin convertirla en un cambio ejecutable de scoring o
# activacion.
MONITORING_POLICY_PROPOSAL_EFFECTS: dict[
    MonitoringReviewRecommendedAction,
    tuple[
        PolicyProposalKind,
        PolicyProposalAdvisorySubject,
        PolicyProposalAdvisoryState,
        PolicyProposalAdvisoryState,
    ],
] = {
    "maintain_policy": (
        "no_change",
        "policy_configuration",
        "unchanged",
        "unchanged",
    ),
    "intensify_observation": (
        "observation",
        "observation_cadence",
        "current_schedule",
        "intensification_requested",
    ),
    "request_human_review": (
        "workflow",
        "human_review",
        "not_requested",
        "requested",
    ),
    "pause_replay": (
        "workflow",
        "replay_execution",
        "current_execution",
        "pause_requested",
    ),
    "insufficient_evidence": (
        "abstain",
        "policy_change",
        "unchanged",
        "withheld",
    ),
}


def _require_unique_non_blank(
    values: tuple[str, ...],
    field_name: str,
) -> tuple[str, ...]:
    if any(not value for value in values):
        raise ValueError(f"{field_name} cannot contain blank values")
    if len(values) != len(set(values)):
        raise ValueError(f"{field_name} cannot contain duplicates")
    return values


class _FrozenReplayModel(StrictBaseModel):
    """Base para registros inmutables que se versionan o persisten append-only."""

    model_config = ConfigDict(frozen=True)


def _canonical_contract_sha256(payload: Mapping[str, Any]) -> str:
    """Calcula una huella estable sobre un payload ya normalizado a JSON."""

    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class _CanonicalHashedReplayModel(_FrozenReplayModel):
    """Contrato que verifica su SHA contra todos sus campos salvo la propia SHA."""

    _canonical_hash_field: ClassVar[str]

    @classmethod
    def canonical_sha256(
        cls,
        value: "_CanonicalHashedReplayModel | Mapping[str, Any]",
    ) -> str:
        """Normaliza defaults con Pydantic y calcula la huella del contrato."""

        if isinstance(value, cls):
            instance = value
        else:
            payload = dict(value)
            payload.pop(cls._canonical_hash_field, None)
            instance = cls.model_construct(**payload)
        normalized = instance.model_dump(
            mode="json",
            exclude={cls._canonical_hash_field},
            warnings=False,
        )
        return _canonical_contract_sha256(normalized)

    @model_validator(mode="after")
    def verify_canonical_sha256(self) -> "_CanonicalHashedReplayModel":
        actual = getattr(self, self._canonical_hash_field)
        expected = type(self).canonical_sha256(self)
        if actual != expected:
            raise ValueError(
                f"{self._canonical_hash_field} does not match canonical payload"
            )
        return self


class ActivePolicyRefs(_FrozenReplayModel):
    """Versiones exactas de las dos politicas activas en una sesion."""

    scoring_version: str = Field(min_length=1, max_length=160)
    activation_version: str = Field(min_length=1, max_length=160)


class ReplayAssetSpec(_FrozenReplayModel):
    """Coordenada declarada de un canal y su capacidad analitica inicial."""

    asset_id: str = Field(min_length=1, max_length=160)
    channel_id: str = Field(min_length=1, max_length=160)
    analysis_status: MonitoringAnalysisStatus


class ReplaySessionConfig(_FrozenReplayModel):
    """Configuracion inmutable que identifica una sesion y su evidencia fuente."""

    schema_version: Literal["monitoring_replay_session_config_v1"] = (
        "monitoring_replay_session_config_v1"
    )
    session_id: str = Field(min_length=1, max_length=160)
    pilot_id: str = Field(min_length=1, max_length=160)
    dataset_id: str = Field(min_length=1, pattern=DATASET_ID_PATTERN)
    trajectory_id: str = Field(min_length=1, max_length=240)
    manifest_ref: str = Field(min_length=1)
    manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    source_fingerprint_sha256: str = Field(pattern=SHA256_PATTERN)
    bootstrap_checkpoints_sha256: str = Field(pattern=SHA256_PATTERN)
    partition_policy_id: str = Field(min_length=1, max_length=160)
    asset_ids: tuple[str, ...] = Field(min_length=1)
    asset_specs: tuple[ReplayAssetSpec, ...] = Field(min_length=1)
    activation_policy_kind: AgentActivationPolicyKind = "P0"
    experiment_mode: ReplayExperimentMode = "frozen_benchmark"
    initial_mode: ReplayMode = "manual"
    initial_speed_multiplier: FiniteFloat = Field(default=1.0, gt=0.0)
    initial_policy_refs: ActivePolicyRefs
    source_timezone: str | None = Field(default=None, min_length=1, max_length=80)
    created_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("asset_ids")
    @classmethod
    def validate_asset_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _require_unique_non_blank(value, "asset_ids")

    @model_validator(mode="after")
    def validate_asset_specs(self) -> "ReplaySessionConfig":
        coordinates = [
            (spec.asset_id, spec.channel_id) for spec in self.asset_specs
        ]
        if len(coordinates) != len(set(coordinates)):
            raise ValueError(
                "asset_specs must contain unique asset/channel coordinates"
            )
        spec_asset_ids = [spec.asset_id for spec in self.asset_specs]
        if len(spec_asset_ids) != len(set(spec_asset_ids)):
            raise ValueError(
                "asset_specs must contain one channel per asset in replay v1"
            )
        declared_asset_ids = tuple(
            spec.asset_id for spec in self.asset_specs
        )
        if declared_asset_ids != self.asset_ids:
            raise ValueError(
                "asset_ids must match asset_specs assets in first-seen order"
            )
        return self


class ReplayAssetCheckpoint(_FrozenReplayModel):
    """Estado causal minimo necesario para reanudar un activo bit a bit."""

    asset_id: str = Field(min_length=1, max_length=160)
    analysis_status: MonitoringAnalysisStatus
    segment_id: NonNegativeInt = 0
    alert_persistence_count: NonNegativeInt = 0
    recovery_persistence_count: NonNegativeInt = 0
    raw_health_history: tuple[FiniteFloat, ...] = Field(default_factory=tuple)
    smoothed_health_history: tuple[FiniteFloat, ...] = Field(default_factory=tuple)
    last_source_time: datetime | None = None
    last_frame_id: str | None = Field(default=None, min_length=1, max_length=240)
    last_health_state: HealthState | None = None
    scoring_version: str | None = Field(default=None, min_length=1, max_length=160)

    @model_validator(mode="after")
    def validate_checkpoint(self) -> "ReplayAssetCheckpoint":
        if (self.last_source_time is None) != (self.last_frame_id is None):
            raise ValueError(
                "last_source_time and last_frame_id must be both set or both null"
            )
        if self.analysis_status == "modeled":
            if self.scoring_version is None:
                raise ValueError("modeled checkpoints require scoring_version")
            if self.last_frame_id is not None and self.last_health_state is None:
                raise ValueError(
                    "resumable modeled checkpoints require last_health_state"
                )
        else:
            if self.scoring_version is not None:
                raise ValueError(
                    "non-modeled checkpoints cannot declare scoring_version"
                )
            if self.last_health_state is not None:
                raise ValueError(
                    "non-modeled checkpoints cannot declare last_health_state"
                )
            if (
                self.alert_persistence_count
                or self.recovery_persistence_count
                or self.raw_health_history
                or self.smoothed_health_history
            ):
                raise ValueError(
                    "non-modeled checkpoints cannot contain diagnostic state"
                )
        return self


class ReplayActivationRuleCheckpoint(_FrozenReplayModel):
    """Ultima activacion efectiva necesaria para aplicar cooldown causal."""

    trigger_type: MonitoringTriggerType
    last_effective_trigger_id: str = Field(min_length=1, max_length=240)
    last_effective_source_time: datetime


class ReplayActivationCheckpoint(_FrozenReplayModel):
    """Estado minimo y versionado de la maquina determinista de triggers."""

    activation_version: str = Field(min_length=1, max_length=160)
    next_event_sequence: PositiveInt = 1
    variable_run_slots_reserved: NonNegativeInt = 0
    persistent_alert_armed: bool = True
    alert_episode_start_cursor: NonNegativeInt | None = None
    alert_episode_start_snapshot_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=240,
    )
    alert_episode_id: str | None = Field(default=None, min_length=1, max_length=240)
    alert_episode_handled_trigger_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=240,
    )
    alert_episode_persistence_trigger_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=240,
    )
    last_evaluated_cursor: NonNegativeInt | None = None
    last_evaluated_tick_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=240,
    )
    rule_checkpoints: tuple[ReplayActivationRuleCheckpoint, ...] = Field(
        default_factory=tuple
    )

    @model_validator(mode="after")
    def validate_activation_checkpoint(self) -> "ReplayActivationCheckpoint":
        if (self.alert_episode_start_cursor is None) != (
            self.alert_episode_start_snapshot_id is None
        ):
            raise ValueError(
                "alert episode cursor and snapshot must be both set or both null"
            )
        if (self.alert_episode_start_cursor is None) != (
            self.alert_episode_id is None
        ):
            raise ValueError(
                "alert episode identity requires an active episode start"
            )
        if (
            self.alert_episode_handled_trigger_id is not None
            and self.alert_episode_id is None
        ):
            raise ValueError(
                "handled trigger requires an active alert episode"
            )
        if (
            self.alert_episode_persistence_trigger_id is not None
            and self.alert_episode_id is None
        ):
            raise ValueError(
                "persistent trigger decision requires an active alert episode"
            )
        if (self.last_evaluated_cursor is None) != (
            self.last_evaluated_tick_id is None
        ):
            raise ValueError(
                "last evaluated cursor and tick must be both set or both null"
            )
        trigger_types = [item.trigger_type for item in self.rule_checkpoints]
        if len(trigger_types) != len(set(trigger_types)):
            raise ValueError(
                "rule_checkpoints must contain unique trigger_type values"
            )
        return self


class ReplaySessionState(StrictBaseModel):
    """Snapshot mutable y revisionado del cursor autoritativo de una sesion."""

    schema_version: Literal["monitoring_replay_session_state_v1"] = (
        "monitoring_replay_session_state_v1"
    )
    session_id: str = Field(min_length=1, max_length=160)
    config_sha256: str = Field(pattern=SHA256_PATTERN)
    status: ReplaySessionStatus = "ready"
    execution_cursor: NonNegativeInt | None = None
    sequence: NonNegativeInt = 0
    revision: NonNegativeInt = 0
    mode: ReplayMode = "manual"
    speed_multiplier: FiniteFloat = Field(default=1.0, gt=0.0)
    active_policy_refs: ActivePolicyRefs
    activation_checkpoint: ReplayActivationCheckpoint | None = None
    asset_checkpoints: tuple[ReplayAssetCheckpoint, ...] = Field(
        default_factory=tuple
    )
    last_committed_tick_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=240,
    )
    last_trigger_id: str | None = Field(default=None, min_length=1, max_length=240)
    child_run_ids: tuple[str, ...] = Field(default_factory=tuple)
    active_child_run_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=240,
    )
    last_command_id: str | None = Field(default=None, min_length=1, max_length=240)
    failure_reason: str | None = Field(default=None, min_length=1)
    updated_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("child_run_ids")
    @classmethod
    def validate_child_run_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _require_unique_non_blank(value, "child_run_ids")

    @model_validator(mode="after")
    def validate_state(self) -> "ReplaySessionState":
        checkpoint_ids = [item.asset_id for item in self.asset_checkpoints]
        if len(checkpoint_ids) != len(set(checkpoint_ids)):
            raise ValueError("asset_checkpoints must contain unique asset_id values")
        if (self.execution_cursor is None) != (self.last_committed_tick_id is None):
            raise ValueError(
                "execution_cursor and last_committed_tick_id must be both set "
                "or both null"
            )
        if self.status == "completed" and self.execution_cursor is None:
            raise ValueError("completed sessions require a committed tick")
        if self.status == "failed":
            if self.failure_reason is None:
                raise ValueError("failed sessions require failure_reason")
        elif self.failure_reason is not None:
            raise ValueError("failure_reason is only valid for failed sessions")
        if (
            self.active_child_run_id is not None
            and self.active_child_run_id not in self.child_run_ids
        ):
            raise ValueError("active_child_run_id must be present in child_run_ids")
        if (
            self.activation_checkpoint is not None
            and self.activation_checkpoint.activation_version
            != self.active_policy_refs.activation_version
        ):
            raise ValueError(
                "activation checkpoint must match the active activation version"
            )
        return self


class MonitoringTelemetrySummary(_FrozenReplayModel):
    """Telemetria descriptiva pequena, sin convertirla en diagnostico PHM."""

    signal_rms: FiniteFloat = Field(ge=0.0)
    signal_peak_abs: FiniteFloat = Field(ge=0.0)
    n_samples: PositiveInt

    @model_validator(mode="after")
    def validate_signal_summary(self) -> "MonitoringTelemetrySummary":
        if self.signal_peak_abs < self.signal_rms:
            raise ValueError("signal_peak_abs cannot be lower than signal_rms")
        return self


class MonitoringFrame(_FrozenReplayModel):
    """Resultado por activo/canal dentro de un unico tick causal."""

    schema_version: Literal["monitoring_frame_v1"] = "monitoring_frame_v1"
    frame_id: str = Field(min_length=1, max_length=240)
    tick_id: str = Field(min_length=1, max_length=240)
    asset_id: str = Field(min_length=1, max_length=160)
    channel_id: str = Field(min_length=1, max_length=160)
    interval_seconds: FiniteFloat | None = Field(default=None, ge=0.0)
    gap_detected: bool = False
    segment_id: NonNegativeInt | None = None
    analysis_status: MonitoringAnalysisStatus
    telemetry: MonitoringTelemetrySummary | None = None
    score: FiniteFloat | None = None
    threshold: FiniteFloat | None = None
    predicted_anomaly: bool | None = None
    score_ratio: FiniteFloat | None = None
    health_index: FiniteFloat | None = Field(default=None, ge=0.0, le=100.0)
    risk_index: FiniteFloat | None = Field(default=None, ge=0.0, le=100.0)
    health_state: HealthState | None = None
    scoring_version: str | None = Field(default=None, min_length=1, max_length=160)
    evidence_refs: tuple[str, ...] = Field(default_factory=tuple)
    unavailable_reason: str | None = Field(default=None, min_length=1)

    @field_validator("evidence_refs")
    @classmethod
    def validate_evidence_refs(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _require_unique_non_blank(value, "evidence_refs")

    @model_validator(mode="after")
    def validate_analysis_payload(self) -> "MonitoringFrame":
        if self.gap_detected and self.interval_seconds is None:
            raise ValueError("gap_detected frames require interval_seconds")
        diagnostic_fields = {
            "score": self.score,
            "threshold": self.threshold,
            "predicted_anomaly": self.predicted_anomaly,
            "score_ratio": self.score_ratio,
            "health_index": self.health_index,
            "risk_index": self.risk_index,
            "health_state": self.health_state,
            "scoring_version": self.scoring_version,
        }
        if self.analysis_status == "modeled":
            if self.segment_id is None:
                raise ValueError("modeled frames require segment_id")
            missing = [
                name for name, value in diagnostic_fields.items() if value is None
            ]
            if missing:
                raise ValueError(
                    "modeled frames require all diagnostic fields: "
                    + ", ".join(missing)
                )
            if self.unavailable_reason is not None:
                raise ValueError("modeled frames cannot declare unavailable_reason")
        else:
            present = [
                name for name, value in diagnostic_fields.items() if value is not None
            ]
            if present:
                raise ValueError(
                    "non-modeled frames cannot contain diagnostics: "
                    + ", ".join(present)
                )
            if self.analysis_status == "telemetry_only":
                if self.telemetry is None:
                    raise ValueError("telemetry_only frames require telemetry")
                if self.unavailable_reason is not None:
                    raise ValueError(
                        "telemetry_only frames cannot declare unavailable_reason"
                    )
            else:
                if self.telemetry is not None:
                    raise ValueError("unavailable frames cannot contain telemetry")
                if self.unavailable_reason is None:
                    raise ValueError("unavailable frames require unavailable_reason")
        return self


class ReplayTick(_FrozenReplayModel):
    """Commit atomico de un snapshot sincronizado y todos sus frames."""

    schema_version: Literal["monitoring_replay_tick_v1"] = (
        "monitoring_replay_tick_v1"
    )
    commit_status: Literal["committed"] = "committed"
    tick_id: str = Field(min_length=1, max_length=240)
    session_id: str = Field(min_length=1, max_length=160)
    cursor: NonNegativeInt
    sequence: PositiveInt
    snapshot_id: str = Field(min_length=1, max_length=240)
    source_time: datetime
    input_record_hash: str = Field(pattern=SHA256_PATTERN)
    active_policy_refs: ActivePolicyRefs
    frames: tuple[MonitoringFrame, ...] = Field(min_length=1)
    committed_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_atomic_frames(self) -> "ReplayTick":
        frame_ids = [frame.frame_id for frame in self.frames]
        if len(frame_ids) != len(set(frame_ids)):
            raise ValueError("frames must contain unique frame_id values")

        coordinates = [(frame.asset_id, frame.channel_id) for frame in self.frames]
        if len(coordinates) != len(set(coordinates)):
            raise ValueError(
                "a tick cannot contain multiple frames for the same asset/channel"
            )

        for frame in self.frames:
            if frame.tick_id != self.tick_id:
                raise ValueError("every frame.tick_id must match ReplayTick.tick_id")
            if (
                frame.analysis_status == "modeled"
                and frame.scoring_version != self.active_policy_refs.scoring_version
            ):
                raise ValueError(
                    "modeled frame scoring_version must match active scoring policy"
                )
        return self


class ScoringPolicyBundle(_FrozenReplayModel):
    """Bundle inmutable de inferencia para una coordenada modelada."""

    schema_version: Literal["scoring_policy_bundle_v1"] = (
        "scoring_policy_bundle_v1"
    )
    policy_version: str = Field(min_length=1, max_length=160)
    policy_sha256: str = Field(pattern=SHA256_PATTERN)
    parent_version: str | None = Field(default=None, min_length=1, max_length=160)
    asset_id: str = Field(min_length=1, max_length=160)
    channel_id: str = Field(min_length=1, max_length=160)
    model_ref: str = Field(min_length=1)
    model_sha256: str = Field(pattern=SHA256_PATTERN)
    scaler_ref: str = Field(min_length=1)
    scaler_sha256: str = Field(pattern=SHA256_PATTERN)
    features_ref: str = Field(min_length=1)
    features_sha256: str = Field(pattern=SHA256_PATTERN)
    feature_columns: tuple[str, ...] = Field(min_length=1)
    threshold: FiniteFloat
    threshold_operator: Literal["greater_than"] = "greater_than"
    aggregation_policy_id: str = Field(min_length=1, max_length=160)
    aggregation_policy_sha256: str = Field(pattern=SHA256_PATTERN)
    gap_policy_id: str = Field(min_length=1, max_length=160)
    gap_policy_sha256: str = Field(pattern=SHA256_PATTERN)
    health_policy_id: str = Field(min_length=1, max_length=160)
    health_policy_sha256: str = Field(pattern=SHA256_PATTERN)
    health_indicator_policy_id: str = Field(min_length=1, max_length=160)
    health_indicator_policy_sha256: str = Field(pattern=SHA256_PATTERN)

    @field_validator("feature_columns")
    @classmethod
    def validate_feature_columns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _require_unique_non_blank(value, "feature_columns")


class CausalEvidenceArtifact(_FrozenReplayModel):
    """Artefacto ya proyectado cuya evidencia no supera un cutoff declarado."""

    evidence_id: str = Field(min_length=1, max_length=240)
    artifact_ref: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    available_at_cursor: NonNegativeInt
    max_source_time: datetime
    record_count: PositiveInt
    fields: tuple[CausalEvidenceField, ...] = Field(min_length=1)

    @field_validator("fields")
    @classmethod
    def validate_fields(
        cls,
        value: tuple[CausalEvidenceField, ...],
    ) -> tuple[CausalEvidenceField, ...]:
        if len(value) != len(set(value)):
            raise ValueError("fields cannot contain duplicates")
        return value


class CausalEvidenceCatalogEntry(_FrozenReplayModel):
    """Handle corto y resolucion canonica de un registro causal sellado."""

    handle: CausalEvidenceHandle = Field(pattern=r"^E(?:0[1-9]|[1-9][0-9])$")
    record_index: NonNegativeInt
    causal_scope_ref: str = Field(min_length=1, max_length=240)
    support_ref: str = Field(min_length=1, max_length=240)
    record_id: str = Field(min_length=1, max_length=240)
    record_sha256: str = Field(pattern=SHA256_PATTERN)
    display_projection_sha256: str = Field(pattern=SHA256_PATTERN)


class CausalEvidenceCatalog(_CanonicalHashedReplayModel):
    """Catalogo determinista E01..E99 ligado a una vista y su artefacto."""

    _canonical_hash_field = "catalog_sha256"

    schema_version: Literal["causal_evidence_catalog_v1"] = (
        "causal_evidence_catalog_v1"
    )
    catalog_id: str = Field(min_length=1, max_length=240)
    catalog_sha256: str = Field(pattern=SHA256_PATTERN)
    causal_view_sha256: str = Field(pattern=SHA256_PATTERN)
    source_artifact_sha256: str = Field(pattern=SHA256_PATTERN)
    causal_scope_refs: tuple[str, ...] = Field(min_length=1)
    entries: tuple[CausalEvidenceCatalogEntry, ...] = Field(
        min_length=1,
        max_length=99,
    )

    @field_validator("causal_scope_refs")
    @classmethod
    def validate_causal_scope_refs(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        return _require_unique_non_blank(value, "causal_scope_refs")

    @model_validator(mode="after")
    def validate_catalog_entries(self) -> "CausalEvidenceCatalog":
        expected_handles = tuple(
            f"E{index:02d}" for index in range(1, len(self.entries) + 1)
        )
        handles = tuple(item.handle for item in self.entries)
        indexes = tuple(item.record_index for item in self.entries)
        if handles != expected_handles:
            raise ValueError("catalog handles must be contiguous E01..EN")
        if indexes != tuple(range(len(self.entries))):
            raise ValueError("catalog record_index values must be contiguous from zero")
        if any(
            item.causal_scope_ref not in self.causal_scope_refs
            for item in self.entries
        ):
            raise ValueError("catalog entry scope must belong to causal_scope_refs")
        for field_name in (
            "support_ref",
            "record_id",
            "record_sha256",
            "display_projection_sha256",
        ):
            values = tuple(getattr(item, field_name) for item in self.entries)
            if len(values) != len(set(values)):
                raise ValueError(f"catalog entries require unique {field_name}")
        return self


class CausalInputView(_CanonicalHashedReplayModel):
    """Vista por whitelist que una revision puede consumir sin leer el raw."""

    _canonical_hash_field = "view_sha256"

    schema_version: Literal["causal_input_view_v1"] = "causal_input_view_v1"
    view_id: str = Field(min_length=1, max_length=240)
    view_sha256: str = Field(pattern=SHA256_PATTERN)
    session_id: str = Field(min_length=1, max_length=160)
    trigger_id: str = Field(min_length=1, max_length=240)
    trigger_event_id: str = Field(min_length=1, max_length=240)
    origin_tick_id: str = Field(min_length=1, max_length=240)
    cutoff_snapshot_id: str = Field(min_length=1, max_length=240)
    cursor: NonNegativeInt
    cutoff_source_time: datetime
    active_policy_refs: ActivePolicyRefs
    manifest_projection_ref: str = Field(min_length=1)
    manifest_projection_sha256: str = Field(pattern=SHA256_PATTERN)
    partition_policy_id: str = Field(min_length=1, max_length=160)
    visible_partitions: tuple[CausalPartition, ...] = Field(min_length=1)
    whitelisted_fields: tuple[CausalEvidenceField, ...] = Field(min_length=1)
    evidence: tuple[CausalEvidenceArtifact, ...] = Field(min_length=1)
    created_at: AwareDatetime

    @field_validator("visible_partitions", "whitelisted_fields")
    @classmethod
    def validate_unique_view_values(cls, value: tuple, info) -> tuple:
        if len(value) != len(set(value)):
            raise ValueError(f"{info.field_name} cannot contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_cutoff(self) -> "CausalInputView":
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence must contain unique evidence_id values")
        whitelist = set(self.whitelisted_fields)
        for item in self.evidence:
            if item.available_at_cursor > self.cursor:
                raise ValueError("evidence cannot become available after view cursor")
            try:
                source_is_future = item.max_source_time > self.cutoff_source_time
            except TypeError as exc:
                raise ValueError(
                    "evidence and view source times must use the same timezone "
                    "convention"
                ) from exc
            if source_is_future:
                raise ValueError("evidence cannot exceed cutoff_source_time")
            if not set(item.fields).issubset(whitelist):
                raise ValueError(
                    "evidence fields must be included in the view whitelist"
                )
        return self


class MonitoringReviewRequest(_CanonicalHashedReplayModel):
    """Orden cerrada para una run hija causal y exclusivamente propose-only."""

    _canonical_hash_field = "request_sha256"

    schema_version: Literal["monitoring_review_request_v1"] = (
        "monitoring_review_request_v1"
    )
    request_id: str = Field(min_length=1, max_length=240)
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    child_run_id: str = Field(min_length=1, max_length=240)
    session_id: str = Field(min_length=1, max_length=160)
    trigger_id: str = Field(min_length=1, max_length=240)
    trigger_event_id: str = Field(min_length=1, max_length=240)
    origin_tick_id: str = Field(min_length=1, max_length=240)
    cutoff_snapshot_id: str = Field(min_length=1, max_length=240)
    cutoff_cursor: NonNegativeInt
    cutoff_source_time: datetime
    active_policy_refs: ActivePolicyRefs
    causal_view_ref: str = Field(min_length=1)
    causal_view_sha256: str = Field(pattern=SHA256_PATTERN)
    review_kind: Literal["monitoring_review"] = "monitoring_review"
    requested_roles: tuple[AgentName, ...] = MONITORING_REVIEW_ROLES
    required_roles: tuple[AgentName, ...] = MONITORING_REVIEW_ROLES
    capabilities: tuple[MonitoringReviewCapability, ...] = (
        MONITORING_REVIEW_CAPABILITIES
    )
    memory_mode: Literal["off"] = "off"
    prompt_template_id: str = Field(min_length=1, max_length=240)
    prompt_template_sha256: str = Field(pattern=SHA256_PATTERN)
    response_schema_id: str = Field(min_length=1, max_length=240)
    response_schema_sha256: str = Field(pattern=SHA256_PATTERN)
    allowed_options_id: str = Field(min_length=1, max_length=240)
    allowed_options_sha256: str = Field(pattern=SHA256_PATTERN)
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_closed_review_scope(self) -> "MonitoringReviewRequest":
        if self.requested_roles != MONITORING_REVIEW_ROLES:
            raise ValueError("requested_roles must contain the seven canonical roles")
        if self.required_roles != MONITORING_REVIEW_ROLES:
            raise ValueError("required_roles must contain the seven canonical roles")
        if self.capabilities != MONITORING_REVIEW_CAPABILITIES:
            raise ValueError(
                "capabilities must be the canonical propose-only capability set"
            )
        return self


class MonitoringReviewDecision(_CanonicalHashedReplayModel):
    """Decision comun, completa y auditable emitida por uno de los siete roles."""

    _canonical_hash_field = "decision_sha256"

    schema_version: Literal["monitoring_review_decision_v1"] = (
        "monitoring_review_decision_v1"
    )
    decision_id: str = Field(min_length=1, max_length=240)
    decision_sha256: str = Field(pattern=SHA256_PATTERN)
    agent_name: AgentName
    decision_kind: Literal["monitoring_review"] = "monitoring_review"
    child_run_id: str = Field(min_length=1, max_length=240)
    trigger_event_id: str = Field(min_length=1, max_length=240)
    cutoff_snapshot_id: str = Field(min_length=1, max_length=240)
    cutoff_cursor: NonNegativeInt
    cutoff_source_time: datetime
    causal_view_sha256: str = Field(pattern=SHA256_PATTERN)
    rationale: str = Field(min_length=1)
    confidence: FiniteFloat = Field(ge=0.0, le=1.0)
    hypothesis: AgentHypothesis
    generation_trace: DecisionGenerationTrace
    observation_summary: str = Field(min_length=1)
    recommended_action: MonitoringReviewRecommendedAction
    action_rationale: str = Field(min_length=1)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    alternatives: tuple[MonitoringReviewRecommendedAction, ...] = Field(
        min_length=1
    )
    requires_human_review: bool
    memory_mode: Literal["off"] = "off"
    policy_application_status: MonitoringPolicyApplicationStatus = "not_applied"
    created_at: AwareDatetime

    @field_validator("evidence_refs")
    @classmethod
    def validate_decision_evidence_refs(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        return _require_unique_non_blank(value, "evidence_refs")

    @model_validator(mode="after")
    def validate_decision_links(self) -> "MonitoringReviewDecision":
        trace = self.generation_trace
        expected_attempt_id = DecisionGenerationTrace.attempt_id_for(
            self.decision_id,
            trace.attempt_index,
        )
        if trace.attempt_id != expected_attempt_id:
            raise ValueError("generation attempt_id must be derived from decision_id")
        if trace.fallback_from_attempt_id is not None:
            valid_sources = {
                DecisionGenerationTrace.attempt_id_for(self.decision_id, index)
                for index in range(1, trace.attempt_index)
            }
            if trace.fallback_from_attempt_id not in valid_sources:
                raise ValueError(
                    "fallback source must be an earlier attempt of the same decision"
                )
        if self.hypothesis.evidence_cutoff != self.cutoff_snapshot_id:
            raise ValueError(
                "hypothesis evidence_cutoff must match cutoff_snapshot_id"
            )
        if not set(self.hypothesis.evidence_refs).issubset(self.evidence_refs):
            raise ValueError(
                "hypothesis evidence_refs must be included in decision evidence_refs"
            )
        if len(self.alternatives) != len(set(self.alternatives)):
            raise ValueError("alternatives cannot contain duplicates")
        if self.recommended_action in self.alternatives:
            raise ValueError("alternatives cannot repeat recommended_action")
        if (
            self.recommended_action == "request_human_review"
            and not self.requires_human_review
        ):
            raise ValueError(
                "request_human_review requires requires_human_review=true"
            )
        return self


class MonitoringReviewRoleResult(_FrozenReplayModel):
    """Resultado explicito de un rol, incluida su decision o su fallo."""

    schema_version: Literal["monitoring_review_role_result_v1"] = (
        "monitoring_review_role_result_v1"
    )
    agent_name: AgentName
    status: MonitoringReviewRoleStatus
    decision: MonitoringReviewDecision | None = None
    runtime_event_ids: tuple[str, ...] = Field(default_factory=tuple)
    failure_reason: str | None = Field(default=None, min_length=1)

    @field_validator("runtime_event_ids")
    @classmethod
    def validate_runtime_event_ids(
        cls,
        value: tuple[str, ...],
    ) -> tuple[str, ...]:
        return _require_unique_non_blank(value, "runtime_event_ids")

    @model_validator(mode="after")
    def validate_role_outcome(self) -> "MonitoringReviewRoleResult":
        if self.status in {"completed", "fallback"}:
            if self.decision is None:
                raise ValueError("completed and fallback role results require a decision")
            if not self.runtime_event_ids:
                raise ValueError(
                    "completed and fallback role results require runtime_event_ids"
                )
            if self.status == "completed" and self.failure_reason is not None:
                raise ValueError(
                    "completed role results cannot declare failure_reason"
                )
            if self.decision.agent_name != self.agent_name:
                raise ValueError("role result agent_name must match decision agent_name")
            is_guardrail_fallback = (
                self.decision.generation_trace.origin == "guardrail_fallback"
            )
            if self.status == "fallback":
                if not is_guardrail_fallback or self.failure_reason is None:
                    raise ValueError(
                        "fallback role results require a guardrail fallback decision "
                        "and failure_reason"
                    )
            elif is_guardrail_fallback:
                raise ValueError(
                    "guardrail fallback decisions cannot be marked completed"
                )
        else:
            if self.decision is not None:
                raise ValueError("non-completed role results cannot contain a decision")
            if self.failure_reason is None:
                raise ValueError(
                    "failed and not_run role results require failure_reason"
                )
        return self


class MonitoringReviewResult(_CanonicalHashedReplayModel):
    """Expediente final del puente trigger-vista-run-decisiones sin aplicar politica."""

    _canonical_hash_field = "result_sha256"

    schema_version: Literal["monitoring_review_result_v1"] = (
        "monitoring_review_result_v1"
    )
    result_id: str = Field(min_length=1, max_length=240)
    result_sha256: str = Field(pattern=SHA256_PATTERN)
    request_id: str = Field(min_length=1, max_length=240)
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    child_run_id: str = Field(min_length=1, max_length=240)
    session_id: str = Field(min_length=1, max_length=160)
    trigger_id: str = Field(min_length=1, max_length=240)
    trigger_event_id: str = Field(min_length=1, max_length=240)
    origin_tick_id: str = Field(min_length=1, max_length=240)
    cutoff_snapshot_id: str = Field(min_length=1, max_length=240)
    cutoff_cursor: NonNegativeInt
    cutoff_source_time: datetime
    active_policy_refs: ActivePolicyRefs
    causal_view_ref: str = Field(min_length=1)
    causal_view_sha256: str = Field(pattern=SHA256_PATTERN)
    requested_roles: tuple[AgentName, ...] = MONITORING_REVIEW_ROLES
    required_roles: tuple[AgentName, ...] = MONITORING_REVIEW_ROLES
    capabilities: tuple[MonitoringReviewCapability, ...] = (
        MONITORING_REVIEW_CAPABILITIES
    )
    role_results: tuple[MonitoringReviewRoleResult, ...] = Field(min_length=7)
    memory_mode: Literal["off"] = "off"
    policy_application_status: MonitoringPolicyApplicationStatus = "not_applied"
    runtime_events_ref: str = Field(min_length=1)
    runtime_events_sha256: str = Field(pattern=SHA256_PATTERN)
    status: MonitoringReviewStatus
    failure_reason: str | None = Field(default=None, min_length=1)
    completed_at: AwareDatetime

    @model_validator(mode="after")
    def validate_review_result(self) -> "MonitoringReviewResult":
        if self.requested_roles != MONITORING_REVIEW_ROLES:
            raise ValueError("requested_roles must contain the seven canonical roles")
        if self.required_roles != MONITORING_REVIEW_ROLES:
            raise ValueError("required_roles must contain the seven canonical roles")
        if self.capabilities != MONITORING_REVIEW_CAPABILITIES:
            raise ValueError(
                "capabilities must be the canonical propose-only capability set"
            )
        role_names = tuple(item.agent_name for item in self.role_results)
        if role_names != MONITORING_REVIEW_ROLES:
            raise ValueError(
                "role_results must contain the seven canonical roles in order"
            )
        decision_ids: list[str] = []
        for item in self.role_results:
            decision = item.decision
            if decision is None:
                continue
            decision_ids.append(decision.decision_id)
            if decision.child_run_id != self.child_run_id:
                raise ValueError("decision child_run_id must match result child_run_id")
            if decision.trigger_event_id != self.trigger_event_id:
                raise ValueError(
                    "decision trigger_event_id must match result trigger_event_id"
                )
            if decision.cutoff_snapshot_id != self.cutoff_snapshot_id:
                raise ValueError(
                    "decision cutoff_snapshot_id must match result cutoff_snapshot_id"
                )
            if decision.cutoff_cursor != self.cutoff_cursor:
                raise ValueError("decision cutoff_cursor must match result cutoff_cursor")
            if decision.cutoff_source_time != self.cutoff_source_time:
                raise ValueError(
                    "decision cutoff_source_time must match result cutoff_source_time"
                )
            if decision.causal_view_sha256 != self.causal_view_sha256:
                raise ValueError(
                    "decision causal_view_sha256 must match result causal_view_sha256"
                )
        if len(decision_ids) != len(set(decision_ids)):
            raise ValueError("role decisions must have unique decision_id values")
        all_completed = all(item.status == "completed" for item in self.role_results)
        if self.status == "completed":
            if not all_completed:
                raise ValueError("completed review requires all seven roles completed")
            if self.failure_reason is not None:
                raise ValueError("completed review cannot declare failure_reason")
        else:
            if all_completed:
                raise ValueError(
                    "failed review requires at least one failed or fallback role"
                )
            if self.failure_reason is None:
                raise ValueError("failed review requires failure_reason")
        return self


class PolicyProposalContribution(_FrozenReplayModel):
    """Proyeccion consultiva de una decision, sin parametros aplicables."""

    schema_version: Literal["policy_proposal_contribution_v1"] = (
        "policy_proposal_contribution_v1"
    )
    agent_name: AgentName
    decision_id: str = Field(min_length=1, max_length=240)
    decision_sha256: str = Field(pattern=SHA256_PATTERN)
    generation_origin: DecisionGenerationOrigin
    recommended_action: MonitoringReviewRecommendedAction
    proposal_kind: PolicyProposalKind
    advisory_subject: PolicyProposalAdvisorySubject
    current_state: PolicyProposalAdvisoryState
    proposed_state: PolicyProposalAdvisoryState
    action_rationale: str = Field(min_length=1)
    risk_notes: tuple[str, ...] = Field(min_length=1)
    evidence_handles: tuple[CausalEvidenceHandle, ...] = Field(min_length=1)
    evidence_support_refs: tuple[str, ...] = Field(min_length=1)
    requires_human_review: bool

    @field_validator(
        "risk_notes",
        "evidence_handles",
        "evidence_support_refs",
    )
    @classmethod
    def validate_unique_contribution_values(
        cls,
        value: tuple[str, ...],
        info,
    ) -> tuple[str, ...]:
        return _require_unique_non_blank(value, info.field_name)

    @field_validator("evidence_handles")
    @classmethod
    def validate_evidence_handles(
        cls,
        value: tuple[CausalEvidenceHandle, ...],
    ) -> tuple[CausalEvidenceHandle, ...]:
        if any(
            len(handle) != 3
            or handle[0] != "E"
            or any(character not in "0123456789" for character in handle[1:])
            or handle == "E00"
            for handle in value
        ):
            raise ValueError("evidence_handles must use the exact E01..E99 format")
        return value

    @model_validator(mode="after")
    def validate_advisory_effect(self) -> "PolicyProposalContribution":
        expected = MONITORING_POLICY_PROPOSAL_EFFECTS[self.recommended_action]
        observed = (
            self.proposal_kind,
            self.advisory_subject,
            self.current_state,
            self.proposed_state,
        )
        if observed != expected:
            raise ValueError(
                "policy proposal contribution does not match the closed action map"
            )
        if len(self.evidence_handles) != len(self.evidence_support_refs):
            raise ValueError(
                "evidence handles and support refs must have the same length"
            )
        if (
            self.recommended_action == "request_human_review"
            and not self.requires_human_review
        ):
            raise ValueError(
                "request_human_review contributions require human review"
            )
        return self


class MonitoringPolicyProposal(_CanonicalHashedReplayModel):
    """Sintesis determinista de siete recomendaciones, siempre no aplicada."""

    _canonical_hash_field = "proposal_sha256"

    schema_version: Literal["monitoring_policy_proposal_v1"] = (
        "monitoring_policy_proposal_v1"
    )
    proposal_id: str = Field(min_length=1, max_length=240)
    proposal_sha256: str = Field(pattern=SHA256_PATTERN)
    request_id: str = Field(min_length=1, max_length=240)
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    child_run_id: str = Field(min_length=1, max_length=240)
    session_id: str = Field(min_length=1, max_length=160)
    trigger_id: str = Field(min_length=1, max_length=240)
    trigger_event_id: str = Field(min_length=1, max_length=240)
    origin_tick_id: str = Field(min_length=1, max_length=240)
    cutoff_snapshot_id: str = Field(min_length=1, max_length=240)
    cutoff_cursor: NonNegativeInt
    cutoff_source_time: datetime
    active_policy_refs: ActivePolicyRefs
    causal_view_sha256: str = Field(pattern=SHA256_PATTERN)
    evidence_catalog_sha256: str = Field(pattern=SHA256_PATTERN)
    proposal_origin: Literal["deterministic_server"] = "deterministic_server"
    status: Literal["advisory_not_applied"] = "advisory_not_applied"
    application_status: MonitoringPolicyApplicationStatus = "not_applied"
    policy_validation_eligible: Literal[False] = False
    agreement_status: PolicyProposalAgreementStatus
    aggregate_action: MonitoringReviewRecommendedAction | None = None
    aggregate_kind: PolicyProposalKind | None = None
    contributions: tuple[PolicyProposalContribution, ...] = Field(
        min_length=7,
        max_length=7,
    )
    human_review_recommended: bool
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_consultative_proposal(self) -> "MonitoringPolicyProposal":
        agents = tuple(item.agent_name for item in self.contributions)
        if agents != MONITORING_REVIEW_ROLES:
            raise ValueError(
                "policy proposal contributions must contain the seven canonical "
                "roles in order"
            )
        decision_ids = tuple(item.decision_id for item in self.contributions)
        decision_hashes = tuple(
            item.decision_sha256 for item in self.contributions
        )
        if len(decision_ids) != len(set(decision_ids)):
            raise ValueError("policy proposal decisions must have unique ids")
        if len(decision_hashes) != len(set(decision_hashes)):
            raise ValueError("policy proposal decisions must have unique hashes")

        expected_human_review = any(
            item.requires_human_review for item in self.contributions
        )
        if self.human_review_recommended != expected_human_review:
            raise ValueError(
                "human_review_recommended must be derived from the decisions"
            )

        actions = {item.recommended_action for item in self.contributions}
        invalid_review = any(
            item.generation_origin != "llm" for item in self.contributions
        )
        if invalid_review:
            expected_agreement = "invalid_review"
            expected_action = None
            expected_kind = None
        elif len(actions) == 1:
            expected_agreement = "unanimous"
            expected_action = next(iter(actions))
            expected_kind = MONITORING_POLICY_PROPOSAL_EFFECTS[
                expected_action
            ][0]
        else:
            expected_agreement = "disagreement"
            expected_action = None
            expected_kind = None
        if (
            self.agreement_status,
            self.aggregate_action,
            self.aggregate_kind,
        ) != (expected_agreement, expected_action, expected_kind):
            raise ValueError(
                "policy proposal aggregate must follow unanimity and invalid-review "
                "rules"
            )
        return self


class MonitoringReviewDispatchCommand(_CanonicalHashedReplayModel):
    """Comando CAS e idempotente que reserva una run hija de revision."""

    _canonical_hash_field = "command_sha256"

    schema_version: Literal["monitoring_review_dispatch_command_v1"] = (
        "monitoring_review_dispatch_command_v1"
    )
    command: Literal["dispatch_monitoring_review"] = "dispatch_monitoring_review"
    command_id: str = Field(min_length=1, max_length=240)
    command_sha256: str = Field(pattern=SHA256_PATTERN)
    session_id: str = Field(min_length=1, max_length=160)
    trigger_id: str = Field(min_length=1, max_length=240)
    trigger_event_id: str = Field(min_length=1, max_length=240)
    child_run_id: str = Field(min_length=1, max_length=240)
    job_id: str = Field(min_length=1, max_length=240)
    run_id: str = Field(min_length=1, max_length=240)
    attempt_no: PositiveInt
    expected_child_revision: NonNegativeInt
    request_ref: str = Field(min_length=1)
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    causal_view_ref: str = Field(min_length=1)
    causal_view_sha256: str = Field(pattern=SHA256_PATTERN)
    issued_at: AwareDatetime

    @model_validator(mode="after")
    def validate_dispatch_identity(self) -> "MonitoringReviewDispatchCommand":
        if not (self.child_run_id == self.job_id == self.run_id):
            raise ValueError("child_run_id, job_id and run_id must be identical")
        return self


class MonitoringChildRunAttempt(_FrozenReplayModel):
    """Snapshot revisionado del ciclo de vida de un intento de run hija."""

    schema_version: Literal["monitoring_child_run_attempt_v1"] = (
        "monitoring_child_run_attempt_v1"
    )
    session_id: str = Field(min_length=1, max_length=160)
    trigger_id: str = Field(min_length=1, max_length=240)
    trigger_event_id: str = Field(min_length=1, max_length=240)
    child_run_id: str = Field(min_length=1, max_length=240)
    job_id: str = Field(min_length=1, max_length=240)
    run_id: str = Field(min_length=1, max_length=240)
    attempt_no: PositiveInt
    child_revision: PositiveInt
    lifecycle_status: MonitoringChildRunStatus
    request_ref: str = Field(min_length=1)
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    causal_view_ref: str = Field(min_length=1)
    causal_view_sha256: str = Field(pattern=SHA256_PATTERN)
    result_ref: str | None = Field(default=None, min_length=1)
    result_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    dispatched_at: AwareDatetime
    started_at: AwareDatetime | None = None
    completed_at: AwareDatetime | None = None
    updated_at: AwareDatetime
    error: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_attempt_lifecycle(self) -> "MonitoringChildRunAttempt":
        if not (self.child_run_id == self.job_id == self.run_id):
            raise ValueError("child_run_id, job_id and run_id must be identical")
        if (self.result_ref is None) != (self.result_sha256 is None):
            raise ValueError("result_ref and result_sha256 must be both set or null")
        if self.updated_at < self.dispatched_at:
            raise ValueError("updated_at cannot precede dispatched_at")
        if self.started_at is not None and self.started_at < self.dispatched_at:
            raise ValueError("started_at cannot precede dispatched_at")
        if self.completed_at is not None:
            if self.started_at is None:
                raise ValueError("completed attempts require started_at")
            if self.completed_at < self.started_at:
                raise ValueError("completed_at cannot precede started_at")
            if self.updated_at < self.completed_at:
                raise ValueError("updated_at cannot precede completed_at")

        if self.lifecycle_status == "dispatched":
            if any(
                value is not None
                for value in (
                    self.started_at,
                    self.completed_at,
                    self.result_ref,
                    self.error,
                )
            ):
                raise ValueError(
                    "dispatched attempts cannot contain execution outcome fields"
                )
        elif self.lifecycle_status == "running":
            if self.started_at is None:
                raise ValueError("running attempts require started_at")
            if any(
                value is not None
                for value in (self.completed_at, self.result_ref, self.error)
            ):
                raise ValueError("running attempts cannot contain outcome fields")
        elif self.lifecycle_status in {"resolved", "failed"}:
            if self.started_at is None or self.completed_at is None:
                raise ValueError(
                    "resolved and failed attempts require start and completion times"
                )
            if self.result_ref is None:
                raise ValueError("resolved and failed attempts require result artifact")
            if self.lifecycle_status == "resolved" and self.error is not None:
                raise ValueError("resolved attempts cannot declare error")
            if self.lifecycle_status == "failed" and self.error is None:
                raise ValueError("failed attempts require error")
        else:
            if self.started_at is None or self.completed_at is None:
                raise ValueError(
                    "interrupted attempts require start and completion times"
                )
            if self.error is None:
                raise ValueError("interrupted attempts require error")
        return self


class MonitoringReviewDispatchReceipt(_CanonicalHashedReplayModel):
    """Resultado persistible de despachar, repetir o rechazar una run hija."""

    _canonical_hash_field = "receipt_sha256"

    schema_version: Literal["monitoring_review_dispatch_receipt_v1"] = (
        "monitoring_review_dispatch_receipt_v1"
    )
    receipt_id: str = Field(min_length=1, max_length=240)
    receipt_sha256: str = Field(pattern=SHA256_PATTERN)
    command_id: str = Field(min_length=1, max_length=240)
    command_sha256: str = Field(pattern=SHA256_PATTERN)
    session_id: str = Field(min_length=1, max_length=160)
    trigger_id: str = Field(min_length=1, max_length=240)
    trigger_event_id: str = Field(min_length=1, max_length=240)
    child_run_id: str = Field(min_length=1, max_length=240)
    job_id: str = Field(min_length=1, max_length=240)
    run_id: str = Field(min_length=1, max_length=240)
    attempt_no: PositiveInt
    expected_child_revision: NonNegativeInt
    child_revision: NonNegativeInt
    request_ref: str = Field(min_length=1)
    request_sha256: str = Field(pattern=SHA256_PATTERN)
    causal_view_ref: str = Field(min_length=1)
    causal_view_sha256: str = Field(pattern=SHA256_PATTERN)
    outcome: MonitoringReviewDispatchOutcome
    attempt: MonitoringChildRunAttempt | None = None
    error: str | None = Field(default=None, min_length=1)
    recorded_at: AwareDatetime

    @model_validator(mode="after")
    def validate_dispatch_receipt(self) -> "MonitoringReviewDispatchReceipt":
        if not (self.child_run_id == self.job_id == self.run_id):
            raise ValueError("child_run_id, job_id and run_id must be identical")
        if self.outcome in {"dispatched", "idempotent_replay"}:
            if self.attempt is None:
                raise ValueError("successful dispatch receipts require attempt")
            if self.error is not None:
                raise ValueError("successful dispatch receipts cannot declare error")
            if self.child_revision != self.expected_child_revision + 1:
                raise ValueError(
                    "successful dispatch must advance exactly one child revision"
                )
            attempt = self.attempt
            receipt_binding = (
                self.session_id,
                self.trigger_id,
                self.trigger_event_id,
                self.child_run_id,
                self.job_id,
                self.run_id,
                self.attempt_no,
                self.child_revision,
                self.request_ref,
                self.request_sha256,
                self.causal_view_ref,
                self.causal_view_sha256,
            )
            attempt_binding = (
                attempt.session_id,
                attempt.trigger_id,
                attempt.trigger_event_id,
                attempt.child_run_id,
                attempt.job_id,
                attempt.run_id,
                attempt.attempt_no,
                attempt.child_revision,
                attempt.request_ref,
                attempt.request_sha256,
                attempt.causal_view_ref,
                attempt.causal_view_sha256,
            )
            if receipt_binding != attempt_binding:
                raise ValueError("dispatch receipt must bind the exact child attempt")
        else:
            if self.attempt is not None:
                raise ValueError("unsuccessful dispatch receipts cannot contain attempt")
            if self.error is None:
                raise ValueError("unsuccessful dispatch receipts require error")
            if (
                self.outcome == "revision_conflict"
                and self.child_revision == self.expected_child_revision
            ):
                raise ValueError(
                    "revision_conflict requires a different child_revision"
                )
        return self


class AgentActivationTriggerRule(_FrozenReplayModel):
    """Regla determinista y versionable para un tipo de trigger."""

    trigger_type: MonitoringTriggerType
    enabled: bool = True
    priority: int = Field(default=50, ge=0, le=100)
    cooldown_source_seconds: FiniteFloat = Field(default=0.0, ge=0.0)
    coalescing_group: str | None = Field(default=None, min_length=1, max_length=160)
    rearm_policy: TriggerRearmPolicy = "after_cooldown"
    state_transition_targets: tuple[HealthState, ...] = Field(
        default_factory=tuple
    )
    requested_roles: tuple[AgentName, ...] = Field(default_factory=tuple)
    counts_toward_variable_budget: bool = True

    @field_validator("requested_roles")
    @classmethod
    def validate_requested_roles(
        cls,
        value: tuple[AgentName, ...],
    ) -> tuple[AgentName, ...]:
        if len(value) != len(set(value)):
            raise ValueError("requested_roles cannot contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_budget_classification(self) -> "AgentActivationTriggerRule":
        if not self.enabled and self.counts_toward_variable_budget:
            raise ValueError("disabled rules cannot consume variable budget")
        if self.trigger_type in {"preflight", "session_close", "manual"}:
            if self.counts_toward_variable_budget:
                raise ValueError(
                    "preflight, session_close and manual are outside variable budget"
                )
        if len(self.state_transition_targets) != len(
            set(self.state_transition_targets)
        ):
            raise ValueError("state_transition_targets cannot contain duplicates")
        if self.trigger_type == "state_transition":
            if self.enabled and not self.state_transition_targets:
                raise ValueError(
                    "enabled state_transition rules require closed target states"
                )
        elif self.state_transition_targets:
            raise ValueError(
                "state_transition_targets are only valid for state_transition"
            )
        if self.rearm_policy == "after_recovery" and self.trigger_type != (
            "persistent_alert"
        ):
            raise ValueError(
                "after_recovery is only valid for persistent_alert"
            )
        if self.rearm_policy == "once_per_session" and self.trigger_type not in {
            "preflight",
            "session_close",
        }:
            raise ValueError(
                "once_per_session is only valid for preflight or session_close"
            )
        if self.rearm_policy == "manual" and self.trigger_type != "manual":
            raise ValueError("manual rearm is only valid for manual triggers")
        if self.trigger_type == "manual" and self.rearm_policy != "manual":
            raise ValueError("manual triggers require manual rearm")
        return self


class AgentActivationPolicy(_FrozenReplayModel):
    """Politica separada del scoring para presupuestar revisiones agenticas."""

    schema_version: Literal["agent_activation_policy_v1"] = (
        "agent_activation_policy_v1"
    )
    policy_version: str = Field(min_length=1, max_length=160)
    policy_sha256: str = Field(pattern=SHA256_PATTERN)
    policy_kind: AgentActivationPolicyKind
    max_variable_child_runs: NonNegativeInt
    budget_unit: Literal["variable_child_runs"] = "variable_child_runs"
    periodic_cursors: tuple[NonNegativeInt, ...] = Field(default_factory=tuple)
    alert_entry_persistence_ticks: PositiveInt = 3
    alert_recovery_persistence_ticks: PositiveInt = 1
    trigger_rules: tuple[AgentActivationTriggerRule, ...] = Field(
        default_factory=tuple
    )
    precedence: tuple[MonitoringTriggerType, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def validate_policy(self) -> "AgentActivationPolicy":
        trigger_types = [rule.trigger_type for rule in self.trigger_rules]
        if len(trigger_types) != len(set(trigger_types)):
            raise ValueError("trigger_rules must contain unique trigger_type values")
        if len(self.precedence) != len(set(self.precedence)):
            raise ValueError("precedence cannot contain duplicates")
        undeclared = set(self.precedence) - set(trigger_types)
        if undeclared:
            raise ValueError("precedence can only reference declared trigger rules")
        if tuple(sorted(self.periodic_cursors)) != self.periodic_cursors:
            raise ValueError("periodic_cursors must be sorted and unique")
        if len(self.periodic_cursors) != len(set(self.periodic_cursors)):
            raise ValueError("periodic_cursors must be sorted and unique")

        periodic_rule = next(
            (
                rule
                for rule in self.trigger_rules
                if rule.trigger_type == "periodic_review" and rule.enabled
            ),
            None,
        )
        if self.periodic_cursors and periodic_rule is None:
            raise ValueError(
                "periodic_cursors require an enabled periodic_review rule"
            )
        if periodic_rule is not None and not self.periodic_cursors:
            raise ValueError(
                "enabled periodic_review rules require a frozen periodic schedule"
            )

        variable_rules = [
            rule
            for rule in self.trigger_rules
            if rule.enabled and rule.counts_toward_variable_budget
        ]
        if variable_rules and self.max_variable_child_runs == 0:
            raise ValueError("enabled variable rules require a positive budget")
        if (
            periodic_rule is not None
            and periodic_rule.counts_toward_variable_budget
            and len(self.periodic_cursors) > self.max_variable_child_runs
        ):
            raise ValueError("periodic schedule cannot exceed the variable budget")
        if self.policy_kind in {"P0", "P1"} and self.max_variable_child_runs != 0:
            raise ValueError("P0 and P1 cannot execute variable child runs")
        if self.policy_kind in {"P2", "P3"} and self.max_variable_child_runs == 0:
            raise ValueError("P2 and P3 require a positive variable-run budget")
        if self.policy_kind == "P2" and periodic_rule is None:
            raise ValueError("P2 requires an enabled periodic_review rule")
        if self.policy_kind == "P3" and not variable_rules:
            raise ValueError("P3 requires at least one enabled variable rule")
        enabled_types = {
            rule.trigger_type for rule in self.trigger_rules if rule.enabled
        }
        if self.policy_kind in {"P2", "P3"} and set(self.precedence) != (
            enabled_types
        ):
            raise ValueError(
                "P2/P3 precedence must include every enabled trigger rule"
            )
        if self.policy_kind in {"P2", "P3"} and any(
            rule.trigger_type
            not in {"preflight", "session_close", "manual"}
            and not rule.counts_toward_variable_budget
            for rule in self.trigger_rules
            if rule.enabled
        ):
            raise ValueError(
                "P2/P3 automatic review rules must consume variable budget"
            )
        budget_class_by_group: dict[str, bool] = {}
        for rule in self.trigger_rules:
            if not rule.enabled:
                continue
            group = rule.coalescing_group or rule.trigger_type
            previous_class = budget_class_by_group.setdefault(
                group,
                rule.counts_toward_variable_budget,
            )
            if previous_class != rule.counts_toward_variable_budget:
                raise ValueError(
                    "coalescing groups cannot mix variable and fixed reviews"
                )
        if self.policy_kind in {"P2", "P3"} and any(
            not rule.requested_roles for rule in variable_rules
        ):
            raise ValueError(
                "P2/P3 variable rules require an explicit requested_roles mapping"
            )
        return self


class MonitoringTriggerEvent(_FrozenReplayModel):
    """Transicion append-only del ciclo de vida de un trigger causal."""

    schema_version: Literal["monitoring_trigger_event_v1"] = (
        "monitoring_trigger_event_v1"
    )
    event_id: str = Field(min_length=1, max_length=240)
    trigger_id: str = Field(min_length=1, max_length=240)
    session_id: str = Field(min_length=1, max_length=160)
    sequence: PositiveInt
    lifecycle_revision: PositiveInt = 1
    previous_event_id: str | None = Field(default=None, min_length=1, max_length=240)
    trigger_type: MonitoringTriggerType
    lifecycle_status: MonitoringTriggerLifecycle
    priority: int = Field(ge=0, le=100)
    reason_code: MonitoringTriggerReasonCode
    reason: str = Field(min_length=1)
    episode_id: str | None = Field(default=None, min_length=1, max_length=240)
    asset_id: str | None = Field(default=None, min_length=1, max_length=160)
    snapshot_start_id: str | None = Field(default=None, min_length=1, max_length=240)
    snapshot_end_id: str | None = Field(default=None, min_length=1, max_length=240)
    condition_start_cursor: NonNegativeInt | None = None
    cutoff_cursor: NonNegativeInt | None = None
    cutoff_source_time: datetime | None = None
    previous_state: HealthState | None = None
    new_state: HealthState | None = None
    cooldown_source_seconds: FiniteFloat = Field(default=0.0, ge=0.0)
    coalescing_group: str | None = Field(default=None, min_length=1, max_length=160)
    rearm_policy: TriggerRearmPolicy
    requested_roles: tuple[AgentName, ...] = Field(default_factory=tuple)
    counts_toward_variable_budget: bool
    budget_reservation_index: PositiveInt | None = None
    dedupe_key: str = Field(min_length=1, max_length=240)
    activation_version: str = Field(min_length=1, max_length=160)
    activation_policy_sha256: str = Field(pattern=SHA256_PATTERN)
    origin_tick_id: str | None = Field(default=None, min_length=1, max_length=240)
    frame_ids: tuple[str, ...] = Field(default_factory=tuple)
    evidence_refs: tuple[str, ...] = Field(default_factory=tuple)
    suppressed_by_trigger_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=240,
    )
    suppression_reason: MonitoringTriggerSuppressionReason | None = None
    coalesced_into_trigger_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=240,
    )
    child_run_id: str | None = Field(default=None, min_length=1, max_length=240)
    recorded_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("frame_ids", "evidence_refs")
    @classmethod
    def validate_unique_refs(
        cls,
        value: tuple[str, ...],
        info,
    ) -> tuple[str, ...]:
        return _require_unique_non_blank(value, info.field_name)

    @field_validator("requested_roles")
    @classmethod
    def validate_event_roles(
        cls,
        value: tuple[AgentName, ...],
    ) -> tuple[AgentName, ...]:
        if len(value) != len(set(value)):
            raise ValueError("requested_roles cannot contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_causal_event(self) -> "MonitoringTriggerEvent":
        if (self.snapshot_start_id is None) != (self.snapshot_end_id is None):
            raise ValueError(
                "snapshot_start_id and snapshot_end_id must be both set or both null"
            )
        if self.trigger_type == "preflight":
            if any(
                value is not None
                for value in (
                    self.origin_tick_id,
                    self.cutoff_cursor,
                    self.condition_start_cursor,
                    self.cutoff_source_time,
                    self.snapshot_start_id,
                    self.snapshot_end_id,
                )
            ) or self.frame_ids:
                raise ValueError("preflight cannot reference a replay tick or cutoff")
        else:
            required = (
                self.origin_tick_id,
                self.condition_start_cursor,
                self.cutoff_cursor,
                self.cutoff_source_time,
                self.snapshot_start_id,
                self.snapshot_end_id,
            )
            if any(value is None for value in required):
                raise ValueError(
                    "non-preflight triggers require tick, cutoff and snapshot range"
                )
            if self.condition_start_cursor > self.cutoff_cursor:
                raise ValueError(
                    "condition_start_cursor cannot exceed cutoff_cursor"
                )

        if (self.previous_state is None) != (self.new_state is None):
            raise ValueError(
                "previous_state and new_state must be both set or both null"
            )
        if self.trigger_type == "state_transition":
            if self.previous_state is None or self.new_state is None:
                raise ValueError(
                    "state_transition requires previous_state and new_state"
                )
            if self.previous_state == self.new_state:
                raise ValueError("state_transition requires two different states")

        if self.lifecycle_status == "suppressed":
            if self.suppression_reason is None:
                raise ValueError("suppressed events require suppression_reason")
            if (
                self.suppression_reason
                in {"cooldown", "not_rearmed", "episode_already_covered"}
                and self.suppressed_by_trigger_id is None
            ):
                raise ValueError(
                    "cooldown, not_rearmed and covered-episode events require "
                    "suppressed_by_trigger_id"
                )
        elif (
            self.suppressed_by_trigger_id is not None
            or self.suppression_reason is not None
        ):
            raise ValueError(
                "suppression fields are only valid for suppressed events"
            )
        if self.lifecycle_status == "coalesced":
            if self.coalesced_into_trigger_id is None:
                raise ValueError(
                    "coalesced events require coalesced_into_trigger_id"
                )
        elif self.coalesced_into_trigger_id is not None:
            raise ValueError(
                "coalesced_into_trigger_id is only valid for coalesced events"
            )
        if self.suppressed_by_trigger_id == self.trigger_id:
            raise ValueError("a trigger cannot suppress itself")
        if self.coalesced_into_trigger_id == self.trigger_id:
            raise ValueError("a trigger cannot coalesce into itself")
        if self.child_run_id is not None and self.lifecycle_status not in {
            "dispatched",
            "running",
            "resolved",
            "failed",
        }:
            raise ValueError(
                "child_run_id requires a dispatched, running, resolved or failed event"
            )
        if (
            self.lifecycle_status == "emitted"
            and self.counts_toward_variable_budget
        ):
            if self.budget_reservation_index is None:
                raise ValueError(
                    "emitted variable triggers require a budget reservation"
                )
        elif self.budget_reservation_index is not None:
            raise ValueError(
                "only emitted variable triggers reserve a budget slot"
            )
        return self


class ReplayStepCommand(_FrozenReplayModel):
    """Peticion CAS para avanzar exactamente un tick de forma idempotente."""

    schema_version: Literal["monitoring_replay_step_command_v1"] = (
        "monitoring_replay_step_command_v1"
    )
    command: Literal["step"] = "step"
    command_id: str = Field(min_length=1, max_length=240)
    session_id: str = Field(min_length=1, max_length=160)
    expected_revision: NonNegativeInt
    issued_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))


class ReplayStepReceipt(_FrozenReplayModel):
    """Resultado trazable de aplicar, repetir o rechazar un comando step."""

    schema_version: Literal["monitoring_replay_step_receipt_v1"] = (
        "monitoring_replay_step_receipt_v1"
    )
    command_id: str = Field(min_length=1, max_length=240)
    session_id: str = Field(min_length=1, max_length=160)
    expected_revision: NonNegativeInt
    outcome: ReplayStepOutcome
    accepted_revision: NonNegativeInt
    tick_id: str | None = Field(default=None, min_length=1, max_length=240)
    reason: str | None = Field(default=None, min_length=1)
    recorded_at: AwareDatetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_receipt(self) -> "ReplayStepReceipt":
        if self.outcome in {"applied", "idempotent_replay"}:
            if self.tick_id is None:
                raise ValueError("successful step receipts require tick_id")
            if self.accepted_revision != self.expected_revision + 1:
                raise ValueError(
                    "successful step receipts must advance exactly one revision"
                )
            if self.reason is not None:
                raise ValueError("successful step receipts cannot declare reason")
        else:
            if self.tick_id is not None:
                raise ValueError("non-successful step receipts cannot declare tick_id")
            if self.reason is None:
                raise ValueError("non-successful step receipts require reason")
            if (
                self.outcome == "revision_conflict"
                and self.accepted_revision == self.expected_revision
            ):
                raise ValueError(
                    "revision_conflict requires a different accepted_revision"
                )
        return self
