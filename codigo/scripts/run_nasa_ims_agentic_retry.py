"""Bounded agentic retry loop for the synthetic NASA IMS benchmark."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codigo.app.agents.evaluator import decide_evaluation_action
from codigo.app.agents.modeler import (
    decide_modeling_retry_action,
    retrieve_modeler_retry_memory_context,
)
from codigo.app.executors.evaluation import generate_evaluation_report
from codigo.app.executors.modeling import generate_model_outputs
from codigo.app.schemas.agent_decisions import ModelingRetryDecision
from codigo.app.schemas.reasoning import RetrievedMemoryContext
from codigo.app.schemas.state import (
    ArtifactRef,
    EvaluationResult,
    HumanApproval,
    MetricsReport,
    PipelineError,
    StateMessage,
    TFMStateModel,
)
from codigo.app.services.reasoning_memory_index import DEFAULT_MEMORY_DIR
from codigo.app.services.iteration_analysis import (
    generate_prediction_failure_analysis,
)
from codigo.app.services.llm import OllamaJSONClient
from codigo.app.services.memory_usage_audit import (
    build_modeling_retry_memory_usage_audit,
    write_memory_usage_audit,
)
from codigo.app.services.decision_memory import (
    build_modeling_retry_decision_episode,
    build_modeling_retry_memory_candidate,
    write_decision_memory_artifacts,
)
from codigo.app.services.reasoning_audit import (
    build_modeling_retry_postmortem,
    write_reasoning_postmortem,
)
from codigo.app.services.run_persistence import (
    DEFAULT_RUNS_DIR,
    load_run_snapshot,
    save_run_snapshot,
)
from codigo.app.services.run_registry import compare_runs
from codigo.app.services.vector_memory import (
    DEFAULT_OLLAMA_EMBEDDING_MODEL,
    LocalHashEmbeddingModel,
    OllamaEmbeddingProvider,
    VectorMemoryStore,
    get_default_vector_memory_store,
)


MIN_RECALL_REQUIRED = 0.90
MAX_FALSE_POSITIVE_RATE = 0.10


def main() -> None:
    args = _parse_args()
    client = OllamaJSONClient(
        model=args.model,
        timeout_seconds=args.timeout_seconds,
        think=args.think,
    )
    source_state = _load_state(args.source_run_id, Path(args.runs_dir))
    result = run_agentic_retry_loop(
        source_state,
        run_id_prefix=args.run_id_prefix,
        llm_client=client,
        max_attempts=args.max_attempts,
        runs_dir=Path(args.runs_dir),
        request_human_review=args.request_human_review,
        reviewer_hint=args.reviewer,
        memory_store=_memory_store_from_args(args) if args.use_memory else None,
        memory_top_k=args.memory_top_k,
        memory_min_similarity=args.memory_min_similarity,
    )
    print(json.dumps(result, indent=2, ensure_ascii=True))


def run_agentic_retry_loop(
    source_state: TFMStateModel,
    *,
    run_id_prefix: str,
    llm_client: OllamaJSONClient,
    max_attempts: int,
    runs_dir: Path,
    request_human_review: bool = False,
    reviewer_hint: str | None = None,
    memory_store: VectorMemoryStore | None = None,
    memory_top_k: int = 3,
    memory_min_similarity: float = 0.0,
) -> dict[str, Any]:
    """Runs at most ``max_attempts`` retries chosen by the modeler agent."""

    previous_state = source_state
    final_state = source_state
    stop_reason = "not_started"
    generated_run_ids: list[str] = []
    decisions: list[dict[str, Any]] = []
    reports: list[str] = []

    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    for attempt_number in range(1, max_attempts + 1):
        retry_run_id = f"{run_id_prefix}-attempt-{attempt_number:02d}"
        analysis_artifacts = _failure_analysis_for_state(
            previous_state,
            retry_run_id=retry_run_id,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
        )
        reports.append(analysis_artifacts.report_path)
        memory_context = None
        memory_context_path = None
        if memory_store is not None:
            memory_context = retrieve_modeler_retry_memory_context(
                previous_state,
                failure_analysis=analysis_artifacts.analysis,
                source_run_id=previous_state.run_id,
                attempt_number=attempt_number,
                max_attempts=max_attempts,
                memory_store=memory_store,
                top_k=memory_top_k,
                min_similarity=memory_min_similarity,
            )
            memory_context_path = _write_memory_context(
                retry_run_id,
                memory_context,
            )
        decision = decide_modeling_retry_action(
            previous_state,
            failure_analysis=analysis_artifacts.analysis,
            source_run_id=previous_state.run_id,
            attempt_number=attempt_number,
            max_attempts=max_attempts,
            memory_context=memory_context,
            llm_client=llm_client,
            use_llm=True,
        )
        decisions.append(decision.model_dump(mode="json"))
        if not decision.should_retry:
            stop_state = _state_for_stop_decision(
                previous_state,
                retry_run_id=retry_run_id,
                decision=decision,
                analysis_artifacts=analysis_artifacts,
                memory_context_path=memory_context_path,
                memory_context=memory_context,
            )
            snapshot = save_run_snapshot(stop_state, runs_dir)
            generated_run_ids.append(snapshot.run_id)
            final_state = stop_state
            stop_reason = "agent_stop"
            break

        retry_state = _execute_retry_attempt(
            previous_state,
            retry_run_id=retry_run_id,
            decision=decision,
            analysis_artifacts=analysis_artifacts,
            llm_client=llm_client,
            request_human_review=request_human_review,
            reviewer_hint=reviewer_hint,
            memory_context_path=memory_context_path,
            memory_context=memory_context,
        )
        snapshot = save_run_snapshot(retry_state, runs_dir)
        generated_run_ids.append(snapshot.run_id)
        if retry_state.report_path:
            reports.append(retry_state.report_path)
        if retry_state.evaluation is not None and retry_state.evaluation.approved:
            final_state = retry_state
            stop_reason = "approved"
            previous_state = retry_state
            break
        final_state = retry_state
        previous_state = retry_state
    else:
        stop_reason = "max_attempts_exhausted"

    comparison_path = _write_comparison(source_state.run_id, generated_run_ids, runs_dir)
    return {
        "source_run_id": source_state.run_id,
        "generated_run_ids": generated_run_ids,
        "decisions": decisions,
        "reports": reports,
        "comparison_path": comparison_path,
        "stop_reason": stop_reason,
        "approved": final_state.evaluation.approved if final_state.evaluation else False,
        "final_run_id": final_state.run_id,
        "finished_at": datetime.now(UTC).isoformat(),
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--source-run-id", default="nasa-ims-synth-agentic-qwen-fase3")
    parser.add_argument(
        "--run-id-prefix",
        default="nasa-ims-synth-agentic-qwen-fase3-retry",
    )
    parser.add_argument("--max-attempts", type=int, default=2)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--think", action="store_true")
    parser.add_argument("--runs-dir", default="codigo/reports/runs")
    parser.add_argument("--request-human-review", action="store_true")
    parser.add_argument("--reviewer", default=None)
    parser.add_argument("--use-memory", action="store_true")
    parser.add_argument("--memory-dir", default=DEFAULT_MEMORY_DIR.as_posix())
    parser.add_argument("--memory-top-k", type=int, default=3)
    parser.add_argument("--memory-min-similarity", type=float, default=0.0)
    parser.add_argument(
        "--embedding-provider",
        choices=["ollama", "local_hash"],
        default="ollama",
    )
    parser.add_argument("--embedding-model", default=DEFAULT_OLLAMA_EMBEDDING_MODEL)
    parser.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    parser.add_argument("--embedding-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--hash-dimension", type=int, default=128)
    return parser.parse_args()


def _memory_store_from_args(args: argparse.Namespace) -> VectorMemoryStore:
    provider = (
        LocalHashEmbeddingModel(dimension=args.hash_dimension)
        if args.embedding_provider == "local_hash"
        else OllamaEmbeddingProvider(
            model=args.embedding_model,
            host=args.ollama_host,
            timeout_seconds=args.embedding_timeout_seconds,
        )
    )
    return get_default_vector_memory_store(
        Path(args.memory_dir),
        embedding_model=provider,
    )


def _load_state(run_id: str, runs_dir: Path) -> TFMStateModel:
    snapshot = load_run_snapshot(run_id, runs_dir)
    return TFMStateModel.model_validate(_read_json(snapshot.state_path))


def _failure_analysis_for_state(
    state: TFMStateModel,
    *,
    retry_run_id: str,
    attempt_number: int,
    max_attempts: int,
):
    predictions_path = _artifact_path(state, "predictions")
    if predictions_path is None:
        raise ValueError(f"run {state.run_id} has no predictions artifact")
    metrics_path = None if state.metrics is None else state.metrics.metrics_path
    modeling_summary_path = _artifact_by_name(state, "modeling_summary")
    if modeling_summary_path is None:
        modeling_summary_path = _artifact_by_name(state, "cwru_modeling_summary")
    output_dir = Path("codigo/reports/nasa_ims_bearing") / retry_run_id / "iteration"
    return generate_prediction_failure_analysis(
        predictions_path,
        output_dir,
        metrics_path=metrics_path,
        modeling_summary_path=modeling_summary_path,
        min_recall_required=MIN_RECALL_REQUIRED,
        max_false_positive_rate=MAX_FALSE_POSITIVE_RATE,
        attempt_number=attempt_number,
        max_attempts=max_attempts,
    )


def _write_memory_context(
    retry_run_id: str,
    memory_context: RetrievedMemoryContext,
) -> str:
    output_dir = Path("codigo/reports/nasa_ims_bearing") / retry_run_id / "iteration"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "retrieved_memory_context.json"
    path.write_text(
        json.dumps(memory_context.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    return path.as_posix()


def _execute_retry_attempt(
    previous_state: TFMStateModel,
    *,
    retry_run_id: str,
    decision: ModelingRetryDecision,
    analysis_artifacts: Any,
    llm_client: OllamaJSONClient,
    request_human_review: bool = False,
    reviewer_hint: str | None = None,
    memory_context_path: str | None = None,
    memory_context: RetrievedMemoryContext | None = None,
) -> TFMStateModel:
    if decision.retry_config is None:
        raise ValueError("retry_config is required to execute retry attempt")
    features_path = _artifact_path(previous_state, "features")
    if features_path is None:
        raise ValueError(f"run {previous_state.run_id} has no features artifact")

    model_dir = Path("codigo/models/nasa_ims_bearing") / retry_run_id
    evaluation_dir = Path("codigo/reports/nasa_ims_bearing") / retry_run_id / "evaluation"
    modeling_result = generate_model_outputs(
        features_path=features_path,
        output_dir=model_dir,
        config=decision.retry_config,
    )
    if modeling_result.status != "success" or modeling_result.predictions_path is None:
        return _state_for_failed_attempt(
            previous_state,
            retry_run_id=retry_run_id,
            decision=decision,
            analysis_artifacts=analysis_artifacts,
            memory_context_path=memory_context_path,
            errors=modeling_result.errors,
            artifacts=modeling_result.artifacts,
        )

    evaluation_result = generate_evaluation_report(
        modeling_result.predictions_path,
        evaluation_dir,
    )
    metrics = _metrics_from_path(evaluation_result.metrics_path)
    state_before_eval = _base_retry_state(
        previous_state,
        retry_run_id=retry_run_id,
        decision=decision,
        analysis_artifacts=analysis_artifacts,
        memory_context_path=memory_context_path,
        artifacts=[*modeling_result.artifacts, *evaluation_result.artifacts],
        metrics=metrics,
        errors=evaluation_result.errors,
    )
    evaluation_decision = decide_evaluation_action(
        state_before_eval,
        llm_client=llm_client,
        use_llm=True,
    )
    effective_evaluation = _effective_evaluation(
        evaluation_decision.evaluation,
        decision=decision,
    )
    final_stage = "completed" if effective_evaluation.approved else "failed"
    iteration_dir = Path("codigo/reports/nasa_ims_bearing") / retry_run_id / "iteration"
    postmortem = build_modeling_retry_postmortem(
        source_run_id=previous_state.run_id,
        run_id=retry_run_id,
        decision=decision,
        before_metrics=previous_state.metrics,
        after_metrics=state_before_eval.metrics,
        evaluation=effective_evaluation,
        request_human_review=request_human_review,
    )
    reasoning_artifacts = write_reasoning_postmortem(
        postmortem,
        iteration_dir,
        request_human_review=request_human_review,
        reviewer_hint=reviewer_hint,
    )
    memory_usage_artifacts = None
    if memory_context is not None or decision.used_memory_context:
        memory_usage_audit = build_modeling_retry_memory_usage_audit(
            run_id=retry_run_id,
            decision=decision,
            memory_context=memory_context,
            before_metrics=previous_state.metrics,
            after_metrics=state_before_eval.metrics,
        )
        memory_usage_artifacts = write_memory_usage_audit(
            memory_usage_audit,
            iteration_dir,
        )
    decision_episode = build_modeling_retry_decision_episode(
        source_run_id=previous_state.run_id,
        run_id=retry_run_id,
        decision=decision,
        postmortem=postmortem,
        before_metrics=previous_state.metrics,
        after_metrics=state_before_eval.metrics,
        evaluation=effective_evaluation,
        memory_context=memory_context,
        data_provenance=previous_state.project_context.data_provenance,
        project_context=previous_state.project_context,
    )
    memory_candidate = build_modeling_retry_memory_candidate(
        decision_episode,
        reusable_as_context=not request_human_review,
    )
    decision_memory_artifacts = write_decision_memory_artifacts(
        episode=decision_episode,
        candidate=memory_candidate,
        output_dir=iteration_dir,
    )
    report_path = _write_iteration_report(
        previous_state,
        state_before_eval,
        decision,
        analysis_artifacts,
        evaluation=effective_evaluation,
        reasoning_report_path=reasoning_artifacts.report_path,
        review_report_path=reasoning_artifacts.review_report_path,
        memory_context_path=memory_context_path,
        memory_usage_report_path=(
            None
            if memory_usage_artifacts is None
            else memory_usage_artifacts.report_path
        ),
        decision_episode_report_path=decision_memory_artifacts.episode_report_path,
        memory_candidate_report_path=decision_memory_artifacts.candidate_report_path,
    )

    payload = state_before_eval.to_langgraph_state()
    payload["current_stage"] = final_stage
    payload["evaluation"] = effective_evaluation.model_dump(mode="json")
    payload["report_path"] = report_path
    payload["artifacts"] = [
        *payload["artifacts"],
        ArtifactRef(
            name="agentic_reasoning_postmortem",
            artifact_type="log",
            path=reasoning_artifacts.postmortem_path,
            producer="modeler",
            metadata={"source_run_id": previous_state.run_id},
        ).model_dump(mode="json"),
        ArtifactRef(
            name="agentic_reasoning_postmortem_report",
            artifact_type="report",
            path=reasoning_artifacts.report_path,
            producer="modeler",
            metadata={"source_run_id": previous_state.run_id},
        ).model_dump(mode="json"),
        *(
            [
                ArtifactRef(
                    name="human_reasoning_review_request",
                    artifact_type="log",
                    path=reasoning_artifacts.review_request_path,
                    producer="human_review",
                    metadata={"postmortem_id": postmortem.postmortem_id},
                ).model_dump(mode="json"),
                ArtifactRef(
                    name="human_reasoning_review_request_report",
                    artifact_type="report",
                    path=reasoning_artifacts.review_report_path,
                    producer="human_review",
                    metadata={"postmortem_id": postmortem.postmortem_id},
                ).model_dump(mode="json"),
                ArtifactRef(
                    name="human_reasoning_review_template",
                    artifact_type="config",
                    path=reasoning_artifacts.review_template_path,
                    producer="human_review",
                    metadata={"postmortem_id": postmortem.postmortem_id},
                ).model_dump(mode="json"),
            ]
            if request_human_review
            and reasoning_artifacts.review_request_path is not None
            and reasoning_artifacts.review_report_path is not None
            and reasoning_artifacts.review_template_path is not None
            else []
        ),
        ArtifactRef(
            name="agentic_retry_report",
            artifact_type="report",
            path=report_path,
            producer="modeler",
            metadata={"source_run_id": previous_state.run_id},
        ).model_dump(mode="json"),
        ArtifactRef(
            name="decision_episode",
            artifact_type="log",
            path=decision_memory_artifacts.episode_path,
            producer="modeler",
            metadata={"source_run_id": previous_state.run_id},
        ).model_dump(mode="json"),
        ArtifactRef(
            name="decision_episode_report",
            artifact_type="report",
            path=decision_memory_artifacts.episode_report_path,
            producer="modeler",
            metadata={"source_run_id": previous_state.run_id},
        ).model_dump(mode="json"),
        ArtifactRef(
            name="memory_candidate",
            artifact_type="log",
            path=decision_memory_artifacts.candidate_path,
            producer="modeler",
            metadata={
                "source_run_id": previous_state.run_id,
                "reusable_as_context": memory_candidate.reusable_as_context,
            },
        ).model_dump(mode="json"),
        ArtifactRef(
            name="memory_candidate_report",
            artifact_type="report",
            path=decision_memory_artifacts.candidate_report_path,
            producer="modeler",
            metadata={"source_run_id": previous_state.run_id},
        ).model_dump(mode="json"),
        *(
            [
                ArtifactRef(
                    name="memory_usage_audit",
                    artifact_type="log",
                    path=memory_usage_artifacts.audit_path,
                    producer="modeler",
                    metadata={"source_run_id": previous_state.run_id},
                ).model_dump(mode="json"),
                ArtifactRef(
                    name="memory_usage_audit_report",
                    artifact_type="report",
                    path=memory_usage_artifacts.report_path,
                    producer="modeler",
                    metadata={"source_run_id": previous_state.run_id},
                ).model_dump(mode="json"),
            ]
            if memory_usage_artifacts is not None
            else []
        ),
    ]
    payload["messages"] = [
        *payload["messages"],
        StateMessage(
            role="agent",
            name="evaluator",
            content=evaluation_decision.model_dump_json(),
        ).model_dump(mode="json"),
    ]
    if request_human_review:
        payload["human_approval"] = HumanApproval(
            required=True,
            approved=None,
            reviewer=reviewer_hint,
            reason=(
                "Human review requested for agent reasoning postmortem before "
                "reusing this decision as memory or RAG context."
            ),
        ).model_dump(mode="json")
    else:
        payload["human_approval"] = None
    return TFMStateModel.model_validate(payload)


def _effective_evaluation(
    evaluation: EvaluationResult,
    *,
    decision: ModelingRetryDecision,
) -> EvaluationResult:
    if evaluation.approved or decision.attempt_number < decision.max_attempts:
        return evaluation

    limitations = [
        *evaluation.limitations,
        (
            "Retry budget exhausted after "
            f"{decision.attempt_number}/{decision.max_attempts} attempts; "
            "the loop stops to avoid unbounded tuning."
        ),
    ]
    return evaluation.model_copy(
        update={
            "next_action": "stop",
            "summary": (
                f"{evaluation.summary} Se detiene el ciclo porque se ha "
                "agotado el numero maximo de reintentos."
            ),
            "limitations": limitations,
        }
    )


def _state_for_failed_attempt(
    previous_state: TFMStateModel,
    *,
    retry_run_id: str,
    decision: ModelingRetryDecision,
    analysis_artifacts: Any,
    memory_context_path: str | None = None,
    errors: list[PipelineError],
    artifacts: list[ArtifactRef],
) -> TFMStateModel:
    return _base_retry_state(
        previous_state,
        retry_run_id=retry_run_id,
        decision=decision,
        analysis_artifacts=analysis_artifacts,
        memory_context_path=memory_context_path,
        artifacts=artifacts,
        metrics=None,
        errors=errors,
        current_stage="failed",
    )


def _state_for_stop_decision(
    previous_state: TFMStateModel,
    *,
    retry_run_id: str,
    decision: ModelingRetryDecision,
    analysis_artifacts: Any,
    memory_context_path: str | None = None,
    memory_context: RetrievedMemoryContext | None = None,
) -> TFMStateModel:
    output_dir = Path("codigo/reports/nasa_ims_bearing") / retry_run_id / "iteration"
    memory_usage_artifacts = None
    if memory_context is not None or decision.used_memory_context:
        memory_usage_audit = build_modeling_retry_memory_usage_audit(
            run_id=retry_run_id,
            decision=decision,
            memory_context=memory_context,
            before_metrics=previous_state.metrics,
            after_metrics=previous_state.metrics,
        )
        memory_usage_artifacts = write_memory_usage_audit(
            memory_usage_audit,
            output_dir,
        )
    report_path = _write_stop_report(
        previous_state,
        retry_run_id,
        decision,
        analysis_artifacts,
        memory_context_path=memory_context_path,
        memory_usage_report_path=(
            None
            if memory_usage_artifacts is None
            else memory_usage_artifacts.report_path
        ),
    )
    state = _base_retry_state(
        previous_state,
        retry_run_id=retry_run_id,
        decision=decision,
        analysis_artifacts=analysis_artifacts,
        memory_context_path=memory_context_path,
        artifacts=[
            ArtifactRef(
                name="agentic_retry_stop_report",
                artifact_type="report",
                path=report_path,
                producer="modeler",
                metadata={"source_run_id": previous_state.run_id},
            ),
            *(
                [
                    ArtifactRef(
                        name="memory_usage_audit",
                        artifact_type="log",
                        path=memory_usage_artifacts.audit_path,
                        producer="modeler",
                        metadata={"source_run_id": previous_state.run_id},
                    ),
                    ArtifactRef(
                        name="memory_usage_audit_report",
                        artifact_type="report",
                        path=memory_usage_artifacts.report_path,
                        producer="modeler",
                        metadata={"source_run_id": previous_state.run_id},
                    ),
                ]
                if memory_usage_artifacts is not None
                else []
            ),
        ],
        metrics=previous_state.metrics,
        errors=[],
        current_stage="failed",
    )
    payload = state.to_langgraph_state()
    payload["report_path"] = report_path
    payload["evaluation"] = EvaluationResult(
        approved=False,
        summary=decision.stop_reason or "Retry stopped by modeler.",
        next_action="stop",
        limitations=[decision.learning_summary],
    ).model_dump(mode="json")
    return TFMStateModel.model_validate(payload)


def _base_retry_state(
    previous_state: TFMStateModel,
    *,
    retry_run_id: str,
    decision: ModelingRetryDecision,
    analysis_artifacts: Any,
    memory_context_path: str | None = None,
    artifacts: list[ArtifactRef],
    metrics: MetricsReport | None,
    errors: list[PipelineError],
    current_stage: str = "evaluation",
) -> TFMStateModel:
    source_artifacts = [
        artifact
        for artifact in previous_state.artifacts
        if artifact.artifact_type
        in {"manifest", "profile", "clean_signals", "features", "tensors", "splits"}
    ]
    payload = previous_state.model_dump(mode="json")
    payload.update(
        {
            "thread_id": f"{retry_run_id}-thread",
            "run_id": retry_run_id,
            "current_stage": current_stage,
            "next_node": None,
            "modeling_config": None
            if decision.retry_config is None
            else decision.retry_config.model_dump(mode="json"),
            "metrics": None if metrics is None else metrics.model_dump(mode="json"),
            "evaluation": None,
            "errors": [error.model_dump(mode="json") for error in errors],
            "report_path": None,
            "artifacts": [
                *[artifact.model_dump(mode="json") for artifact in source_artifacts],
                ArtifactRef(
                    name="agentic_retry_failure_analysis",
                    artifact_type="log",
                    path=analysis_artifacts.analysis_path,
                    producer="modeler",
                    metadata={"source_run_id": previous_state.run_id},
                ).model_dump(mode="json"),
                ArtifactRef(
                    name="agentic_retry_failure_report",
                    artifact_type="report",
                    path=analysis_artifacts.report_path,
                    producer="modeler",
                    metadata={"source_run_id": previous_state.run_id},
                ).model_dump(mode="json"),
                *(
                    [
                        ArtifactRef(
                            name="modeler_retrieved_memory_context",
                            artifact_type="log",
                            path=memory_context_path,
                            producer="modeler",
                            metadata={"source_run_id": previous_state.run_id},
                        ).model_dump(mode="json")
                    ]
                    if memory_context_path is not None
                    else []
                ),
                *[artifact.model_dump(mode="json") for artifact in artifacts],
            ],
            "messages": [
                StateMessage(
                    role="agent",
                    name="modeler",
                    content=decision.model_dump_json(),
                ).model_dump(mode="json")
            ],
        }
    )
    return TFMStateModel.model_validate(payload)


def _metrics_from_path(path: str | None) -> MetricsReport | None:
    if path is None:
        return None
    summary = _read_json(path)
    metrics = summary.get("primary_metrics", {})
    return MetricsReport(
        metrics_path=path,
        precision=metrics.get("precision"),
        recall=metrics.get("recall"),
        f1_score=metrics.get("f1_score"),
        roc_auc=metrics.get("roc_auc"),
        pr_auc=metrics.get("pr_auc"),
        false_positive_rate=metrics.get("false_positive_rate"),
        extra={
            "primary_split": summary.get("primary_split"),
            "n_predictions": summary.get("n_predictions"),
        },
    )


def _write_iteration_report(
    previous_state: TFMStateModel,
    retry_state: TFMStateModel,
    decision: ModelingRetryDecision,
    analysis_artifacts: Any,
    evaluation: EvaluationResult | None = None,
    reasoning_report_path: str | None = None,
    review_report_path: str | None = None,
    memory_context_path: str | None = None,
    memory_usage_report_path: str | None = None,
    decision_episode_report_path: str | None = None,
    memory_candidate_report_path: str | None = None,
) -> str:
    output_dir = Path("codigo/reports/nasa_ims_bearing") / retry_state.run_id / "iteration"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "agentic_retry_report.md"
    metrics = retry_state.metrics
    lines = [
        f"# Reintento agentico {retry_state.run_id}",
        "",
        f"- Run origen: `{previous_state.run_id}`",
        f"- Decision: `{decision.decision_id}`",
        f"- Intento: `{decision.attempt_number}/{decision.max_attempts}`",
        (
            "- Reintentos restantes tras esta decision: "
            f"`{max(0, decision.max_attempts - decision.attempt_number)}`"
        ),
        f"- Reintentar: `{decision.should_retry}`",
        f"- Configuracion propuesta: `{None if decision.retry_config is None else decision.retry_config.model_dump(mode='json')}`",
        f"- Aprendizaje declarado: {decision.learning_summary}",
        f"- Efecto esperado: {decision.expected_effect}",
        f"- Analisis de fallo: `{analysis_artifacts.report_path}`",
        f"- Memoria recuperada: `{memory_context_path or 'desactivada'}`",
        f"- Memoria usada por el agente: `{decision.used_memory_context}`",
        f"- Recuerdos citados: `{decision.memory_record_ids}`",
        f"- Auditoria de memoria: `{memory_usage_report_path or 'n/a'}`",
        f"- Post-mortem de razonamiento: `{reasoning_report_path or 'n/a'}`",
        f"- Episodio de decision: `{decision_episode_report_path or 'n/a'}`",
        f"- Candidato de memoria: `{memory_candidate_report_path or 'n/a'}`",
        f"- Revision humana solicitada: `{review_report_path or 'no'}`",
        "",
        "## Metricas del reintento",
        "",
        f"- Precision: `{_metric_text(None if metrics is None else metrics.precision)}`",
        f"- Recall: `{_metric_text(None if metrics is None else metrics.recall)}`",
        f"- F1-score: `{_metric_text(None if metrics is None else metrics.f1_score)}`",
        f"- FPR: `{_metric_text(None if metrics is None else metrics.false_positive_rate)}`",
    ]
    if evaluation is not None:
        lines.extend(
            [
                "",
                "## Juicio evaluador",
                "",
                f"- Aprobada: `{evaluation.approved}`",
                f"- Resumen: {evaluation.summary}",
                f"- Siguiente accion: `{evaluation.next_action}`",
            ]
        )
        if not evaluation.approved and decision.attempt_number >= decision.max_attempts:
            lines.extend(
                [
                    "",
                    "## Cierre del bucle",
                    "",
                    (
                        "- Motivo: se alcanzo el numero maximo de reintentos "
                        "permitidos sin cumplir los umbrales."
                    ),
                    "- Siguiente accion efectiva: `stop`",
                ]
            )
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return path.as_posix()


def _write_stop_report(
    previous_state: TFMStateModel,
    retry_run_id: str,
    decision: ModelingRetryDecision,
    analysis_artifacts: Any,
    memory_context_path: str | None = None,
    memory_usage_report_path: str | None = None,
) -> str:
    output_dir = Path("codigo/reports/nasa_ims_bearing") / retry_run_id / "iteration"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "agentic_retry_stop_report.md"
    path.write_text(
        "\n".join(
            [
                f"# Parada agentica {retry_run_id}",
                "",
                f"- Run origen: `{previous_state.run_id}`",
                f"- Decision: `{decision.decision_id}`",
                f"- Motivo de parada: {decision.stop_reason}",
                f"- Aprendizaje declarado: {decision.learning_summary}",
                f"- Analisis de fallo: `{analysis_artifacts.report_path}`",
                f"- Memoria recuperada: `{memory_context_path or 'desactivada'}`",
                f"- Memoria usada por el agente: `{decision.used_memory_context}`",
                f"- Recuerdos citados: `{decision.memory_record_ids}`",
                f"- Auditoria de memoria: `{memory_usage_report_path or 'n/a'}`",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path.as_posix()


def _write_comparison(
    source_run_id: str,
    generated_run_ids: list[str],
    runs_dir: Path,
) -> str | None:
    if not generated_run_ids:
        return None
    output_dir = Path("codigo/reports/nasa_ims_bearing") / generated_run_ids[-1] / "iteration"
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "retry_comparison.json"
    comparison = compare_runs([source_run_id, *generated_run_ids], runs_dir=runs_dir)
    path.write_text(
        json.dumps(comparison.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    return path.as_posix()


def _artifact_path(state: TFMStateModel, artifact_type: str) -> str | None:
    matches = [
        artifact.path
        for artifact in state.artifacts
        if artifact.artifact_type == artifact_type
    ]
    return matches[-1] if matches else None


def _artifact_by_name(state: TFMStateModel, name: str) -> str | None:
    matches = [artifact.path for artifact in state.artifacts if artifact.name == name]
    return matches[-1] if matches else None


def _read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _metric_text(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


if __name__ == "__main__":
    main()
