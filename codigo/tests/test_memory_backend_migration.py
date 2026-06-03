import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codigo.app.schemas.reasoning import AgentMemoryQuery, ReasoningMemoryRecord
from codigo.app.services.memory_backend_migration import (
    build_memory_migration_verification_queries,
    migrate_local_json_memory_to_qdrant,
    migrate_memory_records_between_stores,
)
from codigo.app.services.vector_memory import (
    LocalHashEmbeddingModel,
    LocalJsonVectorMemoryStore,
)


class MemoryBackendMigrationTests(unittest.TestCase):
    def test_migrates_records_between_stores_and_compares_retrieval(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            provider = LocalHashEmbeddingModel(dimension=32)
            source = LocalJsonVectorMemoryStore(base / "source", embedding_model=provider)
            target = LocalJsonVectorMemoryStore(base / "target", embedding_model=provider)
            source.rebuild([_modeler_record(), _shared_record()], clear_existing=True)

            report = migrate_memory_records_between_stores(
                source_store=source,
                target_store=target,
                clear_existing=True,
                verification_queries=[
                    AgentMemoryQuery(
                        query_id="migration-query-modeler",
                        target_agent="modeler",
                        query_text="sustained alert lead time threshold",
                        dataset="nasa_ims_bearing",
                        top_k=5,
                        min_similarity=0.0,
                    )
                ],
                source_memory_dir=base / "source",
                target_host="local-test",
            )

            self.assertEqual(report.migrated_record_count, 2)
            self.assertEqual(
                report.collection_counts,
                {"modeler_memory": 1, "shared_methodology_memory": 1},
            )
            self.assertIsNotNone(report.comparison)
            self.assertEqual(report.comparison.query_count, 1)
            self.assertEqual(report.comparison.exact_match_count, 1)
            self.assertEqual(report.comparison.average_overlap_ratio, 1.0)

    def test_wrapper_writes_json_to_qdrant_migration_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            provider = LocalHashEmbeddingModel(dimension=32)
            source = LocalJsonVectorMemoryStore(base / "source", embedding_model=provider)
            source.rebuild([_modeler_record()], clear_existing=True)

            class FakeQdrantStore(LocalJsonVectorMemoryStore):
                backend_name = "qdrant_vector_memory_store"

                def __init__(
                    self,
                    *,
                    host: str,
                    api_key: str | None,
                    embedding_model: LocalHashEmbeddingModel,
                    timeout_seconds: float,
                    distance: str,
                ) -> None:
                    self.host = host
                    self.api_key = api_key
                    self.timeout_seconds = timeout_seconds
                    self.distance = distance
                    super().__init__(base / "qdrant", embedding_model=embedding_model)

            with patch(
                "codigo.app.services.memory_backend_migration.QdrantVectorMemoryStore",
                FakeQdrantStore,
            ):
                artifacts = migrate_local_json_memory_to_qdrant(
                    memory_dir=base / "source",
                    qdrant_host="http://qdrant.test",
                    embedding_provider=provider,
                    output_dir=base / "migration-report",
                )

            self.assertTrue(Path(artifacts.migration_path).exists())
            self.assertTrue(Path(artifacts.report_path).exists())
            self.assertEqual(artifacts.report.target_backend, "qdrant_vector_memory_store")
            self.assertEqual(artifacts.report.target_host, "http://qdrant.test")
            self.assertEqual(artifacts.report.migrated_record_count, 1)

    def test_builds_default_verification_queries_per_agent_and_dataset(self):
        queries = build_memory_migration_verification_queries(
            [_modeler_record(), _shared_record()],
            max_queries=8,
        )

        self.assertEqual(
            [(query.target_agent, query.dataset) for query in queries],
            [("modeler", "nasa_ims_bearing"), ("shared_methodology", None)],
        )
        self.assertEqual(queries[0].top_k, 5)


def _modeler_record() -> ReasoningMemoryRecord:
    return ReasoningMemoryRecord(
        memory_record_id="memory-modeler-run-to-failure-001",
        collection_name="modeler_memory",
        target_agent="modeler",
        source_type="decision_episode",
        run_id="run-memory-modeler",
        decision_id="run-memory-modeler:modeler:001",
        dataset="nasa_ims_bearing",
        source_agent_name="modeler",
        outcome="partially_supported",
        human_verdict="partially_correct",
        memory_role="boundary_case",
        reusable_as_context=True,
        summary="Use sustained alerts before declaring degradation.",
        content=(
            "For run-to-failure monitoring, isolated spikes should not drive "
            "the alert policy. The modeler should compare lead time and false "
            "alarms after requiring sustained warning windows."
        ),
        tags=[
            "run_to_failure_degradation",
            "sustained_alert",
            "lead_time",
            "false_alarm_rate",
        ],
    )


def _shared_record() -> ReasoningMemoryRecord:
    return ReasoningMemoryRecord(
        memory_record_id="memory-shared-methodology-rtf-001",
        collection_name="shared_methodology_memory",
        target_agent="shared_methodology",
        source_type="methodology_note",
        dataset=None,
        source_agent_name=None,
        outcome="supported",
        human_verdict="correct",
        memory_role="methodology",
        reusable_as_context=True,
        summary="F1 is auxiliary in run-to-failure degradation.",
        content=(
            "Operational validation should prioritize detection before failure, "
            "lead time, nominal false alarms and score trend. F1 can be reported "
            "as an auxiliary proxy metric."
        ),
        tags=["methodology", "run_to_failure_degradation", "f1_auxiliary"],
    )


if __name__ == "__main__":
    unittest.main()
