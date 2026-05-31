"""Contratos publicos para estado LLM/Ollama de la aplicacion."""

from __future__ import annotations

from pydantic import Field

from codigo.app.schemas.common import StrictBaseModel


class LLMStatusResponse(StrictBaseModel):
    """Estado observable del proveedor LLM local usado por la API."""

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    host: str = Field(min_length=1)
    timeout_seconds: float
    think: bool | None
    available: bool
    model_available: bool
    models: list[str]
    detail: str | None = Field(default=None, min_length=1)
