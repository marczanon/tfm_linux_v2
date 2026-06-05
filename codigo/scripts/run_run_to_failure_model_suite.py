"""Ejecuta la suite canonica run-to-failure con el runner comun."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codigo.app.graph.pipeline import PipelineMemoryConfig
from codigo.app.services.experiment_protocol import (
    DEFAULT_RUN_TO_FAILURE_EXPERIMENTS_DIR,
    DEFAULT_RUN_TO_FAILURE_PLAN_ID,
    default_run_to_failure_model_suite_plan,
    run_run_to_failure_experiment_plan,
)
from codigo.app.services.llm import OllamaJSONClient
from codigo.app.services.llm_agents import build_ollama_pipeline_agents
from codigo.app.services.reasoning_memory_index import DEFAULT_MEMORY_DIR
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR
from codigo.app.services.vector_memory import (
    DEFAULT_OLLAMA_EMBEDDING_MODEL,
    LocalHashEmbeddingModel,
    OllamaEmbeddingProvider,
    get_default_vector_memory_store,
)


def main() -> None:
    args = _parse_args()
    plan = default_run_to_failure_model_suite_plan(plan_id=args.plan_id)
    if args.plan_only:
        print(json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=True))
        return

    result = run_run_to_failure_experiment_plan(
        plan,
        raw_path=args.raw_path,
        experiments_dir=args.experiments_dir,
        runs_dir=args.runs_dir,
        memory_config=_memory_config(args),
        agents=_agents(args),
        use_llm=args.use_llm,
    )
    print(json.dumps(_summary(result, args), indent=2, ensure_ascii=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan-id", default=DEFAULT_RUN_TO_FAILURE_PLAN_ID)
    parser.add_argument(
        "--raw-path",
        default="codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen",
    )
    parser.add_argument(
        "--experiments-dir",
        type=Path,
        default=DEFAULT_RUN_TO_FAILURE_EXPERIMENTS_DIR,
    )
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--use-llm", action="store_true")
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--think", action="store_true")
    parser.add_argument("--use-memory", action="store_true")
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
    parser.add_argument("--structurer-top-k", type=int, default=3)
    parser.add_argument("--modeler-top-k", type=int, default=3)
    parser.add_argument("--evaluator-top-k", type=int, default=3)
    parser.add_argument("--memory-min-similarity", type=float, default=0.0)
    parser.add_argument("--skip-decision-memory", action="store_true")
    parser.add_argument("--require-human-review-before-reuse", action="store_true")
    return parser.parse_args()


def _memory_config(args: argparse.Namespace) -> PipelineMemoryConfig | None:
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
        output_root=Path("codigo/reports"),
        structurer_top_k=args.structurer_top_k,
        modeler_top_k=args.modeler_top_k,
        evaluator_top_k=args.evaluator_top_k,
        min_similarity=args.memory_min_similarity,
        generate_decision_memory=not args.skip_decision_memory,
        reusable_as_context=not args.require_human_review_before_reuse,
    )


def _agents(args: argparse.Namespace):
    if not args.use_llm:
        return None
    client = OllamaJSONClient(
        model=args.model,
        timeout_seconds=args.timeout_seconds,
        think=args.think,
    )
    return build_ollama_pipeline_agents(client)


def _summary(result, args: argparse.Namespace) -> dict[str, Any]:
    return {
        "plan_id": result.plan_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "raw_path": args.raw_path,
        "use_llm": args.use_llm,
        "use_memory": args.use_memory,
        "plan_path": result.plan_path,
        "comparison_path": result.comparison_path,
        "results_table_path": result.results_table_path,
        "run_ids": [run.run_id for run in result.runs],
        "degradation_best_by_metric": [
            metric.model_dump(mode="json")
            for metric in result.comparison.degradation_metrics
        ],
        "binary_auxiliary_best_by_metric": [
            metric.model_dump(mode="json")
            for metric in result.comparison.metrics
        ],
    }


if __name__ == "__main__":
    main()
