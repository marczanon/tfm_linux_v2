"""Comparacion de modelos CWRU guiada por el agente modelador."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from codigo.app.agents.modeler import decide_modeling_action
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import ArtifactRef, StructuringConfig
from codigo.app.services.experiment_protocol import (
    DEFAULT_MODEL_PLAN_ID,
    cwru_model_experiment_plan_from_decision,
    run_cwru_experiment_plan,
)
from codigo.app.services.llm import OllamaJSONClient


def main() -> None:
    args = _parse_args()
    feature_path = Path(args.features_path)
    if not feature_path.exists():
        raise SystemExit(
            f"feature table not found: {feature_path}. Run structuring first."
        )

    structuring_config = StructuringConfig(
        window_size=args.window_size,
        overlap=args.overlap,
        main_channel="DE_time",
        target_sample_rate_hz=12000,
        label_mode="binary_anomaly",
    )
    state = _modeling_state(args, feature_path, structuring_config)
    client = OllamaJSONClient(
        model=args.model,
        timeout_seconds=args.timeout_seconds,
        think=args.think,
    )
    decision = decide_modeling_action(state, llm_client=client, use_llm=True)
    plan = cwru_model_experiment_plan_from_decision(
        decision,
        plan_id=args.plan_id,
        structuring_config=structuring_config,
    )
    result = run_cwru_experiment_plan(
        plan,
        experiments_dir=args.experiments_dir,
        runs_dir=args.runs_dir,
        raw_path=args.raw_path,
    )

    print(
        json.dumps(
            {
                "plan_id": result.plan_id,
                "generated_at": datetime.now(UTC).isoformat(),
                "modeler_decision_id": decision.decision_id,
                "selected_config": decision.modeling_config.model_dump(mode="json"),
                "comparison_candidates": [
                    candidate.model_dump(mode="json")
                    for candidate in decision.comparison_candidates
                ],
                "plan_path": result.plan_path,
                "comparison_path": result.comparison_path,
                "results_table_path": result.results_table_path,
                "run_ids": [run.run_id for run in result.runs],
                "best_by_metric": [
                    metric.model_dump(mode="json")
                    for metric in result.comparison.metrics
                ],
            },
            indent=2,
            ensure_ascii=True,
        )
    )


def _modeling_state(
    args: argparse.Namespace,
    feature_path: Path,
    structuring_config: StructuringConfig,
):
    state = validate_state(
        create_initial_cwru_state(
            thread_id=f"{args.plan_id}:modeler",
            run_id=f"{args.plan_id}_agent_decision",
            raw_path=args.raw_path,
        )
    )
    payload = state.to_langgraph_state()
    payload["current_stage"] = "modeling"
    payload["next_node"] = "modeling_agent"
    payload["structuring_config"] = structuring_config.model_dump(mode="json")
    payload["tensor_path"] = str(feature_path.with_name("windows_raw.npz"))
    payload["splits_path"] = str(feature_path.with_name("splits.json"))
    payload["artifacts"] = [
        ArtifactRef(
            name="features",
            artifact_type="features",
            path=feature_path.as_posix(),
            producer="structuring_executor",
            metadata={"source": "agentic_model_comparison_context"},
        ).model_dump(mode="json")
    ]
    return validate_state(payload)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--plan-id", default=DEFAULT_MODEL_PLAN_ID)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--think", action="store_true")
    parser.add_argument("--raw-path", default="codigo/data/raw/cwru_bearing/mat")
    parser.add_argument(
        "--features-path",
        default=(
            "codigo/experiments/cwru_local/cwru-agentic-window-qwen-fase3/"
            "win_1024_ov_50_win_1024_ov_50/tensors/windows_features.csv"
        ),
    )
    parser.add_argument("--window-size", type=int, default=1024)
    parser.add_argument("--overlap", type=float, default=0.5)
    parser.add_argument(
        "--experiments-dir",
        default="codigo/experiments/cwru_local",
    )
    parser.add_argument("--runs-dir", default="codigo/reports/runs")
    return parser.parse_args()


if __name__ == "__main__":
    main()
