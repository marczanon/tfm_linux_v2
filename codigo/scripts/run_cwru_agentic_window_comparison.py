"""Comparacion de ventanas CWRU guiada por el agente estructurador.

El script no inventa una segunda configuracion. Si el agente no propone
alternativas comparables, la ejecucion se detiene para conservar protagonismo
agentico y trazabilidad.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from codigo.app.agents.structurer import decide_structuring_action
from codigo.app.graph.state import create_initial_cwru_state, validate_state
from codigo.app.schemas.state import CleaningConfig
from codigo.app.services.experiment_protocol import (
    DEFAULT_WINDOW_PLAN_ID,
    cwru_window_experiment_plan_from_decision,
    run_cwru_experiment_plan,
)
from codigo.app.services.llm import OllamaJSONClient


def main() -> None:
    args = _parse_args()
    clean_dir = Path(args.clean_path)
    if not clean_dir.exists():
        raise SystemExit(
            f"clean CWRU signals not found: {clean_dir}. Run the CWRU pipeline first."
        )

    state = validate_state(
        create_initial_cwru_state(
            thread_id=f"{args.plan_id}:structurer",
            run_id=f"{args.plan_id}_agent_decision",
            raw_path=args.raw_path,
        )
    )
    state_payload = state.to_langgraph_state()
    state_payload["current_stage"] = "structuring"
    state_payload["next_node"] = "structuring_agent"
    state_payload["clean_path"] = clean_dir.as_posix()
    state_payload["cleaning_config"] = CleaningConfig(
        strategy_id="agentic_window_comparison_context",
        remove_non_finite=True,
        resample_to_hz=12000,
        normalization="none",
        selected_channel="DE_time",
    ).model_dump(mode="json")
    structuring_state = validate_state(state_payload)

    client = OllamaJSONClient(
        model=args.model,
        timeout_seconds=args.timeout_seconds,
        think=args.think,
    )
    decision = decide_structuring_action(
        structuring_state,
        llm_client=client,
        use_llm=True,
    )
    plan = cwru_window_experiment_plan_from_decision(decision, plan_id=args.plan_id)
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
                "structurer_decision_id": decision.decision_id,
                "selected_config": decision.structuring_config.model_dump(mode="json"),
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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument("--plan-id", default=DEFAULT_WINDOW_PLAN_ID)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--think", action="store_true")
    parser.add_argument("--raw-path", default="codigo/data/raw/cwru_bearing/mat")
    parser.add_argument(
        "--clean-path",
        default="codigo/data/processed/cwru_bearing/clean_signals",
    )
    parser.add_argument(
        "--experiments-dir",
        default="codigo/experiments/cwru_local",
    )
    parser.add_argument("--runs-dir", default="codigo/reports/runs")
    return parser.parse_args()


if __name__ == "__main__":
    main()
