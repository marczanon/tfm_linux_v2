"""Utilidades compartidas para manifiestos comunes de dataset."""

from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from codigo.app.schemas.dataset import CommonManifestRecord


def read_common_manifest(path: str | Path) -> list[CommonManifestRecord]:
    """Lee un manifiesto comun CSV y devuelve registros validados."""

    with Path(path).open(encoding="utf-8") as file:
        return [
            deserialize_common_manifest_row(row)
            for row in csv.DictReader(file)
        ]


def write_common_manifest(
    path: str | Path,
    records: list[CommonManifestRecord],
) -> None:
    """Escribe registros de manifiesto comun en CSV."""

    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(CommonManifestRecord.model_fields)
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(serialize_common_manifest_row(record))


def serialize_common_manifest_row(record: CommonManifestRecord) -> dict[str, Any]:
    """Serializa una fila de manifiesto comun para CSV."""

    row: dict[str, Any] = {}
    for key, value in record.model_dump().items():
        if value is None:
            row[key] = ""
        elif isinstance(value, datetime):
            row[key] = value.isoformat()
        elif isinstance(value, (dict, list)):
            row[key] = json.dumps(value, sort_keys=True)
        else:
            row[key] = value
    return row


def deserialize_common_manifest_row(row: dict[str, str]) -> CommonManifestRecord:
    """Deserializa y valida una fila CSV de manifiesto comun."""

    data: dict[str, Any] = dict(row)
    data["channel_names"] = _json_list(row.get("channel_names"))
    data["metadata_json"] = _json_object(row.get("metadata_json"))
    for key in ["timestamp_start", "timestamp_end"]:
        if not str(data.get(key) or "").strip():
            data[key] = None
    for key in ["sampling_rate_hz", "target_sample_rate_hz"]:
        if not str(data.get(key) or "").strip():
            data[key] = None
    return CommonManifestRecord.model_validate(data)


def _json_list(value: str | None) -> list[str]:
    text = _optional_text(value)
    if text is None:
        return []
    parsed = json.loads(text)
    if not isinstance(parsed, list):
        raise ValueError("manifest channel_names must be a JSON list")
    return [str(item) for item in parsed]


def _json_object(value: str | None) -> dict[str, Any]:
    text = _optional_text(value)
    if text is None:
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("manifest metadata_json must be a JSON object")
    return parsed


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None
