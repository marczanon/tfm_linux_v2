import asyncio
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from codigo.app.schemas.monitoring_replay import MONITORING_REVIEW_ROLES
from codigo.app.services.agent_reliability import AgentReliabilityAttempt
from codigo.scripts import run_monitoring_review_reliability as cli
from codigo.tests.test_monitoring_review_reliability import _sealed_review_pack


class MonitoringReviewReliabilityScriptTests(unittest.TestCase):
    def test_plan_only_preregisters_without_creating_app_or_ollama_client(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = cli._parse_args(
                [
                    "--plan-only",
                    "--plan-id",
                    "monitoring-review-cli-plan-only",
                    "--output-root",
                    tmp,
                ]
            )
            output = io.StringIO()
            with (
                mock.patch.object(
                    cli,
                    "create_app",
                    side_effect=AssertionError("plan-only must not create FastAPI"),
                ),
                mock.patch.object(
                    cli,
                    "ObservedOllamaJSONClient",
                    side_effect=AssertionError("plan-only must not create Ollama"),
                ),
                mock.patch.object(
                    cli,
                    "_verify_ollama_model_digest",
                    side_effect=AssertionError("plan-only must not query Ollama"),
                ),
                contextlib.redirect_stdout(output),
            ):
                exit_code = asyncio.run(cli._main(args))

            payload = json.loads(output.getvalue())
            self.assertEqual(exit_code, 0)
            self.assertEqual(payload["mode"], "plan_only")
            self.assertFalse(payload["will_execute_ollama"])
            self.assertEqual(payload["expected_child_runs"], 12)
            self.assertEqual(payload["expected_role_decisions"], 84)
            self.assertTrue(
                (Path(tmp) / "monitoring-review-cli-plan-only" / "plan.json").is_file()
            )

    def test_execute_checks_sealed_model_before_client_and_app_creation(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = cli._parse_args(
                [
                    "--execute",
                    "--plan-id",
                    "monitoring-review-cli-digest-stop",
                    "--output-root",
                    tmp,
                ]
            )
            with (
                mock.patch.object(
                    cli,
                    "_verify_ollama_model_digest",
                    side_effect=RuntimeError("digest mismatch sentinel"),
                ) as verify,
                mock.patch.object(
                    cli,
                    "ObservedOllamaJSONClient",
                    side_effect=AssertionError("client constructed before digest check"),
                ),
                mock.patch.object(
                    cli,
                    "create_app",
                    side_effect=AssertionError("app constructed before digest check"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "digest mismatch sentinel"):
                    asyncio.run(cli._main(args))

            verify.assert_awaited_once_with(
                host=cli.DEFAULT_OLLAMA_HOST,
                model="qwen3.5:4b",
                expected_digest=(
                    "2a654d98e6fba55d452b7043684e9b57"
                    "a947e393bbffa62485a7aac05ee4eefd"
                ),
            )

    def test_execute_rejects_plan_id_that_cannot_fit_derived_session_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            args = cli._parse_args(
                [
                    "--execute",
                    "--plan-id",
                    "p" * 154,
                    "--output-root",
                    tmp,
                ]
            )
            with mock.patch.object(
                cli,
                "_verify_ollama_model_digest",
                side_effect=AssertionError("invalid session id reached Ollama"),
            ):
                with self.assertRaisesRegex(ValueError, "at most 153"):
                    asyncio.run(cli._main(args))

    def test_model_digest_verifier_requires_exact_tag_and_digest(self):
        expected = "2a654d98e6fba55d452b7043684e9b57a947e393bbffa62485a7aac05ee4eefd"
        valid = _TagsClient(
            {
                "models": [
                    {
                        "name": "qwen3.5:4b",
                        "model": "qwen3.5:4b",
                        "digest": expected,
                    }
                ]
            }
        )
        asyncio.run(
            cli._verify_ollama_model_digest(
                host="http://unused.test",
                model="qwen3.5:4b",
                expected_digest=expected,
                client=valid,
            )
        )
        self.assertEqual(valid.paths, ["/api/tags"])

        alias_only = _TagsClient(
            {
                "models": [
                    {
                        "name": "qwen3.5:latest",
                        "model": "qwen3.5:4b",
                        "digest": expected,
                    }
                ]
            }
        )
        with self.assertRaisesRegex(RuntimeError, "exact name 'qwen3.5:4b'"):
            asyncio.run(
                cli._verify_ollama_model_digest(
                    host="http://unused.test",
                    model="qwen3.5:4b",
                    expected_digest=expected,
                    client=alias_only,
                )
            )

        changed = _TagsClient(
            {
                "models": [
                    {
                        "name": "qwen3.5:4b",
                        "digest": "f" * 64,
                    }
                ]
            }
        )
        with self.assertRaisesRegex(RuntimeError, "digest mismatch"):
            asyncio.run(
                cli._verify_ollama_model_digest(
                    host="http://unused.test",
                    model="qwen3.5:4b",
                    expected_digest=expected,
                    client=changed,
                )
            )

    def test_partition_assigns_first_pass_repair_and_fallback_to_seven_roles(self):
        role_results = []
        physical_counts = (1, 2, 2, 1, 1, 1, 1)
        for index, role in enumerate(MONITORING_REVIEW_ROLES):
            if index == 1:
                trace = SimpleNamespace(origin="llm", attempt_index=2)
            elif index == 2:
                # Fallback contractual 3 = dos llamadas fisicas fallidas + decision
                # determinista local, que no es una llamada a Ollama.
                trace = SimpleNamespace(
                    origin="guardrail_fallback",
                    attempt_index=3,
                )
            else:
                trace = SimpleNamespace(origin="llm", attempt_index=1)
            role_results.append(
                SimpleNamespace(
                    agent_name=role,
                    decision=SimpleNamespace(generation_trace=trace),
                )
            )
        result = SimpleNamespace(role_results=tuple(role_results))
        attempts = tuple(_physical_attempt(index) for index in range(1, 10))

        partition = cli._partition_physical_attempts(result, attempts)

        self.assertEqual(tuple(partition), MONITORING_REVIEW_ROLES)
        self.assertEqual(
            tuple(len(partition[role]) for role in MONITORING_REVIEW_ROLES),
            physical_counts,
        )
        self.assertEqual(partition["supervisor"][0].attempt_index, 1)
        self.assertEqual(partition["cleaner"][-1].attempt_index, 3)
        self.assertEqual(partition["structurer"][-1].attempt_index, 5)
        self.assertEqual(partition["report_verifier"][-1].attempt_index, 9)

        with self.assertRaisesRegex(RuntimeError, "do not match"):
            cli._partition_physical_attempts(result, attempts[:-1])
        self.assertEqual(
            cli._partition_physical_attempts(
                result,
                (),
                allow_missing=True,
            ),
            {},
        )

    def test_progress_recorder_slices_calls_per_child_and_resumed_child_is_empty(self):
        attempts = [_physical_attempt(1)]
        by_child = {}
        with contextlib.redirect_stdout(io.StringIO()):
            record = cli._progress_recorder(
                1,
                physical_attempts=attempts,
                physical_by_child=by_child,
            )
            attempts.extend((_physical_attempt(2), _physical_attempt(3)))
            record({"kind": "review_terminal", "child_run_id": "child-1"})
            attempts.append(_physical_attempt(4))
            record({"kind": "review_terminal", "child_run_id": "child-2"})
            record({"kind": "review_terminal", "child_run_id": "child-resumed"})

        self.assertEqual(
            tuple(item.attempt_index for item in by_child["child-1"]),
            (2, 3),
        )
        self.assertEqual(
            tuple(item.attempt_index for item in by_child["child-2"]),
            (4,),
        )
        self.assertEqual(by_child["child-resumed"], ())

    def test_observe_cycle_projects_exact_preregistered_context(self):
        trigger, view, request, result = _sealed_review_pack()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            request_path = root / "monitoring_review_request.json"
            view_path = root / "monitoring_review_causal_view.json"
            result_path = root / "monitoring_review_result.json"
            request_path.write_text(
                json.dumps(request.model_dump(mode="json")),
                encoding="utf-8",
            )
            view_path.write_text(
                json.dumps(view.model_dump(mode="json")),
                encoding="utf-8",
            )
            result_path.write_text(
                json.dumps(result.model_dump(mode="json")),
                encoding="utf-8",
            )
            attempt = SimpleNamespace(
                child_run_id=result.child_run_id,
                trigger_id=trigger.trigger_id,
                request_ref=request_path.as_posix(),
                causal_view_ref=view_path.as_posix(),
                result_ref=result_path.as_posix(),
                lifecycle_status="resolved",
                error=None,
            )
            session = SimpleNamespace(
                triggers=(trigger,),
                child_runs=(attempt,),
                state=SimpleNamespace(session_id=view.session_id),
            )
            cycle = {
                "reviews": [
                    {
                        "trigger_id": trigger.trigger_id,
                        "child_run_id": result.child_run_id,
                        "resumed": False,
                    }
                ]
            }
            plan = cli.default_monitoring_review_reliability_plan(
                plan_id="monitoring-review-cli-projection"
            )
            physical = tuple(_physical_attempt(index) for index in range(1, 8))

            observations = cli._observe_cycle(
                plan=plan,
                repetition=2,
                cycle=cycle,
                session=session,
                runs_dir=root,
                physical_by_child={result.child_run_id: physical},
            )

        self.assertEqual(len(observations), 7)
        self.assertEqual(
            tuple(item.agent_name for item in observations),
            MONITORING_REVIEW_ROLES,
        )
        self.assertTrue(all(item.repetition == 2 for item in observations))
        self.assertTrue(
            all(item.context_id == "state_transition_353" for item in observations)
        )
        self.assertTrue(all(item.child_run_id == "child-001" for item in observations))
        self.assertTrue(all(item.outcome == "first_pass" for item in observations))


def _physical_attempt(attempt_index: int) -> AgentReliabilityAttempt:
    return AgentReliabilityAttempt(
        attempt_index=attempt_index,
        kind="initial",
        status="success",
        message_count=2,
        prompt_sha256=f"{attempt_index:064x}",
        schema_sha256="a" * 64,
        response_sha256="b" * 64,
        elapsed_ms=float(attempt_index),
    )


class _TagsResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _TagsClient:
    def __init__(self, payload):
        self._payload = payload
        self.paths = []

    async def get(self, path):
        self.paths.append(path)
        return _TagsResponse(self._payload)


if __name__ == "__main__":
    unittest.main()
