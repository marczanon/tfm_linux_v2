"""Registro local de adaptadores deterministas de dataset."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Protocol, cast

from pydantic import ValidationError

from codigo.app.schemas.common import JsonScalar
from codigo.app.schemas.dataset import (
    CommonManifestRecord,
    DataProvenance,
    DatasetAdapterInfo,
    DatasetDescriptor,
    NASAIMSOfficialArchiveEvidence,
    NASAIMSOfficialProvenanceEvidence,
    NASAIMSOfficialSubsetInventory,
    ProvenanceDetectionMethod,
    SourceFormat,
)
from codigo.app.schemas.executor_results import ManifestResult
from codigo.app.services.common_manifest import write_common_manifest
from codigo.app.schemas.state import ArtifactRef

NASA_IMS_SOURCE_SAMPLE_RATE_HZ = 20000
NASA_IMS_TARGET_SAMPLE_RATE_HZ = 20000
NASA_IMS_POINTS_PER_FILE = 20480
NASA_IMS_ROTATION_RPM = 2000
NASA_IMS_RADIAL_LOAD_LBS = 6000
NASA_IMS_SYNTHETIC_SPEC_FILENAME = "synthetic_dataset_spec.json"
NASA_IMS_OFFICIAL_EVIDENCE_FILENAME = "official_dataset_provenance.json"
NASA_IMS_OFFICIAL_SOURCE_URL = (
    "https://phm-datasets.s3.amazonaws.com/NASA/4.+Bearings.zip"
)
NASA_IMS_OFFICIAL_SOURCES: dict[str, dict[str, str | int]] = {
    NASA_IMS_OFFICIAL_SOURCE_URL: {
        "archive_file_name": "4.+Bearings.zip",
        "archive_size_bytes": 1_075_597_174,
        "archive_sha256": (
            "21001ac266c465f5d345ec42d7b508c6a6328487fd9d4d7774422dd5ea10ad83"
        ),
    }
}
NASA_IMS_OFFICIAL_SUBSET_INVENTORIES: dict[str, dict[str, str | int]] = {
    "set_2": {
        "snapshot_count": 984,
        "expected_n_channels": 4,
        "first_snapshot": "2004.02.12.10.32.39",
        "last_snapshot": "2004.02.19.06.22.39",
        "total_bytes": 544_618_480,
        "tree_sha256": (
            "aaa5210f0052a5b3ad33c47daff8395c2ea7a879b436aa3032e3eb82c0d14ebe"
        ),
    }
}


@dataclass(frozen=True)
class _NASAIMSRunSpec:
    run_id: str
    set_id: str
    expected_n_channels: int
    label_detail: str
    local_variant: bool
    notes: str


@dataclass(frozen=True)
class _DatasetProvenanceEvidence:
    data_provenance: DataProvenance
    detection_method: ProvenanceDetectionMethod
    evidence_path: str | None = None
    evidence_sha256: str | None = None
    metadata: dict[str, JsonScalar] = field(default_factory=dict)


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
            supervision_profile="binary_fault_classification",
            label_granularity="file",
            label_source="official",
            data_provenance="official",
            provenance_detection_method="trusted_adapter",
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
        provenance = _detect_nasa_ims_data_provenance(path)
        notes = [
            "Descriptor preliminar: validar estructura, frecuencia y etiquetas "
            "con la documentacion local antes de modelar."
        ]
        notes.extend(structure.notes)
        notes.append(_nasa_ims_provenance_note(provenance))
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
            supervision_profile="run_to_failure_degradation",
            label_granularity="event",
            label_source="none",
            data_provenance=provenance.data_provenance,
            provenance_detection_method=provenance.detection_method,
            provenance_evidence_path=provenance.evidence_path,
            provenance_evidence_sha256=provenance.evidence_sha256,
            sampling_rate_hz=None,
            channel_names=structure.channel_names,
            has_multiple_conditions=True,
            has_run_to_failure=True,
            metadata={**structure.metadata, **provenance.metadata},
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
            supervision_profile="unlabeled_diagnostic",
            label_granularity="none",
            label_source="none",
            data_provenance="unknown",
            provenance_detection_method="unverified",
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


def _detect_nasa_ims_data_provenance(
    raw_path: Path,
) -> _DatasetProvenanceEvidence:
    official_paths = _nasa_ims_official_evidence_paths(raw_path)
    spec_paths = _nasa_ims_synthetic_spec_paths(raw_path)
    if official_paths and spec_paths:
        raise ValueError(
            "conflicting NASA IMS provenance evidence: official and synthetic "
            "sidecars are both in scope"
        )
    if official_paths:
        verified: list[
            tuple[Path, NASAIMSOfficialProvenanceEvidence]
        ] = []
        for evidence_path in official_paths:
            evidence = verify_nasa_ims_official_provenance(evidence_path)
            subset_path = _official_subset_path(evidence_path, evidence)
            if _raw_path_covers_official_subset(raw_path, subset_path):
                verified.append((evidence_path, evidence))
        if len(verified) > 1:
            candidates = ", ".join(path.as_posix() for path, _ in verified)
            raise ValueError(
                "multiple official_dataset_provenance.json files found under "
                f"NASA IMS input; select one subset explicitly: {candidates}"
            )
        if verified:
            evidence_path, evidence = verified[0]
            raw_evidence = evidence_path.read_bytes()
            return _DatasetProvenanceEvidence(
                data_provenance="official",
                detection_method="official_dataset_provenance",
                evidence_path=evidence_path.as_posix(),
                evidence_sha256=hashlib.sha256(raw_evidence).hexdigest(),
                metadata=_official_provenance_metadata(evidence),
            )

    if not spec_paths:
        return _DatasetProvenanceEvidence(
            data_provenance="unknown",
            detection_method="unverified",
        )
    if len(spec_paths) > 1:
        candidates = ", ".join(path.as_posix() for path in spec_paths)
        raise ValueError(
            "multiple synthetic_dataset_spec.json files found under NASA IMS input; "
            f"select one dataset root explicitly: {candidates}"
        )

    spec_path = spec_paths[0]
    try:
        raw_spec = spec_path.read_bytes()
        payload = json.loads(raw_spec.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(
            f"invalid NASA IMS synthetic provenance spec: {spec_path}"
        ) from exc
    if not isinstance(payload, dict):
        raise ValueError(
            f"NASA IMS synthetic provenance spec must be a JSON object: {spec_path}"
        )
    if payload.get("dataset") != "nasa_ims_bearing" or payload.get("synthetic") is not True:
        raise ValueError(
            "synthetic_dataset_spec.json must declare dataset=nasa_ims_bearing "
            f"and synthetic=true: {spec_path}"
        )
    return _DatasetProvenanceEvidence(
        data_provenance="synthetic",
        detection_method="synthetic_dataset_spec",
        evidence_path=spec_path.as_posix(),
        evidence_sha256=hashlib.sha256(raw_spec).hexdigest(),
    )


def prepare_nasa_ims_official_provenance(
    archive_path: str | Path,
    subset_path: str | Path,
    *,
    source_url: str = NASA_IMS_OFFICIAL_SOURCE_URL,
    evidence_path: str | Path | None = None,
) -> Path:
    """Crea, sin sobrescribir, el sidecar oficial para un subconjunto extraido."""

    archive = Path(archive_path)
    subset = Path(subset_path)
    target = (
        Path(evidence_path)
        if evidence_path is not None
        else archive.parent / NASA_IMS_OFFICIAL_EVIDENCE_FILENAME
    )
    if target.name != NASA_IMS_OFFICIAL_EVIDENCE_FILENAME:
        raise ValueError(
            "official evidence path must end in "
            f"{NASA_IMS_OFFICIAL_EVIDENCE_FILENAME}"
        )
    if target.parent.resolve() != archive.parent.resolve():
        raise ValueError(
            "official evidence and source archive must share the dataset root"
        )

    trusted = _trusted_nasa_ims_official_source(source_url)
    if archive.is_symlink() or not archive.is_file():
        raise ValueError(f"NASA IMS official source archive is missing: {archive}")
    source = NASAIMSOfficialArchiveEvidence(
        source_url=source_url,
        archive_file_name=str(trusted["archive_file_name"]),
        archive_size_bytes=int(trusted["archive_size_bytes"]),
        archive_sha256=str(trusted["archive_sha256"]),
    )
    _validate_nasa_ims_official_archive(archive, source, trusted)

    spec = _nasa_ims_official_run_spec(subset)
    relative_path = _safe_relative_subset_path(subset, target.parent)
    inventory = _build_nasa_ims_official_inventory(
        subset,
        set_id=spec.set_id,
        relative_path=relative_path,
        expected_n_channels=spec.expected_n_channels,
    )
    _validate_nasa_ims_trusted_subset_inventory(inventory)
    evidence = NASAIMSOfficialProvenanceEvidence(
        source=source,
        subset=inventory,
    )
    canonical = _canonical_official_evidence_bytes(evidence)

    if target.exists():
        current = verify_nasa_ims_official_provenance(target)
        if current != evidence or target.read_bytes() != canonical:
            raise FileExistsError(
                "official provenance evidence already exists with different content; "
                "it was not overwritten"
            )
        return target

    if not target.parent.is_dir():
        raise ValueError(f"official evidence parent does not exist: {target.parent}")
    try:
        with target.open("xb") as file:
            file.write(canonical)
    except FileExistsError:
        raise FileExistsError(
            "official provenance evidence appeared concurrently; it was not overwritten"
        ) from None
    return target


def verify_nasa_ims_official_provenance(
    evidence_path: str | Path,
) -> NASAIMSOfficialProvenanceEvidence:
    """Valida contrato, fuente, archivo e inventario de un sidecar oficial."""

    path = Path(evidence_path)
    if path.name != NASA_IMS_OFFICIAL_EVIDENCE_FILENAME:
        raise ValueError(
            "official NASA IMS evidence must use "
            f"{NASA_IMS_OFFICIAL_EVIDENCE_FILENAME}"
        )
    if path.is_symlink():
        raise ValueError(f"NASA IMS official provenance evidence cannot be a symlink: {path}")
    try:
        raw_evidence = path.read_bytes()
        evidence = NASAIMSOfficialProvenanceEvidence.model_validate_json(raw_evidence)
    except (OSError, ValidationError) as exc:
        raise ValueError(f"invalid NASA IMS official provenance evidence: {path}") from exc

    if raw_evidence != _canonical_official_evidence_bytes(evidence):
        raise ValueError(
            "NASA IMS official provenance evidence is not canonical JSON: "
            f"{path}"
        )

    trusted = _trusted_nasa_ims_official_source(evidence.source.source_url)
    archive_path = path.parent / evidence.source.archive_file_name
    _validate_nasa_ims_official_archive(
        archive_path,
        evidence.source,
        trusted,
    )
    subset_path = _official_subset_path(path, evidence)
    _validate_nasa_ims_trusted_subset_inventory(evidence.subset)
    actual_inventory = _build_nasa_ims_official_inventory(
        subset_path,
        set_id=evidence.subset.set_id,
        relative_path=evidence.subset.relative_path,
        expected_n_channels=evidence.subset.expected_n_channels,
    )
    _validate_nasa_ims_trusted_subset_inventory(actual_inventory)
    if actual_inventory != evidence.subset:
        expected = evidence.subset.model_dump(mode="json")
        actual = actual_inventory.model_dump(mode="json")
        mismatches = [
            key for key in expected
            if expected[key] != actual[key]
        ]
        raise ValueError(
            "NASA IMS official subset inventory mismatch for "
            f"{subset_path}: {', '.join(mismatches)}"
        )
    return evidence


def _nasa_ims_official_evidence_paths(raw_path: Path) -> list[Path]:
    path = Path(raw_path)
    base = path if path.is_dir() else path.parent
    candidates: set[Path] = set()
    if base.is_dir():
        direct = base / NASA_IMS_OFFICIAL_EVIDENCE_FILENAME
        if direct.is_file():
            candidates.add(direct)
        candidates.update(
            candidate
            for candidate in base.rglob(NASA_IMS_OFFICIAL_EVIDENCE_FILENAME)
            if candidate.is_file()
        )

    if base.name.lower() in NASA_IMS_RUN_SPECS:
        for ancestor in (base.parent, base.parent.parent):
            candidate = ancestor / NASA_IMS_OFFICIAL_EVIDENCE_FILENAME
            if candidate.is_file():
                candidates.add(candidate)
    elif base.name.lower() == "official":
        candidate = base.parent / NASA_IMS_OFFICIAL_EVIDENCE_FILENAME
        if candidate.is_file():
            candidates.add(candidate)
    return sorted(candidates, key=lambda candidate: candidate.as_posix())


def _nasa_ims_synthetic_spec_paths(raw_path: Path) -> list[Path]:
    path = Path(raw_path)
    candidates: list[Path] = []
    if path.is_dir():
        candidates.extend(path.rglob(NASA_IMS_SYNTHETIC_SPEC_FILENAME))
        if path.name.lower() in NASA_IMS_RUN_SPECS:
            parent_spec = path.parent / NASA_IMS_SYNTHETIC_SPEC_FILENAME
            if parent_spec.is_file():
                candidates.append(parent_spec)
    elif path.is_file():
        sibling_spec = path.parent / NASA_IMS_SYNTHETIC_SPEC_FILENAME
        if sibling_spec.is_file():
            candidates.append(sibling_spec)
    return sorted(
        {candidate for candidate in candidates if candidate.is_file()},
        key=lambda candidate: candidate.as_posix(),
    )


def _trusted_nasa_ims_official_source(
    source_url: str,
) -> dict[str, str | int]:
    try:
        return NASA_IMS_OFFICIAL_SOURCES[source_url]
    except KeyError as exc:
        raise ValueError(
            f"source URL is not an allowed NASA IMS official URL: {source_url}"
        ) from exc


def _validate_nasa_ims_official_archive(
    archive_path: Path,
    source: NASAIMSOfficialArchiveEvidence,
    trusted: dict[str, str | int],
) -> None:
    if archive_path.is_symlink() or not archive_path.is_file():
        raise ValueError(f"NASA IMS official source archive is missing: {archive_path}")
    if archive_path.name != source.archive_file_name:
        raise ValueError(
            "NASA IMS official archive file name mismatch: "
            f"expected {source.archive_file_name}, got {archive_path.name}"
        )
    for field_name in (
        "archive_file_name",
        "archive_size_bytes",
        "archive_sha256",
    ):
        claimed = getattr(source, field_name)
        expected = trusted.get(field_name)
        if claimed != expected:
            raise ValueError(
                "NASA IMS official source identity mismatch for "
                f"{field_name}: expected {expected}, got {claimed}"
            )
    actual_size = archive_path.stat().st_size
    if actual_size != source.archive_size_bytes:
        raise ValueError(
            "NASA IMS official archive size mismatch: "
            f"expected {source.archive_size_bytes}, got {actual_size}"
        )
    actual_sha256 = _sha256_file(archive_path)
    if actual_sha256 != source.archive_sha256:
        raise ValueError(
            "NASA IMS official archive SHA-256 mismatch: "
            f"expected {source.archive_sha256}, got {actual_sha256}"
        )


def _nasa_ims_official_run_spec(subset_path: Path) -> _NASAIMSRunSpec:
    if subset_path.is_symlink() or not subset_path.is_dir():
        raise ValueError(
            f"NASA IMS official subset must be an existing real directory: {subset_path}"
        )
    try:
        spec = NASA_IMS_RUN_SPECS[subset_path.name.lower()]
    except KeyError as exc:
        raise ValueError(
            "NASA IMS official subset directory must be one of "
            "1st_test, 2nd_test or 3rd_test"
        ) from exc
    if spec.local_variant:
        raise ValueError("local NASA IMS variants cannot be certified as official")
    return spec


def _safe_relative_subset_path(subset_path: Path, dataset_root: Path) -> str:
    subset_resolved = subset_path.resolve()
    root_resolved = dataset_root.resolve()
    try:
        relative = subset_resolved.relative_to(root_resolved)
    except ValueError as exc:
        raise ValueError(
            "NASA IMS official subset must be inside the source archive dataset root"
        ) from exc
    value = relative.as_posix()
    if not value or value == "." or ".." in relative.parts:
        raise ValueError("NASA IMS official subset relative path is unsafe")
    return value


def _official_subset_path(
    evidence_path: Path,
    evidence: NASAIMSOfficialProvenanceEvidence,
) -> Path:
    root = evidence_path.parent.resolve()
    subset = (root / evidence.subset.relative_path).resolve()
    try:
        subset.relative_to(root)
    except ValueError as exc:
        raise ValueError(
            "NASA IMS official subset path escapes the evidence root"
        ) from exc
    return subset


def _raw_path_covers_official_subset(raw_path: Path, subset_path: Path) -> bool:
    raw = Path(raw_path)
    scope = (raw if raw.is_dir() else raw.parent).resolve()
    subset = subset_path.resolve()
    return scope == subset or scope in subset.parents or subset in scope.parents


def _build_nasa_ims_official_inventory(
    subset_path: Path,
    *,
    set_id: str,
    relative_path: str,
    expected_n_channels: int,
) -> NASAIMSOfficialSubsetInventory:
    spec = _nasa_ims_official_run_spec(subset_path)
    if spec.set_id != set_id or spec.expected_n_channels != expected_n_channels:
        raise ValueError(
            "NASA IMS official subset identity conflicts with its directory contract"
        )

    all_entries = sorted(subset_path.iterdir(), key=lambda item: item.name)
    symlinks = [entry for entry in all_entries if entry.is_symlink()]
    if symlinks:
        raise ValueError(
            "NASA IMS official subset cannot contain symbolic links: "
            f"{symlinks[0]}"
        )
    nested_or_special = [entry for entry in all_entries if not entry.is_file()]
    if nested_or_special:
        raise ValueError(
            "NASA IMS official subset must contain only flat snapshot files: "
            f"{nested_or_special[0]}"
        )
    files = [entry for entry in all_entries if entry.is_file()]
    if not files:
        raise ValueError(f"NASA IMS official subset has no snapshots: {subset_path}")
    invalid_names = [
        entry.name
        for entry in files
        if not _is_strict_nasa_ims_snapshot_name(entry.name)
    ]
    if invalid_names:
        raise ValueError(
            "NASA IMS official subset contains a non-timestamp snapshot: "
            f"{invalid_names[0]}"
        )

    tree_digest = hashlib.sha256()
    total_bytes = 0
    for file_path in files:
        try:
            channels = _read_header_channels(file_path)
        except UnicodeError as exc:
            raise ValueError(
                f"NASA IMS official snapshot is not valid text: {file_path}"
            ) from exc
        if len(channels) != expected_n_channels:
            raise ValueError(
                "NASA IMS official snapshot channel count mismatch for "
                f"{file_path}: expected {expected_n_channels}, got {len(channels)}"
            )
        size = file_path.stat().st_size
        file_sha256 = _sha256_file(file_path)
        total_bytes += size
        tree_digest.update(
            f"{file_path.name}\0{size}\0{file_sha256}\n".encode("utf-8")
        )

    return NASAIMSOfficialSubsetInventory(
        set_id=cast(Any, set_id),
        relative_path=relative_path,
        snapshot_count=len(files),
        expected_n_channels=expected_n_channels,
        first_snapshot=files[0].name,
        last_snapshot=files[-1].name,
        total_bytes=total_bytes,
        tree_sha256=tree_digest.hexdigest(),
    )


def _validate_nasa_ims_trusted_subset_inventory(
    inventory: NASAIMSOfficialSubsetInventory,
) -> None:
    try:
        trusted = NASA_IMS_OFFICIAL_SUBSET_INVENTORIES[inventory.set_id]
    except KeyError as exc:
        raise ValueError(
            "no trusted NASA IMS official inventory is registered for "
            f"{inventory.set_id}"
        ) from exc
    mismatches = [
        field_name
        for field_name in (
            "snapshot_count",
            "expected_n_channels",
            "first_snapshot",
            "last_snapshot",
            "total_bytes",
            "tree_sha256",
        )
        if getattr(inventory, field_name) != trusted.get(field_name)
    ]
    if mismatches:
        raise ValueError(
            "NASA IMS trusted official subset inventory mismatch for "
            f"{inventory.set_id}: {', '.join(mismatches)}"
        )


def _is_strict_nasa_ims_snapshot_name(value: str) -> bool:
    parts = value.split(".")
    if len(parts) != 6 or [len(part) for part in parts] != [4, 2, 2, 2, 2, 2]:
        return False
    if not all(part.isdigit() for part in parts):
        return False
    try:
        datetime.strptime(value, "%Y.%m.%d.%H.%M.%S")
    except ValueError:
        return False
    return True


def _canonical_official_evidence_bytes(
    evidence: NASAIMSOfficialProvenanceEvidence,
) -> bytes:
    payload = json.dumps(
        evidence.model_dump(mode="json"),
        ensure_ascii=True,
        indent=2,
        sort_keys=True,
    )
    return f"{payload}\n".encode("utf-8")


def _official_provenance_metadata(
    evidence: NASAIMSOfficialProvenanceEvidence,
) -> dict[str, JsonScalar]:
    return {
        "official_provenance_schema_version": evidence.schema_version,
        "official_source_url": evidence.source.source_url,
        "official_archive_file_name": evidence.source.archive_file_name,
        "official_archive_size_bytes": evidence.source.archive_size_bytes,
        "official_archive_sha256": evidence.source.archive_sha256,
        "official_subset_id": evidence.subset.set_id,
        "official_subset_relative_path": evidence.subset.relative_path,
        "official_snapshot_count": evidence.subset.snapshot_count,
        "official_expected_n_channels": evidence.subset.expected_n_channels,
        "official_first_snapshot": evidence.subset.first_snapshot,
        "official_last_snapshot": evidence.subset.last_snapshot,
        "official_subset_total_bytes": evidence.subset.total_bytes,
        "official_subset_tree_sha256": evidence.subset.tree_sha256,
    }


def _sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as file:
            while chunk := file.read(chunk_size):
                digest.update(chunk)
    except OSError as exc:
        raise ValueError(f"could not hash provenance input: {path}") from exc
    return digest.hexdigest()


def _nasa_ims_provenance_note(provenance: _DatasetProvenanceEvidence) -> str:
    if provenance.data_provenance == "synthetic":
        return (
            "Procedencia de datos synthetic detectada mediante "
            "synthetic_dataset_spec.json: las senales imitan el formato NASA IMS, "
            "pero no son mediciones oficiales del dataset NASA IMS."
        )
    if provenance.data_provenance == "official":
        return "Procedencia de datos official confirmada mediante evidencia trazable."
    return (
        "Procedencia de datos unknown: no se encontro evidencia que permita "
        "presentar las senales como mediciones oficiales de NASA IMS."
    )


def _generate_nasa_ims_manifest(raw_path: Path, output_dir: Path) -> ManifestResult:
    if not raw_path.is_dir():
        raise ValueError(
            "NASA IMS manifest generation requires a preextracted directory"
        )

    provenance = _detect_nasa_ims_data_provenance(raw_path)
    records = _build_nasa_ims_records(raw_path, provenance)
    if not records:
        raise ValueError(
            f"no NASA IMS timestamp files found in preextracted directory: {raw_path}"
        )

    output_path = output_dir / "manifest.csv"
    write_common_manifest(output_path, records)
    artifact = ArtifactRef(
        name="nasa_ims_manifest",
        artifact_type="manifest",
        path=output_path.as_posix(),
        producer="manifest_executor",
        metadata={
            "dataset": "nasa_ims_bearing",
            "data_provenance": provenance.data_provenance,
            "provenance_detection_method": provenance.detection_method,
            "provenance_evidence_path": provenance.evidence_path,
            "provenance_evidence_sha256": provenance.evidence_sha256,
            **provenance.metadata,
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
            "data_provenance": provenance.data_provenance,
            "provenance_detection_method": provenance.detection_method,
            "provenance_evidence_path": provenance.evidence_path,
            "provenance_evidence_sha256": provenance.evidence_sha256,
            **provenance.metadata,
        },
        manifest_path=output_path.as_posix(),
        n_rows=len(records),
        label_counts={"unknown": len(records)},
    )


def _build_nasa_ims_records(
    raw_path: Path,
    provenance: _DatasetProvenanceEvidence,
) -> list[CommonManifestRecord]:
    files = _nasa_ims_manifest_files(raw_path)
    records = [
        _nasa_ims_record_from_file(file_path, raw_path, provenance)
        for file_path in files
    ]
    return _with_nasa_ims_run_to_failure_metadata(records)


def _nasa_ims_record_from_file(
    file_path: Path,
    raw_path: Path,
    provenance: _DatasetProvenanceEvidence,
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
        data_provenance=provenance.data_provenance,
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
            "supervision_profile": "run_to_failure_degradation",
            "label_source": "none",
            "label_granularity": "event",
            "official_window_labels": False,
            "data_provenance": provenance.data_provenance,
            "provenance_detection_method": provenance.detection_method,
            "provenance_evidence_path": provenance.evidence_path,
            "provenance_evidence_sha256": provenance.evidence_sha256,
            **provenance.metadata,
            "official_nasa_measurements": (
                True if provenance.data_provenance == "official" else False
                if provenance.data_provenance == "synthetic" else None
            ),
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


def _with_nasa_ims_run_to_failure_metadata(
    records: list[CommonManifestRecord],
) -> list[CommonManifestRecord]:
    grouped: dict[str, list[CommonManifestRecord]] = {}
    for record in records:
        grouped.setdefault(record.run_id or "unknown_run", []).append(record)

    annotated: list[CommonManifestRecord] = []
    for group_key, group_records in grouped.items():
        ordered = sorted(
            group_records,
            key=lambda item: (
                item.timestamp_start or datetime.min,
                item.source_path,
                item.record_id,
            ),
        )
        failure_event_time = _nasa_ims_failure_event_time(ordered)
        failure_mode = _nasa_ims_failure_mode(ordered)
        for index, record in enumerate(ordered):
            metadata = {
                **record.metadata_json,
                "failure_event_time": failure_event_time,
                "failure_mode": failure_mode,
                "end_of_life_policy": "last_snapshot_as_failure_event",
                "temporal_group_id": group_key,
                "temporal_order_index": index,
                "temporal_order_count": len(ordered),
            }
            annotated.append(record.model_copy(update={"metadata_json": metadata}))
    return sorted(annotated, key=lambda item: item.source_path)


def _nasa_ims_failure_event_time(records: list[CommonManifestRecord]) -> str | None:
    candidates = [
        timestamp
        for record in records
        for timestamp in [record.timestamp_end, record.timestamp_start]
        if timestamp is not None
    ]
    if not candidates:
        return None
    return max(candidates).isoformat()


def _nasa_ims_failure_mode(records: list[CommonManifestRecord]) -> str:
    for record in records:
        value = record.metadata_json.get("final_failure") or record.label_detail
        if value:
            return str(value)
    return "unknown_failure_mode"


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
