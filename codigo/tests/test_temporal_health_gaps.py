import unittest

from codigo.app.services.temporal_health_policy import (
    annotate_temporal_gaps,
    causal_differences,
    causal_moving_average,
    temporal_alert_summary,
    temporal_health_state,
)


class TemporalHealthGapTests(unittest.TestCase):
    def test_gap_annotation_and_persistence_do_not_bridge_missing_time(self):
        rows = [
            {
                "run_id": "set_2",
                "timestamp_start": "2004-02-12T10:32:39",
            },
            {
                "run_id": "set_2",
                "timestamp_start": "2004-02-12T10:42:39",
            },
            {
                "run_id": "set_2",
                "timestamp_start": "2004-02-12T11:12:39",
            },
        ]

        annotated = annotate_temporal_gaps(rows)
        segment_ids = [int(row["temporal_segment_id"]) for row in annotated]
        summary = temporal_alert_summary(
            ["warning", "warning", "warning"],
            segment_ids=segment_ids,
        )

        self.assertEqual(
            [row["interval_seconds"] for row in annotated],
            [None, 600.0, 1800.0],
        )
        self.assertEqual(
            [row["gap_detected"] for row in annotated],
            [False, False, True],
        )
        self.assertEqual(segment_ids, [0, 0, 1])
        self.assertEqual(summary["longest_alert_streak"], 2)
        self.assertIsNone(summary["first_persistent_index"])

    def test_causal_smoothing_and_trend_restart_after_gap(self):
        values = [100.0, 80.0, 20.0]
        segment_ids = [0, 0, 1]

        smoothed = causal_moving_average(
            values,
            3,
            segment_ids=segment_ids,
        )
        trends = causal_differences(
            smoothed,
            3,
            segment_ids=segment_ids,
        )

        self.assertEqual(smoothed, [100.0, 90.0, 20.0])
        self.assertEqual(trends, [None, -10.0, None])

    def test_health_state_never_uses_retrospective_relative_life(self):
        state = temporal_health_state(
            {"relative_life": 1.0},
            risk_index=70.0,
            predicted=1,
        )

        self.assertEqual(state, "warning")


if __name__ == "__main__":
    unittest.main()
