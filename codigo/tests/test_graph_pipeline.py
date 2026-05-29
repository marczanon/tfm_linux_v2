import json
import tempfile
import unittest
from pathlib import Path

from codigo.app.graph.pipeline import (
    PipelineAgents,
    PipelineExecutors,
    PipelineMemoryConfig,
    run_and_persist_cwru_pipeline,
    run_cwru_pipeline,
)
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.agent_decisions import EvaluationDecision, StructuringDecision
from codigo.app.schemas.executor_results import (
    CleaningResult,
    EvaluationExecutorResult,
    ManifestResult,
    ModelingResult,
    ProfileResult,
    ReportExecutorResult,
    StructuringResult,
)
from codigo.app.schemas.reasoning import (
    AgentMemoryQuery,
    ReasoningMemoryRecord,
    RetrievedMemoryContext,
    RetrievedMemoryItem,
)
from codigo.app.schemas.state import ArtifactRef, PipelineError
from codigo.app.services.agent_runtime import AgentRuntimeRecorder
from codigo.app.services.run_persistence import load_run_index


class GraphPipelineTests(unittest.TestCase):
    def test_supervised_graph_runs_executors_in_order_and_updates_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            calls: list[str] = []
            paths = _paths(base)
            executors = _successful_executors(paths, calls)
            state = create_initial_cwru_state(
                thread_id="cwru-graph-test",
                run_id="run-001",
                raw_path=str(base / "raw"),
            )

            final_state = run_cwru_pipeline(state, executors)
            validated = validate_state(final_state)

        self.assertEqual(
            calls,
            [
                "manifest",
                "profile",
                "cleaning",
                "structuring",
                "modeling",
                "evaluation",
                "reporting",
            ],
        )
        self.assertEqual(validated.current_stage, "completed")
        self.assertIsNone(validated.next_node)
        self.assertEqual(validated.manifest_path, str(paths["manifest"]))
        self.assertEqual(validated.profile_path, str(paths["profile"]))
        self.assertEqual(validated.clean_path, str(paths["clean_dir"]))
        self.assertEqual(validated.tensor_path, str(paths["tensors"]))
        self.assertEqual(validated.splits_path, str(paths["splits"]))
        self.assertEqual(validated.dataset_profile.n_files, 2)
        self.assertEqual(validated.metrics.f1_score, 0.8)
        self.assertEqual(validated.cleaning_config.strategy_id, "cwru_clean_v1")
        self.assertEqual(validated.structuring_config.window_size, 2048)
        self.assertEqual(validated.modeling_config.model_name, "isolation_forest")
        self.assertTrue(validated.evaluation.approved)
        self.assertEqual(validated.evaluation.next_action, "continue")
        self.assertEqual(validated.report_path, str(paths["final_report"]))
        self.assertEqual(len(validated.messages), 24)
        self.assertEqual(
            [message.role for message in validated.messages],
            [
                "supervisor",
                "tool",
                "supervisor",
                "tool",
                "supervisor",
                "agent",
                "supervisor",
                "tool",
                "supervisor",
                "agent",
                "supervisor",
                "tool",
                "supervisor",
                "agent",
                "supervisor",
                "tool",
                "supervisor",
                "tool",
                "supervisor",
                "agent",
                "supervisor",
                "agent",
                "tool",
                "supervisor",
            ],
        )
        self.assertEqual(
            [message.name for message in validated.messages if message.role == "agent"],
            ["cleaner", "structurer", "modeler", "evaluator", "report_writer"],
        )
        first_decision = json.loads(validated.messages[0].content)
        final_decision = json.loads(validated.messages[-1].content)
        self.assertEqual(first_decision["next_node"], "manifest_executor")
        self.assertEqual(final_decision["next_stage"], "completed")
        self.assertIn("report generated", final_decision["stop_reason"])
        self.assertEqual(validated.errors, [])
        self.assertEqual(
            [artifact.artifact_type for artifact in validated.artifacts],
            [
                "manifest",
                "profile",
                "clean_signals",
                "features",
                "tensors",
                "splits",
                "model",
                "predictions",
                "metrics",
                "report",
                "report",
            ],
        )

    def test_memory_aware_graph_writes_structurer_and_evaluator_memory_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            calls: list[str] = []
            paths = _paths(base)
            executors = _successful_executors(paths, calls)
            memory_output = base / "reports"
            state = create_initial_cwru_state(
                thread_id="cwru-graph-memory-test",
                run_id="run-memory-001",
                raw_path=str(base / "raw"),
            )
            agents = PipelineAgents(
                structurer=_memory_aware_structurer,
                evaluator=_memory_aware_evaluator,
            )

            final_state = run_cwru_pipeline(
                state,
                executors=executors,
                agents=agents,
                memory_config=PipelineMemoryConfig(
                    memory_store=_FakeMemoryStore(),
                    output_root=memory_output,
                    reusable_as_context=True,
                ),
            )
            validated = validate_state(final_state)
            artifacts_by_name = {artifact.name: artifact for artifact in validated.artifacts}
            structurer_candidate_exists = Path(
                artifacts_by_name["structurer_memory_candidate"].path
            ).exists()
            evaluator_candidate_exists = Path(
                artifacts_by_name["evaluator_memory_candidate"].path
            ).exists()

        self.assertEqual(validated.current_stage, "completed")
        self.assertIn("structurer_retrieved_memory_context", artifacts_by_name)
        self.assertIn("structurer_decision_episode", artifacts_by_name)
        self.assertIn("structurer_memory_candidate", artifacts_by_name)
        self.assertIn("evaluator_retrieved_memory_context", artifacts_by_name)
        self.assertIn("evaluator_decision_episode", artifacts_by_name)
        self.assertIn("evaluator_memory_candidate", artifacts_by_name)
        self.assertTrue(structurer_candidate_exists)
        self.assertTrue(evaluator_candidate_exists)
        structurer_decision = json.loads(
            [
                message.content
                for message in validated.messages
                if message.role == "agent" and message.name == "structurer"
            ][-1]
        )
        evaluator_decision = json.loads(
            [
                message.content
                for message in validated.messages
                if message.role == "agent" and message.name == "evaluator"
            ][-1]
        )
        self.assertTrue(structurer_decision["used_memory_context"])
        self.assertTrue(evaluator_decision["used_memory_context"])
        self.assertEqual(
            structurer_decision["memory_record_ids"],
            ["memory-structurer-001"],
        )
        self.assertEqual(
            evaluator_decision["memory_record_ids"],
            ["memory-evaluator-001"],
        )

    def test_runtime_recorder_receives_observable_agent_events(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            calls: list[str] = []
            events = []
            paths = _paths(base)
            executors = _successful_executors(paths, calls)
            state = create_initial_cwru_state(
                thread_id="cwru-runtime-test",
                run_id="run-runtime-001",
                raw_path=str(base / "raw"),
            )
            recorder = AgentRuntimeRecorder("run-runtime-001", events.append)

            final_state = run_cwru_pipeline(
                state,
                executors=executors,
                runtime_recorder=recorder,
            )
            validated = validate_state(final_state)

        kinds = [event.kind for event in events]
        agent_events = [
            event
            for event in events
            if event.kind == "agent_decision" and event.agent_name == "modeler"
        ]
        self.assertEqual(validated.current_stage, "completed")
        self.assertEqual([event.sequence for event in events], list(range(1, len(events) + 1)))
        self.assertIn("supervisor_decision", kinds)
        self.assertIn("agent_decision", kinds)
        self.assertIn("executor_result", kinds)
        self.assertIn("memory_retrieval", kinds)
        self.assertTrue(agent_events)
        self.assertIn("rationale", agent_events[0].payload["decision"])
        self.assertEqual(agent_events[0].payload["state"]["dataset"], "cwru_bearing")

    def test_failed_executor_stops_graph_without_calling_later_nodes(self):
        calls: list[str] = []

        def manifest(**_kwargs):
            calls.append("manifest")
            error = PipelineError(
                stage="dataset_manifest",
                node="manifest_executor",
                message="manifest failed",
            )
            return ManifestResult(
                executor_name="dataset_manifest",
                status="failed",
                message="manifest failed",
                artifacts=[],
                errors=[error],
                state_updates={},
                manifest_path="unused.csv",
                n_rows=0,
                label_counts={"normal": 0, "fault": 0},
            )

        def unexpected(**_kwargs):
            calls.append("unexpected")
            raise AssertionError("graph should have stopped")

        state = create_initial_cwru_state(
            thread_id="cwru-graph-test",
            run_id="run-002",
        )
        final_state = run_cwru_pipeline(
            state,
            PipelineExecutors(
                manifest=manifest,
                profile=unexpected,
                cleaning=unexpected,
                structuring=unexpected,
                modeling=unexpected,
                evaluation=unexpected,
            ),
        )
        validated = validate_state(final_state)

        self.assertEqual(calls, ["manifest"])
        self.assertEqual(validated.current_stage, "failed")
        self.assertIsNone(validated.next_node)
        self.assertEqual(validated.errors[0].message, "manifest failed")
        self.assertEqual(
            [message.role for message in validated.messages],
            ["supervisor", "tool", "supervisor"],
        )
        final_decision = json.loads(validated.messages[-1].content)
        self.assertEqual(final_decision["next_stage"], "failed")
        self.assertEqual(final_decision["stop_reason"], "manifest failed")

    def test_persisted_wrapper_runs_pipeline_and_writes_snapshot(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            calls: list[str] = []
            paths = _paths(base)
            runs_dir = base / "runs"
            executors = _successful_executors(paths, calls)
            state = create_initial_cwru_state(
                thread_id="cwru-graph-persisted-test",
                run_id="run-persisted-001",
                raw_path=str(base / "raw"),
            )

            result = run_and_persist_cwru_pipeline(
                state,
                executors=executors,
                runs_dir=runs_dir,
            )
            validated = validate_state(result.state)
            index = load_run_index(runs_dir)
            state_path_exists = Path(result.snapshot.state_path).exists()
            summary_path_exists = Path(result.snapshot.summary_path).exists()

        self.assertEqual(
            calls,
            [
                "manifest",
                "profile",
                "cleaning",
                "structuring",
                "modeling",
                "evaluation",
                "reporting",
            ],
        )
        self.assertEqual(validated.current_stage, "completed")
        self.assertEqual(result.snapshot.run_id, "run-persisted-001")
        self.assertEqual(result.snapshot.n_artifacts, 11)
        self.assertEqual(result.snapshot.n_decisions, 17)
        self.assertEqual(result.snapshot.n_errors, 0)
        self.assertTrue(state_path_exists)
        self.assertTrue(summary_path_exists)
        self.assertEqual(index.runs[0].run_id, "run-persisted-001")
        self.assertEqual(index.runs[0].f1_score, 0.8)


def _paths(base: Path) -> dict[str, Path]:
    return {
        "manifest": base / "interim" / "manifest.csv",
        "profile": base / "interim" / "profile.json",
        "clean_dir": base / "processed" / "clean_signals",
        "features": base / "tensors" / "windows_features.csv",
        "tensors": base / "tensors" / "windows_raw.npz",
        "splits": base / "tensors" / "splits.json",
        "model": base / "models" / "isolation_forest.joblib",
        "predictions": base / "models" / "predictions.csv",
        "metrics": base / "reports" / "evaluation" / "metrics.json",
        "report": base / "reports" / "evaluation" / "evaluation_summary.md",
        "final_report": base / "reports" / "final_report.md",
    }


def _successful_executors(paths: dict[str, Path], calls: list[str]) -> PipelineExecutors:
    def manifest(raw_dir: str):
        calls.append("manifest")
        self_path = paths["manifest"]
        self_path.parent.mkdir(parents=True, exist_ok=True)
        self_path.write_text("file_id,label\n97,normal\n105,fault\n", encoding="utf-8")
        return ManifestResult(
            executor_name="dataset_manifest",
            status="success",
            message="manifest ok",
            artifacts=[
                ArtifactRef(
                    name="manifest",
                    artifact_type="manifest",
                    path=str(self_path),
                    producer="manifest_executor",
                )
            ],
            errors=[],
            state_updates={"manifest_path": str(self_path)},
            manifest_path=str(self_path),
            n_rows=2,
            label_counts={"normal": 1, "fault": 1},
        )

    def profile(manifest_path: str):
        calls.append("profile")
        self_path = paths["profile"]
        self_path.parent.mkdir(parents=True, exist_ok=True)
        self_path.write_text(
            json.dumps(
                {
                    "dataset": "cwru_bearing",
                    "manifest_path": manifest_path,
                    "generated_at": "2026-05-16T00:00:00+00:00",
                    "n_files": 2,
                    "label_counts": {"normal": 1, "fault": 1},
                    "sample_rate_counts": {"12000": 2},
                    "channels_detected": ["DE_time"],
                }
            ),
            encoding="utf-8",
        )
        return ProfileResult(
            executor_name="data_profiler",
            status="success",
            message="profile ok",
            artifacts=[
                ArtifactRef(
                    name="profile",
                    artifact_type="profile",
                    path=str(self_path),
                    producer="profiler_executor",
                )
            ],
            errors=[],
            state_updates={"profile_path": str(self_path)},
            profile_path=str(self_path),
            n_files_profiled=2,
        )

    def cleaning(manifest_path: str, profile_path: str, config):
        calls.append("cleaning")
        self_path = paths["clean_dir"]
        self_path.mkdir(parents=True, exist_ok=True)
        return CleaningResult(
            executor_name="cleaning",
            status="success",
            message="cleaning ok",
            artifacts=[
                ArtifactRef(
                    name="clean",
                    artifact_type="clean_signals",
                    path=str(self_path),
                    producer="cleaning_executor",
                    metadata={"strategy_id": config.strategy_id},
                )
            ],
            errors=[],
            state_updates={"clean_path": str(self_path)},
            clean_path=str(self_path),
            n_files_cleaned=2,
        )

    def structuring(clean_dir: str, config):
        calls.append("structuring")
        paths["features"].parent.mkdir(parents=True, exist_ok=True)
        paths["features"].write_text("window_id,split,label,target,mean\nw0,train,normal,0,0.0\n")
        return StructuringResult(
            executor_name="structuring",
            status="success",
            message="structuring ok",
            artifacts=[
                ArtifactRef(
                    name="features",
                    artifact_type="features",
                    path=str(paths["features"]),
                    producer="structuring_executor",
                    metadata={"window_size": config.window_size},
                ),
                ArtifactRef(
                    name="tensors",
                    artifact_type="tensors",
                    path=str(paths["tensors"]),
                    producer="structuring_executor",
                ),
                ArtifactRef(
                    name="splits",
                    artifact_type="splits",
                    path=str(paths["splits"]),
                    producer="structuring_executor",
                ),
            ],
            errors=[],
            state_updates={
                "tensor_path": str(paths["tensors"]),
                "splits_path": str(paths["splits"]),
            },
            features_path=str(paths["features"]),
            tensors_path=str(paths["tensors"]),
            splits_path=str(paths["splits"]),
            n_windows=1,
        )

    def modeling(features_path: str, config):
        calls.append("modeling")
        assert features_path == str(paths["features"])
        return ModelingResult(
            executor_name="modeling",
            status="success",
            message="modeling ok",
            artifacts=[
                ArtifactRef(
                    name="model",
                    artifact_type="model",
                    path=str(paths["model"]),
                    producer="modeling_executor",
                    metadata={"model_name": config.model_name},
                ),
                ArtifactRef(
                    name="predictions",
                    artifact_type="predictions",
                    path=str(paths["predictions"]),
                    producer="modeling_executor",
                ),
            ],
            errors=[],
            state_updates={},
            model_path=str(paths["model"]),
            predictions_path=str(paths["predictions"]),
        )

    def evaluation(predictions_path: str):
        calls.append("evaluation")
        assert predictions_path == str(paths["predictions"])
        paths["metrics"].parent.mkdir(parents=True, exist_ok=True)
        paths["metrics"].write_text(
            json.dumps(
                {
                    "primary_split": "test",
                    "primary_metrics": {
                        "precision": 0.75,
                        "recall": 0.9,
                        "f1_score": 0.8,
                        "roc_auc": 0.95,
                        "pr_auc": 0.96,
                        "false_positive_rate": 0.1,
                    },
                    "n_predictions": 10,
                }
            ),
            encoding="utf-8",
        )
        return EvaluationExecutorResult(
            executor_name="evaluation",
            status="success",
            message="evaluation ok",
            artifacts=[
                ArtifactRef(
                    name="metrics",
                    artifact_type="metrics",
                    path=str(paths["metrics"]),
                    producer="evaluator",
                ),
                ArtifactRef(
                    name="report",
                    artifact_type="report",
                    path=str(paths["report"]),
                    producer="evaluator",
                ),
            ],
            errors=[],
            state_updates={"metrics_path": str(paths["metrics"])},
            metrics_path=str(paths["metrics"]),
            report_fragment_path=str(paths["report"]),
        )

    def reporting(state, decision):
        calls.append("reporting")
        paths["final_report"].parent.mkdir(parents=True, exist_ok=True)
        paths["final_report"].write_text("# Informe final\n", encoding="utf-8")
        return ReportExecutorResult(
            executor_name="report_writer",
            status="success",
            message="reporting ok",
            artifacts=[
                ArtifactRef(
                    name="final_report",
                    artifact_type="report",
                    path=str(paths["final_report"]),
                    producer="report_writer",
                    metadata={"decision_id": decision.decision_id},
                )
            ],
            errors=[],
            state_updates={"report_path": str(paths["final_report"])},
            report_path=str(paths["final_report"]),
        )

    return PipelineExecutors(
        manifest=manifest,
        profile=profile,
        cleaning=cleaning,
        structuring=structuring,
        modeling=modeling,
        evaluation=evaluation,
        reporting=reporting,
    )


class _FakeMemoryStore:
    def query(self, query: AgentMemoryQuery) -> RetrievedMemoryContext:
        record = _memory_record(query)
        return RetrievedMemoryContext(
            context_id=f"{query.query_id}:retrieved_memory_context",
            query=query,
            items=[
                RetrievedMemoryItem(
                    record=record,
                    similarity=0.91,
                    retrieval_use="evidence_context",
                    rank=1,
                )
            ],
            retrieval_backend="fake_memory_store",
            embedding_model="fake_embedding:v1",
        )


def _memory_record(query: AgentMemoryQuery) -> ReasoningMemoryRecord:
    collection_by_agent = {
        "structurer": "structurer_memory",
        "evaluator": "evaluator_memory",
    }
    return ReasoningMemoryRecord(
        memory_record_id=f"memory-{query.target_agent}-001",
        collection_name=collection_by_agent[query.target_agent],
        target_agent=query.target_agent,
        source_type="decision_episode",
        source_path="codigo/reports/example/memory_candidate.json",
        run_id="historic-run",
        decision_id="historic-decision",
        dataset=query.dataset,
        source_agent_name=query.target_agent,
        outcome="supported",
        memory_role="evidence",
        reusable_as_context=True,
        summary=f"Historic evidence for {query.target_agent}.",
        content=f"Use this prior {query.target_agent} decision as cautious evidence.",
        tags=["test_memory"],
    )


def _memory_aware_structurer(
    state,
    *,
    memory_context: RetrievedMemoryContext | None = None,
) -> StructuringDecision:
    memory_id = memory_context.items[0].record.memory_record_id
    return StructuringDecision(
        decision_id=f"{state.run_id}:structurer:001",
        rationale="Use the supported default structure and cite retrieved memory.",
        confidence=0.9,
        structuring_config={
            "window_size": 2048,
            "overlap": 0.5,
            "main_channel": "DE_time",
            "target_sample_rate_hz": 12000,
            "label_mode": "binary_anomaly",
            "features": ["mean", "std", "rms", "energy"],
        },
        expected_features_path="codigo/data/tensors/cwru_bearing/windows_features.csv",
        expected_tensors_path="codigo/data/tensors/cwru_bearing/windows_raw.npz",
        expected_splits_path="codigo/data/tensors/cwru_bearing/splits.json",
        memory_context_id=memory_context.context_id,
        used_memory_context=True,
        memory_record_ids=[memory_id],
        memory_usage_summary="Adapt prior structuring evidence without changing guards.",
        memory_record_uses=[
            {
                "memory_record_id": memory_id,
                "usage": "adapted",
                "influence_summary": "Use the memory as evidence for supported windows.",
                "risk_mitigation": "Keep supported window size, overlap and channel.",
            }
        ],
    )


def _memory_aware_evaluator(
    state,
    *,
    memory_context: RetrievedMemoryContext | None = None,
) -> EvaluationDecision:
    memory_id = memory_context.items[0].record.memory_record_id
    return EvaluationDecision(
        decision_id=f"{state.run_id}:evaluator:001",
        rationale="Approve only because metrics satisfy the local protocol.",
        confidence=0.93,
        evaluation={
            "approved": True,
            "summary": "Metrics satisfy recall and FPR requirements.",
            "next_action": "continue",
            "limitations": ["Memory is supporting context, not approval authority."],
        },
        min_recall_required=0.9,
        max_false_positive_rate=0.1,
        memory_context_id=memory_context.context_id,
        used_memory_context=True,
        memory_record_ids=[memory_id],
        memory_usage_summary="Use prior evaluator evidence as a methodological reminder.",
        memory_record_uses=[
            {
                "memory_record_id": memory_id,
                "usage": "adapted",
                "influence_summary": "The memory supports documenting the same thresholds.",
                "risk_mitigation": "Approval still depends only on current metrics.",
            }
        ],
    )


if __name__ == "__main__":
    unittest.main()
