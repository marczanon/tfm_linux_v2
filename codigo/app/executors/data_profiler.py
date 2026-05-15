"""Perfilado determinista de ficheros CWRU."""

from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

from codigo.app.schemas.executor_results import ProfileResult
from codigo.app.schemas.state import ArtifactRef, PipelineError
from codigo.app.services.signal_adapters import read_signal_channels


def generate_data_profile(
    manifest_path: str | Path = "codigo/data/interim/cwru_bearing/manifest.csv",
    output_path: str | Path = "codigo/data/interim/cwru_bearing/profile.json",
) -> ProfileResult:
    """Genera `profile.json` desde un manifiesto validado."""

    started_at = datetime.now(UTC)
    output = Path(output_path)
    try:
        profile = build_data_profile(manifest_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(profile, indent=2), encoding="utf-8")
        artifact = ArtifactRef(
            name="cwru_profile",
            artifact_type="profile",
            path=str(output),
            producer="profiler_executor",
            metadata={
                "n_files_profiled": profile["n_files"],
                "channels": ",".join(profile["channels_detected"]),
            },
        )
        return ProfileResult(
            executor_name="data_profiler",
            status="success",
            message="CWRU data profile generated.",
            artifacts=[artifact],
            errors=[],
            state_updates={"profile_path": str(output)},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            profile_path=str(output),
            n_files_profiled=profile["n_files"],
        )
    except Exception as exc:
        error = PipelineError(
            stage="profiling",
            node="profiler_executor",
            message=str(exc),
            recoverable=True,
        )
        return ProfileResult(
            executor_name="data_profiler",
            status="failed",
            message="CWRU data profiling failed.",
            artifacts=[],
            errors=[error],
            state_updates={},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            profile_path=str(output),
            n_files_profiled=0,
        )


def build_data_profile(manifest_path: str | Path) -> dict[str, Any]:
    """Construye un perfil estadistico ligero para todos los ficheros."""

    manifest = _read_manifest(manifest_path)
    if not manifest:
        raise ValueError(f"empty manifest: {manifest_path}")

    files = [_profile_file(row) for row in manifest]
    channel_names = sorted({name for item in files for name in item["channels"]})
    return {
        "dataset": "cwru_bearing",
        "manifest_path": str(manifest_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "n_files": len(files),
        "label_counts": dict(Counter(row["label"] for row in manifest)),
        "fault_type_counts": dict(
            Counter(row["fault_type"] or "none" for row in manifest)
        ),
        "load_counts": dict(Counter(row["load_hp"] or "unknown" for row in manifest)),
        "sample_rate_counts": dict(
            Counter(row["source_sample_rate_hz"] for row in manifest)
        ),
        "channels_detected": channel_names,
        "files": files,
    }


def _read_manifest(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(encoding="utf-8") as file:
        return list(csv.DictReader(file))


def _profile_file(row: dict[str, str]) -> dict[str, Any]:
    path = Path(row["source_path"])
    if not path.exists():
        raise FileNotFoundError(path)

    channels = {
        name: _channel_stats(channel.source_key, channel.values, channel.shape)
        for name, channel in read_signal_channels(path).items()
    }

    return {
        "file_id": row["file_id"],
        "source_path": row["source_path"],
        "label": row["label"],
        "fault_type": row["fault_type"] or None,
        "load_hp": _optional_int(row["load_hp"]),
        "rpm": _optional_int(row["rpm"]),
        "source_sample_rate_hz": int(row["source_sample_rate_hz"]),
        "target_sample_rate_hz": int(row["target_sample_rate_hz"]),
        "channels": channels,
    }


def _channel_stats(source_key: str, values: np.ndarray, shape: tuple[int, ...]) -> dict[str, Any]:
    array = np.asarray(values, dtype=float).ravel()
    finite = array[np.isfinite(array)]
    stats = {
        "source_key": source_key,
        "shape": list(shape),
        "n_samples": int(array.size),
        "non_finite_count": int(array.size - finite.size),
    }
    if finite.size == 0:
        return stats | {key: None for key in _STAT_KEYS}

    mean = float(finite.mean())
    std = float(finite.std())
    centered = finite - mean
    return stats | {
        "min": float(finite.min()),
        "max": float(finite.max()),
        "mean": mean,
        "std": std,
        "rms": float(np.sqrt(np.mean(finite**2))),
        "kurtosis": None if std == 0 else float(np.mean((centered / std) ** 4) - 3),
        "energy": float(np.sum(finite**2)),
    }


def _optional_int(value: str) -> int | None:
    return int(value) if value else None


_STAT_KEYS = ["min", "max", "mean", "std", "rms", "kurtosis", "energy"]
