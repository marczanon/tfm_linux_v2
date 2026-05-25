"""Generacion determinista del manifiesto CWRU."""

from __future__ import annotations

import csv
from datetime import UTC, datetime
from pathlib import Path

from codigo.app.schemas.dataset import DatasetManifest, DatasetManifestRow
from codigo.app.schemas.executor_results import ManifestResult
from codigo.app.schemas.state import ArtifactRef, PipelineError

LOAD_RPM = [(0, 1797), (1, 1772), (2, 1750), (3, 1730)]
NORMAL_IDS = dict(zip(["97", "98", "99", "100"], LOAD_RPM, strict=True))
TARGET_SAMPLE_RATE_HZ = 12000

FAULT_GROUPS = [
    ("inner_race", 0.007, ["105", "106", "107", "108"], None),
    ("ball", 0.007, ["118", "119", "120", "121"], None),
    ("outer_race", 0.007, ["130", "131", "132", "133"], "outer_position=6"),
    ("outer_race", 0.007, ["144", "145", "146", "147"], "outer_position=3"),
    ("outer_race", 0.007, ["156", "158", "159", "160"], "outer_position=12"),
    ("inner_race", 0.014, ["169", "170", "171", "172"], None),
    ("ball", 0.014, ["185", "186", "187", "188"], None),
    ("outer_race", 0.014, ["197", "198", "199", "200"], "outer_position=6"),
    ("inner_race", 0.021, ["209", "210", "211", "212"], None),
    ("ball", 0.021, ["222", "223", "224", "225"], None),
    ("outer_race", 0.021, ["234", "235", "236", "237"], "outer_position=6"),
    ("outer_race", 0.021, ["246", "247", "248", "249"], "outer_position=3"),
    ("outer_race", 0.021, ["258", "259", "260", "261"], "outer_position=12"),
    ("inner_race", 0.028, ["3001", "3002", "3003", "3004"], None),
    ("ball", 0.028, ["3005", "3006", "3007", "3008"], None),
]

FAULT_IDS = {
    file_id: (fault_type, diameter, load, rpm, note)
    for fault_type, diameter, file_ids, note in FAULT_GROUPS
    for file_id, (load, rpm) in zip(file_ids, LOAD_RPM, strict=True)
}

MANIFEST_FIELDS = list(DatasetManifestRow.model_fields)


def build_cwru_manifest(
    raw_dir: str | Path,
    manifest_path: str | Path | None = None,
) -> DatasetManifest:
    """Construye el manifiesto para los `.mat` presentes en `raw_dir`."""

    raw_path = Path(raw_dir)
    files = sorted(raw_path.glob("*.mat"), key=lambda path: int(path.stem))
    if not files:
        raise ValueError(f"no .mat files found in {raw_path}")

    rows = [_row_from_file(path) for path in files]
    return DatasetManifest(
        dataset="cwru_bearing",
        rows=rows,
        manifest_path=str(manifest_path) if manifest_path else None,
    )


def generate_cwru_manifest(
    raw_dir: str | Path = "codigo/data/raw/cwru_bearing/mat",
    output_path: str | Path = "codigo/data/interim/cwru_bearing/manifest.csv",
) -> ManifestResult:
    """Genera `manifest.csv` y devuelve un resultado estructurado."""

    started_at = datetime.now(UTC)
    output = Path(output_path)
    try:
        manifest = build_cwru_manifest(raw_dir, output)
        output.parent.mkdir(parents=True, exist_ok=True)
        _write_manifest(output, manifest)
        artifact = ArtifactRef(
            name="cwru_manifest",
            artifact_type="manifest",
            path=str(output),
            producer="manifest_executor",
            metadata={"n_rows": len(manifest.rows), **manifest.label_counts},
        )
        return ManifestResult(
            executor_name="dataset_manifest",
            status="success",
            message="CWRU manifest generated.",
            artifacts=[artifact],
            errors=[],
            state_updates={"manifest_path": str(output)},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            manifest_path=str(output),
            n_rows=len(manifest.rows),
            label_counts=manifest.label_counts,
        )
    except Exception as exc:
        error = PipelineError(
            stage="dataset_manifest",
            node="manifest_executor",
            message=str(exc),
            recoverable=True,
        )
        return ManifestResult(
            executor_name="dataset_manifest",
            status="failed",
            message="CWRU manifest generation failed.",
            artifacts=[],
            errors=[error],
            state_updates={},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            manifest_path=str(output),
            n_rows=0,
            label_counts={"normal": 0, "fault": 0},
        )


def generate_dataset_manifest(
    raw_dir: str | Path,
    output_dir: str | Path,
    adapter_id: str | None = None,
) -> ManifestResult:
    """Genera un manifiesto usando un adaptador de dataset registrado."""

    from codigo.app.services.dataset_adapters import (
        get_dataset_adapter,
        infer_dataset_adapter,
    )

    started_at = datetime.now(UTC)
    output_path = Path(output_dir) / "manifest.csv"
    try:
        adapter = (
            get_dataset_adapter(adapter_id)
            if adapter_id is not None
            else infer_dataset_adapter(raw_dir)
        )
        if not adapter.info.supports_manifest:
            raise ValueError(
                f"adapter does not support manifest generation: {adapter.info.adapter_id}"
            )
        return adapter.build_manifest(Path(raw_dir), Path(output_dir))
    except Exception as exc:
        error = PipelineError(
            stage="dataset_manifest",
            node="manifest_executor",
            message=str(exc),
            recoverable=True,
        )
        return ManifestResult(
            executor_name="dataset_manifest",
            status="failed",
            message="Dataset manifest generation failed.",
            artifacts=[],
            errors=[error],
            state_updates={},
            started_at=started_at,
            finished_at=datetime.now(UTC),
            manifest_path=str(output_path),
            n_rows=0,
            label_counts={"normal": 0, "fault": 0},
        )


def _row_from_file(path: Path) -> DatasetManifestRow:
    file_id = path.stem
    if file_id in NORMAL_IDS:
        load, rpm = NORMAL_IDS[file_id]
        return DatasetManifestRow(
            file_id=file_id,
            dataset="cwru_bearing",
            source_path=path.as_posix(),
            label="normal",
            fault_type=None,
            fault_diameter_inch=None,
            load_hp=load,
            rpm=rpm,
            sensor_channel="DE_time",
            source_sample_rate_hz=48000,
            target_sample_rate_hz=TARGET_SAMPLE_RATE_HZ,
            source_format="mat",
            notes="normal_baseline",
        )
    if file_id not in FAULT_IDS:
        raise ValueError(f"unknown CWRU file_id: {file_id}")

    fault_type, diameter, load, rpm, note = FAULT_IDS[file_id]
    return DatasetManifestRow(
        file_id=file_id,
        dataset="cwru_bearing",
        source_path=path.as_posix(),
        label="fault",
        fault_type=fault_type,
        fault_diameter_inch=diameter,
        load_hp=load,
        rpm=rpm,
        sensor_channel="DE_time",
        source_sample_rate_hz=12000,
        target_sample_rate_hz=TARGET_SAMPLE_RATE_HZ,
        source_format="mat",
        notes=note,
    )


def _write_manifest(path: Path, manifest: DatasetManifest) -> None:
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=MANIFEST_FIELDS)
        writer.writeheader()
        for row in manifest.rows:
            writer.writerow(
                {key: "" if value is None else value for key, value in row.model_dump().items()}
            )
