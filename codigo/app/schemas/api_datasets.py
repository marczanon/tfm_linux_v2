"""Contratos publicos para catalogo controlado de datasets."""

from __future__ import annotations

from pydantic import Field

from codigo.app.schemas.common import StrictBaseModel
from codigo.app.schemas.dataset import (
    DATASET_ID_PATTERN,
    DatasetAdapterInfo,
    DatasetDescriptor,
)


class DatasetDescribeRequest(StrictBaseModel):
    """Solicitud API para describir una ruta raw permitida."""

    raw_path: str = Field(min_length=1)
    adapter_id: str | None = Field(
        default=None,
        min_length=1,
        pattern=DATASET_ID_PATTERN,
    )


class DatasetDescribeResponse(StrictBaseModel):
    """Descriptor observable antes de planificar o ejecutar una run."""

    adapter_info: DatasetAdapterInfo
    descriptor: DatasetDescriptor
    allowed_raw_roots: list[str] = Field(min_length=1)
    uploads_dir: str = Field(min_length=1)
