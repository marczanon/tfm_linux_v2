from __future__ import annotations

import copy
import hashlib
import json
import unittest
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError

from codigo.app.schemas.monitoring_replay import (
    ActivePolicyRefs,
    CausalEvidenceArtifact,
    CausalEvidenceCatalog,
    CausalEvidenceCatalogEntry,
    CausalInputView,
)
from codigo.app.services.monitoring_replay import MonitoringReplayConflictError
from codigo.app.services.monitoring_review_store import (
    build_causal_evidence_catalog,
    validate_causal_evidence_catalog,
)


SOURCE_START = datetime(2004, 2, 12, 10, 0, 0)
RUNTIME_TIME = datetime(2026, 8, 12, 12, 0, tzinfo=UTC)
EVIDENCE_FIELDS = (
    "record_id",
    "asset_id",
    "channel_id",
    "snapshot_id",
    "source_time",
    "analysis_status",
    "score",
    "threshold",
    "health_state",
)


def _canonical_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _records(count: int) -> list[dict[str, object]]:
    return [
        {
            "record_id": f"frame-{index:03d}",
            "asset_id": f"bearing_{(index % 4) + 1}",
            "channel_id": f"channel_{(index % 4) + 1}",
            "snapshot_id": f"snapshot-{index:03d}",
            "source_time": (
                SOURCE_START + timedelta(minutes=10 * index)
            ).isoformat(),
            "analysis_status": "modeled",
            "score": float(index) / 10.0,
            "threshold": 0.5,
            "health_state": "warning" if index else "healthy",
        }
        for index in range(count)
    ]


def _causal_view(records: list[dict[str, object]]) -> CausalInputView:
    artifact_sha256 = hashlib.sha256(
        json.dumps(
            records,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    cutoff_record = max(
        records,
        key=lambda record: datetime.fromisoformat(str(record["source_time"])),
    )
    cutoff = datetime.fromisoformat(str(cutoff_record["source_time"]))
    artifact = CausalEvidenceArtifact(
        evidence_id="evidence:catalog-session:trigger-001",
        artifact_ref="artifact:monitoring-evidence:catalog-fixture",
        artifact_sha256=artifact_sha256,
        available_at_cursor=len(records) - 1,
        max_source_time=cutoff,
        record_count=len(records),
        fields=EVIDENCE_FIELDS,
    )
    payload = {
        "view_id": "causal-view:catalog-session:trigger-001",
        "session_id": "catalog-session",
        "trigger_id": "trigger-001",
        "trigger_event_id": "trigger-001:event:001",
        "origin_tick_id": f"tick-{len(records) - 1:03d}",
        "cutoff_snapshot_id": str(cutoff_record["snapshot_id"]),
        "cursor": len(records) - 1,
        "cutoff_source_time": cutoff,
        "active_policy_refs": ActivePolicyRefs(
            scoring_version="scoring-v1",
            activation_version="activation-v1",
        ),
        "manifest_projection_ref": "artifact:manifest-projection:catalog-fixture",
        "manifest_projection_sha256": "c" * 64,
        "partition_policy_id": "nasa_ims_run_to_failure_v2",
        "visible_partitions": ("monitoring",),
        "whitelisted_fields": EVIDENCE_FIELDS,
        "evidence": (artifact,),
        "created_at": RUNTIME_TIME,
    }
    payload["view_sha256"] = CausalInputView.canonical_sha256(payload)
    return CausalInputView.model_validate(payload)


def _resealed_catalog(payload: dict[str, object]) -> CausalEvidenceCatalog:
    candidate = copy.deepcopy(payload)
    candidate.pop("catalog_sha256", None)
    candidate["catalog_sha256"] = CausalEvidenceCatalog.canonical_sha256(
        candidate
    )
    return CausalEvidenceCatalog.model_validate(candidate)


class MonitoringEvidenceCatalogTests(unittest.TestCase):
    def test_twelve_records_keep_order_handles_and_stable_hashes(self) -> None:
        records = _records(12)
        view = _causal_view(records)

        catalog = build_causal_evidence_catalog(view, records)
        rebuilt = build_causal_evidence_catalog(view, copy.deepcopy(records))

        self.assertEqual(
            tuple(entry.handle for entry in catalog.entries),
            tuple(f"E{index:02d}" for index in range(1, 13)),
        )
        self.assertEqual(
            tuple(entry.record_index for entry in catalog.entries),
            tuple(range(12)),
        )
        self.assertEqual(
            tuple(entry.record_id for entry in catalog.entries),
            tuple(str(record["record_id"]) for record in records),
        )
        self.assertEqual(
            catalog.causal_scope_refs,
            (view.evidence[0].evidence_id,),
        )
        self.assertEqual(
            catalog.source_artifact_sha256,
            view.evidence[0].artifact_sha256,
        )
        for entry, record in zip(catalog.entries, records, strict=True):
            record_sha256 = _canonical_sha256(record)
            self.assertEqual(entry.record_sha256, record_sha256)
            self.assertEqual(
                entry.support_ref,
                (
                    "causal-record:"
                    f"{view.evidence[0].artifact_sha256}:{record_sha256}"
                ),
            )
        self.assertEqual(
            catalog.catalog_sha256,
            CausalEvidenceCatalog.canonical_sha256(catalog),
        )
        self.assertEqual(rebuilt, catalog)

    def test_mutated_or_reordered_records_fail_under_the_original_seal(self) -> None:
        records = _records(12)
        view = _causal_view(records)
        mutated = copy.deepcopy(records)
        mutated[5]["score"] = 999.0
        reordered = list(reversed(copy.deepcopy(records)))

        for candidate in (mutated, reordered):
            with self.subTest(first_record=candidate[0]["record_id"]):
                with self.assertRaisesRegex(
                    MonitoringReplayConflictError,
                    "sealed artifact SHA-256",
                ):
                    build_causal_evidence_catalog(view, candidate)

    def test_resealed_order_changes_mapping_view_and_catalog_hashes(self) -> None:
        records = _records(12)
        original_view = _causal_view(records)
        original = build_causal_evidence_catalog(original_view, records)
        reversed_records = list(reversed(copy.deepcopy(records)))
        reversed_view = _causal_view(reversed_records)
        reordered = build_causal_evidence_catalog(
            reversed_view,
            reversed_records,
        )

        self.assertEqual(original.entries[0].record_id, "frame-000")
        self.assertEqual(reordered.entries[0].handle, "E01")
        self.assertEqual(reordered.entries[0].record_id, "frame-011")
        self.assertNotEqual(original_view.view_sha256, reversed_view.view_sha256)
        self.assertNotEqual(
            original.source_artifact_sha256,
            reordered.source_artifact_sha256,
        )
        self.assertNotEqual(original.catalog_sha256, reordered.catalog_sha256)

    def test_validator_rejects_a_resealed_but_swapped_mapping(self) -> None:
        records = _records(12)
        view = _causal_view(records)
        catalog = build_causal_evidence_catalog(view, records)
        payload = catalog.model_dump(mode="python")
        first = payload["entries"][0]
        second = payload["entries"][1]
        for field_name in (
            "support_ref",
            "record_id",
            "record_sha256",
            "display_projection_sha256",
        ):
            first[field_name], second[field_name] = (
                second[field_name],
                first[field_name],
            )
        tampered = _resealed_catalog(payload)

        with self.assertRaisesRegex(
            MonitoringReplayConflictError,
            "does not match its sealed view and records",
        ):
            validate_causal_evidence_catalog(view, records, tampered)

    def test_support_refs_roundtrip_exactly_to_their_selected_handles(self) -> None:
        records = _records(12)
        catalog = build_causal_evidence_catalog(_causal_view(records), records)
        by_handle = {
            entry.handle: entry.support_ref for entry in catalog.entries
        }
        handle_by_ref = {
            entry.support_ref: entry.handle for entry in catalog.entries
        }
        selected_handles = ("E02", "E11")

        selected_support_refs = tuple(
            by_handle[handle] for handle in selected_handles
        )

        self.assertEqual(
            tuple(handle_by_ref[ref] for ref in selected_support_refs),
            selected_handles,
        )
        self.assertEqual(len(handle_by_ref), len(catalog.entries))
        self.assertNotEqual(
            selected_support_refs,
            tuple(entry.support_ref for entry in catalog.entries),
        )

    def test_catalog_schema_rejects_duplicate_and_noncontiguous_shape(self) -> None:
        records = _records(5)
        catalog = build_causal_evidence_catalog(_causal_view(records), records)
        base = catalog.model_dump(mode="python")
        mutations = {
            "duplicate_support_ref": lambda entries: entries[1].update(
                support_ref=entries[0]["support_ref"]
            ),
            "duplicate_record_id": lambda entries: entries[1].update(
                record_id=entries[0]["record_id"]
            ),
            "duplicate_record_sha256": lambda entries: entries[1].update(
                record_sha256=entries[0]["record_sha256"]
            ),
            "duplicate_handle": lambda entries: entries[1].update(handle="E01"),
            "noncontiguous_index": lambda entries: entries[1].update(
                record_index=7
            ),
            "foreign_scope": lambda entries: entries[1].update(
                causal_scope_ref="evidence:foreign"
            ),
        }

        for case_name, mutate in mutations.items():
            with self.subTest(case_name=case_name):
                payload = copy.deepcopy(base)
                mutate(payload["entries"])
                payload.pop("catalog_sha256")
                payload["catalog_sha256"] = CausalEvidenceCatalog.canonical_sha256(
                    payload
                )
                with self.assertRaises(ValidationError):
                    CausalEvidenceCatalog.model_validate(payload)

    def test_builder_rejects_duplicate_record_ids_even_when_artifact_is_sealed(
        self,
    ) -> None:
        records = _records(5)
        records[1]["record_id"] = records[0]["record_id"]
        view = _causal_view(records)

        with self.assertRaisesRegex(
            MonitoringReplayConflictError,
            "unique record_id",
        ):
            build_causal_evidence_catalog(view, records)

    def test_five_record_catalog_uses_the_actual_dynamic_prefix(self) -> None:
        records = _records(5)
        view = _causal_view(records)
        catalog = build_causal_evidence_catalog(view, records)

        self.assertEqual(
            tuple(entry.handle for entry in catalog.entries),
            ("E01", "E02", "E03", "E04", "E05"),
        )
        self.assertEqual(len(catalog.entries), 5)
        validate_causal_evidence_catalog(view, records, catalog)
        self.assertEqual(
            CausalEvidenceCatalog.model_validate(
                catalog.model_dump(mode="json")
            ),
            catalog,
        )

    def test_entry_handle_rejects_noncanonical_shapes(self) -> None:
        records = _records(5)
        entry = build_causal_evidence_catalog(
            _causal_view(records),
            records,
        ).entries[0]
        payload = entry.model_dump(mode="python")

        for invalid_handle in ("E00", "E1", "e01", "E100"):
            with self.subTest(handle=invalid_handle):
                with self.assertRaises(ValidationError):
                    CausalEvidenceCatalogEntry.model_validate(
                        {**payload, "handle": invalid_handle}
                    )


if __name__ == "__main__":
    unittest.main()
