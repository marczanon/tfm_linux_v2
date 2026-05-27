import unittest

from codigo.app.agents.modeler import (
    decide_modeling_action,
    decide_modeling_retry_action,
)
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
                "comparison_candidates": [
                    {
                        "alternative_id": "pca_reconstruction_error",
                        "rationale": "Compare with linear reconstruction error.",
                        "expected_effect": "Different anomaly scoring geometry.",
                        "modeling_config": {
                            "model_name": "pca_reconstruction_error",
                            "random_state": 42,
                            "hyperparameters": {
                                "n_components": 0.95,
                                "svd_solver": "full",
                                "threshold_quantile": 0.99,
                            },
                        },
                    }
                ],
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
        self.assertEqual(
            decision.comparison_candidates[0].modeling_config.model_name,
            "pca_reconstruction_error",
        )
        self.assertIn("ModelingDecision", str(client.json_schema))

    def test_llm_modeler_can_select_pca_when_expected_path_matches(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-modeler-test",
                run_id="run-modeler-pca-001",
            )
        )
        client = FakeLLMClient(
            {
                "agent_name": "modeler",
                "decision_id": "run-modeler-pca-001:modeler:001",
                "rationale": "Use PCA reconstruction error as supported linear baseline.",
                "confidence": 0.87,
                "modeling_config": {
                    "model_name": "pca_reconstruction_error",
                    "random_state": 42,
                    "hyperparameters": {
                        "n_components": 0.95,
                        "svd_solver": "full",
                        "threshold_quantile": 0.99,
                    },
                },
                "train_split": "train",
                "validation_split": "validation",
                "expected_model_path": "codigo/models/cwru_bearing/pca_reconstruction_error.joblib",
            }
        )

        decision = decide_modeling_action(state, llm_client=client, use_llm=True)

        self.assertEqual(decision.modeling_config.model_name, "pca_reconstruction_error")
        self.assertEqual(
            decision.expected_model_path,
            "codigo/models/cwru_bearing/pca_reconstruction_error.joblib",
        )

    def test_llm_modeler_uses_dataset_specific_expected_model_path(self):
        state_dict = create_initial_cwru_state(
            thread_id="nasa-modeler-test",
            run_id="run-modeler-nasa-001",
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
        state = validate_state(state_dict)
        client = FakeLLMClient(
            {
                "agent_name": "modeler",
                "decision_id": "run-modeler-nasa-001:modeler:001",
                "rationale": "Use the supported local anomaly detector.",
                "confidence": 0.88,
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
                        "threshold_quantile": 0.99,
                    },
                },
                "train_split": "train",
                "validation_split": "validation",
                "expected_model_path": "codigo/models/nasa_ims_bearing/isolation_forest.joblib",
            }
        )

        decision = decide_modeling_action(state, llm_client=client, use_llm=True)

        self.assertEqual(
            decision.expected_model_path,
            "codigo/models/nasa_ims_bearing/isolation_forest.joblib",
        )

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

    def test_llm_retry_decision_can_change_threshold_after_failure(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-modeler-test",
                run_id="run-modeler-retry-001",
            )
        )
        payload = state.to_langgraph_state()
        payload["modeling_config"] = {
            "model_name": "isolation_forest",
            "random_state": 42,
            "hyperparameters": {
                "n_estimators": 200,
                "max_samples": "auto",
                "contamination": "auto",
                "max_features": 1.0,
                "bootstrap": False,
                "n_jobs": 1,
                "threshold_quantile": 0.99,
            },
        }
        state = validate_state(payload)
        client = FakeLLMClient(
            {
                "agent_name": "modeler",
                "decision_id": "run-modeler-retry-001:modeler_retry:001",
                "rationale": "Lower the effective threshold to reduce false negatives.",
                "confidence": 0.86,
                "source_run_id": "failed-run",
                "attempt_number": 1,
                "max_attempts": 2,
                "should_retry": True,
                "learning_summary": (
                    "The failed run missed too many anomalies; lowering the "
                    "threshold_quantile should catch more windows."
                ),
                "retry_config": {
                    "model_name": "isolation_forest",
                    "random_state": 42,
                    "hyperparameters": {
                        "n_estimators": 200,
                        "max_samples": "auto",
                        "contamination": "auto",
                        "max_features": 1.0,
                        "bootstrap": False,
                        "n_jobs": 1,
                        "threshold_quantile": 0.95,
                    },
                },
                "expected_effect": "Increase recall with possible FPR cost.",
                "stop_reason": None,
                "evidence_used": ["false_negative_summary", "threshold_convention"],
            }
        )

        decision = decide_modeling_retry_action(
            state,
            failure_analysis={"failure_modes": ["low_recall_many_missed_anomalies"]},
            source_run_id="failed-run",
            attempt_number=1,
            max_attempts=2,
            llm_client=client,
            use_llm=True,
        )

        self.assertTrue(decision.should_retry)
        self.assertEqual(
            decision.retry_config.hyperparameters["threshold_quantile"],
            0.95,
        )
        self.assertIn("ModelingRetryDecision", str(client.json_schema))

    def test_retry_decision_rejects_noop_config_and_falls_back(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-modeler-test",
                run_id="run-modeler-retry-002",
            )
        )
        payload = state.to_langgraph_state()
        payload["modeling_config"] = {
            "model_name": "isolation_forest",
            "random_state": 42,
            "hyperparameters": {"n_estimators": 200, "threshold_quantile": 0.99},
        }
        state = validate_state(payload)
        client = FakeLLMClient(
            {
                "agent_name": "modeler",
                "decision_id": "run-modeler-retry-002:modeler_retry:001",
                "rationale": "Repeat the same config.",
                "confidence": 0.86,
                "source_run_id": "failed-run",
                "attempt_number": 1,
                "max_attempts": 2,
                "should_retry": True,
                "learning_summary": "No useful change.",
                "retry_config": payload["modeling_config"],
                "expected_effect": "None.",
            }
        )

        decision = decide_modeling_retry_action(
            state,
            failure_analysis={"failure_modes": ["low_recall_many_missed_anomalies"]},
            source_run_id="failed-run",
            attempt_number=1,
            max_attempts=2,
            llm_client=client,
            use_llm=True,
        )

        self.assertFalse(decision.should_retry)
        self.assertLessEqual(decision.confidence, 0.7)
        self.assertIn("Fallback after LLM failure", decision.rationale)


if __name__ == "__main__":
    unittest.main()
