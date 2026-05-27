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
    if suffix in {".csv", ".txt", ".tsv"} or _looks_like_nasa_ims_file(
        file_path
    ):
        return _read_table(file_path)
    if suffix == ".npz":
        return _read_npz(file_path)
    raise ValueError(f"unsupported signal file format: {suffix}")


def read_signal_frame(path: str | Path) -> pd.DataFrame:
    """Lee ficheros tabulares de senal como `DataFrame` numerico."""

    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix in {".csv", ".txt", ".tsv"} or _looks_like_nasa_ims_file(
        file_path
    ):
        return _read_table_frame(file_path)
    raise ValueError(f"unsupported tabular signal file format: {suffix}")


def load_signal_channel(path: str | Path, channel: str) -> np.ndarray:
    """Carga un canal concreto como vector float."""

    channels = read_signal_channels(path)
    if channel not in channels:
        available = ", ".join(sorted(channels)) or "none"
        raise ValueError(
            f"channel {channel} not found in {path}; available: {available}"
        )
    return channels[channel].values


def _read_mat(path: Path) -> dict[str, SignalChannel]:
    channels = {}
    for key, value in loadmat(path).items():
        name = _mat_channel_name(key)
        if name is not None:
            channels[name] = _channel(name, key, value)
    return _require_channels(path, channels)


def _read_table(path: Path) -> dict[str, SignalChannel]:
    frame = read_signal_frame(path)
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
    first_line = _first_non_empty_line(path)
    if first_line and _line_has_numeric_values(first_line):
        return _read_numeric_table_without_header(path, first_line)
    if first_line and "\t" in first_line:
        return pd.read_csv(path, sep="\t")
    if first_line and "," in first_line:
        return pd.read_csv(path)
    return pd.read_csv(path, sep=r"\s+")


def _read_numeric_table_without_header(path: Path, first_line: str) -> pd.DataFrame:
    if "\t" in first_line:
        frame = pd.read_csv(path, sep="\t", header=None)
    elif "," in first_line:
        frame = pd.read_csv(path, header=None)
    else:
        frame = pd.read_csv(path, sep=r"\s+", header=None)
    frame.columns = [f"channel_{index}" for index in range(1, frame.shape[1] + 1)]
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


def _require_channels(
    path: Path,
    channels: dict[str, SignalChannel],
) -> dict[str, SignalChannel]:
    if not channels:
        raise ValueError(f"no numeric signal channels found in {path}")
    return channels


def _first_non_empty_line(path: Path) -> str | None:
    try:
        with path.open(encoding="utf-8") as file:
            for line in file:
                stripped = line.strip()
                if stripped:
                    return stripped
    except OSError:
        return None
    return None


def _line_has_numeric_values(line: str) -> bool:
    parts = _split_table_line(line)
    return bool(parts) and all(_is_number(part) for part in parts)


def _split_table_line(line: str) -> list[str]:
    if "\t" in line:
        parts = line.split("\t")
    elif "," in line:
        parts = line.split(",")
    else:
        parts = line.split()
    return [part.strip() for part in parts if part.strip()]


def _looks_like_nasa_ims_file(path: Path) -> bool:
    name = (
        path.stem
        if path.suffix.lower() in {".txt", ".csv", ".tsv"}
        else path.name
    )
    parts = name.split(".")
    return len(parts) == 6 and all(part.isdigit() for part in parts)


def _is_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True
