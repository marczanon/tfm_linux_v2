import unittest

from codigo.app.agents.supervisor import decide_supervisor_action
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import (
    CleaningConfig,
    EvaluationResult,
    MetricsReport,
    ModelingConfig,
    StructuringConfig,
)


class FakeLLMClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete_json(self, messages, *, json_schema=None):
        self.calls += 1
        self.messages = messages
        self.json_schema = json_schema
        return self.payload


class SupervisorAgentTests(unittest.TestCase):
    def test_initial_state_routes_to_manifest_executor(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-supervisor-test",
                run_id="run-supervisor-001",
            )
        )

        decision = decide_supervisor_action(state)

        self.assertEqual(decision.agent_name, "supervisor")
        self.assertEqual(decision.current_stage, "dataset_manifest")
        self.assertEqual(decision.next_stage, "dataset_manifest")
        self.assertEqual(decision.next_node, "manifest_executor")
        self.assertFalse(decision.requires_human_review)
        self.assertIsNone(decision.stop_reason)

    def test_profiling_stage_requires_manifest_path(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-supervisor-test",
            run_id="run-supervisor-002",
        )
        state_dict["current_stage"] = "profiling"
        state_dict["next_node"] = "supervisor"
        state = validate_state(state_dict)

        decision = decide_supervisor_action(state)

        self.assertEqual(decision.next_stage, "failed")
        self.assertIsNone(decision.next_node)
        self.assertIn("manifest_path", decision.stop_reason)

    def test_ready_profiling_stage_routes_to_profiler(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-supervisor-test",
            run_id="run-supervisor-003",
        )
        state_dict["current_stage"] = "profiling"
        state_dict["next_node"] = "supervisor"
        state_dict["manifest_path"] = "codigo/data/interim/cwru_bearing/manifest.csv"
        state = validate_state(state_dict)

        decision = decide_supervisor_action(state)

        self.assertEqual(decision.next_stage, "profiling")
        self.assertEqual(decision.next_node, "profiler_executor")
        self.assertIsNone(decision.stop_reason)

    def test_cleaning_stage_routes_to_cleaner_agent_before_executor(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-supervisor-test",
            run_id="run-supervisor-cleaner-001",
        )
        state_dict["current_stage"] = "cleaning"
        state_dict["next_node"] = "supervisor"
        state_dict["manifest_path"] = "codigo/data/interim/cwru_bearing/manifest.csv"
        state_dict["profile_path"] = "codigo/data/interim/cwru_bearing/profile.json"
        state = validate_state(state_dict)

        decision = decide_supervisor_action(state)

        self.assertEqual(decision.next_stage, "cleaning")
        self.assertEqual(decision.next_node, "cleaner_agent")

    def test_cleaning_stage_routes_to_executor_after_config_exists(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-supervisor-test",
            run_id="run-supervisor-cleaner-002",
        )
        state_dict["current_stage"] = "cleaning"
        state_dict["next_node"] = "supervisor"
        state_dict["manifest_path"] = "codigo/data/interim/cwru_bearing/manifest.csv"
        state_dict["profile_path"] = "codigo/data/interim/cwru_bearing/profile.json"
        state_dict["cleaning_config"] = CleaningConfig(
            strategy_id="test",
            remove_non_finite=True,
            resample_to_hz=12000,
            normalization="none",
        ).model_dump(mode="json")
        state = validate_state(state_dict)

        decision = decide_supervisor_action(state)

        self.assertEqual(decision.next_stage, "cleaning")
        self.assertEqual(decision.next_node, "cleaning_executor")

    def test_structuring_stage_routes_to_structurer_agent_before_executor(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-supervisor-test",
            run_id="run-supervisor-structurer-001",
        )
        state_dict["current_stage"] = "structuring"
        state_dict["next_node"] = "supervisor"
        state_dict["clean_path"] = "codigo/data/processed/cwru_bearing/clean_signals"
        state = validate_state(state_dict)

        decision = decide_supervisor_action(state)

        self.assertEqual(decision.next_stage, "structuring")
        self.assertEqual(decision.next_node, "structuring_agent")

    def test_structuring_stage_routes_to_executor_after_config_exists(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-supervisor-test",
            run_id="run-supervisor-structurer-002",
        )
        state_dict["current_stage"] = "structuring"
        state_dict["next_node"] = "supervisor"
        state_dict["clean_path"] = "codigo/data/processed/cwru_bearing/clean_signals"
        state_dict["structuring_config"] = StructuringConfig().model_dump(mode="json")
        state = validate_state(state_dict)

        decision = decide_supervisor_action(state)

        self.assertEqual(decision.next_stage, "structuring")
        self.assertEqual(decision.next_node, "structuring_executor")

    def test_modeling_stage_routes_to_modeler_agent_before_executor(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-supervisor-test",
            run_id="run-supervisor-modeler-001",
        )
        state_dict["current_stage"] = "modeling"
        state_dict["next_node"] = "supervisor"
        state_dict["artifacts"] = [
            {
                "name": "features",
                "artifact_type": "features",
                "path": "codigo/data/tensors/cwru_bearing/windows_features.csv",
                "producer": "structuring_executor",
            }
        ]
        state = validate_state(state_dict)

        decision = decide_supervisor_action(state)

        self.assertEqual(decision.next_stage, "modeling")
        self.assertEqual(decision.next_node, "modeling_agent")

    def test_modeling_stage_routes_to_executor_after_config_exists(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-supervisor-test",
            run_id="run-supervisor-modeler-002",
        )
        state_dict["current_stage"] = "modeling"
        state_dict["next_node"] = "supervisor"
        state_dict["artifacts"] = [
            {
                "name": "features",
                "artifact_type": "features",
                "path": "codigo/data/tensors/cwru_bearing/windows_features.csv",
                "producer": "structuring_executor",
            }
        ]
        state_dict["modeling_config"] = ModelingConfig(
            model_name="isolation_forest",
            random_state=42,
        ).model_dump(mode="json")
        state = validate_state(state_dict)

        decision = decide_supervisor_action(state)

        self.assertEqual(decision.next_stage, "modeling")
        self.assertEqual(decision.next_node, "modeling_executor")

    def test_evaluation_stage_routes_to_metrics_executor_before_metrics_exist(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-supervisor-test",
            run_id="run-supervisor-evaluator-001",
        )
        state_dict["current_stage"] = "evaluation"
        state_dict["next_node"] = "supervisor"
        state_dict["artifacts"] = [
            {
                "name": "predictions",
                "artifact_type": "predictions",
                "path": "codigo/models/cwru_bearing/predictions.csv",
                "producer": "modeling_executor",
            }
        ]
        state = validate_state(state_dict)

        decision = decide_supervisor_action(state)

        self.assertEqual(decision.next_stage, "evaluation")
        self.assertEqual(decision.next_node, "evaluator")

    def test_evaluation_stage_routes_to_evaluation_agent_after_metrics_exist(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-supervisor-test",
            run_id="run-supervisor-evaluator-002",
        )
        state_dict["current_stage"] = "evaluation"
        state_dict["next_node"] = "supervisor"
        state_dict["metrics"] = MetricsReport(
            recall=0.95,
            f1_score=0.92,
            false_positive_rate=0.08,
        ).model_dump(mode="json")
        state = validate_state(state_dict)

        decision = decide_supervisor_action(state)

        self.assertEqual(decision.next_stage, "evaluation")
        self.assertEqual(decision.next_node, "evaluation_agent")

    def test_evaluation_stage_routes_to_report_writer_after_approval(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-supervisor-test",
            run_id="run-supervisor-evaluator-003",
        )
        state_dict["current_stage"] = "evaluation"
        state_dict["next_node"] = "supervisor"
        state_dict["metrics"] = MetricsReport(
            recall=0.95,
            f1_score=0.92,
            false_positive_rate=0.08,
        ).model_dump(mode="json")
        state_dict["evaluation"] = EvaluationResult(
            approved=True,
            summary="Ejecucion aprobada.",
            next_action="continue",
            limitations=[],
        ).model_dump(mode="json")
        state = validate_state(state_dict)

        decision = decide_supervisor_action(state)

        self.assertEqual(decision.next_stage, "reporting")
        self.assertEqual(decision.next_node, "report_writer")
        self.assertIsNone(decision.stop_reason)

    def test_evaluation_stage_returns_failed_after_rejection(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-supervisor-test",
            run_id="run-supervisor-evaluator-004",
        )
        state_dict["current_stage"] = "evaluation"
        state_dict["next_node"] = "supervisor"
        state_dict["metrics"] = MetricsReport(
            recall=0.70,
            f1_score=0.65,
            false_positive_rate=0.2,
        ).model_dump(mode="json")
        state_dict["evaluation"] = EvaluationResult(
            approved=False,
            summary="Ejecucion rechazada.",
            next_action="retry_with_new_config",
            limitations=[],
        ).model_dump(mode="json")
        state = validate_state(state_dict)

        decision = decide_supervisor_action(state)

        self.assertEqual(decision.next_stage, "failed")
        self.assertIsNone(decision.next_node)
        self.assertEqual(decision.stop_reason, "Ejecucion rechazada.")

    def test_reporting_stage_returns_completed_after_report_exists(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-supervisor-test",
            run_id="run-supervisor-report-001",
        )
        state_dict["current_stage"] = "reporting"
        state_dict["next_node"] = "supervisor"
        state_dict["report_path"] = "codigo/reports/cwru_bearing/final_report.md"
        state = validate_state(state_dict)

        decision = decide_supervisor_action(state)

        self.assertEqual(decision.next_stage, "completed")
        self.assertIsNone(decision.next_node)
        self.assertIn("report generated", decision.stop_reason)

    def test_completed_stage_returns_terminal_decision(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-supervisor-test",
            run_id="run-supervisor-004",
        )
        state_dict["current_stage"] = "completed"
        state_dict["next_node"] = "supervisor"
        state = validate_state(state_dict)

        decision = decide_supervisor_action(state)

        self.assertEqual(decision.next_stage, "completed")
        self.assertIsNone(decision.next_node)
        self.assertEqual(decision.stop_reason, "completed")

    def test_llm_decision_is_used_when_valid(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-supervisor-test",
                run_id="run-supervisor-005",
            )
        )
        client = FakeLLMClient(
            {
                "agent_name": "supervisor",
                "decision_id": "run-supervisor-005:supervisor:001",
                "current_stage": "dataset_manifest",
                "next_stage": "dataset_manifest",
                "next_node": "manifest_executor",
                "requires_human_review": False,
                "stop_reason": None,
                "rationale": "The raw path is present, so the manifest can be generated.",
                "confidence": 0.92,
            }
        )

        decision = decide_supervisor_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.confidence, 0.92)
        self.assertIn("raw path", decision.rationale)
        self.assertIn("SupervisorDecision", str(client.json_schema))

    def test_invalid_llm_transition_falls_back_to_deterministic_policy(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-supervisor-test",
                run_id="run-supervisor-006",
            )
        )
        client = FakeLLMClient(
            {
                "agent_name": "supervisor",
                "decision_id": "run-supervisor-006:supervisor:001",
                "current_stage": "dataset_manifest",
                "next_stage": "cleaning",
                "next_node": "cleaning_executor",
                "requires_human_review": False,
                "stop_reason": None,
                "rationale": "Invalid jump.",
                "confidence": 0.99,
            }
        )

        decision = decide_supervisor_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.next_stage, "dataset_manifest")
        self.assertEqual(decision.next_node, "manifest_executor")
        self.assertLessEqual(decision.confidence, 0.7)
        self.assertIn("Fallback after LLM failure", decision.rationale)


if __name__ == "__main__":
    unittest.main()
