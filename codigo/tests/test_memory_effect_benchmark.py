import json
import tempfile
import unittest
from pathlib import Path

from codigo.app.schemas.reasoning import (
    AgentMemoryQuery,
    ReasoningMemoryRecord,
    RetrievedMemoryContext,
    RetrievedMemoryItem,
)
from codigo.app.schemas.state import (
    ArtifactRef,
    EvaluationResult,
    MetricsReport,
    ModelingConfig,
    ProjectContext,
    StateMessage,
    TFMStateModel,
)
from codigo.app.services.memory_effect_benchmark import (
    benchmark_memory_effect,
    build_memory_effect_benchmark,
)
from codigo.app.services.run_persistence import save_run_snapshot


class MemoryEffectBenchmarkTests(unittest.TestCase):
    def test_benchmark_detects_declared_memory_use_and_baseline_deltas(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            baseline = _state("memory-benchmark-baseline", model_name="isolation_forest")
            memory_run = _state(
                "memory-benchmark-with-memory",
                model_name="pca_reconstruction_error",
                used_memory=True,
                context_path=base / "context.json",
                cited_memory_id="memory-modeler-temporal-001",
            )
            save_run_snapshot(baseline, runs_dir)
            save_run_snapshot(memory_run, runs_dir)

            artifacts = benchmark_memory_effect(
                run_ids=[baseline.run_id, memory_run.run_id],
                baseline_run_id=baseline.run_id,
                runs_dir=runs_dir,
                output_dir=base / "benchmark",
                variant_labels={
                    baseline.run_id: "memory_off",
                    memory_run.run_id: "memory_full",
                },
            )
            benchmark_exists = Path(artifacts.benchmark_path).exists()
            report_exists = Path(artifacts.report_path).exists()
            report_text = Path(artifacts.report_path).read_text(encoding="utf-8")

        benchmark = artifacts.benchmark
        memory_result = [
            run for run in benchmark.runs if run.run_id == "memory-benchmark-with-memory"
        ][0]
        modeler = [
            item for item in memory_result.agents if item.agent_name == "modeler"
        ][0]

        self.assertEqual(benchmark.memory_used_run_count, 1)
        self.assertEqual(benchmark.invalid_usage_run_count, 0)
        self.assertEqual(benchmark.quality_gate_warning_run_count, 1)
        self.assertEqual(benchmark.agent_usage_counts, {"modeler": 1})
        self.assertEqual(
            benchmark.variant_counts,
            {"memory_full": 1, "memory_off": 1},
        )
        self.assertIn("La memoria hizo algo declarado", benchmark.executive_summary)
        self.assertEqual(memory_result.controlled_variant, "memory_full")
        self.assertEqual(memory_result.memory_mode, "memory_used")
        self.assertEqual(modeler.outcome, "used_aligned")
        self.assertEqual(modeler.cited_memory_record_ids, ["memory-modeler-temporal-001"])
        self.assertEqual(modeler.quality_caution_count, 1)
        self.assertEqual(modeler.quality_caution_ids, ["memory-modeler-temporal-001"])
        self.assertTrue(memory_result.effect_signals.config_changed_from_baseline)
        self.assertIn("modeling", memory_result.effect_signals.changed_config_sections)
        recall_delta = {
            item.metric: item for item in memory_result.effect_signals.metric_deltas
        }["recall"]
        self.assertEqual(recall_delta.direction, "better")
        self.assertTrue(benchmark_exists)
        self.assertTrue(report_exists)
        self.assertIn("memory-modeler-temporal-001", report_text)

    def test_benchmark_marks_unknown_citation_as_invalid_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            runs_dir = base / "runs"
            state = _state(
                "memory-benchmark-invalid",
                model_name="pca_reconstruction_error",
                used_memory=True,
                context_path=base / "context.json",
                cited_memory_id="memory-not-retrieved",
            )
            save_run_snapshot(state, runs_dir)

            benchmark = build_memory_effect_benchmark(
                run_ids=[state.run_id],
                runs_dir=runs_dir,
            )

        result = benchmark.runs[0]
        modeler = [item for item in result.agents if item.agent_name == "modeler"][0]
        self.assertEqual(result.memory_mode, "memory_usage_invalid")
        self.assertEqual(modeler.outcome, "usage_invalid")
        self.assertEqual(modeler.cited_without_retrieval, ["memory-not-retrieved"])

    def test_causal_v2_benchmark_reports_only_neutral_unlabeled_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            runs_dir = Path(tmp) / "runs"
            baseline = _state(
                "memory-benchmark-causal-off",
                model_name="pca_reconstruction_error",
                causal_v2=True,
            )
            memory_run = _state(
                "memory-benchmark-causal-on",
                model_name="pca_reconstruction_error",
                used_memory=True,
                causal_v2=True,
                context_path=Path(tmp) / "context-causal.json",
                cited_memory_id="memory-modeler-temporal-001",
            )
            save_run_snapshot(baseline, runs_dir)
            save_run_snapshot(memory_run, runs_dir)

            benchmark = build_memory_effect_benchmark(
                run_ids=[baseline.run_id, memory_run.run_id],
                baseline_run_id=baseline.run_id,
                runs_dir=runs_dir,
            )

        result = next(run for run in benchmark.runs if run.run_id == memory_run.run_id)
        metric_names = {item.metric for item in result.effect_signals.metric_deltas}
        self.assertIn("degradation_persistent_alert_run_rate", metric_names)
        self.assertIn(
            "degradation_mean_first_persistent_alert_time_to_trajectory_end",
            metric_names,
        )
        self.assertIn("degradation_mean_pre_monitoring_alert_rate", metric_names)
        self.assertNotIn("precision", metric_names)
        self.assertNotIn("recall", metric_names)
        self.assertNotIn("degradation_detected_before_failure_rate", metric_names)
        self.assertNotIn("degradation_mean_lead_time_to_failure", metric_names)


def _state(
    run_id: str,
    *,
    model_name: str,
    used_memory: bool = False,
    context_path: Path | None = None,
    cited_memory_id: str | None = None,
    causal_v2: bool = False,
) -> TFMStateModel:
    extra = {
        "degradation_detected_before_failure_rate": 1.0 if used_memory else 0.5,
        "degradation_mean_lead_time_to_failure": 1200.0 if used_memory else 600.0,
        "degradation_mean_false_alarm_rate_nominal": 0.1 if used_memory else 0.2,
        "degradation_mean_score_trend_spearman": 0.8 if used_memory else 0.4,
    }
    if causal_v2:
        extra.update(
            {
                "degradation_interpretation_mode": "causal_v2_unlabeled",
                "degradation_persistent_alert_run_rate": 1.0,
                "degradation_mean_first_persistent_alert_time_to_trajectory_end": (
                    1200.0 if used_memory else 600.0
                ),
                "degradation_mean_pre_monitoring_alert_rate": (
                    0.1 if used_memory else 0.2
                ),
            }
        )
    metrics = MetricsReport(
        precision=0.8 if used_memory else 0.75,
        recall=0.9 if used_memory else 0.7,
        f1_score=0.847 if used_memory else 0.724,
        false_positive_rate=0.1 if used_memory else 0.2,
        extra=extra,
    )
    decision = _modeler_decision(
        run_id,
        model_name=model_name,
        used_memory=used_memory,
        cited_memory_id=cited_memory_id,
        context_id=(
            f"{run_id}:modeler:001:memory_query:retrieved_memory_context"
            if context_path is not None
            else None
        ),
    )
    artifacts = []
    if context_path is not None:
        _write_context(context_path, run_id)
        artifacts.append(
            ArtifactRef(
                name="modeler_retrieved_memory_context",
                artifact_type="config",
                path=str(context_path),
                producer="modeler",
            )
        )
    return TFMStateModel(
        thread_id=f"{run_id}-thread",
        run_id=run_id,
        current_stage="completed",
        next_node=None,
        project_context=ProjectContext(
            dataset="nasa_ims_bearing",
            machine_type="rotating_machinery",
            signal_type="vibration",
            objective="run_to_failure_degradation",
            target_sample_rate_hz=20000,
            main_channel="channel_1",
            label_mode="degradation",
            supervision_profile="run_to_failure_degradation",
            label_granularity="proxy_temporal",
            label_source="none" if causal_v2 else "synthetic",
            data_provenance="official" if causal_v2 else "synthetic",
        ),
        raw_path="codigo/data/raw/nasa_ims_bearing/synthetic",
        messages=[
            StateMessage(
                role="agent",
                name="modeler",
                content=json.dumps(decision),
            )
        ],
        modeling_config=ModelingConfig(
            model_name=model_name,
            random_state=42,
            hyperparameters={"threshold_quantile": 0.99},
        ),
        metrics=metrics,
        evaluation=EvaluationResult(
            approved=True,
            summary="Synthetic benchmark evaluation.",
            next_action="continue",
        ),
        artifacts=artifacts,
    )


def _modeler_decision(
    run_id: str,
    *,
    model_name: str,
    used_memory: bool,
    cited_memory_id: str | None,
    context_id: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "agent_name": "modeler",
        "decision_id": f"{run_id}:modeler:001",
        "rationale": "Select temporal anomaly model.",
        "confidence": 0.9,
        "modeling_config": {
            "model_name": model_name,
            "random_state": 42,
            "hyperparameters": {"threshold_quantile": 0.99},
        },
        "train_split": "train",
        "validation_split": "validation",
        "expected_model_path": f"codigo/models/nasa_ims_bearing/{model_name}.joblib",
    }
    if used_memory:
        payload.update(
            {
                "memory_context_id": context_id,
                "used_memory_context": True,
                "memory_record_ids": [cited_memory_id],
                "memory_usage_summary": "Use temporal memory as evidence.",
                "memory_record_uses": [
                    {
                        "memory_record_id": cited_memory_id,
                        "usage": "adapted",
                        "influence_summary": "Require persistent alerts.",
                        "risk_mitigation": "Check lead time and false alarms.",
                    }
                ],
            }
        )
    return payload


def _write_context(path: Path, run_id: str) -> None:
    query = AgentMemoryQuery(
        query_id=f"{run_id}:modeler:001:memory_query",
        target_agent="modeler",
        query_text="run to failure memory",
        dataset="nasa_ims_bearing",
        run_id=run_id,
        decision_id=f"{run_id}:modeler:001",
    )
    record = ReasoningMemoryRecord(
        memory_record_id="memory-modeler-temporal-001",
        collection_name="modeler_memory",
        target_agent="modeler",
        source_type="decision_episode",
        run_id="historic-run",
        decision_id="historic-run:modeler:001",
        dataset="nasa_ims_bearing",
        source_agent_name="modeler",
        outcome="partially_supported",
        human_verdict="partially_correct",
        memory_role="boundary_case",
        reusable_as_context=True,
        summary="Require persistent alerts in run-to-failure.",
        content="Use sustained temporal evidence and lead time before escalation.",
        tags=["sustained_alert_required", "lead_time"],
    )
    context = RetrievedMemoryContext(
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
    path.write_text(
        json.dumps(context.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
