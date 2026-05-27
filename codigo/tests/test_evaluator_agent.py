import unittest

from codigo.app.agents.evaluator import decide_evaluation_action
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import MetricsReport, ProjectContext


class FakeLLMClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete_json(self, messages, *, json_schema=None):
        self.calls += 1
        self.messages = messages
        self.json_schema = json_schema
        return self.payload


class EvaluatorAgentTests(unittest.TestCase):
    def test_deterministic_evaluator_approves_metrics_above_thresholds(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-evaluator-test",
            run_id="run-evaluator-001",
        )
        state_dict["metrics"] = MetricsReport(
            recall=0.95,
            f1_score=0.92,
            false_positive_rate=0.08,
        ).model_dump(mode="json")
        state = validate_state(state_dict)

        decision = decide_evaluation_action(state)

        self.assertEqual(decision.agent_name, "evaluator")
        self.assertTrue(decision.evaluation.approved)
        self.assertEqual(decision.evaluation.next_action, "continue")
        self.assertEqual(decision.min_recall_required, 0.9)
        self.assertEqual(decision.max_false_positive_rate, 0.1)

    def test_deterministic_evaluator_rejects_low_recall(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-evaluator-test",
            run_id="run-evaluator-002",
        )
        state_dict["metrics"] = MetricsReport(
            recall=0.85,
            f1_score=0.8,
            false_positive_rate=0.04,
        ).model_dump(mode="json")
        state = validate_state(state_dict)

        decision = decide_evaluation_action(state)

        self.assertFalse(decision.evaluation.approved)
        self.assertEqual(decision.evaluation.next_action, "retry_with_new_config")
        self.assertIn("umbrales", " ".join(decision.evaluation.limitations))

    def test_deterministic_evaluator_uses_dataset_specific_limitation(self):
        state_dict = create_initial_cwru_state(
            thread_id="nasa-evaluator-test",
            run_id="run-evaluator-nasa-001",
        )
        state_dict["project_context"] = ProjectContext(
            dataset="nasa_ims_bearing",
            machine_type="rotating_machinery",
            signal_type="vibration",
            objective="binary_anomaly_detection",
            target_sample_rate_hz=20000,
            main_channel="channel_1",
            label_mode="binary_anomaly",
        ).model_dump(mode="json")
        state_dict["metrics"] = MetricsReport(
            recall=0.68,
            f1_score=0.76,
            false_positive_rate=0.28,
        ).model_dump(mode="json")
        state = validate_state(state_dict)

        decision = decide_evaluation_action(state)

        limitations = " ".join(decision.evaluation.limitations)
        self.assertIn("nasa_ims_bearing", limitations)
        self.assertNotIn("CWRU", limitations)

    def test_llm_evaluation_decision_is_used_when_valid(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-evaluator-test",
            run_id="run-evaluator-003",
        )
        state_dict["metrics"] = MetricsReport(
            recall=0.95,
            f1_score=0.92,
            false_positive_rate=0.08,
        ).model_dump(mode="json")
        state = validate_state(state_dict)
        client = FakeLLMClient(
            {
                "agent_name": "evaluator",
                "decision_id": "run-evaluator-003:evaluator:001",
                "rationale": "Recall and false positive rate satisfy the MVP thresholds.",
                "confidence": 0.91,
                "evaluation": {
                    "approved": True,
                    "summary": "Execution approved for the local MVP.",
                    "next_action": "continue",
                    "limitations": ["CWRU remains a controlled benchmark."],
                },
                "min_recall_required": 0.9,
                "max_false_positive_rate": 0.1,
            }
        )

        decision = decide_evaluation_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertTrue(decision.evaluation.approved)
        self.assertEqual(decision.confidence, 0.91)
        self.assertIn("EvaluationDecision", str(client.json_schema))

    def test_invalid_llm_evaluation_decision_falls_back(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-evaluator-test",
            run_id="run-evaluator-004",
        )
        state_dict["metrics"] = MetricsReport(
            recall=0.80,
            f1_score=0.75,
            false_positive_rate=0.12,
        ).model_dump(mode="json")
        state = validate_state(state_dict)
        client = FakeLLMClient(
            {
                "agent_name": "evaluator",
                "decision_id": "run-evaluator-004:evaluator:001",
                "rationale": "Incorrectly approves weak metrics.",
                "confidence": 0.99,
                "evaluation": {
                    "approved": True,
                    "summary": "Approved despite weak metrics.",
                    "next_action": "continue",
                    "limitations": [],
                },
                "min_recall_required": 0.9,
                "max_false_positive_rate": 0.1,
            }
        )

        decision = decide_evaluation_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertFalse(decision.evaluation.approved)
        self.assertEqual(decision.evaluation.next_action, "retry_with_new_config")
        self.assertLessEqual(decision.confidence, 0.7)
        self.assertIn("Fallback after LLM failure", decision.rationale)


if __name__ == "__main__":
    unittest.main()
