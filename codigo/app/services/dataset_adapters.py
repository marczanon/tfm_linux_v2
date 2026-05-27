"""Registro local de adaptadores deterministas de dataset."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

from codigo.app.schemas.dataset import (
    CommonManifestRecord,
    DatasetAdapterInfo,
    DatasetDescriptor,
    SourceFormat,
)
from codigo.app.schemas.executor_results import ManifestResult
from codigo.app.schemas.state import ArtifactRef

NASA_IMS_SOURCE_SAMPLE_RATE_HZ = 20000
NASA_IMS_TARGET_SAMPLE_RATE_HZ = 20000
NASA_IMS_POINTS_PER_FILE = 20480
NASA_IMS_ROTATION_RPM = 2000
NASA_IMS_RADIAL_LOAD_LBS = 6000


@dataclass(frozen=True)
class _NASAIMSRunSpec:
    run_id: str
    set_id: str
    expected_n_channels: int
    label_detail: str
    local_variant: bool
    notes: str


NASA_IMS_RUN_SPECS = {
    "1st_test": _NASAIMSRunSpec(
        run_id="set_1",
        set_id="set_1",
        expected_n_channels=8,
        label_detail="bearing_3_inner_race_and_bearing_4_roller_element",
        local_variant=False,
        notes="readme_set_1",
    ),
    "2nd_test": _NASAIMSRunSpec(
        run_id="set_2",
        set_id="set_2",
        expected_n_channels=4,
        label_detail="bearing_1_outer_race",
        local_variant=False,
        notes="readme_set_2",
    ),
    "3rd_test": _NASAIMSRunSpec(
        run_id="set_3",
        set_id="set_3",
        expected_n_channels=4,
        label_detail="bearing_3_outer_race",
        local_variant=False,
        notes="readme_set_3",
    ),
    "4th_test": _NASAIMSRunSpec(
        run_id="set_3_local_variant",
        set_id="set_3",
        expected_n_channels=4,
        label_detail="bearing_3_outer_race",
        local_variant=True,
        notes="local_variant_observed_as_4th_test_txt",
    ),
}


class DatasetAdapter(Protocol):
    """Interfaz comun para adaptadores de datasets industriales."""

    @property
    def info(self) -> DatasetAdapterInfo:
        """Devuelve metadata del adaptador."""

    def supports(self, raw_path: Path) -> bool:
        """Indica si el adaptador reconoce una ruta cruda."""

    def describe(self, raw_path: Path) -> DatasetDescriptor:
        """Describe el dataset sin modificar datos crudos."""

    def build_manifest(self, raw_path: Path, output_dir: Path) -> Any:
        """Genera un manifiesto cuando el adaptador lo soporte."""


class CWRUBearingAdapter:
    """Adaptador de descriptor para CWRU Bearing Dataset."""

    @property
    def info(self) -> DatasetAdapterInfo:
        return DatasetAdapterInfo(
            adapter_id="cwru_bearing",
            dataset_id="cwru_bearing",
            display_name="CWRU Bearing Dataset",
            supported_source_formats=["mat", "directory"],
            supports_descriptor=True,
            supports_manifest=True,
            is_experimental=False,
            notes="Envuelve el manifiesto CWRU ya verificado.",
        )

    def supports(self, raw_path: Path) -> bool:
        path = Path(raw_path)
        if path.is_file():
            return path.suffix.lower() == ".mat"
        return any(path.glob("*.mat"))

    def describe(self, raw_path: Path) -> DatasetDescriptor:
        path = Path(raw_path)
        return DatasetDescriptor(
            dataset_id="cwru_bearing",
            dataset_name="CWRU Bearing Dataset",
            domain="rotating_machinery",
            asset_type="bearing",
            raw_path=path.as_posix(),
            source_format=_source_format(path),
            adapter_id=self.info.adapter_id,
            label_availability="file_level",
            task_type="binary_anomaly",
            sampling_rate_hz=None,
            channel_names=["DE_time", "FE_time", "BA_time", "RPM"],
            has_multiple_conditions=True,
            has_run_to_failure=False,
            metadata={"target_sample_rate_hz": 12000},
            notes=[
                "CWRU mezcla ficheros a 12 kHz y 48 kHz; la frecuencia se "
                "normaliza durante la limpieza."
            ],
        )

    def build_manifest(self, raw_path: Path, output_dir: Path):
        """Genera el manifiesto CWRU usando el ejecutor existente."""

        from codigo.app.executors.dataset_manifest import generate_cwru_manifest

        return generate_cwru_manifest(raw_path, Path(output_dir) / "manifest.csv")


class NASAIMSBearingAdapter:
    """Adaptador inicial de descriptor para NASA IMS Bearing Dataset."""

    @property
    def info(self) -> DatasetAdapterInfo:
        return DatasetAdapterInfo(
            adapter_id="nasa_ims_bearing",
            dataset_id="nasa_ims_bearing",
            display_name="NASA IMS Bearing Dataset",
            supported_source_formats=["txt", "csv", "tsv", "zip", "directory"],
            supports_descriptor=True,
            supports_manifest=True,
            is_experimental=True,
            notes=(
                "Genera manifiesto solo para carpetas preextraidas; los paquetes "
                "anidados zip/7z/rar quedan como inspeccion preliminar."
            ),
        )

    def supports(self, raw_path: Path) -> bool:
        path = Path(raw_path)
        if _has_nasa_ims_hint(path):
            return True
        return any(
            _looks_like_nasa_ims_file(file_path)
            for file_path in _candidate_signal_files(path)
        )

    def describe(self, raw_path: Path) -> DatasetDescriptor:
        path = Path(raw_path)
        structure = _inspect_tabular_structure(path)
        notes = [
            "Descriptor preliminar: validar estructura, frecuencia y etiquetas "
            "con la documentacion local antes de modelar."
        ]
        notes.extend(structure.notes)
        if not structure.channel_names:
            notes.append("No se pudieron inferir canales leyendo solo cabeceras.")
        return DatasetDescriptor(
            dataset_id="nasa_ims_bearing",
            dataset_name="NASA IMS Bearing Dataset",
            domain="rotating_machinery",
            asset_type="bearing",
            raw_path=path.as_posix(),
            source_format=_source_format(path),
            adapter_id=self.info.adapter_id,
            label_availability="partial",
            task_type="run_to_failure",
            sampling_rate_hz=None,
            channel_names=structure.channel_names,
            has_multiple_conditions=True,
            has_run_to_failure=True,
            metadata=structure.metadata,
            notes=notes,
        )

    def build_manifest(self, raw_path: Path, output_dir: Path) -> ManifestResult:
        return _generate_nasa_ims_manifest(Path(raw_path), Path(output_dir))


class GenericTabularSignalAdapter:
    """Adaptador generico para senales tabulares locales."""

    @property
    def info(self) -> DatasetAdapterInfo:
        return DatasetAdapterInfo(
            adapter_id="generic_tabular_signal",
            dataset_id="generic_tabular_signal",
            display_name="Generic tabular signal dataset",
            supported_source_formats=["csv", "txt", "tsv", "npz", "directory"],
            supports_descriptor=True,
            supports_manifest=False,
            is_experimental=True,
            notes="Solo genera descriptores; requiere contrato especifico para etiquetas.",
        )

    def supports(self, raw_path: Path) -> bool:
        path = Path(raw_path)
        if path.is_file():
            return path.suffix.lower() in {".csv", ".txt", ".tsv", ".npz"}
        return any(_candidate_signal_files(path))

    def describe(self, raw_path: Path) -> DatasetDescriptor:
        path = Path(raw_path)
        structure = _inspect_tabular_structure(path)
        return DatasetDescriptor(
            dataset_id="generic_tabular_signal",
            dataset_name="Generic tabular signal dataset",
            domain="industrial_time_series",
            asset_type="unknown",
            raw_path=path.as_posix(),
            source_format=_source_format(path),
            adapter_id=self.info.adapter_id,
            label_availability="none",
            task_type="unknown",
            sampling_rate_hz=None,
            channel_names=structure.channel_names,
            has_multiple_conditions=False,
            has_run_to_failure=False,
            metadata=structure.metadata,
            notes=[
                "Descriptor generico sin semantica industrial especifica.",
                *structure.notes,
            ],
        )

    def build_manifest(self, raw_path: Path, output_dir: Path) -> Any:
        raise NotImplementedError("generic manifest generation is not implemented yet")


_ADAPTERS: dict[str, DatasetAdapter] = {
    "cwru_bearing": CWRUBearingAdapter(),
    "nasa_ims_bearing": NASAIMSBearingAdapter(),
    "generic_tabular_signal": GenericTabularSignalAdapter(),
}


def list_dataset_adapters() -> list[DatasetAdapterInfo]:
    """Lista adaptadores registrados."""

    return [adapter.info for adapter in _ADAPTERS.values()]


def get_dataset_adapter(adapter_id: str) -> DatasetAdapter:
    """Devuelve un adaptador registrado por identificador."""

    try:
        return _ADAPTERS[adapter_id]
    except KeyError as exc:
        available = ", ".join(sorted(_ADAPTERS))
        raise ValueError(
            f"unknown dataset adapter: {adapter_id}; available: {available}"
        ) from exc


def infer_dataset_adapter(raw_path: str | Path) -> DatasetAdapter:
    """Infiere un adaptador para una ruta local sin ejecutar transformaciones."""

    path = Path(raw_path)
    matches = [adapter for adapter in _ADAPTERS.values() if adapter.supports(path)]
    if not matches:
        raise ValueError(f"no dataset adapter supports path: {path}")
    if len(matches) > 1:
        preferred = _prefer_specific_adapter(matches)
        if preferred is not None:
            return preferred
        ids = ", ".join(adapter.info.adapter_id for adapter in matches)
        raise ValueError(f"ambiguous dataset adapter for {path}: {ids}")
    return matches[0]


def describe_dataset(
    raw_path: str | Path,
    adapter_id: str | None = None,
) -> DatasetDescriptor:
    """Describe un dataset usando un adaptador explicito o inferido."""

    adapter = (
        get_dataset_adapter(adapter_id)
        if adapter_id
        else infer_dataset_adapter(raw_path)
    )
    return adapter.describe(Path(raw_path))


def _generate_nasa_ims_manifest(raw_path: Path, output_dir: Path) -> ManifestResult:
    if not raw_path.is_dir():
        raise ValueError(
            "NASA IMS manifest generation requires a preextracted directory"
        )

    records = _build_nasa_ims_records(raw_path)
    if not records:
        raise ValueError(
            f"no NASA IMS timestamp files found in preextracted directory: {raw_path}"
        )

    output_path = output_dir / "manifest.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_common_manifest(output_path, records)
    artifact = ArtifactRef(
        name="nasa_ims_manifest",
        artifact_type="manifest",
        path=output_path.as_posix(),
        producer="manifest_executor",
        metadata={
            "dataset": "nasa_ims_bearing",
            "n_rows": len(records),
            "unknown": len(records),
            "sampling_rate_hz": NASA_IMS_SOURCE_SAMPLE_RATE_HZ,
        },
    )
    return ManifestResult(
        executor_name="dataset_manifest",
        status="success",
        message="NASA IMS manifest generated from preextracted directory.",
        artifacts=[artifact],
        errors=[],
        state_updates={
            "manifest_path": output_path.as_posix(),
            "dataset_id": "nasa_ims_bearing",
            "adapter_id": "nasa_ims_bearing",
        },
        manifest_path=output_path.as_posix(),
        n_rows=len(records),
        label_counts={"unknown": len(records)},
    )


def _build_nasa_ims_records(raw_path: Path) -> list[CommonManifestRecord]:
    files = _nasa_ims_manifest_files(raw_path)
    return [_nasa_ims_record_from_file(file_path, raw_path) for file_path in files]


def _nasa_ims_record_from_file(
    file_path: Path,
    raw_path: Path,
) -> CommonManifestRecord:
    spec = _nasa_ims_run_spec(file_path, raw_path)
    timestamp_start = _parse_nasa_ims_timestamp(file_path)
    snapshot_duration = NASA_IMS_POINTS_PER_FILE / NASA_IMS_SOURCE_SAMPLE_RATE_HZ
    channel_names = _nasa_ims_channel_names(file_path, spec.expected_n_channels)
    timestamp_key = _nasa_ims_timestamp_token(file_path).replace(".", "_")
    return CommonManifestRecord(
        record_id=f"{spec.run_id}_{timestamp_key}",
        dataset="nasa_ims_bearing",
        source_path=file_path.as_posix(),
        source_format="txt",
        label="unknown",
        label_detail=spec.label_detail,
        condition_id="test_to_failure",
        asset_id="bearing_test_rig",
        run_id=spec.run_id,
        timestamp_start=timestamp_start,
        timestamp_end=timestamp_start + timedelta(seconds=snapshot_duration),
        sampling_rate_hz=NASA_IMS_SOURCE_SAMPLE_RATE_HZ,
        target_sample_rate_hz=NASA_IMS_TARGET_SAMPLE_RATE_HZ,
        channel_names=channel_names,
        primary_channel=channel_names[0],
        n_channels=len(channel_names),
        metadata_json={
            "set_id": spec.set_id,
            "expected_n_channels": spec.expected_n_channels,
            "points_per_file": NASA_IMS_POINTS_PER_FILE,
            "snapshot_duration_seconds": snapshot_duration,
            "rotation_rpm": NASA_IMS_ROTATION_RPM,
            "radial_load_lbs": NASA_IMS_RADIAL_LOAD_LBS,
            "local_variant": spec.local_variant,
            "final_failure": spec.label_detail,
            "source_file_name": file_path.name,
        },
        notes=f"preextracted_nasa_ims_snapshot; {spec.notes}",
    )


def _write_common_manifest(path: Path, records: list[CommonManifestRecord]) -> None:
    fieldnames = list(CommonManifestRecord.model_fields)
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for record in records:
            writer.writerow(_serialize_common_manifest_row(record))


def _serialize_common_manifest_row(record: CommonManifestRecord) -> dict[str, Any]:
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


def _nasa_ims_manifest_files(raw_path: Path) -> list[Path]:
    return sorted(
        [
            file_path
            for file_path in raw_path.rglob("*")
            if file_path.is_file() and _looks_like_nasa_ims_file(file_path)
        ],
        key=lambda path: path.as_posix(),
    )


def _nasa_ims_run_spec(file_path: Path, raw_path: Path) -> _NASAIMSRunSpec:
    relative = file_path.relative_to(raw_path)
    path_parts = [part.lower() for part in relative.parts[:-1]]
    path_parts.extend([raw_path.name.lower(), raw_path.parent.name.lower()])
    for marker, spec in NASA_IMS_RUN_SPECS.items():
        if marker in path_parts:
            return spec
    raise ValueError(f"could not map NASA IMS file to known set: {file_path}")


def _nasa_ims_channel_names(file_path: Path, expected_n_channels: int) -> list[str]:
    detected_channels = _read_header_channels(file_path)
    if detected_channels and len(detected_channels) != expected_n_channels:
        raise ValueError(
            "NASA IMS channel count mismatch for "
            f"{file_path}: expected {expected_n_channels}, got {len(detected_channels)}"
        )
    return [f"channel_{index}" for index in range(1, expected_n_channels + 1)]


def _parse_nasa_ims_timestamp(path: Path) -> datetime:
    return datetime.strptime(_nasa_ims_timestamp_token(path), "%Y.%m.%d.%H.%M.%S")


def _nasa_ims_timestamp_token(path: Path) -> str:
    if path.suffix.lower() in {".txt", ".csv", ".tsv"}:
        return path.stem
    return path.name


def _prefer_specific_adapter(adapters: list[DatasetAdapter]) -> DatasetAdapter | None:
    specific = [
        adapter
        for adapter in adapters
        if adapter.info.adapter_id != "generic_tabular_signal"
    ]
    return specific[0] if len(specific) == 1 else None


def _candidate_signal_files(path: Path) -> list[Path]:
    if path.is_file():
        return (
            [path]
            if _is_candidate_signal_file(path)
            else []
        )
    if not path.exists():
        return []
    files: list[Path] = []
    for file_path in path.rglob("*"):
        if file_path.is_file() and _is_candidate_signal_file(file_path):
            files.append(file_path)
    return sorted(files)


def _source_format(path: Path) -> SourceFormat:
    if path.is_dir():
        return "directory"
    suffix = path.suffix.lower().lstrip(".")
    if suffix in {"mat", "csv", "txt", "tsv", "npz", "zip", "parquet"}:
        return cast(SourceFormat, suffix)
    return "directory"


class _TabularStructure:
    def __init__(
        self,
        channel_names: list[str],
        metadata: dict[str, str | int | float | bool | None],
        notes: list[str],
    ) -> None:
        self.channel_names = channel_names
        self.metadata = metadata
        self.notes = notes


def _inspect_tabular_structure(path: Path, max_files: int = 20) -> _TabularStructure:
    files = _candidate_signal_files(path)
    if not files:
        return _TabularStructure(
            channel_names=[],
            metadata={"candidate_file_count": 0, "inspected_file_count": 0},
            notes=[],
        )

    inspected = files[:max_files]
    channel_sets = [_read_header_channels(file_path) for file_path in inspected]
    channel_sets = [channels for channels in channel_sets if channels]
    channel_counts = sorted({len(channels) for channels in channel_sets})
    metadata: dict[str, str | int | float | bool | None] = {
        "candidate_file_count": len(files),
        "inspected_file_count": len(inspected),
        "example_file": files[0].as_posix(),
        "file_extensions": _extensions_summary(files),
        "channel_count_values": ",".join(str(count) for count in channel_counts),
        "inconsistent_channel_counts": len(channel_counts) > 1,
    }
    notes: list[str] = []
    if len(channel_counts) > 1:
        notes.append(
            "Se detectaron recuentos de canales inconsistentes entre ficheros "
            "sinteticos; revisar estructura antes de generar manifiesto."
        )
    if not channel_sets:
        return _TabularStructure(channel_names=[], metadata=metadata, notes=notes)

    channel_names = channel_sets[0]
    metadata["inferred_n_channels"] = len(channel_names)
    return _TabularStructure(
        channel_names=channel_names,
        metadata=metadata,
        notes=notes,
    )


def _read_header_channels(path: Path) -> list[str]:
    if path.suffix.lower() == ".npz":
        return []
    try:
        with path.open(encoding="utf-8") as file:
            for line in file:
                stripped = line.strip()
                if stripped:
                    return _channels_from_line(stripped)
    except OSError:
        return []
    return []


def _channels_from_line(line: str) -> list[str]:
    if "\t" in line:
        parts = line.split("\t")
    elif "," in line:
        parts = line.split(",")
    else:
        parts = line.split()
    cleaned = [part.strip() for part in parts if part.strip()]
    if not cleaned:
        return []
    if all(_is_number(part) for part in cleaned):
        return [f"channel_{index}" for index in range(1, len(cleaned) + 1)]
    return cleaned


def _is_candidate_signal_file(path: Path) -> bool:
    return path.suffix.lower() in {".csv", ".txt", ".tsv", ".npz"} or _looks_like_nasa_ims_file(path)


def _has_nasa_ims_hint(path: Path) -> bool:
    tokens: set[str] = set()
    for part in path.parts:
        normalized = (
            part.lower()
            .replace("-", "_")
            .replace(" ", "_")
            .replace("+", "_")
            .replace(".", "_")
        )
        tokens.update(token for token in normalized.split("_") if token)
        if part.lower() in {"ims", "ims.7z"}:
            return True
    return ("nasa" in tokens and "ims" in tokens) or (
        "ims" in tokens and "bearing" in tokens
    )


def _looks_like_nasa_ims_file(path: Path) -> bool:
    name = path.stem if path.suffix.lower() in {".txt", ".csv", ".tsv"} else path.name
    parts = name.split(".")
    return len(parts) == 6 and all(part.isdigit() for part in parts)


def _extensions_summary(files: list[Path]) -> str:
    extensions = sorted({_logical_extension(file_path) for file_path in files})
    return ",".join(extensions)


def _logical_extension(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".csv", ".txt", ".tsv", ".npz"}:
        return suffix
    if _looks_like_nasa_ims_file(path):
        return "<none>"
    return suffix or "<none>"


def _is_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True
