"""Clientes LLM con salida JSON para agentes del TFM."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol


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
class OllamaJSONClient:
    """Cliente local para Ollama usando `/api/chat` y modo JSON."""

    model: str
    host: str = "http://127.0.0.1:11434"
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

    model = os.getenv("TFM_LLM_MODEL") or os.getenv("OLLAMA_MODEL")
    if not model:
        raise LLMCallError("TFM_LLM_MODEL or OLLAMA_MODEL must be set")

    host = os.getenv("OLLAMA_HOST", "http://127.0.0.1:11434")
    timeout = float(os.getenv("TFM_LLM_TIMEOUT_SECONDS", "60"))
    think = _ollama_think_from_env()
    return OllamaJSONClient(
        model=model,
        host=host,
        timeout_seconds=timeout,
        think=think,
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
