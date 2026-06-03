"""Migra memoria agentica JSON local a Qdrant y compara retrieval."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from codigo.app.services.memory_backend_migration import (
    migrate_local_json_memory_to_qdrant,
)
from codigo.app.services.reasoning_memory_index import DEFAULT_MEMORY_DIR
from codigo.app.services.vector_memory import (
    DEFAULT_OLLAMA_EMBEDDING_MODEL,
    DEFAULT_QDRANT_HOST,
    LocalHashEmbeddingModel,
    OllamaEmbeddingProvider,
)


def main() -> None:
    args = _parse_args()
    provider = (
        LocalHashEmbeddingModel(dimension=args.hash_dimension)
        if args.embedding_provider == "local_hash"
        else OllamaEmbeddingProvider(
            model=args.embedding_model,
            host=args.ollama_host,
            timeout_seconds=args.embedding_timeout_seconds,
        )
    )
    artifacts = migrate_local_json_memory_to_qdrant(
        memory_dir=args.memory_dir,
        qdrant_host=args.qdrant_host,
        qdrant_api_key=args.qdrant_api_key,
        embedding_provider=provider,
        clear_existing=not args.keep_existing,
        qdrant_timeout_seconds=args.qdrant_timeout_seconds,
        qdrant_distance=args.qdrant_distance,
        verification_queries=[] if args.skip_comparison else None,
        output_dir=args.output_dir,
    )
    print(json.dumps(_summary(artifacts.model_dump(mode="json")), indent=2))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--memory-dir", type=Path, default=DEFAULT_MEMORY_DIR)
    parser.add_argument("--qdrant-host", default=DEFAULT_QDRANT_HOST)
    parser.add_argument("--qdrant-api-key", default=None)
    parser.add_argument("--qdrant-timeout-seconds", type=float, default=10.0)
    parser.add_argument("--qdrant-distance", default="Cosine")
    parser.add_argument("--keep-existing", action="store_true")
    parser.add_argument("--skip-comparison", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=None)
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


def _summary(payload: dict[str, Any]) -> dict[str, Any]:
    report = payload["report"]
    comparison = report.get("comparison") or {}
    return {
        "migration_path": payload["migration_path"],
        "report_path": payload["report_path"],
        "source_backend": report["source_backend"],
        "target_backend": report["target_backend"],
        "migrated_record_count": report["migrated_record_count"],
        "collection_counts": report["collection_counts"],
        "comparison_query_count": comparison.get("query_count", 0),
        "average_overlap_ratio": comparison.get("average_overlap_ratio"),
        "exact_match_count": comparison.get("exact_match_count", 0),
    }


if __name__ == "__main__":
    main()
