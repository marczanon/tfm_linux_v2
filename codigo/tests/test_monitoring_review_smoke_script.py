from __future__ import annotations

from copy import deepcopy
import unittest

from codigo.scripts.run_nasa_monitoring_trigger_review_smoke import (
    run_full_session_review_cycle,
)


class _Response:
    def __init__(self, status_code: int, payload=None) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return deepcopy(self._payload)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FullCycleClient:
    def __init__(self) -> None:
        self.session = None
        self.posts: list[str] = []
        self.gets: list[str] = []
        self.dispatches: list[str] = []

    async def get(self, path: str):
        self.gets.append(path)
        if path == "/monitoring/sessions/full-cycle-test":
            if self.session is None:
                return _Response(404, {"detail": "not found"})
            return _Response(200, self.session)
        if path.endswith("/child-runs"):
            active = next(
                (
                    item
                    for item in self.session["child_runs"]
                    if item["lifecycle_status"] in {"dispatched", "running"}
                ),
                None,
            )
            if active is not None:
                active["lifecycle_status"] = (
                    "resolved" if active["child_run_id"] == "child-1" else "interrupted"
                )
                if active["lifecycle_status"] == "interrupted":
                    active["error"] = "worker stopped"
            return _Response(
                200,
                {
                    "session_id": "full-cycle-test",
                    "child_revision": self.session["child_revision"] + 1,
                    "child_runs": self.session["child_runs"],
                },
            )
        if path == "/run-jobs/child-1":
            return _Response(
                200,
                {
                    "status": "completed",
                    "events": [
                        {
                            "kind": "supervisor_decision",
                            "payload": {
                                "decision": {
                                    "generation_trace": {"origin": "llm"}
                                }
                            },
                        }
                    ],
                },
            )
        if path == "/run-jobs/child-close":
            return _Response(404, {"detail": "not found"})
        raise AssertionError(f"unexpected GET {path}")

    async def post(self, path: str, json: dict):
        self.posts.append(path)
        if path == "/monitoring/sessions":
            self.session = {
                "config": {"activation_policy_kind": "P3"},
                "state": {"revision": 0, "status": "ready"},
                "total_monitoring_ticks": 3,
                "triggers": [],
                "child_revision": 0,
                "child_runs": [],
                "active_child_run_id": None,
            }
            return _Response(200, self.session)
        if path.endswith("/step"):
            revision = json["expected_revision"]
            self.session["state"] = {
                "revision": revision + 1,
                "status": "completed" if revision == 2 else "paused",
            }
            triggers = []
            if revision == 0:
                triggers = [_trigger("trigger-1", 1, "state_transition", 0)]
            elif revision == 2:
                triggers = [_trigger("trigger-close", 2, "session_close", 2)]
            self.session["triggers"].extend(triggers)
            return _Response(
                200,
                {"state": self.session["state"], "triggers": triggers},
            )
        if path.endswith("/dispatch"):
            trigger_id = path.split("/triggers/", 1)[1].split("/", 1)[0]
            self.dispatches.append(trigger_id)
            child_run_id = "child-1" if trigger_id == "trigger-1" else "child-close"
            self.session["child_revision"] += 1
            attempt = {
                "trigger_id": trigger_id,
                "child_run_id": child_run_id,
                "lifecycle_status": "dispatched",
                "error": None,
            }
            self.session["child_runs"].append(attempt)
            self.session["active_child_run_id"] = child_run_id
            return _Response(
                202,
                {
                    "receipt": {"child_run_id": child_run_id},
                    "session": self.session,
                },
            )
        raise AssertionError(f"unexpected POST {path}")


def _trigger(
    trigger_id: str,
    sequence: int,
    trigger_type: str,
    cutoff_cursor: int,
) -> dict:
    return {
        "event_id": f"{trigger_id}:event:1",
        "trigger_id": trigger_id,
        "sequence": sequence,
        "trigger_type": trigger_type,
        "lifecycle_status": "emitted",
        "cutoff_cursor": cutoff_cursor,
    }


class FullMonitoringReviewCycleTests(unittest.IsolatedAsyncioTestCase):
    async def test_dispatches_all_emitted_including_close_without_retry(self) -> None:
        client = _FullCycleClient()
        progress: list[dict[str, object]] = []

        result = await run_full_session_review_cycle(
            session_id="full-cycle-test",
            timeout_seconds=1.0,
            use_llm=True,
            client=client,
            progress_callback=progress.append,
            poll_interval_seconds=0.0,
        )

        self.assertEqual(client.dispatches, ["trigger-1", "trigger-close"])
        self.assertEqual(
            client.posts.count("/monitoring/sessions/full-cycle-test/step"),
            3,
        )
        self.assertEqual(
            client.gets.count("/monitoring/sessions/full-cycle-test"),
            1,
        )
        self.assertEqual(result["session_status"], "completed")
        self.assertEqual(result["review_count"], 2)
        self.assertEqual(
            [item["trigger_type"] for item in result["reviews"]],
            ["state_transition", "session_close"],
        )
        self.assertEqual(
            [item["child_lifecycle"] for item in result["reviews"]],
            ["resolved", "interrupted"],
        )
        self.assertEqual(result["terminal_counts"], {"interrupted": 1, "resolved": 1})
        self.assertEqual(
            [item["kind"] for item in progress],
            [
                "review_dispatching",
                "review_terminal",
                "review_dispatching",
                "review_terminal",
            ],
        )
        self.assertTrue(
            all(item.get("child_run_id") for item in progress)
        )


if __name__ == "__main__":
    unittest.main()
