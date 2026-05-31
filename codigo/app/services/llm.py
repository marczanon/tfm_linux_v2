"""Clientes LLM con salida JSON para agentes del TFM."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol


DEFAULT_OLLAMA_CHAT_MODEL = "qwen3.5:4b"
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"


class LLMCallError(RuntimeError):
    """Error controlado durante una llamada LLM."""


@dataclass(frozen=True)
class LLMMessage:
    """Mensaje minimo para una conversacion con un LLM."""

    role: Literal["system", "user", "assistant"]
    content: str


class JSONLLMClient(Protocol):
    """Interfaz comun para clientes LLM que deben devolver JSON."""

    def complete_json(
        self,
        messages: Sequence[LLMMessage],
        *,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Devuelve un objeto JSON como diccionario."""


@dataclass(frozen=True)
class LLMProviderStatus:
    """Estado observable del proveedor LLM local."""

    provider: str
    model: str
    host: str
    timeout_seconds: float
    think: bool | None
    available: bool
    model_available: bool
    models: list[str]
    detail: str | None = None


@dataclass(frozen=True)
class OllamaJSONClient:
    """Cliente local para Ollama usando `/api/chat` y modo JSON."""

    model: str
    host: str = DEFAULT_OLLAMA_HOST
    timeout_seconds: float = 60.0
    think: bool | None = False

    def complete_json(
        self,
        messages: Sequence[LLMMessage],
        *,
        json_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in messages
            ],
            "stream": False,
            "format": "json",
        }
        if self.think is not None:
            payload["think"] = self.think
        if json_schema:
            payload["options"] = {
                "temperature": 0,
                "num_ctx": 8192,
                "num_predict": 2048,
            }

        request = urllib.request.Request(
            f"{self.host.rstrip('/')}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                raw_response = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise LLMCallError(f"ollama call failed: {exc}") from exc

        content = raw_response.get("message", {}).get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMCallError("ollama response did not include message.content")
        return parse_json_object(content)


def get_default_json_llm_client() -> JSONLLMClient:
    """Crea el cliente LLM configurado por variables de entorno."""

    provider = os.getenv("TFM_LLM_PROVIDER", "ollama").strip().lower()
    if provider != "ollama":
        raise LLMCallError(f"unsupported TFM_LLM_PROVIDER: {provider}")

    model = _default_ollama_model()
    host = _default_ollama_host()
    timeout = float(os.getenv("TFM_LLM_TIMEOUT_SECONDS", "60"))
    think = _ollama_think_from_env()
    return OllamaJSONClient(
        model=model,
        host=host,
        timeout_seconds=timeout,
        think=think,
    )


def get_default_llm_status(
    *,
    timeout_seconds: float = 2.0,
) -> LLMProviderStatus:
    """Comprueba si Ollama y el modelo de chat configurado estan disponibles."""

    provider = os.getenv("TFM_LLM_PROVIDER", "ollama").strip().lower()
    model = _default_ollama_model()
    host = _default_ollama_host()
    think = _ollama_think_from_env()
    if provider != "ollama":
        return LLMProviderStatus(
            provider=provider,
            model=model,
            host=host,
            timeout_seconds=timeout_seconds,
            think=think,
            available=False,
            model_available=False,
            models=[],
            detail=f"unsupported TFM_LLM_PROVIDER: {provider}",
        )

    request = urllib.request.Request(
        f"{host.rstrip('/')}/api/tags",
        headers={"Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw_response = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        return LLMProviderStatus(
            provider=provider,
            model=model,
            host=host,
            timeout_seconds=timeout_seconds,
            think=think,
            available=False,
            model_available=False,
            models=[],
            detail=f"ollama status check failed: {exc}",
        )

    models = _model_names_from_tags_response(raw_response)
    return LLMProviderStatus(
        provider=provider,
        model=model,
        host=host,
        timeout_seconds=timeout_seconds,
        think=think,
        available=True,
        model_available=model in models,
        models=models,
        detail=None if model in models else f"model not found in Ollama: {model}",
    )


def parse_json_object(content: str) -> dict[str, Any]:
    """Parsea un objeto JSON, tolerando texto alrededor si aparece."""

    stripped = content.strip()
    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise LLMCallError("LLM response does not contain a JSON object")
        try:
            parsed = json.loads(stripped[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMCallError(f"invalid JSON object from LLM: {exc}") from exc

    if not isinstance(parsed, dict):
        raise LLMCallError("LLM JSON response must be an object")
    return parsed


def _default_ollama_model() -> str:
    return (
        os.getenv("TFM_LLM_MODEL")
        or os.getenv("OLLAMA_MODEL")
        or DEFAULT_OLLAMA_CHAT_MODEL
    )


def _default_ollama_host() -> str:
    return os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST)


def _ollama_think_from_env() -> bool | None:
    raw_value = os.getenv("TFM_LLM_THINK")
    if raw_value is None:
        return False

    normalized = raw_value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    if normalized in {"auto", "omit", "none"}:
        return None
    raise LLMCallError(
        "TFM_LLM_THINK must be true, false, auto, omit or none"
    )


def _model_names_from_tags_response(raw_response: Any) -> list[str]:
    if not isinstance(raw_response, dict):
        return []
    raw_models = raw_response.get("models", [])
    if not isinstance(raw_models, list):
        return []
    names: list[str] = []
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        name = item.get("name") or item.get("model")
        if isinstance(name, str) and name:
            names.append(name)
    return sorted(set(names))
