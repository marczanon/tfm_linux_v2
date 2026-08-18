"""Exportacion post-hoc, trazable y no operativa de la campana NASA P3.

Este modulo no avanza el replay, no despacha revisiones y no consulta un LLM.
Su unica responsabilidad es prerregistrar una receta visual y, una vez cerrada
la campana oficial, convertir sus artefactos ya validados en una linea temporal
2D portable. La secuencia resultante es una vista derivada; la fuente de verdad
continua siendo la campana, la cadena de commits y las runs hijas.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import uuid
import fcntl
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, Literal

from pydantic import AwareDatetime, ConfigDict, Field, model_validator

from codigo.app.schemas.agent_decisions import AgentName
from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.monitoring_replay import (
    CausalEvidenceCatalog,
    MonitoringAnalysisStatus,
    MonitoringPolicyProposal,
    MonitoringReviewResult,
    MonitoringTriggerReasonCode,
    MonitoringTriggerType,
)
from codigo.app.schemas.temporal_health import HealthState
from codigo.app.services.monitoring_evidence_campaign import (
    DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_ID,
    DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_OUTPUT_DIR,
    MonitoringEvidenceCampaignPlan,
    MonitoringEvidenceCampaignPublished,
    load_published_monitoring_evidence_campaign,
)
from codigo.app.services.monitoring_replay import (
    DEFAULT_MONITORING_SESSIONS_DIR,
    MonitoringReplayStore,
)
from codigo.app.services.run_persistence import (
    DEFAULT_RUNS_DIR,
    load_run_runtime_events,
    load_run_snapshot,
)


OFFICIAL_CAMPAIGN_PLAN_SHA256 = (
    "2c6b1ad76904bac23970e35965fade6eac883d31b6c1c6ef8e4200b4ea65b95e"
)
DEFAULT_MONITORING_CINEMATIC_OUTPUT_DIR = Path(
    "codigo/reports/validation/monitoring_cinematic"
)
MONITORING_CINEMATIC_RENDERER_ID = "monitoring_cinematic_2d_v1"
ZERO_SHA256 = "0" * 64
EXPECTED_TICK_BEATS = 689
EXPECTED_TRIGGER_BEATS = 4
EXPECTED_DECISION_BEATS = 28
EXPECTED_PROPOSAL_BEATS = 4
EXPECTED_VERDICT_BEATS = 1
EXPECTED_BEATS = 726
EXPECTED_VIDEO_FRAMES = 1121
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")


BeatKind = Literal[
    "tick",
    "trigger",
    "agent_decision",
    "policy_proposal",
    "final_verdict",
]
DisplayPhase = Literal["pre_roll", "agentic_window", "closing"]


def _json_sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    ).encode("utf-8")


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class _HashedCinematicModel(StrictBaseModel):
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


class MonitoringCinematicStoryRecipe(StrictBaseModel):
    model_config = ConfigDict(frozen=True)
    include_all_689_ticks: Literal[True] = True
    tick_duration_frames: Literal[1] = 1
    trigger_duration_frames: Literal[12] = 12
    decision_duration_frames: Literal[9] = 9
    proposal_duration_frames: Literal[24] = 24
    verdict_duration_frames: Literal[36] = 36


class MonitoringCinematicCapturePlan(_HashedCinematicModel):
    """Receta visual congelada antes del comienzo de la campana oficial."""

    _hash_field = "capture_plan_sha256"
    schema_version: Literal["monitoring_cinematic_capture_plan_v1"] = (
        "monitoring_cinematic_capture_plan_v1"
    )
    capture_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
    campaign_id: Literal["nasa-p3-agentic-window-56h-v1"] = (
        DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_ID
    )
    campaign_session_id: str = Field(min_length=1, max_length=220)
    campaign_plan_sha256: Literal[
        "2c6b1ad76904bac23970e35965fade6eac883d31b6c1c6ef8e4200b4ea65b95e"
    ] = OFFICIAL_CAMPAIGN_PLAN_SHA256
    renderer_id: Literal["monitoring_cinematic_2d_v1"] = (
        MONITORING_CINEMATIC_RENDERER_ID
    )
    viewport_width: Literal[1920] = 1920
    viewport_height: Literal[1080] = 1080
    device_scale_factor: Literal[1] = 1
    locale: Literal["es-ES"] = "es-ES"
    color_scheme: Literal["light"] = "light"
    reduced_motion: Literal[True] = True
    fps: Literal[12] = 12
    story_recipe: MonitoringCinematicStoryRecipe = Field(
        default_factory=MonitoringCinematicStoryRecipe
    )
    keyframes: tuple[str, ...] = (
        "tick:000",
        "tick:352",
        "trigger:353",
        "tick:496",
        "trigger:498",
        "trigger:499",
        "trigger:688",
        "final_verdict",
    )
    expected_tick_beat_count: Literal[689] = EXPECTED_TICK_BEATS
    expected_trigger_beat_count: Literal[4] = EXPECTED_TRIGGER_BEATS
    expected_decision_beat_count: Literal[28] = EXPECTED_DECISION_BEATS
    expected_proposal_beat_count: Literal[4] = EXPECTED_PROPOSAL_BEATS
    expected_verdict_beat_count: Literal[1] = EXPECTED_VERDICT_BEATS
    expected_beat_count: Literal[726] = EXPECTED_BEATS
    expected_video_frame_count: Literal[1121] = EXPECTED_VIDEO_FRAMES
    source_sha256s: dict[str, str]
    capture_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_closed_recipe(self):
        expected_frames = (
            self.expected_tick_beat_count * self.story_recipe.tick_duration_frames
            + self.expected_trigger_beat_count
            * self.story_recipe.trigger_duration_frames
            + self.expected_decision_beat_count
            * self.story_recipe.decision_duration_frames
            + self.expected_proposal_beat_count
            * self.story_recipe.proposal_duration_frames
            + self.expected_verdict_beat_count
            * self.story_recipe.verdict_duration_frames
        )
        if expected_frames != self.expected_video_frame_count:
            raise ValueError("cinematic frame budget does not match story recipe")
        if self.keyframes != (
            "tick:000",
            "tick:352",
            "trigger:353",
            "tick:496",
            "trigger:498",
            "trigger:499",
            "trigger:688",
            "final_verdict",
        ):
            raise ValueError("cinematic keyframes must match the frozen story")
        if not self.source_sha256s or any(
            not reference
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            for reference, digest in self.source_sha256s.items()
        ):
            raise ValueError("cinematic source hashes must be complete")
        return self


class MonitoringCinematicPreregistration(_HashedCinematicModel):
    _hash_field = "registration_sha256"
    schema_version: Literal["monitoring_cinematic_preregistration_v1"] = (
        "monitoring_cinematic_preregistration_v1"
    )
    capture_id: str = Field(min_length=1, max_length=200)
    campaign_id: str = Field(min_length=1, max_length=140)
    campaign_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture_plan_ref: str = Field(min_length=1)
    capture_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registered_at: AwareDatetime


class MonitoringCinematicAssetProjection(StrictBaseModel):
    model_config = ConfigDict(frozen=True)
    asset_id: str = Field(min_length=1)
    asset_label: str = Field(min_length=1)
    channel_id: str = Field(min_length=1)
    analysis_status: MonitoringAnalysisStatus
    analysis_label: str = Field(min_length=1)
    signal_rms: float | None = Field(default=None, ge=0.0)
    signal_peak_abs: float | None = Field(default=None, ge=0.0)
    health_index: float | None = Field(default=None, ge=0.0, le=100.0)
    risk_index: float | None = Field(default=None, ge=0.0, le=100.0)
    health_state: HealthState | None = None
    health_state_label: str | None = None
    score: float | None = None
    threshold: float | None = None
    score_ratio: float | None = None
    gap_detected: bool

    @model_validator(mode="after")
    def validate_semantics(self):
        diagnostic = (
            self.health_index,
            self.risk_index,
            self.health_state,
            self.health_state_label,
            self.score,
            self.threshold,
            self.score_ratio,
        )
        if self.analysis_status == "modeled":
            if any(value is None for value in diagnostic):
                raise ValueError("modeled cinematic assets require diagnostics")
        elif any(value is not None for value in diagnostic):
            raise ValueError("non-modeled cinematic assets cannot imply health")
        if (self.signal_rms is None) != (self.signal_peak_abs is None):
            raise ValueError("telemetry values must appear together")
        return self


class MonitoringCinematicTriggerProjection(StrictBaseModel):
    model_config = ConfigDict(frozen=True)
    ordinal: int = Field(ge=1, le=4)
    trigger_type: MonitoringTriggerType
    trigger_type_label: str = Field(min_length=1)
    reason_code: MonitoringTriggerReasonCode
    summary: str = Field(min_length=1)
    condition_start_cursor: int = Field(ge=0)
    cutoff_cursor: int = Field(ge=0)


class MonitoringCinematicDecisionProjection(StrictBaseModel):
    model_config = ConfigDict(frozen=True)
    agent_name: AgentName
    role_label: str = Field(min_length=1)
    hypothesis: str = Field(min_length=1)
    expected_observation: str = Field(min_length=1)
    falsification_criterion: str = Field(min_length=1)
    recommended_action: str = Field(min_length=1)
    action_label: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_handles: tuple[str, ...] = Field(min_length=1)
    generation_origin: str = Field(min_length=1)
    generation_validation_status: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_handles(self):
        if len(self.evidence_handles) != len(set(self.evidence_handles)) or any(
            not re.fullmatch(r"E(?:0[1-9]|[1-9][0-9])", handle)
            for handle in self.evidence_handles
        ):
            raise ValueError("cinematic evidence handles must be unique E01..E99")
        return self


class MonitoringCinematicProposalProjection(StrictBaseModel):
    model_config = ConfigDict(frozen=True)
    status: str = Field(min_length=1)
    agreement_status: str = Field(min_length=1)
    agreement_label: str = Field(min_length=1)
    application_status: Literal["not_applied"] = "not_applied"
    aggregate_action: str | None = None
    action_counts: dict[str, int]
    human_review_recommended: bool

    @model_validator(mode="after")
    def validate_action_counts(self):
        if sum(self.action_counts.values()) != 7 or any(
            count <= 0 for count in self.action_counts.values()
        ):
            raise ValueError("proposal action counts must cover seven roles")
        return self


class MonitoringCinematicVerdictProjection(StrictBaseModel):
    model_config = ConfigDict(frozen=True)
    operational: Literal["passed", "blocked"]
    agentic: Literal["passed", "blocked"]
    evidence: Literal["passed", "blocked"]
    blockers: tuple[str, ...] = ()


class MonitoringCinematicDisplayProjection(StrictBaseModel):
    """Proyeccion estable que la UI consume sin reinterpretar artefactos."""

    model_config = ConfigDict(frozen=True)
    schema_version: Literal["monitoring_cinematic_display_v1"] = (
        "monitoring_cinematic_display_v1"
    )
    title: str = Field(min_length=1)
    subtitle: str = Field(min_length=1)
    phase: DisplayPhase
    cursor: int = Field(ge=0, le=688)
    source_time: datetime
    assets: tuple[MonitoringCinematicAssetProjection, ...] = Field(
        min_length=4,
        max_length=4,
    )
    trigger: MonitoringCinematicTriggerProjection | None = None
    decision: MonitoringCinematicDecisionProjection | None = None
    proposal: MonitoringCinematicProposalProjection | None = None
    verdict: MonitoringCinematicVerdictProjection | None = None


class MonitoringCinematicBeat(_HashedCinematicModel):
    _hash_field = "beat_sha256"
    schema_version: Literal["monitoring_cinematic_beat_v1"] = (
        "monitoring_cinematic_beat_v1"
    )
    beat_index: int = Field(ge=0, le=725)
    kind: BeatKind
    duration_frames: int = Field(gt=0)
    campaign_id: str = Field(min_length=1)
    session_id: str = Field(min_length=1)
    cursor: int = Field(ge=0, le=688)
    source_time: datetime
    wall_time: AwareDatetime | None = None
    tick_id: str = Field(min_length=1)
    replay_commit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    trigger_id: str | None = None
    child_run_id: str | None = None
    event_id: str | None = None
    decision_id: str | None = None
    decision_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    proposal_id: str | None = None
    proposal_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    previous_beat_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    beat_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    display_projection: MonitoringCinematicDisplayProjection

    @model_validator(mode="after")
    def validate_kind_projection(self):
        projection = self.display_projection
        expected_duration = {
            "tick": 1,
            "trigger": 12,
            "agent_decision": 9,
            "policy_proposal": 24,
            "final_verdict": 36,
        }[self.kind]
        if self.duration_frames != expected_duration:
            raise ValueError("beat duration does not match the frozen recipe")
        presence = (
            projection.trigger is not None,
            projection.decision is not None,
            projection.proposal is not None,
            projection.verdict is not None,
        )
        expected_presence = {
            "tick": (False, False, False, False),
            "trigger": (True, False, False, False),
            "agent_decision": (True, True, False, False),
            "policy_proposal": (True, False, True, False),
            "final_verdict": (False, False, False, True),
        }[self.kind]
        if presence != expected_presence:
            raise ValueError("beat kind and display projection are inconsistent")
        identity_presence = (
            self.trigger_id is not None,
            self.child_run_id is not None,
            self.event_id is not None,
            self.decision_id is not None,
            self.decision_sha256 is not None,
            self.proposal_id is not None,
            self.proposal_sha256 is not None,
        )
        expected_identities = {
            "tick": (False, False, False, False, False, False, False),
            "trigger": (True, True, True, False, False, False, False),
            "agent_decision": (True, True, True, True, True, False, False),
            "policy_proposal": (True, True, True, False, False, True, True),
            "final_verdict": (False, False, False, False, False, False, False),
        }[self.kind]
        if identity_presence != expected_identities:
            raise ValueError("beat kind and trace identities are inconsistent")
        if projection.cursor != self.cursor or projection.source_time != self.source_time:
            raise ValueError("beat display must preserve cursor and source time")
        return self


class MonitoringCinematicDecisionMaterial(StrictBaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: str
    event_sequence: int = Field(ge=0)
    decision_id: str
    decision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    wall_time: AwareDatetime
    projection: MonitoringCinematicDecisionProjection


class MonitoringCinematicProposalMaterial(StrictBaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: str
    event_sequence: int = Field(ge=0)
    proposal_id: str
    proposal_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    wall_time: AwareDatetime
    projection: MonitoringCinematicProposalProjection


class MonitoringCinematicReviewMaterial(StrictBaseModel):
    model_config = ConfigDict(frozen=True)
    ordinal: int = Field(ge=1, le=4)
    cursor: int = Field(ge=0, le=688)
    source_time: datetime
    tick_id: str
    trigger_id: str
    trigger_event_id: str
    trigger_wall_time: AwareDatetime
    child_run_id: str
    trigger: MonitoringCinematicTriggerProjection
    decisions: tuple[MonitoringCinematicDecisionMaterial, ...] = Field(
        min_length=7,
        max_length=7,
    )
    proposal: MonitoringCinematicProposalMaterial

    @model_validator(mode="after")
    def validate_runtime_order(self):
        sequences = tuple(item.event_sequence for item in self.decisions)
        if len(sequences) != len(set(sequences)):
            raise ValueError("cinematic decision runtime sequences must be unique")
        if self.proposal.event_sequence <= max(sequences):
            raise ValueError("cinematic proposal must follow all role decisions")
        return self


class MonitoringCinematicTickMaterial(StrictBaseModel):
    model_config = ConfigDict(frozen=True)
    cursor: int = Field(ge=0, le=688)
    source_time: datetime
    wall_time: AwareDatetime
    tick_id: str
    commit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    assets: tuple[MonitoringCinematicAssetProjection, ...] = Field(
        min_length=4,
        max_length=4,
    )


class MonitoringCinematicInputArtifact(StrictBaseModel):
    model_config = ConfigDict(frozen=True)
    input_role: str = Field(min_length=1)
    path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=0)


class MonitoringCinematicManifest(_HashedCinematicModel):
    _hash_field = "manifest_sha256"
    schema_version: Literal["monitoring_cinematic_manifest_v1"] = (
        "monitoring_cinematic_manifest_v1"
    )
    capture_id: str
    campaign_id: str
    session_id: str
    campaign_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    campaign_result_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    campaign_publication_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    capture_plan_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    registration_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    terminal_commit_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    generated_at: AwareDatetime
    inputs: tuple[MonitoringCinematicInputArtifact, ...] = Field(
        min_length=19,
        max_length=19,
    )
    timeline_path: str
    timeline_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    timeline_size_bytes: int = Field(gt=0)
    tick_beat_count: Literal[689] = EXPECTED_TICK_BEATS
    trigger_beat_count: Literal[4] = EXPECTED_TRIGGER_BEATS
    decision_beat_count: Literal[28] = EXPECTED_DECISION_BEATS
    proposal_beat_count: Literal[4] = EXPECTED_PROPOSAL_BEATS
    verdict_beat_count: Literal[1] = EXPECTED_VERDICT_BEATS
    beat_count: Literal[726] = EXPECTED_BEATS
    video_frame_count: Literal[1121] = EXPECTED_VIDEO_FRAMES
    fps: Literal[12] = 12
    viewport_width: Literal[1920] = 1920
    viewport_height: Literal[1080] = 1080
    semantic_reproducibility: Literal[
        "timeline_canonical_pixels_environment_bound"
    ] = "timeline_canonical_pixels_environment_bound"
    operational_verdict: Literal["passed", "blocked"]
    agentic_verdict: Literal["passed", "blocked"]
    evidence_verdict: Literal["passed", "blocked"]
    manifest_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def validate_input_roles(self):
        expected = [
            "campaign_publication",
            "campaign_result",
            "session_terminal_commit",
        ]
        for ordinal in range(1, 5):
            expected.extend(
                [
                    f"child_{ordinal:02d}_review_result",
                    f"child_{ordinal:02d}_runtime_events",
                    f"child_{ordinal:02d}_policy_proposal",
                    f"child_{ordinal:02d}_evidence_catalog",
                ]
            )
        if [item.input_role for item in self.inputs] != expected:
            raise ValueError("cinematic manifest inputs must use canonical order")
        return self


class MonitoringCinematicArtifacts(StrictBaseModel):
    output_dir: str
    capture_plan_path: str
    preregistration_path: str
    timeline_path: str
    manifest_path: str
    checksums_path: str
    manifest: MonitoringCinematicManifest


def _with_hash(model_cls, payload: Mapping[str, Any]):
    values = dict(payload)
    values[model_cls._hash_field] = model_cls.canonical_sha256(values)
    return model_cls.model_validate(values)


def _cinematic_source_hashes() -> dict[str, str]:
    references = {
        "codigo/app/services/monitoring_cinematic_export.py",
        "codigo/scripts/export_monitoring_campaign_cinematic.py",
        "codigo/frontend/scripts/capture-monitoring-cinematic.mjs",
        "codigo/frontend/src/App.tsx",
        "codigo/frontend/src/api.ts",
        "codigo/frontend/src/components/monitoring/MonitoringView.tsx",
        "codigo/frontend/src/components/monitoring/MonitoringReplayChart.tsx",
        "codigo/frontend/src/lib/agentRuntime.ts",
        "codigo/frontend/src/lib/agentStory.ts",
        "codigo/frontend/src/lib/monitoringCinematic.ts",
        "codigo/frontend/src/styles.css",
        "codigo/frontend/src/types.ts",
        "codigo/frontend/src/types/ui.ts",
        "codigo/frontend/package.json",
        "codigo/frontend/package-lock.json",
    }
    monitoring_dir = _PROJECT_ROOT / "codigo/frontend/src/components/monitoring"
    if monitoring_dir.is_dir():
        references.update(
            path.relative_to(_PROJECT_ROOT).as_posix()
            for path in monitoring_dir.glob("*Cinematic*.tsx")
        )
    hashes: dict[str, str] = {}
    for reference in sorted(references):
        path = _PROJECT_ROOT / reference
        if not path.is_file() or path.is_symlink():
            raise FileNotFoundError(f"cinematic renderer source missing: {reference}")
        hashes[reference] = _file_sha256(path)
    return hashes


def default_monitoring_cinematic_capture_plan(
    campaign_plan: MonitoringEvidenceCampaignPlan,
    *,
    capture_id: str | None = None,
) -> MonitoringCinematicCapturePlan:
    if (
        campaign_plan.campaign_id != DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_ID
        or campaign_plan.plan_sha256 != OFFICIAL_CAMPAIGN_PLAN_SHA256
    ):
        raise ValueError("cinematic export is bound to the official campaign plan")
    resolved_capture_id = capture_id or f"{campaign_plan.campaign_id}-cinematic-2d-v1"
    return _with_hash(
        MonitoringCinematicCapturePlan,
        {
            "capture_id": resolved_capture_id,
            "campaign_id": campaign_plan.campaign_id,
            "campaign_session_id": campaign_plan.session_id,
            "campaign_plan_sha256": campaign_plan.plan_sha256,
            "source_sha256s": _cinematic_source_hashes(),
        },
    )


def preregister_monitoring_cinematic_capture(
    plan: MonitoringCinematicCapturePlan,
    *,
    output_root: Path | str = DEFAULT_MONITORING_CINEMATIC_OUTPUT_DIR,
    registered_at: datetime | None = None,
) -> MonitoringCinematicPreregistration:
    destination = _capture_dir(output_root, plan.capture_id)
    root = Path(output_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".preregistration.lock").open("a+b") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        destination.mkdir(parents=True, exist_ok=True)
        plan_path = destination / "capture_plan.json"
        registration_path = destination / "preregistration.json"
        if plan_path.exists() or registration_path.exists():
            if not plan_path.is_file() or not registration_path.is_file():
                raise ValueError(
                    "cinematic preregistration paths must be regular files"
                )
            existing_plan = MonitoringCinematicCapturePlan.model_validate(
                _read_json(plan_path)
            )
            existing_registration = MonitoringCinematicPreregistration.model_validate(
                _read_json(registration_path)
            )
            if existing_plan != plan or (
                existing_registration.capture_plan_sha256
                != plan.capture_plan_sha256
                or existing_registration.capture_id != plan.capture_id
            ):
                raise ValueError(
                    "cinematic capture identity is already preregistered"
                )
            return existing_registration
        _write_json_atomic(plan_path, plan.model_dump(mode="json"))
        registration = _with_hash(
            MonitoringCinematicPreregistration,
            {
                "capture_id": plan.capture_id,
                "campaign_id": plan.campaign_id,
                "campaign_plan_sha256": plan.campaign_plan_sha256,
                "capture_plan_ref": plan_path.as_posix(),
                "capture_plan_sha256": plan.capture_plan_sha256,
                "registered_at": registered_at or datetime.now(UTC),
            },
        )
        _write_json_atomic(
            registration_path,
            registration.model_dump(mode="json"),
        )
        return registration


def load_monitoring_cinematic_preregistration(
    capture_id: str,
    *,
    output_root: Path | str = DEFAULT_MONITORING_CINEMATIC_OUTPUT_DIR,
) -> tuple[MonitoringCinematicCapturePlan, MonitoringCinematicPreregistration]:
    destination = _capture_dir(output_root, capture_id)
    plan_path = destination / "capture_plan.json"
    registration_path = destination / "preregistration.json"
    plan = MonitoringCinematicCapturePlan.model_validate(_read_json(plan_path))
    registration = MonitoringCinematicPreregistration.model_validate(
        _read_json(registration_path)
    )
    if (
        registration.capture_id != plan.capture_id
        or registration.campaign_id != plan.campaign_id
        or registration.campaign_plan_sha256 != plan.campaign_plan_sha256
        or registration.capture_plan_sha256 != plan.capture_plan_sha256
        or Path(registration.capture_plan_ref).resolve() != plan_path.resolve()
    ):
        raise ValueError("cinematic preregistration binding is invalid")
    return plan, registration


def validate_monitoring_cinematic_sources(
    plan: MonitoringCinematicCapturePlan,
) -> None:
    for reference, expected_sha256 in plan.source_sha256s.items():
        path = _PROJECT_ROOT / reference
        if not path.is_file() or path.is_symlink() or _file_sha256(path) != expected_sha256:
            raise ValueError(f"cinematic renderer source changed: {reference}")


def build_monitoring_cinematic_timeline(
    *,
    campaign_id: str,
    session_id: str,
    ticks: Sequence[MonitoringCinematicTickMaterial],
    reviews: Sequence[MonitoringCinematicReviewMaterial],
    operational_verdict: Literal["passed", "blocked"],
    agentic_verdict: Literal["passed", "blocked"],
    evidence_verdict: Literal["passed", "blocked"],
    blockers: Sequence[str] = (),
    completed_at: datetime | None = None,
) -> tuple[MonitoringCinematicBeat, ...]:
    if len(ticks) != EXPECTED_TICK_BEATS or tuple(
        item.cursor for item in ticks
    ) != tuple(range(EXPECTED_TICK_BEATS)):
        raise ValueError("cinematic timeline requires exact cursors 0..688")
    if len(reviews) != EXPECTED_TRIGGER_BEATS or tuple(
        item.ordinal for item in reviews
    ) != (1, 2, 3, 4):
        raise ValueError("cinematic timeline requires four ordered reviews")
    if tuple(item.cursor for item in reviews) != (353, 498, 499, 688):
        raise ValueError("cinematic reviews do not match frozen P3 cutoffs")
    review_by_cursor = {item.cursor: item for item in reviews}
    beats: list[MonitoringCinematicBeat] = []
    previous_sha = ZERO_SHA256

    def append(
        kind: BeatKind,
        tick: MonitoringCinematicTickMaterial,
        display: MonitoringCinematicDisplayProjection,
        *,
        wall_time: datetime | None,
        trigger_id: str | None = None,
        child_run_id: str | None = None,
        event_id: str | None = None,
        decision_id: str | None = None,
        decision_sha256: str | None = None,
        proposal_id: str | None = None,
        proposal_sha256: str | None = None,
    ) -> None:
        nonlocal previous_sha
        payload = {
            "beat_index": len(beats),
            "kind": kind,
            "duration_frames": {
                "tick": 1,
                "trigger": 12,
                "agent_decision": 9,
                "policy_proposal": 24,
                "final_verdict": 36,
            }[kind],
            "campaign_id": campaign_id,
            "session_id": session_id,
            "cursor": tick.cursor,
            "source_time": tick.source_time,
            "wall_time": wall_time,
            "tick_id": tick.tick_id,
            "replay_commit_sha256": tick.commit_sha256,
            "trigger_id": trigger_id,
            "child_run_id": child_run_id,
            "event_id": event_id,
            "decision_id": decision_id,
            "decision_sha256": decision_sha256,
            "proposal_id": proposal_id,
            "proposal_sha256": proposal_sha256,
            "previous_beat_sha256": previous_sha,
            "display_projection": display,
        }
        beat = _with_hash(MonitoringCinematicBeat, payload)
        beats.append(beat)
        previous_sha = beat.beat_sha256

    for tick in ticks:
        phase: DisplayPhase = "pre_roll" if tick.cursor <= 352 else "agentic_window"
        modeled = next(item for item in tick.assets if item.analysis_status == "modeled")
        append(
            "tick",
            tick,
            MonitoringCinematicDisplayProjection(
                title=f"Rodamiento 1 · {modeled.health_state_label}",
                subtitle=(
                    "Pre-roll causal · todavía sin revisión agéntica"
                    if phase == "pre_roll"
                    else "Ventana agéntica · estado algorítmico, no diagnóstico físico"
                ),
                phase=phase,
                cursor=tick.cursor,
                source_time=tick.source_time,
                assets=tick.assets,
            ),
            wall_time=tick.wall_time,
        )
        review = review_by_cursor.get(tick.cursor)
        if review is None:
            continue
        append(
            "trigger",
            tick,
            MonitoringCinematicDisplayProjection(
                title=f"Trigger {review.ordinal} · {review.trigger.trigger_type_label}",
                subtitle=review.trigger.summary,
                phase="agentic_window",
                cursor=tick.cursor,
                source_time=tick.source_time,
                assets=tick.assets,
                trigger=review.trigger,
            ),
            wall_time=review.trigger_wall_time,
            trigger_id=review.trigger_id,
            child_run_id=review.child_run_id,
            event_id=review.trigger_event_id,
        )
        for decision in sorted(
            review.decisions,
            key=lambda item: item.event_sequence,
        ):
            append(
                "agent_decision",
                tick,
                MonitoringCinematicDisplayProjection(
                    title=f"{decision.projection.role_label} formula una hipótesis",
                    subtitle=decision.projection.hypothesis,
                    phase="agentic_window",
                    cursor=tick.cursor,
                    source_time=tick.source_time,
                    assets=tick.assets,
                    trigger=review.trigger,
                    decision=decision.projection,
                ),
                wall_time=decision.wall_time,
                trigger_id=review.trigger_id,
                child_run_id=review.child_run_id,
                event_id=decision.event_id,
                decision_id=decision.decision_id,
                decision_sha256=decision.decision_sha256,
            )
        proposal = review.proposal
        append(
            "policy_proposal",
            tick,
            MonitoringCinematicDisplayProjection(
                title=f"Propuesta consultiva · {proposal.projection.agreement_label}",
                subtitle="La recomendación queda registrada y no se aplica.",
                phase="agentic_window",
                cursor=tick.cursor,
                source_time=tick.source_time,
                assets=tick.assets,
                trigger=review.trigger,
                proposal=proposal.projection,
            ),
            wall_time=proposal.wall_time,
            trigger_id=review.trigger_id,
            child_run_id=review.child_run_id,
            event_id=proposal.event_id,
            proposal_id=proposal.proposal_id,
            proposal_sha256=proposal.proposal_sha256,
        )

    final_tick = ticks[-1]
    append(
        "final_verdict",
        final_tick,
        MonitoringCinematicDisplayProjection(
            title="Cierre de la campaña de evidencia",
            subtitle="Cierre del replay histórico; no acredita un fallo físico.",
            phase="closing",
            cursor=final_tick.cursor,
            source_time=final_tick.source_time,
            assets=final_tick.assets,
            verdict=MonitoringCinematicVerdictProjection(
                operational=operational_verdict,
                agentic=agentic_verdict,
                evidence=evidence_verdict,
                blockers=tuple(blockers),
            ),
        ),
        wall_time=completed_at,
    )
    _validate_timeline(beats)
    return tuple(beats)


def export_monitoring_cinematic(
    plan: MonitoringCinematicCapturePlan,
    registration: MonitoringCinematicPreregistration,
    *,
    campaign_output_root: Path | str = DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_OUTPUT_DIR,
    output_root: Path | str = DEFAULT_MONITORING_CINEMATIC_OUTPUT_DIR,
    sessions_root: Path | str = DEFAULT_MONITORING_SESSIONS_DIR,
    runs_root: Path | str = DEFAULT_RUNS_DIR,
) -> MonitoringCinematicArtifacts:
    published = load_published_monitoring_evidence_campaign(
        output_root=campaign_output_root,
        campaign_id=plan.campaign_id,
    )
    _validate_export_preconditions(plan, registration, published)
    validate_monitoring_cinematic_sources(plan)
    assert published.result is not None
    session = _load_monitoring_session_read_only(
        Path(sessions_root),
        session_id=plan.campaign_session_id,
    )
    if (
        session.state.status != "completed"
        or session.state.revision != EXPECTED_TICK_BEATS
        or session.state.execution_cursor != 688
        or len(session.ticks) != EXPECTED_TICK_BEATS
    ):
        raise ValueError("cinematic export requires a complete 689-tick session")
    commit_hashes, terminal_commit_path = _load_commit_hashes(
        Path(sessions_root),
        session_id=plan.campaign_session_id,
        expected_ticks=session.ticks,
    )
    tick_materials = tuple(
        _tick_material(tick, commit_hashes[tick.cursor]) for tick in session.ticks
    )
    trigger_by_event = {item.event_id: item for item in session.triggers}
    review_materials: list[MonitoringCinematicReviewMaterial] = []
    child_input_paths: list[tuple[str, Path]] = []
    for review in published.result.final_state.reviews:
        if not all(
            (review.trigger_id, review.trigger_event_id, review.child_run_id)
        ):
            raise ValueError("cinematic export requires complete review identities")
        trigger = trigger_by_event.get(str(review.trigger_event_id))
        if trigger is None:
            raise ValueError("campaign review trigger is absent from replay ledger")
        material, paths = _load_review_material(
            published=published,
            review=review,
            trigger=trigger,
            runs_root=Path(runs_root),
        )
        review_materials.append(material)
        child_input_paths.extend(paths)
    timeline = build_monitoring_cinematic_timeline(
        campaign_id=plan.campaign_id,
        session_id=plan.campaign_session_id,
        ticks=tick_materials,
        reviews=review_materials,
        operational_verdict=published.result.operational_verdict,
        agentic_verdict=published.result.agentic_verdict,
        evidence_verdict=published.result.evidence_verdict,
        blockers=published.result.blockers,
        completed_at=published.result.completed_at,
    )
    destination = _capture_dir(output_root, plan.capture_id)
    destination.mkdir(parents=True, exist_ok=True)
    plan_path = destination / "capture_plan.json"
    registration_path = destination / "preregistration.json"
    if Path(registration.capture_plan_ref).resolve() != plan_path.resolve():
        raise ValueError("cinematic preregistration plan_ref is not canonical")
    _write_immutable_json(plan_path, plan.model_dump(mode="json"))
    _write_immutable_json(registration_path, registration.model_dump(mode="json"))
    timeline_path = destination / "cinematic_timeline.jsonl"
    timeline_bytes = b"".join(
        _canonical_json_bytes(item.model_dump(mode="json")) + b"\n"
        for item in timeline
    )
    _write_immutable_bytes(timeline_path, timeline_bytes)

    campaign_dir = (Path(campaign_output_root) / plan.campaign_id).resolve()
    publication_path = campaign_dir / "publication.json"
    result_path = campaign_dir / "result.json"
    input_paths = [
        ("campaign_publication", publication_path),
        ("campaign_result", result_path),
        ("session_terminal_commit", terminal_commit_path),
        *child_input_paths,
    ]
    inputs = tuple(_input_artifact(role, path) for role, path in input_paths)
    manifest = _with_hash(
        MonitoringCinematicManifest,
        {
            "capture_id": plan.capture_id,
            "campaign_id": plan.campaign_id,
            "session_id": plan.campaign_session_id,
            "campaign_plan_sha256": plan.campaign_plan_sha256,
            "campaign_result_sha256": published.result.result_sha256,
            "campaign_publication_sha256": (
                published.publication.publication_sha256
            ),
            "capture_plan_sha256": plan.capture_plan_sha256,
            "registration_sha256": registration.registration_sha256,
            "terminal_commit_sha256": commit_hashes[688],
            "generated_at": published.result.completed_at,
            "inputs": inputs,
            "timeline_path": timeline_path.as_posix(),
            "timeline_sha256": hashlib.sha256(timeline_bytes).hexdigest(),
            "timeline_size_bytes": len(timeline_bytes),
            "operational_verdict": published.result.operational_verdict,
            "agentic_verdict": published.result.agentic_verdict,
            "evidence_verdict": published.result.evidence_verdict,
        },
    )
    manifest_path = destination / "manifest.json"
    _write_immutable_json(manifest_path, manifest.model_dump(mode="json"))
    checksums_path = destination / "checksums.sha256"
    checksum_text = _checksums_text(
        destination,
        (plan_path, registration_path, timeline_path, manifest_path),
    )
    _write_immutable_bytes(checksums_path, checksum_text.encode("utf-8"))
    return MonitoringCinematicArtifacts(
        output_dir=destination.as_posix(),
        capture_plan_path=plan_path.as_posix(),
        preregistration_path=registration_path.as_posix(),
        timeline_path=timeline_path.as_posix(),
        manifest_path=manifest_path.as_posix(),
        checksums_path=checksums_path.as_posix(),
        manifest=manifest,
    )


def _validate_export_preconditions(
    plan: MonitoringCinematicCapturePlan,
    registration: MonitoringCinematicPreregistration,
    published: MonitoringEvidenceCampaignPublished,
) -> None:
    result = published.result
    if (
        published.plan.campaign_id != plan.campaign_id
        or published.plan.session_id != plan.campaign_session_id
        or published.plan.plan_sha256 != plan.campaign_plan_sha256
    ):
        raise ValueError("cinematic capture plan does not bind published campaign")
    if (
        registration.capture_id != plan.capture_id
        or registration.campaign_id != plan.campaign_id
        or registration.campaign_plan_sha256 != plan.campaign_plan_sha256
        or registration.capture_plan_sha256 != plan.capture_plan_sha256
    ):
        raise ValueError("cinematic preregistration does not bind capture plan")
    if result is None or published.publication.result_ref is None:
        raise ValueError("cinematic export requires a published campaign result")
    if (
        published.state.status not in {"completed", "failed"}
        or result.final_state.status not in {"completed", "failed"}
        or result.final_state.current_revision != EXPECTED_TICK_BEATS
    ):
        raise ValueError("cinematic export accepts only a completed campaign")
    if registration.registered_at > result.started_at:
        raise ValueError("cinematic capture must be preregistered before campaign start")


def _load_monitoring_session_read_only(
    sessions_root: Path,
    *,
    session_id: str,
    scenarios: Mapping[str, Any] | None = None,
):
    """Valida el replay sobre una copia para no reparar la evidencia fuente.

    ``MonitoringReplayStore.get_session`` repara de forma deliberada un
    ``state.json`` atrasado respecto al ledger. Esa conducta es correcta para
    recuperar el servicio, pero un exportador post-hoc debe ser observacional.
    La copia se toma bajo el mismo flock de sesión y cualquier reparación queda
    confinada al directorio temporal.
    """

    if not _SAFE_ID.fullmatch(session_id):
        raise ValueError("unsafe monitoring session id")
    root = sessions_root.resolve()
    source = root / session_id
    if source.is_symlink() or not source.is_dir() or source.resolve().parent != root:
        raise ValueError("monitoring session source is not canonical")
    if any(path.is_symlink() for path in source.rglob("*")):
        raise ValueError("monitoring session source cannot contain symlinks")
    lock_path = source / ".session.lock"
    if lock_path.is_symlink() or not lock_path.is_file():
        raise ValueError("monitoring session lock is unavailable")

    with lock_path.open("rb") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_SH)
        try:
            with tempfile.TemporaryDirectory(prefix="tfm-cinematic-session-") as tmp:
                copied_root = Path(tmp) / "sessions"
                copied_root.mkdir()
                shutil.copytree(source, copied_root / session_id, symlinks=True)
                copied_store = MonitoringReplayStore(
                    copied_root,
                    **({"scenarios": scenarios} if scenarios is not None else {}),
                )
                return copied_store.get_session(session_id)
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def _load_commit_hashes(
    sessions_root: Path,
    *,
    session_id: str,
    expected_ticks: Sequence[Any],
) -> tuple[dict[int, str], Path]:
    if not _SAFE_ID.fullmatch(session_id):
        raise ValueError("unsafe monitoring session id")
    session_dir = (sessions_root / session_id).resolve()
    if sessions_root.resolve() not in session_dir.parents:
        raise ValueError("monitoring session leaves configured root")
    commits_dir = session_dir / "commits"
    files = sorted(commits_dir.glob("*.json"))
    if len(files) != EXPECTED_TICK_BEATS:
        raise ValueError("cinematic export requires exactly 689 commit files")
    previous = ZERO_SHA256
    hashes: dict[int, str] = {}
    for index, (path, expected_tick) in enumerate(
        zip(files, expected_ticks, strict=True), start=1
    ):
        if path.is_symlink() or path.name != f"{index:06d}.json":
            raise ValueError("monitoring commit sequence is not canonical")
        payload = _read_json(path)
        claimed = payload.get("commit_sha256")
        core = {key: value for key, value in payload.items() if key != "commit_sha256"}
        tick_payload = payload.get("tick")
        if (
            not isinstance(claimed, str)
            or not re.fullmatch(r"[0-9a-f]{64}", claimed)
            or payload.get("previous_commit_sha256") != previous
            or _json_sha256(core) != claimed
            or not isinstance(tick_payload, dict)
            or tick_payload.get("cursor") != expected_tick.cursor
            or tick_payload.get("tick_id") != expected_tick.tick_id
        ):
            raise ValueError("monitoring commit chain changed after validated load")
        hashes[expected_tick.cursor] = claimed
        previous = claimed
    return hashes, files[-1]


def _tick_material(tick: Any, commit_sha256: str) -> MonitoringCinematicTickMaterial:
    assets = tuple(
        _asset_projection(frame, index=index)
        for index, frame in enumerate(tick.frames, start=1)
    )
    if len(assets) != 4:
        raise ValueError("cinematic tick must expose four bearing channels")
    return MonitoringCinematicTickMaterial(
        cursor=tick.cursor,
        source_time=tick.source_time,
        wall_time=tick.committed_at,
        tick_id=tick.tick_id,
        commit_sha256=commit_sha256,
        assets=assets,
    )


def _asset_projection(frame: Any, *, index: int) -> MonitoringCinematicAssetProjection:
    telemetry = frame.telemetry
    state = frame.health_state
    return MonitoringCinematicAssetProjection(
        asset_id=frame.asset_id,
        asset_label=f"Rodamiento {index}",
        channel_id=frame.channel_id,
        analysis_status=frame.analysis_status,
        analysis_label={
            "modeled": "Estado algorítmico",
            "telemetry_only": "Solo telemetría · sin diagnóstico",
            "unavailable": "Dato no disponible",
        }[frame.analysis_status],
        signal_rms=telemetry.signal_rms if telemetry is not None else None,
        signal_peak_abs=(telemetry.signal_peak_abs if telemetry is not None else None),
        health_index=frame.health_index,
        risk_index=frame.risk_index,
        health_state=state,
        health_state_label=(
            {
                "nominal": "Nominal",
                "watch": "Vigilancia",
                "warning": "Advertencia",
                "critical": "Crítico",
            }[state]
            if state is not None
            else None
        ),
        score=frame.score,
        threshold=frame.threshold,
        score_ratio=frame.score_ratio,
        gap_detected=frame.gap_detected,
    )


def _load_review_material(
    *,
    published: MonitoringEvidenceCampaignPublished,
    review: Any,
    trigger: Any,
    runs_root: Path,
) -> tuple[MonitoringCinematicReviewMaterial, list[tuple[str, Path]]]:
    child_run_id = str(review.child_run_id)
    snapshot = load_run_snapshot(child_run_id, runs_root)
    run_dir = Path(snapshot.snapshot_dir).resolve()
    if runs_root.resolve() not in run_dir.parents:
        raise ValueError("cinematic child run leaves configured runs root")
    result_path = run_dir / "monitoring_review_result.json"
    events_path = run_dir / "monitoring_review_events.json"
    proposal_path = run_dir / "monitoring_policy_proposal.json"
    catalog_path = run_dir / "monitoring_review_evidence_catalog.json"
    for path in (result_path, events_path, proposal_path, catalog_path):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"cinematic child artifact is unavailable: {path.name}")
    result = MonitoringReviewResult.model_validate(_read_json(result_path))
    proposal = MonitoringPolicyProposal.model_validate(_read_json(proposal_path))
    catalog = CausalEvidenceCatalog.model_validate(_read_json(catalog_path))
    events = load_run_runtime_events(child_run_id, runs_root)
    _validate_review_artifact_binding(
        session_id=published.plan.session_id,
        child_run_id=child_run_id,
        review=review,
        trigger=trigger,
        result=result,
        proposal=proposal,
        catalog=catalog,
    )
    decision_events = {
        event.decision_id: event
        for event in events
        if event.kind in {"supervisor_decision", "agent_decision"}
        and event.decision_id is not None
    }
    contributions = {item.decision_id: item for item in proposal.contributions}
    decisions: list[MonitoringCinematicDecisionMaterial] = []
    for role_result in result.role_results:
        decision = role_result.decision
        if decision is None:
            raise ValueError("cinematic timeline requires all 28 sealed decisions")
        event = decision_events.get(decision.decision_id)
        contribution = contributions.get(decision.decision_id)
        if (
            event is None
            or event.event_id not in role_result.runtime_event_ids
            or contribution is None
            or contribution.decision_sha256 != decision.decision_sha256
        ):
            raise ValueError("cinematic decision is not bound to runtime/proposal")
        decisions.append(
            MonitoringCinematicDecisionMaterial(
                event_id=event.event_id,
                event_sequence=event.sequence,
                decision_id=decision.decision_id,
                decision_sha256=decision.decision_sha256,
                wall_time=event.created_at,
                projection=MonitoringCinematicDecisionProjection(
                    agent_name=decision.agent_name,
                    role_label=_role_label(decision.agent_name),
                    hypothesis=decision.hypothesis.statement,
                    expected_observation=decision.hypothesis.expected_observation,
                    falsification_criterion=(
                        decision.hypothesis.falsification_criterion
                    ),
                    recommended_action=decision.recommended_action,
                    action_label=_action_label(decision.recommended_action),
                    confidence=decision.confidence,
                    evidence_handles=contribution.evidence_handles,
                    generation_origin=decision.generation_trace.origin,
                    generation_validation_status=(
                        decision.generation_trace.validation_status
                    ),
                ),
            )
        )
    proposal_events = [event for event in events if event.kind == "policy_proposal"]
    if len(proposal_events) != 1:
        raise ValueError("cinematic review requires one proposal runtime event")
    proposal_event = proposal_events[0]
    proposal_material = MonitoringCinematicProposalMaterial(
        event_id=proposal_event.event_id,
        event_sequence=proposal_event.sequence,
        proposal_id=proposal.proposal_id,
        proposal_sha256=proposal.proposal_sha256,
        wall_time=proposal_event.created_at,
        projection=MonitoringCinematicProposalProjection(
            status=proposal.status,
            agreement_status=proposal.agreement_status,
            agreement_label={
                "unanimous": "unanimidad",
                "disagreement": "desacuerdo visible",
                "invalid_review": "revisión no válida",
            }[proposal.agreement_status],
            application_status=proposal.application_status,
            aggregate_action=proposal.aggregate_action,
            action_counts=dict(
                sorted(
                    Counter(
                        item.recommended_action for item in proposal.contributions
                    ).items()
                )
            ),
            human_review_recommended=proposal.human_review_recommended,
        ),
    )
    material = MonitoringCinematicReviewMaterial(
        ordinal=review.ordinal,
        cursor=review.cutoff_cursor,
        source_time=result.cutoff_source_time,
        tick_id=result.origin_tick_id,
        trigger_id=result.trigger_id,
        trigger_event_id=result.trigger_event_id,
        trigger_wall_time=trigger.recorded_at,
        child_run_id=child_run_id,
        trigger=MonitoringCinematicTriggerProjection(
            ordinal=review.ordinal,
            trigger_type=review.trigger_type,
            trigger_type_label=_trigger_label(review.trigger_type),
            reason_code=review.reason_code,
            summary=trigger.reason,
            condition_start_cursor=review.condition_start_cursor,
            cutoff_cursor=review.cutoff_cursor,
        ),
        decisions=tuple(decisions),
        proposal=proposal_material,
    )
    prefix = f"child_{review.ordinal:02d}"
    paths = [
        (f"{prefix}_review_result", result_path),
        (f"{prefix}_runtime_events", events_path),
        (f"{prefix}_policy_proposal", proposal_path),
        (f"{prefix}_evidence_catalog", catalog_path),
    ]
    return material, paths


def _validate_review_artifact_binding(
    *,
    session_id: str,
    child_run_id: str,
    review: Any,
    trigger: Any,
    result: Any,
    proposal: Any,
    catalog: Any,
) -> None:
    if (
        result.child_run_id != child_run_id
        or result.session_id != session_id
        or result.trigger_id != review.trigger_id
        or result.trigger_event_id != review.trigger_event_id
        or result.cutoff_cursor != review.cutoff_cursor
        or result.origin_tick_id != trigger.origin_tick_id
        or proposal.proposal_id != review.proposal_id
        or proposal.proposal_sha256 != review.proposal_sha256
        or proposal.child_run_id != child_run_id
        or proposal.trigger_event_id != result.trigger_event_id
        or proposal.request_id != result.request_id
        or proposal.request_sha256 != result.request_sha256
        or proposal.causal_view_sha256 != result.causal_view_sha256
        or proposal.evidence_catalog_sha256 != catalog.catalog_sha256
    ):
        raise ValueError("cinematic child artifacts do not bind campaign review")


def _validate_timeline(beats: Sequence[MonitoringCinematicBeat]) -> None:
    if len(beats) != EXPECTED_BEATS:
        raise ValueError("cinematic timeline must contain exactly 726 beats")
    counts = Counter(item.kind for item in beats)
    if counts != {
        "tick": EXPECTED_TICK_BEATS,
        "trigger": EXPECTED_TRIGGER_BEATS,
        "agent_decision": EXPECTED_DECISION_BEATS,
        "policy_proposal": EXPECTED_PROPOSAL_BEATS,
        "final_verdict": EXPECTED_VERDICT_BEATS,
    }:
        raise ValueError("cinematic timeline beat matrix is incomplete")
    previous = ZERO_SHA256
    for index, beat in enumerate(beats):
        if beat.beat_index != index or beat.previous_beat_sha256 != previous:
            raise ValueError("cinematic beat chain is not contiguous")
        previous = beat.beat_sha256
    if sum(item.duration_frames for item in beats) != EXPECTED_VIDEO_FRAMES:
        raise ValueError("cinematic timeline video frame budget is not exact")


def _input_artifact(role: str, path: Path) -> MonitoringCinematicInputArtifact:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"cinematic input is unavailable: {role}")
    return MonitoringCinematicInputArtifact(
        input_role=role,
        path=path.as_posix(),
        sha256=_file_sha256(path),
        size_bytes=path.stat().st_size,
    )


def _role_label(agent_name: AgentName) -> str:
    return {
        "supervisor": "Supervisor",
        "cleaner": "Especialista de calidad",
        "structurer": "Estructurador temporal",
        "modeler": "Modelador",
        "evaluator": "Evaluador",
        "report_writer": "Redactor técnico",
        "report_verifier": "Verificador",
    }[agent_name]


def _action_label(action: str) -> str:
    return {
        "maintain_policy": "Mantener observación",
        "intensify_observation": "Intensificar observación",
        "request_human_review": "Solicitar revisión humana",
        "inspect_data_quality": "Revisar calidad de datos",
        "revisit_temporal_context": "Revisar contexto temporal",
        "compare_model_behavior": "Comparar comportamiento del modelo",
        "document_uncertainty": "Documentar incertidumbre",
    }.get(action, action.replace("_", " "))


def _trigger_label(trigger_type: MonitoringTriggerType) -> str:
    return {
        "preflight": "Preflight",
        "periodic_review": "Revisión periódica",
        "persistent_alert": "Alerta persistente",
        "state_transition": "Cambio de estado",
        "continuity_gap": "Hueco de continuidad",
        "session_close": "Cierre del replay",
        "manual": "Activación manual",
    }[trigger_type]


def _capture_dir(output_root: Path | str, capture_id: str) -> Path:
    if not _SAFE_ID.fullmatch(capture_id):
        raise ValueError("unsafe cinematic capture id")
    root = Path(output_root).resolve()
    destination = (root / capture_id).resolve()
    if root not in destination.parents:
        raise ValueError("cinematic capture path leaves output root")
    return destination


def _read_json(path: Path) -> Any:
    if path.is_symlink() or not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, payload: Any) -> None:
    _write_bytes_atomic(
        path,
        json.dumps(
            payload,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
        + b"\n",
    )


def _write_bytes_atomic(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _write_immutable_json(path: Path, payload: Any) -> None:
    content = (
        json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True).encode(
            "utf-8"
        )
        + b"\n"
    )
    _write_immutable_bytes(path, content)


def _write_immutable_bytes(path: Path, content: bytes) -> None:
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.read_bytes() != content:
            raise ValueError(f"immutable cinematic artifact conflict: {path}")
        return
    _write_bytes_atomic(path, content)


def _checksums_text(root: Path, paths: Sequence[Path]) -> str:
    lines = [
        f"{_file_sha256(path)}  {path.relative_to(root).as_posix()}"
        for path in sorted(paths, key=lambda item: item.as_posix())
    ]
    return "\n".join(lines) + "\n"


__all__ = [
    "DEFAULT_MONITORING_CINEMATIC_OUTPUT_DIR",
    "EXPECTED_BEATS",
    "EXPECTED_VIDEO_FRAMES",
    "MONITORING_CINEMATIC_RENDERER_ID",
    "OFFICIAL_CAMPAIGN_PLAN_SHA256",
    "MonitoringCinematicArtifacts",
    "MonitoringCinematicBeat",
    "MonitoringCinematicCapturePlan",
    "MonitoringCinematicDecisionMaterial",
    "MonitoringCinematicDecisionProjection",
    "MonitoringCinematicDisplayProjection",
    "MonitoringCinematicManifest",
    "MonitoringCinematicPreregistration",
    "MonitoringCinematicProposalMaterial",
    "MonitoringCinematicProposalProjection",
    "MonitoringCinematicReviewMaterial",
    "MonitoringCinematicTickMaterial",
    "MonitoringCinematicTriggerProjection",
    "build_monitoring_cinematic_timeline",
    "default_monitoring_cinematic_capture_plan",
    "export_monitoring_cinematic",
    "load_monitoring_cinematic_preregistration",
    "preregister_monitoring_cinematic_capture",
    "validate_monitoring_cinematic_sources",
]
