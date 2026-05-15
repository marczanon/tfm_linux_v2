"""Tipos comunes para contratos Pydantic."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

JsonScalar = str | int | float | bool | None


class StrictBaseModel(BaseModel):
    """Base comun: valida asignaciones y rechaza campos no declarados."""

    model_config = ConfigDict(
        extra="forbid",
        validate_assignment=True,
        str_strip_whitespace=True,
    )
