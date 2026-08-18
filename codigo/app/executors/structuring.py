"""Estructuracion temporal determinista de senales limpias."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from codigo.app.schemas.executor_results import StructuringResult
from codigo.app.schemas.state import ArtifactRef, PipelineError, StructuringConfig


DEFAULT_STRUCTURING_CONFIG = StructuringConfig(
    window_size=2048,
    overlap=0.5,
    main_channel="DE_time",
    target_sample_rate_hz=12000,
    label_mode="binary_anomaly",
)

SUPPORTED_WINDOW_SIZES = (1024, 2048, 4096)
SUPPORTED_OVERLAPS = (0.25, 0.5, 0.75)
TIME_DOMAIN_BASELINE_FEATURES = [
    "mean",
    "std",
    "rms",
    "min",
    "max",
    "peak_to_peak",
    "energy",
]
TIME_DOMAIN_FULL_FEATURES = [
    "mean",
    "std",
    "rms",
    "min",
    "max",
    "peak_to_peak",
    "skewness",
    "kurtosis",
    "crest_factor",
    "energy",
]

METADATA_FIELDS = [
    "window_id",
    "file_id",
    "source_path",
    "condition_id",
    "asset_id",
    "run_id",
    "label_source",
    "label_granularity",
    "window_index",
    "start",
    "end",
    "timestamp_start",
    "timestamp_end",
    "time_since_start_seconds",
    "time_to_failure_seconds",
    "relative_life",
    "temporal_partition",
    "split",
    "label",
    "target",
    "fault_type",
    "sample_rate_hz",
    "channel",
]


def build_structuring_decision_summary(
    clean_dir: str | Path,
    *,
    dataset: str = "unknown",
    target_sample_rate_hz: int | None = None,
    main_channel: str | None = None,
    allowed_split_hints: set[str] | None = None,
) -> dict[str, Any]:
    """Resume senales limpias y propone configuraciones temporales soportadas."""

    clean_path = Path(clean_dir)
    files = [
        _load_clean_file_metadata(path)
        for path in sorted(clean_path.glob("*.npz"), key=_path_key)
    ]
    if allowed_split_hints is not None:
        files = [
            item
            for item in files
            if item.get("split_hint") in allowed_split_hints
        ]
    if not files:
        return {
            "available": False,
            "path": str(clean_path),
            "quality_status": "insufficient_inputs",
            "blocking_warnings": ["no_clean_npz_files"],
            "non_blocking_warnings": [],
            "candidate_configurations": [],
            "unsupported_capabilities": [],
        }

    summary = _clean_files_summary(files)
    candidate_configurations = _structuring_candidates(
        files,
        target_sample_rate_hz=target_sample_rate_hz,
        main_channel=main_channel,
    )
    blocking_warnings = _structuring_blocking_warnings(
        summary,
        candidate_configurations,
        target_sample_rate_hz=target_sample_rate_hz,
        main_channel=main_channel,
    )
    non_blocking_warnings = _structuring_non_blocking_warnings(
        dataset,
        summary,
        candidate_configurations,
    )
    return {
        "available": True,
        "path": str(clean_path),
        "quality_status": "ready" if not blocking_warnings else "blocked",
        "required_actions": ["select_window_configuration"],
        "summary": summary,
        "candidate_configurations": candidate_configurations,
        "recommended_configuration_id": (
            candidate_configurations[0]["configuration_id"]
            if candidate_configurations and not blocking_warnings
            else None
        ),
        "supported_feature_sets": _supported_feature_sets(),
        "unsupported_capabilities": _unsupported_structuring_capabilities(
            dataset,
            has_temporal_split=bool(summary.get("split_hint_counts")),
        ),
        "blocking_warnings": blocking_warnings,
        "non_blocking_warnings": non_blocking_warnings,
        "agent_guidance": (
            "Choose one supported configuration and justify the trade-off between "
            "temporal resolution, number of windows, cost and leakage risk."
        ),
    }


def generate_temporal_structure(
    clean_dir: str | Path = "codigo/data/processed/cwru_bearing/clean_signals",
    output_dir: str | Path = "codigo/data/tensors/cwru_bearing",
    config: StructuringConfig | None = None,
) -> StructuringResult:
    """Genera features, tensores y particiones desde senales limpias."""

    started_at = datetime.now(UTC)
    output = Path(output_dir)
    features_path = output / "windows_features.csv"
    tensors_path = output / "windows_raw.npz"
    splits_path = output / "splits.json"
    cfg = config or DEFAULT_STRUCTURING_CONFIG
    try:
        summary = build_temporal_dataset(clean_dir, output, cfg)
        artifacts = [
            ArtifactRef(
                name="windows_features",
                artifact_type="features",
                path=summary["features_path"],
                producer="structuring_executor",
                metadata={"n_windows": summary["n_windows"]},
            ),
            ArtifactRef(
                name="windows_raw",
                artifact_type="tensors",
                path=summary["tensors_path"],
                producer="structuring_executor",
                metadata={"window_size": cfg.window_size},
            ),
            ArtifactRef(
                name="windows_splits",
                artifact_type="splits",
                path=summary["splits_path"],
                producer="structuring_executor",
                metadata=summary["window_counts"],
            ),
        ]
        return StructuringResult(
            executor_name="structuring",
            status="success",
            message="Temporal structure generated.",
            artifacts=artifacts,
            errors=[],
            state_updates={
                "tensor_path": summary["tensors_path"],
                "splits_path": summary["splits_path"],
            },
            started_at=started_at,
            finished_at=datetime.now(UTC),
            features_path=summary["features_path"],
            tensors_path=summary["tensors_path"],
            splits_path=summary["splits_path"],
            n_windows=summary["n_windows"],
        )
    except Exception as exc:
        error = PipelineError(
            stage="structuring",
            node="structuring_executor",
            message=str(exc),
            recoverable=True,
        )
        return StructuringResult(
            executor_name="structuring",
            status="failed",
            message="Temporal structuring failed.",
            artifacts=[],
            errors=[error],
            state_updates={},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            features_path=str(features_path),
            tensors_path=str(tensors_path),
            splits_path=str(splits_path),
            n_windows=0,
        )


def build_temporal_dataset(
    clean_dir: str | Path,
    output_dir: str | Path,
    config: StructuringConfig = DEFAULT_STRUCTURING_CONFIG,
) -> dict[str, Any]:
    """Crea ventanas crudas, features tabulares y split reproducible."""

    files = [_load_clean_file(path, config) for path in sorted(Path(clean_dir).glob("*.npz"), key=_path_key)]
    if not files:
        raise ValueError(f"no clean .npz files found in {clean_dir}")

    _validate_features(config.features)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    split_by_file, split_strategy = _assign_splits(files)
    rows, windows = _window_files(files, split_by_file, config)
    if not rows:
        raise ValueError("no windows generated; check window_size and clean signals")

    features_path = output / "windows_features.csv"
    tensors_path = output / "windows_raw.npz"
    splits_path = output / "splits.json"
    _write_features(features_path, rows, config.features)
    _write_tensors(tensors_path, rows, windows)
    splits = _split_summary(rows, split_by_file, config, strategy=split_strategy)
    splits_path.write_text(json.dumps(splits, indent=2), encoding="utf-8")

    return {
        "features_path": str(features_path),
        "tensors_path": str(tensors_path),
        "splits_path": str(splits_path),
        "n_windows": len(rows),
        "window_counts": splits["window_counts"],
    }


def _load_clean_file(path: Path, config: StructuringConfig) -> dict[str, Any]:
    with np.load(path) as data:
        sample_rate = int(data["sample_rate_hz"].item())
        channel = str(data["channel"].item())
        if sample_rate != config.target_sample_rate_hz:
            raise ValueError(f"{path.name} sample_rate_hz={sample_rate}, expected {config.target_sample_rate_hz}")
        if channel != config.main_channel:
            raise ValueError(f"{path.name} channel={channel}, expected {config.main_channel}")
        metadata = _clean_metadata(data)
        return {
            "path": path,
            "signal": np.asarray(data["signal"], dtype=np.float32).ravel(),
            "file_id": str(data["file_id"].item()),
            "source_path": _npz_text(data, "source_path", ""),
            "label": str(data["label"].item()),
            "fault_type": str(data["fault_type"].item() or ""),
            "condition_id": _npz_text(data, "condition_id", ""),
            "asset_id": _npz_text(data, "asset_id", ""),
            "run_id": _npz_text(data, "run_id", ""),
            "timestamp_start": _parse_datetime(_npz_text(data, "timestamp_start", "")),
            "timestamp_end": _parse_datetime(_npz_text(data, "timestamp_end", "")),
            "sample_rate_hz": sample_rate,
            "channel": channel,
            "metadata_json": metadata,
            "split_hint": _split_hint(metadata),
        }


def _load_clean_file_metadata(path: Path) -> dict[str, Any]:
    with np.load(path) as data:
        signal = np.asarray(data["signal"], dtype=np.float32).ravel()
        metadata = _clean_metadata(data)
        return {
            "path": path,
            "file_id": str(data["file_id"].item()),
            "dataset": _npz_text(data, "dataset", "unknown"),
            "label": str(data["label"].item()),
            "fault_type": _npz_text(data, "fault_type", ""),
            "condition_id": _npz_text(data, "condition_id", ""),
            "asset_id": _npz_text(data, "asset_id", ""),
            "run_id": _npz_text(data, "run_id", ""),
            "timestamp_start": _parse_datetime(_npz_text(data, "timestamp_start", "")),
            "timestamp_end": _parse_datetime(_npz_text(data, "timestamp_end", "")),
            "sample_rate_hz": int(data["sample_rate_hz"].item()),
            "channel": str(data["channel"].item()),
            "n_samples": int(signal.size),
            "split_hint": _split_hint(metadata),
        }


def _path_key(path: Path) -> int | str:
    return int(path.stem) if path.stem.isdigit() else path.stem


def _clean_files_summary(files: list[dict[str, Any]]) -> dict[str, Any]:
    n_samples = [item["n_samples"] for item in files]
    return {
        "n_clean_files": len(files),
        "sample_rate_counts": dict(
            Counter(str(item["sample_rate_hz"]) for item in files)
        ),
        "channel_counts": dict(Counter(item["channel"] for item in files)),
        "label_counts": dict(Counter(item["label"] for item in files)),
        "run_counts": dict(
            Counter(item["run_id"] for item in files if item.get("run_id"))
        ),
        "condition_counts": dict(
            Counter(
                item["condition_id"]
                for item in files
                if item.get("condition_id")
            )
        ),
        "split_hint_counts": dict(
            Counter(
                item["split_hint"]
                for item in files
                if item.get("split_hint")
            )
        ),
        "min_samples": min(n_samples),
        "median_samples": int(np.median(n_samples)),
        "max_samples": max(n_samples),
    }


def _structuring_candidates(
    files: list[dict[str, Any]],
    *,
    target_sample_rate_hz: int | None,
    main_channel: str | None,
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for window_size in SUPPORTED_WINDOW_SIZES:
        for overlap in SUPPORTED_OVERLAPS:
            candidate = _structuring_candidate(
                files,
                window_size=window_size,
                overlap=overlap,
                target_sample_rate_hz=target_sample_rate_hz,
                main_channel=main_channel,
            )
            if candidate["estimated_total_windows"] > 0:
                candidates.append(candidate)
    return sorted(
        candidates,
        key=lambda item: (
            _cost_rank(item["cost_level"]),
            abs(item["window_size"] - DEFAULT_STRUCTURING_CONFIG.window_size),
            -item["estimated_total_windows"],
            item["overlap"],
        ),
    )


def _structuring_candidate(
    files: list[dict[str, Any]],
    *,
    window_size: int,
    overlap: float,
    target_sample_rate_hz: int | None,
    main_channel: str | None,
) -> dict[str, Any]:
    step_samples = max(1, int(window_size * (1 - overlap)))
    window_counts = [
        _estimated_windows(item["n_samples"], window_size, step_samples)
        for item in files
    ]
    total_windows = int(sum(window_counts))
    sample_rate = target_sample_rate_hz or files[0]["sample_rate_hz"]
    warnings = _candidate_warnings(
        files,
        window_size=window_size,
        total_windows=total_windows,
        target_sample_rate_hz=target_sample_rate_hz,
        main_channel=main_channel,
    )
    return {
        "configuration_id": f"win_{window_size}_ov_{int(overlap * 100):02d}",
        "window_size": window_size,
        "overlap": overlap,
        "step_samples": step_samples,
        "duration_seconds": round(window_size / sample_rate, 6)
        if sample_rate
        else None,
        "estimated_total_windows": total_windows,
        "min_windows_per_file": min(window_counts) if window_counts else 0,
        "max_windows_per_file": max(window_counts) if window_counts else 0,
        "estimated_cost_units": int(total_windows * window_size),
        "cost_level": _cost_level(total_windows * window_size),
        "supported_feature_sets": ["time_domain_baseline", "time_domain_full"],
        "recommended_feature_set": "time_domain_full",
        "leakage_warnings": _leakage_warnings(files),
        "warnings": warnings,
        "status": "supported" if total_windows > 0 else "unsupported",
    }


def _estimated_windows(n_samples: int, window_size: int, step_samples: int) -> int:
    if n_samples < window_size:
        return 0
    return 1 + ((n_samples - window_size) // step_samples)


def _candidate_warnings(
    files: list[dict[str, Any]],
    *,
    window_size: int,
    total_windows: int,
    target_sample_rate_hz: int | None,
    main_channel: str | None,
) -> list[str]:
    warnings: list[str] = []
    if total_windows == 0:
        warnings.append("window_too_large_for_clean_signals")
    if target_sample_rate_hz and any(
        item["sample_rate_hz"] != target_sample_rate_hz for item in files
    ):
        warnings.append("sample_rate_mismatch")
    if main_channel and any(item["channel"] != main_channel for item in files):
        warnings.append("channel_mismatch")
    if any(item["n_samples"] < window_size * 2 for item in files):
        warnings.append("low_windows_per_file")
    return warnings


def _structuring_blocking_warnings(
    summary: dict[str, Any],
    candidate_configurations: list[dict[str, Any]],
    *,
    target_sample_rate_hz: int | None,
    main_channel: str | None,
) -> list[str]:
    warnings: list[str] = []
    if not candidate_configurations:
        warnings.append("no_supported_window_configuration")
    if target_sample_rate_hz and set(summary["sample_rate_counts"]) != {
        str(target_sample_rate_hz)
    }:
        warnings.append("clean_sample_rate_does_not_match_target")
    if main_channel and set(summary["channel_counts"]) != {main_channel}:
        warnings.append("clean_channel_does_not_match_main_channel")
    return warnings


def _structuring_non_blocking_warnings(
    dataset: str,
    summary: dict[str, Any],
    candidate_configurations: list[dict[str, Any]],
) -> list[str]:
    warnings: list[str] = []
    if len(summary["label_counts"]) == 1 and "unknown" in summary["label_counts"]:
        warnings.append("labels_unknown_structuring_only")
    if summary["run_counts"]:
        warnings.append("preserve_run_boundaries_to_avoid_leakage")
    if dataset == "nasa_ims_bearing" and not summary.get("split_hint_counts"):
        warnings.append("requires_temporal_split_policy_before_modeling")
    elif dataset == "nasa_ims_bearing":
        warnings.append("uses_manifest_split_hints_from_temporal_policy")
    if candidate_configurations and candidate_configurations[0]["cost_level"] != "low":
        warnings.append("windowing_cost_not_low")
    return warnings


def _leakage_warnings(files: list[dict[str, Any]]) -> list[str]:
    warnings = ["split_by_file_before_windowing"]
    if any(item.get("run_id") for item in files):
        warnings.append("split_by_run_or_time_for_run_to_failure_data")
    if all(item["label"] == "unknown" for item in files):
        warnings.append("do_not_train_supervised_model_without_label_policy")
    return warnings


def _supported_feature_sets() -> list[dict[str, Any]]:
    return [
        {
            "feature_set_id": "time_domain_baseline",
            "features": TIME_DOMAIN_BASELINE_FEATURES,
            "status": "supported",
        },
        {
            "feature_set_id": "time_domain_full",
            "features": TIME_DOMAIN_FULL_FEATURES,
            "status": "supported",
        },
    ]


def _unsupported_structuring_capabilities(
    dataset: str,
    *,
    has_temporal_split: bool = False,
) -> list[dict[str, str]]:
    capabilities = [
        {
            "capability": "frequency_domain_features",
            "status": "unsupported",
            "next_action": "implement_feature_executor",
        }
    ]
    if dataset == "nasa_ims_bearing" and not has_temporal_split:
        capabilities.append(
            {
                "capability": "run_to_failure_temporal_split",
                "status": "unsupported",
                "next_action": "define_temporal_split_policy",
            }
        )
    return capabilities


def _cost_level(cost_units: int) -> str:
    if cost_units <= 1_000_000:
        return "low"
    if cost_units <= 10_000_000:
        return "medium"
    return "high"


def _cost_rank(level: str) -> int:
    return {"low": 0, "medium": 1, "high": 2}.get(level, 99)


def _npz_text(data: Any, key: str, default: str) -> str:
    if key not in data.files:
        return default
    value = str(data[key].item())
    return value or default


def _clean_metadata(data: Any) -> dict[str, Any]:
    if "metadata_json" not in data.files:
        return {}
    text = str(data["metadata_json"].item() or "").strip()
    if not text:
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("clean metadata_json must be a JSON object")
    return parsed


def _split_hint(metadata: dict[str, Any]) -> str | None:
    value = metadata.get("split_hint")
    if value is None:
        return None
    text = str(value).strip()
    if text not in {"train", "validation", "test"}:
        raise ValueError(f"unsupported split_hint: {text}")
    return text


def _assign_splits(files: list[dict[str, Any]]) -> tuple[dict[str, str], str]:
    hinted = {item["file_id"]: item.get("split_hint") for item in files}
    if hinted and all(value in {"train", "validation", "test"} for value in hinted.values()):
        return (
            {file_id: str(split) for file_id, split in hinted.items()},
            "metadata_json_split_hint",
        )

    normal_ids = [item["file_id"] for item in files if item["label"] == "normal"]
    n_train = max(1, int(len(normal_ids) * 0.6)) if normal_ids else 0
    remaining = len(normal_ids) - n_train
    n_val = 1 if remaining > 1 else remaining
    train = set(normal_ids[:n_train])
    validation = set(normal_ids[n_train : n_train + n_val])
    return (
        {
            item["file_id"]: (
                "train"
                if item["file_id"] in train
                else "validation"
                if item["file_id"] in validation
                else "test"
            )
            for item in files
        },
        "file_level_normal_train_fault_test",
    )


def _window_files(
    files: list[dict[str, Any]],
    split_by_file: dict[str, str],
    config: StructuringConfig,
) -> tuple[list[dict[str, Any]], list[np.ndarray]]:
    rows: list[dict[str, Any]] = []
    windows: list[np.ndarray] = []
    step = max(1, int(config.window_size * (1 - config.overlap)))
    temporal_context = _temporal_context(files)
    for item in files:
        signal = item["signal"]
        for index, start in enumerate(range(0, signal.size - config.window_size + 1, step)):
            window = signal[start : start + config.window_size]
            row = _metadata_row(
                item,
                index,
                start,
                split_by_file[item["file_id"]],
                config,
                temporal_context,
            )
            row.update(_feature_values(window, config.features))
            rows.append(row)
            windows.append(window)
    return rows, windows


def _metadata_row(
    item: dict[str, Any],
    index: int,
    start: int,
    split: str,
    config: StructuringConfig,
    temporal_context: dict[str, dict[str, datetime | None]],
) -> dict[str, Any]:
    file_id = item["file_id"]
    target: int | str
    if item["label"] == "normal":
        target = 0
    elif item["label"] in {"anomaly", "degradation", "fault"}:
        target = 1
    else:
        target = ""
    if config.label_mode == "fault_type":
        target = item["fault_type"] or "normal"
    window_start = _window_timestamp(item.get("timestamp_start"), start, item["sample_rate_hz"])
    window_end = _window_timestamp(
        item.get("timestamp_start"),
        start + config.window_size,
        item["sample_rate_hz"],
    )
    temporal = _window_temporal_metrics(item, window_start, temporal_context)
    return {
        "window_id": f"{file_id}_{index:06d}",
        "file_id": file_id,
        "source_path": item.get("source_path", ""),
        "condition_id": item.get("condition_id", ""),
        "asset_id": item.get("asset_id", ""),
        "run_id": item.get("run_id", ""),
        "label_source": item.get("metadata_json", {}).get("label_source", ""),
        "label_granularity": item.get("metadata_json", {}).get(
            "label_granularity",
            "",
        ),
        "window_index": index,
        "start": start,
        "end": start + config.window_size,
        "timestamp_start": _datetime_text(window_start),
        "timestamp_end": _datetime_text(window_end),
        "time_since_start_seconds": temporal["time_since_start_seconds"],
        "time_to_failure_seconds": temporal["time_to_failure_seconds"],
        "relative_life": temporal["relative_life"],
        "temporal_partition": item.get("metadata_json", {}).get(
            "temporal_partition",
            "",
        ),
        "split": split,
        "label": item["label"],
        "target": target,
        "fault_type": item["fault_type"],
        "sample_rate_hz": item["sample_rate_hz"],
        "channel": item["channel"],
    }


def _temporal_context(
    files: list[dict[str, Any]],
) -> dict[str, dict[str, datetime | None]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in files:
        grouped[_temporal_group_id(item)].append(item)

    context: dict[str, dict[str, datetime | None]] = {}
    for group_id, group_items in grouped.items():
        starts = [
            timestamp
            for item in group_items
            for timestamp in [item.get("timestamp_start")]
            if isinstance(timestamp, datetime)
        ]
        failures = [
            failure
            for item in group_items
            for failure in [_parse_datetime(item["metadata_json"].get("failure_event_time"))]
            if failure is not None
        ]
        context[group_id] = {
            "run_start": min(starts) if starts else None,
            "failure_event_time": max(failures) if failures else None,
        }
    return context


def _window_temporal_metrics(
    item: dict[str, Any],
    window_start: datetime | None,
    temporal_context: dict[str, dict[str, datetime | None]],
) -> dict[str, float | None]:
    context = temporal_context.get(_temporal_group_id(item), {})
    run_start = context.get("run_start")
    failure_event_time = context.get("failure_event_time")
    time_since_start = _seconds_between(run_start, window_start)
    time_to_failure = _seconds_between(window_start, failure_event_time)
    relative_life = None
    total_life = _seconds_between(run_start, failure_event_time)
    if (
        time_since_start is not None
        and total_life is not None
        and total_life > 0
    ):
        relative_life = min(1.0, max(0.0, time_since_start / total_life))
    return {
        "time_since_start_seconds": time_since_start,
        "time_to_failure_seconds": time_to_failure,
        "relative_life": relative_life,
    }


def _temporal_group_id(item: dict[str, Any]) -> str:
    return str(item.get("run_id") or item.get("file_id") or "unknown_run")


def _window_timestamp(
    base: datetime | None,
    sample_offset: int,
    sample_rate_hz: int | float,
) -> datetime | None:
    if base is None or sample_rate_hz <= 0:
        return None
    return base + timedelta(seconds=sample_offset / float(sample_rate_hz))


def _seconds_between(
    start: datetime | None,
    end: datetime | None,
) -> float | None:
    if start is None or end is None:
        return None
    return float((end - start).total_seconds())


def _parse_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is not None:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed


def _datetime_text(value: datetime | None) -> str:
    return "" if value is None else value.isoformat()


def _feature_values(window: np.ndarray, names: list[str]) -> dict[str, float]:
    mean = float(window.mean())
    std = float(window.std())
    centered = window - mean
    rms = float(np.sqrt(np.mean(window**2)))
    peak = float(np.max(np.abs(window)))
    values = {
        "mean": mean,
        "std": std,
        "rms": rms,
        "min": float(window.min()),
        "max": float(window.max()),
        "peak_to_peak": float(window.max() - window.min()),
        "skewness": 0.0 if std == 0 else float(np.mean((centered / std) ** 3)),
        "kurtosis": 0.0 if std == 0 else float(np.mean((centered / std) ** 4) - 3),
        "crest_factor": 0.0 if rms == 0 else peak / rms,
        "energy": float(np.sum(window**2)),
    }
    return {name: values[name] for name in names}


def _validate_features(names: list[str]) -> None:
    unsupported = sorted(set(names) - set(_SUPPORTED_FEATURES))
    if unsupported:
        raise ValueError(f"unsupported features: {', '.join(unsupported)}")


def _write_features(path: Path, rows: list[dict[str, Any]], features: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=METADATA_FIELDS + features)
        writer.writeheader()
        writer.writerows(rows)


def _write_tensors(path: Path, rows: list[dict[str, Any]], windows: list[np.ndarray]) -> None:
    np.savez_compressed(
        path,
        windows=np.asarray(windows, dtype=np.float32),
        window_ids=np.asarray([row["window_id"] for row in rows]),
        file_ids=np.asarray([row["file_id"] for row in rows]),
        temporal_partitions=np.asarray(
            [row["temporal_partition"] for row in rows]
        ),
        splits=np.asarray([row["split"] for row in rows]),
        labels=np.asarray([row["label"] for row in rows]),
        targets=np.asarray([row["target"] for row in rows]),
    )


def _split_summary(
    rows: list[dict[str, Any]],
    split_by_file: dict[str, str],
    config: StructuringConfig,
    *,
    strategy: str,
) -> dict[str, Any]:
    labels_by_split: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        labels_by_split[row["split"]][row["label"]] += 1
    return {
        "strategy": strategy,
        "generated_at": datetime.now(UTC).isoformat(),
        "config": config.model_dump(mode="json"),
        "files": {
            split: sorted(file_id for file_id, value in split_by_file.items() if value == split)
            for split in ["train", "validation", "test"]
        },
        "window_counts": dict(Counter(row["split"] for row in rows)),
        "temporal_partition_counts": dict(
            Counter(
                str(row["temporal_partition"])
                for row in rows
                if row.get("temporal_partition")
            )
        ),
        "label_counts_by_split": {
            split: dict(counter) for split, counter in labels_by_split.items()
        },
    }


_SUPPORTED_FEATURES = {
    "mean",
    "std",
    "rms",
    "min",
    "max",
    "peak_to_peak",
    "skewness",
    "kurtosis",
    "crest_factor",
    "energy",
}
