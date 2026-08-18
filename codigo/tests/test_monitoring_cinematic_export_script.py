from __future__ import annotations

import contextlib
import io
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from codigo.app.services import monitoring_cinematic_export as cinematic
from codigo.app.services.monitoring_evidence_campaign import (
    default_monitoring_evidence_campaign_plan,
)
from codigo.scripts import export_monitoring_campaign_cinematic as cli


class MonitoringCinematicExportScriptTests(unittest.TestCase):
    def test_browser_capture_script_is_syntax_valid_and_read_only_by_contract(self):
        script = Path(
            "codigo/frontend/scripts/capture-monitoring-cinematic.mjs"
        )
        source = script.read_text(encoding="utf-8")
        checked = subprocess.run(
            ["node", "--check", str(script)],
            capture_output=True,
            check=False,
            text=True,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("__TFM_MONITORING_CINEMATIC_TIMELINE__", source)
        self.assertIn('name: "Seleccionar acto de la cinemática"', source)
        self.assertIn("mutationAttempts", source)
        self.assertIn('"preregistration.json"', source)
        self.assertIn("validateRendererSources", source)
        self.assertIn("served_renderer_binding", source)
        self.assertIn("sourceManifest.registration_sha256", source)
        self.assertIn("validateSessionAgainstTimeline", source)
        self.assertIn("primaryEvents.length !== 14", source)
        self.assertIn("session.ticks.length !== 689", source)
        for test_id in (
            "monitoring-cinematic-stage",
            "monitoring-bearing-rig",
            "monitoring-health-trend",
            "monitoring-score-ratio-trend",
            "monitoring-agent-act",
            "monitoring-evidence-heatmap",
            "monitoring-act-rail",
        ):
            self.assertIn(test_id, source)

    def test_plan_only_preregisters_without_replay_browser_or_ollama(self):
        campaign_plan = default_monitoring_evidence_campaign_plan()
        with tempfile.TemporaryDirectory() as tmp:
            args = cli._parse_args(
                [
                    "--plan-only",
                    "--capture-id",
                    "cinematic-cli-plan-test",
                    "--campaign-output-root",
                    str(Path(tmp) / "campaign"),
                    "--output-root",
                    tmp,
                ]
            )
            output = io.StringIO()
            with (
                mock.patch.object(
                    cli,
                    "export_monitoring_cinematic",
                    side_effect=AssertionError("plan-only attempted export"),
                ),
                mock.patch.object(
                    cli,
                    "load_published_monitoring_evidence_campaign",
                    return_value=SimpleNamespace(plan=campaign_plan),
                ),
                contextlib.redirect_stdout(output),
            ):
                exit_code = cli._run(args)

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["mode"], "plan_only")
            self.assertFalse(payload["will_execute_replay"])
            self.assertFalse(payload["will_call_ollama"])
            self.assertFalse(payload["will_capture_browser"])
            self.assertEqual(payload["expected_beats"], 726)
            self.assertEqual(payload["expected_video_frames"], 1121)
            self.assertEqual(payload["viewport"], [1920, 1080])
            self.assertTrue(
                (Path(tmp) / "cinematic-cli-plan-test" / "capture_plan.json").is_file()
            )
            self.assertTrue(
                (Path(tmp) / "cinematic-cli-plan-test" / "preregistration.json").is_file()
            )

    def test_export_rejects_planned_campaign_before_loading_session(self):
        campaign_plan = default_monitoring_evidence_campaign_plan()
        planned = SimpleNamespace(
            plan=campaign_plan,
            state=SimpleNamespace(status="planned"),
            result=None,
            publication=SimpleNamespace(result_ref=None),
        )
        with tempfile.TemporaryDirectory() as tmp:
            args = cli._parse_args(
                [
                    "--export",
                    "--capture-id",
                    "cinematic-cli-terminal-test",
                    "--campaign-output-root",
                    str(Path(tmp) / "campaign"),
                    "--output-root",
                    tmp,
                    "--sessions-dir",
                    str(Path(tmp) / "must-not-be-read"),
                    "--runs-dir",
                    str(Path(tmp) / "must-not-be-read-runs"),
                ]
            )
            with (
                mock.patch.object(
                    cli,
                    "load_published_monitoring_evidence_campaign",
                    return_value=planned,
                ),
                mock.patch.object(
                    cinematic,
                    "load_published_monitoring_evidence_campaign",
                    return_value=planned,
                ),
            ):
                with self.assertRaisesRegex(ValueError, "published campaign result"):
                    cli._run(args)


if __name__ == "__main__":
    unittest.main()
