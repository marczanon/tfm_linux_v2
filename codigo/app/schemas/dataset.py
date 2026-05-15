"""Contratos de dataset y manifiesto."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import Field, NonNegativeInt, PositiveInt, model_validator

from codigo.app.schemas.common import StrictBaseModel

DatasetName = Literal["cwru_bearing", "nasa_ims_bearing"]
DatasetLabel = Literal["normal", "fault"]
FaultType = Literal["inner_race", "outer_race", "ball"]
SensorChannelName = Literal["DE_time", "FE_time", "BA_time", "RPM"]
SourceFormat = Literal["mat", "zip", "csv", "parquet"]


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
