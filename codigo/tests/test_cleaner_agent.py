import json
import tempfile
import unittest
from pathlib import Path

from codigo.app.agents.cleaner import decide_cleaning_action
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import ProjectContext


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

    def test_deterministic_cleaner_uses_dataset_context_for_nasa_ims(self):
        state_dict = create_initial_cwru_state(
            thread_id="nasa-cleaner-test",
            run_id="run-cleaner-nasa-001",
        )
        state_dict["project_context"] = ProjectContext(
            dataset="nasa_ims_bearing",
            machine_type="rotating_machinery",
            signal_type="vibration",
            objective="run_to_failure_degradation",
            target_sample_rate_hz=20000,
            main_channel="channel_1",
            label_mode="degradation",
        ).model_dump(mode="json")
        state = validate_state(state_dict)

        decision = decide_cleaning_action(state)

        self.assertEqual(
            decision.cleaning_config.strategy_id,
            "nasa_ims_bearing_clean_v1",
        )
        self.assertEqual(decision.cleaning_config.resample_to_hz, 20000)
        self.assertEqual(decision.cleaning_config.selected_channel, "channel_1")
        self.assertEqual(
            decision.expected_artifact_path,
            "codigo/data/processed/nasa_ims_bearing/clean_signals",
        )

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

    def test_llm_cleaner_receives_profile_decision_summary(self):
        with tempfile.TemporaryDirectory() as tmp:
            profile_path = Path(tmp) / "profile.json"
            profile_path.write_text(
                json.dumps(
                    {
                        "dataset": "cwru_bearing",
                        "n_files": 1,
                        "sample_rate_counts": {"12000": 1},
                        "channels_detected": ["DE_time", "FE_time"],
                        "decision_summary": {
                            "quality_status": "needs_channel_selection",
                            "recommended_channels": ["DE_time", "FE_time"],
                            "supported_cleaning_options": [
                                {
                                    "option_id": "clean_DE_time_to_12000_hz",
                                    "selected_channel": "DE_time",
                                    "status": "supported",
                                }
                            ],
                        },
                        "files": [],
                    }
                ),
                encoding="utf-8",
            )
            state_dict = create_initial_cwru_state(
                thread_id="cwru-cleaner-test",
                run_id="run-cleaner-profile-001",
            )
            state_dict["profile_path"] = profile_path.as_posix()
            state = validate_state(state_dict)
            client = FakeLLMClient(
                {
                    "agent_name": "cleaner",
                    "decision_id": "run-cleaner-profile-001:cleaner:001",
                    "rationale": "Use the supported DE_time cleaning option.",
                    "confidence": 0.9,
                    "cleaning_config": {
                        "strategy_id": "cwru_clean_llm_v1",
                        "remove_non_finite": True,
                        "resample_to_hz": 12000,
                        "normalization": "none",
                        "selected_channel": "DE_time",
                        "audit_log_path": "codigo/data/processed/cwru_bearing/cleaning_summary.json",
                    },
                    "expected_artifact_path": "codigo/data/processed/cwru_bearing/clean_signals",
                    "warnings": [],
                }
            )

            decide_cleaning_action(state, llm_client=client, use_llm=True)

        prompt = client.messages[1].content
        self.assertIn("decision_summary", prompt)
        self.assertIn("needs_channel_selection", prompt)
        self.assertIn("clean_DE_time_to_12000_hz", prompt)

    def test_llm_cleaner_receives_run_to_failure_temporal_context(self):
        state_dict = create_initial_cwru_state(
            thread_id="nasa-cleaner-temporal-test",
            run_id="run-cleaner-temporal-001",
        )
        state_dict["project_context"] = ProjectContext(
            dataset="nasa_ims_bearing",
            machine_type="rotating_machinery",
            signal_type="vibration",
            objective="run_to_failure_degradation",
            target_sample_rate_hz=20000,
            main_channel="channel_1",
            label_mode="degradation",
            supervision_profile="run_to_failure_degradation",
            label_granularity="proxy_temporal",
            label_source="temporal_proxy",
        ).model_dump(mode="json")
        state = validate_state(state_dict)
        client = FakeLLMClient(
            {
                "agent_name": "cleaner",
                "decision_id": "run-cleaner-temporal-001:cleaner:001",
                "rationale": (
                    "Keep channel_1 and avoid normalization to preserve temporal "
                    "score continuity."
                ),
                "confidence": 0.88,
                "cleaning_config": {
                    "strategy_id": "nasa_ims_bearing_clean_llm_v1",
                    "remove_non_finite": True,
                    "resample_to_hz": 20000,
                    "normalization": "none",
                    "selected_channel": "channel_1",
                    "audit_log_path": "codigo/data/processed/nasa_ims_bearing/cleaning_summary.json",
                },
                "expected_artifact_path": (
                    "codigo/data/processed/nasa_ims_bearing/clean_signals"
                ),
                "warnings": [],
            }
        )

        decide_cleaning_action(state, llm_client=client, use_llm=True)

        prompt = client.messages[1].content
        self.assertIn("Contexto temporal del perfil", prompt)
        self.assertIn("run_to_failure_degradation", prompt)
        self.assertIn("signal_quality_gate_for_temporal_monitoring", prompt)
        self.assertIn("continuidad temporal", prompt)
        self.assertIn("El cleaner no decide fallos ni RUL", prompt)

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
