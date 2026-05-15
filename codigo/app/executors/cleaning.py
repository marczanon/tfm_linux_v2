"""Limpieza determinista de senales CWRU."""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from math import gcd
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat
from scipy.signal import resample_poly

from codigo.app.schemas.executor_results import CleaningResult
from codigo.app.schemas.state import ArtifactRef, CleaningConfig, PipelineError


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
        artifact = ArtifactRef(
            name="cwru_clean_signals",
            artifact_type="clean_signals",
            path=str(output),
            producer="cleaning_executor",
            metadata={"n_files_cleaned": len(summary["files"])},
        )
        log_artifact = ArtifactRef(
            name="cwru_cleaning_summary",
            artifact_type="log",
            path=summary["summary_path"],
            producer="cleaning_executor",
            metadata={"strategy_id": cfg.strategy_id},
        )
        return CleaningResult(
            executor_name="cleaning",
            status="success",
            message="CWRU clean signals generated.",
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
            message="CWRU cleaning failed.",
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
    profile = json.loads(Path(profile_path).read_text(encoding="utf-8"))
    if profile.get("n_files") != len(manifest):
        raise ValueError("profile and manifest file counts do not match")

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    records = [_clean_row(row, output, config) for row in manifest]
    summary = {
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
    raw = _load_channel(Path(row["source_path"]), row["sensor_channel"])
    cleaned, removed = _clean_signal(raw, int(row["source_sample_rate_hz"]), config)
    sample_rate = config.resample_to_hz or int(row["source_sample_rate_hz"])
    output_path = output_dir / f"{row['file_id']}.npz"
    np.savez_compressed(
        output_path,
        signal=cleaned.astype(np.float32),
        file_id=row["file_id"],
        label=row["label"],
        fault_type=row["fault_type"],
        channel=row["sensor_channel"],
        sample_rate_hz=sample_rate,
    )
    return {
        "file_id": row["file_id"],
        "source_path": row["source_path"],
        "output_path": output_path.as_posix(),
        "label": row["label"],
        "fault_type": row["fault_type"] or None,
        "channel": row["sensor_channel"],
        "source_sample_rate_hz": int(row["source_sample_rate_hz"]),
        "sample_rate_hz": sample_rate,
        "n_samples_in": int(raw.size),
        "n_samples_out": int(cleaned.size),
        "non_finite_removed": removed,
    }


def _load_channel(path: Path, channel: str) -> np.ndarray:
    suffix = {
        "DE_time": "_DE_time",
        "FE_time": "_FE_time",
        "BA_time": "_BA_time",
    }.get(channel)
    if suffix is None:
        raise ValueError(f"unsupported signal channel: {channel}")

    for key, value in loadmat(path).items():
        if key.endswith(suffix):
            return np.asarray(value, dtype=float).ravel()
    raise ValueError(f"channel {channel} not found in {path}")


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
