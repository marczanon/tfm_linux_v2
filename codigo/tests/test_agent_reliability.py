import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from codigo.app.agents.supervisor import decide_supervisor_action_deterministic
from codigo.app.services.agent_reliability import (
    AgentReliabilityAcceptancePolicy,
    AgentReliabilityAttempt,
    AgentReliabilityInvariant,
    AgentReliabilityModelConfig,
    AgentReliabilityObservation,
    AgentReliabilityPlan,
    ObservedOllamaJSONClient,
    assess_agent_reliability_gate,
    default_agent_reliability_plan,
    materialize_agent_reliability_state,
    run_agent_reliability_plan,
    summarize_agent_reliability,
    write_agent_reliability_artifacts,
)
from codigo.app.services.llm import LLMCallError, LLMMessage, OllamaJSONClient
from codigo.scripts import run_agent_decision_reliability as cli
from codigo.tests.agent_hypothesis_fixtures import with_test_agent_hypothesis


class FailingJSONClient:
    def complete_json(self, messages, *, json_schema=None):
        del messages, json_schema
        raise LLMCallError("synthetic transport failure")


class SequenceJSONClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = 0

    def complete_json(self, messages, *, json_schema=None):
        del messages, json_schema
        index = min(self.calls, len(self.payloads) - 1)
        self.calls += 1
        return with_test_agent_hypothesis(self.payloads[index])


class AgentReliabilityTests(unittest.TestCase):
    def test_default_plan_covers_every_agent_callable_without_memory_or_pipeline(self):
        plan = default_agent_reliability_plan()

        self.assertEqual(
            {scenario.entrypoint for scenario in plan.scenarios},
            {
                "supervisor",
                "cleaner",
                "structurer",
                "modeler",
                "modeler_retry",
                "evaluator",
                "report_writer",
                "report_reviser",
                "report_verifier",
            },
        )
        self.assertFalse(plan.memory_enabled)
        self.assertFalse(plan.pipeline_executed)
        self.assertTrue(
            any(scenario.dataset == "nasa_ims_bearing" for scenario in plan.scenarios)
        )
        self.assertTrue(
            any(scenario.dataset == "cwru_bearing" for scenario in plan.scenarios)
        )

    def test_all_scenarios_are_dispatchable_and_every_fallback_blocks_gate(self):
        plan = default_agent_reliability_plan(
            repetitions=1,
            minimum_first_pass_rate=0.0,
        )

        result = run_agent_reliability_plan(
            plan,
            client_factory=lambda _scenario, _state, _attempts: FailingJSONClient(),
            model_config=AgentReliabilityModelConfig(
                provider="scripted",
                model="always-fails",
                transport_trace_scope="logical_complete_json_only",
            ),
        )

        self.assertEqual(len(result.observations), len(plan.scenarios))
        self.assertEqual(result.summary.fallback_count, len(plan.scenarios))
        self.assertEqual(result.summary.error_count, 0)
        self.assertEqual(result.gate.verdict, "blocked")
        self.assertIn(
            f"fallback_count:{len(plan.scenarios)}",
            result.gate.blockers,
        )
        self.assertEqual(
            {item.entrypoint for item in result.observations},
            {scenario.entrypoint for scenario in plan.scenarios},
        )

    def test_valid_supervisor_payload_is_classified_as_first_pass_llm(self):
        base_plan = default_agent_reliability_plan(
            repetitions=1,
            minimum_first_pass_rate=0.0,
        )
        scenario = next(
            item
            for item in base_plan.scenarios
            if item.scenario_id == "supervisor_cwru_initial"
        )
        plan = base_plan.model_copy(
            update={
                "scenarios": [scenario],
                "acceptance": AgentReliabilityAcceptancePolicy(
                    minimum_repetitions=1,
                    minimum_first_pass_rate=1.0,
                ),
            }
        )

        def factory(_scenario, state, _attempts):
            payload = decide_supervisor_action_deterministic(state).model_dump(
                mode="json",
                exclude={"generation_trace"},
            )
            return SequenceJSONClient([payload])

        result = run_agent_reliability_plan(
            plan,
            client_factory=factory,
            model_config=AgentReliabilityModelConfig(
                provider="scripted",
                model="valid-supervisor",
                transport_trace_scope="logical_complete_json_only",
            ),
        )

        self.assertEqual(result.observations[0].outcome, "first_pass")
        self.assertEqual(result.observations[0].generation_origin, "llm")
        self.assertEqual(result.summary.first_pass_rate, 1.0)
        self.assertEqual(result.gate.verdict, "passed")

    def test_contract_repair_is_llm_success_but_not_first_pass(self):
        base_plan = default_agent_reliability_plan(
            repetitions=1,
            minimum_first_pass_rate=0.0,
        )
        scenario = next(
            item
            for item in base_plan.scenarios
            if item.scenario_id == "supervisor_cwru_initial"
        )
        plan = base_plan.model_copy(
            update={
                "scenarios": [scenario],
                "acceptance": AgentReliabilityAcceptancePolicy(
                    minimum_repetitions=1,
                    minimum_first_pass_rate=0.0,
                ),
            }
        )

        def factory(_scenario, state, _attempts):
            valid = decide_supervisor_action_deterministic(state).model_dump(
                mode="json",
                exclude={"generation_trace"},
            )
            invalid = dict(valid)
            invalid.update(next_stage="cleaning", next_node="cleaning_executor")
            return SequenceJSONClient([invalid, valid])

        result = run_agent_reliability_plan(
            plan,
            client_factory=factory,
            model_config=AgentReliabilityModelConfig(
                provider="scripted",
                model="repaired-supervisor",
                transport_trace_scope="logical_complete_json_only",
            ),
        )

        observation = result.observations[0]
        self.assertEqual(observation.outcome, "llm_repaired")
        self.assertEqual(observation.generation_origin, "llm")
        self.assertEqual(observation.generation_validation_status, "repaired")
        self.assertEqual(len(observation.logical_attempts), 2)
        self.assertEqual(
            observation.logical_attempts[0].response_payload["next_stage"],
            "cleaning",
        )
        self.assertEqual(
            observation.logical_attempts[1].response_payload["next_stage"],
            "dataset_manifest",
        )
        self.assertEqual(result.gate.verdict, "passed")

    def test_report_verifier_policy_overlay_is_semantic_failure(self):
        base_plan = default_agent_reliability_plan(
            repetitions=1,
            minimum_first_pass_rate=0.0,
        )
        scenario = next(
            item
            for item in base_plan.scenarios
            if item.scenario_id == "report_verifier_unsafe"
        )
        plan = base_plan.model_copy(
            update={
                "scenarios": [scenario],
                "acceptance": AgentReliabilityAcceptancePolicy(
                    minimum_repetitions=1,
                    minimum_first_pass_rate=0.0,
                ),
            }
        )

        def factory(_scenario, state, _attempts):
            return SequenceJSONClient(
                [
                    {
                        "decision_id": f"{state.run_id}:report_verifier:001",
                        "rationale": "No se identifican riesgos en el informe.",
                        "confidence": 0.95,
                        "report_path": (
                            f"codigo/reports/{state.project_context.dataset}/"
                            f"{state.run_id}/final_report.md"
                        ),
                        "verification_status": "approved",
                        "summary": "Informe aprobado.",
                        "unsupported_claims": [],
                        "misleading_claims": [],
                        "missing_limitations": [],
                        "required_corrections": [],
                        "acceptable_style_notes": [],
                        "evidence_refs": [],
                    }
                ]
            )

        result = run_agent_reliability_plan(
            plan,
            client_factory=factory,
            model_config=AgentReliabilityModelConfig(
                provider="scripted",
                model="unsafe-verifier",
                transport_trace_scope="logical_complete_json_only",
            ),
        )

        observation = result.observations[0]
        overlay_invariant = next(
            item
            for item in observation.invariants
            if item.invariant_id == "verifier_without_policy_overlay"
        )
        self.assertEqual(observation.outcome, "semantic_failure")
        self.assertTrue(observation.decision_payload["policy_overlay_applied"])
        self.assertTrue(observation.decision_payload["policy_overlay_issue_ids"])
        self.assertFalse(overlay_invariant.passed)
        self.assertIn("policy_overlay_issue_ids", overlay_invariant.detail)
        self.assertEqual(result.gate.verdict, "blocked")
        self.assertIn("semantic_failure_count:1", result.gate.blockers)

    def test_non_agentic_and_semantic_failures_block_even_without_fallback(self):
        base = default_agent_reliability_plan(repetitions=3)
        plan = base.model_copy(
            update={
                "scenarios": [base.scenarios[0]],
                "acceptance": AgentReliabilityAcceptancePolicy(
                    minimum_repetitions=3,
                    minimum_first_pass_rate=0.0,
                ),
            }
        )
        first_pass = _observation(1, "first_pass")
        non_agentic = _observation(2, "non_agentic", origin="deterministic")
        semantic = _observation(3, "semantic_failure")

        summary = summarize_agent_reliability(
            plan,
            [first_pass, non_agentic, semantic],
        )
        gate = assess_agent_reliability_gate(plan, summary)

        self.assertEqual(gate.verdict, "blocked")
        self.assertIn("non_agentic_count:1", gate.blockers)
        self.assertIn("semantic_failure_count:1", gate.blockers)

    def test_observed_ollama_client_sees_internal_json_repair_as_physical_call(self):
        physical_attempts = []
        client = ObservedOllamaJSONClient(
            physical_attempts=physical_attempts,
            model="fake-model",
        )
        responses = [
            {"message": {"content": '{"ok": true'}},
            {
                "message": {"content": '{"ok": true}'},
                "prompt_eval_count": 12,
                "eval_count": 4,
                "total_duration": 1234,
                "done_reason": "stop",
            },
        ]

        with patch.object(OllamaJSONClient, "_chat", side_effect=responses):
            payload = client.complete_json(
                [LLMMessage(role="user", content="Devuelve JSON valido.")],
                json_schema={"type": "object", "properties": {"ok": {"type": "boolean"}}},
            )

        self.assertEqual(payload, {"ok": True})
        self.assertEqual([item.kind for item in physical_attempts], ["initial", "json_repair"])
        self.assertEqual(physical_attempts[1].prompt_eval_count, 12)
        self.assertEqual(physical_attempts[1].done_reason, "stop")

    def test_artifacts_are_separate_from_runs_and_manifest_does_not_persist_host(self):
        plan = default_agent_reliability_plan(
            plan_id="reliability-test-artifacts",
            repetitions=1,
            minimum_first_pass_rate=0.0,
        ).model_copy(
            update={
                "acceptance": AgentReliabilityAcceptancePolicy(
                    minimum_repetitions=1,
                    minimum_first_pass_rate=0.0,
                )
            }
        )
        result = run_agent_reliability_plan(
            plan,
            client_factory=lambda _scenario, _state, _attempts: FailingJSONClient(),
            model_config=AgentReliabilityModelConfig(
                model="no-network",
                transport_trace_scope="logical_complete_json_only",
            ),
        )

        with tempfile.TemporaryDirectory() as tmp:
            artifacts = write_agent_reliability_artifacts(result, output_root=tmp)
            manifest_text = Path(artifacts.manifest_path).read_text(encoding="utf-8")
            summary_payload = json.loads(
                Path(artifacts.summary_path).read_text(encoding="utf-8")
            )

        self.assertNotIn("ollama_host", manifest_text)
        self.assertNotIn("127.0.0.1", manifest_text)
        self.assertEqual(summary_payload["gate"]["verdict"], "blocked")
        self.assertTrue(artifacts.output_dir.endswith("reliability-test-artifacts"))

    def test_cli_defaults_to_plan_only_and_never_builds_ollama_client(self):
        output = io.StringIO()
        with patch.object(
            cli,
            "build_observed_ollama_client_factory",
            side_effect=AssertionError("Ollama factory must not be built"),
        ):
            with redirect_stdout(output):
                exit_code = cli.main(["--repetitions", "1"])

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["mode"], "plan_only")
        self.assertFalse(payload["will_execute_ollama"])

    def test_cli_can_select_a_small_scenario_subset(self):
        output = io.StringIO()
        with redirect_stdout(output):
            exit_code = cli.main(
                [
                    "--repetitions",
                    "3",
                    "--scenario-id",
                    "report_writer_nasa",
                    "--scenario-id",
                    "report_verifier_safe",
                ]
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(exit_code, 0)
        self.assertEqual(payload["observation_count"], 6)
        self.assertEqual(
            [item["scenario_id"] for item in payload["plan"]["scenarios"]],
            ["report_writer_nasa", "report_verifier_safe"],
        )

    def test_materialized_nasa_scenario_is_small_and_memory_free(self):
        plan = default_agent_reliability_plan(repetitions=1)
        scenario = next(
            item
            for item in plan.scenarios
            if item.state_profile == "nasa_online_blind_modeling"
        )

        state = materialize_agent_reliability_state(
            scenario,
            run_id="reliability-nasa-state",
        )

        self.assertEqual(state.project_context.dataset, "nasa_ims_bearing")
        self.assertEqual(state.project_context.label_source, "none")
        self.assertEqual(state.current_stage, "modeling")
        self.assertEqual(state.messages, [])
        self.assertLess(len(state.model_dump_json()), 10_000)


def _observation(
    repetition: int,
    outcome: str,
    *,
    origin: str = "llm",
) -> AgentReliabilityObservation:
    return AgentReliabilityObservation(
        observation_id=f"synthetic:{repetition}",
        scenario_id="supervisor_cwru_initial",
        entrypoint="supervisor",
        dataset="cwru_bearing",
        repetition=repetition,
        outcome=outcome,
        elapsed_ms=1.0,
        decision_id=f"synthetic-{repetition}:supervisor:001",
        generation_origin=origin,
        generation_validation_status=(
            "validated" if outcome != "non_agentic" else "validated"
        ),
        generation_attempt_index=1,
        trace_available=True,
        invariants=[
            AgentReliabilityInvariant(
                invariant_id="synthetic",
                passed=outcome != "semantic_failure",
                detail="synthetic gate observation",
            )
        ],
        logical_attempts=[
            AgentReliabilityAttempt(
                attempt_index=1,
                kind="logical_complete_json",
                status="success",
                message_count=1,
                prompt_sha256="a" * 64,
                response_sha256="b" * 64,
                elapsed_ms=1.0,
            )
        ],
    )


if __name__ == "__main__":
    unittest.main()
