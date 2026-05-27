"""Full agentic run on a labeled synthetic NASA IMS-like benchmark."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from codigo.app.agents.cleaner import decide_cleaning_action
from codigo.app.agents.evaluator import decide_evaluation_action
from codigo.app.agents.modeler import decide_modeling_action
from codigo.app.agents.report_writer import decide_report_action
from codigo.app.agents.structurer import decide_structuring_action
from codigo.app.agents.supervisor import decide_supervisor_action
from codigo.app.executors.cleaning import generate_clean_signals
from codigo.app.executors.data_profiler import generate_data_profile
from codigo.app.executors.evaluation import generate_evaluation_report
from codigo.app.executors.modeling import generate_model_outputs
from codigo.app.executors.reporting import generate_technical_report
from codigo.app.executors.structuring import generate_temporal_structure
from codigo.app.graph.pipeline import (
    PipelineAgents,
    PipelineExecutors,
    run_and_persist_cwru_pipeline,
)
from codigo.app.graph.state import TFMState
from codigo.app.schemas.state import CleaningConfig, ProjectContext, TFMStateModel
from codigo.app.services.llm import OllamaJSONClient
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR, extract_decisions
from codigo.app.services.synthetic_nasa_ims import (
    generate_synthetic_nasa_ims_binary_manifest,
    prepare_synthetic_nasa_ims_binary_dataset,
)


def main() -> None:
    args = _parse_args()
    paths = _run_paths(args.run_id)
    prepare_synthetic_nasa_ims_binary_dataset(
        paths["raw_dir"],
        seed=args.seed,
        n_normal_files=args.n_normal_files,
        n_fault_files=args.n_fault_files,
        sample_count=args.sample_count,
    )

    client = OllamaJSONClient(
        model=args.model,
        timeout_seconds=args.timeout_seconds,
        think=args.think,
    )
    result = run_and_persist_cwru_pipeline(
        _initial_state(args.run_id, paths["raw_dir"]),
        executors=_executors(paths, args),
        agents=_agents(client),
        runs_dir=DEFAULT_RUNS_DIR,
    )
    final_model = TFMStateModel.model_validate(result.state)
    _print_summary(final_model, result.snapshot.snapshot_dir, paths)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument(
        "--run-id",
        default=f"nasa-ims-synth-agentic-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
    )
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--think", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-normal-files", type=int, default=7)
    parser.add_argument("--n-fault-files", type=int, default=5)
    parser.add_argument("--sample-count", type=int, default=8192)
    return parser.parse_args()


def _run_paths(run_id: str) -> dict[str, Path]:
    return {
        "raw_dir": Path("codigo/data/raw/nasa_ims_bearing/synthetic_temporal_binary")
        / run_id,
        "interim_dir": Path("codigo/data/interim/nasa_ims_bearing") / run_id,
        "clean_dir": Path("codigo/data/processed/nasa_ims_bearing")
        / run_id
        / "clean_signals",
        "tensor_dir": Path("codigo/data/tensors/nasa_ims_bearing") / run_id,
        "model_dir": Path("codigo/models/nasa_ims_bearing") / run_id,
        "evaluation_dir": Path("codigo/reports/nasa_ims_bearing")
        / run_id
        / "evaluation",
        "cleaning_summary": Path("codigo/data/processed/nasa_ims_bearing")
        / run_id
        / "cleaning_summary.json",
    }


def _initial_state(run_id: str, raw_dir: Path) -> TFMState:
    state = TFMStateModel(
        thread_id=f"{run_id}-thread",
        run_id=run_id,
        current_stage="dataset_manifest",
        next_node="manifest_executor",
        project_context=ProjectContext(
            dataset="nasa_ims_bearing",
            machine_type="rotating_machinery",
            signal_type="vibration",
            objective="binary_anomaly_detection",
            target_sample_rate_hz=20000,
            main_channel="channel_1",
            label_mode="binary_anomaly",
            notes=(
                "Synthetic NASA IMS-like binary benchmark. Labels are generated "
                "by construction and are not official NASA IMS annotations."
            ),
        ),
        raw_path=raw_dir.as_posix(),
    )
    return TFMState(**state.to_langgraph_state())


def _executors(paths: dict[str, Path], args: argparse.Namespace) -> PipelineExecutors:
    def cleaning(manifest_path: str, profile_path: str, config: CleaningConfig):
        run_config = config.model_copy(
            update={"audit_log_path": paths["cleaning_summary"].as_posix()}
        )
        return generate_clean_signals(
            manifest_path,
            profile_path,
            paths["clean_dir"],
            run_config,
        )

    return PipelineExecutors(
        manifest=lambda raw_dir: generate_synthetic_nasa_ims_binary_manifest(
            raw_dir,
            paths["interim_dir"],
            n_normal_files=args.n_normal_files,
            sample_count=args.sample_count,
        ),
        profile=lambda manifest_path: generate_data_profile(
            manifest_path,
            paths["interim_dir"] / "profile.json",
        ),
        cleaning=cleaning,
        structuring=lambda clean_dir, config: generate_temporal_structure(
            clean_dir,
            paths["tensor_dir"],
            config,
        ),
        modeling=lambda features_path, config: generate_model_outputs(
            features_path,
            paths["model_dir"],
            config,
        ),
        evaluation=lambda predictions_path: generate_evaluation_report(
            predictions_path,
            paths["evaluation_dir"],
        ),
        reporting=generate_technical_report,
    )


def _agents(client: OllamaJSONClient) -> PipelineAgents:
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
        structurer=lambda state: decide_structuring_action(
            state,
            llm_client=client,
            use_llm=True,
        ),
        modeler=lambda state: decide_modeling_action(
            state,
            llm_client=client,
            use_llm=True,
        ),
        evaluator=lambda state: decide_evaluation_action(
            state,
            llm_client=client,
            use_llm=True,
        ),
        report_writer=lambda state: decide_report_action(
            state,
            llm_client=client,
            use_llm=True,
        ),
    )


def _print_summary(
    state: TFMStateModel,
    snapshot_dir: str,
    paths: dict[str, Path],
) -> None:
    decisions = extract_decisions(state)
    print(
        json.dumps(
            {
                "run_id": state.run_id,
                "dataset": state.project_context.dataset,
                "synthetic": True,
                "final_stage": state.current_stage,
                "approved": None if state.evaluation is None else state.evaluation.approved,
                "snapshot_dir": snapshot_dir,
                "raw_dir": paths["raw_dir"].as_posix(),
                "report_path": state.report_path,
                "metrics": None
                if state.metrics is None
                else state.metrics.model_dump(mode="json"),
                "artifact_types": [artifact.artifact_type for artifact in state.artifacts],
                "errors": [error.message for error in state.errors],
                "decisions": [
                    {
                        "agent": decision.get("agent_name"),
                        "decision_id": decision.get("decision_id"),
                        "rationale": decision.get("payload", {}).get("rationale"),
                        "confidence": decision.get("payload", {}).get("confidence"),
                    }
                    for decision in decisions
                ],
            },
            indent=2,
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
