"""Perfilado determinista de manifiestos de senal."""

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
            name=f"{profile['dataset']}_profile",
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
            message="Data profile generated.",
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
            message="Data profiling failed.",
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
    dataset = manifest[0].get("dataset") or "unknown"
    decision_summary = _build_agent_decision_summary(files, channel_names)
    return {
        "dataset": dataset,
        "manifest_format": _manifest_format(manifest[0]),
        "manifest_path": str(manifest_path),
        "generated_at": datetime.now(UTC).isoformat(),
        "n_files": len(files),
        "label_counts": dict(Counter(row["label"] for row in manifest)),
        "fault_type_counts": dict(
            Counter(_count_value(row.get("fault_type")) for row in manifest)
        ),
        "label_detail_counts": dict(
            Counter(_count_value(row.get("label_detail")) for row in manifest)
        ),
        "load_counts": dict(
            Counter(_count_value(row.get("load_hp")) for row in manifest)
        ),
        "run_counts": dict(
            Counter(row.get("run_id", "") for row in manifest if row.get("run_id"))
        ),
        "condition_counts": dict(
            Counter(
                row.get("condition_id", "")
                for row in manifest
                if row.get("condition_id")
            )
        ),
        "sample_rate_counts": dict(
            Counter(_sample_rate_key(row) for row in manifest)
        ),
        "channels_detected": channel_names,
        "decision_summary": decision_summary,
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
    sample_rate = _row_number(row, "source_sample_rate_hz", "sampling_rate_hz")
    target_sample_rate = _row_number(row, "target_sample_rate_hz")
    metadata = _json_object(row.get("metadata_json"))
    expected_n_samples = _expected_n_samples(metadata, sample_rate)

    return {
        "file_id": _record_id(row),
        "record_id": _record_id(row),
        "dataset": row.get("dataset") or "unknown",
        "source_path": row["source_path"],
        "source_format": row.get("source_format") or None,
        "label": row["label"],
        "fault_type": _optional_text(row.get("fault_type")),
        "label_detail": _optional_text(row.get("label_detail")),
        "condition_id": _optional_text(row.get("condition_id")),
        "asset_id": _optional_text(row.get("asset_id")),
        "run_id": _optional_text(row.get("run_id")),
        "timestamp_start": _optional_text(row.get("timestamp_start")),
        "timestamp_end": _optional_text(row.get("timestamp_end")),
        "load_hp": _optional_int(row.get("load_hp")),
        "rpm": _optional_int(row.get("rpm")),
        "source_sample_rate_hz": sample_rate,
        "sampling_rate_hz": sample_rate,
        "target_sample_rate_hz": target_sample_rate,
        "primary_channel": _primary_channel(row),
        "manifest_channel_names": _json_list(row.get("channel_names")),
        "n_channels_manifest": _optional_int(row.get("n_channels")),
        "expected_n_samples": expected_n_samples,
        "metadata": metadata,
        "channels": channels,
    }


def _channel_stats(
    source_key: str,
    values: np.ndarray,
    shape: tuple[int, ...],
) -> dict[str, Any]:
    array = np.asarray(values, dtype=float).ravel()
    finite = array[np.isfinite(array)]
    stats = {
        "source_key": source_key,
        "shape": list(shape),
        "n_samples": int(array.size),
        "non_finite_count": int(array.size - finite.size),
    }
    if finite.size == 0:
        return stats | {
            **{key: None for key in _STAT_KEYS},
            "finite_ratio": 0.0,
            "non_finite_ratio": 1.0 if array.size else 0.0,
            "saturation_ratio": None,
            "drift_score": None,
            "quality_flags": ["no_finite_samples"],
        }

    mean = float(finite.mean())
    std = float(finite.std())
    centered = finite - mean
    non_finite_ratio = float((array.size - finite.size) / array.size)
    saturation_ratio = _saturation_ratio(finite)
    drift_score = _drift_score(array)
    return stats | {
        "min": float(finite.min()),
        "max": float(finite.max()),
        "mean": mean,
        "std": std,
        "rms": float(np.sqrt(np.mean(finite**2))),
        "kurtosis": None if std == 0 else float(np.mean((centered / std) ** 4) - 3),
        "energy": float(np.sum(finite**2)),
        "finite_ratio": float(finite.size / array.size),
        "non_finite_ratio": non_finite_ratio,
        "saturation_ratio": saturation_ratio,
        "drift_score": drift_score,
        "quality_flags": _channel_quality_flags(
            non_finite_ratio=non_finite_ratio,
            std=std,
            saturation_ratio=saturation_ratio,
            drift_score=drift_score,
        ),
    }


def _build_agent_decision_summary(
    files: list[dict[str, Any]],
    channel_names: list[str],
) -> dict[str, Any]:
    candidates = _channel_candidates(files, channel_names)
    viable = [item for item in candidates if not item["blocking"]]
    recommended = [
        item["channel"]
        for item in viable
        if item["quality_score"] >= _RECOMMENDED_CHANNEL_SCORE
    ]
    if not recommended and viable:
        recommended = [viable[0]["channel"]]

    required_actions = _required_actions(files, recommended)
    blocking_warnings = _blocking_warnings(candidates)
    non_blocking_warnings = _non_blocking_warnings(files, candidates, recommended)
    status = _quality_status(
        recommended_channels=recommended,
        required_actions=required_actions,
        blocking_warnings=blocking_warnings,
    )

    return {
        "quality_status": status,
        "required_actions": required_actions,
        "recommended_channels": recommended,
        "candidate_channels": candidates,
        "supported_cleaning_options": _supported_cleaning_options(files, recommended),
        "blocking_warnings": blocking_warnings,
        "non_blocking_warnings": non_blocking_warnings,
        "agent_guidance": (
            "Choose one supported option and justify it from evidence. "
            "If none is adequate, return an unsupported capability or stop."
        ),
    }


def _channel_candidates(
    files: list[dict[str, Any]],
    channel_names: list[str],
) -> list[dict[str, Any]]:
    candidates = [
        _channel_candidate(channel, files)
        for channel in channel_names
    ]
    return sorted(
        candidates,
        key=lambda item: (
            not item["preferred_by_manifest"],
            -item["quality_score"],
            item["channel"],
        ),
    )


def _channel_candidate(channel: str, files: list[dict[str, Any]]) -> dict[str, Any]:
    stats = [
        item["channels"][channel]
        for item in files
        if channel in item["channels"]
    ]
    n_present = len(stats)
    n_files = len(files)
    non_finite_ratios = [float(item.get("non_finite_ratio") or 0.0) for item in stats]
    no_finite_count = _count_flag(stats, "no_finite_samples")
    constant_count = _count_flag(stats, "constant_signal")
    saturated_count = _count_flag(stats, "saturation_warning")
    drift_count = _count_flag(stats, "drift_warning")
    missing_count = n_files - n_present
    preferred_count = sum(item.get("primary_channel") == channel for item in files)
    blocking = n_present == 0 or no_finite_count == n_present or (
        n_present > 0 and constant_count == n_present
    )
    quality_score = _quality_score(
        mean_non_finite_ratio=float(np.mean(non_finite_ratios))
        if non_finite_ratios
        else 1.0,
        missing_ratio=missing_count / n_files if n_files else 1.0,
        no_finite_ratio=no_finite_count / n_present if n_present else 1.0,
        constant_ratio=constant_count / n_present if n_present else 1.0,
        saturated_ratio=saturated_count / n_present if n_present else 0.0,
        drift_ratio=drift_count / n_present if n_present else 0.0,
    )
    warnings = _candidate_warnings(
        missing_count=missing_count,
        no_finite_count=no_finite_count,
        constant_count=constant_count,
        saturated_count=saturated_count,
        drift_count=drift_count,
        non_finite_ratios=non_finite_ratios,
    )
    return {
        "channel": channel,
        "quality_score": quality_score,
        "n_files_present": n_present,
        "preferred_by_manifest": preferred_count > 0,
        "mean_non_finite_ratio": round(float(np.mean(non_finite_ratios)), 6)
        if non_finite_ratios
        else 1.0,
        "max_non_finite_ratio": round(max(non_finite_ratios), 6)
        if non_finite_ratios
        else 1.0,
        "constant_file_count": constant_count,
        "saturated_file_count": saturated_count,
        "drift_warning_count": drift_count,
        "blocking": blocking,
        "warnings": warnings,
        "rationale": _candidate_rationale(channel, quality_score, warnings, blocking),
    }


def _required_actions(
    files: list[dict[str, Any]],
    recommended_channels: list[str],
) -> list[str]:
    actions: list[str] = []
    if _resampling_needed(files):
        actions.append("resample")
    if len(recommended_channels) > 1:
        actions.append("select_channel")
    if _non_finite_present(files):
        actions.append("remove_non_finite")
    return actions


def _quality_status(
    *,
    recommended_channels: list[str],
    required_actions: list[str],
    blocking_warnings: list[str],
) -> str:
    if not recommended_channels or blocking_warnings:
        return "insufficient_quality"
    if "resample" in required_actions:
        return "needs_resampling"
    if "select_channel" in required_actions:
        return "needs_channel_selection"
    return "clean"


def _supported_cleaning_options(
    files: list[dict[str, Any]],
    recommended_channels: list[str],
) -> list[dict[str, Any]]:
    target_rate = _dominant_target_rate(files)
    options = []
    for channel in recommended_channels:
        options.append(
            {
                "option_id": f"clean_{channel}_to_{target_rate}_hz",
                "selected_channel": channel,
                "remove_non_finite": True,
                "resample_to_hz": target_rate,
                "supported_normalizations": ["none", "zscore", "robust"],
                "recommended_normalization": "none",
                "status": "supported",
            }
        )
    return options


def _blocking_warnings(candidates: list[dict[str, Any]]) -> list[str]:
    if any(not item["blocking"] for item in candidates):
        return []
    return ["no_viable_signal_channel"]


def _non_blocking_warnings(
    files: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    recommended_channels: list[str],
) -> list[str]:
    warnings: list[str] = []
    if _resampling_needed(files):
        warnings.append("source_sample_rate_differs_from_target")
    if len(recommended_channels) > 1:
        warnings.append("multiple_viable_channels_require_agent_choice")
    if _non_finite_present(files):
        warnings.append("non_finite_values_detected")
    if any(item["constant_file_count"] for item in candidates):
        warnings.append("constant_channels_detected")
    if any(item["saturated_file_count"] for item in candidates):
        warnings.append("possible_saturation_detected")
    if _sample_count_mismatch(files):
        warnings.append("sample_count_differs_from_manifest_expectation")
    return warnings


def _quality_score(
    *,
    mean_non_finite_ratio: float,
    missing_ratio: float,
    no_finite_ratio: float,
    constant_ratio: float,
    saturated_ratio: float,
    drift_ratio: float,
) -> float:
    penalty = (
        mean_non_finite_ratio * 0.8
        + missing_ratio * 0.5
        + no_finite_ratio * 1.0
        + constant_ratio * 0.7
        + saturated_ratio * 0.2
        + drift_ratio * 0.1
    )
    return round(max(0.0, min(1.0, 1.0 - penalty)), 4)


def _candidate_warnings(
    *,
    missing_count: int,
    no_finite_count: int,
    constant_count: int,
    saturated_count: int,
    drift_count: int,
    non_finite_ratios: list[float],
) -> list[str]:
    warnings: list[str] = []
    if missing_count:
        warnings.append("channel_missing_in_some_files")
    if no_finite_count:
        warnings.append("no_finite_samples")
    if constant_count:
        warnings.append("constant_signal")
    if saturated_count:
        warnings.append("saturation_warning")
    if drift_count:
        warnings.append("drift_warning")
    if any(value > 0.0 for value in non_finite_ratios):
        warnings.append("contains_non_finite")
    return warnings


def _candidate_rationale(
    channel: str,
    quality_score: float,
    warnings: list[str],
    blocking: bool,
) -> str:
    if blocking:
        return f"{channel} is not suitable for automatic cleaning."
    if warnings:
        return (
            f"{channel} is usable with quality_score={quality_score}, "
            f"but requires attention to: {', '.join(warnings)}."
        )
    return f"{channel} is a strong candidate with quality_score={quality_score}."


def _count_flag(stats: list[dict[str, Any]], flag: str) -> int:
    return sum(flag in item.get("quality_flags", []) for item in stats)


def _channel_quality_flags(
    *,
    non_finite_ratio: float,
    std: float,
    saturation_ratio: float | None,
    drift_score: float | None,
) -> list[str]:
    flags: list[str] = []
    if non_finite_ratio > 0.0:
        flags.append("contains_non_finite")
    if non_finite_ratio >= _NON_FINITE_WARNING_RATIO:
        flags.append("non_finite_warning")
    if std == 0.0:
        flags.append("constant_signal")
    if (
        saturation_ratio is not None
        and saturation_ratio >= _SATURATION_WARNING_RATIO
    ):
        flags.append("saturation_warning")
    if drift_score is not None and drift_score >= _DRIFT_WARNING_SCORE:
        flags.append("drift_warning")
    return flags


def _saturation_ratio(finite: np.ndarray) -> float | None:
    if finite.size < _SATURATION_MIN_SAMPLES:
        return None
    min_count = int(np.isclose(finite, finite.min()).sum())
    max_count = int(np.isclose(finite, finite.max()).sum())
    return float(max(min_count, max_count) / finite.size)


def _drift_score(array: np.ndarray) -> float | None:
    if array.size < 4:
        return None
    midpoint = array.size // 2
    first = array[:midpoint]
    second = array[midpoint:]
    first = first[np.isfinite(first)]
    second = second[np.isfinite(second)]
    finite = array[np.isfinite(array)]
    if first.size == 0 or second.size == 0 or finite.size == 0:
        return None
    std = float(finite.std())
    if std == 0.0:
        return 0.0
    return float(abs(second.mean() - first.mean()) / std)


def _expected_n_samples(
    metadata: dict[str, Any],
    sample_rate: float | int | None,
) -> int | None:
    points_per_file = metadata.get("points_per_file")
    if points_per_file is not None:
        return int(points_per_file)
    duration_seconds = metadata.get("snapshot_duration_seconds")
    if duration_seconds is not None and sample_rate is not None:
        return int(round(float(duration_seconds) * float(sample_rate)))
    return None


def _dominant_target_rate(files: list[dict[str, Any]]) -> int | None:
    rates = [
        item.get("target_sample_rate_hz") or item.get("source_sample_rate_hz")
        for item in files
        if item.get("target_sample_rate_hz") or item.get("source_sample_rate_hz")
    ]
    if not rates:
        return None
    counter = Counter(int(rate) for rate in rates)
    return counter.most_common(1)[0][0]


def _resampling_needed(files: list[dict[str, Any]]) -> bool:
    return any(
        item.get("target_sample_rate_hz") is not None
        and item.get("source_sample_rate_hz") is not None
        and item["target_sample_rate_hz"] != item["source_sample_rate_hz"]
        for item in files
    )


def _non_finite_present(files: list[dict[str, Any]]) -> bool:
    return any(
        stats.get("non_finite_count", 0) > 0
        for item in files
        for stats in item["channels"].values()
    )


def _sample_count_mismatch(files: list[dict[str, Any]]) -> bool:
    for item in files:
        expected = item.get("expected_n_samples")
        if expected is None:
            continue
        for stats in item["channels"].values():
            observed = stats.get("n_samples")
            if observed is not None and observed != expected:
                return True
    return False


def _record_id(row: dict[str, str]) -> str:
    return row.get("file_id") or row.get("record_id") or Path(row["source_path"]).stem


def _primary_channel(row: dict[str, str]) -> str | None:
    return _optional_text(row.get("sensor_channel")) or _optional_text(
        row.get("primary_channel")
    )


def _manifest_format(row: dict[str, str]) -> str:
    if "record_id" in row and "channel_names" in row and "sampling_rate_hz" in row:
        return "common"
    return "cwru_legacy"


def _sample_rate_key(row: dict[str, str]) -> str:
    value = _row_number(row, "source_sample_rate_hz", "sampling_rate_hz")
    if value is None:
        return "unknown"
    return str(int(value)) if float(value).is_integer() else str(value)


def _row_number(row: dict[str, str], *keys: str) -> float | int | None:
    for key in keys:
        value = _optional_text(row.get(key))
        if value is None:
            continue
        number = float(value)
        return int(number) if number.is_integer() else number
    return None


def _optional_int(value: str | None) -> int | None:
    text = _optional_text(value)
    if text is None:
        return None
    return int(float(text))


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None


def _count_value(value: str | None) -> str:
    return _optional_text(value) or "none"


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


_STAT_KEYS = ["min", "max", "mean", "std", "rms", "kurtosis", "energy"]
_RECOMMENDED_CHANNEL_SCORE = 0.65
_NON_FINITE_WARNING_RATIO = 0.01
_SATURATION_MIN_SAMPLES = 16
_SATURATION_WARNING_RATIO = 0.25
_DRIFT_WARNING_SCORE = 3.0
