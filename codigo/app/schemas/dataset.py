"""Contratos de dataset y manifiesto."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import (
    Field,
    NonNegativeInt,
    PositiveInt,
    field_validator,
    model_validator,
)

from codigo.app.schemas.common import JsonScalar, StrictBaseModel

DatasetName = Literal["cwru_bearing", "nasa_ims_bearing"]
DatasetLabel = Literal["normal", "fault"]
FaultType = Literal["inner_race", "outer_race", "ball"]
SensorChannelName = Literal["DE_time", "FE_time", "BA_time", "RPM"]
SourceFormat = Literal[
    "mat",
    "zip",
    "csv",
    "txt",
    "tsv",
    "npz",
    "parquet",
    "directory",
]
DatasetDomain = Literal["rotating_machinery", "industrial_time_series", "unknown"]
AssetType = Literal["bearing", "motor", "turbine", "pump", "unknown"]
LabelAvailability = Literal["file_level", "window_level", "run_level", "none", "partial"]
TaskType = Literal["binary_anomaly", "multiclass_fault", "run_to_failure", "unknown"]
CommonDatasetLabel = Literal["normal", "fault", "unknown", "degradation"]
SupervisionProfile = Literal[
    "binary_fault_classification",
    "run_to_failure_degradation",
    "unlabeled_diagnostic",
]
LabelGranularity = Literal["window", "file", "run", "event", "none", "proxy_temporal"]
LabelSource = Literal["official", "curated", "temporal_proxy", "synthetic", "none"]


DATASET_ID_PATTERN = r"^[a-z0-9][a-z0-9_]*$"


class SignalChannel(StrictBaseModel):
    """Canal disponible en un fichero de senal."""

    name: SensorChannelName
    source_key: str = Field(min_length=1)
    sample_rate_hz: PositiveInt | None
    unit: str | None
    role: Literal["main", "auxiliary", "target", "metadata"] = "auxiliary"


class FaultMetadata(StrictBaseModel):
    """Metadatos del fallo asociado a una muestra o fichero."""

    fault_type: FaultType | None
    fault_diameter_inch: float | None = Field(default=None, gt=0.0)
    load_hp: NonNegativeInt | None
    rpm: PositiveInt | None


class DatasetManifestRow(StrictBaseModel):
    """Fila del manifiesto de datos crudos."""

    file_id: str = Field(min_length=1)
    dataset: DatasetName
    source_path: str = Field(min_length=1)
    label: DatasetLabel
    fault_type: FaultType | None
    fault_diameter_inch: float | None = Field(default=None, gt=0.0)
    load_hp: NonNegativeInt | None
    rpm: PositiveInt | None
    sensor_channel: SensorChannelName
    source_sample_rate_hz: PositiveInt
    target_sample_rate_hz: PositiveInt
    source_format: SourceFormat
    notes: str | None = None

    @model_validator(mode="after")
    def validate_label_metadata(self) -> "DatasetManifestRow":
        if self.label == "normal":
            if self.fault_type is not None or self.fault_diameter_inch is not None:
                raise ValueError("normal rows must use null fault metadata")
        if self.label == "fault":
            if self.fault_type is None or self.fault_diameter_inch is None:
                raise ValueError("fault rows require fault_type and fault_diameter_inch")
        return self


class DatasetManifest(StrictBaseModel):
    """Manifiesto completo de un dataset."""

    dataset: DatasetName
    rows: list[DatasetManifestRow] = Field(min_length=1)
    manifest_path: str | None = None
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_rows(self) -> "DatasetManifest":
        file_ids = [row.file_id for row in self.rows]
        if len(file_ids) != len(set(file_ids)):
            raise ValueError("manifest rows must have unique file_id values")
        wrong_dataset = [row.file_id for row in self.rows if row.dataset != self.dataset]
        if wrong_dataset:
            raise ValueError("all manifest rows must match manifest dataset")
        return self

    @property
    def label_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {"normal": 0, "fault": 0}
        for row in self.rows:
            counts[row.label] += 1
        return counts


class DatasetDescriptor(StrictBaseModel):
    """Descriptor comun de un dataset antes de generar el manifiesto."""

    dataset_id: str = Field(min_length=1, pattern=DATASET_ID_PATTERN)
    dataset_name: str = Field(min_length=1)
    domain: DatasetDomain
    asset_type: AssetType
    raw_path: str = Field(min_length=1)
    source_format: SourceFormat
    adapter_id: str = Field(min_length=1, pattern=DATASET_ID_PATTERN)
    label_availability: LabelAvailability
    task_type: TaskType
    supervision_profile: SupervisionProfile = "binary_fault_classification"
    label_granularity: LabelGranularity = "file"
    label_source: LabelSource = "official"
    sampling_rate_hz: float | None = Field(default=None, gt=0.0)
    channel_names: list[str] = Field(default_factory=list)
    has_multiple_conditions: bool
    has_run_to_failure: bool
    metadata: dict[str, JsonScalar] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)

    @field_validator("channel_names")
    @classmethod
    def validate_channel_names(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("channel_names cannot contain empty values")
        if len(value) != len(set(value)):
            raise ValueError("channel_names must be unique")
        return value


class DatasetAdapterInfo(StrictBaseModel):
    """Metadata ligera de un adaptador de dataset registrado."""

    adapter_id: str = Field(min_length=1, pattern=DATASET_ID_PATTERN)
    dataset_id: str = Field(min_length=1, pattern=DATASET_ID_PATTERN)
    display_name: str = Field(min_length=1)
    supported_source_formats: list[SourceFormat] = Field(min_length=1)
    supports_descriptor: bool = True
    supports_manifest: bool = False
    is_experimental: bool = True
    notes: str | None = None


class CommonManifestRecord(StrictBaseModel):
    """Fila comun de manifiesto independiente del dataset concreto."""

    record_id: str = Field(min_length=1)
    dataset: str = Field(min_length=1, pattern=DATASET_ID_PATTERN)
    source_path: str = Field(min_length=1)
    source_format: SourceFormat
    label: CommonDatasetLabel
    label_detail: str | None = None
    condition_id: str | None = None
    asset_id: str | None = None
    run_id: str | None = None
    timestamp_start: datetime | None = None
    timestamp_end: datetime | None = None
    sampling_rate_hz: float | None = Field(default=None, gt=0.0)
    target_sample_rate_hz: float | None = Field(default=None, gt=0.0)
    channel_names: list[str] = Field(min_length=1)
    primary_channel: str | None = None
    n_channels: PositiveInt
    metadata_json: dict[str, JsonScalar] = Field(default_factory=dict)
    notes: str | None = None

    @field_validator("channel_names")
    @classmethod
    def validate_manifest_channel_names(cls, value: list[str]) -> list[str]:
        if any(not item.strip() for item in value):
            raise ValueError("channel_names cannot contain empty values")
        if len(value) != len(set(value)):
            raise ValueError("channel_names must be unique")
        return value

    @model_validator(mode="after")
    def validate_channel_consistency(self) -> "CommonManifestRecord":
        if self.n_channels != len(self.channel_names):
            raise ValueError("n_channels must match channel_names length")
        if self.primary_channel is not None and self.primary_channel not in self.channel_names:
            raise ValueError("primary_channel must be present in channel_names")
        if (
            self.timestamp_start is not None
            and self.timestamp_end is not None
            and self.timestamp_end < self.timestamp_start
        ):
            raise ValueError("timestamp_end cannot be earlier than timestamp_start")
        return self
