"""Genera un benchmark offline sobre si la memoria RAG influye en las runs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from codigo.app.services.memory_effect_benchmark import (
    MemoryControlledVariant,
    MemoryEffectBenchmarkArtifacts,
    benchmark_memory_effect,
)
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR


def main() -> None:
    args = _parse_args()
    artifacts = benchmark_memory_effect(
        run_ids=args.run_id,
        baseline_run_id=args.baseline_run_id,
        runs_dir=args.runs_dir,
        output_dir=args.output_dir,
        variant_labels=_parse_variants(args.variant),
    )
    print(json.dumps(_summary(artifacts), indent=2, ensure_ascii=True))


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--run-id",
        action="append",
        required=True,
        help="Run persistida a incluir. Puede repetirse.",
    )
    parser.add_argument(
        "--baseline-run-id",
        default=None,
        help="Run base para comparar configuraciones y metricas.",
    )
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument(
        "--variant",
        action="append",
        default=[],
        help=(
            "Etiqueta de variante controlada en formato run_id=label. "
            "Labels: baseline, memory_off, memory_full, memory_filtered, "
            "memory_conflict_excluded, retrieval_only, unknown."
        ),
    )
    return parser.parse_args()


def _parse_variants(values: list[str]) -> dict[str, MemoryControlledVariant]:
    allowed = {
        "baseline",
        "memory_off",
        "memory_full",
        "memory_filtered",
        "memory_conflict_excluded",
        "retrieval_only",
        "unknown",
    }
    variants: dict[str, MemoryControlledVariant] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"invalid variant format: {value}")
        run_id, label = value.split("=", maxsplit=1)
        if label not in allowed:
            raise ValueError(f"unsupported variant label: {label}")
        variants[run_id] = label  # type: ignore[assignment]
    return variants


def _summary(artifacts: MemoryEffectBenchmarkArtifacts) -> dict[str, Any]:
    benchmark = artifacts.benchmark
    return {
        "report_id": benchmark.report_id,
        "run_ids": benchmark.run_ids,
        "baseline_run_id": benchmark.baseline_run_id,
        "executive_summary": benchmark.executive_summary,
        "retrieval_run_count": benchmark.retrieval_run_count,
        "memory_used_run_count": benchmark.memory_used_run_count,
        "invalid_usage_run_count": benchmark.invalid_usage_run_count,
        "quality_gate_warning_run_count": benchmark.quality_gate_warning_run_count,
        "agent_usage_counts": benchmark.agent_usage_counts,
        "variant_counts": benchmark.variant_counts,
        "benchmark_path": artifacts.benchmark_path,
        "report_path": artifacts.report_path,
    }


if __name__ == "__main__":
    main()
