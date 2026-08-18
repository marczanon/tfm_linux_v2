"""Ejecucion agentica controlada NASA IMS con Qwen/Ollama.

El objetivo no es entrenar un modelo NASA IMS, sino comprobar si los agentes
LLM usan los expedientes expertos y respetan los bloqueos metodologicos.
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np

from codigo.app.agents.cleaner import decide_cleaning_action
from codigo.app.agents.evaluator import decide_evaluation_action
from codigo.app.agents.modeler import decide_modeling_action
from codigo.app.agents.report_writer import decide_report_action
from codigo.app.agents.structurer import decide_structuring_action
from codigo.app.agents.supervisor import decide_supervisor_action
from codigo.app.executors.cleaning import generate_clean_signals
from codigo.app.executors.data_profiler import generate_data_profile
from codigo.app.executors.dataset_manifest import generate_dataset_manifest
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
from codigo.app.schemas.executor_results import ModelingResult
from codigo.app.schemas.state import PipelineError, ProjectContext, TFMStateModel
from codigo.app.services.llm import OllamaJSONClient
from codigo.app.services.run_persistence import DEFAULT_RUNS_DIR, extract_decisions
from codigo.app.services.dataset_adapters import describe_dataset


def main() -> None:
    args = _parse_args()
    paths = _run_paths(args.run_id)
    raw_dir = _prepare_synthetic_nasa_ims(paths["raw_dir"])
    client = OllamaJSONClient(
        model=args.model,
        timeout_seconds=args.timeout_seconds,
        think=args.think,
    )

    initial_state = _initial_state(args.run_id, raw_dir)
    executors = _executors(paths)
    agents = _agents(client)

    result = run_and_persist_cwru_pipeline(
        initial_state,
        executors=executors,
        agents=agents,
        runs_dir=DEFAULT_RUNS_DIR,
    )
    final_model = TFMStateModel.model_validate(result.state)
    _print_summary(final_model, result.snapshot.snapshot_dir)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="qwen3.5:4b")
    parser.add_argument(
        "--run-id",
        default=f"nasa-ims-qwen-smoke-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}",
    )
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--think", action="store_true")
    return parser.parse_args()


def _run_paths(run_id: str) -> dict[str, Path]:
    return {
        "raw_dir": Path("codigo/data/raw/nasa_ims_bearing/preextracted_synthetic_qwen"),
        "interim_dir": Path("codigo/data/interim/nasa_ims_bearing") / run_id,
        "clean_dir": Path("codigo/data/processed/nasa_ims_bearing") / run_id / "clean_signals",
        "tensor_dir": Path("codigo/data/tensors/nasa_ims_bearing") / run_id,
        "model_dir": Path("codigo/models/nasa_ims_bearing") / run_id,
    }


def _prepare_synthetic_nasa_ims(raw_dir: Path) -> Path:
    target_dir = raw_dir / "2nd_test"
    target_dir.mkdir(parents=True, exist_ok=True)
    sample_count = 4096
    time = np.linspace(0, 1, sample_count, endpoint=False)
    for index, timestamp in enumerate(
        [
            "2004.02.12.10.32.39",
            "2004.02.12.10.42.39",
            "2004.02.12.10.52.39",
        ]
    ):
        base = 0.08 + index * 0.01
        frame = np.column_stack(
            [
                np.sin(2 * np.pi * 25 * time) * (1.0 + base),
                np.sin(2 * np.pi * 35 * time) * (0.8 + base),
                np.cos(2 * np.pi * 15 * time) * (0.6 + base),
                np.sin(2 * np.pi * 5 * time) * (0.4 + base),
            ]
        )
        np.savetxt(target_dir / timestamp, frame, fmt="%.8f", delimiter="\t")
    (raw_dir / "synthetic_dataset_spec.json").write_text(
        json.dumps(
            {
                "dataset": "nasa_ims_bearing",
                "synthetic": True,
                "generator": "run_nasa_ims_qwen_smoke",
                "sample_count": sample_count,
                "sample_rate_hz": 20000,
                "n_files": 3,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return raw_dir


def _initial_state(run_id: str, raw_dir: Path) -> TFMState:
    descriptor = describe_dataset(raw_dir, adapter_id="nasa_ims_bearing")
    state = TFMStateModel(
        thread_id=f"{run_id}-thread",
        run_id=run_id,
        current_stage="dataset_manifest",
        next_node="manifest_executor",
        project_context=ProjectContext(
            dataset="nasa_ims_bearing",
            machine_type="rotating_machinery",
            signal_type="vibration",
            objective="run_to_failure_degradation",
            target_sample_rate_hz=20000,
            main_channel="channel_1",
            label_mode="degradation",
            supervision_profile="run_to_failure_degradation",
            label_granularity="event",
            label_source="none",
            data_provenance=descriptor.data_provenance,
            provenance_detection_method=descriptor.provenance_detection_method,
            provenance_evidence_path=descriptor.provenance_evidence_path,
            provenance_evidence_sha256=descriptor.provenance_evidence_sha256,
            notes=(
                "NASA IMS synthetic preextracted smoke run; modeling is expected "
                "to be blocked until temporal labels and split policy exist."
            ),
        ),
        raw_path=raw_dir.as_posix(),
    )
    return TFMState(**state.to_langgraph_state())


def _executors(paths: dict[str, Path]) -> PipelineExecutors:
    return PipelineExecutors(
        manifest=lambda raw_dir: generate_dataset_manifest(
            raw_dir,
            paths["interim_dir"],
            adapter_id="nasa_ims_bearing",
        ),
        profile=lambda manifest_path: generate_data_profile(
            manifest_path,
            paths["interim_dir"] / "profile.json",
        ),
        cleaning=lambda manifest_path, profile_path, config: generate_clean_signals(
            manifest_path,
            profile_path,
            paths["clean_dir"],
            config,
        ),
        structuring=lambda clean_dir, config: generate_temporal_structure(
            clean_dir,
            paths["tensor_dir"],
            config,
        ),
        modeling=lambda features_path, config: _blocked_nasa_modeling(
            paths["model_dir"],
        ),
        evaluation=generate_evaluation_report,
        reporting=generate_technical_report,
    )


def _blocked_nasa_modeling(model_dir: Path) -> ModelingResult:
    model_dir.mkdir(parents=True, exist_ok=True)
    log_path = model_dir / "modeling_blocked.json"
    payload = {
        "status": "blocked",
        "reason": (
            "NASA IMS run-to-failure data has unknown window labels and no "
            "validated temporal split policy yet."
        ),
        "required_capability": "run_to_failure_temporal_split_and_label_policy",
        "next_action": "define_temporal_split_policy_before_modeling",
    }
    log_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return ModelingResult(
        executor_name="modeling",
        status="failed",
        message="NASA IMS modeling blocked by methodological guardrail.",
        errors=[
            PipelineError(
                stage="modeling",
                node="modeling_executor",
                message=payload["reason"],
                recoverable=True,
            )
        ],
        model_path=log_path.as_posix(),
        predictions_path=None,
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
        modeler=lambda state, memory_context=None: decide_modeling_action(
            state,
            memory_context=memory_context,
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


def _print_summary(state: TFMStateModel, snapshot_dir: str) -> None:
    decisions = extract_decisions(state)
    print(
        json.dumps(
            {
                "run_id": state.run_id,
                "dataset": state.project_context.dataset,
                "final_stage": state.current_stage,
                "snapshot_dir": snapshot_dir,
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
