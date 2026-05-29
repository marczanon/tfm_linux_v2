"""Politica temporal trazable para habilitar NASA IMS en ejecuciones completas."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from codigo.app.schemas.dataset import CommonManifestRecord
from codigo.app.schemas.executor_results import ManifestResult
from codigo.app.schemas.state import ArtifactRef

NASA_IMS_TEMPORAL_POLICY_V1 = "nasa_ims_temporal_v1"
NASA_IMS_TEMPORAL_POLICY_LABEL_SOURCE = "temporal_proxy_v1"
NASA_IMS_TEMPORAL_POLICY_MIN_RECORDS_PER_RUN = 3
NASA_IMS_TEMPORAL_POLICY_NORMAL_FRACTION = 0.4


@dataclass(frozen=True)
class NasaIMSTemporalPolicySummary:
    """Resumen auditable de una aplicacion de politica temporal."""

    manifest_path: str
    n_rows: int
    label_counts: dict[str, int]
    split_counts: dict[str, int]
    run_counts: dict[str, int]
    source_manifest_path: str


def apply_nasa_ims_temporal_policy_to_result(
    result: ManifestResult,
    output_dir: str | Path,
) -> ManifestResult:
    """Devuelve un ManifestResult apuntando al manifiesto con politica v1."""

    summary = apply_nasa_ims_temporal_policy(
        result.manifest_path,
        Path(output_dir) / "manifest_temporal_policy_v1.csv",
    )
    artifact = ArtifactRef(
        name="nasa_ims_temporal_policy_manifest",
        artifact_type="manifest",
        path=summary.manifest_path,
        producer="manifest_executor",
        description=(
            "Manifiesto NASA IMS con etiquetas proxy temporales versionadas; "
            "no son etiquetas oficiales de NASA."
        ),
        metadata={
            "dataset": "nasa_ims_bearing",
            "dataset_policy_id": NASA_IMS_TEMPORAL_POLICY_V1,
            "label_source": NASA_IMS_TEMPORAL_POLICY_LABEL_SOURCE,
            "official_nasa_labels": False,
            "n_rows": summary.n_rows,
            "source_manifest_path": summary.source_manifest_path,
            **summary.label_counts,
        },
    )
    return result.model_copy(
        update={
            "message": (
                "NASA IMS manifest generated and temporal proxy policy v1 applied."
            ),
            "artifacts": [*result.artifacts, artifact],
            "state_updates": {
                **result.state_updates,
                "manifest_path": summary.manifest_path,
                "dataset_policy_id": NASA_IMS_TEMPORAL_POLICY_V1,
            },
            "manifest_path": summary.manifest_path,
            "n_rows": summary.n_rows,
            "label_counts": summary.label_counts,
            "finished_at": datetime.now(UTC),
        }
    )


def apply_nasa_ims_temporal_policy(
    manifest_path: str | Path,
    output_path: str | Path,
    *,
    normal_fraction: float = NASA_IMS_TEMPORAL_POLICY_NORMAL_FRACTION,
) -> NasaIMSTemporalPolicySummary:
    """Etiqueta cada run NASA IMS por orden temporal y escribe un manifiesto nuevo."""

    if not 0.0 < normal_fraction < 1.0:
        raise ValueError("normal_fraction must be in (0, 1)")

    source = Path(manifest_path)
    records = _read_common_manifest(source)
    if not records:
        raise ValueError(f"empty NASA IMS manifest: {source}")
    if any(record.dataset != "nasa_ims_bearing" for record in records):
        raise ValueError("temporal policy v1 only supports nasa_ims_bearing records")

    rewritten: list[CommonManifestRecord] = []
    for group_key, group_records in _records_by_run(records).items():
        ordered = _temporal_order(group_records)
        if len(ordered) < NASA_IMS_TEMPORAL_POLICY_MIN_RECORDS_PER_RUN:
            raise ValueError(
                "NASA IMS temporal policy v1 requires at least "
                f"{NASA_IMS_TEMPORAL_POLICY_MIN_RECORDS_PER_RUN} records per run; "
                f"{group_key} has {len(ordered)}"
            )
        rewritten.extend(
            _apply_policy_to_run(
                ordered,
                group_key=group_key,
                normal_fraction=normal_fraction,
            )
        )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_common_manifest(output, rewritten)
    return NasaIMSTemporalPolicySummary(
        manifest_path=output.as_posix(),
        n_rows=len(rewritten),
        label_counts=dict(Counter(record.label for record in rewritten)),
        split_counts=dict(
            Counter(str(record.metadata_json["split_hint"]) for record in rewritten)
        ),
        run_counts=dict(Counter(record.run_id or "unknown_run" for record in rewritten)),
        source_manifest_path=source.as_posix(),
    )


def _apply_policy_to_run(
    records: list[CommonManifestRecord],
    *,
    group_key: str,
    normal_fraction: float,
) -> list[CommonManifestRecord]:
    n_records = len(records)
    n_normal = max(2, int(n_records * normal_fraction))
    n_normal = min(n_records - 1, n_normal)
    n_train = max(1, int(n_normal * 0.6))
    normal_remaining = n_normal - n_train
    n_validation = 1 if normal_remaining >= 2 else 0

    rewritten: list[CommonManifestRecord] = []
    for index, record in enumerate(records):
        if index < n_normal:
            label = "normal"
            phase = "nominal_proxy"
            if index < n_train:
                split = "train"
            elif index < n_train + n_validation:
                split = "validation"
            else:
                split = "test"
            label_detail = "temporal_proxy_nominal_phase"
        else:
            label = "degradation"
            phase = "degradation_proxy"
            split = "test"
            final_failure = record.metadata_json.get("final_failure") or record.label_detail
            label_detail = f"temporal_proxy_degradation_to_{final_failure}"

        metadata = {
            **record.metadata_json,
            "dataset_policy_id": NASA_IMS_TEMPORAL_POLICY_V1,
            "label_source": NASA_IMS_TEMPORAL_POLICY_LABEL_SOURCE,
            "official_nasa_labels": False,
            "temporal_group_id": group_key,
            "temporal_order_index": index,
            "temporal_order_count": n_records,
            "temporal_phase": phase,
            "split_hint": split,
            "split_source": NASA_IMS_TEMPORAL_POLICY_V1,
            "temporal_policy_normal_fraction": normal_fraction,
        }
        rewritten.append(
            record.model_copy(
                update={
                    "label": label,
                    "label_detail": label_detail,
                    "metadata_json": metadata,
                    "notes": _policy_notes(record),
                }
            )
        )
    return rewritten


def _records_by_run(
    records: list[CommonManifestRecord],
) -> dict[str, list[CommonManifestRecord]]:
    groups: dict[str, list[CommonManifestRecord]] = defaultdict(list)
    for record in records:
        groups[record.run_id or "unknown_run"].append(record)
    return dict(groups)


def _temporal_order(records: list[CommonManifestRecord]) -> list[CommonManifestRecord]:
    return sorted(
        records,
        key=lambda record: (
            record.timestamp_start or datetime.min,
            record.source_path,
            record.record_id,
        ),
    )


def _policy_notes(record: CommonManifestRecord) -> str:
    original = record.notes or ""
    parts = [
        "temporal_policy_v1_proxy_label",
        "not_official_nasa_label",
        f"original_label={record.label}",
    ]
    if original:
        parts.append(f"original_notes={original}")
    return "; ".join(parts)


def _read_common_manifest(path: Path) -> list[CommonManifestRecord]:
    with path.open(encoding="utf-8") as file:
        return [
            _deserialize_common_manifest_row(row)
            for row in csv.DictReader(file)
        ]


def _deserialize_common_manifest_row(row: dict[str, str]) -> CommonManifestRecord:
    data: dict[str, Any] = dict(row)
    data["channel_names"] = _json_list(row.get("channel_names"))
    data["metadata_json"] = _json_object(row.get("metadata_json"))
    for key in ["timestamp_start", "timestamp_end"]:
        if not str(data.get(key) or "").strip():
            data[key] = None
    for key in ["sampling_rate_hz", "target_sample_rate_hz"]:
        if not str(data.get(key) or "").strip():
            data[key] = None
    return CommonManifestRecord.model_validate(data)


def _write_common_manifest(
    path: Path,
    records: list[CommonManifestRecord],
) -> None:
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


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = str(value).strip()
    return stripped or None
