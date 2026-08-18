"""Replay causal manual de una trayectoria NASA IMS con scoring congelado.

La responsabilidad de este servicio es estrecha: posee sesion, cursor, ledger
y checkpoint. No sustituye al pipeline multiagente ni usa artefactos
retrospectivos como entrada. ``predictions.csv`` y ``snapshot_trajectory.csv``
quedan fuera de este modulo y solo pueden actuar como oraculos de QA.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
import fcntl
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd

from codigo.app.executors.modeling import (
    load_frozen_model_bundle,
    score_frozen_feature_rows,
)
from codigo.app.schemas.api_monitoring import (
    MonitoringReplaySourceSummary,
    MonitoringSessionView,
    MonitoringStepResponse,
    MonitoringTickListResponse,
)
from codigo.app.schemas.monitoring_replay import (
    ActivePolicyRefs,
    AgentActivationPolicy,
    AgentActivationPolicyKind,
    AgentActivationTriggerRule,
    MonitoringFrame,
    MonitoringTelemetrySummary,
    MonitoringTriggerEvent,
    ReplayActivationCheckpoint,
    ReplayAssetCheckpoint,
    ReplayAssetSpec,
    ReplayExperimentMode,
    ReplaySessionConfig,
    ReplaySessionState,
    ReplayStepCommand,
    ReplayStepReceipt,
    ReplayTick,
    ScoringPolicyBundle,
)
from codigo.app.schemas.temporal_health import (
    DEFAULT_SNAPSHOT_AGGREGATION_POLICY,
    DEFAULT_TEMPORAL_GAP_POLICY,
    DEFAULT_TEMPORAL_HEALTH_INDICATOR_POLICY,
    DEFAULT_TEMPORAL_HEALTH_POLICY,
    SnapshotAggregationPolicy,
    TemporalGapPolicy,
    TemporalHealthIndicatorPolicy,
    TemporalHealthPolicy,
)
from codigo.app.services.common_manifest import read_common_manifest
from codigo.app.services.monitoring_trigger_engine import (
    evaluate_monitoring_triggers,
    initial_activation_checkpoint,
)
from codigo.app.services.signal_adapters import read_signal_channels
from codigo.app.services.temporal_health_policy import (
    aggregate_temporal_snapshots,
    annotate_temporal_gaps,
    causal_temporal_health_points,
    temporal_health_values,
)


DEFAULT_MONITORING_SESSIONS_DIR = Path("codigo/reports/monitoring_sessions")
DEFAULT_SCENARIO_ID = "NASA-RTF-HYB-01"
DEFAULT_PILOT_RUN_ID = "nasa-ims-official-set2-v2-pca-003"
DEFAULT_SCORING_VERSION = "nasa-set2-pca-003-scoring-v1"
DEFAULT_ACTIVATION_VERSION = "deterministic-observer-p0-v1"
P3_ACTIVATION_VERSION = "nasa-rtf-hyb-p3-01-activation-v1"
P3_MAX_VARIABLE_CHILD_RUNS = 7
P3_COOLDOWN_SOURCE_SECONDS = 51_600.0
P3_AGENT_ROLES = (
    "supervisor",
    "cleaner",
    "structurer",
    "modeler",
    "evaluator",
    "report_writer",
    "report_verifier",
)

SAFE_FEATURE_COLUMNS = (
    "mean",
    "std",
    "rms",
    "min",
    "max",
    "peak_to_peak",
    "skewness",
    "kurtosis",
    "crest_factor",
    "energy",
)
SAFE_FEATURE_METADATA_COLUMNS = (
    "window_id",
    "file_id",
    "run_id",
    "window_index",
    "timestamp_start",
    "timestamp_end",
    "temporal_partition",
)
SAFE_FEATURE_INPUT_COLUMNS = SAFE_FEATURE_METADATA_COLUMNS + SAFE_FEATURE_COLUMNS
EXPECTED_WINDOWS_PER_SNAPSHOT = 19


class MonitoringReplayError(RuntimeError):
    """Error base del replay que puede traducirse de forma segura en API."""


class MonitoringReplayNotFoundError(MonitoringReplayError):
    """Escenario o sesion inexistente."""


class MonitoringReplayConflictError(MonitoringReplayError):
    """Conflicto de identidad, revision o comando."""


class MonitoringReplayUnavailableError(MonitoringReplayError):
    """El escenario registrado no supera su preflight local."""


@dataclass(frozen=True)
class RegisteredReplayScenario:
    """Registro interno; las rutas nunca proceden del body HTTP."""

    scenario_id: str
    title: str
    dataset_id: str
    trajectory_id: str
    source_label: str
    pilot_run_id: str
    manifest_path: Path
    manifest_sha256: str
    features_path: Path
    features_sha256: str
    model_path: Path
    model_sha256: str
    expected_snapshot_count: int
    expected_bootstrap_count: int
    expected_monitoring_count: int
    expected_windows_per_snapshot: int
    asset_specs: tuple[ReplayAssetSpec, ...]


@dataclass(frozen=True)
class _SafeSnapshot:
    snapshot_id: str
    run_id: str
    source_time: datetime
    temporal_partition: str
    source_path: Path
    input_record_hash: str
    score: float
    threshold: float
    predicted_anomaly: int
    n_windows: int
    n_alerted_windows: int
    window_alert_fraction: float

    def health_row(self) -> dict[str, Any]:
        return {
            "window_id": f"snapshot:{self.run_id}:{self.snapshot_id}",
            "snapshot_id": self.snapshot_id,
            "file_id": self.snapshot_id,
            "run_id": self.run_id,
            "timestamp_start": self.source_time.isoformat(),
            "anomaly_score": self.score,
            "threshold": self.threshold,
            "predicted_anomaly": self.predicted_anomaly,
            "temporal_partition": self.temporal_partition,
        }


@dataclass
class _ScenarioRuntime:
    definition: RegisteredReplayScenario
    features: pd.DataFrame
    feature_groups: dict[str, pd.DataFrame]
    ordered_snapshot_ids: tuple[str, ...]
    monitoring_snapshot_ids: tuple[str, ...]
    manifest_records: dict[str, Any]
    model_bundle: dict[str, Any]
    scoring_policy: ScoringPolicyBundle
    activation_policy: AgentActivationPolicy
    temporal_policies: _TemporalPolicyDependencies
    bootstrap_snapshots: tuple[_SafeSnapshot, ...]
    bootstrap_checkpoint: ReplayAssetCheckpoint


@dataclass(frozen=True)
class _TemporalPolicyDependencies:
    aggregation: SnapshotAggregationPolicy
    gap: TemporalGapPolicy
    health: TemporalHealthPolicy
    health_indicator: TemporalHealthIndicatorPolicy


@dataclass(frozen=True)
class _PersistedSessionPolicies:
    scoring: ScoringPolicyBundle
    activation: AgentActivationPolicy
    temporal: _TemporalPolicyDependencies


def default_registered_replay_scenarios() -> dict[str, RegisteredReplayScenario]:
    """Devuelve el unico piloto NASA registrado en este incremento."""

    base = DEFAULT_PILOT_RUN_ID
    specs = tuple(
        ReplayAssetSpec(
            asset_id=f"bearing_{index}",
            channel_id=f"channel_{index}",
            analysis_status="modeled" if index == 1 else "telemetry_only",
        )
        for index in range(1, 5)
    )
    scenario = RegisteredReplayScenario(
        scenario_id=DEFAULT_SCENARIO_ID,
        title="NASA IMS Set 2 · replay causal PCA",
        dataset_id="nasa_ims_bearing",
        trajectory_id="set_2",
        source_label="NASA IMS Set 2 oficial · replay historico",
        pilot_run_id=base,
        manifest_path=Path(
            f"codigo/data/interim/nasa_ims_bearing/{base}/"
            "manifest_run_to_failure_v2.csv"
        ),
        manifest_sha256=(
            "c3600b40f43fbbcdc9a99555c56e0a93f69ad386935a5622936255d46071cc0f"
        ),
        features_path=Path(
            f"codigo/data/tensors/nasa_ims_bearing/{base}/windows_features.csv"
        ),
        features_sha256=(
            "cf7a2b5591d8f5cf5d67194062b553b0665d772b2794f805ffd8cc9ab5288839"
        ),
        model_path=Path(
            f"codigo/models/nasa_ims_bearing/{base}/"
            "pca_reconstruction_error.joblib"
        ),
        model_sha256=(
            "10e99c38d125a5903bb410b4c119901feeed20b2b7c5cadac7c4e4c02a657e1d"
        ),
        expected_snapshot_count=984,
        expected_bootstrap_count=295,
        expected_monitoring_count=689,
        expected_windows_per_snapshot=EXPECTED_WINDOWS_PER_SNAPSHOT,
        asset_specs=specs,
    )
    return {scenario.scenario_id: scenario}


class MonitoringReplayStore:
    """Store local con CAS, commits atomicos e idempotencia durable."""

    def __init__(
        self,
        sessions_root: str | Path = DEFAULT_MONITORING_SESSIONS_DIR,
        *,
        scenarios: dict[str, RegisteredReplayScenario] | None = None,
    ) -> None:
        self.sessions_root = Path(sessions_root)
        self._scenarios = scenarios or default_registered_replay_scenarios()
        self._runtimes: dict[str, _ScenarioRuntime] = {}
        self._validated_ledger_heads: dict[str, str] = {}
        self._validated_bootstrap_bindings: dict[
            str,
            tuple[str, tuple[ReplayAssetCheckpoint, ...]],
        ] = {}
        self._lock = threading.RLock()

    def list_sources(self) -> list[MonitoringReplaySourceSummary]:
        return [
            self._source_summary(definition)
            for definition in sorted(
                self._scenarios.values(), key=lambda item: item.scenario_id
            )
        ]

    def create_session(
        self,
        *,
        scenario_id: str,
        session_id: str | None = None,
        activation_policy_kind: AgentActivationPolicyKind = "P0",
        experiment_mode: ReplayExperimentMode = "frozen_benchmark",
    ) -> MonitoringSessionView:
        with self._lock, self._root_file_lock():
            if experiment_mode != "frozen_benchmark":
                raise MonitoringReplayUnavailableError(
                    "adaptive_replay_exploratory is not enabled until policy "
                    "validation and forward-only application are implemented"
                )
            runtime = self._runtime(scenario_id)
            activation_policy = _activation_policy_for_kind(
                runtime.definition,
                activation_policy_kind,
                expected_cadence_seconds=(
                    runtime.temporal_policies.gap.expected_cadence_seconds
                ),
            )
            if activation_policy.policy_kind == "P3" and (
                runtime.bootstrap_checkpoint.alert_persistence_count != 0
                or runtime.bootstrap_checkpoint.last_health_state
                in {"warning", "critical"}
            ):
                raise MonitoringReplayUnavailableError(
                    "P3 v1 requires a non-alert bootstrap boundary; carrying "
                    "an alert episode across monitoring start is not implemented"
                )
            resolved_session_id = session_id or self._new_session_id()
            session_dir = self._session_dir(resolved_session_id)
            if session_dir.exists():
                raise MonitoringReplayConflictError(
                    f"monitoring session already exists: {resolved_session_id}"
                )
            session_dir.mkdir(parents=True, exist_ok=False)
            (session_dir / "commits").mkdir()
            (session_dir / "receipts").mkdir()

            policy_refs = ActivePolicyRefs(
                scoring_version=runtime.scoring_policy.policy_version,
                activation_version=activation_policy.policy_version,
            )
            definition = runtime.definition
            source_fingerprint = _source_fingerprint(
                runtime.definition,
                runtime.scoring_policy,
                activation_policy,
            )
            asset_ids = tuple(
                dict.fromkeys(spec.asset_id for spec in definition.asset_specs)
            )
            checkpoints = _initial_session_checkpoints(
                runtime.bootstrap_checkpoint,
                definition.asset_specs,
            )
            bootstrap_checkpoints_sha256 = _canonical_sha256(
                [item.model_dump(mode="json") for item in checkpoints]
            )
            config = ReplaySessionConfig(
                session_id=resolved_session_id,
                pilot_id=definition.scenario_id,
                dataset_id=definition.dataset_id,
                trajectory_id=definition.trajectory_id,
                manifest_ref=(
                    f"artifact:{definition.pilot_run_id}:manifest_run_to_failure_v2"
                ),
                manifest_sha256=definition.manifest_sha256,
                source_fingerprint_sha256=source_fingerprint,
                bootstrap_checkpoints_sha256=bootstrap_checkpoints_sha256,
                partition_policy_id="nasa_ims_run_to_failure_v2",
                asset_ids=asset_ids,
                asset_specs=definition.asset_specs,
                activation_policy_kind=activation_policy.policy_kind,
                experiment_mode=experiment_mode,
                initial_mode="manual",
                initial_speed_multiplier=1.0,
                initial_policy_refs=policy_refs,
                source_timezone=None,
            )
            config_sha256 = _canonical_sha256(config.model_dump(mode="json"))
            state = ReplaySessionState(
                session_id=resolved_session_id,
                config_sha256=config_sha256,
                status="ready",
                execution_cursor=None,
                sequence=0,
                revision=0,
                mode="manual",
                speed_multiplier=1.0,
                active_policy_refs=policy_refs,
                activation_checkpoint=initial_activation_checkpoint(
                    activation_policy
                ),
                asset_checkpoints=checkpoints,
            )
            _write_json_atomic(
                session_dir / "config.json", config.model_dump(mode="json")
            )
            _write_json_atomic(
                session_dir / "scoring_policy.json",
                runtime.scoring_policy.model_dump(mode="json"),
            )
            _write_json_atomic(
                session_dir / "activation_policy.json",
                activation_policy.model_dump(mode="json"),
            )
            _write_json_atomic(
                session_dir / "temporal_policies.json",
                _temporal_policy_payload(runtime.temporal_policies),
            )
            _write_json_atomic(
                session_dir / "bootstrap_checkpoints.json",
                {
                    "schema_version": "monitoring_bootstrap_checkpoints_v1",
                    "checkpoints": [
                        item.model_dump(mode="json") for item in checkpoints
                    ],
                },
            )
            _write_json_atomic(
                session_dir / "state.json", state.model_dump(mode="json")
            )
            return self.get_session(resolved_session_id)

    def get_session(self, session_id: str) -> MonitoringSessionView:
        with self._lock, self._session_file_lock(session_id):
            config, state, commits, _ = self._load_session(session_id)
            runtime = self._runtime(config.pilot_id)
            return MonitoringSessionView(
                source=self._source_summary(runtime.definition),
                config=config,
                state=state,
                total_monitoring_ticks=len(runtime.monitoring_snapshot_ids),
                ticks=tuple(item["tick"] for item in commits),
                triggers=tuple(
                    event
                    for item in commits
                    for event in item.get("triggers", ())
                ),
            )

    def list_ticks(
        self,
        session_id: str,
        *,
        after_sequence: int = 0,
    ) -> MonitoringTickListResponse:
        with self._lock, self._session_file_lock(session_id):
            _, _, commits, _ = self._load_session(session_id)
            selected = [
                item for item in commits if item["tick"].sequence > after_sequence
            ]
            return MonitoringTickListResponse(
                session_id=session_id,
                after_sequence=after_sequence,
                ticks=tuple(item["tick"] for item in selected),
                triggers=tuple(
                    event
                    for item in selected
                    for event in item.get("triggers", ())
                ),
            )

    def step(
        self,
        command: ReplayStepCommand,
        *,
        before_apply: Callable[[MonitoringSessionView], None] | None = None,
    ) -> MonitoringStepResponse:
        with self._lock, self._session_file_lock(command.session_id):
            config, state, commits, policies = self._load_session(
                command.session_id
            )
            session_dir = self._session_dir(command.session_id)
            persisted = _read_command_response(session_dir, command.command_id)
            if persisted is not None:
                original, response = persisted
                _ensure_same_command(original, command)
                if response.receipt.outcome == "applied":
                    committed = next(
                        (
                            item
                            for item in commits
                            if item["command"].command_id == command.command_id
                        ),
                        None,
                    )
                    if (
                        committed is None
                        or response.receipt != committed["receipt"]
                        or response.tick != committed["tick"]
                    ):
                        raise MonitoringReplayConflictError(
                            "applied command receipt diverges from commit ledger"
                        )
                    return MonitoringStepResponse(
                        receipt=committed["receipt"].model_copy(
                            update={
                                "outcome": "idempotent_replay",
                                "recorded_at": datetime.now(UTC),
                            }
                        ),
                        state=state,
                        tick=committed["tick"],
                        triggers=committed.get("triggers", ()),
                    )
                return response.model_copy(update={"state": state})
            repeated = next(
                (
                    item
                    for item in commits
                    if item["command"].command_id == command.command_id
                ),
                None,
            )
            if repeated is not None:
                original = repeated["command"]
                _ensure_same_command(original, command)
                receipt = repeated["receipt"].model_copy(
                    update={
                        "outcome": "idempotent_replay",
                        "recorded_at": datetime.now(UTC),
                    }
                )
                response = MonitoringStepResponse(
                    receipt=receipt,
                    state=state,
                    tick=repeated["tick"],
                    triggers=repeated.get("triggers", ()),
                )
                _write_command_response(session_dir, original, response)
                return response

            if before_apply is not None:
                runtime = self._runtime(config.pilot_id)
                before_apply(
                    MonitoringSessionView(
                        source=self._source_summary(runtime.definition),
                        config=config,
                        state=state,
                        total_monitoring_ticks=len(runtime.monitoring_snapshot_ids),
                        ticks=tuple(item["tick"] for item in commits),
                        triggers=tuple(
                            event
                            for item in commits
                            for event in item.get("triggers", ())
                        ),
                    )
                )

            if command.expected_revision != state.revision:
                receipt = ReplayStepReceipt(
                    command_id=command.command_id,
                    session_id=command.session_id,
                    expected_revision=command.expected_revision,
                    outcome="revision_conflict",
                    accepted_revision=state.revision,
                    reason=(
                        f"expected revision {command.expected_revision}, "
                        f"current revision is {state.revision}"
                    ),
                )
                response = MonitoringStepResponse(receipt=receipt, state=state)
                _write_command_response(session_dir, command, response)
                return response

            runtime = self._runtime(config.pilot_id)
            next_cursor = (
                0 if state.execution_cursor is None else state.execution_cursor + 1
            )
            if next_cursor >= len(runtime.monitoring_snapshot_ids):
                receipt = ReplayStepReceipt(
                    command_id=command.command_id,
                    session_id=command.session_id,
                    expected_revision=command.expected_revision,
                    outcome="rejected",
                    accepted_revision=state.revision,
                    reason="the replay session has reached the final monitoring tick",
                )
                response = MonitoringStepResponse(receipt=receipt, state=state)
                _write_command_response(session_dir, command, response)
                return response

            snapshot_id = runtime.monitoring_snapshot_ids[next_cursor]
            snapshot = _score_snapshot(
                runtime,
                snapshot_id,
                scoring_policy=policies.scoring,
                aggregation_policy=policies.temporal.aggregation,
            )
            tick_id = f"{command.session_id}:tick:{next_cursor:06d}"
            frames, checkpoints, input_record_hash = _frames_for_snapshot(
                runtime,
                snapshot,
                tick_id=tick_id,
                state=state,
                policies=policies,
                asset_specs=config.asset_specs,
            )
            tick = ReplayTick(
                tick_id=tick_id,
                session_id=command.session_id,
                cursor=next_cursor,
                sequence=state.sequence + 1,
                snapshot_id=snapshot.snapshot_id,
                source_time=snapshot.source_time,
                input_record_hash=input_record_hash,
                active_policy_refs=state.active_policy_refs,
                frames=frames,
            )
            completed = next_cursor == len(runtime.monitoring_snapshot_ids) - 1
            if state.activation_checkpoint is None:
                raise MonitoringReplayConflictError(
                    "monitoring session lacks its activation checkpoint"
                )
            prior_events = tuple(
                event
                for item in commits
                for event in item.get("triggers", ())
            )
            try:
                trigger_result = evaluate_monitoring_triggers(
                    session_id=command.session_id,
                    tick=tick,
                    previous_asset_checkpoints=state.asset_checkpoints,
                    current_asset_checkpoints=checkpoints,
                    prior_events=prior_events,
                    policy=policies.activation,
                    checkpoint=state.activation_checkpoint,
                    session_completed=completed,
                )
            except ValueError as exc:
                raise MonitoringReplayConflictError(
                    f"monitoring trigger engine rejected the causal state: {exc}"
                ) from exc
            triggers = trigger_result.events
            new_state = state.model_copy(
                update={
                    "status": "completed" if completed else "paused",
                    "execution_cursor": next_cursor,
                    "sequence": state.sequence + 1,
                    "revision": state.revision + 1,
                    "activation_checkpoint": trigger_result.checkpoint,
                    "asset_checkpoints": checkpoints,
                    "last_committed_tick_id": tick.tick_id,
                    "last_trigger_id": (
                        triggers[-1].trigger_id
                        if triggers
                        else state.last_trigger_id
                    ),
                    "last_command_id": command.command_id,
                    "updated_at": datetime.now(UTC),
                }
            )
            receipt = ReplayStepReceipt(
                command_id=command.command_id,
                session_id=command.session_id,
                expected_revision=command.expected_revision,
                outcome="applied",
                accepted_revision=new_state.revision,
                tick_id=tick.tick_id,
            )
            previous_commit_sha256 = (
                commits[-1]["commit_sha256"] if commits else "0" * 64
            )
            commit_core = {
                "schema_version": "monitoring_replay_commit_v1",
                "previous_commit_sha256": previous_commit_sha256,
                "command": command.model_dump(mode="json"),
                "receipt": receipt.model_dump(mode="json"),
                "tick": tick.model_dump(mode="json"),
                "state": new_state.model_dump(mode="json"),
                "triggers": [
                    event.model_dump(mode="json") for event in triggers
                ],
            }
            commit_payload = {
                **commit_core,
                "commit_sha256": _canonical_sha256(commit_core),
            }
            _write_json_atomic(
                session_dir / "commits" / f"{tick.sequence:06d}.json",
                commit_payload,
            )
            self._validated_ledger_heads[command.session_id] = commit_payload[
                "commit_sha256"
            ]
            response = MonitoringStepResponse(
                receipt=receipt,
                state=new_state,
                tick=tick,
                triggers=triggers,
            )
            _write_command_response(session_dir, command, response)
            _write_json_atomic(
                session_dir / "state.json", new_state.model_dump(mode="json")
            )
            return response

    def _runtime(self, scenario_id: str) -> _ScenarioRuntime:
        if scenario_id in self._runtimes:
            return self._runtimes[scenario_id]
        definition = self._scenarios.get(scenario_id)
        if definition is None:
            raise MonitoringReplayNotFoundError(
                f"unknown monitoring scenario: {scenario_id}"
            )
        runtime = _load_scenario_runtime(definition)
        self._runtimes[scenario_id] = runtime
        return runtime

    def _source_summary(
        self,
        definition: RegisteredReplayScenario,
    ) -> MonitoringReplaySourceSummary:
        missing = [
            path.as_posix()
            for path in (
                definition.manifest_path,
                definition.features_path,
                definition.model_path,
            )
            if not path.is_file()
        ]
        mismatched: list[str] = []
        if not missing:
            for path, expected in (
                (definition.manifest_path, definition.manifest_sha256),
                (definition.features_path, definition.features_sha256),
                (definition.model_path, definition.model_sha256),
            ):
                if _file_sha256(path) != expected:
                    mismatched.append(path.name)
        available = not missing and not mismatched
        reason = None
        if missing:
            reason = "Faltan artefactos locales congelados del piloto NASA."
        elif mismatched:
            reason = "Los hashes del piloto NASA no coinciden con el registro."
        return MonitoringReplaySourceSummary(
            scenario_id=definition.scenario_id,
            title=definition.title,
            dataset_id=definition.dataset_id,
            trajectory_id=definition.trajectory_id,
            source_label=definition.source_label,
            available=available,
            unavailable_reason=reason,
            total_monitoring_ticks=definition.expected_monitoring_count,
            modeled_channel_id=next(
                spec.channel_id
                for spec in definition.asset_specs
                if spec.analysis_status == "modeled"
            ),
            channel_ids=tuple(spec.channel_id for spec in definition.asset_specs),
            available_activation_policy_kinds=("P0", "P3"),
        )

    def _load_session(
        self,
        session_id: str,
    ) -> tuple[
        ReplaySessionConfig,
        ReplaySessionState,
        list[dict[str, Any]],
        _PersistedSessionPolicies,
    ]:
        session_dir = self._session_dir(session_id)
        if not session_dir.is_dir():
            raise MonitoringReplayNotFoundError(
                f"unknown monitoring session: {session_id}"
            )
        config = ReplaySessionConfig.model_validate(
            _read_json(session_dir / "config.json")
        )
        state = ReplaySessionState.model_validate(_read_json(session_dir / "state.json"))
        commits = _read_commits(session_dir / "commits")
        if commits:
            committed_state = commits[-1]["state"]
            if state.revision > committed_state.revision:
                raise MonitoringReplayConflictError(
                    "monitoring state is ahead of the committed ledger"
                )
            if committed_state.revision > state.revision:
                state = committed_state
                _write_json_atomic(
                    session_dir / "state.json", state.model_dump(mode="json")
                )
            elif state.model_dump(mode="json") != committed_state.model_dump(
                mode="json"
            ):
                raise MonitoringReplayConflictError(
                    "monitoring state diverges from the committed ledger"
                )
        elif (
            state.revision != 0
            or state.sequence != 0
            or state.execution_cursor is not None
        ):
            raise MonitoringReplayConflictError(
                "monitoring state advances without a committed ledger"
            )
        policies = _load_persisted_session_policies(session_dir)
        initial_checkpoints = _load_bootstrap_checkpoints(session_dir, config)
        runtime = self._runtime(config.pilot_id)
        bootstrap_binding_key = _canonical_sha256(
            {
                "scoring": policies.scoring.model_dump(mode="json"),
                "temporal": _temporal_policy_payload(policies.temporal),
                "asset_specs": [
                    item.model_dump(mode="json") for item in config.asset_specs
                ],
            }
        )
        cached_bootstrap = self._validated_bootstrap_bindings.get(session_id)
        if cached_bootstrap is None or cached_bootstrap[0] != (
            bootstrap_binding_key
        ):
            _, expected_modeled_checkpoint = _bootstrap_for_policies(
                runtime,
                scoring_policy=policies.scoring,
                temporal_policies=policies.temporal,
            )
            expected_initial_checkpoints = _initial_session_checkpoints(
                expected_modeled_checkpoint,
                config.asset_specs,
            )
            self._validated_bootstrap_bindings[session_id] = (
                bootstrap_binding_key,
                expected_initial_checkpoints,
            )
        else:
            expected_initial_checkpoints = cached_bootstrap[1]
        ledger_head = commits[-1]["commit_sha256"] if commits else None
        _validate_session_contract(
            config,
            state,
            commits,
            policies,
            runtime,
            initial_checkpoints,
            expected_initial_checkpoints,
            validate_scoring=(
                ledger_head is not None
                and self._validated_ledger_heads.get(session_id) != ledger_head
            ),
        )
        if ledger_head is not None:
            self._validated_ledger_heads[session_id] = ledger_head
        return config, state, commits, policies

    def _session_dir(self, session_id: str) -> Path:
        if (
            not session_id
            or len(session_id) > 160
            or not session_id[0].isalnum()
            or any(
                character
                not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-"
                for character in session_id
            )
        ):
            raise MonitoringReplayConflictError("invalid monitoring session_id")
        root = self.sessions_root.resolve()
        resolved = (root / session_id).resolve()
        if resolved.parent != root:
            raise MonitoringReplayConflictError("invalid monitoring session_id")
        return resolved

    @contextmanager
    def _root_file_lock(self):
        root = self.sessions_root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        with (root / ".monitoring-store.lock").open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @contextmanager
    def _session_file_lock(self, session_id: str):
        session_dir = self._session_dir(session_id)
        if not session_dir.is_dir():
            raise MonitoringReplayNotFoundError(
                f"unknown monitoring session: {session_id}"
            )
        with (session_dir / ".session.lock").open("a+b") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _new_session_id() -> str:
        return f"nasa-rtf-{uuid.uuid4().hex[:10]}"


def _activation_policy_for_kind(
    definition: RegisteredReplayScenario,
    policy_kind: AgentActivationPolicyKind,
    *,
    expected_cadence_seconds: float,
) -> AgentActivationPolicy:
    """Resuelve una politica registrada; HTTP nunca aporta un bundle libre."""

    if policy_kind == "P0":
        payload = {
            "schema_version": "agent_activation_policy_v1",
            "policy_version": DEFAULT_ACTIVATION_VERSION,
            "policy_kind": "P0",
            "max_variable_child_runs": 0,
            "budget_unit": "variable_child_runs",
            "periodic_cursors": (),
            "alert_entry_persistence_ticks": 3,
            "alert_recovery_persistence_ticks": 1,
            "trigger_rules": (),
            "precedence": (),
        }
        return AgentActivationPolicy(
            **payload,
            policy_sha256=_canonical_sha256(payload),
        )
    if policy_kind != "P3":
        raise MonitoringReplayUnavailableError(
            f"activation policy {policy_kind} is not registered in this increment"
        )

    if expected_cadence_seconds <= 0.0:
        raise MonitoringReplayUnavailableError(
            "registered P3 policy requires a positive source cadence"
        )
    budget = P3_MAX_VARIABLE_CHILD_RUNS
    cooldown_seconds = P3_COOLDOWN_SOURCE_SECONDS
    review_group = "monitoring_review"
    rules = (
        AgentActivationTriggerRule(
            trigger_type="continuity_gap",
            priority=100,
            cooldown_source_seconds=cooldown_seconds,
            coalescing_group=review_group,
            rearm_policy="after_cooldown",
            requested_roles=P3_AGENT_ROLES,
        ),
        AgentActivationTriggerRule(
            trigger_type="state_transition",
            priority=90,
            cooldown_source_seconds=cooldown_seconds,
            coalescing_group=review_group,
            rearm_policy="after_cooldown",
            state_transition_targets=("critical",),
            requested_roles=P3_AGENT_ROLES,
        ),
        AgentActivationTriggerRule(
            trigger_type="persistent_alert",
            priority=80,
            cooldown_source_seconds=cooldown_seconds,
            coalescing_group=review_group,
            rearm_policy="after_recovery",
            requested_roles=P3_AGENT_ROLES,
        ),
        AgentActivationTriggerRule(
            trigger_type="session_close",
            priority=20,
            cooldown_source_seconds=0.0,
            coalescing_group="session_close",
            rearm_policy="once_per_session",
            requested_roles=P3_AGENT_ROLES,
            counts_toward_variable_budget=False,
        ),
    )
    payload = {
        "schema_version": "agent_activation_policy_v1",
        "policy_version": P3_ACTIVATION_VERSION,
        "policy_kind": "P3",
        "max_variable_child_runs": budget,
        "budget_unit": "variable_child_runs",
        "periodic_cursors": (),
        "alert_entry_persistence_ticks": 3,
        "alert_recovery_persistence_ticks": 1,
        "trigger_rules": tuple(
            rule.model_dump(mode="json") for rule in rules
        ),
        "precedence": (
            "continuity_gap",
            "state_transition",
            "persistent_alert",
            "session_close",
        ),
    }
    return AgentActivationPolicy(
        **payload,
        policy_sha256=_canonical_sha256(payload),
    )


def _load_scenario_runtime(
    definition: RegisteredReplayScenario,
) -> _ScenarioRuntime:
    if (
        definition.expected_bootstrap_count
        + definition.expected_monitoring_count
        != definition.expected_snapshot_count
    ):
        raise MonitoringReplayUnavailableError(
            "registered bootstrap and monitoring counts must cover the trajectory"
        )
    if definition.expected_windows_per_snapshot < 1:
        raise MonitoringReplayUnavailableError(
            "registered windows per snapshot must be positive"
        )
    for path, expected in (
        (definition.manifest_path, definition.manifest_sha256),
        (definition.features_path, definition.features_sha256),
        (definition.model_path, definition.model_sha256),
    ):
        if not path.is_file():
            raise MonitoringReplayUnavailableError(
                f"required replay artifact is missing: {path.as_posix()}"
            )
        actual = _file_sha256(path)
        if actual != expected:
            raise MonitoringReplayUnavailableError(
                f"replay artifact SHA-256 mismatch for {path.name}"
            )

    model_bundle = load_frozen_model_bundle(
        definition.model_path,
        expected_sha256=definition.model_sha256,
    )
    feature_columns = tuple(str(item) for item in model_bundle["feature_columns"])
    if feature_columns != SAFE_FEATURE_COLUMNS:
        raise MonitoringReplayUnavailableError(
            "frozen PCA feature order does not match the replay whitelist"
        )
    features = pd.read_csv(
        definition.features_path,
        usecols=list(SAFE_FEATURE_INPUT_COLUMNS),
    )
    if features.empty:
        raise MonitoringReplayUnavailableError("replay feature artifact is empty")
    if features[list(SAFE_FEATURE_INPUT_COLUMNS)].isnull().any().any():
        raise MonitoringReplayUnavailableError(
            "replay feature whitelist contains missing values"
        )
    if features["window_id"].duplicated().any():
        raise MonitoringReplayUnavailableError("replay window_id values must be unique")

    records = read_common_manifest(definition.manifest_path)
    if len(records) != definition.expected_snapshot_count:
        raise MonitoringReplayUnavailableError(
            "manifest snapshot count does not match the registered scenario"
        )
    ordered_records = sorted(
        records,
        key=lambda item: (
            item.timestamp_start or datetime.min,
            item.record_id,
        ),
    )
    manifest_records = {item.record_id: item for item in ordered_records}
    if len(manifest_records) != len(ordered_records):
        raise MonitoringReplayUnavailableError("manifest record_id values must be unique")

    groups: dict[str, pd.DataFrame] = {}
    for snapshot_id, group in features.groupby("file_id", sort=False):
        ordered = group.sort_values("window_index", kind="mergesort").reset_index(
            drop=True
        )
        if len(ordered) != definition.expected_windows_per_snapshot:
            raise MonitoringReplayUnavailableError(
                f"snapshot {snapshot_id} does not contain the registered "
                "number of feature windows"
            )
        expected_indexes = list(range(definition.expected_windows_per_snapshot))
        indexes = ordered["window_index"].astype(int).tolist()
        if indexes != expected_indexes:
            raise MonitoringReplayUnavailableError(
                f"snapshot {snapshot_id} has invalid window order"
            )
        groups[str(snapshot_id)] = ordered
    ordered_snapshot_ids = tuple(item.record_id for item in ordered_records)
    if set(groups) != set(ordered_snapshot_ids):
        raise MonitoringReplayUnavailableError(
            "feature snapshots and manifest records do not match"
        )
    monitoring_ids = tuple(
        snapshot_id
        for snapshot_id in ordered_snapshot_ids
        if str(groups[snapshot_id]["temporal_partition"].iloc[0]) == "monitoring"
    )
    if len(monitoring_ids) != definition.expected_monitoring_count:
        raise MonitoringReplayUnavailableError(
            "monitoring snapshot count does not match the registered scenario"
        )

    temporal_policies = _TemporalPolicyDependencies(
        aggregation=SnapshotAggregationPolicy.model_validate(
            DEFAULT_SNAPSHOT_AGGREGATION_POLICY.model_dump(mode="json")
        ),
        gap=TemporalGapPolicy.model_validate(
            DEFAULT_TEMPORAL_GAP_POLICY.model_dump(mode="json")
        ),
        health=TemporalHealthPolicy.model_validate(
            DEFAULT_TEMPORAL_HEALTH_POLICY.model_dump(mode="json")
        ),
        health_indicator=TemporalHealthIndicatorPolicy.model_validate(
            DEFAULT_TEMPORAL_HEALTH_INDICATOR_POLICY.model_dump(mode="json")
        ),
    )
    threshold = float(model_bundle["threshold"])
    scoring_payload = {
        "schema_version": "scoring_policy_bundle_v1",
        "policy_version": DEFAULT_SCORING_VERSION,
        "parent_version": None,
        "asset_id": "bearing_1",
        "channel_id": "channel_1",
        "model_ref": f"artifact:{definition.pilot_run_id}:pca_model",
        "model_sha256": definition.model_sha256,
        "scaler_ref": f"artifact:{definition.pilot_run_id}:pca_model#scaler",
        "scaler_sha256": definition.model_sha256,
        "features_ref": f"artifact:{definition.pilot_run_id}:windows_features",
        "features_sha256": definition.features_sha256,
        "feature_columns": feature_columns,
        "threshold": threshold,
        "threshold_operator": "greater_than",
        "aggregation_policy_id": temporal_policies.aggregation.policy_id,
        "aggregation_policy_sha256": _canonical_sha256(
            temporal_policies.aggregation.model_dump(mode="json")
        ),
        "gap_policy_id": temporal_policies.gap.policy_id,
        "gap_policy_sha256": _canonical_sha256(
            temporal_policies.gap.model_dump(mode="json")
        ),
        "health_policy_id": temporal_policies.health.policy_id,
        "health_policy_sha256": _canonical_sha256(
            temporal_policies.health.model_dump(mode="json")
        ),
        "health_indicator_policy_id": (
            temporal_policies.health_indicator.policy_id
        ),
        "health_indicator_policy_sha256": _canonical_sha256(
            temporal_policies.health_indicator.model_dump(mode="json")
        ),
    }
    scoring_policy = ScoringPolicyBundle(
        **scoring_payload,
        policy_sha256=_canonical_sha256(scoring_payload),
    )
    modeled_specs = tuple(
        spec
        for spec in definition.asset_specs
        if spec.analysis_status == "modeled"
    )
    if len(modeled_specs) != 1 or (
        scoring_policy.asset_id,
        scoring_policy.channel_id,
    ) != (
        modeled_specs[0].asset_id,
        modeled_specs[0].channel_id,
    ):
        raise MonitoringReplayUnavailableError(
            "registered modeled asset/channel does not match the frozen scorer"
        )
    activation_policy = _activation_policy_for_kind(
        definition,
        "P0",
        expected_cadence_seconds=(
            temporal_policies.gap.expected_cadence_seconds
        ),
    )

    bootstrap_ids = tuple(
        snapshot_id
        for snapshot_id in ordered_snapshot_ids
        if snapshot_id not in set(monitoring_ids)
    )
    if (
        len(bootstrap_ids) != definition.expected_bootstrap_count
        or ordered_snapshot_ids[: definition.expected_bootstrap_count]
        != bootstrap_ids
    ):
        raise MonitoringReplayUnavailableError(
            "registered scenario has an invalid causal bootstrap prefix"
        )
    provisional = _ScenarioRuntime(
        definition=definition,
        features=features,
        feature_groups=groups,
        ordered_snapshot_ids=ordered_snapshot_ids,
        monitoring_snapshot_ids=monitoring_ids,
        manifest_records=manifest_records,
        model_bundle=model_bundle,
        scoring_policy=scoring_policy,
        activation_policy=activation_policy,
        temporal_policies=temporal_policies,
        bootstrap_snapshots=(),
        bootstrap_checkpoint=ReplayAssetCheckpoint(
            asset_id="bearing_1",
            analysis_status="modeled",
            scoring_version=scoring_policy.policy_version,
        ),
    )
    bootstrap_snapshots, checkpoint = _bootstrap_for_policies(
        provisional,
        scoring_policy=scoring_policy,
        temporal_policies=temporal_policies,
    )
    provisional.bootstrap_snapshots = bootstrap_snapshots
    provisional.bootstrap_checkpoint = checkpoint
    return provisional


def _bootstrap_for_policies(
    runtime: _ScenarioRuntime,
    *,
    scoring_policy: ScoringPolicyBundle,
    temporal_policies: _TemporalPolicyDependencies,
) -> tuple[tuple[_SafeSnapshot, ...], ReplayAssetCheckpoint]:
    definition = runtime.definition
    bootstrap_ids = runtime.ordered_snapshot_ids[
        : definition.expected_bootstrap_count
    ]
    bootstrap_snapshots = tuple(
        _score_snapshot(
            runtime,
            snapshot_id,
            scoring_policy=scoring_policy,
            aggregation_policy=temporal_policies.aggregation,
        )
        for snapshot_id in bootstrap_ids
    )
    annotated = annotate_temporal_gaps(
        [item.health_row() for item in bootstrap_snapshots],
        policy=temporal_policies.gap,
    )
    health_points = causal_temporal_health_points(
        annotated,
        score_min=None,
        score_max=None,
        health_policy=temporal_policies.health,
        indicator_policy=temporal_policies.health_indicator,
    )
    last_segment = int(annotated[-1]["temporal_segment_id"])
    same_segment_indexes = [
        index
        for index, row in enumerate(annotated)
        if int(row["temporal_segment_id"]) == last_segment
    ]
    history_limit = max(
        temporal_policies.health_indicator.smoothing_window,
        temporal_policies.health_indicator.trend_window,
    ) - 1
    tail_indexes = same_segment_indexes[-history_limit:]
    raw_history = tuple(
        float(health_points[index]["health_index_raw"])
        for index in tail_indexes
        if health_points[index]["health_index_raw"] is not None
    )
    smoothed_history = tuple(
        float(health_points[index]["health_index_smoothed"])
        for index in tail_indexes
        if health_points[index]["health_index_smoothed"] is not None
    )
    states = [str(point["health_state"]) for point in health_points]
    segment_ids = [int(row["temporal_segment_id"]) for row in annotated]
    last_snapshot = bootstrap_snapshots[-1]
    checkpoint = ReplayAssetCheckpoint(
        asset_id=scoring_policy.asset_id,
        analysis_status="modeled",
        segment_id=last_segment,
        alert_persistence_count=_trailing_alert_count(states, segment_ids),
        recovery_persistence_count=_trailing_recovery_count(states, segment_ids),
        raw_health_history=raw_history,
        smoothed_health_history=smoothed_history,
        last_source_time=last_snapshot.source_time,
        last_frame_id=(
            f"bootstrap:{last_snapshot.snapshot_id}:{scoring_policy.asset_id}"
        ),
        last_health_state=states[-1],
        scoring_version=scoring_policy.policy_version,
    )
    return bootstrap_snapshots, checkpoint


def _initial_session_checkpoints(
    modeled_checkpoint: ReplayAssetCheckpoint,
    asset_specs: tuple[ReplayAssetSpec, ...],
) -> tuple[ReplayAssetCheckpoint, ...]:
    return tuple(
        modeled_checkpoint
        if spec.analysis_status == "modeled"
        else ReplayAssetCheckpoint(
            asset_id=spec.asset_id,
            analysis_status=spec.analysis_status,
        )
        for spec in asset_specs
    )


def _score_snapshot(
    runtime: _ScenarioRuntime,
    snapshot_id: str,
    *,
    scoring_policy: ScoringPolicyBundle | None = None,
    aggregation_policy: SnapshotAggregationPolicy | None = None,
) -> _SafeSnapshot:
    group = runtime.feature_groups[snapshot_id]
    scores = score_frozen_feature_rows(runtime.model_bundle, group)
    active_scoring = scoring_policy or runtime.scoring_policy
    threshold = active_scoring.threshold
    rows: list[dict[str, Any]] = []
    safe_records: list[dict[str, Any]] = []
    for row, score in zip(group.to_dict("records"), scores, strict=True):
        safe = {
            key: _json_scalar(row[key]) for key in SAFE_FEATURE_INPUT_COLUMNS
        }
        safe_records.append(safe)
        rows.append(
            {
                **{key: safe[key] for key in SAFE_FEATURE_METADATA_COLUMNS},
                "anomaly_score": float(score),
                "threshold": threshold,
                "predicted_anomaly": int(float(score) > threshold),
            }
        )
    aggregated = aggregate_temporal_snapshots(
        rows,
        policy=aggregation_policy or runtime.temporal_policies.aggregation,
    )
    if len(aggregated) != 1:
        raise MonitoringReplayUnavailableError(
            f"snapshot {snapshot_id} could not be aggregated atomically"
        )
    result = aggregated[0]
    record = runtime.manifest_records[snapshot_id]
    if record.timestamp_start is None:
        raise MonitoringReplayUnavailableError(
            f"snapshot {snapshot_id} has no source timestamp"
        )
    return _SafeSnapshot(
        snapshot_id=snapshot_id,
        run_id=str(result["run_id"]),
        source_time=record.timestamp_start,
        temporal_partition=str(result["temporal_partition"]),
        source_path=Path(record.source_path),
        input_record_hash=_canonical_sha256(safe_records),
        score=float(result["anomaly_score"]),
        threshold=float(result["threshold"]),
        predicted_anomaly=int(result["predicted_anomaly"]),
        n_windows=int(result["n_windows"]),
        n_alerted_windows=int(result["n_alerted_windows"]),
        window_alert_fraction=float(result["window_alert_fraction"]),
    )


def _frames_for_snapshot(
    runtime: _ScenarioRuntime,
    snapshot: _SafeSnapshot,
    *,
    tick_id: str,
    state: ReplaySessionState,
    policies: _PersistedSessionPolicies,
    asset_specs: tuple[ReplayAssetSpec, ...],
) -> tuple[
    tuple[MonitoringFrame, ...],
    tuple[ReplayAssetCheckpoint, ...],
    str,
]:
    checkpoints = {item.asset_id: item for item in state.asset_checkpoints}
    modeled_spec = next(
        spec
        for spec in asset_specs
        if spec.analysis_status == "modeled"
    )
    previous = checkpoints[modeled_spec.asset_id]
    interval = (
        None
        if previous.last_source_time is None
        else (snapshot.source_time - previous.last_source_time).total_seconds()
    )
    gap_detected = bool(
        interval is not None
        and interval > policies.temporal.gap.max_contiguous_interval_seconds
    )
    segment_id = previous.segment_id + int(gap_detected)
    base = temporal_health_values(
        snapshot.health_row(),
        score_min=None,
        score_max=None,
        policy=policies.temporal.health,
    )
    raw_health = float(base["health_index"])
    raw_history = () if gap_detected else previous.raw_health_history
    smoothing_window = policies.temporal.health_indicator.smoothing_window
    smoothing_input = (*raw_history, raw_health)
    smoothed_health = sum(smoothing_input[-smoothing_window:]) / len(
        smoothing_input[-smoothing_window:]
    )
    smoothed_history = () if gap_detected else previous.smoothed_health_history
    history_limit = max(
        policies.temporal.health_indicator.smoothing_window,
        policies.temporal.health_indicator.trend_window,
    ) - 1
    health_state = str(base["health_state"])
    is_alert = health_state in {"warning", "critical"}
    alert_count = 1 + (0 if gap_detected else previous.alert_persistence_count) if is_alert else 0
    recovery_count = (
        0
        if is_alert
        else 1 + (0 if gap_detected else previous.recovery_persistence_count)
    )

    try:
        raw_input_hash = _file_sha256(snapshot.source_path)
        channels = read_signal_channels(snapshot.source_path)
        if _file_sha256(snapshot.source_path) != raw_input_hash:
            raise MonitoringReplayConflictError(
                "raw snapshot changed while its telemetry was being read"
            )
    except (OSError, ValueError):
        raw_input_hash = None
        channels = {}
    telemetry: dict[str, MonitoringTelemetrySummary] = {}
    for channel_id, channel in channels.items():
        values = np.asarray(channel.values, dtype=float).reshape(-1)
        finite = values[np.isfinite(values)]
        if finite.size:
            telemetry[channel_id] = MonitoringTelemetrySummary(
                signal_rms=float(np.sqrt(np.mean(finite**2))),
                signal_peak_abs=float(np.max(np.abs(finite))),
                n_samples=int(finite.size),
            )

    evidence_ref = f"evidence:features:{snapshot.snapshot_id}:{snapshot.input_record_hash}"
    raw_evidence_ref = (
        f"evidence:raw:{snapshot.snapshot_id}:{raw_input_hash}"
        if raw_input_hash is not None
        else f"evidence:raw:{snapshot.snapshot_id}:unavailable"
    )
    modeled_frame_id = f"{tick_id}:{modeled_spec.asset_id}:{modeled_spec.channel_id}"
    frames: list[MonitoringFrame] = [
        MonitoringFrame(
            frame_id=modeled_frame_id,
            tick_id=tick_id,
            asset_id=modeled_spec.asset_id,
            channel_id=modeled_spec.channel_id,
            interval_seconds=interval,
            gap_detected=gap_detected,
            segment_id=segment_id,
            analysis_status="modeled",
            telemetry=telemetry.get(modeled_spec.channel_id),
            score=snapshot.score,
            threshold=snapshot.threshold,
            predicted_anomaly=bool(snapshot.predicted_anomaly),
            score_ratio=float(base["score_ratio"]),
            health_index=smoothed_health,
            risk_index=100.0 - smoothed_health,
            health_state=health_state,
            scoring_version=state.active_policy_refs.scoring_version,
            evidence_refs=(evidence_ref, raw_evidence_ref),
        )
    ]
    new_checkpoints: list[ReplayAssetCheckpoint] = [
        ReplayAssetCheckpoint(
            asset_id=modeled_spec.asset_id,
            analysis_status="modeled",
            segment_id=segment_id,
            alert_persistence_count=alert_count,
            recovery_persistence_count=recovery_count,
            raw_health_history=tuple((*raw_history, raw_health)[-history_limit:]),
            smoothed_health_history=tuple(
                (*smoothed_history, smoothed_health)[-history_limit:]
            ),
            last_source_time=snapshot.source_time,
            last_frame_id=modeled_frame_id,
            last_health_state=health_state,
            scoring_version=state.active_policy_refs.scoring_version,
        )
    ]
    for spec in asset_specs:
        if spec.analysis_status == "modeled":
            continue
        frame_id = f"{tick_id}:{spec.asset_id}:{spec.channel_id}"
        summary = telemetry.get(spec.channel_id)
        if summary is None:
            frames.append(
                MonitoringFrame(
                    frame_id=frame_id,
                    tick_id=tick_id,
                    asset_id=spec.asset_id,
                    channel_id=spec.channel_id,
                    interval_seconds=interval,
                    gap_detected=gap_detected,
                    analysis_status="unavailable",
                    unavailable_reason="No se pudo leer el canal en este snapshot.",
                    evidence_refs=(raw_evidence_ref,),
                )
            )
            new_checkpoints.append(
                ReplayAssetCheckpoint(
                    asset_id=spec.asset_id,
                    analysis_status="unavailable",
                    last_source_time=snapshot.source_time,
                    last_frame_id=frame_id,
                )
            )
            continue
        frames.append(
            MonitoringFrame(
                frame_id=frame_id,
                tick_id=tick_id,
                asset_id=spec.asset_id,
                channel_id=spec.channel_id,
                interval_seconds=interval,
                gap_detected=gap_detected,
                analysis_status="telemetry_only",
                telemetry=summary,
                evidence_refs=(raw_evidence_ref,),
            )
        )
        new_checkpoints.append(
            ReplayAssetCheckpoint(
                asset_id=spec.asset_id,
                analysis_status="telemetry_only",
                last_source_time=snapshot.source_time,
                last_frame_id=frame_id,
            )
        )
    return (
        tuple(frames),
        tuple(new_checkpoints),
        _canonical_sha256(
            {
                "features_sha256": snapshot.input_record_hash,
                "raw_sha256": raw_input_hash,
            }
        ),
    )


def _read_commits(directory: Path) -> list[dict[str, Any]]:
    commits: list[dict[str, Any]] = []
    if not directory.is_dir():
        return commits
    previous_commit_sha256 = "0" * 64
    for path in sorted(directory.glob("*.json")):
        payload = _read_json(path)
        commit_sha256 = payload.get("commit_sha256")
        commit_core = {
            key: value for key, value in payload.items() if key != "commit_sha256"
        }
        if (
            payload.get("schema_version") != "monitoring_replay_commit_v1"
            or payload.get("previous_commit_sha256") != previous_commit_sha256
            or not isinstance(commit_sha256, str)
            or _canonical_sha256(commit_core) != commit_sha256
        ):
            raise MonitoringReplayConflictError(
                "monitoring commit SHA-256 chain is invalid"
            )
        commits.append(
            {
                "command": ReplayStepCommand.model_validate(payload["command"]),
                "receipt": ReplayStepReceipt.model_validate(payload["receipt"]),
                "tick": ReplayTick.model_validate(payload["tick"]),
                "state": ReplaySessionState.model_validate(payload["state"]),
                "triggers": tuple(
                    MonitoringTriggerEvent.model_validate(item)
                    for item in payload.get("triggers", ())
                ),
                "commit_sha256": commit_sha256,
            }
        )
        previous_commit_sha256 = commit_sha256
    for expected, item in enumerate(commits, start=1):
        if item["tick"].sequence != expected:
            raise MonitoringReplayConflictError(
                "monitoring commit ledger has a missing or duplicate sequence"
            )
    return commits


def _temporal_policy_payload(
    policies: _TemporalPolicyDependencies,
) -> dict[str, Any]:
    return {
        "schema_version": "monitoring_temporal_policy_dependencies_v1",
        "aggregation": policies.aggregation.model_dump(mode="json"),
        "gap": policies.gap.model_dump(mode="json"),
        "health": policies.health.model_dump(mode="json"),
        "health_indicator": policies.health_indicator.model_dump(mode="json"),
    }


def _load_persisted_session_policies(
    session_dir: Path,
) -> _PersistedSessionPolicies:
    scoring = ScoringPolicyBundle.model_validate(
        _read_json(session_dir / "scoring_policy.json")
    )
    activation = AgentActivationPolicy.model_validate(
        _read_json(session_dir / "activation_policy.json")
    )
    raw_temporal = _read_json(session_dir / "temporal_policies.json")
    if raw_temporal.get("schema_version") != (
        "monitoring_temporal_policy_dependencies_v1"
    ):
        raise MonitoringReplayConflictError(
            "monitoring temporal policy dependencies have an invalid schema"
        )
    temporal = _TemporalPolicyDependencies(
        aggregation=SnapshotAggregationPolicy.model_validate(
            raw_temporal["aggregation"]
        ),
        gap=TemporalGapPolicy.model_validate(raw_temporal["gap"]),
        health=TemporalHealthPolicy.model_validate(raw_temporal["health"]),
        health_indicator=TemporalHealthIndicatorPolicy.model_validate(
            raw_temporal["health_indicator"]
        ),
    )
    if _model_contract_sha256(scoring) != scoring.policy_sha256:
        raise MonitoringReplayConflictError(
            "persisted scoring policy SHA-256 does not match its content"
        )
    if _model_contract_sha256(activation) != activation.policy_sha256:
        raise MonitoringReplayConflictError(
            "persisted activation policy SHA-256 does not match its content"
        )
    expected_temporal_hashes = {
        "aggregation": scoring.aggregation_policy_sha256,
        "gap": scoring.gap_policy_sha256,
        "health": scoring.health_policy_sha256,
        "health_indicator": scoring.health_indicator_policy_sha256,
    }
    for name, policy in (
        ("aggregation", temporal.aggregation),
        ("gap", temporal.gap),
        ("health", temporal.health),
        ("health_indicator", temporal.health_indicator),
    ):
        if _canonical_sha256(policy.model_dump(mode="json")) != (
            expected_temporal_hashes[name]
        ):
            raise MonitoringReplayConflictError(
                f"persisted {name} policy SHA-256 does not match scoring bundle"
            )
    return _PersistedSessionPolicies(
        scoring=scoring,
        activation=activation,
        temporal=temporal,
    )


def _load_bootstrap_checkpoints(
    session_dir: Path,
    config: ReplaySessionConfig,
) -> tuple[ReplayAssetCheckpoint, ...]:
    payload = _read_json(session_dir / "bootstrap_checkpoints.json")
    if payload.get("schema_version") != "monitoring_bootstrap_checkpoints_v1":
        raise MonitoringReplayConflictError(
            "monitoring bootstrap checkpoint sidecar has an invalid schema"
        )
    checkpoints = tuple(
        ReplayAssetCheckpoint.model_validate(item)
        for item in payload.get("checkpoints", ())
    )
    if not checkpoints or _canonical_sha256(
        [item.model_dump(mode="json") for item in checkpoints]
    ) != config.bootstrap_checkpoints_sha256:
        raise MonitoringReplayConflictError(
            "monitoring bootstrap checkpoint SHA-256 does not match config"
        )
    return checkpoints


def _validate_session_contract(
    config: ReplaySessionConfig,
    state: ReplaySessionState,
    commits: list[dict[str, Any]],
    policies: _PersistedSessionPolicies,
    runtime: _ScenarioRuntime,
    initial_checkpoints: tuple[ReplayAssetCheckpoint, ...],
    expected_initial_checkpoints: tuple[ReplayAssetCheckpoint, ...],
    *,
    validate_scoring: bool,
) -> None:
    config_sha256 = _canonical_sha256(config.model_dump(mode="json"))
    if config_sha256 != state.config_sha256:
        raise MonitoringReplayConflictError(
            "monitoring state config_sha256 does not match persisted config"
        )
    definition = runtime.definition
    if (
        config.pilot_id != definition.scenario_id
        or config.dataset_id != definition.dataset_id
        or config.trajectory_id != definition.trajectory_id
        or config.asset_specs != definition.asset_specs
        or config.manifest_sha256 != definition.manifest_sha256
        or policies.scoring.features_sha256 != definition.features_sha256
        or policies.scoring.model_sha256 != definition.model_sha256
        or policies.scoring.scaler_sha256 != definition.model_sha256
        or config.activation_policy_kind != policies.activation.policy_kind
    ):
        raise MonitoringReplayConflictError(
            "monitoring session artifacts no longer match the registered scenario"
        )
    expected_activation_policy = _activation_policy_for_kind(
        definition,
        config.activation_policy_kind,
        expected_cadence_seconds=(
            runtime.temporal_policies.gap.expected_cadence_seconds
        ),
    )
    if policies.scoring != runtime.scoring_policy:
        raise MonitoringReplayConflictError(
            "persisted scoring policy is not the registered frozen bundle"
        )
    if policies.temporal != runtime.temporal_policies:
        raise MonitoringReplayConflictError(
            "persisted temporal policies are not the registered frozen bundle"
        )
    if policies.activation != expected_activation_policy:
        raise MonitoringReplayConflictError(
            "persisted activation policy is not the registered policy bundle"
        )
    modeled_specs = tuple(
        spec for spec in config.asset_specs if spec.analysis_status == "modeled"
    )
    if len(modeled_specs) != 1 or (
        policies.scoring.asset_id,
        policies.scoring.channel_id,
    ) != (
        modeled_specs[0].asset_id,
        modeled_specs[0].channel_id,
    ):
        raise MonitoringReplayConflictError(
            "monitoring scoring policy is not bound to the modeled asset/channel"
        )
    fingerprint = _source_fingerprint(
        definition,
        policies.scoring,
        policies.activation,
    )
    if config.source_fingerprint_sha256 != fingerprint:
        raise MonitoringReplayConflictError(
            "monitoring source fingerprint does not match persisted policies"
        )
    expected_refs = ActivePolicyRefs(
        scoring_version=policies.scoring.policy_version,
        activation_version=policies.activation.policy_version,
    )
    if (
        config.initial_policy_refs != expected_refs
        or state.active_policy_refs != expected_refs
    ):
        raise MonitoringReplayConflictError(
            "monitoring active policy refs do not match persisted bundles"
        )
    expected_policy_ids = (
        policies.temporal.aggregation.policy_id,
        policies.temporal.gap.policy_id,
        policies.temporal.health.policy_id,
        policies.temporal.health_indicator.policy_id,
    )
    declared_policy_ids = (
        policies.scoring.aggregation_policy_id,
        policies.scoring.gap_policy_id,
        policies.scoring.health_policy_id,
        policies.scoring.health_indicator_policy_id,
    )
    if expected_policy_ids != declared_policy_ids:
        raise MonitoringReplayConflictError(
            "monitoring temporal policy IDs do not match scoring bundle"
        )
    _validate_checkpoint_set(config, initial_checkpoints, expected_refs)
    modeled_initial = next(
        item for item in initial_checkpoints if item.analysis_status == "modeled"
    )
    if policies.activation.policy_kind == "P3" and (
        modeled_initial.alert_persistence_count != 0
        or modeled_initial.last_health_state in {"warning", "critical"}
    ):
        raise MonitoringReplayConflictError(
            "P3 bootstrap boundary contains an unsupported active alert episode"
        )
    if initial_checkpoints != expected_initial_checkpoints:
        raise MonitoringReplayConflictError(
            "monitoring bootstrap sidecar does not match the frozen causal seed"
        )
    if not commits:
        expected_activation_checkpoint = initial_activation_checkpoint(
            policies.activation
        )
        if (
            state.status != "ready"
            or state.mode != config.initial_mode
            or state.speed_multiplier != config.initial_speed_multiplier
            or state.asset_checkpoints != initial_checkpoints
            or state.activation_checkpoint != expected_activation_checkpoint
            or state.last_trigger_id is not None
            or state.child_run_ids
            or state.active_child_run_id is not None
            or state.last_command_id is not None
        ):
            raise MonitoringReplayConflictError(
                "monitoring initial state does not match the frozen causal seed"
            )
    _validate_state_binding(config, state, expected_refs)
    previous_checkpoints = initial_checkpoints
    previous_activation_checkpoint = initial_activation_checkpoint(
        policies.activation
    )
    prior_trigger_events: list[MonitoringTriggerEvent] = []
    previous_last_trigger_id: str | None = None
    for index, item in enumerate(commits, start=1):
        tick = item["tick"]
        committed_state = item["state"]
        command = item["command"]
        if (
            tick.session_id != config.session_id
            or committed_state.session_id != config.session_id
            or command.session_id != config.session_id
            or tick.cursor != index - 1
            or tick.sequence != index
            or committed_state.sequence != index
            or committed_state.revision != index
            or command.expected_revision != index - 1
            or committed_state.config_sha256 != config_sha256
            or tick.active_policy_refs != expected_refs
            or committed_state.active_policy_refs != expected_refs
        ):
            raise MonitoringReplayConflictError(
                "monitoring commit ledger violates session continuity"
            )
        expected_status = (
            "completed"
            if index == len(runtime.monitoring_snapshot_ids)
            else "paused"
        )
        if (
            committed_state.status != expected_status
            or committed_state.mode != config.initial_mode
            or committed_state.speed_multiplier != config.initial_speed_multiplier
            or committed_state.failure_reason is not None
            or committed_state.child_run_ids
            or committed_state.active_child_run_id is not None
        ):
            raise MonitoringReplayConflictError(
                "monitoring lifecycle state is inconsistent with its ledger"
            )
        _validate_committed_tick_binding(
            config,
            committed_state,
            tick,
            item["receipt"],
            command,
            expected_refs,
            runtime,
            index=index,
        )
        if validate_scoring:
            expected_snapshot = _score_snapshot(
                runtime,
                runtime.monitoring_snapshot_ids[index - 1],
                scoring_policy=policies.scoring,
                aggregation_policy=policies.temporal.aggregation,
            )
            _validate_scored_tick_binding(tick, expected_snapshot, config)
        _validate_checkpoint_transition(
            config,
            previous_checkpoints,
            committed_state,
            tick,
            policies,
        )
        try:
            expected_trigger_result = evaluate_monitoring_triggers(
                session_id=config.session_id,
                tick=tick,
                previous_asset_checkpoints=previous_checkpoints,
                current_asset_checkpoints=committed_state.asset_checkpoints,
                prior_events=tuple(prior_trigger_events),
                policy=policies.activation,
                checkpoint=previous_activation_checkpoint,
                session_completed=(index == len(runtime.monitoring_snapshot_ids)),
            )
        except ValueError as exc:
            raise MonitoringReplayConflictError(
                f"monitoring trigger ledger cannot be reconstructed: {exc}"
            ) from exc
        expected_last_trigger_id = (
            expected_trigger_result.events[-1].trigger_id
            if expected_trigger_result.events
            else previous_last_trigger_id
        )
        if (
            item["triggers"] != expected_trigger_result.events
            or committed_state.activation_checkpoint
            != expected_trigger_result.checkpoint
            or committed_state.last_trigger_id != expected_last_trigger_id
        ):
            raise MonitoringReplayConflictError(
                "monitoring trigger events do not follow the causal policy"
            )
        prior_trigger_events.extend(item["triggers"])
        previous_activation_checkpoint = expected_trigger_result.checkpoint
        previous_last_trigger_id = expected_last_trigger_id
        previous_checkpoints = committed_state.asset_checkpoints


def _validate_state_binding(
    config: ReplaySessionConfig,
    state: ReplaySessionState,
    expected_refs: ActivePolicyRefs,
) -> None:
    _validate_checkpoint_set(config, state.asset_checkpoints, expected_refs)
    if (
        state.activation_checkpoint is None
        or state.activation_checkpoint.activation_version
        != expected_refs.activation_version
    ):
        raise MonitoringReplayConflictError(
            "monitoring activation checkpoint is missing or uses another policy"
        )


def _validate_checkpoint_set(
    config: ReplaySessionConfig,
    checkpoint_values: tuple[ReplayAssetCheckpoint, ...],
    expected_refs: ActivePolicyRefs,
) -> None:
    specs = {spec.asset_id: spec for spec in config.asset_specs}
    checkpoints = {item.asset_id: item for item in checkpoint_values}
    if set(checkpoints) != set(specs):
        raise MonitoringReplayConflictError(
            "monitoring checkpoints do not match configured assets"
        )
    for asset_id, spec in specs.items():
        checkpoint = checkpoints[asset_id]
        if spec.analysis_status == "modeled":
            if (
                checkpoint.analysis_status != "modeled"
                or checkpoint.scoring_version != expected_refs.scoring_version
            ):
                raise MonitoringReplayConflictError(
                    "modeled checkpoint is not bound to the active scorer"
                )
        elif spec.analysis_status == "telemetry_only":
            if checkpoint.analysis_status not in {
                "telemetry_only",
                "unavailable",
            }:
                raise MonitoringReplayConflictError(
                    "context checkpoint has an invalid analysis status"
                )
        elif checkpoint.analysis_status != "unavailable":
            raise MonitoringReplayConflictError(
                "unavailable asset has an invalid checkpoint status"
            )


def _validate_checkpoint_transition(
    config: ReplaySessionConfig,
    previous_values: tuple[ReplayAssetCheckpoint, ...],
    state: ReplaySessionState,
    tick: ReplayTick,
    policies: _PersistedSessionPolicies,
) -> None:
    previous = {item.asset_id: item for item in previous_values}
    actual = {item.asset_id: item for item in state.asset_checkpoints}
    frames = {(frame.asset_id, frame.channel_id): frame for frame in tick.frames}
    modeled_spec = next(
        spec for spec in config.asset_specs if spec.analysis_status == "modeled"
    )
    modeled_frame = frames[(modeled_spec.asset_id, modeled_spec.channel_id)]
    modeled_previous = previous[modeled_spec.asset_id]
    interval = (
        None
        if modeled_previous.last_source_time is None
        else (tick.source_time - modeled_previous.last_source_time).total_seconds()
    )
    gap_detected = bool(
        interval is not None
        and interval > policies.temporal.gap.max_contiguous_interval_seconds
    )
    for frame in tick.frames:
        if frame.interval_seconds != interval or frame.gap_detected != gap_detected:
            raise MonitoringReplayConflictError(
                "monitoring frame gap transition is inconsistent"
            )
    expected_segment = modeled_previous.segment_id + int(gap_detected)
    base = temporal_health_values(
        {
            "anomaly_score": modeled_frame.score,
            "threshold": modeled_frame.threshold,
            "predicted_anomaly": int(bool(modeled_frame.predicted_anomaly)),
        },
        score_min=None,
        score_max=None,
        policy=policies.temporal.health,
    )
    raw_health = float(base["health_index"])
    raw_history = () if gap_detected else modeled_previous.raw_health_history
    smoothing_window = policies.temporal.health_indicator.smoothing_window
    smoothing_input = (*raw_history, raw_health)
    smoothed_health = sum(smoothing_input[-smoothing_window:]) / len(
        smoothing_input[-smoothing_window:]
    )
    smoothed_history = (
        () if gap_detected else modeled_previous.smoothed_health_history
    )
    history_limit = max(
        policies.temporal.health_indicator.smoothing_window,
        policies.temporal.health_indicator.trend_window,
    ) - 1
    health_state = str(base["health_state"])
    is_alert = health_state in {"warning", "critical"}
    alert_count = (
        1 + (0 if gap_detected else modeled_previous.alert_persistence_count)
        if is_alert
        else 0
    )
    recovery_count = (
        0
        if is_alert
        else 1
        + (0 if gap_detected else modeled_previous.recovery_persistence_count)
    )
    expected_modeled = ReplayAssetCheckpoint(
        asset_id=modeled_spec.asset_id,
        analysis_status="modeled",
        segment_id=expected_segment,
        alert_persistence_count=alert_count,
        recovery_persistence_count=recovery_count,
        raw_health_history=tuple((*raw_history, raw_health)[-history_limit:]),
        smoothed_health_history=tuple(
            (*smoothed_history, smoothed_health)[-history_limit:]
        ),
        last_source_time=tick.source_time,
        last_frame_id=modeled_frame.frame_id,
        last_health_state=health_state,
        scoring_version=policies.scoring.policy_version,
    )
    if actual[modeled_spec.asset_id] != expected_modeled or not all(
        (
            np.isclose(
                float(modeled_frame.score_ratio),
                float(base["score_ratio"]),
                rtol=0.0,
                atol=1e-12,
            ),
            np.isclose(
                float(modeled_frame.health_index),
                smoothed_health,
                rtol=0.0,
                atol=1e-12,
            ),
            np.isclose(
                float(modeled_frame.risk_index),
                100.0 - smoothed_health,
                rtol=0.0,
                atol=1e-12,
            ),
            modeled_frame.health_state == health_state,
            modeled_frame.segment_id == expected_segment,
        )
    ):
        raise MonitoringReplayConflictError(
            "modeled checkpoint does not follow the previous causal state"
        )
    for spec in config.asset_specs:
        if spec.analysis_status == "modeled":
            continue
        frame = frames[(spec.asset_id, spec.channel_id)]
        expected_context = ReplayAssetCheckpoint(
            asset_id=spec.asset_id,
            analysis_status=frame.analysis_status,
            last_source_time=tick.source_time,
            last_frame_id=frame.frame_id,
        )
        if actual[spec.asset_id] != expected_context:
            raise MonitoringReplayConflictError(
                "context checkpoint does not follow its committed frame"
            )


def _validate_committed_tick_binding(
    config: ReplaySessionConfig,
    state: ReplaySessionState,
    tick: ReplayTick,
    receipt: ReplayStepReceipt,
    command: ReplayStepCommand,
    expected_refs: ActivePolicyRefs,
    runtime: _ScenarioRuntime,
    *,
    index: int,
) -> None:
    _validate_state_binding(config, state, expected_refs)
    expected_snapshot_id = runtime.monitoring_snapshot_ids[index - 1]
    expected_source_time = runtime.manifest_records[expected_snapshot_id].timestamp_start
    if (
        tick.tick_id != f"{config.session_id}:tick:{index - 1:06d}"
        or tick.snapshot_id != expected_snapshot_id
        or tick.source_time != expected_source_time
        or state.execution_cursor != index - 1
        or state.last_committed_tick_id != tick.tick_id
        or state.last_command_id != command.command_id
        or receipt.outcome != "applied"
        or receipt.command_id != command.command_id
        or receipt.session_id != config.session_id
        or receipt.accepted_revision != index
        or receipt.tick_id != tick.tick_id
    ):
        raise MonitoringReplayConflictError(
            "monitoring committed tick identity or receipt is inconsistent"
        )
    specs = {
        (spec.asset_id, spec.channel_id): spec for spec in config.asset_specs
    }
    frames = {(frame.asset_id, frame.channel_id): frame for frame in tick.frames}
    if set(frames) != set(specs):
        raise MonitoringReplayConflictError(
            "monitoring tick frames do not match configured coordinates"
        )
    checkpoints = {item.asset_id: item for item in state.asset_checkpoints}
    for coordinate, spec in specs.items():
        frame = frames[coordinate]
        checkpoint = checkpoints[spec.asset_id]
        valid_statuses = (
            {"modeled"}
            if spec.analysis_status == "modeled"
            else {"telemetry_only", "unavailable"}
            if spec.analysis_status == "telemetry_only"
            else {"unavailable"}
        )
        if (
            frame.analysis_status not in valid_statuses
            or checkpoint.analysis_status != frame.analysis_status
            or checkpoint.last_source_time != tick.source_time
            or checkpoint.last_frame_id != frame.frame_id
        ):
            raise MonitoringReplayConflictError(
                "monitoring frame and checkpoint bindings are inconsistent"
            )
        if frame.analysis_status == "modeled" and (
            checkpoint.segment_id != frame.segment_id
            or checkpoint.last_health_state != frame.health_state
        ):
            raise MonitoringReplayConflictError(
                "modeled frame and checkpoint diagnostic state diverge"
            )


def _validate_scored_tick_binding(
    tick: ReplayTick,
    expected: _SafeSnapshot,
    config: ReplaySessionConfig,
) -> None:
    modeled_spec = next(
        spec for spec in config.asset_specs if spec.analysis_status == "modeled"
    )
    modeled_frame = next(
        frame
        for frame in tick.frames
        if (frame.asset_id, frame.channel_id)
        == (modeled_spec.asset_id, modeled_spec.channel_id)
    )
    expected_feature_ref = (
        f"evidence:features:{expected.snapshot_id}:{expected.input_record_hash}"
    )
    raw_prefix = f"evidence:raw:{expected.snapshot_id}:"
    raw_refs = tuple(
        reference
        for reference in modeled_frame.evidence_refs
        if reference.startswith(raw_prefix)
    )
    if (
        modeled_frame.score != expected.score
        or modeled_frame.threshold != expected.threshold
        or modeled_frame.predicted_anomaly != bool(expected.predicted_anomaly)
        or expected_feature_ref not in modeled_frame.evidence_refs
        or len(raw_refs) != 1
        or any(raw_refs[0] not in frame.evidence_refs for frame in tick.frames)
    ):
        raise MonitoringReplayConflictError(
            "monitoring frame is not bound to the frozen snapshot scorer"
        )
    raw_token = raw_refs[0][len(raw_prefix) :]
    if raw_token == "unavailable":
        raw_sha256 = None
    else:
        try:
            if len(raw_token) != 64:
                raise ValueError
            int(raw_token, 16)
        except ValueError as exc:
            raise MonitoringReplayConflictError(
                "monitoring raw evidence reference has an invalid SHA-256"
            ) from exc
        raw_sha256 = raw_token
    expected_input_hash = _canonical_sha256(
        {
            "features_sha256": expected.input_record_hash,
            "raw_sha256": raw_sha256,
        }
    )
    if tick.input_record_hash != expected_input_hash:
        raise MonitoringReplayConflictError(
            "monitoring tick input hash does not match its evidence references"
        )


def _source_fingerprint(
    definition: RegisteredReplayScenario,
    scoring: ScoringPolicyBundle,
    activation: AgentActivationPolicy,
) -> str:
    return _canonical_sha256(
        {
            "scenario_id": definition.scenario_id,
            "dataset_id": definition.dataset_id,
            "trajectory_id": definition.trajectory_id,
            "pilot_run_id": definition.pilot_run_id,
            "manifest_sha256": definition.manifest_sha256,
            "features_sha256": definition.features_sha256,
            "model_sha256": definition.model_sha256,
            "expected_snapshot_count": definition.expected_snapshot_count,
            "expected_bootstrap_count": definition.expected_bootstrap_count,
            "expected_monitoring_count": definition.expected_monitoring_count,
            "expected_windows_per_snapshot": (
                definition.expected_windows_per_snapshot
            ),
            "asset_specs": [
                spec.model_dump(mode="json") for spec in definition.asset_specs
            ],
            "scoring_policy_sha256": scoring.policy_sha256,
            "activation_policy_sha256": activation.policy_sha256,
        }
    )


def _model_contract_sha256(model: Any) -> str:
    return _canonical_sha256(
        model.model_dump(mode="json", exclude={"policy_sha256"})
    )


def _command_receipt_path(session_dir: Path, command_id: str) -> Path:
    digest = hashlib.sha256(command_id.encode("utf-8")).hexdigest()
    return session_dir / "receipts" / f"{digest}.json"


def _write_command_response(
    session_dir: Path,
    command: ReplayStepCommand,
    response: MonitoringStepResponse,
) -> None:
    core = {
        "schema_version": "monitoring_command_receipt_v1",
        "command": command.model_dump(mode="json"),
        "response": response.model_dump(mode="json"),
    }
    _write_json_atomic(
        _command_receipt_path(session_dir, command.command_id),
        {
            **core,
            "receipt_sha256": _canonical_sha256(core),
        },
    )


def _read_command_response(
    session_dir: Path,
    command_id: str,
) -> tuple[ReplayStepCommand, MonitoringStepResponse] | None:
    path = _command_receipt_path(session_dir, command_id)
    if not path.is_file():
        return None
    payload = _read_json(path)
    receipt_sha256 = payload.get("receipt_sha256")
    core = {
        key: value for key, value in payload.items() if key != "receipt_sha256"
    }
    if (
        payload.get("schema_version") != "monitoring_command_receipt_v1"
        or not isinstance(receipt_sha256, str)
        or _canonical_sha256(core) != receipt_sha256
    ):
        raise MonitoringReplayConflictError(
            "persisted monitoring command receipt SHA-256 is invalid"
        )
    command = ReplayStepCommand.model_validate(payload["command"])
    response = MonitoringStepResponse.model_validate(payload["response"])
    if command.command_id != command_id:
        raise MonitoringReplayConflictError(
            "persisted monitoring command receipt has an invalid identity"
        )
    return command, response


def _ensure_same_command(
    original: ReplayStepCommand,
    repeated: ReplayStepCommand,
) -> None:
    if original.model_dump(mode="json", exclude={"issued_at"}) != repeated.model_dump(
        mode="json",
        exclude={"issued_at"},
    ):
        raise MonitoringReplayConflictError(
            "command_id was already used with another command payload"
        )


def _trailing_alert_count(states: list[str], segment_ids: list[int]) -> int:
    if not states:
        return 0
    active_segment = segment_ids[-1]
    count = 0
    for state, segment_id in zip(reversed(states), reversed(segment_ids), strict=True):
        if segment_id != active_segment or state not in {"warning", "critical"}:
            break
        count += 1
    return count


def _trailing_recovery_count(states: list[str], segment_ids: list[int]) -> int:
    if not states:
        return 0
    active_segment = segment_ids[-1]
    count = 0
    for state, segment_id in zip(reversed(states), reversed(segment_ids), strict=True):
        if segment_id != active_segment or state in {"warning", "critical"}:
            break
        count += 1
    return count


def _canonical_sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_scalar(value: Any) -> str | int | float | bool | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MonitoringReplayConflictError(
            f"invalid monitoring persistence file: {path.name}"
        ) from exc


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
