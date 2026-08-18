from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from codigo.app.api import create_app
from codigo.app.services.monitoring_evidence_campaign import (
    default_monitoring_evidence_campaign_plan,
    preregister_monitoring_evidence_campaign_plan,
    publish_monitoring_evidence_campaign,
    start_monitoring_evidence_campaign_state,
    update_monitoring_evidence_campaign_state,
)


class APIMonitoringEvidenceCampaignTests(unittest.TestCase):
    def test_current_campaign_projects_verified_progress_without_write_controls(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            output_root = base / "campaigns"
            plan = default_monitoring_evidence_campaign_plan(
                campaign_id="api-monitoring-campaign-fixture",
            )
            preregistration = preregister_monitoring_evidence_campaign_plan(
                plan,
                output_root=output_root,
            )
            started_at = datetime.now(UTC)
            state = start_monitoring_evidence_campaign_state(
                plan,
                started_at=started_at,
            )
            state = update_monitoring_evidence_campaign_state(
                plan,
                state,
                {
                    "kind": "review_dispatching",
                    "revision": 354,
                    "cutoff_cursor": 353,
                    "trigger_id": "trigger-353",
                    "child_run_id": "child-353",
                },
                recorded_at=started_at + timedelta(seconds=1),
            )
            state = update_monitoring_evidence_campaign_state(
                plan,
                state,
                {
                    "kind": "review_terminal",
                    "revision": 354,
                    "cutoff_cursor": 353,
                    "trigger_id": "trigger-353",
                    "child_run_id": "child-353",
                    "child_lifecycle": "resolved",
                    "decision_count": 7,
                    "llm_origin_count": 7,
                    "fallback_count": 0,
                    "proposal_status": "advisory_not_applied",
                    "proposal_application_status": "not_applied",
                },
                recorded_at=started_at + timedelta(seconds=2),
            )
            publication = publish_monitoring_evidence_campaign(
                plan,
                state,
                preregistration=preregistration,
                output_root=output_root,
            )
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base],
                monitoring_evidence_campaign_output_dir=output_root,
                monitoring_review_use_llm=False,
            )

            response = _get(app, "/monitoring/evidence-campaigns/current")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["publication_sha256"], publication.publication_sha256)
        self.assertEqual(
            payload["published_at"],
            publication.published_at.isoformat().replace("+00:00", "Z"),
        )
        self.assertEqual(
            payload["registration_sha256"],
            preregistration.registration_sha256,
        )
        self.assertEqual(
            payload["registered_at"],
            preregistration.registered_at.isoformat().replace("+00:00", "Z"),
        )
        self.assertEqual(payload["plan_sha256"], plan.plan_sha256)
        self.assertEqual(payload["state_sha256"], state.state_sha256)
        self.assertIsNone(payload["result_sha256"])
        self.assertEqual(payload["campaign_id"], plan.campaign_id)
        self.assertEqual(payload["session_id"], plan.session_id)
        self.assertEqual(payload["status"], "running")
        self.assertEqual(payload["phase"], "agentic_window")
        self.assertEqual(payload["agentic_window_source_duration_seconds"], 201000)
        self.assertEqual(payload["observed_trigger_count"], 1)
        self.assertEqual(payload["resolved_child_run_count"], 1)
        self.assertEqual(payload["observed_decision_count"], 7)
        self.assertEqual(payload["physical_attempt_count"], 0)
        self.assertEqual(payload["fallback_count"], 0)
        self.assertEqual(payload["policy_proposal_count"], 1)
        self.assertEqual(len(payload["reviews"]), 4)
        self.assertEqual(payload["reviews"][0]["lifecycle"], "resolved")
        self.assertEqual(payload["memory_mode"], "off")
        self.assertEqual(payload["policy_application_status"], "not_applied")

    def test_absent_campaign_is_404_but_corrupt_publication_is_409(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            output_root = base / "campaigns"
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base],
                monitoring_evidence_campaign_output_dir=output_root,
                monitoring_review_use_llm=False,
            )
            absent = _get(app, "/monitoring/evidence-campaigns/current")

            output_root.mkdir(parents=True)
            (output_root / "current.json").write_text(
                json.dumps({"schema_version": "corrupt"}),
                encoding="utf-8",
            )
            corrupt = _get(app, "/monitoring/evidence-campaigns/current")

        self.assertEqual(absent.status_code, 404)
        self.assertEqual(corrupt.status_code, 409)
        self.assertIn("integrity", corrupt.json()["detail"])

    def test_tampered_preregistration_is_409(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            output_root = base / "campaigns"
            plan = default_monitoring_evidence_campaign_plan(
                campaign_id="api-monitoring-campaign-prereg-tamper",
            )
            preregistration = preregister_monitoring_evidence_campaign_plan(
                plan,
                output_root=output_root,
            )
            state = start_monitoring_evidence_campaign_state(plan)
            publish_monitoring_evidence_campaign(
                plan,
                state,
                preregistration=preregistration,
                output_root=output_root,
            )
            registration_path = Path(preregistration.plan_ref).with_name(
                "preregistration.json"
            )
            payload = json.loads(registration_path.read_text(encoding="utf-8"))
            payload["registered_at"] = "2026-08-18T00:00:00Z"
            registration_path.write_text(json.dumps(payload), encoding="utf-8")
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base],
                monitoring_evidence_campaign_output_dir=output_root,
                monitoring_review_use_llm=False,
            )

            response = _get(app, "/monitoring/evidence-campaigns/current")

        self.assertEqual(response.status_code, 409)
        self.assertIn("integrity", response.json()["detail"])


def _get(app, path: str) -> httpx.Response:
    async def request() -> httpx.Response:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://testserver",
        ) as client:
            return await client.get(path)

    return asyncio.run(request())


if __name__ == "__main__":
    unittest.main()
