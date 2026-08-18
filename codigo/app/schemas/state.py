"""Contratos Pydantic para el estado global del pipeline."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import Field, NonNegativeInt, PositiveInt, model_validator

from codigo.app.schemas.common import JsonScalar, StrictBaseModel
from codigo.app.schemas.dataset import (
    DataProvenance,
    LabelGranularity,
    LabelSource,
    ProvenanceDetectionMethod,
    SupervisionProfile,
)
from codigo.app.schemas.reasoning import MemoryApplicability, MemoryTransferScope

PipelineStage = Literal[
    "initialized",
    "dataset_manifest",
    "profiling",
    "cleaning",
    "structuring",
    "modeling",
    "evaluation",
    "reporting",
    "human_review",
    "completed",
    "failed",
]

NodeName = Literal[
    "supervisor",
    "manifest_executor",
    "profiler_executor",
    "cleaner_agent",
    "cleaning_executor",
    "structuring_agent",
    "structuring_executor",
    "modeling_agent",
    "modeling_executor",
    "evaluator",
    "evaluation_agent",
    "report_writer",
    "human_review",
]

class ProjectContext(StrictBaseModel):
    """Contexto industrial y experimental de una ejecucion."""

    domain: Literal["industrial_anomaly_detection"] = "industrial_anomaly_detection"
    machine_type: Literal[
        "electric_motor_bearing",
        "rotating_machinery",
        "turbofan_engine",
        "industrial_process",
    ] = "electric_motor_bearing"
    signal_type: Literal["vibration", "multivariate_sensor"] = "vibration"
    dataset: Literal["cwru_bearing", "nasa_ims_bearing"] = "cwru_bearing"
    objective: Literal[
        "binary_anomaly_detection",
        "fault_type_classification",
        "run_to_failure_degradation",
    ] = "binary_anomaly_detection"
    target_sample_rate_hz: PositiveInt = 12000
    main_channel: str = Field(default="DE_time", min_length=1)
    label_mode: Literal["binary_anomaly", "fault_type", "degradation"] = (
        "binary_anomaly"
    )
    supervision_profile: SupervisionProfile = "binary_fault_classification"
    label_granularity: LabelGranularity = "file"
    label_source: LabelSource = "official"
    trajectory_group_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=160,
    )
    evaluation_group_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=160,
    )
    transfer_scope: MemoryTransferScope = "same_dataset"
    data_provenance: DataProvenance = "unknown"
    provenance_detection_method: ProvenanceDetectionMethod = "unverified"
    provenance_evidence_path: str | None = Field(default=None, min_length=1)
    provenance_evidence_sha256: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    notes: str | None = None

    @model_validator(mode="before")
    @classmethod
    def default_provenance_by_dataset(cls, value: Any) -> Any:
        if not isinstance(value, dict) or "data_provenance" in value:
            return value
        updated = dict(value)
        if updated.get("dataset", "cwru_bearing") == "cwru_bearing":
            updated["data_provenance"] = "official"
            updated.setdefault("provenance_detection_method", "trusted_adapter")
        else:
            updated["data_provenance"] = "unknown"
            updated.setdefault("provenance_detection_method", "unverified")
        return updated

    def to_memory_applicability(self) -> MemoryApplicability:
        """Proyecta solo el contexto necesario para gobernar transferencia RAG."""

        return MemoryApplicability(
            supervision_profile=self.supervision_profile,
            label_source=self.label_source,
            label_granularity=self.label_granularity,
            target_sample_rate_hz=self.target_sample_rate_hz,
            trajectory_group_id=self.trajectory_group_id,
            evaluation_group_id=self.evaluation_group_id,
            transfer_scope=self.transfer_scope,
        )


class StateMessage(StrictBaseModel):
    """Mensaje ligero para trazabilidad del grafo."""

    role: Literal["system", "user", "assistant", "agent", "tool", "supervisor"]
    content: str = Field(min_length=1)
    name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DatasetProfileSummary(StrictBaseModel):
    """Resumen estadistico; nunca contiene senales completas."""

    dataset_name: str = Field(min_length=1)
    n_files: NonNegativeInt = 0
    n_samples_total: NonNegativeInt | None = None
    channels: list[str] = Field(default_factory=list)
    sample_rates_hz: list[PositiveInt] = Field(default_factory=list)
    label_counts: dict[str, NonNegativeInt] = Field(default_factory=dict)
    stats_path: str | None = None
    summary: dict[str, JsonScalar] = Field(default_factory=dict)


class CleaningConfig(StrictBaseModel):
    """Configuracion validada para el ejecutor de limpieza."""

    strategy_id: str = Field(default="default_cleaning", min_length=1)
    remove_non_finite: bool = True
    resample_to_hz: PositiveInt | None = None
    normalization: Literal["none", "zscore", "robust"] = "none"
    selected_channel: str | None = Field(default=None, min_length=1)
    audit_log_path: str | None = None


class StructuringConfig(StrictBaseModel):
    """Configuracion validada para ventanas y features."""

    window_size: PositiveInt = 2048
    overlap: float = Field(default=0.5, ge=0.0, lt=1.0)
    main_channel: str = Field(default="DE_time", min_length=1)
    target_sample_rate_hz: PositiveInt = 12000
    label_mode: Literal["binary_anomaly", "fault_type", "degradation"] = (
        "binary_anomaly"
    )
    features: list[str] = Field(
        default_factory=lambda: [
            "mean",
            "std",
            "rms",
            "min",
            "max",
            "peak_to_peak",
            "skewness",
            "kurtosis",
            "crest_factor",
            "energy",
        ]
    )


class ModelingConfig(StrictBaseModel):
    """Configuracion validada para entrenamiento o inferencia."""

    model_name: Literal[
        "isolation_forest",
        "one_class_svm",
        "local_outlier_factor",
        "pca_reconstruction_error",
        "autoencoder_dense",
        "lstm_autoencoder",
    ]
    random_state: int | None = 42
    hyperparameters: dict[str, JsonScalar] = Field(default_factory=dict)


class MetricsReport(StrictBaseModel):
    """Metricas agregadas de una ejecucion."""

    metrics_path: str | None = None
    precision: float | None = Field(default=None, ge=0.0, le=1.0)
    recall: float | None = Field(default=None, ge=0.0, le=1.0)
    f1_score: float | None = Field(default=None, ge=0.0, le=1.0)
    roc_auc: float | None = Field(default=None, ge=0.0, le=1.0)
    pr_auc: float | None = Field(default=None, ge=0.0, le=1.0)
    false_positive_rate: float | None = Field(default=None, ge=0.0, le=1.0)
    extra: dict[str, JsonScalar] = Field(default_factory=dict)


class EvaluationResult(StrictBaseModel):
    """Juicio estructurado del evaluador."""

    approved: bool
    summary: str = Field(min_length=1)
    next_action: Literal[
        "continue",
        "retry_with_new_config",
        "request_human_review",
        "stop",
    ]
    limitations: list[str] = Field(default_factory=list)


class PipelineError(StrictBaseModel):
    """Error capturado sin corromper el estado."""

    stage: PipelineStage
    message: str = Field(min_length=1)
    node: NodeName | None = None
    recoverable: bool = True
    details: dict[str, JsonScalar] = Field(default_factory=dict)
    occurred_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class HumanApproval(StrictBaseModel):
    """Registro de revision humana para fases costosas o sensibles."""

    required: bool = False
    approved: bool | None = None
    reviewer: str | None = None
    reason: str | None = None
    reviewed_at: datetime | None = None


class ArtifactRef(StrictBaseModel):
    """Referencia ligera a un artefacto producido en disco."""

    name: str = Field(min_length=1)
    artifact_type: Literal[
        "manifest",
        "profile",
        "extracted_signals",
        "clean_signals",
        "features",
        "tensors",
        "splits",
        "model",
        "predictions",
        "metrics",
        "report",
        "log",
        "config",
    ]
    path: str = Field(min_length=1)
    producer: NodeName | str = Field(min_length=1)
    description: str | None = None
    metadata: dict[str, JsonScalar] = Field(default_factory=dict)


class TFMStateModel(StrictBaseModel):
    """Estado global validado para una ejecucion del pipeline."""

    thread_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    current_stage: PipelineStage = "initialized"
    next_node: NodeName | None = None

    project_context: ProjectContext

    raw_path: str = Field(min_length=1)
    manifest_path: str | None = None
    profile_path: str | None = None
    extracted_signals_path: str | None = None
    clean_path: str | None = None
    tensor_path: str | None = None
    splits_path: str | None = None
    report_path: str | None = None

    messages: list[StateMessage] = Field(default_factory=list)
    dataset_profile: DatasetProfileSummary | None = None

    cleaning_config: CleaningConfig | None = None
    structuring_config: StructuringConfig | None = None
    modeling_config: ModelingConfig | None = None

    metrics: MetricsReport | None = None
    evaluation: EvaluationResult | None = None
    errors: list[PipelineError] = Field(default_factory=list)
    human_approval: HumanApproval | None = None
    artifacts: list[ArtifactRef] = Field(default_factory=list)

    def to_langgraph_state(self) -> dict[str, Any]:
        """Devuelve una version JSON-serializable para LangGraph."""

        return self.model_dump(mode="json")
