"""Prerregistra o exporta la cinematica 2D de la campana NASA ya cerrada."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from codigo.app.services.monitoring_cinematic_export import (
    DEFAULT_MONITORING_CINEMATIC_OUTPUT_DIR,
    default_monitoring_cinematic_capture_plan,
    export_monitoring_cinematic,
    preregister_monitoring_cinematic_capture,
)
from codigo.app.services.monitoring_evidence_campaign import (
    DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_ID,
    DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_OUTPUT_DIR,
    load_published_monitoring_evidence_campaign,
)
from codigo.app.services.monitoring_replay import DEFAULT_MONITORING_SESSIONS_DIR
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    return _run(args)


def _run(args: argparse.Namespace) -> int:
    published = load_published_monitoring_evidence_campaign(
        output_root=args.campaign_output_root,
        campaign_id=args.campaign_id,
    )
    plan = default_monitoring_cinematic_capture_plan(
        published.plan,
        capture_id=args.capture_id,
    )
    registration = preregister_monitoring_cinematic_capture(
        plan,
        output_root=args.output_root,
    )
    if not args.export:
        print(
            json.dumps(
                {
                    "mode": "plan_only",
                    "will_execute_replay": False,
                    "will_call_ollama": False,
                    "will_capture_browser": False,
                    "capture_id": plan.capture_id,
                    "campaign_id": plan.campaign_id,
                    "campaign_plan_sha256": plan.campaign_plan_sha256,
                    "capture_plan_sha256": plan.capture_plan_sha256,
                    "registration_sha256": registration.registration_sha256,
                    "expected_beats": plan.expected_beat_count,
                    "expected_video_frames": plan.expected_video_frame_count,
                    "viewport": [plan.viewport_width, plan.viewport_height],
                    "fps": plan.fps,
                },
                ensure_ascii=True,
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    artifacts = export_monitoring_cinematic(
        plan,
        registration,
        campaign_output_root=args.campaign_output_root,
        output_root=args.output_root,
        sessions_root=args.sessions_dir,
        runs_root=args.runs_dir,
    )
    print(
        json.dumps(
            {
                "mode": "export",
                "will_execute_replay": False,
                "will_call_ollama": False,
                "will_capture_browser": False,
                "capture_id": plan.capture_id,
                "campaign_id": plan.campaign_id,
                "beat_count": artifacts.manifest.beat_count,
                "video_frame_count": artifacts.manifest.video_frame_count,
                "timeline_sha256": artifacts.manifest.timeline_sha256,
                "manifest_sha256": artifacts.manifest.manifest_sha256,
                "artifacts": artifacts.model_dump(
                    mode="json",
                    exclude={"manifest"},
                ),
            },
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def _parse_args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--plan-only", action="store_true")
    mode.add_argument("--export", action="store_true")
    parser.add_argument(
        "--campaign-id",
        default=DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_ID,
    )
    parser.add_argument("--capture-id", default=None)
    parser.add_argument(
        "--campaign-output-root",
        type=Path,
        default=DEFAULT_MONITORING_EVIDENCE_CAMPAIGN_OUTPUT_DIR,
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_MONITORING_CINEMATIC_OUTPUT_DIR,
    )
    parser.add_argument(
        "--sessions-dir",
        type=Path,
        default=DEFAULT_MONITORING_SESSIONS_DIR,
    )
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    return parser.parse_args(argv)


if __name__ == "__main__":
    raise SystemExit(main())
