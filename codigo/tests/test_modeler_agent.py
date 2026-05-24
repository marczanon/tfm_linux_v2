import unittest

from codigo.app.agents.modeler import decide_modeling_action
from codigo.app.graph.state import create_initial_cwru_state, validate_state


class FakeLLMClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete_json(self, messages, *, json_schema=None):
        self.calls += 1
        self.messages = messages
        self.json_schema = json_schema
        return self.payload


class ModelerAgentTests(unittest.TestCase):
    def test_deterministic_modeler_returns_safe_default_config(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-modeler-test",
                run_id="run-modeler-001",
            )
        )

        decision = decide_modeling_action(state)

        self.assertEqual(decision.agent_name, "modeler")
        self.assertEqual(decision.modeling_config.model_name, "isolation_forest")
        self.assertEqual(decision.modeling_config.random_state, 42)
        self.assertEqual(decision.train_split, "train")
        self.assertEqual(decision.validation_split, "validation")
        self.assertEqual(
            decision.expected_model_path,
            "codigo/models/cwru_bearing/isolation_forest.joblib",
        )
        self.assertEqual(
            decision.modeling_config.hyperparameters["threshold_quantile"],
            0.99,
        )

    def test_llm_modeling_decision_is_used_when_valid(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-modeler-test",
                run_id="run-modeler-002",
            )
        )
        client = FakeLLMClient(
            {
                "agent_name": "modeler",
                "decision_id": "run-modeler-002:modeler:001",
                "rationale": "Use Isolation Forest as the supported MVP anomaly detector.",
                "confidence": 0.91,
                "modeling_config": {
                    "model_name": "isolation_forest",
                    "random_state": 42,
                    "hyperparameters": {
                        "n_estimators": 100,
                        "max_samples": "auto",
                        "contamination": "auto",
                        "max_features": 1.0,
                        "bootstrap": False,
                        "n_jobs": 1,
                        "threshold_quantile": 0.95,
                    },
                },
                "train_split": "train",
                "validation_split": "validation",
                "expected_model_path": "codigo/models/cwru_bearing/isolation_forest.joblib",
            }
        )

        decision = decide_modeling_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.confidence, 0.91)
        self.assertEqual(decision.modeling_config.hyperparameters["n_estimators"], 100)
        self.assertEqual(
            decision.modeling_config.hyperparameters["threshold_quantile"],
            0.95,
        )
        self.assertIn("ModelingDecision", str(client.json_schema))

    def test_invalid_llm_modeling_decision_falls_back(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-modeler-test",
                run_id="run-modeler-003",
            )
        )
        client = FakeLLMClient(
            {
                "agent_name": "modeler",
                "decision_id": "run-modeler-003:modeler:001",
                "rationale": "Try a model that the MVP executor cannot train yet.",
                "confidence": 0.99,
                "modeling_config": {
                    "model_name": "one_class_svm",
                    "random_state": 42,
                    "hyperparameters": {},
                },
                "train_split": "train",
                "validation_split": "validation",
                "expected_model_path": "codigo/models/cwru_bearing/isolation_forest.joblib",
            }
        )

        decision = decide_modeling_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.modeling_config.model_name, "isolation_forest")
        self.assertLessEqual(decision.confidence, 0.7)
        self.assertIn("Fallback after LLM failure", decision.rationale)


if __name__ == "__main__":
    unittest.main()
