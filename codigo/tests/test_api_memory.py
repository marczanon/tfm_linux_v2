import asyncio
import tempfile
import unittest
from pathlib import Path

import httpx

from codigo.app.api import create_app
from codigo.app.schemas.reasoning import ReasoningMemoryRecord
from codigo.app.services.vector_memory import (
    LocalHashEmbeddingModel,
    LocalJsonVectorMemoryStore,
)


class APIMemoryTests(unittest.TestCase):
    def test_memory_collections_and_records_are_queryable(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            memory_dir = base / "memory"
            store = LocalJsonVectorMemoryStore(
                memory_dir,
                embedding_model=LocalHashEmbeddingModel(),
            )
            store.upsert(_record("memory-modeler-001", dataset="nasa_ims_bearing"))
            store.upsert(
                _record(
                    "memory-structurer-001",
                    collection_name="structurer_memory",
                    target_agent="structurer",
                    dataset="cwru_bearing",
                    memory_role="evidence",
                    summary="Window evidence for CWRU.",
                    content="Use stable window sizes for CWRU.",
                )
            )
            app = create_app(runs_dir=base / "runs", memory_dir=memory_dir)

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
            app = create_app(runs_dir=base / "runs", memory_dir=memory_dir)

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


def _record(
    memory_record_id: str,
    *,
    collection_name: str = "modeler_memory",
    target_agent: str = "modeler",
    dataset: str = "nasa_ims_bearing",
    memory_role: str = "warning",
    summary: str = "Threshold warning for NASA IMS.",
    content: str = "Reduce threshold carefully.",
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
        source_agent_name=target_agent,
        outcome="supported",
        human_verdict="partially_correct",
        memory_role=memory_role,
        reusable_as_context=True,
        exclude_from_context=False,
        summary=summary,
        content=content,
        tags=[target_agent, memory_role],
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


if __name__ == "__main__":
    unittest.main()
