import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import httpx

from codigo.app.api import create_app
from codigo.app.schemas.reasoning import ReasoningMemoryRecord
from codigo.app.services.memory_registry import (
    load_memory_governance_ledger,
    memory_governance_ledger_path,
)
from codigo.app.services.vector_memory import (
    LocalHashEmbeddingModel,
    LocalJsonVectorMemoryStore,
)


class APIMemoryTests(unittest.TestCase):
    def test_memory_status_reports_operational_corpus_and_stable_fingerprint(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            memory_dir = base / "memory"
            store = LocalJsonVectorMemoryStore(
                memory_dir,
                embedding_model=LocalHashEmbeddingModel(),
            )
            store.upsert(
                _record(
                    "memory-status-modeler",
                    dataset="nasa_ims_bearing",
                    data_provenance="official",
                )
            )
            store.upsert(
                _record(
                    "memory-status-structurer",
                    collection_name="structurer_memory",
                    target_agent="structurer",
                    dataset="cwru_bearing",
                    data_provenance="official",
                    memory_role="evidence",
                )
            )
            store.upsert(
                _record(
                    "memory-status-methodology",
                    collection_name="shared_methodology_memory",
                    target_agent="shared_methodology",
                    dataset=None,
                    data_provenance="official",
                    memory_role="methodology",
                )
            )
            app = create_app(
                runs_dir=base / "runs",
                reports_root=base / "reports",
                memory_dir=memory_dir,
                memory_store=store,
            )

            first_response = _get(app, "/memory/status")
            second_response = _get(app, "/memory/status")
            curation_response = _patch(
                app,
                "/memory/records/memory-status-modeler/curation",
                json={
                    "action": "exclude",
                    "reason": "Verify governance-sensitive corpus fingerprint.",
                    "reviewer": "test_runner",
                },
            )
            governed_response = _get(app, "/memory/status")

        self.assertEqual(first_response.status_code, 200)
        body = first_response.json()
        self.assertEqual(body["backend"]["configured_backend"], "json")
        self.assertEqual(
            body["backend"]["backend_name"],
            "local_json_vector_memory_store",
        )
        self.assertTrue(body["backend"]["operational"])
        self.assertEqual(body["corpus"]["total_records"], 3)
        self.assertEqual(body["corpus"]["reusable_records"], 3)
        self.assertEqual(body["corpus"]["official_records"], 3)
        self.assertEqual(body["corpus"]["official_reusable_records"], 3)
        self.assertEqual(body["corpus"]["shared_methodology_records"], 1)
        self.assertEqual(body["corpus"]["n_reusable_datasets"], 2)
        self.assertEqual(body["corpus"]["n_reusable_agents"], 2)
        self.assertRegex(body["corpus"]["corpus_fingerprint"], r"^[0-9a-f]{64}$")
        self.assertEqual(
            body["corpus"]["corpus_fingerprint"],
            second_response.json()["corpus"]["corpus_fingerprint"],
        )
        self.assertEqual(curation_response.status_code, 200)
        self.assertNotEqual(
            body["corpus"]["corpus_fingerprint"],
            governed_response.json()["corpus"]["corpus_fingerprint"],
        )
        self.assertFalse(body["corpus"]["frozen_manifest_available"])
        self.assertFalse(
            body["scientific_readiness"]["ready_for_memory_effect_benchmark"]
        )
        self.assertEqual(
            [
                blocker["code"]
                for blocker in body["scientific_readiness"]["blockers"]
            ],
            ["frozen_manifest_unavailable"],
        )

    def test_memory_status_returns_200_when_backend_is_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            store = Mock()
            store.backend_name = "qdrant_vector_memory_store"
            store.list_records.side_effect = RuntimeError("connection refused")
            app = create_app(
                runs_dir=base / "runs",
                reports_root=base / "reports",
                memory_dir=base / "memory",
                memory_store=store,
            )

            response = _get(app, "/memory/status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["backend"]["configured_backend"], "qdrant")
        self.assertFalse(body["backend"]["operational"])
        self.assertEqual(body["backend"]["error_type"], "RuntimeError")
        self.assertIn("connection refused", body["backend"]["diagnostic"])
        self.assertFalse(body["corpus"]["available"])
        self.assertEqual(body["corpus"]["total_records"], 0)
        self.assertIsNone(body["corpus"]["corpus_fingerprint"])
        blocker_codes = {
            blocker["code"]
            for blocker in body["scientific_readiness"]["blockers"]
        }
        self.assertIn("backend_unavailable", blocker_codes)
        self.assertNotIn("empty_corpus", blocker_codes)

    def test_memory_status_captures_backend_initialization_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            app = create_app(
                runs_dir=base / "runs",
                reports_root=base / "reports",
                memory_dir=base / "memory",
            )

            with patch.dict(
                os.environ,
                {
                    "TFM_MEMORY_BACKEND": "pgvector",
                    "TFM_EMBEDDING_PROVIDER": "local_hash",
                },
            ):
                response = _get(app, "/memory/status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["backend"]["configured_backend"], "pgvector")
        self.assertEqual(
            body["backend"]["backend_name"],
            "pgvector_vector_memory_store",
        )
        self.assertFalse(body["backend"]["operational"])
        self.assertEqual(
            body["backend"]["error_type"],
            "VectorMemoryConfigError",
        )

    def test_memory_status_explains_empty_corpus_and_pending_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            reports_root = base / "reports"
            _write_candidate(reports_root / "run" / "memory_candidate.json")
            memory_dir = base / "memory"
            store = LocalJsonVectorMemoryStore(
                memory_dir,
                embedding_model=LocalHashEmbeddingModel(),
            )
            app = create_app(
                runs_dir=base / "runs",
                reports_root=reports_root,
                memory_dir=memory_dir,
                memory_store=store,
            )

            response = _get(app, "/memory/status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["corpus"]["candidate_queue_available"])
        self.assertEqual(body["corpus"]["pending_candidates"], 1)
        blocker_codes = {
            blocker["code"]
            for blocker in body["scientific_readiness"]["blockers"]
        }
        self.assertTrue(
            {
                "empty_corpus",
                "no_reusable_memory",
                "no_official_provenance",
                "insufficient_dataset_coverage",
                "insufficient_agent_coverage",
                "pending_candidates",
                "frozen_manifest_unavailable",
            }.issubset(blocker_codes)
        )

    def test_memory_status_captures_candidate_queue_failure_without_500(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            candidate_path = base / "reports" / "run" / "memory_candidate.json"
            candidate_path.parent.mkdir(parents=True)
            candidate_path.write_text("not-json", encoding="utf-8")
            memory_dir = base / "memory"
            store = LocalJsonVectorMemoryStore(
                memory_dir,
                embedding_model=LocalHashEmbeddingModel(),
            )
            app = create_app(
                runs_dir=base / "runs",
                reports_root=base / "reports",
                memory_dir=memory_dir,
                memory_store=store,
            )

            response = _get(app, "/memory/status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["corpus"]["candidate_queue_available"])
        self.assertIsNotNone(body["corpus"]["candidate_queue_error_type"])
        self.assertIn(
            "candidate_queue_unavailable",
            {
                blocker["code"]
                for blocker in body["scientific_readiness"]["blockers"]
            },
        )

    def test_candidate_queue_promotes_immediately_without_mutating_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            reports_root = base / "reports"
            candidate_path = reports_root / "run" / "memory_candidate.json"
            _write_candidate(candidate_path, reusable_as_context=False)
            original_source = candidate_path.read_bytes()
            memory_dir = base / "memory"
            store = LocalJsonVectorMemoryStore(
                memory_dir,
                embedding_model=LocalHashEmbeddingModel(),
            )
            app = create_app(
                runs_dir=base / "runs",
                reports_root=reports_root,
                memory_dir=memory_dir,
                memory_store=store,
            )

            pending = _get(app, "/memory/candidates")
            promoted = _patch(
                app,
                "/memory/candidates/candidate-api-pending/decision",
                json={
                    "action": "promote",
                    "reason": "Validated reusable boundary lesson.",
                    "reviewer": "advisor",
                },
            )
            queue_after = _get(app, "/memory/candidates")
            reusable_records = _get(
                app,
                "/memory/records",
                params={"target_agent": "modeler", "reusable_only": True},
            )
            source_after = candidate_path.read_bytes()

        self.assertEqual(pending.status_code, 200)
        self.assertEqual(pending.json()["summary"]["n_pending"], 1)
        self.assertEqual(pending.json()["candidates"][0]["status"], "pending")
        self.assertEqual(
            pending.json()["candidates"][0]["data_provenance"],
            "synthetic",
        )
        self.assertEqual(promoted.status_code, 200)
        promoted_body = promoted.json()
        self.assertEqual(promoted_body["candidate"]["status"], "promoted")
        self.assertEqual(promoted_body["candidate"]["data_provenance"], "synthetic")
        self.assertEqual(promoted_body["record"]["data_provenance"], "synthetic")
        self.assertTrue(promoted_body["record"]["reusable_as_context"])
        self.assertFalse(promoted_body["record"]["exclude_from_context"])
        self.assertEqual(
            promoted_body["record"]["human_verdict"],
            "partially_correct",
        )
        self.assertIn("manual_promote", promoted_body["record"]["tags"])
        self.assertEqual(
            promoted_body["governance_event"]["reviewer"],
            "advisor",
        )
        self.assertEqual(
            promoted_body["governance_event"]["source_hash"],
            promoted_body["record"]["source_hash"],
        )
        self.assertEqual(queue_after.json()["summary"]["n_promoted"], 1)
        self.assertEqual(len(reusable_records.json()), 1)
        self.assertEqual(source_after, original_source)

    def test_candidate_exclusion_is_immediate_and_requires_a_reviewer(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            reports_root = base / "reports"
            _write_candidate(
                reports_root / "run" / "memory_candidate.json",
                reusable_as_context=False,
            )
            memory_dir = base / "memory"
            store = LocalJsonVectorMemoryStore(
                memory_dir,
                embedding_model=LocalHashEmbeddingModel(),
            )
            app = create_app(
                runs_dir=base / "runs",
                reports_root=reports_root,
                memory_dir=memory_dir,
                memory_store=store,
            )

            missing_reviewer = _patch(
                app,
                "/memory/candidates/candidate-api-pending/decision",
                json={"action": "promote", "reason": "Incomplete decision."},
            )
            excluded = _patch(
                app,
                "/memory/candidates/candidate-api-pending/decision",
                json={
                    "action": "exclude",
                    "reason": "Dataset context is incompatible.",
                    "reviewer": "advisor",
                },
            )
            unbound_restore = _patch(
                app,
                (
                    "/memory/records/"
                    "candidate-api-pending:memory:modeler/curation"
                ),
                json={
                    "action": "restore",
                    "reason": "Must use source-bound promotion.",
                    "reviewer": "advisor",
                },
            )
            reusable_records = _get(
                app,
                "/memory/records",
                params={"target_agent": "modeler", "reusable_only": True},
            )

        self.assertEqual(missing_reviewer.status_code, 422)
        self.assertEqual(excluded.status_code, 200)
        self.assertEqual(excluded.json()["candidate"]["status"], "excluded")
        self.assertTrue(excluded.json()["record"]["exclude_from_context"])
        self.assertFalse(excluded.json()["record"]["reusable_as_context"])
        self.assertEqual(unbound_restore.status_code, 400)
        self.assertIn("source-bound promote", unbound_restore.text)
        self.assertEqual(reusable_records.json(), [])

    def test_candidate_decision_uses_injected_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            reports_root = base / "reports"
            _write_candidate(
                reports_root / "run" / "memory_candidate.json",
                reusable_as_context=False,
            )
            memory_dir = base / "memory"
            store = Mock()
            store.backend_name = "configured_qdrant_store"
            store.upsert.side_effect = lambda record: record
            app = create_app(
                runs_dir=base / "runs",
                reports_root=reports_root,
                memory_dir=memory_dir,
                memory_store=store,
            )

            response = _patch(
                app,
                "/memory/candidates/candidate-api-pending/decision",
                json={
                    "action": "promote",
                    "reason": "Backend injection check.",
                    "reviewer": "test_runner",
                },
            )

        self.assertEqual(response.status_code, 200)
        store.upsert.assert_called_once()
        self.assertFalse((memory_dir / "modeler_memory.json").exists())

    def test_candidate_queue_rejects_duplicates_and_paths_outside_reports_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            reports_root = base / "reports"
            _write_candidate(reports_root / "run-a" / "memory_candidate.json")
            _write_candidate(reports_root / "run-b" / "memory_candidate.json")
            duplicate_app = create_app(
                runs_dir=base / "runs",
                reports_root=reports_root,
                memory_dir=base / "memory",
                memory_store=Mock(),
            )
            duplicate_response = _get(duplicate_app, "/memory/candidates")

            safe_root = base / "safe-reports"
            outside = base / "outside" / "memory_candidate.json"
            _write_candidate(outside)
            symlink_path = safe_root / "run" / "memory_candidate.json"
            symlink_path.parent.mkdir(parents=True)
            symlink_path.symlink_to(outside)
            unsafe_app = create_app(
                runs_dir=base / "runs-2",
                reports_root=safe_root,
                memory_dir=base / "memory-2",
                memory_store=Mock(),
            )
            unsafe_response = _get(unsafe_app, "/memory/candidates")

        self.assertEqual(duplicate_response.status_code, 409)
        self.assertIn("duplicate memory candidate_id", duplicate_response.text)
        self.assertEqual(unsafe_response.status_code, 400)
        self.assertIn("outside configured reports_root", unsafe_response.text)

    def test_memory_collections_and_records_are_queryable(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            memory_dir = base / "memory"
            store = LocalJsonVectorMemoryStore(
                memory_dir,
                embedding_model=LocalHashEmbeddingModel(),
            )
            store.upsert(
                _record(
                    "memory-modeler-001",
                    dataset="nasa_ims_bearing",
                    data_provenance="synthetic",
                )
            )
            store.upsert(
                _record(
                    "memory-structurer-001",
                    collection_name="structurer_memory",
                    target_agent="structurer",
                    dataset="cwru_bearing",
                    data_provenance="official",
                    memory_role="evidence",
                    summary="Window evidence for CWRU.",
                    content="Use stable window sizes for CWRU.",
                )
            )
            app = create_app(
                runs_dir=base / "runs",
                memory_dir=memory_dir,
                memory_store=store,
            )

            collections_response = _get(app, "/memory/collections")
            records_response = _get(
                app,
                "/memory/records",
                params={
                    "target_agent": "modeler",
                    "dataset": "nasa_ims_bearing",
                    "reusable_only": True,
                },
            )
            detail_response = _get(
                app,
                "/memory/records/memory-modeler-001",
            )

        self.assertEqual(collections_response.status_code, 200)
        collections = {
            item["collection_name"]: item
            for item in collections_response.json()
        }
        self.assertEqual(collections["modeler_memory"]["n_records"], 1)
        self.assertEqual(collections["structurer_memory"]["n_records"], 1)
        self.assertEqual(records_response.status_code, 200)
        self.assertEqual(
            [item["memory_record_id"] for item in records_response.json()],
            ["memory-modeler-001"],
        )
        self.assertEqual(records_response.json()[0]["data_provenance"], "synthetic")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["content"], "Reduce threshold carefully.")

    def test_memory_records_support_text_search_and_missing_detail_404(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            memory_dir = base / "memory"
            store = LocalJsonVectorMemoryStore(
                memory_dir,
                embedding_model=LocalHashEmbeddingModel(),
            )
            store.upsert(_record("memory-modeler-001", dataset="nasa_ims_bearing"))
            app = create_app(
                runs_dir=base / "runs",
                memory_dir=memory_dir,
                memory_store=store,
            )

            search_response = _get(
                app,
                "/memory/records",
                params={
                    "target_agent": "modeler",
                    "search_text": "threshold",
                },
            )
            empty_search_response = _get(
                app,
                "/memory/records",
                params={
                    "target_agent": "modeler",
                    "search_text": "not-present",
                },
            )
            missing_response = _get(app, "/memory/records/missing-memory")

        self.assertEqual(search_response.status_code, 200)
        self.assertEqual(len(search_response.json()), 1)
        self.assertEqual(empty_search_response.status_code, 200)
        self.assertEqual(empty_search_response.json(), [])
        self.assertEqual(missing_response.status_code, 404)

    def test_memory_record_curation_can_exclude_restore_and_delete(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            memory_dir = base / "memory"
            store = LocalJsonVectorMemoryStore(
                memory_dir,
                embedding_model=LocalHashEmbeddingModel(),
            )
            store.upsert(_record("memory-modeler-001", dataset="nasa_ims_bearing"))
            app = create_app(
                runs_dir=base / "runs",
                memory_dir=memory_dir,
                memory_store=store,
            )

            exclude_response = _patch(
                app,
                "/memory/records/memory-modeler-001/curation",
                json={
                    "action": "exclude",
                    "reason": "Benchmark excludes contaminated memory.",
                    "reviewer": "test_runner",
                },
            )
            reusable_after_exclude = _get(
                app,
                "/memory/records",
                params={"target_agent": "modeler", "reusable_only": True},
            )
            restore_response = _patch(
                app,
                "/memory/records/memory-modeler-001/curation",
                json={
                    "action": "restore",
                    "reason": "Memory accepted after review.",
                    "reviewer": "test_runner",
                },
            )
            reusable_after_restore = _get(
                app,
                "/memory/records",
                params={"target_agent": "modeler", "reusable_only": True},
            )
            delete_response = _delete(
                app,
                "/memory/records/memory-modeler-001",
                params={
                    "reason": "Remove benchmark-only memory.",
                    "reviewer": "test_runner",
                },
            )
            missing_after_delete = _get(app, "/memory/records/memory-modeler-001")
            ledger = load_memory_governance_ledger(memory_dir)
            ledger_path_exists = memory_governance_ledger_path(memory_dir).exists()

        self.assertEqual(exclude_response.status_code, 200)
        excluded = exclude_response.json()["record"]
        self.assertFalse(excluded["reusable_as_context"])
        self.assertTrue(excluded["exclude_from_context"])
        self.assertIn("manual_exclude", excluded["tags"])
        self.assertEqual(reusable_after_exclude.status_code, 200)
        self.assertEqual(reusable_after_exclude.json(), [])
        self.assertEqual(restore_response.status_code, 200)
        restored = restore_response.json()["record"]
        self.assertTrue(restored["reusable_as_context"])
        self.assertFalse(restored["exclude_from_context"])
        self.assertIn("manual_restore", restored["tags"])
        self.assertEqual(reusable_after_restore.status_code, 200)
        self.assertEqual(
            [item["memory_record_id"] for item in reusable_after_restore.json()],
            ["memory-modeler-001"],
        )
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["action"], "delete")
        self.assertEqual(
            delete_response.json()["governance_event"]["reviewer"],
            "test_runner",
        )
        self.assertEqual(missing_after_delete.status_code, 404)
        self.assertTrue(ledger_path_exists)
        self.assertEqual(ledger.overrides[0].current_action, "delete")
        self.assertEqual(
            [event.action for event in ledger.overrides[0].history],
            ["exclude", "restore", "delete"],
        )
        self.assertEqual(
            [event.reason for event in ledger.overrides[0].history],
            [
                "Benchmark excludes contaminated memory.",
                "Memory accepted after review.",
                "Remove benchmark-only memory.",
            ],
        )

    def test_memory_role_excluded_cannot_be_restored(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            memory_dir = base / "memory"
            store = LocalJsonVectorMemoryStore(
                memory_dir,
                embedding_model=LocalHashEmbeddingModel(),
            )
            store.upsert(
                _record(
                    "memory-excluded-001",
                    memory_role="excluded",
                )
            )
            app = create_app(
                runs_dir=base / "runs",
                memory_dir=memory_dir,
                memory_store=store,
            )

            response = _patch(
                app,
                "/memory/records/memory-excluded-001/curation",
                json={
                    "action": "restore",
                    "reason": "Attempt to restore an intrinsically excluded record.",
                    "reviewer": "test_runner",
                },
            )
            ledger_path_exists = memory_governance_ledger_path(memory_dir).exists()

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ledger_path_exists)


def _record(
    memory_record_id: str,
    *,
    collection_name: str = "modeler_memory",
    target_agent: str = "modeler",
    dataset: str | None = "nasa_ims_bearing",
    memory_role: str = "warning",
    summary: str = "Threshold warning for NASA IMS.",
    content: str = "Reduce threshold carefully.",
    data_provenance: str = "unknown",
) -> ReasoningMemoryRecord:
    return ReasoningMemoryRecord(
        memory_record_id=memory_record_id,
        collection_name=collection_name,
        target_agent=target_agent,
        source_type="human_review",
        source_path=f"codigo/reports/{memory_record_id}/memory_candidate.json",
        run_id=f"run-{memory_record_id}",
        decision_id=f"{memory_record_id}:decision",
        dataset=dataset,
        data_provenance=data_provenance,  # type: ignore[arg-type]
        source_agent_name=target_agent,
        outcome="supported",
        human_verdict="partially_correct",
        memory_role=memory_role,
        reusable_as_context=memory_role != "excluded",
        exclude_from_context=memory_role == "excluded",
        summary=summary,
        content=content,
        tags=[target_agent, memory_role],
    )


def _write_candidate(
    path: Path,
    *,
    reusable_as_context: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "candidate_id": "candidate-api-pending",
                "source_episode_id": "episode-api-pending",
                "target_agent": "modeler",
                "source_type": "memory_candidate",
                "run_id": "run-api-pending",
                "decision_id": "modeler-api-pending",
                "dataset": "nasa_ims_bearing",
                "data_provenance": "synthetic",
                "source_agent_name": "modeler",
                "outcome": "partially_supported",
                "human_verdict": "partially_correct",
                "memory_role": "boundary_case",
                "reusable_as_context": reusable_as_context,
                "exclude_from_context": False,
                "summary": "A moderate threshold change needs manual review.",
                "content": "Keep false-positive rate under explicit control.",
                "when_to_reuse": ["recall is low and FPR remains controlled"],
                "when_not_to_reuse": ["dataset provenance is incompatible"],
                "risk_if_misused": "May transfer an incompatible threshold.",
                "metrics": {"recall": 0.7, "false_positive_rate": 0.2},
                "tags": ["modeler", "threshold"],
            }
        ),
        encoding="utf-8",
    )


def _get(app, path: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.get(path, **kwargs)

    return asyncio.run(request())


def _patch(app, path: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.patch(path, **kwargs)

    return asyncio.run(request())


def _delete(app, path: str, **kwargs) -> httpx.Response:
    async def request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://testserver",
        ) as client:
            return await client.delete(path, **kwargs)

    return asyncio.run(request())


if __name__ == "__main__":
    unittest.main()
