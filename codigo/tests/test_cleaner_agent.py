import unittest

from codigo.app.agents.cleaner import decide_cleaning_action
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


class CleanerAgentTests(unittest.TestCase):
    def test_deterministic_cleaner_returns_safe_default_config(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-cleaner-test",
                run_id="run-cleaner-001",
            )
        )

        decision = decide_cleaning_action(state)

        self.assertEqual(decision.agent_name, "cleaner")
        self.assertEqual(decision.cleaning_config.strategy_id, "cwru_clean_v1")
        self.assertTrue(decision.cleaning_config.remove_non_finite)
        self.assertEqual(decision.cleaning_config.resample_to_hz, 12000)
        self.assertEqual(decision.cleaning_config.normalization, "none")

    def test_llm_cleaning_decision_is_used_when_valid(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-cleaner-test",
                run_id="run-cleaner-002",
            )
        )
        client = FakeLLMClient(
            {
                "agent_name": "cleaner",
                "decision_id": "run-cleaner-002:cleaner:001",
                "rationale": "The profile uses CWRU vibration signals and should be resampled.",
                "confidence": 0.91,
                "cleaning_config": {
                    "strategy_id": "cwru_clean_llm_v1",
                    "remove_non_finite": True,
                    "resample_to_hz": 12000,
                    "normalization": "none",
                    "audit_log_path": "codigo/data/processed/cwru_bearing/cleaning_summary.json",
                },
                "expected_artifact_path": "codigo/data/processed/cwru_bearing/clean_signals",
                "warnings": [],
            }
        )

        decision = decide_cleaning_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.confidence, 0.91)
        self.assertEqual(decision.cleaning_config.strategy_id, "cwru_clean_llm_v1")

    def test_invalid_llm_cleaning_decision_falls_back(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-cleaner-test",
                run_id="run-cleaner-003",
            )
        )
        client = FakeLLMClient(
            {
                "agent_name": "cleaner",
                "decision_id": "run-cleaner-003:cleaner:001",
                "rationale": "Invalid sample rate.",
                "confidence": 0.99,
                "cleaning_config": {
                    "strategy_id": "bad_config",
                    "remove_non_finite": True,
                    "resample_to_hz": 48000,
                    "normalization": "none",
                    "audit_log_path": None,
                },
                "expected_artifact_path": "codigo/data/processed/cwru_bearing/clean_signals",
                "warnings": [],
            }
        )

        decision = decide_cleaning_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.cleaning_config.strategy_id, "cwru_clean_v1")
        self.assertEqual(decision.cleaning_config.resample_to_hz, 12000)
        self.assertLessEqual(decision.confidence, 0.7)
        self.assertIn("Fallback after LLM failure", decision.rationale)


if __name__ == "__main__":
    unittest.main()
