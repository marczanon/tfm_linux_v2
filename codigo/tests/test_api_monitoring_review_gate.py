from __future__ import annotations

import asyncio
import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

from codigo.app.api import create_app
from codigo.app.services.monitoring_review_reliability import (
    build_monitoring_review_reliability_result,
    default_monitoring_review_reliability_plan,
    preregister_monitoring_review_reliability_plan,
    publish_monitoring_review_reliability,
    write_monitoring_review_reliability_artifacts,
)
from codigo.tests.test_monitoring_review_reliability import (
    _complete_observations,
)


class APIMonitoringReviewGateTests(unittest.TestCase):
    def test_current_gate_projects_roles_matrix_coverage_and_run_links(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            gate_root = base / "gate"
            plan = default_monitoring_review_reliability_plan(
                plan_id="api-monitoring-gate-fixture"
            )
            preregistration = preregister_monitoring_review_reliability_plan(
                plan,
                output_root=gate_root,
            )
            started_at = max(datetime.now(UTC), preregistration.registered_at)
            result = build_monitoring_review_reliability_result(
                plan,
                _complete_observations(plan),
                preregistration=preregistration,
                llm_config=plan.llm_config,
                started_at=started_at,
                completed_at=started_at + timedelta(seconds=1),
            )
            artifacts = write_monitoring_review_reliability_artifacts(
                result,
                output_root=gate_root,
            )
            publish_monitoring_review_reliability(
                result,
                artifacts,
                output_root=gate_root,
            )
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base],
                monitoring_review_reliability_output_dir=gate_root,
                monitoring_review_use_llm=False,
            )

            response = _get(app, "/monitoring/review-gates/current")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["gate_id"], plan.plan_id)
        self.assertEqual(payload["verdict"], "passed")
        self.assertEqual(payload["model"], "qwen3.5:4b")
        self.assertEqual(payload["memory_mode"], "off")
        self.assertEqual(payload["outcomes"]["expected_count"], 84)
        self.assertEqual(payload["outcomes"]["first_pass_count"], 84)
        self.assertEqual(len(payload["roles"]), 7)
        self.assertEqual(len(payload["cases"]), 12)
        self.assertEqual(
            [item["kind"] for item in payload["coverage"]],
            [
                "hypothesis_structure",
                "causal_grounding",
                "trigger_decision_result_binding",
            ],
        )
        first_case = payload["cases"][0]
        self.assertEqual(first_case["session_id"], "session-001")
        self.assertEqual(first_case["bridge_lifecycle_status"], "resolved")
        self.assertEqual(len(first_case["role_results"]), 7)

    def test_absent_publication_is_404_but_corrupt_publication_is_409(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary)
            gate_root = base / "gate"
            app = create_app(
                runs_dir=base / "runs",
                allowed_raw_roots=[base],
                monitoring_review_reliability_output_dir=gate_root,
                monitoring_review_use_llm=False,
            )
            absent = _get(app, "/monitoring/review-gates/current")

            gate_root.mkdir(parents=True)
            (gate_root / "current.json").write_text(
                json.dumps({"schema_version": "corrupt"}),
                encoding="utf-8",
            )
            corrupt = _get(app, "/monitoring/review-gates/current")

        self.assertEqual(absent.status_code, 404)
        self.assertEqual(corrupt.status_code, 409)
        self.assertIn("integrity", corrupt.json()["detail"])


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
