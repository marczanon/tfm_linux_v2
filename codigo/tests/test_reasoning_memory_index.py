import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from codigo.app.schemas.reasoning import AgentMemoryQuery
from codigo.app.services.memory_registry import (
    append_memory_governance_event,
    curate_memory_record,
    decide_memory_candidate,
    delete_memory_record,
    load_memory_candidate_artifacts,
    load_memory_governance_ledger,
    list_memory_candidate_queue,
    memory_governance_ledger_path,
)
from codigo.app.services.reasoning_memory_index import index_reasoning_memory
from codigo.app.services.vector_memory import (
    LocalHashEmbeddingModel,
    LocalJsonVectorMemoryStore,
)


class ReasoningMemoryIndexTests(unittest.TestCase):
    def test_indexer_requires_human_review_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / "reports" / "nasa_ims_bearing" / "run" / "iteration"
            reports.mkdir(parents=True)
            _write_postmortem(reports / "reasoning_postmortem.json")

            result = index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=root / "memory",
                embedding_provider=LocalHashEmbeddingModel(dimension=32),
            )

            self.assertEqual(result.indexed_records, [])
            self.assertEqual(len(result.missing_reviews), 1)
            self.assertTrue((root / "memory" / "reasoning_memory_index_report.json").exists())

    def test_indexer_adds_reviewed_reusable_memory(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / "reports" / "nasa_ims_bearing" / "run" / "iteration"
            reports.mkdir(parents=True)
            _write_postmortem(reports / "reasoning_postmortem.json")
            _write_review(reports / "human_reasoning_review.json")

            result = index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=root / "memory",
                embedding_provider=LocalHashEmbeddingModel(dimension=32),
                clear_existing=True,
            )

            self.assertEqual(len(result.indexed_records), 1)
            record = result.indexed_records[0]
            self.assertEqual(record.collection_name, "modeler_memory")
            self.assertTrue(record.reusable_as_context)
            self.assertEqual(record.memory_role, "boundary_case")
            self.assertEqual(record.dataset, "nasa_ims_bearing")
            self.assertEqual(record.embedding_dimension, 32)

            store = LocalJsonVectorMemoryStore(
                root / "memory",
                embedding_model=LocalHashEmbeddingModel(dimension=32),
            )
            context = store.query(
                AgentMemoryQuery(
                    query_id="query-indexed-memory",
                    target_agent="modeler",
                    query_text="threshold recall false positive overcorrection",
                    dataset="nasa_ims_bearing",
                    min_similarity=0.01,
                )
            )
            self.assertEqual(len(context.items), 1)
            self.assertEqual(context.items[0].record.run_id, "retry-run")

    def test_indexer_keeps_memory_usage_audits_as_non_reusable_observations(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / "reports" / "nasa_ims_bearing" / "run" / "iteration"
            reports.mkdir(parents=True)
            _write_memory_usage_audit(reports / "memory_usage_audit.json")

            result = index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=root / "memory",
                embedding_provider=LocalHashEmbeddingModel(dimension=32),
                include_memory_usage_audits=True,
                clear_existing=True,
            )

            self.assertEqual(len(result.indexed_records), 1)
            self.assertEqual(len(result.indexed_memory_usage_audits), 1)
            record = result.indexed_records[0]
            self.assertEqual(record.source_type, "memory_usage_audit")
            self.assertEqual(record.target_agent, "modeler")
            self.assertEqual(record.memory_role, "warning")
            self.assertEqual(record.collection_name, "modeler_memory")
            self.assertFalse(record.reusable_as_context)
            self.assertIn("non_reusable_memory_observation", record.tags)

            store = LocalJsonVectorMemoryStore(
                root / "memory",
                embedding_model=LocalHashEmbeddingModel(dimension=32),
            )
            context = store.query(
                AgentMemoryQuery(
                    query_id="query-indexed-audit",
                    target_agent="modeler",
                    query_text="memory repeated false positive failure",
                    dataset="nasa_ims_bearing",
                    min_similarity=0.0,
                )
            )
            self.assertEqual(context.items, [])

    def test_indexer_quarantines_legacy_reusable_candidate_without_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / "reports" / "nasa_ims_bearing" / "run" / "iteration"
            reports.mkdir(parents=True)
            _write_memory_candidate(reports / "memory_candidate.json")

            result = index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=root / "memory",
                embedding_provider=LocalHashEmbeddingModel(dimension=32),
                clear_existing=True,
            )

            self.assertEqual(len(result.indexed_records), 1)
            self.assertEqual(len(result.indexed_memory_candidates), 1)
            self.assertEqual(len(result.quarantined_memory_candidates), 1)
            record = result.indexed_records[0]
            self.assertEqual(record.source_type, "memory_candidate")
            self.assertEqual(record.memory_role, "boundary_case")
            self.assertEqual(record.collection_name, "modeler_memory")
            self.assertFalse(record.reusable_as_context)
            self.assertIn("pending_manual_promotion", record.tags)

            store = LocalJsonVectorMemoryStore(
                root / "memory",
                embedding_model=LocalHashEmbeddingModel(dimension=32),
            )
            context = store.query(
                AgentMemoryQuery(
                    query_id="query-indexed-candidate",
                    target_agent="modeler",
                    query_text="moderate threshold memory warning fpr",
                    dataset="nasa_ims_bearing",
                    min_similarity=0.0,
                )
            )
            self.assertEqual(context.items, [])
            queue = list_memory_candidate_queue(root / "reports", root / "memory")
            self.assertEqual(queue.summary.n_pending, 1)
            self.assertEqual(queue.candidates[0].status, "pending")

    def test_pending_candidate_becomes_retrievable_only_after_manual_promotion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / "reports" / "nasa_ims_bearing" / "run" / "iteration"
            reports.mkdir(parents=True)
            _write_memory_candidate(
                reports / "memory_candidate.json",
                reusable_as_context=False,
            )
            memory_dir = root / "memory"
            store = _local_store(memory_dir)

            with self.assertRaisesRegex(ValueError, "source_hash"):
                append_memory_governance_event(
                    memory_dir,
                    _candidate_memory_record_id(),
                    action="promote",
                    reason="Unbound promotion must be rejected.",
                    reviewer="advisor",
                )

            pending_result = index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=memory_dir,
                memory_store=store,
                clear_existing=True,
            )
            self.assertEqual(len(pending_result.indexed_records), 1)
            self.assertFalse(pending_result.indexed_records[0].reusable_as_context)
            self.assertEqual(len(pending_result.quarantined_memory_candidates), 1)
            self.assertEqual(_query_candidate(store).items, [])

            append_memory_governance_event(
                memory_dir,
                _candidate_memory_record_id(),
                action="promote",
                reason="Advisor validated the boundary lesson.",
                reviewer="advisor",
                source_hash=load_memory_candidate_artifacts(
                    root / "reports"
                )[0].source_hash,
            )
            promoted_result = index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=memory_dir,
                memory_store=store,
                clear_existing=True,
            )

            promoted_record = promoted_result.indexed_records[0]
            self.assertTrue(promoted_record.reusable_as_context)
            self.assertFalse(promoted_record.exclude_from_context)
            self.assertEqual(promoted_record.promotion_source_hash, promoted_record.source_hash)
            self.assertEqual(promoted_record.human_verdict, "partially_correct")
            self.assertIn("manual_promote", promoted_record.tags)
            self.assertEqual(
                [item.effect for item in promoted_result.applied_governance_actions],
                ["promoted"],
            )
            self.assertEqual(len(_query_candidate(store).items), 1)

            reindexed_result = index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=memory_dir,
                memory_store=store,
                clear_existing=True,
            )
            self.assertEqual(
                reindexed_result.applied_governance_actions[0].effect,
                "promoted",
            )
            self.assertEqual(len(_query_candidate(store).items), 1)

    def test_excluded_pending_candidate_stays_out_of_retrieval_after_reindex(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / "reports" / "nasa_ims_bearing" / "run" / "iteration"
            reports.mkdir(parents=True)
            _write_memory_candidate(
                reports / "memory_candidate.json",
                reusable_as_context=False,
            )
            memory_dir = root / "memory"
            store = _local_store(memory_dir)
            append_memory_governance_event(
                memory_dir,
                _candidate_memory_record_id(),
                action="exclude",
                reason="Candidate uses incompatible evidence.",
                reviewer="advisor",
            )

            first_result = index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=memory_dir,
                memory_store=store,
                clear_existing=True,
            )
            second_result = index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=memory_dir,
                memory_store=store,
                clear_existing=True,
            )

            self.assertEqual(_query_candidate(store).items, [])
            self.assertTrue(first_result.indexed_records[0].exclude_from_context)
            self.assertFalse(first_result.indexed_records[0].reusable_as_context)
            self.assertEqual(
                second_result.applied_governance_actions[0].effect,
                "excluded",
            )

    def test_promotion_fails_closed_when_candidate_changes_after_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / "reports" / "nasa_ims_bearing" / "run" / "iteration"
            reports.mkdir(parents=True)
            candidate_path = reports / "memory_candidate.json"
            _write_memory_candidate(candidate_path, reusable_as_context=False)
            memory_dir = root / "memory"
            store = _local_store(memory_dir)
            reviewed_hash = load_memory_candidate_artifacts(
                root / "reports"
            )[0].source_hash
            append_memory_governance_event(
                memory_dir,
                _candidate_memory_record_id(),
                action="promote",
                reason="Reviewed exact candidate contents.",
                reviewer="advisor",
                source_hash=reviewed_hash,
            )
            index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=memory_dir,
                memory_store=store,
                clear_existing=True,
            )
            self.assertEqual(len(_query_candidate(store).items), 1)

            mutated = json.loads(candidate_path.read_text(encoding="utf-8"))
            mutated["content"] = "Changed lesson after the manual review."
            candidate_path.write_text(json.dumps(mutated), encoding="utf-8")
            result = index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=memory_dir,
                memory_store=store,
                clear_existing=False,
            )

            self.assertEqual(_query_candidate(store).items, [])
            stored = {
                record.memory_record_id: record for record in store.list_records()
            }[_candidate_memory_record_id()]
            self.assertFalse(stored.reusable_as_context)
            self.assertTrue(stored.exclude_from_context)
            self.assertIn("manual_promote_source_hash_mismatch", stored.tags)
            self.assertEqual(
                result.applied_governance_actions[0].effect,
                "source_hash_mismatch",
            )
            queue = list_memory_candidate_queue(root / "reports", memory_dir)
            self.assertEqual(queue.summary.n_stale_promotions, 1)
            self.assertEqual(queue.candidates[0].status, "stale_promotion")
            self.assertNotEqual(
                reviewed_hash,
                load_memory_candidate_artifacts(root / "reports")[0].source_hash,
            )

    def test_indexer_reuses_injected_store_with_incremental_upsert_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / "reports" / "nasa_ims_bearing" / "run" / "iteration"
            reports.mkdir(parents=True)
            _write_memory_candidate(reports / "memory_candidate.json")
            store = Mock()
            store.backend_name = "configured_qdrant_store"
            store.upsert.side_effect = lambda record: record

            result = index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=root / "memory",
                memory_store=store,
            )

            store.upsert.assert_called_once()
            store.rebuild.assert_not_called()
            self.assertEqual(result.memory_backend, "configured_qdrant_store")
            self.assertFalse(result.destructive_rebuild)
            self.assertFalse((root / "memory" / "modeler_memory.json").exists())
            self.assertTrue(
                (root / "memory" / "reasoning_memory_index_report.json").exists()
            )

    def test_indexer_only_rebuilds_destructively_when_explicitly_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = root / "reports" / "nasa_ims_bearing" / "run" / "iteration"
            reports.mkdir(parents=True)
            _write_memory_candidate(reports / "memory_candidate.json")
            store = Mock()
            store.backend_name = "configured_qdrant_store"
            store.rebuild.side_effect = lambda records, **_: records

            result = index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=root / "memory",
                memory_store=store,
                clear_existing=True,
            )

            store.rebuild.assert_called_once()
            _, kwargs = store.rebuild.call_args
            self.assertEqual(kwargs, {"clear_existing": True})
            store.upsert.assert_not_called()
            self.assertTrue(result.destructive_rebuild)

    def test_manual_exclude_survives_reindex_and_stays_out_of_retrieval(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            reports = _prepare_memory_candidate(root)
            memory_dir = root / "memory"
            store = _local_store(memory_dir)
            index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=memory_dir,
                memory_store=store,
                clear_existing=True,
            )
            record_id = _candidate_memory_record_id()

            curate_memory_record(
                memory_dir,
                record_id,
                action="exclude",
                reason="Contaminated benchmark evidence.",
                reviewer="advisor",
                memory_store=store,
            )
            result = index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=memory_dir,
                memory_store=store,
                clear_existing=True,
            )

            stored = {record.memory_record_id: record for record in store.list_records()}
            self.assertIn(record_id, stored)
            self.assertTrue(stored[record_id].exclude_from_context)
            self.assertFalse(stored[record_id].reusable_as_context)
            self.assertEqual(_query_candidate(store).items, [])
            self.assertTrue(memory_governance_ledger_path(memory_dir).exists())
            self.assertEqual(result.governance_overrides_loaded, 1)
            self.assertEqual(
                [item.effect for item in result.applied_governance_actions],
                ["excluded"],
            )

    def test_source_bound_promotion_survives_reindex_after_exclusion(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_memory_candidate(root)
            memory_dir = root / "memory"
            store = _local_store(memory_dir)
            index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=memory_dir,
                memory_store=store,
                clear_existing=True,
            )
            record_id = _candidate_memory_record_id()
            curate_memory_record(
                memory_dir,
                record_id,
                action="exclude",
                reason="Hold until a second review.",
                reviewer="advisor",
                memory_store=store,
            )
            decide_memory_candidate(
                root / "reports",
                memory_dir,
                "candidate-modeler-threshold-095",
                action="promote",
                reason="Second review accepted the evidence.",
                reviewer="advisor_2",
                memory_store=store,
            )

            result = index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=memory_dir,
                memory_store=store,
                clear_existing=True,
            )

            retrieved = _query_candidate(store)
            self.assertEqual(
                [item.record.memory_record_id for item in retrieved.items],
                [record_id],
            )
            ledger = load_memory_governance_ledger(memory_dir)
            self.assertEqual(ledger.overrides[0].current_action, "promote")
            self.assertEqual(len(ledger.overrides[0].history), 2)
            self.assertEqual(
                [event.reviewer for event in ledger.overrides[0].history],
                ["advisor", "advisor_2"],
            )
            self.assertEqual(
                [item.effect for item in result.applied_governance_actions],
                ["promoted"],
            )

    def test_manual_delete_tombstone_prevents_resurrection_on_reindex(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_memory_candidate(root)
            memory_dir = root / "memory"
            store = _local_store(memory_dir)
            index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=memory_dir,
                memory_store=store,
                clear_existing=True,
            )
            record_id = _candidate_memory_record_id()
            delete_memory_record(
                memory_dir,
                record_id,
                reason="Superseded and unsafe memory.",
                reviewer="advisor",
                memory_store=store,
            )

            result = index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=memory_dir,
                memory_store=store,
                clear_existing=True,
            )

            self.assertNotIn(
                record_id,
                {record.memory_record_id for record in store.list_records()},
            )
            self.assertEqual(_query_candidate(store).items, [])
            self.assertEqual(result.active_tombstones, [record_id])
            self.assertEqual(
                [item.effect for item in result.applied_governance_actions],
                ["tombstoned"],
            )

    def test_governance_overlay_is_applied_with_an_injected_backend(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _prepare_memory_candidate(root)
            memory_dir = root / "memory"
            record_id = _candidate_memory_record_id()
            append_memory_governance_event(
                memory_dir,
                record_id,
                action="exclude",
                reason="Cross-backend governance check.",
                reviewer="test_runner",
            )
            store = Mock()
            store.backend_name = "configured_qdrant_store"
            store.upsert.side_effect = lambda record: record

            result = index_reasoning_memory(
                reports_root=root / "reports",
                memory_dir=memory_dir,
                memory_store=store,
            )

            store.upsert.assert_called_once()
            governed_record = store.upsert.call_args.args[0]
            self.assertEqual(governed_record.memory_record_id, record_id)
            self.assertTrue(governed_record.exclude_from_context)
            self.assertFalse(governed_record.reusable_as_context)
            self.assertEqual(result.memory_backend, "configured_qdrant_store")
            self.assertEqual(result.applied_governance_actions[0].effect, "excluded")
            self.assertFalse((memory_dir / "modeler_memory.json").exists())


def _write_postmortem(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "postmortem_id": "postmortem-retry-001",
                "run_id": "retry-run",
                "source_run_id": "base-run",
                "agent_name": "modeler",
                "decision_id": "modeler-retry-001",
                "attempt_number": 2,
                "max_attempts": 2,
                "hypothesis": "Lowering threshold should recover false negatives.",
                "action_taken": "threshold_quantile=0.5",
                "expected_effect": "Increase recall.",
                "before_metrics": {"recall": 0.65, "false_positive_rate": 0.21},
                "after_metrics": {"recall": 1.0, "false_positive_rate": 1.0},
                "metric_deltas": [],
                "outcome": "overcorrected",
                "automatic_critique": "Recall improved but FPR became unsafe.",
                "reusable_lessons": [
                    "do_not_optimize_recall_without_fpr_control"
                ],
                "requires_human_review": True,
                "human_review_status": "pending_human_review",
            }
        ),
        encoding="utf-8",
    )


def _prepare_memory_candidate(root: Path) -> Path:
    reports = root / "reports" / "nasa_ims_bearing" / "run" / "iteration"
    reports.mkdir(parents=True)
    _write_memory_candidate(reports / "memory_candidate.json")
    return reports


def _local_store(memory_dir: Path) -> LocalJsonVectorMemoryStore:
    return LocalJsonVectorMemoryStore(
        memory_dir,
        embedding_model=LocalHashEmbeddingModel(dimension=32),
    )


def _candidate_memory_record_id() -> str:
    return "candidate-modeler-threshold-095:memory:modeler"


def _query_candidate(store: LocalJsonVectorMemoryStore):
    return store.query(
        AgentMemoryQuery(
            query_id="query-governed-candidate",
            target_agent="modeler",
            query_text="moderate threshold memory warning fpr",
            dataset="nasa_ims_bearing",
            min_similarity=0.0,
        )
    )


def _write_review(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "review_id": "review-retry-001",
                "postmortem_id": "postmortem-retry-001",
                "run_id": "retry-run",
                "decision_id": "modeler-retry-001",
                "reviewer": "advisor",
                "verdict": "partially_correct",
                "rationale": "Correct direction but unsafe magnitude.",
                "reusable_as_context": True,
                "exclude_from_context": False,
                "tags": ["threshold", "overcorrection"],
            }
        ),
        encoding="utf-8",
    )


def _write_memory_usage_audit(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "audit_id": "memory-audit-001",
                "run_id": "retry-run",
                "decision_id": "modeler-retry-001",
                "memory_context_id": "ctx-001",
                "used_memory_context": True,
                "memory_usage_summary": (
                    "The agent cited a boundary warning but repeated the failure."
                ),
                "retrieved_memory_record_ids": [
                    "postmortem-retry-02:memory:modeler"
                ],
                "cited_memory_record_ids": [
                    "postmortem-retry-02:memory:modeler"
                ],
                "uncited_retrieved_record_ids": [],
                "cited_without_retrieval": [],
                "before_metrics": {"recall": 0.65, "false_positive_rate": 0.21},
                "after_metrics": {"recall": 1.0, "false_positive_rate": 1.0},
                "outcome": "memory_repeated_boundary_failure",
                "summary": (
                    "The retrieved memory was used rhetorically, but the "
                    "configuration reproduced the high false positive rate."
                ),
                "items": [],
            }
        ),
        encoding="utf-8",
    )


def _write_memory_candidate(
    path: Path,
    *,
    reusable_as_context: bool = True,
) -> None:
    path.write_text(
        json.dumps(
            {
                "candidate_id": "candidate-modeler-threshold-095",
                "source_episode_id": "episode-modeler-threshold-095",
                "target_agent": "modeler",
                "source_type": "memory_candidate",
                "run_id": "memory-fed-run",
                "decision_id": "modeler-retry-001",
                "dataset": "nasa_ims_bearing",
                "source_agent_name": "modeler",
                "outcome": "partially_supported",
                "human_verdict": "partially_correct",
                "memory_role": "boundary_case",
                "reusable_as_context": reusable_as_context,
                "exclude_from_context": False,
                "summary": (
                    "A moderate threshold move improved recall but raised FPR."
                ),
                "content": (
                    "The modeler used memory warnings to avoid threshold 0.50 "
                    "and selected threshold_quantile=0.95 instead."
                ),
                "when_to_reuse": [
                    "low recall with warning against radical threshold shifts"
                ],
                "when_not_to_reuse": [
                    "FPR is already above the evaluator limit"
                ],
                "risk_if_misused": (
                    "May keep tuning threshold when model family comparison is needed."
                ),
                "metrics": {"recall": 0.6571, "false_positive_rate": 0.2143},
                "tags": ["threshold_quantile", "memory_warning", "modeler"],
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
