"""Politica temporal trazable para habilitar NASA IMS en ejecuciones completas."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_FLOOR, Decimal
from pathlib import Path

from codigo.app.schemas.dataset import CommonManifestRecord
from codigo.app.schemas.executor_results import ManifestResult
from codigo.app.schemas.temporal_health import (
    DEFAULT_RUN_TO_FAILURE_PARTITION_POLICY,
    DEFAULT_TEMPORAL_GAP_POLICY,
    RunToFailurePartitionPolicy,
    TemporalGapPolicy,
)
from codigo.app.schemas.state import ArtifactRef
from codigo.app.services.common_manifest import read_common_manifest, write_common_manifest

NASA_IMS_TEMPORAL_POLICY_V1 = "nasa_ims_temporal_v1"
NASA_IMS_TEMPORAL_POLICY_LABEL_SOURCE = "temporal_proxy"
NASA_IMS_TEMPORAL_POLICY_MIN_RECORDS_PER_RUN = 3
NASA_IMS_TEMPORAL_POLICY_NORMAL_FRACTION = 0.4
NASA_IMS_RUN_TO_FAILURE_POLICY_V2 = "nasa_ims_run_to_failure_v2"
NASA_IMS_RUN_TO_FAILURE_BASELINE_LABEL_SOURCE = "temporal_proxy"


@dataclass(frozen=True)
class NasaIMSTemporalPolicySummary:
    """Resumen auditable de una aplicacion de politica temporal."""

    manifest_path: str
    n_rows: int
    label_counts: dict[str, int]
    split_counts: dict[str, int]
    run_counts: dict[str, int]
    source_manifest_path: str


@dataclass(frozen=True)
class NasaIMSRunToFailurePolicySummary:
    """Resumen de particion causal y continuidad producido por la politica v2."""

    manifest_path: str
    source_manifest_path: str
    n_rows: int
    partition_policy_id: str
    gap_policy_id: str
    partition_counts: dict[str, int]
    split_counts: dict[str, int]
    label_counts: dict[str, int]
    run_counts: dict[str, int]
    n_intervals: int
    cadence_interval_counts: dict[str, int]
    cadence_match_count: int
    cadence_deviation_count: int
    gap_count: int
    max_interval_seconds: float | None


@dataclass(frozen=True)
class _V2RunResult:
    records: list[CommonManifestRecord]
    partition_counts: dict[str, int]
    interval_counts: Counter[str]
    n_intervals: int
    cadence_match_count: int
    gap_count: int
    max_interval_seconds: float | None


def apply_nasa_ims_temporal_policy_to_result(
    result: ManifestResult,
    output_dir: str | Path,
) -> ManifestResult:
    """Devuelve un ManifestResult apuntando al manifiesto con politica v1."""

    summary = apply_nasa_ims_temporal_policy(
        result.manifest_path,
        Path(output_dir) / "manifest_temporal_policy_v1.csv",
    )
    data_provenance = _manifest_result_data_provenance(result)
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
            "data_provenance": data_provenance,
            "dataset_policy_id": NASA_IMS_TEMPORAL_POLICY_V1,
            "label_source": NASA_IMS_TEMPORAL_POLICY_LABEL_SOURCE,
            "label_policy_id": NASA_IMS_TEMPORAL_POLICY_V1,
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
                "data_provenance": data_provenance,
            },
            "manifest_path": summary.manifest_path,
            "n_rows": summary.n_rows,
            "label_counts": summary.label_counts,
            "finished_at": datetime.now(UTC),
        }
    )


def apply_nasa_ims_run_to_failure_policy_v2_to_result(
    result: ManifestResult,
    output_dir: str | Path,
    *,
    partition_policy: RunToFailurePartitionPolicy | None = None,
    gap_policy: TemporalGapPolicy | None = None,
) -> ManifestResult:
    """Aplica la politica causal v2 a un manifiesto NASA IMS oficial."""

    data_provenance = _manifest_result_data_provenance(result)
    if data_provenance != "official":
        raise ValueError(
            "NASA IMS run-to-failure policy v2 requires official data provenance; "
            f"received {data_provenance}"
        )
    summary = apply_nasa_ims_run_to_failure_policy_v2(
        result.manifest_path,
        Path(output_dir) / "manifest_run_to_failure_v2.csv",
        partition_policy=partition_policy,
        gap_policy=gap_policy,
    )
    artifact = ArtifactRef(
        name="nasa_ims_run_to_failure_policy_manifest",
        artifact_type="manifest",
        path=summary.manifest_path,
        producer="manifest_executor",
        description=(
            "Manifiesto NASA IMS oficial con particion causal 20/10/70 y "
            "auditoria versionada de cadencia y gaps."
        ),
        metadata={
            "dataset": "nasa_ims_bearing",
            "data_provenance": "official",
            "dataset_policy_id": summary.partition_policy_id,
            "gap_policy_id": summary.gap_policy_id,
            "official_nasa_labels": False,
            "n_rows": summary.n_rows,
            "baseline_train_count": summary.partition_counts["baseline_train"],
            "calibration_count": summary.partition_counts["calibration"],
            "monitoring_count": summary.partition_counts["monitoring"],
            "n_intervals": summary.n_intervals,
            "cadence_match_count": summary.cadence_match_count,
            "cadence_deviation_count": summary.cadence_deviation_count,
            "gap_count": summary.gap_count,
            "max_interval_seconds": summary.max_interval_seconds,
            "source_manifest_path": summary.source_manifest_path,
        },
    )
    return result.model_copy(
        update={
            "message": (
                "NASA IMS official manifest generated and causal "
                "run-to-failure policy v2 applied."
            ),
            "artifacts": [*result.artifacts, artifact],
            "state_updates": {
                **result.state_updates,
                "manifest_path": summary.manifest_path,
                "dataset_policy_id": summary.partition_policy_id,
                "data_provenance": "official",
            },
            "manifest_path": summary.manifest_path,
            "n_rows": summary.n_rows,
            "label_counts": summary.label_counts,
            "finished_at": datetime.now(UTC),
        }
    )


def _manifest_result_data_provenance(result: ManifestResult) -> str:
    for artifact in result.artifacts:
        value = artifact.metadata.get("data_provenance")
        if value in {"official", "synthetic", "unknown"}:
            return str(value)
    value = result.state_updates.get("data_provenance")
    if value in {"official", "synthetic", "unknown"}:
        return str(value)
    return "unknown"


def apply_nasa_ims_run_to_failure_policy_v2(
    manifest_path: str | Path,
    output_path: str | Path,
    *,
    partition_policy: RunToFailurePartitionPolicy | None = None,
    gap_policy: TemporalGapPolicy | None = None,
) -> NasaIMSRunToFailurePolicySummary:
    """Congela split 20/10/70 y audita continuidad sin crear fallo proxy."""

    active_partition_policy = (
        partition_policy or DEFAULT_RUN_TO_FAILURE_PARTITION_POLICY
    )
    active_gap_policy = gap_policy or DEFAULT_TEMPORAL_GAP_POLICY
    source = Path(manifest_path)
    records = read_common_manifest(source)
    if not records:
        raise ValueError(f"empty NASA IMS manifest: {source}")
    if any(record.dataset != "nasa_ims_bearing" for record in records):
        raise ValueError(
            "run-to-failure policy v2 only supports nasa_ims_bearing records"
        )
    _validate_v2_official_provenance(records)

    rewritten: list[CommonManifestRecord] = []
    partition_counts: Counter[str] = Counter()
    interval_counts: Counter[str] = Counter()
    n_intervals = 0
    cadence_match_count = 0
    gap_count = 0
    max_intervals: list[float] = []
    grouped = _records_by_run(records)
    for group_key in sorted(grouped):
        if group_key == "unknown_run":
            raise ValueError(
                "NASA IMS run-to-failure policy v2 requires a stable run_id"
            )
        ordered = _temporal_order(grouped[group_key])
        if len(ordered) < active_partition_policy.min_records_per_run:
            raise ValueError(
                "NASA IMS run-to-failure policy v2 requires at least "
                f"{active_partition_policy.min_records_per_run} records per run; "
                f"{group_key} has {len(ordered)}"
            )
        run_result = _apply_v2_policy_to_run(
            ordered,
            group_key=group_key,
            partition_policy=active_partition_policy,
            gap_policy=active_gap_policy,
        )
        rewritten.extend(run_result.records)
        partition_counts.update(run_result.partition_counts)
        interval_counts.update(run_result.interval_counts)
        n_intervals += run_result.n_intervals
        cadence_match_count += run_result.cadence_match_count
        gap_count += run_result.gap_count
        if run_result.max_interval_seconds is not None:
            max_intervals.append(run_result.max_interval_seconds)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    write_common_manifest(output, rewritten)
    return NasaIMSRunToFailurePolicySummary(
        manifest_path=output.as_posix(),
        source_manifest_path=source.as_posix(),
        n_rows=len(rewritten),
        partition_policy_id=active_partition_policy.policy_id,
        gap_policy_id=active_gap_policy.policy_id,
        partition_counts=dict(partition_counts),
        split_counts=dict(
            Counter(str(record.metadata_json["split_hint"]) for record in rewritten)
        ),
        label_counts=dict(Counter(record.label for record in rewritten)),
        run_counts=dict(Counter(record.run_id or "unknown_run" for record in rewritten)),
        n_intervals=n_intervals,
        cadence_interval_counts=dict(sorted(interval_counts.items())),
        cadence_match_count=cadence_match_count,
        cadence_deviation_count=n_intervals - cadence_match_count,
        gap_count=gap_count,
        max_interval_seconds=max(max_intervals) if max_intervals else None,
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
    records = read_common_manifest(source)
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
    write_common_manifest(output, rewritten)
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
            "label_granularity": "proxy_temporal",
            "label_policy_id": NASA_IMS_TEMPORAL_POLICY_V1,
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


def _apply_v2_policy_to_run(
    records: list[CommonManifestRecord],
    *,
    group_key: str,
    partition_policy: RunToFailurePartitionPolicy,
    gap_policy: TemporalGapPolicy,
) -> _V2RunResult:
    counts = _allocate_v2_partition_counts(len(records), partition_policy)
    baseline_end = counts["baseline_train"]
    calibration_end = baseline_end + counts["calibration"]
    rewritten: list[CommonManifestRecord] = []
    interval_counts: Counter[str] = Counter()
    cadence_match_count = 0
    gap_count = 0
    max_interval: float | None = None
    previous_timestamp: datetime | None = None
    temporal_segment_index = 0

    for index, record in enumerate(records):
        timestamp = record.timestamp_start
        if timestamp is None:
            raise ValueError(
                "NASA IMS run-to-failure policy v2 requires timestamp_start for "
                f"every record; missing in {record.record_id}"
            )

        interval_seconds: float | None = None
        cadence_matches: bool | None = None
        gap_before = False
        estimated_missing_snapshots = 0
        if previous_timestamp is not None:
            interval_seconds = float((timestamp - previous_timestamp).total_seconds())
            if interval_seconds <= 0.0:
                raise ValueError(
                    "NASA IMS run-to-failure policy v2 requires strictly "
                    f"increasing timestamps in {group_key}; found interval "
                    f"{interval_seconds:g} before {record.record_id}"
                )
            interval_counts[_interval_key(interval_seconds)] += 1
            cadence_matches = (
                abs(interval_seconds - gap_policy.expected_cadence_seconds)
                <= gap_policy.cadence_match_tolerance_seconds
            )
            if cadence_matches:
                cadence_match_count += 1
            gap_before = (
                interval_seconds > gap_policy.max_contiguous_interval_seconds
            )
            if gap_before:
                gap_count += 1
                temporal_segment_index += 1
                estimated_missing_snapshots = max(
                    0,
                    int(round(interval_seconds / gap_policy.expected_cadence_seconds))
                    - 1,
                )
            max_interval = (
                interval_seconds
                if max_interval is None
                else max(max_interval, interval_seconds)
            )

        partition, split = _v2_partition_and_split(
            index,
            baseline_end=baseline_end,
            calibration_end=calibration_end,
            policy=partition_policy,
        )
        is_baseline = partition == "baseline_train"
        metadata = {
            **record.metadata_json,
            "dataset_policy_id": partition_policy.policy_id,
            "partition_policy_id": partition_policy.policy_id,
            "partition_allocation_method": partition_policy.allocation_method,
            "partition_baseline_fraction": partition_policy.baseline_fraction,
            "partition_calibration_fraction": partition_policy.calibration_fraction,
            "partition_monitoring_fraction": partition_policy.monitoring_fraction,
            "temporal_partition": partition,
            "temporal_phase": partition,
            "split_hint": split,
            "split_source": partition_policy.policy_id,
            "label_source": (
                NASA_IMS_RUN_TO_FAILURE_BASELINE_LABEL_SOURCE
                if is_baseline
                else "none"
            ),
            "label_granularity": "proxy_temporal" if is_baseline else "none",
            "label_policy_id": partition_policy.policy_id,
            "official_nasa_labels": False,
            "official_window_labels": False,
            "protocol_baseline_assumption": is_baseline,
            "temporal_group_id": group_key,
            "temporal_order_index": index,
            "temporal_order_count": len(records),
            "partition_baseline_count": counts["baseline_train"],
            "partition_calibration_count": counts["calibration"],
            "partition_monitoring_count": counts["monitoring"],
            "temporal_gap_policy_id": gap_policy.policy_id,
            "expected_cadence_seconds": gap_policy.expected_cadence_seconds,
            "cadence_match_tolerance_seconds": (
                gap_policy.cadence_match_tolerance_seconds
            ),
            "max_contiguous_interval_seconds": (
                gap_policy.max_contiguous_interval_seconds
            ),
            "gap_operator": gap_policy.gap_operator,
            "gap_resets_alert_persistence": gap_policy.reset_alert_persistence,
            "gap_resets_causal_smoothing": gap_policy.reset_causal_smoothing,
            "interval_from_previous_seconds": interval_seconds,
            "cadence_matches_expected": cadence_matches,
            "gap_before": gap_before,
            "gap_before_seconds": interval_seconds if gap_before else None,
            "estimated_missing_snapshots_before": estimated_missing_snapshots,
            "temporal_segment_index": temporal_segment_index,
        }
        rewritten.append(
            record.model_copy(
                update={
                    "label": "normal" if is_baseline else "unknown",
                    "label_detail": (
                        "protocol_baseline_assumption"
                        if is_baseline
                        else None
                    ),
                    "metadata_json": metadata,
                    "notes": _v2_policy_notes(record, partition),
                }
            )
        )
        previous_timestamp = timestamp

    return _V2RunResult(
        records=rewritten,
        partition_counts=counts,
        interval_counts=interval_counts,
        n_intervals=max(0, len(records) - 1),
        cadence_match_count=cadence_match_count,
        gap_count=gap_count,
        max_interval_seconds=max_interval,
    )


def _allocate_v2_partition_counts(
    n_records: int,
    policy: RunToFailurePartitionPolicy,
) -> dict[str, int]:
    """Distribuye enteros con restos mayores y desempate por orden causal."""

    roles = list(policy.partition_order)
    fractions = [
        Decimal(str(policy.baseline_fraction)),
        Decimal(str(policy.calibration_fraction)),
        Decimal(str(policy.monitoring_fraction)),
    ]
    exact = [Decimal(n_records) * fraction for fraction in fractions]
    allocated = [
        int(value.to_integral_value(rounding=ROUND_FLOOR)) for value in exact
    ]
    remaining = n_records - sum(allocated)
    ranked_indexes = sorted(
        range(len(roles)),
        key=lambda item: (-(exact[item] - Decimal(allocated[item])), item),
    )
    for item in ranked_indexes[:remaining]:
        allocated[item] += 1
    counts = dict(zip(roles, allocated, strict=True))
    if any(counts[role] <= 0 for role in roles):
        raise ValueError(
            "NASA IMS run-to-failure policy v2 requires non-empty baseline, "
            "calibration and monitoring partitions"
        )
    if sum(counts.values()) != n_records:
        raise RuntimeError("run-to-failure partition allocation is inconsistent")
    return counts


def _v2_partition_and_split(
    index: int,
    *,
    baseline_end: int,
    calibration_end: int,
    policy: RunToFailurePartitionPolicy,
) -> tuple[str, str]:
    if index < baseline_end:
        return "baseline_train", policy.baseline_split
    if index < calibration_end:
        return "calibration", policy.calibration_split
    return "monitoring", policy.monitoring_split


def _validate_v2_official_provenance(
    records: list[CommonManifestRecord],
) -> None:
    identities: set[tuple[str, str]] = set()
    for record in records:
        metadata = record.metadata_json
        evidence_path = str(metadata.get("provenance_evidence_path") or "").strip()
        evidence_sha256 = str(
            metadata.get("provenance_evidence_sha256") or ""
        ).strip()
        is_official = (
            record.data_provenance == "official"
            and metadata.get("data_provenance") == "official"
            and metadata.get("official_nasa_measurements") is True
            and metadata.get("provenance_detection_method")
            == "official_dataset_provenance"
            and bool(evidence_path)
            and _is_sha256(evidence_sha256)
        )
        if not is_official:
            raise ValueError(
                "NASA IMS run-to-failure policy v2 requires official data "
                f"provenance for every record; invalid record {record.record_id}"
            )
        identities.add((evidence_path, evidence_sha256))
    if len(identities) != 1:
        raise ValueError(
            "NASA IMS run-to-failure policy v2 requires one frozen official "
            "provenance identity per manifest"
        )


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(
        character in "0123456789abcdef" for character in value
    )


def _interval_key(value: float) -> str:
    return f"{value:.6f}".rstrip("0").rstrip(".")


def _v2_policy_notes(record: CommonManifestRecord, partition: str) -> str:
    original = record.notes or ""
    parts = [
        "run_to_failure_policy_v2",
        f"temporal_partition={partition}",
        "not_official_nasa_snapshot_label",
        f"original_label={record.label}",
    ]
    if original:
        parts.append(f"original_notes={original}")
    return "; ".join(parts)
