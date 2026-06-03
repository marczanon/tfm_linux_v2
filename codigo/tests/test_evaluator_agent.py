import unittest

from codigo.app.agents.evaluator import build_evaluator_memory_query
from codigo.app.agents.evaluator import decide_evaluation_action
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.reasoning import (
    AgentMemoryQuery,
    ReasoningMemoryRecord,
    RetrievedMemoryContext,
    RetrievedMemoryItem,
)
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
        self.assertEqual(decision.evaluation.next_action, "continue")
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

    def test_deterministic_evaluator_uses_temporal_degradation_metrics(self):
        state = _temporal_state("run-evaluator-nasa-temporal-001")

        decision = decide_evaluation_action(state)

        self.assertTrue(decision.evaluation.approved)
        self.assertIsNone(decision.min_recall_required)
        self.assertIsNone(decision.max_false_positive_rate)
        self.assertIn("temporal_health_lookup", decision.tool_names)
        self.assertIn("degradation_metrics_lookup", decision.tool_names)
        self.assertIn("tool:temporal_health_lookup", decision.evidence_refs)
        self.assertIn("metric:mean_lead_time_to_failure", decision.evidence_refs)
        self.assertIn("pico", decision.operational_assessment)
        self.assertIn("rul_not_estimated", decision.temporal_guardrail_checks)
        self.assertIn("F1", " ".join(decision.temporal_debate_points))
        self.assertIn("run-to-failure", decision.evaluation.summary)
        self.assertIn("no son oficiales", " ".join(decision.evaluation.limitations))

    def test_llm_temporal_evaluator_accepts_operational_audit(self):
        state = _temporal_state("run-evaluator-nasa-temporal-llm-001")
        client = FakeLLMClient(
            {
                "agent_name": "evaluator",
                "decision_id": "run-evaluator-nasa-temporal-llm-001:evaluator:001",
                "rationale": "Approve with temporal operational caveats.",
                "confidence": 0.88,
                "evaluation": {
                    "approved": True,
                    "summary": "Run-to-failure approved by temporal metrics.",
                    "next_action": "continue",
                    "limitations": [
                        "Temporal proxy labels are not official per-window ground truth.",
                        "RUL is not estimated in this run.",
                    ],
                },
                "min_recall_required": None,
                "max_false_positive_rate": None,
                "tool_names": [
                    "temporal_health_lookup",
                    "degradation_metrics_lookup",
                ],
                "evidence_refs": [
                    "tool:temporal_health_lookup",
                    "tool:degradation_metrics_lookup",
                    "temporal:first_persistent_alert",
                    "temporal:isolated_alert_points",
                    "metric:mean_lead_time_to_failure",
                    "metric:mean_false_alarm_rate_nominal",
                    "metric:mean_score_trend_spearman",
                    "label_source:temporal_proxy",
                ],
                "operational_assessment": (
                    "Detection is operationally defendible with caveats: an "
                    "isolated pico is not failure, aviso sostenido matters, RUL "
                    "is not estimated and proxy labels are not official."
                ),
                "temporal_debate_points": [
                    "Separar pico aislado de aviso sostenido antes de interpretar riesgo.",
                    "Falsas alarmas nominales son bajas para el protocolo local.",
                    "Las etiquetas proxy no son oficiales por ventana.",
                    "F1 queda como metrica auxiliar, no principal.",
                ],
                "temporal_guardrail_checks": [
                    "isolated_spike_not_failure",
                    "sustained_alert_required",
                    "rul_not_estimated",
                    "proxy_labels_not_official",
                    "f1_auxiliary_only",
                ],
            }
        )

        decision = decide_evaluation_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertTrue(decision.evaluation.approved)
        self.assertEqual(decision.confidence, 0.88)
        self.assertIn("degradation_metrics_lookup", decision.tool_names)
        self.assertIn("RUL", decision.operational_assessment)

    def test_llm_temporal_evaluator_rejects_missing_operational_guardrails(self):
        state = _temporal_state("run-evaluator-nasa-temporal-bad-guardrails-001")
        client = FakeLLMClient(
            {
                "agent_name": "evaluator",
                "decision_id": (
                    "run-evaluator-nasa-temporal-bad-guardrails-001:evaluator:001"
                ),
                "rationale": "Approve without temporal debate.",
                "confidence": 0.95,
                "evaluation": {
                    "approved": True,
                    "summary": "Approved.",
                    "next_action": "continue",
                    "limitations": [],
                },
                "min_recall_required": None,
                "max_false_positive_rate": None,
                "tool_names": ["degradation_metrics_lookup"],
                "evidence_refs": ["tool:degradation_metrics_lookup"],
                "operational_assessment": "Looks good.",
                "temporal_debate_points": [],
                "temporal_guardrail_checks": [],
            }
        )

        decision = decide_evaluation_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertTrue(decision.evaluation.approved)
        self.assertLessEqual(decision.confidence, 0.7)
        self.assertIn("Fallback after LLM failure", decision.rationale)
        self.assertIn("temporal_health_lookup", decision.tool_names)

    def test_llm_temporal_evaluator_receives_tool_catalog_in_prompt(self):
        state = _temporal_state("run-evaluator-nasa-temporal-prompt-001")
        client = FakeLLMClient(
            {
                "agent_name": "evaluator",
                "decision_id": "run-evaluator-nasa-temporal-prompt-001:evaluator:001",
                "rationale": "Invalid on purpose to inspect prompt.",
                "confidence": 0.95,
                "evaluation": {
                    "approved": True,
                    "summary": "Approved.",
                    "next_action": "continue",
                    "limitations": [],
                },
                "min_recall_required": 0.9,
                "max_false_positive_rate": 0.1,
            }
        )

        decide_evaluation_action(state, llm_client=client, use_llm=True)

        prompt = client.messages[1].content
        self.assertIn("Herramientas agenticas disponibles", prompt)
        self.assertIn("temporal_health_lookup", prompt)
        self.assertIn("degradation_metrics_lookup", prompt)
        self.assertIn("operational_assessment", prompt)
        self.assertIn("temporal_guardrail_checks", prompt)

    def test_llm_temporal_evaluator_cannot_use_binary_threshold_fields(self):
        state_dict = create_initial_cwru_state(
            thread_id="nasa-evaluator-temporal-test",
            run_id="run-evaluator-nasa-temporal-invalid-001",
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
        state_dict["metrics"] = MetricsReport(
            extra={
                "degradation_available": True,
                "degradation_detected_before_failure_rate": 1.0,
                "degradation_mean_lead_time_to_failure": 100.0,
                "degradation_mean_false_alarm_rate_nominal": 0.0,
                "degradation_mean_score_trend_spearman": 0.7,
            },
        ).model_dump(mode="json")
        state = validate_state(state_dict)
        client = FakeLLMClient(
            {
                "agent_name": "evaluator",
                "decision_id": "run-evaluator-nasa-temporal-invalid-001:evaluator:001",
                "rationale": "Incorrectly keeps binary threshold fields.",
                "confidence": 0.92,
                "evaluation": {
                    "approved": True,
                    "summary": "Approved with temporal metrics.",
                    "next_action": "continue",
                    "limitations": ["Temporal proxy labels."],
                },
                "min_recall_required": 0.9,
                "max_false_positive_rate": 0.1,
            }
        )

        decision = decide_evaluation_action(state, llm_client=client, use_llm=True)

        self.assertEqual(client.calls, 1)
        self.assertTrue(decision.evaluation.approved)
        self.assertIsNone(decision.min_recall_required)
        self.assertIn("Fallback after LLM failure", decision.rationale)

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

    def test_evaluator_memory_query_targets_evaluator(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-evaluator-test",
            run_id="run-evaluator-memory-query-001",
        )
        state_dict["metrics"] = MetricsReport(
            recall=0.82,
            f1_score=0.78,
            false_positive_rate=0.12,
        ).model_dump(mode="json")
        state = validate_state(state_dict)

        query = build_evaluator_memory_query(state, top_k=4, min_similarity=0.2)

        self.assertEqual(query.target_agent, "evaluator")
        self.assertEqual(query.top_k, 4)
        self.assertEqual(query.min_similarity, 0.2)
        self.assertIn("metric trade-offs", query.query_text)
        self.assertEqual(query.decision_context["recall"], 0.82)

    def test_llm_evaluator_receives_and_declares_memory_context(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-evaluator-test",
            run_id="run-evaluator-memory-001",
        )
        state_dict["metrics"] = MetricsReport(
            recall=0.82,
            f1_score=0.78,
            false_positive_rate=0.12,
        ).model_dump(mode="json")
        state = validate_state(state_dict)
        memory_context = _evaluator_memory_context(state.run_id)
        client = FakeLLMClient(
            {
                "agent_name": "evaluator",
                "decision_id": "run-evaluator-memory-001:evaluator:001",
                "rationale": "Use prior evaluation evidence as caution, but reject by thresholds.",
                "confidence": 0.9,
                "evaluation": {
                    "approved": False,
                    "summary": "Completed but not approved because recall and FPR do not satisfy the local protocol.",
                    "next_action": "continue",
                    "limitations": [
                        "Prior memory supports caution; current metrics remain insufficient."
                    ],
                },
                "min_recall_required": 0.9,
                "max_false_positive_rate": 0.1,
                "memory_context_id": memory_context.context_id,
                "used_memory_context": True,
                "memory_record_ids": ["memory-evaluator-tradeoff-001"],
                "memory_usage_summary": "Use memory as methodological caution.",
                "memory_record_uses": [
                    {
                        "memory_record_id": "memory-evaluator-tradeoff-001",
                        "usage": "adapted",
                        "influence_summary": "The memory reinforces checking recall and FPR together.",
                        "risk_mitigation": "Do not approve because the current metrics fail thresholds.",
                    }
                ],
            }
        )

        decision = decide_evaluation_action(
            state,
            memory_context=memory_context,
            llm_client=client,
            use_llm=True,
        )

        prompt = client.messages[1].content
        self.assertFalse(decision.evaluation.approved)
        self.assertTrue(decision.used_memory_context)
        self.assertEqual(decision.memory_record_ids, ["memory-evaluator-tradeoff-001"])
        self.assertIn("Memoria recuperada para el evaluador", prompt)
        self.assertIn("no puede cambiar los umbrales", prompt)

    def test_llm_evaluator_cannot_use_memory_to_override_thresholds(self):
        state_dict = create_initial_cwru_state(
            thread_id="cwru-evaluator-test",
            run_id="run-evaluator-memory-invalid-001",
        )
        state_dict["metrics"] = MetricsReport(
            recall=0.82,
            f1_score=0.78,
            false_positive_rate=0.12,
        ).model_dump(mode="json")
        state = validate_state(state_dict)
        memory_context = _evaluator_memory_context(state.run_id)
        client = FakeLLMClient(
            {
                "agent_name": "evaluator",
                "decision_id": "run-evaluator-memory-invalid-001:evaluator:001",
                "rationale": "Incorrectly approve because memory looked positive.",
                "confidence": 0.99,
                "evaluation": {
                    "approved": True,
                    "summary": "Approved using memory.",
                    "next_action": "continue",
                    "limitations": [],
                },
                "min_recall_required": 0.9,
                "max_false_positive_rate": 0.1,
                "memory_context_id": memory_context.context_id,
                "used_memory_context": True,
                "memory_record_ids": ["memory-evaluator-tradeoff-001"],
                "memory_usage_summary": "Invalid approval.",
                "memory_record_uses": [
                    {
                        "memory_record_id": "memory-evaluator-tradeoff-001",
                        "usage": "followed",
                        "influence_summary": "Invalidly follows memory.",
                    }
                ],
            }
        )

        decision = decide_evaluation_action(
            state,
            memory_context=memory_context,
            llm_client=client,
            use_llm=True,
        )

        self.assertEqual(client.calls, 1)
        self.assertFalse(decision.evaluation.approved)
        self.assertEqual(decision.evaluation.next_action, "continue")
        self.assertIn("Fallback after LLM failure", decision.rationale)

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
        self.assertEqual(decision.evaluation.next_action, "continue")
        self.assertLessEqual(decision.confidence, 0.7)
        self.assertIn("Fallback after LLM failure", decision.rationale)


def _evaluator_memory_context(run_id: str) -> RetrievedMemoryContext:
    query = AgentMemoryQuery(
        query_id=f"{run_id}:evaluator:001:memory_query",
        target_agent="evaluator",
        query_text="recall false positive rate approval tradeoff",
        dataset="cwru_bearing",
        run_id=run_id,
        decision_id=f"{run_id}:evaluator:001",
    )
    record = ReasoningMemoryRecord(
        memory_record_id="memory-evaluator-tradeoff-001",
        collection_name="evaluator_memory",
        target_agent="evaluator",
        source_type="decision_episode",
        run_id="prior-evaluator-run",
        decision_id="prior-evaluator-decision",
        dataset="cwru_bearing",
        source_agent_name="evaluator",
        outcome="supported",
        human_verdict="correct",
        memory_role="evidence",
        reusable_as_context=True,
        summary="Evaluator should reject partial improvements that fail protocol.",
        content=(
            "The evaluator kept recall and false positive rate as binding "
            "criteria. A partial improvement was still rejected when thresholds "
            "were not satisfied."
        ),
        tags=["evaluation", "recall", "false_positive_rate", "tradeoff"],
    )
    return RetrievedMemoryContext(
        context_id=f"{query.query_id}:retrieved_memory_context",
        query=query,
        items=[
            RetrievedMemoryItem(
                record=record,
                similarity=0.87,
                retrieval_use="evidence_context",
                rank=1,
            )
        ],
        retrieval_backend="test",
        embedding_model="local_hash_embedding",
    )


def _temporal_state(run_id: str):
    state_dict = create_initial_cwru_state(
        thread_id="nasa-evaluator-temporal-test",
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
    ).model_dump(mode="json")
    state_dict["metrics"] = MetricsReport(
        recall=0.42,
        f1_score=0.50,
        false_positive_rate=0.40,
        extra={
            "metric_families": "binary_classification, run_to_failure_degradation",
            "degradation_available": True,
            "degradation_detected_before_failure_rate": 1.0,
            "degradation_mean_lead_time_to_failure": 300.0,
            "degradation_mean_false_alarm_rate_nominal": 0.0,
            "degradation_mean_score_trend_spearman": 0.9,
        },
    ).model_dump(mode="json")
    return validate_state(state_dict)


if __name__ == "__main__":
    unittest.main()
