"""Adaptadores ligeros para leer senales desde distintos formatos."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.io import loadmat


@dataclass(frozen=True)
class SignalChannel:
    """Canal numerico normalizado a un vector."""

    name: str
    source_key: str
    values: np.ndarray
    shape: tuple[int, ...]


def read_signal_channels(path: str | Path) -> dict[str, SignalChannel]:
    """Lee todos los canales numericos conocidos de un fichero."""

    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix == ".mat":
        return _read_mat(file_path)
    if suffix in {".csv", ".txt", ".tsv"}:
        return _read_table(file_path)
    if suffix == ".npz":
        return _read_npz(file_path)
    raise ValueError(f"unsupported signal file format: {suffix}")


def load_signal_channel(path: str | Path, channel: str) -> np.ndarray:
    """Carga un canal concreto como vector float."""

    channels = read_signal_channels(path)
    if channel not in channels:
        available = ", ".join(sorted(channels)) or "none"
        raise ValueError(f"channel {channel} not found in {path}; available: {available}")
    return channels[channel].values


def _read_mat(path: Path) -> dict[str, SignalChannel]:
    channels = {}
    for key, value in loadmat(path).items():
        name = _mat_channel_name(key)
        if name is not None:
            channels[name] = _channel(name, key, value)
    return _require_channels(path, channels)


def _read_table(path: Path) -> dict[str, SignalChannel]:
    frame = _read_table_frame(path)
    numeric = frame.apply(pd.to_numeric, errors="coerce").dropna(axis=1, how="all")
    channels = {
        str(column): _channel(str(column), str(column), numeric[column].to_numpy())
        for column in numeric.columns
    }
    return _require_channels(path, channels)


def _read_table_frame(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    frame = pd.read_csv(path, sep=None, engine="python")
    if suffix == ".txt" and frame.shape[1] == 1:
        return pd.read_csv(path, sep=r"\s+", header=None)
    return frame


def _read_npz(path: Path) -> dict[str, SignalChannel]:
    with np.load(path) as data:
        if "signal" in data:
            name = str(data["channel"].item()) if "channel" in data else "signal"
            return {name: _channel(name, "signal", data["signal"])}
        channels = {
            key: _channel(key, key, data[key])
            for key in data.files
            if np.issubdtype(data[key].dtype, np.number)
        }
    return _require_channels(path, channels)


def _channel(name: str, source_key: str, values: np.ndarray) -> SignalChannel:
    array = np.asarray(values, dtype=float)
    return SignalChannel(name, source_key, array.ravel(), tuple(array.shape))


def _mat_channel_name(key: str) -> str | None:
    if key.endswith("_DE_time"):
        return "DE_time"
    if key.endswith("_FE_time"):
        return "FE_time"
    if key.endswith("_BA_time"):
        return "BA_time"
    if key.endswith("RPM"):
        return "RPM"
    return None


def _require_channels(path: Path, channels: dict[str, SignalChannel]) -> dict[str, SignalChannel]:
    if not channels:
        raise ValueError(f"no numeric signal channels found in {path}")
    return channels
