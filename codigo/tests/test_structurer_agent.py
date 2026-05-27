import tempfile
import unittest
from pathlib import Path

import numpy as np

from codigo.app.agents.structurer import decide_structuring_action
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


class StructurerAgentTests(unittest.TestCase):
    def test_deterministic_structurer_returns_safe_default_config(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-structurer-test",
                run_id="run-structurer-001",
            )
        )

        decision = decide_structuring_action(state)

        self.assertEqual(decision.agent_name, "structurer")
        self.assertEqual(decision.structuring_config.window_size, 2048)
        self.assertEqual(decision.structuring_config.overlap, 0.5)
        self.assertEqual(decision.structuring_config.main_channel, "DE_time")
        self.assertEqual(decision.structuring_config.label_mode, "binary_anomaly")
        self.assertIn("rms", decision.structuring_config.features)

    def test_llm_structuring_decision_is_used_when_valid(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-structurer-test",
                run_id="run-structurer-002",
            )
        )
        client = FakeLLMClient(
            {
                "agent_name": "structurer",
                "decision_id": "run-structurer-002:structurer:001",
                "rationale": "Use standard CWRU temporal windows for baseline anomaly detection.",
                "confidence": 0.91,
                "structuring_config": {
                    "window_size": 2048,
                    "overlap": 0.5,
                    "main_channel": "DE_time",
                    "target_sample_rate_hz": 12000,
                    "label_mode": "binary_anomaly",
                    "features": ["mean", "std", "rms", "min", "max"],
                },
                "expected_features_path": "codigo/data/tensors/cwru_bearing/windows_features.csv",
                "expected_tensors_path": "codigo/data/tensors/cwru_bearing/windows_raw.npz",
                "expected_splits_path": "codigo/data/tensors/cwru_bearing/splits.json",
                "comparison_candidates": [
                    {
                        "alternative_id": "win_1024_ov_50",
                        "rationale": "Compare shorter windows.",
                        "expected_effect": "Higher temporal resolution.",
                        "structuring_config": {
                            "window_size": 1024,
                            "overlap": 0.5,
                            "main_channel": "DE_time",
                            "target_sample_rate_hz": 12000,
                            "label_mode": "binary_anomaly",
                            "features": ["mean", "std", "rms", "min", "max"],
                        },
                    }
                ],
            }
        )

        decision = decide_structuring_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.confidence, 0.91)
        self.assertEqual(decision.structuring_config.features, ["mean", "std", "rms", "min", "max"])
        self.assertEqual(decision.comparison_candidates[0].alternative_id, "win_1024_ov_50")

    def test_llm_structurer_can_choose_supported_alternative_window(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-structurer-test",
                run_id="run-structurer-004",
            )
        )
        client = FakeLLMClient(
            {
                "agent_name": "structurer",
                "decision_id": "run-structurer-004:structurer:001",
                "rationale": "Choose a shorter supported window for higher temporal resolution.",
                "confidence": 0.88,
                "structuring_config": {
                    "window_size": 1024,
                    "overlap": 0.25,
                    "main_channel": "DE_time",
                    "target_sample_rate_hz": 12000,
                    "label_mode": "binary_anomaly",
                    "features": ["mean", "std", "rms", "energy"],
                },
                "expected_features_path": "codigo/data/tensors/cwru_bearing/windows_features.csv",
                "expected_tensors_path": "codigo/data/tensors/cwru_bearing/windows_raw.npz",
                "expected_splits_path": "codigo/data/tensors/cwru_bearing/splits.json",
            }
        )

        decision = decide_structuring_action(state, llm_client=client, use_llm=True)

        self.assertEqual(decision.structuring_config.window_size, 1024)
        self.assertEqual(decision.structuring_config.overlap, 0.25)

    def test_llm_structurer_receives_structuring_decision_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            clean_dir = Path(tmp) / "clean"
            clean_dir.mkdir()
            np.savez_compressed(
                clean_dir / "97.npz",
                signal=np.asarray(list(range(4096)), dtype=np.float32),
                file_id="97",
                label="normal",
                fault_type="",
                channel="DE_time",
                sample_rate_hz=12000,
            )
            state_dict = create_initial_cwru_state(
                thread_id="cwru-structurer-test",
                run_id="run-structurer-summary-001",
            )
            state_dict["clean_path"] = clean_dir.as_posix()
            state = validate_state(state_dict)
            client = FakeLLMClient(
                {
                    "agent_name": "structurer",
                    "decision_id": "run-structurer-summary-001:structurer:001",
                    "rationale": "Use the supported 2048-window baseline.",
                    "confidence": 0.9,
                    "structuring_config": {
                        "window_size": 2048,
                        "overlap": 0.5,
                        "main_channel": "DE_time",
                        "target_sample_rate_hz": 12000,
                        "label_mode": "binary_anomaly",
                        "features": ["mean", "std", "rms", "energy"],
                    },
                    "expected_features_path": "codigo/data/tensors/cwru_bearing/windows_features.csv",
                    "expected_tensors_path": "codigo/data/tensors/cwru_bearing/windows_raw.npz",
                    "expected_splits_path": "codigo/data/tensors/cwru_bearing/splits.json",
                }
            )

            decide_structuring_action(state, llm_client=client, use_llm=True)

        prompt = client.messages[1].content
        self.assertIn("decision_summary", prompt)
        self.assertIn("candidate_configurations", prompt)
        self.assertIn("comparison_candidates", prompt)
        self.assertIn("win_2048_ov_50", prompt)

    def test_invalid_llm_structuring_alternative_falls_back(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-structurer-test",
                run_id="run-structurer-invalid-alt-001",
            )
        )
        client = FakeLLMClient(
            {
                "agent_name": "structurer",
                "decision_id": "run-structurer-invalid-alt-001:structurer:001",
                "rationale": "Use valid main config but invalid alternative.",
                "confidence": 0.99,
                "structuring_config": {
                    "window_size": 2048,
                    "overlap": 0.5,
                    "main_channel": "DE_time",
                    "target_sample_rate_hz": 12000,
                    "label_mode": "binary_anomaly",
                    "features": ["mean", "rms"],
                },
                "expected_features_path": "codigo/data/tensors/cwru_bearing/windows_features.csv",
                "expected_tensors_path": "codigo/data/tensors/cwru_bearing/windows_raw.npz",
                "expected_splits_path": "codigo/data/tensors/cwru_bearing/splits.json",
                "comparison_candidates": [
                    {
                        "alternative_id": "bad_freq",
                        "rationale": "Invalid target rate.",
                        "expected_effect": "Should be rejected.",
                        "structuring_config": {
                            "window_size": 1024,
                            "overlap": 0.5,
                            "main_channel": "DE_time",
                            "target_sample_rate_hz": 48000,
                            "label_mode": "binary_anomaly",
                            "features": ["mean", "rms"],
                        },
                    }
                ],
            }
        )

        decision = decide_structuring_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.structuring_config.window_size, 2048)
        self.assertEqual(decision.comparison_candidates, [])
        self.assertIn("Fallback after LLM failure", decision.rationale)

    def test_invalid_llm_structuring_decision_falls_back(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-structurer-test",
                run_id="run-structurer-003",
            )
        )
        client = FakeLLMClient(
            {
                "agent_name": "structurer",
                "decision_id": "run-structurer-003:structurer:001",
                "rationale": "Invalid frequency.",
                "confidence": 0.99,
                "structuring_config": {
                    "window_size": 1024,
                    "overlap": 0.25,
                    "main_channel": "DE_time",
                    "target_sample_rate_hz": 48000,
                    "label_mode": "binary_anomaly",
                    "features": ["mean", "rms"],
                },
                "expected_features_path": "codigo/data/tensors/cwru_bearing/windows_features.csv",
                "expected_tensors_path": "codigo/data/tensors/cwru_bearing/windows_raw.npz",
                "expected_splits_path": "codigo/data/tensors/cwru_bearing/splits.json",
            }
        )

        decision = decide_structuring_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.structuring_config.window_size, 2048)
        self.assertEqual(decision.structuring_config.target_sample_rate_hz, 12000)
        self.assertLessEqual(decision.confidence, 0.7)
        self.assertIn("Fallback after LLM failure", decision.rationale)


if __name__ == "__main__":
    unittest.main()
