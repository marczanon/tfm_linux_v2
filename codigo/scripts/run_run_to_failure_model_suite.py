"""Ejecuta la suite canonica run-to-failure con el runner comun."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codigo.app.graph.pipeline import PipelineMemoryConfig
from codigo.app.services.experiment_protocol import (
    DEFAULT_RUN_TO_FAILURE_EXPERIMENTS_DIR,
    DEFAULT_RUN_TO_FAILURE_PLAN_ID,
    DEFAULT_RUN_TO_FAILURE_POLICY_ID,
    DEFAULT_RUN_TO_FAILURE_V2_PLAN_ID,
    ExperimentExecutionManifest,
    RUN_TO_FAILURE_CAUSAL_V2_REPORTED_METRICS,
    RUN_TO_FAILURE_MODEL_FAMILIES,
    default_run_to_failure_model_suite_plan,
    run_run_to_failure_experiment_plan,
)
from codigo.app.services.llm import OllamaJSONClient
from codigo.app.services.llm_agents import build_ollama_pipeline_agents
from codigo.app.services.nasa_ims_temporal_policy import (
    NASA_IMS_RUN_TO_FAILURE_POLICY_V2,
    NASA_IMS_TEMPORAL_POLICY_V1,
)
from codigo.app.services.reasoning_memory_index import DEFAULT_MEMORY_DIR
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR
from codigo.app.services.vector_memory import (
    DEFAULT_OLLAMA_EMBEDDING_MODEL,
    LocalHashEmbeddingModel,
    OllamaEmbeddingProvider,
    get_default_vector_memory_store,
)


DEFAULT_RUN_TO_FAILURE_V1_RAW_PATH = (
    "codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen"
)
DEFAULT_RUN_TO_FAILURE_V2_RAW_PATH = (
    "codigo/data/raw/nasa_ims_bearing/official/2nd_test"
)


def main() -> None:
    args = _parse_args()
    raw_path = _effective_raw_path(args)
    plan = default_run_to_failure_model_suite_plan(
        plan_id=_effective_plan_id(args),
        dataset_policy_id=args.dataset_policy_id,
        model_families=_parse_model_families(args.model_family),
    )
    plan = plan.model_copy(
        update={"execution_manifest": _execution_manifest(args)},
        deep=True,
    )
    if args.plan_only:
        print(json.dumps(plan.model_dump(mode="json"), indent=2, ensure_ascii=True))
        return

    result = run_run_to_failure_experiment_plan(
        plan,
        raw_path=raw_path,
        experiments_dir=args.experiments_dir,
        runs_dir=args.runs_dir,
        memory_config=_memory_config(args),
        agents=_agents(args),
        use_llm=args.use_llm,
    )
    print(json.dumps(_summary(result, args, raw_path), indent=2, ensure_ascii=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--plan-id",
        default=None,
        help=(
            "Identificador del plan. Si se omite se usa el id v1 historico o "
            "un id v2 separado segun --dataset-policy-id."
        ),
    )
    parser.add_argument(
        "--dataset-policy-id",
        choices=[NASA_IMS_TEMPORAL_POLICY_V1, NASA_IMS_RUN_TO_FAILURE_POLICY_V2],
        default=DEFAULT_RUN_TO_FAILURE_POLICY_ID,
    )
    parser.add_argument(
        "--raw-path",
        default=None,
        help=(
            "Raiz NASA IMS. Por defecto usa el piloto sintetico para v1 y el "
            "Set 2 oficial verificado para v2."
        ),
    )
    parser.add_argument(
        "--model-family",
        "--model-families",
        action="append",
        default=None,
        help=(
            "Familia a incluir; se puede repetir o pasar una lista separada "
            "por comas. Deben quedar al menos dos familias distintas."
        ),
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
        default="ollama",
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
    parser.add_argument(
        "--require-human-review-before-reuse",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    return parser.parse_args()


def _parse_model_families(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    families: list[str] = []
    for value in values:
        families.extend(
            family.strip()
            for family in value.split(",")
            if family.strip()
        )
    unique = list(dict.fromkeys(families))
    unsupported = [
        family for family in unique if family not in RUN_TO_FAILURE_MODEL_FAMILIES
    ]
    if unsupported:
        available = ", ".join(RUN_TO_FAILURE_MODEL_FAMILIES)
        raise ValueError(
            "unsupported --model-family values: "
            f"{', '.join(unsupported)}; available: {available}"
        )
    return unique


def _effective_plan_id(args: argparse.Namespace) -> str:
    if args.plan_id:
        return args.plan_id
    if args.dataset_policy_id == NASA_IMS_RUN_TO_FAILURE_POLICY_V2:
        return DEFAULT_RUN_TO_FAILURE_V2_PLAN_ID
    return DEFAULT_RUN_TO_FAILURE_PLAN_ID


def _effective_raw_path(args: argparse.Namespace) -> str:
    if args.raw_path:
        return args.raw_path
    if args.dataset_policy_id == NASA_IMS_RUN_TO_FAILURE_POLICY_V2:
        return DEFAULT_RUN_TO_FAILURE_V2_RAW_PATH
    return DEFAULT_RUN_TO_FAILURE_V1_RAW_PATH


def _execution_manifest(args: argparse.Namespace) -> ExperimentExecutionManifest:
    memory_backend = "disabled"
    if args.use_memory:
        memory_backend = os.getenv("TFM_MEMORY_BACKEND", "json").strip().lower()
        if memory_backend in {"local", "local_json"}:
            memory_backend = "json"
    return ExperimentExecutionManifest(
        llm_backend="ollama" if args.use_llm else None,
        use_llm=args.use_llm,
        llm_model=args.model if args.use_llm else None,
        llm_think=args.think if args.use_llm else None,
        llm_timeout_seconds=args.timeout_seconds if args.use_llm else None,
        use_memory=args.use_memory,
        memory_backend=memory_backend,
        memory_root=str(args.memory_dir) if args.use_memory else None,
        embedding_provider=(
            args.embedding_provider if args.use_memory else None
        ),
        embedding_model=(
            args.embedding_model
            if args.use_memory and args.embedding_provider == "ollama"
            else None
        ),
        embedding_timeout_seconds=(
            args.embedding_timeout_seconds if args.use_memory else None
        ),
        hash_dimension=(
            args.hash_dimension
            if args.use_memory and args.embedding_provider == "local_hash"
            else None
        ),
        structurer_top_k=args.structurer_top_k if args.use_memory else None,
        modeler_top_k=args.modeler_top_k if args.use_memory else None,
        evaluator_top_k=args.evaluator_top_k if args.use_memory else None,
        memory_min_similarity=(
            args.memory_min_similarity if args.use_memory else None
        ),
        generate_decision_memory=(
            not args.skip_decision_memory if args.use_memory else None
        ),
        require_human_review_before_reuse=(
            args.require_human_review_before_reuse
            if args.use_memory
            else None
        ),
    )


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


def _summary(
    result,
    args: argparse.Namespace,
    raw_path: str,
) -> dict[str, Any]:
    degradation_metrics = result.comparison.degradation_metrics
    if args.dataset_policy_id == NASA_IMS_RUN_TO_FAILURE_POLICY_V2:
        degradation_metrics = [
            metric
            for metric in degradation_metrics
            if metric.metric in RUN_TO_FAILURE_CAUSAL_V2_REPORTED_METRICS
        ]
    payload = {
        "plan_id": result.plan_id,
        "dataset_policy_id": args.dataset_policy_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "raw_path": raw_path,
        "use_llm": args.use_llm,
        "use_memory": args.use_memory,
        "plan_path": result.plan_path,
        "comparison_path": result.comparison_path,
        "results_table_path": result.results_table_path,
        "run_ids": [run.run_id for run in result.runs],
        "degradation_best_by_metric": [
            metric.model_dump(mode="json")
            for metric in degradation_metrics
        ],
    }
    if args.dataset_policy_id != NASA_IMS_RUN_TO_FAILURE_POLICY_V2:
        payload["binary_auxiliary_best_by_metric"] = [
            metric.model_dump(mode="json")
            for metric in result.comparison.metrics
        ]
    else:
        payload["binary_metrics_reported"] = False
    return payload


if __name__ == "__main__":
    main()
