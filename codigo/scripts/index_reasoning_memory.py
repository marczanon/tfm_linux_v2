"""Indexa razonamientos en el backend vectorial configurado para el TFM."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from codigo.app.services.reasoning_memory_index import (
    DEFAULT_MEMORY_DIR,
    index_reasoning_memory,
)
from codigo.app.services.vector_memory import (
    EmbeddingProvider,
    LocalHashEmbeddingModel,
    OllamaEmbeddingProvider,
    VectorMemoryStore,
    get_default_vector_memory_store,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-root", default="codigo/reports")
    parser.add_argument("--memory-dir", default=DEFAULT_MEMORY_DIR.as_posix())
    parser.add_argument("--dataset", default=None)
    parser.add_argument("--include-unreviewed", action="store_true")
    parser.add_argument("--include-memory-usage-audits", action="store_true")
    parser.add_argument("--skip-memory-candidates", action="store_true")
    parser.add_argument("--clear-existing", action="store_true")
    parser.add_argument(
        "--embedding-provider",
        choices=["ollama", "local_hash"],
        default="ollama",
    )
    parser.add_argument("--embedding-model", default="qwen3-embedding:0.6b")
    parser.add_argument("--ollama-host", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument("--hash-dimension", type=int, default=128)
    args = parser.parse_args()

    memory_store = _memory_store_from_args(args)
    result = index_reasoning_memory(
        reports_root=Path(args.reports_root),
        memory_dir=Path(args.memory_dir),
        include_unreviewed=args.include_unreviewed,
        include_memory_candidates=not args.skip_memory_candidates,
        include_memory_usage_audits=args.include_memory_usage_audits,
        dataset=args.dataset,
        memory_store=memory_store,
        clear_existing=args.clear_existing,
        write_report=True,
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2))


def _embedding_provider_from_args(args: argparse.Namespace) -> EmbeddingProvider:
    return (
        LocalHashEmbeddingModel(dimension=args.hash_dimension)
        if args.embedding_provider == "local_hash"
        else OllamaEmbeddingProvider(
            model=args.embedding_model,
            host=args.ollama_host,
            timeout_seconds=args.timeout_seconds,
        )
    )


def _memory_store_from_args(args: argparse.Namespace) -> VectorMemoryStore:
    """Respeta TFM_MEMORY_BACKEND y reutiliza el proveedor elegido por CLI."""

    return get_default_vector_memory_store(
        Path(args.memory_dir),
        embedding_model=_embedding_provider_from_args(args),
    )


if __name__ == "__main__":
    main()
