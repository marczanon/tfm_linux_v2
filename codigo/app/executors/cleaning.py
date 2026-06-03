"""Limpieza determinista de manifiestos de senal."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from math import gcd
from pathlib import Path
from typing import Any

import numpy as np
from scipy.signal import resample_poly

from codigo.app.schemas.executor_results import CleaningResult
from codigo.app.schemas.state import ArtifactRef, CleaningConfig, PipelineError
from codigo.app.services.signal_adapters import load_signal_channel


DEFAULT_CLEANING_CONFIG = CleaningConfig(
    strategy_id="cwru_clean_v1",
    remove_non_finite=True,
    resample_to_hz=12000,
    normalization="none",
    audit_log_path="codigo/data/processed/cwru_bearing/cleaning_summary.json",
)


def generate_clean_signals(
    manifest_path: str | Path = "codigo/data/interim/cwru_bearing/manifest.csv",
    profile_path: str | Path = "codigo/data/interim/cwru_bearing/profile.json",
    output_dir: str | Path = "codigo/data/processed/cwru_bearing/clean_signals",
    config: CleaningConfig | None = None,
) -> CleaningResult:
    """Genera senales limpias por fichero y devuelve un resultado estructurado."""

    started_at = datetime.now(UTC)
    output = Path(output_dir)
    cfg = config or DEFAULT_CLEANING_CONFIG
    try:
        summary = clean_dataset(manifest_path, profile_path, output, cfg)
        dataset = summary["dataset"]
        artifact = ArtifactRef(
            name=f"{dataset}_clean_signals",
            artifact_type="clean_signals",
            path=str(output),
            producer="cleaning_executor",
            metadata={"n_files_cleaned": len(summary["files"])},
        )
        log_artifact = ArtifactRef(
            name=f"{dataset}_cleaning_summary",
            artifact_type="log",
            path=summary["summary_path"],
            producer="cleaning_executor",
            metadata={"strategy_id": cfg.strategy_id},
        )
        return CleaningResult(
            executor_name="cleaning",
            status="success",
            message="Clean signals generated.",
            artifacts=[artifact, log_artifact],
            errors=[],
            state_updates={"clean_path": str(output)},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            clean_path=str(output),
            n_files_cleaned=len(summary["files"]),
        )
    except Exception as exc:
        error = PipelineError(
            stage="cleaning",
            node="cleaning_executor",
            message=str(exc),
            recoverable=True,
        )
        return CleaningResult(
            executor_name="cleaning",
            status="failed",
            message="Signal cleaning failed.",
            artifacts=[],
            errors=[error],
            state_updates={},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            clean_path=str(output),
            n_files_cleaned=0,
        )


def clean_dataset(
    manifest_path: str | Path,
    profile_path: str | Path,
    output_dir: str | Path,
    config: CleaningConfig = DEFAULT_CLEANING_CONFIG,
) -> dict[str, Any]:
    """Limpia el canal principal de cada fila del manifiesto."""

    manifest = _read_manifest(manifest_path)
    if not manifest:
        raise ValueError(f"empty manifest: {manifest_path}")
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    if profile.get("n_files") != len(manifest):
        raise ValueError("profile and manifest file counts do not match")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    records = [_clean_row(row, output, config) for row in manifest]
    dataset = manifest[0].get("dataset") or "unknown"
    summary = {
        "dataset": dataset,
        "manifest_format": _manifest_format(manifest[0]),
        "strategy_id": config.strategy_id,
        "manifest_path": str(manifest_path),
        "profile_path": str(profile_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "n_files": len(records),
        "config": config.model_dump(mode="json"),
        "files": records,
    }
    summary_path = Path(config.audit_log_path or output.parent / "cleaning_summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary["summary_path"] = str(summary_path)
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def _read_manifest(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _clean_row(
    row: dict[str, str],
    output_dir: Path,
    config: CleaningConfig,
) -> dict[str, Any]:
    record_id = _record_id(row)
    channel = _selected_channel(row, config)
    source_rate = _source_sample_rate(row)
    raw = load_signal_channel(row["source_path"], channel)
    cleaned, removed = _clean_signal(raw, source_rate, config)
    sample_rate = config.resample_to_hz or source_rate
    output_path = output_dir / f"{_safe_output_stem(record_id)}.npz"
    metadata = _json_object(row.get("metadata_json"))
    np.savez_compressed(
        output_path,
        signal=cleaned.astype(np.float32),
        file_id=record_id,
        record_id=record_id,
        dataset=row.get("dataset") or "unknown",
        label=row["label"],
        fault_type=_optional_text(row.get("fault_type")) or "",
        label_detail=_optional_text(row.get("label_detail")) or "",
        condition_id=_optional_text(row.get("condition_id")) or "",
        asset_id=_optional_text(row.get("asset_id")) or "",
        run_id=_optional_text(row.get("run_id")) or "",
        timestamp_start=_optional_text(row.get("timestamp_start")) or "",
        timestamp_end=_optional_text(row.get("timestamp_end")) or "",
        source_path=row["source_path"],
        channel=channel,
        sample_rate_hz=sample_rate,
        metadata_json=json.dumps(metadata, sort_keys=True),
    )
    return {
        "file_id": record_id,
        "record_id": record_id,
        "dataset": row.get("dataset") or "unknown",
        "source_path": row["source_path"],
        "output_path": output_path.as_posix(),
        "label": row["label"],
        "fault_type": _optional_text(row.get("fault_type")),
        "label_detail": _optional_text(row.get("label_detail")),
        "condition_id": _optional_text(row.get("condition_id")),
        "asset_id": _optional_text(row.get("asset_id")),
        "run_id": _optional_text(row.get("run_id")),
        "timestamp_start": _optional_text(row.get("timestamp_start")),
        "timestamp_end": _optional_text(row.get("timestamp_end")),
        "channel": channel,
        "source_sample_rate_hz": source_rate,
        "sample_rate_hz": sample_rate,
        "n_samples_in": int(raw.size),
        "n_samples_out": int(cleaned.size),
        "non_finite_removed": removed,
    }


def _clean_signal(
    signal: np.ndarray,
    source_rate: int,
    config: CleaningConfig,
) -> tuple[np.ndarray, int]:
    finite = np.isfinite(signal)
    removed = int(signal.size - finite.sum())
    if removed and not config.remove_non_finite:
        raise ValueError("non-finite values found and remove_non_finite is false")

    cleaned = signal[finite] if config.remove_non_finite else signal.copy()
    if config.resample_to_hz and config.resample_to_hz != source_rate:
        factor = gcd(source_rate, config.resample_to_hz)
        cleaned = resample_poly(cleaned, config.resample_to_hz // factor, source_rate // factor)
    cleaned = _normalize(cleaned, config.normalization)
    return cleaned, removed


def _normalize(signal: np.ndarray, mode: str) -> np.ndarray:
    if mode == "none":
        return signal
    if mode == "zscore":
        std = signal.std()
        return signal - signal.mean() if std == 0 else (signal - signal.mean()) / std
    if mode == "robust":
        q25, q75 = np.percentile(signal, [25, 75])
        iqr = q75 - q25
        return signal - np.median(signal) if iqr == 0 else (signal - np.median(signal)) / iqr
    raise ValueError(f"unsupported normalization: {mode}")


def _record_id(row: dict[str, str]) -> str:
    return (
        _optional_text(row.get("file_id"))
        or _optional_text(row.get("record_id"))
        or Path(row["source_path"]).stem
    )


def _selected_channel(row: dict[str, str], config: CleaningConfig) -> str:
    channel = config.selected_channel or _optional_text(
        row.get("sensor_channel")
    ) or _optional_text(row.get("primary_channel"))
    declared_channels = _json_list(row.get("channel_names"))
    if channel is None and declared_channels:
        channel = declared_channels[0]
    if channel is None:
        raise ValueError(f"no selectable channel declared for {_record_id(row)}")
    if declared_channels and channel not in declared_channels:
        raise ValueError(
            f"selected channel {channel} not declared for {_record_id(row)}; "
            f"available: {', '.join(declared_channels)}"
        )
    return channel


def _source_sample_rate(row: dict[str, str]) -> int:
    value = _row_number(row, "source_sample_rate_hz", "sampling_rate_hz")
    if value is None:
        raise ValueError(f"missing sample rate for {_record_id(row)}")
    if not float(value).is_integer():
        raise ValueError(f"sample rate must be an integer for {_record_id(row)}")
    return int(value)


def _manifest_format(row: dict[str, str]) -> str:
    if "record_id" in row and "channel_names" in row and "sampling_rate_hz" in row:
        return "common"
    return "cwru_legacy"


def _row_number(row: dict[str, str], *keys: str) -> float | None:
    for key in keys:
        text = _optional_text(row.get(key))
        if text is not None:
            return float(text)
    return None


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


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


def _safe_output_stem(record_id: str) -> str:
    return record_id.replace("/", "_").replace("\\", "_")
