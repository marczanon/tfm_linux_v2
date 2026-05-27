"""Servicios compartidos de la aplicacion."""

from codigo.app.services.llm import (
    JSONLLMClient,
    LLMCallError,
    LLMMessage,
    OllamaJSONClient,
    get_default_json_llm_client,
    parse_json_object,
)
from codigo.app.services.run_persistence import (
    DEFAULT_RUNS_DIR,
    RunIndex,
    RunIndexEntry,
    RunSnapshot,
    extract_decisions,
    load_run_index,
    load_run_snapshot,
    save_run_snapshot,
    update_run_index,
)
from codigo.app.services.run_registry import (
    MetricComparison,
    RunComparison,
    RunComparisonRow,
    compare_runs,
    get_run,
    get_run_artifacts,
    list_runs,
)
from codigo.app.services.experiment_protocol import (
    DEFAULT_EXPERIMENTS_DIR,
    DEFAULT_MODEL_PLAN_ID,
    DEFAULT_PLAN_ID,
    DEFAULT_WINDOW_PLAN_ID,
    ExperimentPlan,
    ExperimentPlanResult,
    ExperimentRunSummary,
    ExperimentSpec,
    cwru_model_experiment_plan_from_decision,
    cwru_window_experiment_plan_from_decision,
    default_cwru_experiment_plan,
    run_cwru_experiment_plan,
)
from codigo.app.services.degradation_diagnostics import (
    generate_degradation_diagnostics,
)
from codigo.app.services.synthetic_nasa_ims import (
    generate_synthetic_nasa_ims_binary_manifest,
    prepare_synthetic_nasa_ims_binary_dataset,
)
from codigo.app.services.iteration_analysis import (
    FailureAnalysisArtifacts,
    build_prediction_failure_analysis,
    generate_prediction_failure_analysis,
)
from codigo.app.services.reasoning_audit import (
    ReasoningAuditArtifacts,
    build_modeling_retry_postmortem,
    write_reasoning_postmortem,
)
from codigo.app.services.dataset_adapters import (
    DatasetAdapter,
    describe_dataset,
    get_dataset_adapter,
    infer_dataset_adapter,
    list_dataset_adapters,
)
from codigo.app.services.signal_adapters import (
    SignalChannel,
    load_signal_channel,
    read_signal_channels,
    read_signal_frame,
)

__all__ = [
    "DEFAULT_EXPERIMENTS_DIR",
    "DEFAULT_MODEL_PLAN_ID",
    "DEFAULT_PLAN_ID",
    "DEFAULT_WINDOW_PLAN_ID",
    "DEFAULT_RUNS_DIR",
    "DatasetAdapter",
    "ExperimentPlan",
    "ExperimentPlanResult",
    "ExperimentRunSummary",
    "FailureAnalysisArtifacts",
    "ExperimentSpec",
    "JSONLLMClient",
    "LLMCallError",
    "LLMMessage",
    "MetricComparison",
    "OllamaJSONClient",
    "RunComparison",
    "RunComparisonRow",
    "RunIndex",
    "RunIndexEntry",
    "RunSnapshot",
    "ReasoningAuditArtifacts",
    "SignalChannel",
    "compare_runs",
    "cwru_model_experiment_plan_from_decision",
    "cwru_window_experiment_plan_from_decision",
    "default_cwru_experiment_plan",
    "describe_dataset",
    "extract_decisions",
    "get_dataset_adapter",
    "get_run",
    "get_run_artifacts",
    "get_default_json_llm_client",
    "generate_degradation_diagnostics",
    "generate_synthetic_nasa_ims_binary_manifest",
    "build_prediction_failure_analysis",
    "generate_prediction_failure_analysis",
    "build_modeling_retry_postmortem",
    "infer_dataset_adapter",
    "list_dataset_adapters",
    "list_runs",
    "load_signal_channel",
    "load_run_index",
    "load_run_snapshot",
    "parse_json_object",
    "prepare_synthetic_nasa_ims_binary_dataset",
    "read_signal_channels",
    "read_signal_frame",
    "run_cwru_experiment_plan",
    "save_run_snapshot",
    "update_run_index",
    "write_reasoning_postmortem",
]
