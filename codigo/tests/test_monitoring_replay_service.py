from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

from codigo.app.schemas.dataset import CommonManifestRecord
from codigo.app.schemas.monitoring_replay import ReplayAssetSpec, ReplayStepCommand
from codigo.app.services.common_manifest import write_common_manifest
from codigo.app.services.monitoring_replay import (
    SAFE_FEATURE_COLUMNS,
    SAFE_FEATURE_INPUT_COLUMNS,
    MonitoringReplayConflictError,
    MonitoringReplayStore,
    MonitoringReplayUnavailableError,
    RegisteredReplayScenario,
    _activation_policy_for_kind,
    _canonical_sha256,
)


class MonitoringReplayStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.scenario = _write_safe_scenario(self.base)
        self.store = MonitoringReplayStore(
            self.base / "sessions",
            scenarios={self.scenario.scenario_id: self.scenario},
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_manual_step_uses_safe_features_and_keeps_channels_distinct(self) -> None:
        created = self.store.create_session(
            scenario_id=self.scenario.scenario_id,
            session_id="safe-replay",
        )
        self.assertIsNone(created.state.execution_cursor)
        self.assertEqual(created.state.revision, 0)
        initial_modeled_checkpoint = next(
            checkpoint
            for checkpoint in created.state.asset_checkpoints
            if checkpoint.analysis_status == "modeled"
        )
        self.assertEqual(initial_modeled_checkpoint.recovery_persistence_count, 2)

        response = self.store.step(
            ReplayStepCommand(
                command_id="step-001",
                session_id="safe-replay",
                expected_revision=0,
            )
        )

        self.assertEqual(response.receipt.outcome, "applied")
        self.assertEqual(response.state.execution_cursor, 0)
        self.assertEqual(response.tick.cursor, 0)
        self.assertEqual(len(response.tick.frames), 4)
        self.assertEqual(response.tick.frames[0].analysis_status, "modeled")
        self.assertTrue(all(frame.telemetry for frame in response.tick.frames))
        self.assertEqual(response.tick.frames[0].interval_seconds, 600.0)
        self.assertFalse(response.tick.frames[0].gap_detected)
        self.assertTrue(
            any(
                evidence.startswith("evidence:raw:")
                and not evidence.endswith(":unavailable")
                for evidence in response.tick.frames[0].evidence_refs
            )
        )
        self.assertEqual(len(response.tick.input_record_hash), 64)
        modeled_checkpoint = next(
            checkpoint
            for checkpoint in response.state.asset_checkpoints
            if checkpoint.analysis_status == "modeled"
        )
        self.assertEqual(
            modeled_checkpoint.last_health_state,
            response.tick.frames[0].health_state,
        )
        self.assertEqual(modeled_checkpoint.recovery_persistence_count, 3)
        self.assertTrue(
            all(
                frame.score is None
                for frame in response.tick.frames
                if frame.analysis_status == "telemetry_only"
            )
        )
        runtime = self.store._runtime(self.scenario.scenario_id)
        self.assertEqual(tuple(runtime.features.columns), SAFE_FEATURE_INPUT_COLUMNS)
        self.assertFalse(
            {
                "relative_life",
                "time_to_failure_seconds",
                "label",
                "target",
                "fault_type",
            }
            & set(runtime.features.columns)
        )

    def test_step_is_durable_idempotent_and_uses_revision_cas(self) -> None:
        initial = self.store.create_session(
            scenario_id=self.scenario.scenario_id,
            session_id="durable-replay",
        )
        future_command = ReplayStepCommand(
            command_id="future-revision",
            session_id="durable-replay",
            expected_revision=1,
        )
        future_conflict = self.store.step(future_command)
        self.assertEqual(future_conflict.receipt.outcome, "revision_conflict")
        first_command = ReplayStepCommand(
            command_id="step-001",
            session_id="durable-replay",
            expected_revision=0,
        )
        first = self.store.step(first_command)
        repeated = self.store.step(first_command)
        self.assertEqual(repeated.receipt.outcome, "idempotent_replay")
        self.assertEqual(repeated.tick.tick_id, first.tick.tick_id)

        future_repeated = self.store.step(future_command)
        self.assertEqual(future_repeated.receipt.outcome, "revision_conflict")
        self.assertEqual(future_repeated.state.execution_cursor, 0)
        self.assertEqual(future_repeated.state.revision, 1)

        stale = self.store.step(
            ReplayStepCommand(
                command_id="stale-command",
                session_id="durable-replay",
                expected_revision=0,
            )
        )
        self.assertEqual(stale.receipt.outcome, "revision_conflict")
        self.assertEqual(stale.state.revision, 1)

        with self.assertRaisesRegex(
            MonitoringReplayConflictError,
            "another command payload",
        ):
            self.store.step(
                ReplayStepCommand(
                    command_id="stale-command",
                    session_id="durable-replay",
                    expected_revision=1,
                )
            )

        # Simula un crash despues del commit atomico y antes de actualizar
        # state.json. El commit debe seguir siendo la fuente autoritativa.
        state_path = self.base / "sessions" / "durable-replay" / "state.json"
        state_path.write_text(
            json.dumps(initial.state.model_dump(mode="json")),
            encoding="utf-8",
        )

        resumed_store = MonitoringReplayStore(
            self.base / "sessions",
            scenarios={self.scenario.scenario_id: self.scenario},
        )
        resumed = resumed_store.get_session("durable-replay")
        self.assertEqual(resumed.state.execution_cursor, 0)
        self.assertEqual(len(resumed.ticks), 1)

    def test_gap_resets_segment_and_end_of_stream_is_explicit(self) -> None:
        self.store.create_session(
            scenario_id=self.scenario.scenario_id,
            session_id="gap-replay",
        )
        first = self.store.step(
            ReplayStepCommand(
                command_id="step-001",
                session_id="gap-replay",
                expected_revision=0,
            )
        )
        second = self.store.step(
            ReplayStepCommand(
                command_id="step-002",
                session_id="gap-replay",
                expected_revision=1,
            )
        )
        self.assertEqual(first.tick.frames[0].segment_id, 0)
        self.assertEqual(second.tick.frames[0].segment_id, 1)
        self.assertTrue(second.tick.frames[0].gap_detected)
        self.assertEqual(second.tick.frames[0].interval_seconds, 1200.0)
        self.assertEqual(second.state.status, "completed")

        exhausted = self.store.step(
            ReplayStepCommand(
                command_id="step-003",
                session_id="gap-replay",
                expected_revision=2,
            )
        )
        self.assertEqual(exhausted.receipt.outcome, "rejected")
        self.assertIn("final monitoring tick", exhausted.receipt.reason)

    def test_p3_co_commits_gap_and_close_with_one_variable_slot(self) -> None:
        created = self.store.create_session(
            scenario_id=self.scenario.scenario_id,
            session_id="p3-replay",
            activation_policy_kind="P3",
        )
        self.assertEqual(created.config.activation_policy_kind, "P3")
        self.assertEqual(
            created.state.activation_checkpoint.variable_run_slots_reserved,
            0,
        )

        first = self.store.step(
            ReplayStepCommand(
                command_id="p3-step-001",
                session_id="p3-replay",
                expected_revision=0,
            )
        )
        second_command = ReplayStepCommand(
            command_id="p3-step-002",
            session_id="p3-replay",
            expected_revision=1,
        )
        second = self.store.step(second_command)

        self.assertEqual(first.triggers, ())
        self.assertEqual(
            [(event.trigger_type, event.lifecycle_status) for event in second.triggers],
            [("continuity_gap", "emitted"), ("session_close", "emitted")],
        )
        self.assertEqual(second.triggers[0].budget_reservation_index, 1)
        self.assertIsNone(second.triggers[1].budget_reservation_index)
        self.assertEqual(
            second.state.activation_checkpoint.variable_run_slots_reserved,
            1,
        )
        self.assertEqual(second.state.activation_checkpoint.next_event_sequence, 3)

        repeated = self.store.step(second_command)
        self.assertEqual(repeated.receipt.outcome, "idempotent_replay")
        self.assertEqual(repeated.triggers, second.triggers)
        resumed = MonitoringReplayStore(
            self.base / "sessions",
            scenarios={self.scenario.scenario_id: self.scenario},
        ).get_session("p3-replay")
        self.assertEqual(resumed.triggers, second.triggers)

    def test_p3_rejects_an_alert_episode_crossing_the_bootstrap_boundary(self) -> None:
        runtime = self.store._runtime(self.scenario.scenario_id)
        runtime.bootstrap_checkpoint = runtime.bootstrap_checkpoint.model_copy(
            update={
                "last_health_state": "warning",
                "alert_persistence_count": 2,
                "recovery_persistence_count": 0,
            }
        )

        with self.assertRaisesRegex(
            MonitoringReplayUnavailableError,
            "non-alert bootstrap boundary",
        ):
            self.store.create_session(
                scenario_id=self.scenario.scenario_id,
                session_id="p3-active-bootstrap",
                activation_policy_kind="P3",
            )

    def test_rehashed_p3_trigger_tampering_is_rejected(self) -> None:
        self.store.create_session(
            scenario_id=self.scenario.scenario_id,
            session_id="tampered-p3-trigger",
            activation_policy_kind="P3",
        )
        self.store.step(
            ReplayStepCommand(
                command_id="p3-step-001",
                session_id="tampered-p3-trigger",
                expected_revision=0,
            )
        )
        self.store.step(
            ReplayStepCommand(
                command_id="p3-step-002",
                session_id="tampered-p3-trigger",
                expected_revision=1,
            )
        )
        session_dir = self.base / "sessions" / "tampered-p3-trigger"
        commit_path = session_dir / "commits" / "000002.json"
        commit = json.loads(commit_path.read_text(encoding="utf-8"))
        commit["triggers"][0]["reason"] = "Texto alterado tras el commit."
        core = {
            key: value for key, value in commit.items() if key != "commit_sha256"
        }
        commit["commit_sha256"] = _canonical_sha256(core)
        commit_path.write_text(json.dumps(commit), encoding="utf-8")

        resumed_store = MonitoringReplayStore(
            self.base / "sessions",
            scenarios={self.scenario.scenario_id: self.scenario},
        )
        with self.assertRaisesRegex(
            MonitoringReplayConflictError,
            "trigger events do not follow",
        ):
            resumed_store.get_session("tampered-p3-trigger")

    def test_changing_future_suffix_does_not_change_first_tick(self) -> None:
        altered_base = self.base / "altered"
        altered_base.mkdir()
        altered = _write_safe_scenario(altered_base)
        data = pd.read_csv(altered.features_path)
        final_snapshot = data["file_id"] == "safe_003"
        data.loc[final_snapshot, list(SAFE_FEATURE_COLUMNS)] += 1000.0
        data.to_csv(altered.features_path, index=False)
        altered = replace(
            altered,
            features_sha256=_sha256(altered.features_path),
        )
        other_store = MonitoringReplayStore(
            altered_base / "sessions",
            scenarios={altered.scenario_id: altered},
        )
        self.store.create_session(
            scenario_id=self.scenario.scenario_id,
            session_id="original",
        )
        other_store.create_session(
            scenario_id=altered.scenario_id,
            session_id="altered",
        )

        original_tick = self.store.step(
            ReplayStepCommand(
                command_id="step-001",
                session_id="original",
                expected_revision=0,
            )
        ).tick
        altered_tick = other_store.step(
            ReplayStepCommand(
                command_id="step-001",
                session_id="altered",
                expected_revision=0,
            )
        ).tick

        self.assertEqual(original_tick.snapshot_id, altered_tick.snapshot_id)
        self.assertAlmostEqual(
            original_tick.frames[0].score,
            altered_tick.frames[0].score,
            places=12,
        )
        self.assertAlmostEqual(
            original_tick.frames[0].health_index,
            altered_tick.frames[0].health_index,
            places=12,
        )

    def test_direct_store_rejects_session_path_escape(self) -> None:
        with self.assertRaisesRegex(
            MonitoringReplayConflictError,
            "invalid monitoring session_id",
        ):
            self.store.create_session(
                scenario_id=self.scenario.scenario_id,
                session_id="..",
            )

    def test_p3_accepts_maximum_length_registered_and_session_ids(self) -> None:
        long_scenario = replace(self.scenario, scenario_id="S" * 110)
        long_session_id = "s" * 160
        store = MonitoringReplayStore(
            self.base / "long-id-sessions",
            scenarios={long_scenario.scenario_id: long_scenario},
        )
        store.create_session(
            scenario_id=long_scenario.scenario_id,
            session_id=long_session_id,
            activation_policy_kind="P3",
        )
        store.step(
            ReplayStepCommand(
                command_id="long-id-step-001",
                session_id=long_session_id,
                expected_revision=0,
            )
        )
        completed = store.step(
            ReplayStepCommand(
                command_id="long-id-step-002",
                session_id=long_session_id,
                expected_revision=1,
            )
        )

        self.assertEqual(completed.state.status, "completed")
        self.assertTrue(completed.triggers)
        self.assertTrue(
            all(len(event.dedupe_key) <= 240 for event in completed.triggers)
        )

    def test_p3_budget_and_cooldown_do_not_depend_on_future_suffix_length(self) -> None:
        shorter = replace(self.scenario, expected_monitoring_count=200)
        longer = replace(self.scenario, expected_monitoring_count=201)
        short_policy = _activation_policy_for_kind(
            shorter,
            "P3",
            expected_cadence_seconds=600.0,
        )
        long_policy = _activation_policy_for_kind(
            longer,
            "P3",
            expected_cadence_seconds=600.0,
        )

        self.assertEqual(short_policy, long_policy)
        self.assertEqual(short_policy.max_variable_child_runs, 7)
        self.assertEqual(
            {
                rule.cooldown_source_seconds
                for rule in short_policy.trigger_rules
                if rule.counts_toward_variable_budget
            },
            {51_600.0},
        )

    def test_persisted_policy_tampering_is_rejected_on_resume(self) -> None:
        self.store.create_session(
            scenario_id=self.scenario.scenario_id,
            session_id="tampered-policy",
        )
        policy_path = (
            self.base
            / "sessions"
            / "tampered-policy"
            / "scoring_policy.json"
        )
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
        payload["threshold"] = float(payload["threshold"]) + 1.0
        policy_path.write_text(json.dumps(payload), encoding="utf-8")

        resumed_store = MonitoringReplayStore(
            self.base / "sessions",
            scenarios={self.scenario.scenario_id: self.scenario},
        )
        with self.assertRaisesRegex(
            MonitoringReplayConflictError,
            "scoring policy SHA-256",
        ):
            resumed_store.get_session("tampered-policy")

    def test_initial_checkpoint_tampering_is_rejected_before_first_tick(self) -> None:
        self.store.create_session(
            scenario_id=self.scenario.scenario_id,
            session_id="tampered-seed",
        )
        state_path = self.base / "sessions" / "tampered-seed" / "state.json"
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        modeled = next(
            checkpoint
            for checkpoint in payload["asset_checkpoints"]
            if checkpoint["analysis_status"] == "modeled"
        )
        modeled["raw_health_history"] = [0.0, 0.0]
        state_path.write_text(json.dumps(payload), encoding="utf-8")

        resumed_store = MonitoringReplayStore(
            self.base / "sessions",
            scenarios={self.scenario.scenario_id: self.scenario},
        )
        with self.assertRaisesRegex(
            MonitoringReplayConflictError,
            "frozen causal seed",
        ):
            resumed_store.get_session("tampered-seed")

    def test_rehashed_bootstrap_sidecar_is_rejected_after_commits(self) -> None:
        self.store.create_session(
            scenario_id=self.scenario.scenario_id,
            session_id="tampered-bootstrap-ledger",
            activation_policy_kind="P3",
        )
        for revision in range(2):
            self.store.step(
                ReplayStepCommand(
                    command_id=f"step-{revision + 1:03d}",
                    session_id="tampered-bootstrap-ledger",
                    expected_revision=revision,
                )
            )
        session_dir = self.base / "sessions" / "tampered-bootstrap-ledger"
        sidecar_path = session_dir / "bootstrap_checkpoints.json"
        sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
        contextual = next(
            checkpoint
            for checkpoint in sidecar["checkpoints"]
            if checkpoint["asset_id"] == "bearing_2"
        )
        contextual["analysis_status"] = "unavailable"
        sidecar_path.write_text(json.dumps(sidecar), encoding="utf-8")

        config_path = session_dir / "config.json"
        config = json.loads(config_path.read_text(encoding="utf-8"))
        config["bootstrap_checkpoints_sha256"] = _canonical_sha256(
            sidecar["checkpoints"]
        )
        config_path.write_text(json.dumps(config), encoding="utf-8")
        config_sha256 = _canonical_sha256(config)

        previous_sha256 = "0" * 64
        last_state = None
        for commit_path in sorted((session_dir / "commits").glob("*.json")):
            commit = json.loads(commit_path.read_text(encoding="utf-8"))
            commit["previous_commit_sha256"] = previous_sha256
            commit["state"]["config_sha256"] = config_sha256
            core = {
                key: value
                for key, value in commit.items()
                if key != "commit_sha256"
            }
            commit["commit_sha256"] = _canonical_sha256(core)
            previous_sha256 = commit["commit_sha256"]
            last_state = commit["state"]
            commit_path.write_text(json.dumps(commit), encoding="utf-8")
        (session_dir / "state.json").write_text(
            json.dumps(last_state),
            encoding="utf-8",
        )

        resumed_store = MonitoringReplayStore(
            self.base / "sessions",
            scenarios={self.scenario.scenario_id: self.scenario},
        )
        with self.assertRaisesRegex(
            MonitoringReplayConflictError,
            "frozen causal seed",
        ):
            resumed_store.get_session("tampered-bootstrap-ledger")

    def test_rehashed_commit_cannot_break_checkpoint_transition(self) -> None:
        self.store.create_session(
            scenario_id=self.scenario.scenario_id,
            session_id="tampered-transition",
        )
        self.store.step(
            ReplayStepCommand(
                command_id="step-001",
                session_id="tampered-transition",
                expected_revision=0,
            )
        )
        session_dir = self.base / "sessions" / "tampered-transition"
        commit_path = session_dir / "commits" / "000001.json"
        commit = json.loads(commit_path.read_text(encoding="utf-8"))
        modeled = next(
            checkpoint
            for checkpoint in commit["state"]["asset_checkpoints"]
            if checkpoint["analysis_status"] == "modeled"
        )
        modeled["raw_health_history"] = [0.0, 0.0]
        core = {
            key: value for key, value in commit.items() if key != "commit_sha256"
        }
        commit["commit_sha256"] = _canonical_sha256(core)
        commit_path.write_text(json.dumps(commit), encoding="utf-8")
        (session_dir / "state.json").write_text(
            json.dumps(commit["state"]),
            encoding="utf-8",
        )

        resumed_store = MonitoringReplayStore(
            self.base / "sessions",
            scenarios={self.scenario.scenario_id: self.scenario},
        )
        with self.assertRaisesRegex(
            MonitoringReplayConflictError,
            "previous causal state",
        ):
            resumed_store.get_session("tampered-transition")

    def test_rehashed_commit_cannot_replace_frozen_snapshot_score(self) -> None:
        self.store.create_session(
            scenario_id=self.scenario.scenario_id,
            session_id="tampered-score",
        )
        self.store.step(
            ReplayStepCommand(
                command_id="step-001",
                session_id="tampered-score",
                expected_revision=0,
            )
        )
        session_dir = self.base / "sessions" / "tampered-score"
        commit_path = session_dir / "commits" / "000001.json"
        commit = json.loads(commit_path.read_text(encoding="utf-8"))
        modeled = next(
            frame
            for frame in commit["tick"]["frames"]
            if frame["analysis_status"] == "modeled"
        )
        modeled["score"] = float(modeled["score"]) * 2.0
        modeled["threshold"] = float(modeled["threshold"]) * 2.0
        core = {
            key: value for key, value in commit.items() if key != "commit_sha256"
        }
        commit["commit_sha256"] = _canonical_sha256(core)
        commit_path.write_text(json.dumps(commit), encoding="utf-8")
        (session_dir / "state.json").write_text(
            json.dumps(commit["state"]),
            encoding="utf-8",
        )

        resumed_store = MonitoringReplayStore(
            self.base / "sessions",
            scenarios={self.scenario.scenario_id: self.scenario},
        )
        with self.assertRaisesRegex(
            MonitoringReplayConflictError,
            "frozen snapshot scorer",
        ):
            resumed_store.get_session("tampered-score")

    def test_rehashed_commit_cannot_complete_session_early(self) -> None:
        self.store.create_session(
            scenario_id=self.scenario.scenario_id,
            session_id="tampered-lifecycle",
        )
        self.store.step(
            ReplayStepCommand(
                command_id="step-001",
                session_id="tampered-lifecycle",
                expected_revision=0,
            )
        )
        session_dir = self.base / "sessions" / "tampered-lifecycle"
        commit_path = session_dir / "commits" / "000001.json"
        commit = json.loads(commit_path.read_text(encoding="utf-8"))
        commit["state"]["status"] = "completed"
        core = {
            key: value for key, value in commit.items() if key != "commit_sha256"
        }
        commit["commit_sha256"] = _canonical_sha256(core)
        commit_path.write_text(json.dumps(commit), encoding="utf-8")
        (session_dir / "state.json").write_text(
            json.dumps(commit["state"]),
            encoding="utf-8",
        )

        resumed_store = MonitoringReplayStore(
            self.base / "sessions",
            scenarios={self.scenario.scenario_id: self.scenario},
        )
        with self.assertRaisesRegex(
            MonitoringReplayConflictError,
            "lifecycle state",
        ):
            resumed_store.get_session("tampered-lifecycle")

    @unittest.skipUnless(os.name == "posix", "file locking requires POSIX flock")
    def test_independent_processes_commit_one_step_exactly_once(self) -> None:
        self.store.create_session(
            scenario_id=self.scenario.scenario_id,
            session_id="concurrent-replay",
        )
        context = multiprocessing.get_context("fork")
        ready = context.Queue()
        start = context.Event()
        results = context.Queue()
        processes = [
            context.Process(
                target=_parallel_step_worker,
                args=(
                    self.base / "sessions",
                    self.scenario,
                    index,
                    ready,
                    start,
                    results,
                ),
            )
            for index in range(2)
        ]
        for process in processes:
            process.start()
        self.assertEqual(sorted(ready.get(timeout=10) for _ in range(2)), [0, 1])
        start.set()
        outcomes = sorted(results.get(timeout=20)[1] for _ in range(2))
        for process in processes:
            process.join(timeout=20)
            self.assertEqual(process.exitcode, 0)

        self.assertEqual(outcomes, ["applied", "revision_conflict"])
        resumed = self.store.get_session("concurrent-replay")
        self.assertEqual(resumed.state.revision, 1)
        self.assertEqual(len(resumed.ticks), 1)

    def test_resume_rejects_changed_asset_channel_mapping(self) -> None:
        self.store.create_session(
            scenario_id=self.scenario.scenario_id,
            session_id="frozen-mapping",
        )
        original = self.scenario.asset_specs
        changed = replace(
            self.scenario,
            asset_specs=(
                original[0],
                original[1].model_copy(update={"channel_id": "channel_3"}),
                original[2].model_copy(update={"channel_id": "channel_2"}),
                original[3],
            ),
        )
        resumed_store = MonitoringReplayStore(
            self.base / "sessions",
            scenarios={changed.scenario_id: changed},
        )

        with self.assertRaisesRegex(
            MonitoringReplayConflictError,
            "registered scenario",
        ):
            resumed_store.get_session("frozen-mapping")

    def test_registry_rejects_scorer_bound_to_another_channel(self) -> None:
        specs = self.scenario.asset_specs
        changed = replace(
            self.scenario,
            asset_specs=(
                specs[0].model_copy(
                    update={
                        "analysis_status": "telemetry_only",
                    }
                ),
                specs[1].model_copy(
                    update={
                        "analysis_status": "modeled",
                    }
                ),
                specs[2],
                specs[3],
            ),
        )
        invalid_store = MonitoringReplayStore(
            self.base / "other-sessions",
            scenarios={changed.scenario_id: changed},
        )

        with self.assertRaisesRegex(
            MonitoringReplayUnavailableError,
            "frozen scorer",
        ):
            invalid_store.create_session(
                scenario_id=changed.scenario_id,
                session_id="invalid-mapping",
            )


def _write_safe_scenario(base: Path) -> RegisteredReplayScenario:
    manifest_path = base / "manifest.csv"
    features_path = base / "features.csv"
    model_path = base / "model.joblib"
    start = datetime(2004, 2, 12, 10, 0, 0)
    timestamps = [
        start,
        start + timedelta(minutes=10),
        start + timedelta(minutes=20),
        start + timedelta(minutes=40),
    ]
    partitions = ["baseline_train", "calibration", "monitoring", "monitoring"]
    records: list[CommonManifestRecord] = []
    feature_rows: list[dict[str, object]] = []
    for snapshot_index, (source_time, partition) in enumerate(
        zip(timestamps, partitions, strict=True)
    ):
        snapshot_id = f"safe_{snapshot_index:03d}"
        raw_path = base / f"{snapshot_id}.txt"
        raw = np.column_stack(
            [
                np.linspace(0.1 * channel, 1.0 * channel, 16)
                + snapshot_index * 0.01
                for channel in range(1, 5)
            ]
        )
        pd.DataFrame(raw).to_csv(
            raw_path,
            sep=" ",
            header=False,
            index=False,
        )
        records.append(
            CommonManifestRecord(
                record_id=snapshot_id,
                dataset="nasa_ims_bearing",
                source_path=raw_path.as_posix(),
                source_format="txt",
                data_provenance="official",
                label="unknown",
                condition_id="test_to_failure",
                asset_id="bearing_test_rig",
                run_id="safe_run",
                timestamp_start=source_time,
                timestamp_end=source_time + timedelta(seconds=1),
                sampling_rate_hz=20_000,
                target_sample_rate_hz=20_000,
                channel_names=[f"channel_{index}" for index in range(1, 5)],
                primary_channel="channel_1",
                n_channels=4,
            )
        )
        for window_index in range(2):
            base_value = snapshot_index * 0.4 + window_index * 0.03
            features = {
                column: base_value + feature_index * 0.01
                for feature_index, column in enumerate(SAFE_FEATURE_COLUMNS)
            }
            feature_rows.append(
                {
                    "window_id": f"{snapshot_id}_{window_index:02d}",
                    "file_id": snapshot_id,
                    "run_id": "safe_run",
                    "window_index": window_index,
                    "timestamp_start": (
                        source_time + timedelta(milliseconds=window_index * 50)
                    ).isoformat(),
                    "timestamp_end": (
                        source_time + timedelta(milliseconds=(window_index + 1) * 50)
                    ).isoformat(),
                    "temporal_partition": partition,
                    **features,
                    # Future bait: the service must never load these columns.
                    "relative_life": snapshot_index / 3,
                    "time_to_failure_seconds": float(3 - snapshot_index),
                    "label": "future-secret",
                    "target": 1,
                    "fault_type": "hidden-fault",
                }
            )
    write_common_manifest(manifest_path, records)
    data = pd.DataFrame(feature_rows)
    data.to_csv(features_path, index=False)

    matrix = data.loc[:, SAFE_FEATURE_COLUMNS].to_numpy(dtype=float)
    scaler = StandardScaler().fit(matrix[:4])
    scaled = scaler.transform(matrix[:4])
    model = PCA(n_components=1, random_state=42).fit(scaled)
    bundle = {
        "model": model,
        "scaler": scaler,
        "model_family": "pca_reconstruction_error",
        "feature_columns": list(SAFE_FEATURE_COLUMNS),
        "threshold": 0.1,
    }
    joblib.dump(bundle, model_path)

    specs = tuple(
        ReplayAssetSpec(
            asset_id=f"bearing_{index}",
            channel_id=f"channel_{index}",
            analysis_status="modeled" if index == 1 else "telemetry_only",
        )
        for index in range(1, 5)
    )
    return RegisteredReplayScenario(
        scenario_id="SAFE-RTF-01",
        title="Safe replay fixture",
        dataset_id="nasa_ims_bearing",
        trajectory_id="safe_run",
        source_label="Fixture causal saneado",
        pilot_run_id="safe-run",
        manifest_path=manifest_path,
        manifest_sha256=_sha256(manifest_path),
        features_path=features_path,
        features_sha256=_sha256(features_path),
        model_path=model_path,
        model_sha256=_sha256(model_path),
        expected_snapshot_count=4,
        expected_bootstrap_count=2,
        expected_monitoring_count=2,
        expected_windows_per_snapshot=2,
        asset_specs=specs,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _parallel_step_worker(
    sessions_root: Path,
    scenario: RegisteredReplayScenario,
    index: int,
    ready: multiprocessing.Queue,
    start: multiprocessing.Event,
    results: multiprocessing.Queue,
) -> None:
    store = MonitoringReplayStore(
        sessions_root,
        scenarios={scenario.scenario_id: scenario},
    )
    ready.put(index)
    if not start.wait(timeout=10):
        raise RuntimeError("parallel replay test did not receive start signal")
    response = store.step(
        ReplayStepCommand(
            command_id=f"parallel-{index}",
            session_id="concurrent-replay",
            expected_revision=0,
        )
    )
    results.put((index, response.receipt.outcome))


if __name__ == "__main__":
    unittest.main()
