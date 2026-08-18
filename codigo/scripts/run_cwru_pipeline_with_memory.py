"""Ejecucion CWRU completa con memoria RAG transversal opcional.

Este script es deliberadamente especifico de CWRU y queda como atajo canonico
para el experimento CWRU. Para entradas seleccionadas por interfaz/API debe
usarse el runner comun `run_dataset_pipeline_with_memory.py`, que aplica
adaptador y politica de dataset explicitos.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codigo.app.agents.cleaner import decide_cleaning_action
from codigo.app.agents.evaluator import decide_evaluation_action
from codigo.app.agents.modeler import decide_modeling_action
from codigo.app.agents.report_writer import decide_report_action
from codigo.app.agents.structurer import decide_structuring_action
from codigo.app.agents.supervisor import decide_supervisor_action
from codigo.app.graph.pipeline import (
    PipelineAgents,
    PipelineMemoryConfig,
    run_and_persist_cwru_pipeline,
)
from codigo.app.graph.state import create_initial_cwru_state
from codigo.app.schemas.state import TFMStateModel
from codigo.app.services.llm import OllamaJSONClient
from codigo.app.services.reasoning_memory_index import (
    DEFAULT_MEMORY_DIR,
    ReasoningMemoryIndexResult,
    index_reasoning_memory,
)
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR, extract_decisions
from codigo.app.services.vector_memory import (
    DEFAULT_OLLAMA_EMBEDDING_MODEL,
    EmbeddingProvider,
    LocalHashEmbeddingModel,
    OllamaEmbeddingProvider,
    get_default_vector_memory_store,
)


def main() -> None:
    args = _parse_args()
    _validate_cwru_only_args(args)
    embedding_provider = _embedding_provider_from_args(args)
    memory_store = get_default_vector_memory_store(
        args.memory_dir,
        embedding_model=embedding_provider,
    )
    result = run_and_persist_cwru_pipeline(
        create_initial_cwru_state(
            thread_id=f"{args.run_id}-thread",
            run_id=args.run_id,
            raw_path=args.raw_path,
        ),
        agents=_agents(args),
        runs_dir=args.runs_dir,
        memory_config=PipelineMemoryConfig(
            memory_store=memory_store,
            output_root=args.memory_output_root,
            structurer_top_k=args.structurer_top_k,
            evaluator_top_k=args.evaluator_top_k,
            min_similarity=args.memory_min_similarity,
            generate_decision_memory=not args.skip_decision_memory,
            reusable_as_context=not args.require_human_review_before_reuse,
        ),
    )
    final_state = TFMStateModel.model_validate(result.state)
    index_result = None
    if args.rebuild_index:
        index_result = index_reasoning_memory(
            reports_root=args.reports_root,
            memory_dir=args.memory_dir,
            include_unreviewed=args.include_unreviewed,
            include_memory_candidates=not args.skip_memory_candidates,
            include_memory_usage_audits=not args.skip_memory_usage_audits,
            dataset=None,
            memory_store=memory_store,
            clear_existing=args.clear_existing,
            write_report=True,
        )
    print(
        json.dumps(
            _summary(final_state, result.snapshot.snapshot_dir, index_result),
            indent=2,
            ensure_ascii=True,
        )
    )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id",
        default=f"cwru-memory-transversal-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
    )
    parser.add_argument("--raw-path", default="codigo/data/raw/cwru_bearing/mat")
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--reports-root", type=Path, default=Path("codigo/reports"))
    parser.add_argument("--memory-dir", type=Path, default=DEFAULT_MEMORY_DIR)
    parser.add_argument("--memory-output-root", type=Path, default=Path("codigo/reports"))
    parser.add_argument("--structurer-top-k", type=int, default=3)
    parser.add_argument("--evaluator-top-k", type=int, default=3)
    parser.add_argument("--memory-min-similarity", type=float, default=0.0)
    parser.add_argument("--skip-decision-memory", action="store_true")
    parser.add_argument(
        "--require-human-review-before-reuse",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    parser.add_argument("--rebuild-index", action="store_true")
    parser.add_argument("--clear-existing", action="store_true")
    parser.add_argument("--include-unreviewed", action="store_true")
    parser.add_argument("--skip-memory-candidates", action="store_true")
    parser.add_argument("--skip-memory-usage-audits", action="store_true")
    parser.add_argument(
        "--embedding-provider",
        choices=["ollama", "local_hash"],
        default="ollama",
    )
    parser.add_argument("--embedding-model", default=DEFAULT_OLLAMA_EMBEDDING_MODEL)
    parser.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    parser.add_argument("--embedding-timeout-seconds", type=float, default=60.0)
    parser.add_argument("--hash-dimension", type=int, default=128)
    parser.add_argument("--use-llm", action="store_true")
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--think", action="store_true")
    return parser.parse_args()


def _validate_cwru_only_args(args: argparse.Namespace) -> None:
    raw_path = Path(args.raw_path)
    raw_path_text = raw_path.as_posix().lower()
    raw_path_parts = {part.lower() for part in raw_path.parts}
    if "nasa" in raw_path_text or "ims" in raw_path_parts:
        raise SystemExit(
            "run_cwru_pipeline_with_memory.py is CWRU-only. "
            f"The raw path looks like NASA/IMS data: {args.raw_path}. "
            "Use run_dataset_pipeline_with_memory.py with an explicit dataset policy."
        )


def _embedding_provider_from_args(args: argparse.Namespace) -> EmbeddingProvider:
    if args.embedding_provider == "local_hash":
        return LocalHashEmbeddingModel(dimension=args.hash_dimension)
    return OllamaEmbeddingProvider(
        model=args.embedding_model,
        host=args.ollama_host,
        timeout_seconds=args.embedding_timeout_seconds,
    )


def _agents(args: argparse.Namespace) -> PipelineAgents | None:
    if not args.use_llm:
        return None
    client = OllamaJSONClient(
        model=args.model,
        timeout_seconds=args.timeout_seconds,
        think=args.think,
    )
    return PipelineAgents(
        supervisor=lambda state: decide_supervisor_action(
            state,
            llm_client=client,
            use_llm=True,
        ),
        cleaner=lambda state: decide_cleaning_action(
            state,
            llm_client=client,
            use_llm=True,
        ),
        structurer=lambda state, memory_context=None: decide_structuring_action(
            state,
            memory_context=memory_context,
            llm_client=client,
            use_llm=True,
        ),
        modeler=lambda state, memory_context=None: decide_modeling_action(
            state,
            memory_context=memory_context,
            llm_client=client,
            use_llm=True,
        ),
        evaluator=lambda state, memory_context=None: decide_evaluation_action(
            state,
            memory_context=memory_context,
            llm_client=client,
            use_llm=True,
        ),
        report_writer=lambda state: decide_report_action(
            state,
            llm_client=client,
            use_llm=True,
        ),
    )


def _summary(
    state: TFMStateModel,
    snapshot_dir: str,
    index_result: ReasoningMemoryIndexResult | None,
) -> dict[str, Any]:
    decisions = extract_decisions(state)
    memory_artifacts = [
        artifact
        for artifact in state.artifacts
        if "memory" in artifact.name or "decision_episode" in artifact.name
    ]
    payload: dict[str, Any] = {
        "run_id": state.run_id,
        "script_scope": "cwru_bearing_only",
        "dataset": state.project_context.dataset,
        "final_stage": state.current_stage,
        "approved": None if state.evaluation is None else state.evaluation.approved,
        "snapshot_dir": snapshot_dir,
        "report_path": state.report_path,
        "metrics": None if state.metrics is None else state.metrics.model_dump(mode="json"),
        "memory_artifacts": [
            {
                "name": artifact.name,
                "type": artifact.artifact_type,
                "path": artifact.path,
                "producer": artifact.producer,
            }
            for artifact in memory_artifacts
        ],
        "decisions": [
            {
                "agent": decision.get("agent_name"),
                "decision_id": decision.get("decision_id"),
                "used_memory_context": decision.get("payload", {}).get(
                    "used_memory_context"
                ),
                "memory_record_ids": decision.get("payload", {}).get(
                    "memory_record_ids"
                ),
            }
            for decision in decisions
            if decision.get("agent_name") in {"structurer", "evaluator"}
        ],
        "errors": [error.message for error in state.errors],
    }
    if index_result is not None:
        payload["index_result"] = _index_summary(index_result)
    return payload


def _index_summary(result: ReasoningMemoryIndexResult) -> dict[str, Any]:
    return {
        "memory_dir": result.memory_dir,
        "memory_backend": result.memory_backend,
        "destructive_rebuild": result.destructive_rebuild,
        "index_report_path": result.index_report_path,
        "indexed_records": len(result.indexed_records),
        "by_collection": dict(Counter(record.collection_name for record in result.indexed_records)),
        "by_source": dict(Counter(record.source_type for record in result.indexed_records)),
        "missing_reviews": len(result.missing_reviews),
        "skipped_postmortems": len(result.skipped_postmortems),
        "indexed_memory_candidates": len(result.indexed_memory_candidates),
        "skipped_memory_candidates": len(result.skipped_memory_candidates),
        "indexed_memory_usage_audits": len(result.indexed_memory_usage_audits),
        "skipped_memory_usage_audits": len(result.skipped_memory_usage_audits),
    }


if __name__ == "__main__":
    main()
