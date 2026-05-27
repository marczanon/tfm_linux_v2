import json
import tempfile
import unittest
from pathlib import Path

from codigo.app.schemas.reasoning import AgentMemoryQuery
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

    def test_indexer_can_promote_memory_usage_audits_as_warning_memory(self):
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
            self.assertEqual(len(context.items), 1)
            self.assertEqual(context.items[0].retrieval_use, "negative_warning")

    def test_indexer_adds_reusable_memory_candidates_by_default(self):
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
            record = result.indexed_records[0]
            self.assertEqual(record.source_type, "memory_candidate")
            self.assertEqual(record.memory_role, "boundary_case")
            self.assertEqual(record.collection_name, "modeler_memory")

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
            self.assertEqual(len(context.items), 1)
            self.assertEqual(context.items[0].retrieval_use, "boundary_context")


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


def _write_memory_candidate(path: Path) -> None:
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
                "reusable_as_context": True,
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
