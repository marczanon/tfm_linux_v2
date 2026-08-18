from __future__ import annotations

import os
import tempfile
import unittest
from collections import Counter
from pathlib import Path

import pandas as pd

from codigo.app.services.monitoring_replay import (
    DEFAULT_PILOT_RUN_ID,
    DEFAULT_SCENARIO_ID,
    MonitoringReplayStore,
    _canonical_sha256,
    _score_snapshot,
)
from codigo.app.schemas.monitoring_replay import ReplayStepCommand
from codigo.app.services.temporal_health_policy import (
    annotate_temporal_gaps,
    causal_temporal_health_points,
)


@unittest.skipUnless(
    os.getenv("TFM_RUN_NASA_REPLAY_INTEGRATION") == "1",
    "set TFM_RUN_NASA_REPLAY_INTEGRATION=1 for local ignored NASA artifacts",
)
class NASAMonitoringReplayIntegrationTests(unittest.TestCase):
    def test_frozen_replay_matches_retrospective_oracle_on_safe_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = MonitoringReplayStore(Path(temporary) / "sessions")
            runtime = store._runtime(DEFAULT_SCENARIO_ID)
        snapshots = [
            *runtime.bootstrap_snapshots,
            *(
                _score_snapshot(runtime, snapshot_id)
                for snapshot_id in runtime.monitoring_snapshot_ids
            ),
        ]
        annotated = annotate_temporal_gaps([item.health_row() for item in snapshots])
        health = causal_temporal_health_points(
            annotated,
            score_min=None,
            score_max=None,
        )
        oracle_path = Path(
            "codigo/reports/nasa_ims_bearing"
        ) / DEFAULT_PILOT_RUN_ID / "evaluation" / "snapshot_trajectory.csv"
        oracle = pd.read_csv(oracle_path)

        self.assertEqual(len(snapshots), len(oracle))
        max_score_delta = 0.0
        max_health_delta = 0.0
        for index, (snapshot, annotated_row, health_point) in enumerate(
            zip(snapshots, annotated, health, strict=True)
        ):
            expected = oracle.iloc[index]
            self.assertEqual(snapshot.snapshot_id, expected["snapshot_id"])
            self.assertEqual(
                snapshot.predicted_anomaly,
                int(expected["predicted_anomaly"]),
            )
            self.assertEqual(
                int(annotated_row["temporal_segment_id"]),
                int(expected["temporal_segment_id"]),
            )
            self.assertEqual(
                bool(annotated_row["gap_detected"]),
                bool(expected["gap_detected"]),
            )
            self.assertEqual(health_point["health_state"], expected["health_state"])
            max_score_delta = max(
                max_score_delta,
                abs(snapshot.score - float(expected["anomaly_score"])),
            )
            max_health_delta = max(
                max_health_delta,
                abs(
                    float(health_point["health_index_smoothed"])
                    - float(expected["health_index_smoothed"])
                ),
            )

        self.assertLess(max_score_delta, 1e-10)
        self.assertLess(max_health_delta, 1e-10)

        with tempfile.TemporaryDirectory() as temporary:
            store = MonitoringReplayStore(Path(temporary) / "sessions")
            created = store.create_session(
                scenario_id=DEFAULT_SCENARIO_ID,
                session_id="full-incremental-parity",
                activation_policy_kind="P3",
            )
            self.assertEqual(created.state.revision, 0)
            trigger_events = []
            monitoring_oracle = oracle.iloc[len(runtime.bootstrap_snapshots) :]
            self.assertEqual(
                len(monitoring_oracle),
                len(runtime.monitoring_snapshot_ids),
            )
            for cursor, (_, expected) in enumerate(monitoring_oracle.iterrows()):
                response = store.step(
                    ReplayStepCommand(
                        command_id=f"nasa-step-{cursor:06d}",
                        session_id="full-incremental-parity",
                        expected_revision=cursor,
                    )
                )
                trigger_events.extend(response.triggers)
                tick = response.tick
                self.assertIsNotNone(tick)
                frame = next(
                    item
                    for item in tick.frames
                    if item.analysis_status == "modeled"
                )
                self.assertEqual(tick.cursor, cursor)
                self.assertEqual(tick.snapshot_id, expected["snapshot_id"])
                self.assertEqual(frame.health_state, expected["health_state"])
                self.assertEqual(
                    frame.segment_id,
                    int(expected["temporal_segment_id"]),
                )
                self.assertAlmostEqual(
                    frame.score,
                    float(expected["anomaly_score"]),
                    places=10,
                )
                self.assertAlmostEqual(
                    frame.health_index,
                    float(expected["health_index_smoothed"]),
                    places=10,
                )
                self.assertEqual(len(tick.frames), 4)
                self.assertTrue(
                    all(
                        item.score is None
                        for item in tick.frames
                        if item.analysis_status == "telemetry_only"
                    )
                )

            final = store.get_session("full-incremental-parity")
            self.assertEqual(
                Counter(event.trigger_type for event in trigger_events),
                Counter(
                    {
                        "state_transition": 11,
                        "persistent_alert": 2,
                        "session_close": 1,
                    }
                ),
            )
            self.assertEqual(
                Counter(event.lifecycle_status for event in trigger_events),
                Counter({"emitted": 4, "suppressed": 10}),
            )
            self.assertEqual(
                Counter(
                    event.suppression_reason
                    for event in trigger_events
                    if event.suppression_reason is not None
                ),
                Counter({"cooldown": 9, "episode_already_covered": 1}),
            )
            self.assertEqual(
                final.state.activation_checkpoint.variable_run_slots_reserved,
                3,
            )
            self.assertEqual(
                final.state.activation_checkpoint.next_event_sequence,
                15,
            )
            semantic_projection = [
                {
                    "sequence": event.sequence,
                    "trigger_type": event.trigger_type,
                    "lifecycle_status": event.lifecycle_status,
                    "reason_code": event.reason_code,
                    "condition_start_cursor": event.condition_start_cursor,
                    "cutoff_cursor": event.cutoff_cursor,
                    "suppression_reason": event.suppression_reason,
                    "budget_reservation_index": (
                        event.budget_reservation_index
                    ),
                    "coalesced_into_trigger_id": (
                        event.coalesced_into_trigger_id
                    ),
                }
                for event in trigger_events
            ]
            self.assertEqual(
                _canonical_sha256(semantic_projection),
                "84fe3c6b1a8054e23abc795d31c8aeca8f0b3e13979ce292c48ae6e5f8d2b0c1",
            )


if __name__ == "__main__":
    unittest.main()
