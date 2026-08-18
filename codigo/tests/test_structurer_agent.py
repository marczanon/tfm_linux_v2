import tempfile
import unittest
from pathlib import Path

import numpy as np

from codigo.app.agents.structurer import decide_structuring_action
from codigo.app.agents.structurer import build_structurer_memory_query
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
        self.assertIsNotNone(decision.generation_trace)
        self.assertEqual(decision.generation_trace.origin, "deterministic")
        self.assertEqual(decision.hypothesis.kind, "temporal_representation")
        self.assertIn("fuga", decision.hypothesis.falsification_criterion)

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
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.attempt_index, 1)

    def test_llm_structurer_uses_server_owned_envelope_without_repair(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-structurer-envelope-test",
                run_id="run-structurer-envelope-001",
            )
        )
        payload = decide_structuring_action(state).model_dump(mode="json")
        payload.update(
            {
                "agent_name": "cleaner",
                "decision_id": "foreign-run:structurer:999",
                "created_at": "not-a-server-timestamp",
                "expected_features_path": "/tmp/llm-features.csv",
                "expected_tensors_path": "/tmp/llm-tensors.npz",
                "expected_splits_path": "/tmp/llm-splits.json",
                "protocol_trace": {"forged": True},
                "rationale": "Use the supported baseline window configuration.",
            }
        )
        payload["generation_trace"] = {"forged": True}
        client = FakeLLMClient(payload)

        decision = decide_structuring_action(
            state,
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.agent_name, "structurer")
        self.assertEqual(
            decision.decision_id,
            "run-structurer-envelope-001:structurer:001",
        )
        self.assertEqual(
            decision.expected_features_path,
            "codigo/data/tensors/cwru_bearing/windows_features.csv",
        )
        self.assertEqual(
            decision.expected_tensors_path,
            "codigo/data/tensors/cwru_bearing/windows_raw.npz",
        )
        self.assertEqual(
            decision.expected_splits_path,
            "codigo/data/tensors/cwru_bearing/splits.json",
        )
        self.assertIsNone(decision.protocol_trace)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.validation_status, "validated")
        self.assertIn("server-owned", client.messages[1].content)

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

    def test_official_online_blind_structurer_hides_future_dataset_profile(self):
        state_dict = create_initial_cwru_state(
            thread_id="nasa-structurer-online-blind-test",
            run_id="run-structurer-online-blind-001",
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
            channels=["channel_1", "channel_2"],
            sample_rates_hz=[20000],
            label_counts={"SECRET_FAILURE_MODE": 984},
            summary={"final_failure": "SECRET_FINAL_EVENT"},
        ).model_dump(mode="json")
        state = validate_state(state_dict)
        memory_context = _structurer_memory_context(state.run_id)
        client = FakeLLMClient(decide_structuring_action(state).model_dump(mode="json"))

        decision = decide_structuring_action(
            state,
            memory_context=memory_context,
            llm_client=client,
            use_llm=True,
        )

        prompt = client.messages[1].content
        self.assertEqual(decision.structuring_config.label_mode, "degradation")
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertIn('"evidence_view": "online_blind"', prompt)
        self.assertIn("online_blind_causal_projection_v1", prompt)
        self.assertNotIn("SECRET_FAILURE_MODE", prompt)
        self.assertNotIn("SECRET_FINAL_EVENT", prompt)
        self.assertNotIn("Shorter 1024-sample windows", prompt)
        self.assertNotIn('"n_files": 984', prompt)
        self.assertNotIn('"label_counts"', prompt)

    def test_structurer_memory_query_targets_structurer(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-structurer-test",
                run_id="run-structurer-memory-query-001",
            )
        )

        query = build_structurer_memory_query(state, top_k=5, min_similarity=0.1)

        self.assertEqual(query.target_agent, "structurer")
        self.assertEqual(query.data_provenance, "official")
        self.assertEqual(query.decision_context["data_provenance"], "official")
        self.assertEqual(
            query.decision_context["supervision_profile"],
            "binary_fault_classification",
        )
        self.assertEqual(query.decision_context["label_source"], "official")
        self.assertEqual(query.decision_context["label_granularity"], "file")
        self.assertEqual(query.decision_context["target_sample_rate_hz"], 12000)
        self.assertEqual(query.decision_context["transfer_scope"], "same_dataset")
        self.assertEqual(query.top_k, 5)
        self.assertEqual(query.min_similarity, 0.1)
        self.assertIn("window size", query.query_text)
        self.assertIn("temporal splits", query.query_text)

    def test_llm_structurer_receives_and_declares_memory_context(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-structurer-test",
                run_id="run-structurer-memory-001",
            )
        )
        memory_context = _structurer_memory_context(state.run_id)
        client = FakeLLMClient(
            {
                "agent_name": "structurer",
                "decision_id": "run-structurer-memory-001:structurer:001",
                "rationale": "Use memory about shorter windows, but keep a supported configuration.",
                "confidence": 0.89,
                "structuring_config": {
                    "window_size": 1024,
                    "overlap": 0.5,
                    "main_channel": "DE_time",
                    "target_sample_rate_hz": 12000,
                    "label_mode": "binary_anomaly",
                    "features": ["mean", "std", "rms", "energy"],
                },
                "expected_features_path": "codigo/data/tensors/cwru_bearing/windows_features.csv",
                "expected_tensors_path": "codigo/data/tensors/cwru_bearing/windows_raw.npz",
                "expected_splits_path": "codigo/data/tensors/cwru_bearing/splits.json",
                "comparison_candidates": [],
                "memory_context_id": memory_context.context_id,
                "used_memory_context": True,
                "memory_record_ids": ["memory-structurer-window-001"],
                "memory_usage_summary": "Adapt the prior short-window evidence to this CWRU run.",
                "memory_record_uses": [
                    {
                        "memory_record_id": "memory-structurer-window-001",
                        "usage": "adapted",
                        "influence_summary": "The memory supports comparing shorter windows for temporal resolution.",
                        "risk_mitigation": "Keep supported sample rate, channel and overlap constraints.",
                    }
                ],
            }
        )

        decision = decide_structuring_action(
            state,
            memory_context=memory_context,
            llm_client=client,
            use_llm=True,
        )

        prompt = client.messages[1].content
        self.assertTrue(decision.used_memory_context)
        self.assertEqual(decision.memory_record_ids, ["memory-structurer-window-001"])
        self.assertIn("Memoria recuperada para el estructurador", prompt)
        self.assertIn("memory-structurer-window-001", prompt)

    def test_llm_structurer_can_trace_empty_context_without_claiming_use(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-structurer-test",
                run_id="run-structurer-memory-empty-001",
            )
        )
        memory_context = _structurer_memory_context(state.run_id).model_copy(
            update={"items": []}
        )
        client = FakeLLMClient(
            {
                "agent_name": "structurer",
                "decision_id": "run-structurer-memory-empty-001:structurer:001",
                "rationale": (
                    "No relevant memory was returned, so the proposal relies "
                    "only on the current signal profile."
                ),
                "confidence": 0.84,
                "structuring_config": {
                    "window_size": 2048,
                    "overlap": 0.5,
                    "main_channel": "DE_time",
                    "target_sample_rate_hz": 12000,
                    "label_mode": "binary_anomaly",
                    "features": ["mean", "std", "rms", "energy"],
                },
                "expected_features_path": (
                    "codigo/data/tensors/cwru_bearing/windows_features.csv"
                ),
                "expected_tensors_path": (
                    "codigo/data/tensors/cwru_bearing/windows_raw.npz"
                ),
                "expected_splits_path": (
                    "codigo/data/tensors/cwru_bearing/splits.json"
                ),
                "comparison_candidates": [],
                "memory_context_id": memory_context.context_id,
                "used_memory_context": False,
                "memory_record_ids": [],
                "memory_usage_summary": None,
                "memory_record_uses": [],
            }
        )

        decision = decide_structuring_action(
            state,
            memory_context=memory_context,
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertEqual(decision.memory_context_id, memory_context.context_id)
        self.assertFalse(decision.used_memory_context)
        self.assertNotIn("Fallback after LLM failure", decision.rationale)

    def test_llm_structurer_cannot_cite_unretrieved_memory(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-structurer-test",
                run_id="run-structurer-memory-invalid-001",
            )
        )
        memory_context = _structurer_memory_context(state.run_id)
        client = FakeLLMClient(
            {
                "agent_name": "structurer",
                "decision_id": "run-structurer-memory-invalid-001:structurer:001",
                "rationale": "Cite an unavailable memory.",
                "confidence": 0.99,
                "structuring_config": {
                    "window_size": 1024,
                    "overlap": 0.5,
                    "main_channel": "DE_time",
                    "target_sample_rate_hz": 12000,
                    "label_mode": "binary_anomaly",
                    "features": ["mean", "std", "rms", "energy"],
                },
                "expected_features_path": "codigo/data/tensors/cwru_bearing/windows_features.csv",
                "expected_tensors_path": "codigo/data/tensors/cwru_bearing/windows_raw.npz",
                "expected_splits_path": "codigo/data/tensors/cwru_bearing/splits.json",
                "memory_context_id": memory_context.context_id,
                "used_memory_context": True,
                "memory_record_ids": ["memory-not-retrieved"],
                "memory_usage_summary": "Invalid citation.",
                "memory_record_uses": [
                    {
                        "memory_record_id": "memory-not-retrieved",
                        "usage": "followed",
                        "influence_summary": "Invalid.",
                    }
                ],
            }
        )

        decision = decide_structuring_action(
            state,
            memory_context=memory_context,
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertFalse(decision.used_memory_context)
        self.assertEqual(decision.structuring_config.window_size, 2048)
        self.assertIn("Guardrail correction", decision.rationale)

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

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.structuring_config.window_size, 2048)
        self.assertEqual(decision.comparison_candidates, [])
        self.assertIn("Guardrail correction", decision.rationale)

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

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.structuring_config.window_size, 2048)
        self.assertEqual(decision.structuring_config.target_sample_rate_hz, 12000)
        self.assertLessEqual(decision.confidence, 0.82)
        self.assertIn("Guardrail correction", decision.rationale)
        trace = decision.generation_trace
        self.assertIsNotNone(trace)
        self.assertEqual(trace.origin, "guardrail_fallback")
        self.assertEqual(trace.validation_status, "fallback_applied")
        self.assertEqual(trace.attempt_index, 3)
        self.assertEqual(
            trace.fallback_from_attempt_id,
            "run-structurer-003:structurer:001:attempt:002",
        )

    def test_invalid_llm_structuring_decision_is_repaired_before_fallback(self):
        state = validate_state(
            create_initial_cwru_state(
                thread_id="cwru-structurer-repair-test",
                run_id="run-structurer-repair-001",
            )
        )
        invalid_payload = {
            "agent_name": "structurer",
            "decision_id": "run-structurer-repair-001:structurer:001",
            "rationale": "Use an unsupported frequency.",
            "confidence": 0.99,
            "structuring_config": {
                "window_size": 1024,
                "overlap": 0.25,
                "main_channel": "DE_time",
                "target_sample_rate_hz": 48000,
                "label_mode": "binary_anomaly",
                "features": ["mean", "rms"],
            },
            "expected_features_path": (
                "codigo/data/tensors/cwru_bearing/windows_features.csv"
            ),
            "expected_tensors_path": (
                "codigo/data/tensors/cwru_bearing/windows_raw.npz"
            ),
            "expected_splits_path": "codigo/data/tensors/cwru_bearing/splits.json",
        }
        repaired_payload = decide_structuring_action(state).model_dump(mode="json")
        client = FakeLLMClient([invalid_payload, repaired_payload])

        decision = decide_structuring_action(
            state,
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 2)
        self.assertEqual(decision.structuring_config.target_sample_rate_hz, 12000)
        self.assertEqual(decision.generation_trace.origin, "llm")
        self.assertEqual(decision.generation_trace.attempt_index, 2)
        self.assertEqual(decision.generation_trace.validation_status, "repaired")
        repair_prompt = client.messages[-1].content
        self.assertIn("target_sample_rate_hz must be 12000", repair_prompt)
        self.assertIn("Declaracion de memoria esperada", repair_prompt)


def _structurer_memory_context(run_id: str) -> RetrievedMemoryContext:
    query = AgentMemoryQuery(
        query_id=f"{run_id}:structurer:001:memory_query",
        target_agent="structurer",
        query_text="shorter windows temporal resolution feature trade-off",
        dataset="cwru_bearing",
        run_id=run_id,
        decision_id=f"{run_id}:structurer:001",
    )
    record = ReasoningMemoryRecord(
        memory_record_id="memory-structurer-window-001",
        collection_name="structurer_memory",
        target_agent="structurer",
        source_type="decision_episode",
        run_id="cwru-agentic-window-qwen-fase3",
        decision_id="structurer-window-001",
        dataset="cwru_bearing",
        source_agent_name="structurer",
        outcome="supported",
        human_verdict="partially_correct",
        memory_role="evidence",
        reusable_as_context=True,
        summary="Shorter 1024-sample windows improved temporal resolution.",
        content=(
            "The structurer compared 1024, 2048 and 4096 sample windows. "
            "The shorter supported window was useful as a comparable hypothesis."
        ),
        tags=["structuring", "window_size_1024", "temporal_resolution"],
    )
    return RetrievedMemoryContext(
        context_id=f"{query.query_id}:retrieved_memory_context",
        query=query,
        items=[
            RetrievedMemoryItem(
                record=record,
                similarity=0.82,
                retrieval_use="evidence_context",
                rank=1,
            )
        ],
        retrieval_backend="test",
        embedding_model="local_hash_embedding",
    )


if __name__ == "__main__":
    unittest.main()
