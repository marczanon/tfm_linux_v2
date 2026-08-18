"""Genera figuras reproducibles desde artefactos canonicos de validacion."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

from codigo.app.services.validation_figures import (
    DEFAULT_AGENT_RELIABILITY_FIGURE_NAME,
    DEFAULT_MEMORY_CORPUS_FIGURE_NAME,
    DEFAULT_MEMORY_INDEX_REPORT,
    DEFAULT_MONITORING_REVIEW_RELIABILITY_FIGURE_NAME,
    DEFAULT_MONITORING_REVIEW_RELIABILITY_OUTPUT_DIR,
    DEFAULT_OFFICIAL_RUN_METRICS,
    DEFAULT_OFFICIAL_RUN_TRAJECTORY,
    DEFAULT_RUN_TRAJECTORY_FIGURE_NAME,
    DEFAULT_VALIDATION_FIGURES_DIR,
    RunTrajectoryValidationProfile,
    render_agent_reliability_figure,
    render_memory_corpus_governance_figure,
    render_monitoring_review_reliability_figure,
    render_run_trajectory_figure,
)


def main(
    argv: Sequence[str] | None = None,
    *,
    run_trajectory_profile: RunTrajectoryValidationProfile | None = None,
) -> None:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.figure_type == "run-trajectory":
            figure_name = args.figure_name or DEFAULT_RUN_TRAJECTORY_FIGURE_NAME
            artifacts = render_run_trajectory_figure(
                snapshot_trajectory_path=args.snapshot_trajectory,
                metrics_path=args.metrics_report,
                output_dir=args.output_dir,
                figure_name=figure_name,
                validation_profile=run_trajectory_profile,
            )
            output = {
                "figure_type": args.figure_type,
                "pdf_path": artifacts.pdf_path,
                "manifest_path": artifacts.manifest_path,
                "inputs": {
                    item.input_role: item.sha256
                    for item in artifacts.manifest.inputs
                },
                "snapshot_count": (
                    artifacts.manifest.validation_summary.snapshot_count
                ),
                "partition_counts": (
                    artifacts.manifest.validation_summary.partition_counts
                ),
            }
        elif args.figure_type == "agent-reliability":
            if args.plan_dir is None:
                parser.error(
                    "--plan-dir is required for --figure-type agent-reliability"
                )
            figure_name = args.figure_name or DEFAULT_AGENT_RELIABILITY_FIGURE_NAME
            artifacts = render_agent_reliability_figure(
                plan_dir=args.plan_dir,
                output_dir=args.output_dir,
                figure_name=figure_name,
            )
            summary = artifacts.manifest.metrics
            output = {
                "figure_type": args.figure_type,
                "pdf_path": artifacts.pdf_path,
                "png_path": artifacts.png_path,
                "manifest_path": artifacts.manifest_path,
                "inputs": {
                    item.input_role: item.sha256
                    for item in artifacts.manifest.inputs
                },
                "observation_count": summary.observation_count,
                "entrypoint_count": len(summary.entrypoints),
                "outcomes": {
                    "first_pass": summary.first_pass_count,
                    "llm_repaired": summary.repaired_count,
                    "fallback": summary.fallback_count,
                    "semantic_failure": summary.semantic_failure_count,
                    "non_agentic": summary.non_agentic_count,
                    "error": summary.error_count,
                },
                "benchmark_scope": artifacts.manifest.benchmark_scope,
            }
        elif args.figure_type == "monitoring-review-reliability":
            figure_name = (
                args.figure_name
                or DEFAULT_MONITORING_REVIEW_RELIABILITY_FIGURE_NAME
            )
            artifacts = render_monitoring_review_reliability_figure(
                publication_root=args.publication_root,
                output_dir=args.output_dir,
                figure_name=figure_name,
            )
            metrics = artifacts.manifest.metrics
            output = {
                "figure_type": args.figure_type,
                "pdf_path": artifacts.pdf_path,
                "png_path": artifacts.png_path,
                "manifest_path": artifacts.manifest_path,
                "verdict": metrics.verdict,
                "blockers": list(metrics.blockers),
                "observation_count": metrics.observation_count,
                "role_count": len(metrics.roles),
                "matrix_cell_count": len(metrics.matrix),
                "coverages": {
                    item.coverage_id: item.rate for item in metrics.coverages
                },
            }
        else:
            figure_name = args.figure_name or DEFAULT_MEMORY_CORPUS_FIGURE_NAME
            artifacts = render_memory_corpus_governance_figure(
                source_report_path=args.source_report,
                output_dir=args.output_dir,
                figure_name=figure_name,
            )
            output = {
                "figure_type": args.figure_type,
                "pdf_path": artifacts.pdf_path,
                "manifest_path": artifacts.manifest_path,
                "source_sha256": artifacts.manifest.source_sha256,
                "source_record_count": artifacts.manifest.source_record_count,
                "categories": {
                    category.category_id: category.count
                    for category in artifacts.manifest.categories
                },
            }
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False,
            sort_keys=True,
        )
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--figure-type",
        choices=(
            "memory-corpus",
            "run-trajectory",
            "agent-reliability",
            "monitoring-review-reliability",
        ),
        default="memory-corpus",
        help="Producto canonico que se desea renderizar.",
    )
    parser.add_argument(
        "--source-report",
        type=Path,
        default=DEFAULT_MEMORY_INDEX_REPORT,
        help="Informe canonico reasoning_memory_index_report.json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_VALIDATION_FIGURES_DIR,
        help="Directorio para el PDF vectorial y su manifiesto JSON.",
    )
    parser.add_argument(
        "--figure-name",
        default=None,
        help="Nombre base, sin directorio ni extension.",
    )
    parser.add_argument(
        "--snapshot-trajectory",
        type=Path,
        default=DEFAULT_OFFICIAL_RUN_TRAJECTORY,
        help="CSV canonico longitudinal por snapshot.",
    )
    parser.add_argument(
        "--metrics-report",
        type=Path,
        default=DEFAULT_OFFICIAL_RUN_METRICS,
        help="metrics.json canonico asociado a la trayectoria.",
    )
    parser.add_argument(
        "--plan-dir",
        type=Path,
        default=None,
        help=(
            "Directorio de un plan agent_reliability con summary.json y "
            "observations.jsonl."
        ),
    )
    parser.add_argument(
        "--publication-root",
        type=Path,
        default=DEFAULT_MONITORING_REVIEW_RELIABILITY_OUTPUT_DIR,
        help="Raiz con current.json del gate monitoring_review_reliability.",
    )
    return parser


if __name__ == "__main__":
    main()
