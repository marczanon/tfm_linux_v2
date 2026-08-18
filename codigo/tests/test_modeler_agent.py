import tempfile
import unittest
from pathlib import Path

from codigo.app.agents.modeler import (
    build_modeler_memory_query,
    build_modeler_retry_memory_query,
    decide_modeling_action,
    decide_modeling_retry_action,
)
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.reasoning import (
    AgentMemoryQuery,
    ReasoningMemoryRecord,
    RetrievedMemoryContext,
    RetrievedMemoryItem,
)
from codigo.app.schemas.state import DatasetProfileSummary, ProjectContext
from codigo.tests.agent_hypothesis_fixtures import with_test_agent_hypothesis


class FakeLLMClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = 0

    def complete_json(self, messages, *, json_schema=None):
        self.calls += 1
        self.messages = messages
        self.json_schema = json_schema
        if isinstance(self.payload, list):
            index = min(self.calls - 1, len(self.payload) - 1)
            return with_test_agent_hypothesis(self.payload[index])
        return with_test_agent_hypothesis(self.payload)


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
        self.assertIsNotNone(decision.generation_trace)
        self.assertEqual(decision.generation_trace.origin, "deterministic")
        self.assertEqual(decision.hypothesis.kind, "model_performance")
        self.assertTrue(decision.hypothesis.evidence_cutoff)

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
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.validation_status, "validated")

    def test_llm_modeler_uses_server_owned_envelope_without_repair(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-modeler-envelope-test",
                run_id="run-modeler-envelope-001",
            )
        )
        payload = decide_modeling_action(state).model_dump(mode="json")
        payload.update(
            {
                "agent_name": "evaluator",
                "decision_id": "foreign-run:modeler:999",
                "created_at": "not-a-server-timestamp",
                "expected_model_path": "/tmp/llm-model.bin",
                "protocol_trace": {"forged": True},
                "rationale": "Keep the supported Isolation Forest hypothesis.",
            }
        )
        payload["generation_trace"] = {"forged": True}
        client = FakeLLMClient(payload)

        decision = decide_modeling_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.agent_name, "modeler")
        self.assertEqual(
            decision.decision_id,
            "run-modeler-envelope-001:modeler:001",
        )
        self.assertEqual(
            decision.expected_model_path,
            "codigo/models/cwru_bearing/isolation_forest.joblib",
        )
        self.assertIsNone(decision.protocol_trace)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.validation_status, "validated")
        self.assertIn("server-owned", client.messages[1].content)

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

    def test_llm_modeler_can_select_one_class_svm_with_bounded_hyperparameters(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-modeler-test",
                run_id="run-modeler-ocsvm-001",
            )
        )
        client = FakeLLMClient(
            {
                "agent_name": "modeler",
                "decision_id": "run-modeler-ocsvm-001:modeler:001",
                "rationale": "Use One-Class SVM to test a margin-based detector.",
                "confidence": 0.86,
                "decision_strategy": {
                    "strategy_type": "model_family_selection",
                    "hypothesis": (
                        "Compare a margin-based unsupervised detector against "
                        "the tree and reconstruction baselines."
                    ),
                    "risk_notes": [
                        "One-Class SVM is sensitive to scaling and nu/gamma choices."
                    ],
                },
                "modeling_config": {
                    "model_name": "one_class_svm",
                    "random_state": 42,
                    "hyperparameters": {
                        "kernel": "rbf",
                        "nu": 0.05,
                        "gamma": "scale",
                        "shrinking": True,
                        "tol": 0.001,
                        "max_iter": -1,
                        "threshold_quantile": 0.99,
                    },
                },
                "train_split": "train",
                "validation_split": "validation",
                "expected_model_path": "codigo/models/cwru_bearing/one_class_svm.joblib",
                "comparison_candidates": [
                    {
                        "alternative_id": "pca_reconstruction_error",
                        "rationale": "Keep a reconstruction baseline under comparison.",
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

        self.assertEqual(decision.modeling_config.model_name, "one_class_svm")
        self.assertEqual(decision.modeling_config.hyperparameters["kernel"], "rbf")
        self.assertEqual(
            decision.expected_model_path,
            "codigo/models/cwru_bearing/one_class_svm.joblib",
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

    def test_deterministic_modeler_uses_temporal_health_indicator_policy(self):
        state = _temporal_state("run-modeler-nasa-temporal-001")

        decision = decide_modeling_action(state)

        self.assertEqual(decision.modeling_config.model_name, "pca_reconstruction_error")
        self.assertEqual(decision.decision_strategy.strategy_type, "feature_model_fit")
        self.assertIn("tendencia", decision.decision_strategy.hypothesis)
        self.assertIn(
            "temporal_health_lookup",
            decision.decision_strategy.tool_names,
        )
        self.assertIn(
            "degradation_metrics_lookup",
            decision.decision_strategy.tool_names,
        )
        self.assertIn(
            "mean_lead_time_to_failure",
            decision.decision_strategy.optimization_targets,
        )
        self.assertIn("sostenido", decision.decision_strategy.alert_policy)
        self.assertIn(
            "tool:temporal_health_lookup",
            decision.decision_strategy.evidence_refs,
        )
        self.assertIn("F1", decision.rationale)
        self.assertEqual(
            decision.expected_model_path,
            "codigo/models/nasa_ims_bearing/pca_reconstruction_error.joblib",
        )

    def test_modeler_memory_query_targets_modeler_initial_decision(self):
        state = _temporal_state("run-modeler-memory-query-001")

        query = build_modeler_memory_query(state, top_k=4, min_similarity=0.2)

        self.assertEqual(query.target_agent, "modeler")
        self.assertEqual(query.dataset, "nasa_ims_bearing")
        self.assertEqual(query.data_provenance, "synthetic")
        self.assertEqual(
            query.decision_context["supervision_profile"],
            "run_to_failure_degradation",
        )
        self.assertEqual(query.decision_context["label_source"], "temporal_proxy")
        self.assertEqual(
            query.decision_context["label_granularity"],
            "proxy_temporal",
        )
        self.assertEqual(query.decision_context["target_sample_rate_hz"], 20000)
        self.assertEqual(query.decision_context["transfer_scope"], "same_dataset")
        self.assertEqual(query.top_k, 4)
        self.assertEqual(query.min_similarity, 0.2)
        self.assertIn("run_to_failure_degradation", query.query_text)
        self.assertIn("lead time", query.query_text)

    def test_modeler_retry_memory_query_preserves_run_provenance(self):
        state = _temporal_state("run-modeler-retry-memory-query-001")

        query = build_modeler_retry_memory_query(
            state,
            failure_analysis={"failure_modes": ["late_detection"]},
            source_run_id="source-run",
            attempt_number=1,
            max_attempts=2,
        )

        self.assertEqual(query.data_provenance, "synthetic")
        self.assertEqual(query.decision_context["data_provenance"], "synthetic")
        self.assertIn("Data provenance: synthetic", query.query_text)

    def test_official_online_blind_query_hides_monitoring_and_retrospective_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            features_path = Path(tmp) / "features.csv"
            features_path.write_text(
                "\n".join(
                    [
                        (
                            "window_id,run_id,split,label,target,fault_type,"
                            "relative_life,time_to_failure_seconds,"
                            "time_since_start_seconds,rms"
                        ),
                        "train-1,set_2,train,normal,0,,0.01,9999,0,0.10",
                        "cal-1,set_2,validation,unknown,0,,0.21,8888,600,0.12",
                        (
                            "monitor-secret,set_2,test,degradation,1,"
                            "SECRET_FAILURE_MODE,0.99,SECRET_TTF,1200,9.99"
                        ),
                    ]
                ),
                encoding="utf-8",
            )
            state = _official_online_blind_state(
                "run-modeler-online-blind-query-001",
                features_path=features_path,
            )

            query = build_modeler_memory_query(state)

        self.assertIn('"evidence_view": "online_blind"', query.query_text)
        self.assertIn('"held_out_monitoring_present": true', query.query_text)
        self.assertNotIn("monitor-secret", query.query_text)
        self.assertNotIn("SECRET_FAILURE_MODE", query.query_text)
        self.assertNotIn("SECRET_TTF", query.query_text)
        self.assertNotIn("relative_life", query.query_text)
        self.assertNotIn("time_to_failure_seconds", query.query_text)
        self.assertNotIn('"target"', query.query_text)
        self.assertNotIn('"label_counts"', query.query_text)
        self.assertNotIn("lead time", query.query_text)

    def test_official_online_blind_decision_uses_only_causal_targets(self):
        state = _official_online_blind_state(
            "run-modeler-online-blind-decision-001",
        )

        decision = decide_modeling_action(state)

        self.assertEqual(
            set(decision.decision_strategy.optimization_targets),
            {
                "calibration_false_alarm_rate",
                "monitoring_alert_persistence",
                "score_trend_stability",
                "causal_leakage_prevention",
            },
        )
        self.assertEqual(decision.decision_strategy.tool_names, [])
        strategy_text = str(decision.decision_strategy.model_dump(mode="json")).lower()
        self.assertNotIn("lead_time", strategy_text)
        self.assertNotIn("time_to_failure", strategy_text)
        self.assertIn(
            "temporal:monitoring_held_out",
            decision.decision_strategy.evidence_refs,
        )
        self.assertNotIn(
            "autoencoder_dense",
            {
                candidate.modeling_config.model_name
                for candidate in decision.comparison_candidates
            },
        )

    def test_official_online_blind_llm_template_passes_guardrails(self):
        state = _official_online_blind_state(
            "run-modeler-online-blind-valid-001",
        )
        payload = decide_modeling_action(state).model_dump(mode="json")
        client = FakeLLMClient(payload)

        decision = decide_modeling_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.attempt_index, 1)
        self.assertEqual(decision.generation_trace.validation_status, "validated")
        self.assertIn(
            "policy:nasa_ims_run_to_failure_v2",
            decision.decision_strategy.evidence_refs,
        )

    def test_official_online_blind_rejects_extra_retrospective_evidence_ref(self):
        state = _official_online_blind_state(
            "run-modeler-online-blind-retrospective-ref-001",
        )
        payload = decide_modeling_action(state).model_dump(mode="json")
        payload["decision_strategy"]["evidence_refs"].append("metric:failure_time")
        client = FakeLLMClient(payload)

        decision = decide_modeling_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.generation_trace.origin, "guardrail_fallback")
        self.assertEqual(decision.generation_trace.attempt_index, 3)
        self.assertIn("retrospective evidence", decision.generation_trace.fallback_cause)
        repair_prompt = client.messages[-1].content
        self.assertIn("decision online_blind", repair_prompt)
        self.assertIn("No menciones resultados de fallo", repair_prompt)

    def test_official_online_blind_prompt_hides_dataset_profile_future_metadata(self):
        state = _official_online_blind_state(
            "run-modeler-online-blind-prompt-001",
        )
        memory_context = _memory_context_for_initial_modeler(state.run_id)
        payload = decide_modeling_action(state).model_dump(mode="json")
        client = FakeLLMClient(payload)

        decide_modeling_action(
            state,
            memory_context=memory_context,
            llm_client=client,
            use_llm=True,
        )
        prompt = "\n".join(message.content for message in client.messages)

        self.assertIn('"evidence_view": "online_blind"', prompt)
        self.assertIn("online_blind_causal_projection_v1", prompt)
        self.assertIn("Separar picos aislados de alertas sostenidas", prompt)
        self.assertNotIn("SECRET_FINAL_EVENT", prompt)
        self.assertNotIn("SECRET_FAILURE_MODE", prompt)
        self.assertNotIn("A single critical window", prompt)
        self.assertNotIn("3600.0", prompt)
        self.assertNotIn('"n_files": 984', prompt)
        self.assertNotIn('"label_counts"', prompt)
        self.assertNotIn('"tool_name": "degradation_metrics_lookup"', prompt)
        self.assertNotIn('"tool_name": "temporal_health_lookup"', prompt)

    def test_official_online_blind_blocks_retrospective_retry_query(self):
        state = _official_online_blind_state(
            "run-modeler-online-blind-retry-001",
        )

        with self.assertRaisesRegex(ValueError, "monitoring evidence is held out"):
            build_modeler_retry_memory_query(
                state,
                failure_analysis={
                    "failure_mode": "SECRET_FAILURE_MODE",
                    "mean_lead_time_to_failure": 3600.0,
                },
                source_run_id="source-run",
                attempt_number=1,
                max_attempts=2,
            )

    def test_llm_initial_modeler_can_use_retrieved_memory(self):
        state = _temporal_state("run-modeler-memory-001")
        memory_context = _memory_context_for_initial_modeler(state.run_id)
        memory_id = memory_context.items[0].record.memory_record_id
        client = FakeLLMClient(
            {
                "agent_name": "modeler",
                "decision_id": "run-modeler-memory-001:modeler:001",
                "rationale": (
                    "Use PCA and cite prior boundary memory so isolated early "
                    "critical spikes are not treated as confirmed failure."
                ),
                "confidence": 0.9,
                "decision_strategy": {
                    "strategy_type": "feature_model_fit",
                    "hypothesis": (
                        "Prioritize a temporal health indicator with sustained "
                        "alerts, lead time and nominal false-alarm control."
                    ),
                    "evidence_refs": [
                        "tool:temporal_health_lookup",
                        "tool:degradation_metrics_lookup",
                        "temporal:first_persistent_alert",
                        "metric:mean_lead_time_to_failure",
                        f"memory:{memory_id}",
                    ],
                    "risk_notes": [
                        "A critical isolated window can revert to nominal in the next window.",
                        "F1 is auxiliary under the run-to-failure profile.",
                    ],
                    "tool_names": [
                        "temporal_health_lookup",
                        "degradation_metrics_lookup",
                    ],
                    "optimization_targets": [
                        "detected_before_failure_rate",
                        "mean_lead_time_to_failure",
                        "mean_false_alarm_rate_nominal",
                        "mean_score_trend_spearman",
                    ],
                    "alert_policy": (
                        "Escalate only with persistent alert evidence; keep "
                        "isolated spikes as warning evidence, not final failure."
                    ),
                },
                "modeling_config": {
                    "model_name": "pca_reconstruction_error",
                    "random_state": 42,
                    "hyperparameters": {
                        "n_components": 0.95,
                        "svd_solver": "full",
                        "whiten": False,
                        "threshold_quantile": 0.99,
                    },
                },
                "train_split": "train",
                "validation_split": "validation",
                "expected_model_path": (
                    "codigo/models/nasa_ims_bearing/pca_reconstruction_error.joblib"
                ),
                "comparison_candidates": [
                    {
                        "alternative_id": "isolation_forest_temporal_candidate",
                        "rationale": "Compare a tree baseline for anomaly score geometry.",
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
                    }
                ],
                "memory_context_id": memory_context.context_id,
                "used_memory_context": True,
                "memory_record_ids": [memory_id],
                "memory_usage_summary": (
                    "Use the retrieved boundary case to require sustained "
                    "alert evidence before treating a window as confirmed failure."
                ),
                "memory_record_uses": [
                    {
                        "memory_record_id": memory_id,
                        "usage": "adapted",
                        "influence_summary": (
                            "Preserve early warning but avoid declaring failure "
                            "from a single critical spike."
                        ),
                        "risk_mitigation": (
                            "Evaluate persistent alert streaks, lead time and "
                            "nominal false alarms together."
                        ),
                    }
                ],
            }
        )

        decision = decide_modeling_action(
            state,
            llm_client=client,
            use_llm=True,
            memory_context=memory_context,
        )

        prompt = "\n".join(message.content for message in client.messages)
        self.assertTrue(decision.used_memory_context)
        self.assertEqual(decision.memory_context_id, memory_context.context_id)
        self.assertEqual(decision.memory_record_ids, [memory_id])
        self.assertIn("Memoria recuperada para el modelador", prompt)
        self.assertIn(memory_id, prompt)
        self.assertIn('"data_provenance": "unknown"', prompt)
        self.assertIn('"provenance_caution": true', prompt)

    def test_llm_temporal_modeler_accepts_agentic_strategy_with_tools(self):
        state = _temporal_state("run-modeler-nasa-temporal-llm-001")
        client = FakeLLMClient(
            {
                "agent_name": "modeler",
                "decision_id": "run-modeler-nasa-temporal-llm-001:modeler:001",
                "rationale": (
                    "Use PCA as interpretable temporal health score after "
                    "consulting temporal health and degradation metrics."
                ),
                "confidence": 0.89,
                "decision_strategy": {
                    "strategy_type": "feature_model_fit",
                    "hypothesis": (
                        "Prioritize a stable reconstruction-error trajectory "
                        "for early warning, lead time and nominal false alarms."
                    ),
                    "evidence_refs": [
                        "tool:temporal_health_lookup",
                        "tool:degradation_metrics_lookup",
                        "temporal:first_persistent_alert",
                        "temporal:longest_alert_streak",
                        "metric:mean_lead_time_to_failure",
                        "metric:mean_false_alarm_rate_nominal",
                        "metric:mean_score_trend_spearman",
                    ],
                    "risk_notes": [
                        "temporal_proxy labels are not official per-window ground truth.",
                        "F1 remains auxiliary for this profile.",
                    ],
                    "tool_names": [
                        "temporal_health_lookup",
                        "degradation_metrics_lookup",
                    ],
                    "optimization_targets": [
                        "detected_before_failure_rate",
                        "mean_lead_time_to_failure",
                        "mean_false_alarm_rate_nominal",
                        "mean_score_trend_spearman",
                    ],
                    "alert_policy": (
                        "Treat threshold as auxiliary; separate pico aislado "
                        "from aviso sostenido and compare sustained alerts "
                        "against trend and nominal false alarms."
                    ),
                },
                "modeling_config": {
                    "model_name": "pca_reconstruction_error",
                    "random_state": 42,
                    "hyperparameters": {
                        "n_components": 0.95,
                        "svd_solver": "full",
                        "whiten": False,
                        "threshold_quantile": 0.99,
                    },
                },
                "train_split": "train",
                "validation_split": "validation",
                "expected_model_path": (
                    "codigo/models/nasa_ims_bearing/pca_reconstruction_error.joblib"
                ),
                "comparison_candidates": [
                    {
                        "alternative_id": "isolation_forest_temporal_candidate",
                        "rationale": "Compare tree isolation as alternative score.",
                        "expected_effect": (
                            "Check earlier alerts versus nominal false alarms."
                        ),
                        "modeling_config": {
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
                        },
                    },
                    {
                        "alternative_id": "one_class_svm_temporal_candidate",
                        "rationale": "Compare non-linear margin sensitivity.",
                        "expected_effect": (
                            "Check sensitivity to degradation trend with nu/gamma."
                        ),
                        "modeling_config": {
                            "model_name": "one_class_svm",
                            "random_state": 42,
                            "hyperparameters": {
                                "kernel": "rbf",
                                "nu": 0.05,
                                "gamma": "scale",
                                "shrinking": True,
                                "tol": 0.001,
                                "max_iter": -1,
                                "threshold_quantile": 0.99,
                            },
                        },
                    },
                ],
            }
        )

        decision = decide_modeling_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.modeling_config.model_name, "pca_reconstruction_error")
        self.assertIn("temporal_health_lookup", decision.decision_strategy.tool_names)
        self.assertIn(
            "mean_false_alarm_rate_nominal",
            decision.decision_strategy.optimization_targets,
        )
        self.assertIn("aviso sostenido", decision.decision_strategy.alert_policy)
        self.assertEqual(len(decision.comparison_candidates), 2)

    def test_llm_temporal_modeler_can_select_autoencoder_with_readiness(self):
        state = _temporal_state("run-modeler-nasa-autoencoder-001")
        client = FakeLLMClient(
            {
                "agent_name": "modeler",
                "decision_id": "run-modeler-nasa-autoencoder-001:modeler:001",
                "rationale": (
                    "Use autoencoder_dense only after readiness confirms enough "
                    "nominal train windows and compare it against PCA."
                ),
                "confidence": 0.84,
                "decision_strategy": {
                    "strategy_type": "feature_model_fit",
                    "hypothesis": (
                        "Test a learned reconstruction score for degradation "
                        "trend, sustained onset and nominal false alarms."
                    ),
                    "evidence_refs": [
                        "tool:temporal_health_lookup",
                        "tool:degradation_metrics_lookup",
                        "tool:temporal_model_readiness_assessor",
                        "readiness:temporal_model_readiness",
                        "readiness:autoencoder_ready",
                        "temporal:first_persistent_alert",
                        "metric:mean_lead_time_to_failure",
                        "metric:mean_false_alarm_rate_nominal",
                        "metric:mean_score_trend_spearman",
                    ],
                    "risk_notes": [
                        "Autoencoder may improve sensitivity but increase false alarms.",
                        "Temporal proxy labels remain auxiliary evidence.",
                    ],
                    "tool_names": [
                        "temporal_health_lookup",
                        "degradation_metrics_lookup",
                        "temporal_model_readiness_assessor",
                    ],
                    "optimization_targets": [
                        "detected_before_failure_rate",
                        "mean_lead_time_to_failure",
                        "mean_false_alarm_rate_nominal",
                        "mean_score_trend_spearman",
                    ],
                    "alert_policy": (
                        "Compare pico aislado, aviso sostenido, persistent "
                        "alerts and nominal false alarms before approval."
                    ),
                },
                "modeling_config": {
                    "model_name": "autoencoder_dense",
                    "random_state": 42,
                    "hyperparameters": {
                        "hidden_layers": "32,16",
                        "latent_dim": 8,
                        "learning_rate": 0.001,
                        "batch_size": 32,
                        "max_epochs": 50,
                        "patience": 8,
                        "weight_decay": 0.0001,
                        "threshold_quantile": 0.99,
                        "device": "cpu",
                    },
                },
                "train_split": "train",
                "validation_split": "validation",
                "expected_model_path": "codigo/models/nasa_ims_bearing/autoencoder_dense.pt",
                "comparison_candidates": [
                    {
                        "alternative_id": "pca_reference",
                        "rationale": "Keep PCA as interpretable reconstruction baseline.",
                        "expected_effect": "Compare linear and non-linear reconstruction scores.",
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

        self.assertEqual(decision.modeling_config.model_name, "autoencoder_dense")
        self.assertEqual(
            decision.expected_model_path,
            "codigo/models/nasa_ims_bearing/autoencoder_dense.pt",
        )
        self.assertIn(
            "temporal_model_readiness_assessor",
            decision.decision_strategy.tool_names,
        )

    def test_llm_temporal_modeler_rejects_autoencoder_without_readiness(self):
        state = _temporal_state("run-modeler-nasa-autoencoder-invalid-001")
        client = FakeLLMClient(
            {
                "agent_name": "modeler",
                "decision_id": "run-modeler-nasa-autoencoder-invalid-001:modeler:001",
                "rationale": "Use autoencoder without checking readiness.",
                "confidence": 0.94,
                "decision_strategy": {
                    "strategy_type": "feature_model_fit",
                    "hypothesis": "Try a learned reconstruction score.",
                    "evidence_refs": [
                        "tool:temporal_health_lookup",
                        "tool:degradation_metrics_lookup",
                        "temporal:first_persistent_alert",
                        "metric:mean_lead_time_to_failure",
                        "metric:mean_false_alarm_rate_nominal",
                        "metric:mean_score_trend_spearman",
                    ],
                    "risk_notes": ["Proxy labels remain auxiliary."],
                    "tool_names": [
                        "temporal_health_lookup",
                        "degradation_metrics_lookup",
                    ],
                    "optimization_targets": [
                        "detected_before_failure_rate",
                        "mean_lead_time_to_failure",
                        "mean_false_alarm_rate_nominal",
                        "mean_score_trend_spearman",
                    ],
                    "alert_policy": "Compare pico aislado and aviso sostenido.",
                },
                "modeling_config": {
                    "model_name": "autoencoder_dense",
                    "random_state": 42,
                    "hyperparameters": {
                        "hidden_layers": "32,16",
                        "latent_dim": 8,
                        "learning_rate": 0.001,
                        "batch_size": 32,
                        "max_epochs": 50,
                        "patience": 8,
                        "weight_decay": 0.0001,
                        "threshold_quantile": 0.99,
                        "device": "cpu",
                    },
                },
                "train_split": "train",
                "validation_split": "validation",
                "expected_model_path": "codigo/models/nasa_ims_bearing/autoencoder_dense.pt",
            }
        )

        decision = decide_modeling_action(state, llm_client=client, use_llm=True)

        self.assertEqual(decision.modeling_config.model_name, "pca_reconstruction_error")
        self.assertIn("Guardrail correction", decision.rationale)

    def test_llm_temporal_modeler_receives_tool_catalog_in_prompt(self):
        state = _temporal_state("run-modeler-nasa-temporal-prompt-001")
        client = FakeLLMClient(
            {
                "agent_name": "modeler",
                "decision_id": "run-modeler-nasa-temporal-prompt-001:modeler:001",
                "rationale": "Invalid on purpose to inspect the prompt.",
                "confidence": 0.9,
                "modeling_config": {
                    "model_name": "local_outlier_factor",
                    "random_state": 42,
                    "hyperparameters": {},
                },
                "train_split": "train",
                "validation_split": "validation",
                "expected_model_path": "bad",
            }
        )

        decide_modeling_action(state, llm_client=client, use_llm=True)

        prompt = client.messages[1].content
        self.assertIn("Herramientas agenticas disponibles", prompt)
        self.assertIn("temporal_health_lookup", prompt)
        self.assertIn("degradation_metrics_lookup", prompt)
        self.assertIn("optimization_targets", prompt)
        self.assertIn("alert_policy", prompt)

    def test_temporal_modeler_rejects_threshold_only_strategy(self):
        state = _temporal_state("run-modeler-nasa-temporal-invalid-001")
        client = FakeLLMClient(
            {
                "agent_name": "modeler",
                "decision_id": "run-modeler-nasa-temporal-invalid-001:modeler:001",
                "rationale": "Tune only threshold for temporal run.",
                "confidence": 0.9,
                "decision_strategy": {
                    "strategy_type": "threshold_calibration",
                    "hypothesis": "Only tune the threshold.",
                    "risk_notes": ["Has PCA candidate."],
                },
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
                "comparison_candidates": [
                    {
                        "alternative_id": "pca",
                        "rationale": "Compare PCA.",
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

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.modeling_config.model_name, "pca_reconstruction_error")
        self.assertIn("Guardrail correction", decision.rationale)

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
                    "model_name": "local_outlier_factor",
                    "random_state": 42,
                    "hyperparameters": {},
                },
                "train_split": "train",
                "validation_split": "validation",
                "expected_model_path": "codigo/models/cwru_bearing/isolation_forest.joblib",
            }
        )

        decision = decide_modeling_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.modeling_config.model_name, "isolation_forest")
        self.assertLessEqual(decision.confidence, 0.82)
        self.assertIn("Guardrail correction", decision.rationale)
        trace = decision.generation_trace
        self.assertIsNotNone(trace)
        self.assertEqual(trace.origin, "guardrail_fallback")
        self.assertEqual(trace.attempt_index, 3)
        self.assertEqual(
            trace.fallback_from_attempt_id,
            "run-modeler-003:modeler:001:attempt:002",
        )

    def test_invalid_llm_modeling_decision_is_repaired_before_fallback(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-modeler-repair-test",
                run_id="run-modeler-repair-001",
            )
        )
        invalid_payload = {
            "agent_name": "modeler",
            "decision_id": "run-modeler-repair-001:modeler:001",
            "rationale": "Select an unsupported model.",
            "confidence": 0.99,
            "modeling_config": {
                "model_name": "local_outlier_factor",
                "random_state": 42,
                "hyperparameters": {},
            },
            "train_split": "train",
            "validation_split": "validation",
            "expected_model_path": (
                "codigo/models/cwru_bearing/isolation_forest.joblib"
            ),
        }
        repaired_payload = decide_modeling_action(state).model_dump(mode="json")
        client = FakeLLMClient([invalid_payload, repaired_payload])

        decision = decide_modeling_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.modeling_config.model_name, "isolation_forest")
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.attempt_index, 2)
        self.assertEqual(decision.generation_trace.validation_status, "repaired")
        repair_prompt = client.messages[-1].content
        self.assertIn("model_name", repair_prompt)
        self.assertIn("Declaracion de memoria segura", repair_prompt)

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
                "decision_strategy": {
                    "strategy_type": (
                        "threshold_calibration_with_alternative_comparison"
                    ),
                    "hypothesis": (
                        "Compare a bounded threshold adjustment with a family change."
                    ),
                    "evidence_refs": ["failure_analysis"],
                    "risk_notes": ["Do not optimize recall in isolation."],
                },
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
                "memory_record_uses_details": [],
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
        self.assertEqual(
            decision.decision_strategy.strategy_type,
            "threshold_calibration",
        )
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.attempt_index, 1)

    def test_llm_modeler_retry_uses_server_owned_envelope_without_repair(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-modeler-retry-envelope-test",
                run_id="run-modeler-retry-envelope-001",
            )
        )
        failure_analysis = {"failure_modes": ["insufficient_evidence"]}
        payload = decide_modeling_retry_action(
            state,
            failure_analysis=failure_analysis,
            source_run_id="failed-run",
            attempt_number=1,
            max_attempts=2,
        ).model_dump(mode="json")
        payload.update(
            {
                "agent_name": "cleaner",
                "decision_id": "foreign-run:modeler_retry:999",
                "created_at": "not-a-server-timestamp",
                "source_run_id": "llm-invented-source",
                "attempt_number": 99,
                "max_attempts": 100,
                "rationale": "Stop because the evidence does not justify a retry.",
            }
        )
        payload["generation_trace"] = {"forged": True}
        client = FakeLLMClient(payload)

        decision = decide_modeling_retry_action(
            state,
            failure_analysis=failure_analysis,
            source_run_id="failed-run",
            attempt_number=1,
            max_attempts=2,
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.agent_name, "modeler")
        self.assertEqual(
            decision.decision_id,
            "run-modeler-retry-envelope-001:modeler_retry:001",
        )
        self.assertEqual(decision.source_run_id, "failed-run")
        self.assertEqual(decision.attempt_number, 1)
        self.assertEqual(decision.max_attempts, 2)
        self.assertFalse(decision.should_retry)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.validation_status, "validated")
        self.assertIn("server-owned", client.messages[1].content)

    def test_retry_prompt_can_include_supervised_memory_context(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-modeler-test",
                run_id="run-modeler-retry-memory-001",
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
        memory_context = _memory_context_for_modeler_retry(state.run_id)
        client = FakeLLMClient(
            {
                "agent_name": "modeler",
                "decision_id": "run-modeler-retry-memory-001:modeler_retry:001",
                "rationale": "Lower the threshold but avoid the old overcorrection.",
                "confidence": 0.86,
                "source_run_id": "failed-run",
                "attempt_number": 1,
                "max_attempts": 2,
                "should_retry": True,
                "learning_summary": (
                    "The current run missed anomalies, while the retrieved "
                    "memory warns that recall-only tuning can overcorrect."
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
                "expected_effect": "Increase recall while monitoring FPR.",
                "stop_reason": None,
                "memory_context_id": memory_context.context_id,
                "used_memory_context": True,
                "memory_record_ids": ["memory-overcorrection-001"],
                "memory_usage_summary": (
                    "Use the boundary memory as a warning against an excessive "
                    "threshold drop."
                ),
                "memory_record_uses": [
                    {
                        "memory_record_id": "memory-overcorrection-001",
                        "usage": "adapted",
                        "influence_summary": (
                            "The memory supports lowering the threshold directionally."
                        ),
                        "risk_mitigation": (
                            "Use a moderate change and monitor FPR to avoid FPR=1.0."
                        ),
                    }
                ],
                "evidence_used": [
                    "false_negative_summary",
                    "memory-overcorrection-001",
                ],
            }
        )

        decision = decide_modeling_retry_action(
            state,
            failure_analysis={"failure_modes": ["low_recall_many_missed_anomalies"]},
            source_run_id="failed-run",
            attempt_number=1,
            max_attempts=2,
            memory_context=memory_context,
            llm_client=client,
            use_llm=True,
        )

        prompt = client.messages[1].content
        self.assertTrue(decision.used_memory_context)
        self.assertEqual(decision.memory_record_ids, ["memory-overcorrection-001"])
        self.assertIn("Memoria recuperada para el modelador", prompt)
        self.assertIn("memory-overcorrection-001", prompt)
        self.assertIn('"source_type": "human_review"', prompt)
        self.assertIn("pca_reconstruction_error_candidate", prompt)
        self.assertIn("compare_model_family_after_partial_threshold_gain", prompt)
        self.assertIn("no obliga a poner should_retry=false", prompt)
        self.assertIn("Guia derivada de la memoria recuperada", prompt)

    def test_retry_prompt_prefers_pca_when_episode_memory_shows_threshold_plateau(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-modeler-test",
                run_id="run-modeler-retry-memory-family-001",
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
                "threshold_quantile": 0.95,
            },
        }
        state = validate_state(payload)
        memory_context = _episode_memory_context_for_modeler_retry(state.run_id)
        client = FakeLLMClient(
            {
                "agent_name": "modeler",
                "decision_id": "run-modeler-retry-memory-family-001:modeler_retry:001",
                "rationale": "Use PCA because prior threshold tuning plateaued.",
                "confidence": 0.84,
                "source_run_id": "failed-run",
                "attempt_number": 1,
                "max_attempts": 2,
                "should_retry": True,
                "learning_summary": (
                    "The retrieved episode says threshold tuning improved F1 "
                    "only partially, so a supported model-family change is "
                    "the next hypothesis."
                ),
                "retry_config": {
                    "model_name": "pca_reconstruction_error",
                    "random_state": 42,
                    "hyperparameters": {
                        "n_components": 0.95,
                        "svd_solver": "full",
                        "whiten": False,
                        "threshold_quantile": 0.99,
                    },
                },
                "expected_effect": "Test whether reconstruction error lowers FPR.",
                "stop_reason": None,
                "memory_context_id": memory_context.context_id,
                "used_memory_context": True,
                "memory_record_ids": ["memory-threshold-plateau-001"],
                "memory_usage_summary": (
                    "Use the episode as evidence that another threshold-only "
                    "retry has limited value."
                ),
                "memory_record_uses": [
                    {
                        "memory_record_id": "memory-threshold-plateau-001",
                        "usage": "adapted",
                        "influence_summary": (
                            "The episode motivates trying a different supported "
                            "model family."
                        ),
                        "risk_mitigation": (
                            "Keep PCA within supported hyperparameters and audit "
                            "recall/FPR trade-off."
                        ),
                    }
                ],
                "evidence_used": [
                    "memory-threshold-plateau-001",
                    "supported_retry_space",
                ],
            }
        )

        decision = decide_modeling_retry_action(
            state,
            failure_analysis={"failure_modes": ["low_recall_many_missed_anomalies"]},
            source_run_id="failed-run",
            attempt_number=1,
            max_attempts=2,
            memory_context=memory_context,
            llm_client=client,
            use_llm=True,
        )

        prompt = client.messages[1].content
        self.assertTrue(decision.should_retry)
        self.assertEqual(decision.retry_config.model_name, "pca_reconstruction_error")
        self.assertIn(
            '"retry_config": {\n    "model_name": "pca_reconstruction_error"',
            prompt,
        )
        self.assertIn("retry_config preferente", prompt)
        self.assertIn("0.95 es menor que 0.99", prompt)
        self.assertIn('"model_family_shift_recommended": true', prompt)
        self.assertIn('"avoid_threshold_only_isolation_forest_retry": true', prompt)
        self.assertIn("pca_reconstruction_error como retry_config", prompt)

    def test_retry_rejects_memory_id_not_in_retrieved_context(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-modeler-test",
                run_id="run-modeler-retry-memory-002",
            )
        )
        payload = state.to_langgraph_state()
        payload["modeling_config"] = {
            "model_name": "isolation_forest",
            "random_state": 42,
            "hyperparameters": {"n_estimators": 200, "threshold_quantile": 0.99},
        }
        state = validate_state(payload)
        memory_context = _memory_context_for_modeler_retry(state.run_id)
        client = FakeLLMClient(
            {
                "agent_name": "modeler",
                "decision_id": "run-modeler-retry-memory-002:modeler_retry:001",
                "rationale": "Invents a memory id.",
                "confidence": 0.86,
                "source_run_id": "failed-run",
                "attempt_number": 1,
                "max_attempts": 2,
                "should_retry": True,
                "learning_summary": "Use unavailable memory.",
                "retry_config": {
                    "model_name": "isolation_forest",
                    "random_state": 42,
                    "hyperparameters": {
                        "n_estimators": 200,
                        "threshold_quantile": 0.95,
                    },
                },
                "expected_effect": "Increase recall.",
                "memory_context_id": memory_context.context_id,
                "used_memory_context": True,
                "memory_record_ids": ["memory-not-retrieved"],
                "memory_usage_summary": "Invents a memory usage declaration.",
                "memory_record_uses": [
                    {
                        "memory_record_id": "memory-not-retrieved",
                        "usage": "adapted",
                        "influence_summary": "Unavailable memory.",
                        "risk_mitigation": "Unavailable mitigation.",
                    }
                ],
            }
        )

        decision = decide_modeling_retry_action(
            state,
            failure_analysis={"failure_modes": ["low_recall_many_missed_anomalies"]},
            source_run_id="failed-run",
            attempt_number=1,
            max_attempts=2,
            memory_context=memory_context,
            llm_client=client,
            use_llm=True,
        )

        self.assertFalse(decision.should_retry)
        self.assertIn("Guardrail correction", decision.rationale)

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
        self.assertLessEqual(decision.confidence, 0.82)
        self.assertIn("Guardrail correction", decision.rationale)
        self.assertEqual(decision.generation_trace.origin, "guardrail_fallback")
        self.assertEqual(decision.generation_trace.attempt_index, 3)
        self.assertEqual(
            decision.generation_trace.fallback_from_attempt_id,
            "run-modeler-retry-002:modeler_retry:001:attempt:002",
        )

    def test_invalid_llm_retry_decision_is_repaired_before_fallback(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-modeler-retry-repair-test",
                run_id="run-modeler-retry-repair-001",
            )
        )
        state_payload = state.to_langgraph_state()
        state_payload["modeling_config"] = {
            "model_name": "isolation_forest",
            "random_state": 42,
            "hyperparameters": {"n_estimators": 200, "threshold_quantile": 0.99},
        }
        state = validate_state(state_payload)
        invalid_payload = {
            "agent_name": "modeler",
            "decision_id": "run-modeler-retry-repair-001:modeler_retry:001",
            "rationale": "Repeat the same configuration.",
            "confidence": 0.86,
            "source_run_id": "failed-run",
            "attempt_number": 1,
            "max_attempts": 2,
            "should_retry": True,
            "learning_summary": "No useful change.",
            "retry_config": state_payload["modeling_config"],
            "expected_effect": "None.",
        }
        repaired_payload = decide_modeling_retry_action(
            state,
            failure_analysis={"failure_modes": ["low_recall_many_missed_anomalies"]},
            source_run_id="failed-run",
            attempt_number=1,
            max_attempts=2,
            use_llm=False,
        ).model_dump(mode="json")
        repaired_payload["memory_record_uses_details"] = []
        client = FakeLLMClient([invalid_payload, repaired_payload])

        decision = decide_modeling_retry_action(
            state,
            failure_analysis={"failure_modes": ["low_recall_many_missed_anomalies"]},
            source_run_id="failed-run",
            attempt_number=1,
            max_attempts=2,
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertFalse(decision.should_retry)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.attempt_index, 2)
        self.assertEqual(decision.generation_trace.validation_status, "repaired")
        repair_prompt = client.messages[-1].content
        self.assertIn("retry_config must differ", repair_prompt)
        self.assertIn("Declaracion de memoria segura", repair_prompt)


def _memory_context_for_modeler_retry(run_id: str) -> RetrievedMemoryContext:
    query = AgentMemoryQuery(
        query_id=f"{run_id}:modeler_retry:001:memory_query",
        target_agent="modeler",
        query_text="low recall with risk of overcorrection",
        dataset="cwru_bearing",
        run_id=run_id,
        decision_id=f"{run_id}:modeler_retry:001",
        top_k=3,
    )
    record = ReasoningMemoryRecord(
        memory_record_id="memory-overcorrection-001",
        collection_name="modeler_memory",
        target_agent="modeler",
        source_type="human_review",
        run_id="old-run",
        postmortem_id="old-run:reasoning_postmortem:001",
        decision_id="old-run:modeler_retry:001",
        dataset="cwru_bearing",
        source_agent_name="modeler",
        outcome="overcorrected",
        human_verdict="partially_correct",
        memory_role="boundary_case",
        reusable_as_context=True,
        summary="Overcorrected recall-only threshold change.",
        content=(
            "Lowering threshold_quantile can catch missed anomalies, but a large "
            "drop may create too many false positives."
        ),
        metrics={"recall": 1.0, "false_positive_rate": 0.5},
        tags=["overcorrected", "threshold_quantile"],
    )
    return RetrievedMemoryContext(
        context_id=f"{query.query_id}:retrieved_memory_context",
        query=query,
        items=[
            RetrievedMemoryItem(
                record=record,
                similarity=0.91,
                retrieval_use="boundary_context",
                rank=1,
            )
        ],
        retrieval_backend="test_memory_store",
        embedding_model="local_hash_embedding:v1",
    )


def _memory_context_for_initial_modeler(run_id: str) -> RetrievedMemoryContext:
    query = AgentMemoryQuery(
        query_id=f"{run_id}:modeler:001:memory_query",
        target_agent="modeler",
        query_text="run to failure sustained alert lead time isolated spike",
        dataset="nasa_ims_bearing",
        run_id=run_id,
        decision_id=f"{run_id}:modeler:001",
        top_k=3,
    )
    record = ReasoningMemoryRecord(
        memory_record_id="memory-isolated-spike-001",
        collection_name="modeler_memory",
        target_agent="modeler",
        source_type="decision_episode",
        run_id="historic-run-to-failure",
        decision_id="historic-run-to-failure:modeler:001",
        dataset="nasa_ims_bearing",
        source_agent_name="modeler",
        outcome="partially_supported",
        human_verdict="partially_correct",
        memory_role="boundary_case",
        reusable_as_context=True,
        summary="A single critical window is not enough to declare failure.",
        content=(
            "An isolated critical anomaly score can return to nominal in the "
            "next temporal window; require sustained alert evidence and lead "
            "time analysis before treating the sequence as confirmed failure."
        ),
        metrics={
            "mean_lead_time_to_failure": 3600.0,
            "mean_false_alarm_rate_nominal": 0.12,
        },
        tags=[
            "isolated_spike_not_failure",
            "lead_time",
            "sustained_alert",
        ],
    )
    return RetrievedMemoryContext(
        context_id=f"{query.query_id}:retrieved_memory_context",
        query=query,
        items=[
            RetrievedMemoryItem(
                record=record,
                similarity=0.92,
                retrieval_use="boundary_context",
                rank=1,
            )
        ],
        retrieval_backend="test_memory_store",
        embedding_model="local_hash_embedding:v1",
    )


def _episode_memory_context_for_modeler_retry(run_id: str) -> RetrievedMemoryContext:
    query = AgentMemoryQuery(
        query_id=f"{run_id}:modeler_retry:001:memory_query",
        target_agent="modeler",
        query_text="partial threshold gain recall fpr compare model family",
        dataset="cwru_bearing",
        run_id=run_id,
        decision_id=f"{run_id}:modeler_retry:001",
        top_k=3,
    )
    record = ReasoningMemoryRecord(
        memory_record_id="memory-threshold-plateau-001",
        collection_name="modeler_memory",
        target_agent="modeler",
        source_type="decision_episode",
        run_id="old-episode-run",
        decision_id="old-episode-run:modeler_retry:001",
        dataset="cwru_bearing",
        source_agent_name="modeler",
        outcome="partially_supported",
        human_verdict=None,
        memory_role="boundary_case",
        reusable_as_context=True,
        summary="Threshold tuning improved recall only partially.",
        content=(
            "The modeler reduced threshold false negatives, but FPR remained "
            "above target; compare model family after partial threshold gain."
        ),
        metrics={"recall": 0.6571, "false_positive_rate": 0.2143},
        tags=[
            "compare_model_family_after_partial_threshold_gain",
            "recall_below_target",
            "false_positive_rate_above_target",
            "threshold_adjustment_can_reduce_false_negatives",
            "recall_gain_must_be_checked_against_fpr",
        ],
    )
    return RetrievedMemoryContext(
        context_id=f"{query.query_id}:retrieved_memory_context",
        query=query,
        items=[
            RetrievedMemoryItem(
                record=record,
                similarity=0.88,
                retrieval_use="boundary_context",
                rank=1,
            )
        ],
        retrieval_backend="test_memory_store",
        embedding_model="local_hash_embedding:v1",
    )


def _temporal_state(run_id: str):
    state_dict = create_initial_cwru_state(
        thread_id="nasa-modeler-temporal-test",
        run_id=run_id,
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
        data_provenance="synthetic",
    ).model_dump(mode="json")
    return validate_state(state_dict)


def _official_online_blind_state(
    run_id: str,
    *,
    features_path: Path | None = None,
):
    state_dict = create_initial_cwru_state(
        thread_id="nasa-modeler-online-blind-test",
        run_id=run_id,
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
        label_granularity="event",
        label_source="none",
        data_provenance="official",
        provenance_detection_method="official_dataset_provenance",
    ).model_dump(mode="json")
    state_dict["dataset_profile"] = DatasetProfileSummary(
        dataset_name="NASA IMS Set 2",
        n_files=984,
        n_samples_total=20_152_320,
        channels=["channel_1", "channel_2", "channel_3", "channel_4"],
        sample_rates_hz=[20000],
        label_counts={"SECRET_FAILURE_MODE": 984},
        summary={
            "failure_mode": "SECRET_FAILURE_MODE",
            "final_event": "SECRET_FINAL_EVENT",
        },
    ).model_dump(mode="json")
    if features_path is not None:
        state_dict["artifacts"].append(
            {
                "name": "windows_features",
                "artifact_type": "features",
                "path": features_path.as_posix(),
                "producer": "structuring_executor",
            }
        )
    return validate_state(state_dict)


if __name__ == "__main__":
    unittest.main()
