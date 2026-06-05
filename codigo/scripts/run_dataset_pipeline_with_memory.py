"""Runner comun multi-dataset con memoria opcional y politica explicita."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codigo.app.graph.pipeline import PipelineMemoryConfig
from codigo.app.schemas.pipeline_run import PipelineRunRequest
from codigo.app.schemas.state import TFMStateModel
from codigo.app.services.pipeline_runner import (
    plan_dataset_pipeline_run,
    run_dataset_pipeline,
)
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR, extract_decisions
from codigo.app.services.vector_memory import (
    DEFAULT_OLLAMA_EMBEDDING_MODEL,
    LocalHashEmbeddingModel,
    OllamaEmbeddingProvider,
    get_default_vector_memory_store,
)
from codigo.app.services.reasoning_memory_index import DEFAULT_MEMORY_DIR


def main() -> None:
    args = _parse_args()
    request = _request_from_args(args)
    plan = plan_dataset_pipeline_run(request)
    if args.plan_only:
        print(json.dumps(_plan_summary(plan), indent=2, ensure_ascii=True))
        return
    result = run_dataset_pipeline(
        request,
        runs_dir=args.runs_dir,
        memory_config=_memory_config(args, plan.paths.memory_output_root),
    )
    final_state = TFMStateModel.model_validate(result.state)
    print(
        json.dumps(
            _run_summary(final_state, result.snapshot.snapshot_dir, plan),
            indent=2,
            ensure_ascii=True,
        )
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--raw-path", required=True)
    parser.add_argument("--adapter-id", default=None)
    parser.add_argument("--dataset-policy-id", default=None)
    parser.add_argument(
        "--run-id",
        default=f"dataset-pipeline-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
    )
    parser.add_argument(
        "--execution-mode",
        choices=["full", "diagnostic"],
        default="full",
    )
    parser.add_argument("--allow-synthetic-labels", action="store_true")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--use-memory", action="store_true")
    parser.add_argument("--use-llm", action="store_true")
    parser.add_argument("--memory-dir", type=Path, default=DEFAULT_MEMORY_DIR)
    parser.add_argument(
        "--embedding-provider",
        choices=["ollama", "local_hash"],
        default="local_hash",
    )
    parser.add_argument("--embedding-model", default=DEFAULT_OLLAMA_EMBEDDING_MODEL)
    parser.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    parser.add_argument("--embedding-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--hash-dimension", type=int, default=128)
    return parser.parse_args()


def _request_from_args(args: argparse.Namespace) -> PipelineRunRequest:
    return PipelineRunRequest(
        run_id=args.run_id,
        dataset_id=args.dataset_id,
        raw_path=args.raw_path,
        adapter_id=args.adapter_id,
        dataset_policy_id=args.dataset_policy_id,
        execution_mode=args.execution_mode,
        use_memory=args.use_memory,
        use_llm=args.use_llm,
        allow_synthetic_labels=args.allow_synthetic_labels,
    )


def _memory_config(
    args: argparse.Namespace,
    output_root: str,
) -> PipelineMemoryConfig | None:
    if not args.use_memory:
        return None
    if args.embedding_provider == "ollama":
        embedding_provider = OllamaEmbeddingProvider(
            model=args.embedding_model,
            host=args.ollama_host,
            timeout_seconds=args.embedding_timeout_seconds,
        )
    else:
        embedding_provider = LocalHashEmbeddingModel(dimension=args.hash_dimension)
    return PipelineMemoryConfig(
        memory_store=get_default_vector_memory_store(
            args.memory_dir,
            embedding_model=embedding_provider,
        ),
        output_root=output_root,
    )


def _plan_summary(plan) -> dict[str, Any]:
    return {
        "run_id": plan.request.run_id,
        "dataset_id": plan.request.dataset_id,
        "adapter_id": plan.adapter_info.adapter_id,
        "dataset_policy_id": plan.request.dataset_policy_id,
        "execution_mode": plan.request.execution_mode,
        "effective_stages": plan.effective_stages,
        "can_execute_requested_stages": plan.can_execute_requested_stages,
        "blocking_reasons": plan.blocking_reasons,
        "descriptor": plan.descriptor.model_dump(mode="json"),
        "policy": plan.policy.model_dump(mode="json"),
        "paths": plan.paths.model_dump(mode="json"),
    }


def _run_summary(
    state: TFMStateModel,
    snapshot_dir: str,
    plan,
) -> dict[str, Any]:
    decisions = extract_decisions(state)
    payload = _plan_summary(plan)
    payload.update(
        {
            "final_stage": state.current_stage,
            "approved": None if state.evaluation is None else state.evaluation.approved,
            "snapshot_dir": snapshot_dir,
            "report_path": state.report_path,
            "metrics": None
            if state.metrics is None
            else state.metrics.model_dump(mode="json"),
            "errors": [error.message for error in state.errors],
            "decisions": [
                {
                    "agent": decision.get("agent_name"),
                    "decision_id": decision.get("decision_id"),
                    "confidence": decision.get("payload", {}).get("confidence"),
                }
                for decision in decisions
            ],
        }
    )
    return payload


if __name__ == "__main__":
    main()
