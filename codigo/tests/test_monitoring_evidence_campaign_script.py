from __future__ import annotations

import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from codigo.scripts import run_monitoring_evidence_campaign as cli


class MonitoringEvidenceCampaignScriptTests(unittest.TestCase):
    def test_plan_only_publishes_prepared_campaign_without_ollama_or_app(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = cli._parse_args(
                [
                    "--plan-only",
                    "--campaign-id",
                    "campaign-cli-plan-only",
                    "--speed-multiplier",
                    "120",
                    "--heartbeat-interval-seconds",
                    "2",
                    "--output-root",
                    tmp,
                ]
            )
            output = io.StringIO()
            with (
                mock.patch.object(
                    cli,
                    "create_app",
                    side_effect=AssertionError("plan-only created FastAPI"),
                ),
                mock.patch.object(
                    cli,
                    "ObservedOllamaJSONClient",
                    side_effect=AssertionError("plan-only created Ollama client"),
                ),
                mock.patch.object(
                    cli,
                    "_verify_ollama_model_digest",
                    side_effect=AssertionError("plan-only queried Ollama"),
                ),
                contextlib.redirect_stdout(output),
            ):
                exit_code = asyncio.run(cli._main(args))

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["mode"], "plan_only")
            self.assertFalse(payload["will_execute_ollama"])
            self.assertEqual(payload["pre_roll_ticks"], 353)
            self.assertEqual(payload["agentic_window_ticks"], 336)
            self.assertEqual(payload["expected_child_runs"], 4)
            self.assertEqual(payload["expected_role_decisions"], 28)
            self.assertEqual(payload["step_interval_seconds"], 5.0)

            repeated_output = io.StringIO()
            with contextlib.redirect_stdout(repeated_output):
                repeated_exit = asyncio.run(cli._main(args))
            repeated = json.loads(repeated_output.getvalue())
            self.assertEqual(repeated_exit, 0)
            self.assertEqual(
                repeated["publication_sha256"],
                payload["publication_sha256"],
            )
            self.assertEqual(
                len(list((Path(tmp) / "campaign-cli-plan-only" / "states").glob("*.json"))),
                1,
            )

    def test_execute_checks_frozen_sources_and_model_before_app_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = cli._parse_args(
                [
                    "--execute",
                    "--campaign-id",
                    "campaign-cli-preflight-stop",
                    "--output-root",
                    tmp,
                    "--sessions-dir",
                    str(Path(tmp) / "sessions"),
                    "--runs-dir",
                    str(Path(tmp) / "runs"),
                ]
            )
            with (
                mock.patch.object(
                    cli,
                    "_verify_ollama_model_digest",
                    side_effect=RuntimeError("digest sentinel"),
                ) as verify,
                mock.patch.object(
                    cli,
                    "create_app",
                    side_effect=AssertionError("app created before digest check"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "digest sentinel"):
                    asyncio.run(cli._main(args))

            verify.assert_awaited_once()
            published = cli.load_published_monitoring_evidence_campaign(
                output_root=tmp,
                campaign_id="campaign-cli-preflight-stop",
            )
            self.assertEqual(published.state.status, "failed")

    def test_execute_rejects_preexisting_session_before_ollama(self):
        with tempfile.TemporaryDirectory() as tmp:
            session_root = Path(tmp) / "sessions"
            session_id = "campaign-cli-existing-session-session"
            (session_root / session_id).mkdir(parents=True)
            args = cli._parse_args(
                [
                    "--execute",
                    "--campaign-id",
                    "campaign-cli-existing-session",
                    "--output-root",
                    tmp,
                    "--sessions-dir",
                    str(session_root),
                    "--runs-dir",
                    str(Path(tmp) / "runs"),
                ]
            )
            with mock.patch.object(
                cli,
                "_verify_ollama_model_digest",
                side_effect=AssertionError("Ollama queried for a reused session"),
            ):
                with self.assertRaisesRegex(ValueError, "session already exists"):
                    asyncio.run(cli._main(args))

            published = cli.load_published_monitoring_evidence_campaign(
                output_root=tmp,
                campaign_id="campaign-cli-existing-session",
            )
            self.assertEqual(published.state.status, "failed")

    def test_execution_lock_is_single_flight(self):
        with tempfile.TemporaryDirectory() as tmp:
            with cli._campaign_execution_lock(tmp, "campaign-lock-test"):
                with self.assertRaisesRegex(RuntimeError, "already active"):
                    with cli._campaign_execution_lock(tmp, "campaign-lock-test"):
                        self.fail("second campaign lock unexpectedly acquired")


if __name__ == "__main__":
    unittest.main()
