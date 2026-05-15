"""Estructuracion temporal determinista de senales limpias CWRU."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import UTC, datetime
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

METADATA_FIELDS = [
    "window_id",
    "file_id",
    "window_index",
    "start",
    "end",
    "split",
    "label",
    "target",
    "fault_type",
    "sample_rate_hz",
    "channel",
]


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
                name="cwru_windows_features",
                artifact_type="features",
                path=summary["features_path"],
                producer="structuring_executor",
                metadata={"n_windows": summary["n_windows"]},
            ),
            ArtifactRef(
                name="cwru_windows_raw",
                artifact_type="tensors",
                path=summary["tensors_path"],
                producer="structuring_executor",
                metadata={"window_size": cfg.window_size},
            ),
            ArtifactRef(
                name="cwru_windows_splits",
                artifact_type="splits",
                path=summary["splits_path"],
                producer="structuring_executor",
                metadata=summary["window_counts"],
            ),
        ]
        return StructuringResult(
            executor_name="structuring",
            status="success",
            message="CWRU temporal structure generated.",
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
            message="CWRU temporal structuring failed.",
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

    split_by_file = _assign_splits(files)
    rows, windows = _window_files(files, split_by_file, config)
    if not rows:
        raise ValueError("no windows generated; check window_size and clean signals")

    features_path = output / "windows_features.csv"
    tensors_path = output / "windows_raw.npz"
    splits_path = output / "splits.json"
    _write_features(features_path, rows, config.features)
    _write_tensors(tensors_path, rows, windows)
    splits = _split_summary(rows, split_by_file, config)
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
        return {
            "path": path,
            "signal": np.asarray(data["signal"], dtype=np.float32).ravel(),
            "file_id": str(data["file_id"].item()),
            "label": str(data["label"].item()),
            "fault_type": str(data["fault_type"].item() or ""),
            "sample_rate_hz": sample_rate,
            "channel": channel,
        }


def _path_key(path: Path) -> int | str:
    return int(path.stem) if path.stem.isdigit() else path.stem


def _assign_splits(files: list[dict[str, Any]]) -> dict[str, str]:
    normal_ids = [item["file_id"] for item in files if item["label"] == "normal"]
    n_train = max(1, int(len(normal_ids) * 0.6)) if normal_ids else 0
    remaining = len(normal_ids) - n_train
    n_val = 1 if remaining > 1 else remaining
    train = set(normal_ids[:n_train])
    validation = set(normal_ids[n_train : n_train + n_val])
    return {
        item["file_id"]: (
            "train"
            if item["file_id"] in train
            else "validation"
            if item["file_id"] in validation
            else "test"
        )
        for item in files
    }


def _window_files(
    files: list[dict[str, Any]],
    split_by_file: dict[str, str],
    config: StructuringConfig,
) -> tuple[list[dict[str, Any]], list[np.ndarray]]:
    rows: list[dict[str, Any]] = []
    windows: list[np.ndarray] = []
    step = max(1, int(config.window_size * (1 - config.overlap)))
    for item in files:
        signal = item["signal"]
        for index, start in enumerate(range(0, signal.size - config.window_size + 1, step)):
            window = signal[start : start + config.window_size]
            row = _metadata_row(item, index, start, split_by_file[item["file_id"]], config)
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
) -> dict[str, Any]:
    file_id = item["file_id"]
    target = 0 if item["label"] == "normal" else 1
    if config.label_mode == "fault_type":
        target = item["fault_type"] or "normal"
    return {
        "window_id": f"{file_id}_{index:06d}",
        "file_id": file_id,
        "window_index": index,
        "start": start,
        "end": start + config.window_size,
        "split": split,
        "label": item["label"],
        "target": target,
        "fault_type": item["fault_type"],
        "sample_rate_hz": item["sample_rate_hz"],
        "channel": item["channel"],
    }


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
        splits=np.asarray([row["split"] for row in rows]),
        labels=np.asarray([row["label"] for row in rows]),
        targets=np.asarray([row["target"] for row in rows]),
    )


def _split_summary(
    rows: list[dict[str, Any]],
    split_by_file: dict[str, str],
    config: StructuringConfig,
) -> dict[str, Any]:
    labels_by_split: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        labels_by_split[row["split"]][row["label"]] += 1
    return {
        "strategy": "file_level_normal_train_fault_test",
        "generated_at": datetime.now(UTC).isoformat(),
        "config": config.model_dump(mode="json"),
        "files": {
            split: sorted(file_id for file_id, value in split_by_file.items() if value == split)
            for split in ["train", "validation", "test"]
        },
        "window_counts": dict(Counter(row["split"] for row in rows)),
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
