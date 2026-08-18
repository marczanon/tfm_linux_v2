import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codigo.app.schemas.reasoning import (
    AgentMemoryQuery,
    AgentReasoningPostmortem,
    DecisionEpisode,
    DecisionOption,
    HumanReasoningReview,
    MemoryUsageAudit,
    ReasoningMemoryRecord,
)
from codigo.app.services.vector_memory import (
    DEFAULT_OLLAMA_EMBEDDING_MODEL,
    DEFAULT_QDRANT_HOST,
    QDRANT_MEMORY_PAYLOAD_INDEXES,
    LocalHashEmbeddingModel,
    LocalJsonVectorMemoryStore,
    OllamaEmbeddingProvider,
    QdrantMemoryError,
    QdrantVectorMemoryStore,
    VectorMemoryConfigError,
    VectorMemoryStore,
    get_default_vector_memory_store,
    collection_for_agent,
    get_default_embedding_provider,
    memory_candidate_from_decision_episode,
    memory_record_from_candidate,
    memory_record_from_memory_usage_audit,
    memory_record_from_postmortem,
)


class VectorMemoryStoreTests(unittest.TestCase):
    def test_collection_for_agent_uses_canonical_names(self):
        self.assertEqual(collection_for_agent("modeler"), "modeler_memory")
        self.assertEqual(
            collection_for_agent("shared_methodology"),
            "shared_methodology_memory",
        )

    def test_local_json_store_implements_vector_memory_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalJsonVectorMemoryStore(tmp)

            self.assertIsInstance(store, VectorMemoryStore)

    def test_qdrant_store_implements_vector_memory_protocol(self):
        store = QdrantVectorMemoryStore(
            host="http://qdrant.test",
            embedding_model=LocalHashEmbeddingModel(dimension=16),
        )

        self.assertIsInstance(store, VectorMemoryStore)

    def test_default_embedding_provider_uses_qwen3_embedding_06b(self):
        with patch.dict(os.environ, {}, clear=True):
            provider = get_default_embedding_provider()

        self.assertIsInstance(provider, OllamaEmbeddingProvider)
        self.assertEqual(provider.model, DEFAULT_OLLAMA_EMBEDDING_MODEL)
        self.assertEqual(provider.identifier, "ollama:qwen3-embedding:0.6b")

    def test_local_hash_provider_can_be_selected_for_tests(self):
        with patch.dict(
            os.environ,
            {
                "TFM_EMBEDDING_PROVIDER": "local_hash",
                "TFM_EMBEDDING_DIMENSION": "32",
            },
            clear=True,
        ):
            provider = get_default_embedding_provider()

        self.assertIsInstance(provider, LocalHashEmbeddingModel)
        self.assertEqual(len(provider.embed("threshold recall")), 32)

    def test_default_vector_memory_store_uses_json_backend_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.dict(
                os.environ,
                {"TFM_EMBEDDING_PROVIDER": "local_hash"},
                clear=True,
            ):
                store = get_default_vector_memory_store(tmp)

        self.assertIsInstance(store, LocalJsonVectorMemoryStore)

    def test_default_vector_memory_store_can_select_qdrant_backend(self):
        with patch.dict(
            os.environ,
            {
                "TFM_MEMORY_BACKEND": "qdrant",
                "TFM_EMBEDDING_PROVIDER": "local_hash",
                "TFM_EMBEDDING_DIMENSION": "24",
                "TFM_QDRANT_HOST": "http://qdrant.test",
                "TFM_QDRANT_TIMEOUT_SECONDS": "7",
            },
            clear=True,
        ):
            store = get_default_vector_memory_store()

        self.assertIsInstance(store, QdrantVectorMemoryStore)
        self.assertEqual(store.host, "http://qdrant.test")
        self.assertEqual(store.timeout_seconds, 7.0)
        self.assertEqual(store.embedding_model.identifier, "local_hash_embedding:v1")
        self.assertEqual(DEFAULT_QDRANT_HOST, "http://127.0.0.1:6333")

    def test_ollama_embedding_provider_parses_api_embed_response(self):
        provider = OllamaEmbeddingProvider(
            model="qwen3-embedding:0.6b",
            host="http://ollama.test",
            timeout_seconds=3,
        )

        with patch(
            "codigo.app.services.vector_memory.urllib.request.urlopen",
            return_value=_FakeHTTPResponse({"embeddings": [[0.1, 0.2, 0.3]]}),
        ) as urlopen:
            vector = provider.embed("texto tecnico de prueba")

        self.assertEqual(vector, [0.1, 0.2, 0.3])
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, "http://ollama.test/api/embed")
        self.assertEqual(provider.model_name, "qwen3-embedding")
        self.assertEqual(provider.version, "0.6b")

    def test_qdrant_store_upsert_sends_record_payload(self):
        store = QdrantVectorMemoryStore(
            host="http://qdrant.test",
            embedding_model=LocalHashEmbeddingModel(dimension=16),
        )

        with patch(
            "codigo.app.services.vector_memory.urllib.request.urlopen",
            side_effect=[
                _FakeHTTPResponse(_qdrant_collection_info_payload()),
                _FakeHTTPResponse({"result": {"operation_id": 1}}),
            ],
        ) as urlopen:
            stored = store.upsert(_overcorrection_record())

        self.assertEqual(stored.embedding_model, "local_hash_embedding")
        self.assertEqual(stored.embedding_dimension, 16)
        self.assertEqual(stored.vector_id, "modeler_memory:memory-overcorrection-001")
        requests = [call.args[0] for call in urlopen.call_args_list]
        self.assertEqual(requests[0].full_url, "http://qdrant.test/collections/modeler_memory")
        self.assertIn(
            "/collections/modeler_memory/points?wait=true",
            requests[1].full_url,
        )
        body = json.loads(requests[1].data.decode("utf-8"))
        point = body["points"][0]
        self.assertEqual(
            point["payload"]["record"]["memory_record_id"],
            "memory-overcorrection-001",
        )
        self.assertEqual(point["payload"]["data_provenance"], "unknown")
        self.assertEqual(len(point["vector"]), 16)

    def test_qdrant_rejects_incompatible_collection_dimension_before_upsert(self):
        store = QdrantVectorMemoryStore(
            host="http://qdrant.test",
            embedding_model=LocalHashEmbeddingModel(dimension=16),
        )
        with patch.object(
            store,
            "_request_json",
            return_value=_qdrant_collection_info_payload(vector_size=32),
        ) as request_json:
            with self.assertRaisesRegex(
                VectorMemoryConfigError,
                "uses dimension 32",
            ):
                store.upsert(_overcorrection_record())

        self.assertEqual(request_json.call_count, 1)

    def test_qdrant_rejects_incompatible_collection_dimension_before_query(self):
        store = QdrantVectorMemoryStore(
            host="http://qdrant.test",
            embedding_model=LocalHashEmbeddingModel(dimension=16),
        )
        with patch.object(
            store,
            "_request_json",
            return_value=_qdrant_collection_info_payload(vector_size=32),
        ) as request_json:
            with self.assertRaisesRegex(
                VectorMemoryConfigError,
                "uses dimension 32",
            ):
                store.query(
                    AgentMemoryQuery(
                        query_id="query-incompatible-qdrant",
                        target_agent="modeler",
                        query_text="threshold",
                    )
                )

        self.assertEqual(request_json.call_count, 1)

    def test_qdrant_store_creates_payload_indexes_once_for_a_new_collection(self):
        store = QdrantVectorMemoryStore(
            host="http://qdrant.test",
            embedding_model=LocalHashEmbeddingModel(dimension=16),
        )
        collection_exists = False
        indexed_fields: dict[str, str] = {}

        def fake_request(
            method: str,
            path: str,
            payload: dict[str, object] | None = None,
        ) -> dict[str, object]:
            nonlocal collection_exists
            if method == "GET" and path == "/collections/modeler_memory":
                if not collection_exists:
                    raise QdrantMemoryError("not found", status_code=404)
                return _qdrant_collection_info_payload(indexed_fields)
            if method == "PUT" and path == "/collections/modeler_memory":
                collection_exists = True
                return {"result": True}
            if method == "PUT" and path.endswith("/index?wait=true"):
                assert payload is not None
                field_name = str(payload["field_name"])
                indexed_fields[field_name] = str(payload["field_schema"])
                return {"result": {"operation_id": len(indexed_fields)}}
            if method == "PUT" and path.endswith("/points?wait=true"):
                return {"result": {"operation_id": 100}}
            self.fail(f"unexpected Qdrant request: {method} {path}")

        with patch.object(
            store,
            "_request_json",
            side_effect=fake_request,
        ) as request_json:
            store.upsert(_overcorrection_record())
            store.upsert(_overcorrection_record())

        calls = request_json.call_args_list
        collection_create_calls = [
            call
            for call in calls
            if call.args[:2] == ("PUT", "/collections/modeler_memory")
        ]
        index_calls = [
            call
            for call in calls
            if call.args[0] == "PUT" and call.args[1].endswith("/index?wait=true")
        ]
        point_calls = [
            call
            for call in calls
            if call.args[0] == "PUT" and call.args[1].endswith("/points?wait=true")
        ]

        self.assertEqual(len(collection_create_calls), 1)
        self.assertEqual(
            [call.args[2]["field_name"] for call in index_calls],
            [field_name for field_name, _ in QDRANT_MEMORY_PAYLOAD_INDEXES],
        )
        self.assertEqual(indexed_fields, dict(QDRANT_MEMORY_PAYLOAD_INDEXES))
        self.assertEqual(len(point_calls), 2)

    def test_qdrant_store_query_merges_agent_and_shared_collections(self):
        store = QdrantVectorMemoryStore(
            host="http://qdrant.test",
            embedding_model=LocalHashEmbeddingModel(dimension=16),
        )
        stored = _overcorrection_record().model_copy(
            update={
                "embedding_model": "local_hash_embedding",
                "embedding_version": "v1",
                "embedding_dimension": 16,
                "vector_id": "modeler_memory:memory-overcorrection-001",
            }
        )
        shared = _shared_methodology_record().model_copy(
            update={
                "embedding_model": "local_hash_embedding",
                "embedding_version": "v1",
                "embedding_dimension": 16,
                "vector_id": "shared_methodology_memory:memory-shared-methodology-001",
            }
        )

        with patch(
            "codigo.app.services.vector_memory.urllib.request.urlopen",
            side_effect=[
                _FakeHTTPResponse(_qdrant_collection_info_payload()),
                _FakeHTTPResponse(
                    {
                        "result": [
                            {
                                "id": "point-a",
                                "score": 0.87,
                                "payload": {"record": stored.model_dump(mode="json")},
                            }
                        ]
                    }
                ),
                _FakeHTTPResponse(_qdrant_collection_info_payload()),
                _FakeHTTPResponse(
                    {
                        "result": [
                            {
                                "id": "point-b",
                                "score": 0.74,
                                "payload": {"record": shared.model_dump(mode="json")},
                            }
                        ]
                    }
                ),
            ],
        ) as urlopen:
            context = store.query(
                AgentMemoryQuery(
                    query_id="query-qdrant",
                    target_agent="modeler",
                    query_text="threshold tradeoff methodology",
                    dataset="nasa_ims_bearing",
                    min_similarity=0.0,
                    top_k=3,
                )
            )

        self.assertEqual(context.retrieval_backend, "qdrant_vector_memory_store")
        self.assertEqual(context.embedding_model, "local_hash_embedding:v1")
        self.assertEqual(
            [item.record.memory_record_id for item in context.items],
            ["memory-overcorrection-001", "memory-shared-methodology-001"],
        )
        requests = [call.args[0] for call in urlopen.call_args_list]
        query_requests = [
            request for request in requests if "/points/query" in request.full_url
        ]
        self.assertIn(
            "/collections/modeler_memory/points/query",
            query_requests[0].full_url,
        )
        self.assertIn(
            "/collections/shared_methodology_memory/points/query",
            query_requests[1].full_url,
        )
        query_bodies = [
            json.loads(request.data.decode("utf-8")) for request in query_requests
        ]
        self.assertEqual(query_bodies[0]["filter"], query_bodies[1]["filter"])
        query_filter = query_bodies[0]["filter"]
        keyed_conditions = {
            condition["key"]: condition
            for condition in query_filter["must"]
            if "key" in condition
        }
        self.assertEqual(
            keyed_conditions["target_agent"]["match"]["any"],
            ["modeler", "shared_methodology"],
        )
        self.assertEqual(
            keyed_conditions["memory_role"]["match"]["any"],
            [
                "boundary_case",
                "evidence",
                "methodology",
                "negative_example",
                "positive_example",
                "warning",
            ],
        )
        self.assertEqual(
            keyed_conditions["reusable_as_context"]["match"],
            {"value": True},
        )
        self.assertEqual(
            keyed_conditions["exclude_from_context"]["match"],
            {"value": False},
        )
        self.assertEqual(
            keyed_conditions["record.embedding_model"]["match"],
            {"value": "local_hash_embedding"},
        )
        self.assertEqual(
            keyed_conditions["record.embedding_version"]["match"],
            {"value": "v1"},
        )
        dataset_condition = next(
            condition
            for condition in query_filter["must"]
            if condition.get("should")
            and condition["should"][0].get("key") == "dataset"
        )
        self.assertEqual(
            dataset_condition["should"],
            [
                {
                    "key": "dataset",
                    "match": {"value": "nasa_ims_bearing"},
                },
                {"is_null": {"key": "dataset"}},
            ],
        )
        provenance_condition = next(
            condition
            for condition in query_filter["must"]
            if condition.get("should")
            and condition["should"][0].get("must")
        )
        self.assertIn(
            {"is_empty": {"key": "data_provenance"}},
            provenance_condition["should"][0]["must"][1]["should"][0]["should"],
        )
        governance_condition = next(
            condition
            for condition in query_filter["must"]
            if condition.get("must_not")
            and condition["must_not"][0].get("key") == "source_type"
        )
        self.assertEqual(
            governance_condition["must_not"],
            [
                {
                    "key": "source_type",
                    "match": {"value": "memory_usage_audit"},
                }
            ],
        )
        self.assertIn(
            {"is_empty": {"key": "promotion_source_hash"}},
            governance_condition["should"][1]["must_not"],
        )
        self.assertEqual(
            query_filter["must_not"],
            [
                {
                    "key": "human_verdict",
                    "match": {"any": ["unsafe"]},
                }
            ],
        )

    def test_qdrant_store_legacy_search_preserves_payload_filter(self):
        store = QdrantVectorMemoryStore(
            host="http://qdrant.test",
            embedding_model=LocalHashEmbeddingModel(dimension=16),
        )
        stored = _overcorrection_record().model_copy(
            update={
                "embedding_model": "local_hash_embedding",
                "embedding_version": "v1",
                "embedding_dimension": 16,
                "vector_id": "modeler_memory:memory-overcorrection-001",
            }
        )
        query = AgentMemoryQuery(
            query_id="query-qdrant-legacy",
            target_agent="modeler",
            query_text="threshold tradeoff",
            dataset="nasa_ims_bearing",
        )

        with patch.object(
            store,
            "_request_json",
            side_effect=[
                _qdrant_collection_info_payload(),
                QdrantMemoryError("query endpoint unavailable", status_code=405),
                {
                    "result": [
                        {
                            "id": "point-a",
                            "score": 0.87,
                            "payload": {"record": stored.model_dump(mode="json")},
                        }
                    ]
                },
                QdrantMemoryError("collection not found", status_code=404),
            ],
        ) as request_json:
            context = store.query(query)

        calls = request_json.call_args_list
        query_call = next(call for call in calls if call.args[1].endswith("/points/query"))
        legacy_call = next(call for call in calls if call.args[1].endswith("/points/search"))
        query_payload = query_call.args[2]
        legacy_payload = legacy_call.args[2]
        self.assertIn("query", query_payload)
        self.assertNotIn("vector", query_payload)
        self.assertNotIn("query", legacy_payload)
        self.assertIn("vector", legacy_payload)
        self.assertEqual(legacy_payload["filter"], query_payload["filter"])
        self.assertEqual(
            [item.record.memory_record_id for item in context.items],
            ["memory-overcorrection-001"],
        )

    def test_qdrant_store_keeps_local_filter_as_defensive_validation(self):
        store = QdrantVectorMemoryStore(
            host="http://qdrant.test",
            embedding_model=LocalHashEmbeddingModel(dimension=16),
        )
        unsafe = _unsafe_warning_record()

        with patch(
            "codigo.app.services.vector_memory.urllib.request.urlopen",
            side_effect=[
                _FakeHTTPResponse(_qdrant_collection_info_payload()),
                _FakeHTTPResponse(
                    {
                        "result": [
                            {
                                "id": "point-unsafe",
                                "score": 0.99,
                                "payload": {"record": unsafe.model_dump(mode="json")},
                            }
                        ]
                    }
                ),
                _FakeHTTPResponse(_qdrant_collection_info_payload()),
                _FakeHTTPResponse({"result": []}),
            ],
        ):
            context = store.query(
                AgentMemoryQuery(
                    query_id="query-qdrant-defensive-filter",
                    target_agent="modeler",
                    query_text="unsafe threshold",
                )
            )

        self.assertEqual(context.items, [])

    def test_qdrant_defensive_filter_rejects_opposite_provenance(self):
        store = QdrantVectorMemoryStore(
            host="http://qdrant.test",
            embedding_model=LocalHashEmbeddingModel(dimension=16),
        )
        official = _overcorrection_record().model_copy(
            update={
                "data_provenance": "official",
                "embedding_model": "local_hash_embedding",
                "embedding_version": "v1",
                "embedding_dimension": 16,
                "vector_id": "modeler_memory:memory-overcorrection-001",
            }
        )

        with patch.object(
            store,
            "_request_json",
            side_effect=[
                _qdrant_collection_info_payload(),
                {
                    "result": [
                        {
                            "id": "point-official",
                            "score": 0.99,
                            "payload": {"record": official.model_dump(mode="json")},
                        }
                    ]
                },
                _qdrant_collection_info_payload(),
                {"result": []},
            ],
        ) as request_json:
            context = store.query(
                AgentMemoryQuery(
                    query_id="query-synthetic-defensive-filter",
                    target_agent="modeler",
                    query_text="threshold provenance",
                    dataset="nasa_ims_bearing",
                    data_provenance="synthetic",
                )
            )

        self.assertEqual(context.items, [])
        query_call = next(
            call
            for call in request_json.call_args_list
            if call.args[1].endswith("/points/query")
        )
        provenance_scope = next(
            condition
            for condition in query_call.args[2]["filter"]["must"]
            if condition.get("should")
            and condition["should"][0].get("must")
        )
        specific_allowed = provenance_scope["should"][0]["must"][1]["should"]
        self.assertIn(
            {"key": "data_provenance", "match": {"value": "synthetic"}},
            specific_allowed,
        )
        self.assertNotIn(
            {"key": "data_provenance", "match": {"value": "official"}},
            specific_allowed,
        )

    def test_qdrant_store_list_and_delete_use_scroll_payloads(self):
        store = QdrantVectorMemoryStore(
            host="http://qdrant.test",
            embedding_model=LocalHashEmbeddingModel(dimension=16),
        )
        cleaner = _cleaner_record()

        with patch(
            "codigo.app.services.vector_memory.urllib.request.urlopen",
            side_effect=[
                _FakeHTTPResponse(
                    {
                        "result": {
                            "points": [
                                {
                                    "id": "point-cleaner",
                                    "payload": {
                                        "record": cleaner.model_dump(mode="json")
                                    },
                                }
                            ],
                            "next_page_offset": None,
                        }
                    }
                ),
                _FakeHTTPResponse(
                    {
                        "result": {
                            "points": [
                                {
                                    "id": "point-cleaner",
                                    "payload": {
                                        "record": cleaner.model_dump(mode="json")
                                    },
                                }
                            ],
                            "next_page_offset": None,
                        }
                    }
                ),
                _FakeHTTPResponse({"result": {"operation_id": 2}}),
            ],
        ) as urlopen:
            listed = store.list_records(collection_name="cleaner_memory")
            deleted = store.delete("memory-cleaner-001")

        self.assertEqual([record.memory_record_id for record in listed], ["memory-cleaner-001"])
        self.assertEqual(deleted.memory_record_id, "memory-cleaner-001")
        requests = [call.args[0] for call in urlopen.call_args_list]
        self.assertIn("/collections/cleaner_memory/points/scroll", requests[0].full_url)
        self.assertIn(
            "/collections/cleaner_memory/points/delete?wait=true",
            requests[-1].full_url,
        )

    def test_upsert_persists_embedding_metadata_and_query_retrieves_boundary_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalJsonVectorMemoryStore(
                tmp,
                embedding_model=LocalHashEmbeddingModel(dimension=64),
            )
            stored = store.upsert(_overcorrection_record())

            self.assertEqual(stored.embedding_model, "local_hash_embedding")
            self.assertEqual(stored.embedding_dimension, 64)
            self.assertTrue(stored.vector_id)
            self.assertTrue((Path(tmp) / "modeler_memory.json").exists())

            context = store.query(
                AgentMemoryQuery(
                    query_id="query-threshold-overcorrection",
                    target_agent="modeler",
                    query_text=(
                        "threshold recall false positives overcorrection "
                        "unsafe anomaly retry"
                    ),
                    dataset="nasa_ims_bearing",
                    min_similarity=0.01,
                )
            )

            self.assertEqual(len(context.items), 1)
            self.assertEqual(
                context.items[0].record.memory_record_id,
                "memory-overcorrection-001",
            )
            self.assertEqual(context.items[0].retrieval_use, "boundary_context")

    def test_local_json_rejects_embedding_mismatch_without_rewriting_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = LocalJsonVectorMemoryStore(
                tmp,
                embedding_model=LocalHashEmbeddingModel(dimension=16),
            )
            original.upsert(_overcorrection_record())
            index_path = Path(tmp) / "modeler_memory.json"
            before = index_path.read_bytes()

            incompatible = LocalJsonVectorMemoryStore(
                tmp,
                embedding_model=LocalHashEmbeddingModel(dimension=32),
            )
            with self.assertRaisesRegex(
                VectorMemoryConfigError,
                "dimension mismatch",
            ):
                incompatible.query(
                    AgentMemoryQuery(
                        query_id="query-incompatible-json",
                        target_agent="modeler",
                        query_text="threshold",
                    )
                )

            self.assertEqual(index_path.read_bytes(), before)

    def test_default_query_excludes_unsafe_verdicts(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalJsonVectorMemoryStore(tmp)
            store.upsert(_unsafe_warning_record())

            default_context = store.query(
                AgentMemoryQuery(
                    query_id="query-default",
                    target_agent="modeler",
                    query_text="unsafe threshold overcorrection",
                )
            )
            self.assertEqual(default_context.items, [])

            warning_context = store.query(
                AgentMemoryQuery(
                    query_id="query-allow-unsafe-warning",
                    target_agent="modeler",
                    query_text="unsafe threshold overcorrection",
                    excluded_verdicts=[],
                    min_similarity=0.01,
                )
            )
            self.assertEqual(len(warning_context.items), 1)
            self.assertEqual(
                warning_context.items[0].retrieval_use,
                "negative_warning",
            )

    def test_query_is_scoped_to_target_agent_and_shared_methodology(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalJsonVectorMemoryStore(tmp)
            store.rebuild(
                [
                    _overcorrection_record(),
                    _cleaner_record(),
                    _shared_methodology_record(),
                ]
            )

            context = store.query(
                AgentMemoryQuery(
                    query_id="query-modeler",
                    target_agent="modeler",
                    query_text="threshold overcorrection methodology",
                    min_similarity=0.0,
                    excluded_verdicts=[],
                )
            )
            returned_ids = {item.record.memory_record_id for item in context.items}

            self.assertIn("memory-overcorrection-001", returned_ids)
            self.assertIn("memory-shared-methodology-001", returned_ids)
            self.assertNotIn("memory-cleaner-001", returned_ids)

    def test_dataset_specific_memory_never_crosses_official_and_synthetic_runs(self):
        official = _overcorrection_record().model_copy(
            update={
                "memory_record_id": "memory-official",
                "data_provenance": "official",
            }
        )
        synthetic = _overcorrection_record().model_copy(
            update={
                "memory_record_id": "memory-synthetic",
                "data_provenance": "synthetic",
            }
        )
        unknown = _overcorrection_record().model_copy(
            update={
                "memory_record_id": "memory-unknown",
                "data_provenance": "unknown",
            }
        )
        shared_unknown = _shared_methodology_record()
        shared_official = _shared_methodology_record().model_copy(
            update={
                "memory_record_id": "memory-shared-official",
                "data_provenance": "official",
            }
        )

        with tempfile.TemporaryDirectory() as tmp:
            store = LocalJsonVectorMemoryStore(tmp)
            store.rebuild(
                [official, synthetic, unknown, shared_unknown, shared_official]
            )
            synthetic_context = store.query(
                AgentMemoryQuery(
                    query_id="query-synthetic-provenance",
                    target_agent="modeler",
                    query_text="threshold overcorrection methodology",
                    dataset="nasa_ims_bearing",
                    data_provenance="synthetic",
                    excluded_verdicts=[],
                    top_k=10,
                )
            )
            official_context = store.query(
                AgentMemoryQuery(
                    query_id="query-official-provenance",
                    target_agent="modeler",
                    query_text="threshold overcorrection methodology",
                    dataset="nasa_ims_bearing",
                    data_provenance="official",
                    excluded_verdicts=[],
                    top_k=10,
                )
            )

        synthetic_ids = {
            item.record.memory_record_id for item in synthetic_context.items
        }
        official_ids = {
            item.record.memory_record_id for item in official_context.items
        }
        self.assertEqual(
            synthetic_ids,
            {
                "memory-synthetic",
                "memory-unknown",
                "memory-shared-methodology-001",
            },
        )
        self.assertEqual(
            official_ids,
            {
                "memory-official",
                "memory-unknown",
                "memory-shared-methodology-001",
            },
        )

    def test_other_agents_have_their_own_memory_collections(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalJsonVectorMemoryStore(tmp)
            store.rebuild([_evaluator_record(), _shared_methodology_record()])

            evaluator_context = store.query(
                AgentMemoryQuery(
                    query_id="query-evaluator-memory",
                    target_agent="evaluator",
                    query_text="precision recall false positive approval",
                    min_similarity=0.0,
                )
            )
            modeler_context = store.query(
                AgentMemoryQuery(
                    query_id="query-modeler-memory",
                    target_agent="modeler",
                    query_text="precision recall false positive approval",
                    min_similarity=0.0,
                )
            )
            evaluator_ids = {
                item.record.memory_record_id for item in evaluator_context.items
            }
            modeler_ids = {
                item.record.memory_record_id for item in modeler_context.items
            }

            self.assertIn("memory-evaluator-001", evaluator_ids)
            self.assertIn("memory-shared-methodology-001", evaluator_ids)
            self.assertNotIn("memory-evaluator-001", modeler_ids)

    def test_rebuild_is_reproducible_and_new_store_can_read_index(self):
        records = [_overcorrection_record()]
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalJsonVectorMemoryStore(tmp)
            store.rebuild(records)
            first_payload = (Path(tmp) / "modeler_memory.json").read_text(
                encoding="utf-8"
            )

            store.rebuild(records)
            second_payload = (Path(tmp) / "modeler_memory.json").read_text(
                encoding="utf-8"
            )
            self.assertEqual(json.loads(first_payload), json.loads(second_payload))

            reloaded = LocalJsonVectorMemoryStore(tmp)
            context = reloaded.query(
                AgentMemoryQuery(
                    query_id="query-reloaded",
                    target_agent="modeler",
                    query_text="recall threshold false positive",
                    min_similarity=0.01,
                )
            )

            self.assertEqual(context.items[0].record.memory_record_id, records[0].memory_record_id)

    def test_local_json_reads_legacy_record_without_provenance_as_unknown(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalJsonVectorMemoryStore(tmp)
            store.upsert(_overcorrection_record())
            index_path = Path(tmp) / "modeler_memory.json"
            payload = json.loads(index_path.read_text(encoding="utf-8"))
            payload["entries"][0]["record"].pop("data_provenance")
            index_path.write_text(json.dumps(payload), encoding="utf-8")

            reloaded = LocalJsonVectorMemoryStore(tmp)
            records = reloaded.list_records("modeler_memory")
            context = reloaded.query(
                AgentMemoryQuery(
                    query_id="query-legacy-unknown-provenance",
                    target_agent="modeler",
                    query_text="threshold overcorrection",
                    dataset="nasa_ims_bearing",
                    data_provenance="unknown",
                    excluded_verdicts=[],
                )
            )

        self.assertEqual(records[0].data_provenance, "unknown")
        self.assertEqual(len(context.items), 1)
        self.assertEqual(context.items[0].record.data_provenance, "unknown")

    def test_delete_removes_record_from_collection_without_rebuilding(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = LocalJsonVectorMemoryStore(tmp)
            store.rebuild([_overcorrection_record(), _evaluator_record()])

            deleted = store.delete("memory-overcorrection-001")
            modeler_context = store.query(
                AgentMemoryQuery(
                    query_id="query-after-delete",
                    target_agent="modeler",
                    query_text="threshold overcorrection",
                    min_similarity=0.0,
                    excluded_verdicts=[],
                )
            )
            evaluator_context = store.query(
                AgentMemoryQuery(
                    query_id="query-evaluator-after-delete",
                    target_agent="evaluator",
                    query_text="precision recall false positive",
                    min_similarity=0.0,
                )
            )

            self.assertEqual(deleted.memory_record_id, "memory-overcorrection-001")
            self.assertEqual(modeler_context.items, [])
            self.assertEqual(len(evaluator_context.items), 1)
            with self.assertRaises(FileNotFoundError):
                store.delete("memory-overcorrection-001")

    def test_memory_record_from_postmortem_respects_review_policy(self):
        postmortem = AgentReasoningPostmortem(
            postmortem_id="postmortem-overcorrected-001",
            run_id="retry-run",
            source_run_id="base-run",
            agent_name="modeler",
            decision_id="modeler-retry-001",
            attempt_number=2,
            max_attempts=2,
            hypothesis="Lowering the threshold should catch missed anomalies.",
            action_taken="threshold_quantile=0.5",
            expected_effect="Increase recall.",
            before_metrics={"recall": 0.65, "false_positive_rate": 0.21},
            after_metrics={"recall": 1.0, "false_positive_rate": 1.0},
            outcome="overcorrected",
            automatic_critique="Recall improved but FPR became unsafe.",
            reusable_lessons=["do_not_optimize_recall_without_fpr_control"],
        )

        pending_record = memory_record_from_postmortem(
            postmortem,
            dataset="nasa_ims_bearing",
        )
        self.assertFalse(pending_record.reusable_as_context)
        self.assertEqual(pending_record.memory_role, "boundary_case")

        reviewed_record = memory_record_from_postmortem(
            postmortem,
            review=HumanReasoningReview(
                review_id="review-overcorrected-001",
                postmortem_id=postmortem.postmortem_id,
                run_id=postmortem.run_id,
                decision_id=postmortem.decision_id,
                reviewer="advisor",
                verdict="partially_correct",
                rationale="Correct direction but unsafe magnitude.",
                reusable_as_context=True,
                tags=["threshold", "overcorrection"],
            ),
            dataset="nasa_ims_bearing",
        )

        self.assertTrue(reviewed_record.reusable_as_context)
        self.assertEqual(reviewed_record.memory_role, "boundary_case")
        self.assertEqual(reviewed_record.collection_name, "modeler_memory")

    def test_memory_record_from_usage_audit_is_non_reusable_observation(self):
        record = memory_record_from_memory_usage_audit(
            _memory_usage_audit(),
            target_agent="modeler",
            dataset="nasa_ims_bearing",
            source_path="reports/run/iteration/memory_usage_audit.json",
            source_hash="abc123",
        )

        self.assertEqual(record.source_type, "memory_usage_audit")
        self.assertEqual(record.collection_name, "modeler_memory")
        self.assertEqual(record.memory_role, "warning")
        self.assertFalse(record.reusable_as_context)
        self.assertIn("non_reusable_memory_observation", record.tags)
        self.assertIn("memory_repeated_boundary_failure", record.tags)
        self.assertIn("false_positive_rate", record.content)

    def test_decision_episode_candidate_requires_source_bound_promotion(self):
        candidate = memory_candidate_from_decision_episode(
            _decision_episode(),
            human_verdict="partially_correct",
            reusable_as_context=True,
        )
        record = memory_record_from_candidate(
            candidate,
            source_path="reports/run/iteration/memory_candidate.json",
            source_hash="d" * 64,
        )

        self.assertEqual(record.source_type, "decision_episode")
        self.assertEqual(candidate.data_provenance, "synthetic")
        self.assertEqual(record.data_provenance, "synthetic")
        self.assertEqual(record.memory_role, "boundary_case")
        self.assertIn("When to reuse", record.content)
        self.assertIn("modeler", record.tags)

        with tempfile.TemporaryDirectory() as tmp:
            store = LocalJsonVectorMemoryStore(
                tmp,
                embedding_model=LocalHashEmbeddingModel(dimension=64),
            )
            store.upsert(record)
            context = store.query(
                AgentMemoryQuery(
                    query_id="query-episode-candidate",
                    target_agent="modeler",
                    query_text="moderate threshold recall false positive tradeoff",
                    dataset="nasa_ims_bearing",
                    data_provenance="synthetic",
                    min_similarity=0.0,
                )
            )

            self.assertEqual(context.items, [])

            promoted = record.model_copy(
                update={"promotion_source_hash": record.source_hash}
            )
            store.upsert(promoted)
            promoted_context = store.query(
                AgentMemoryQuery(
                    query_id="query-decision-episode-promoted",
                    target_agent="modeler",
                    query_text="moderate threshold false positive rate",
                    dataset="nasa_ims_bearing",
                    data_provenance="synthetic",
                    min_similarity=0.0,
                )
            )
            self.assertEqual(
                [item.record.memory_record_id for item in promoted_context.items],
                [record.memory_record_id],
            )


class _FakeHTTPResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def __enter__(self) -> "_FakeHTTPResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


def _qdrant_collection_info_payload(
    indexed_fields: dict[str, str] | None = None,
    *,
    vector_size: int = 16,
    distance: str = "Cosine",
) -> dict[str, object]:
    resolved_fields = (
        dict(QDRANT_MEMORY_PAYLOAD_INDEXES)
        if indexed_fields is None
        else indexed_fields
    )
    return {
        "result": {
            "status": "green",
            "config": {
                "params": {
                    "vectors": {
                        "size": vector_size,
                        "distance": distance,
                    }
                }
            },
            "payload_schema": {
                field_name: {"data_type": field_schema}
                for field_name, field_schema in resolved_fields.items()
            },
        }
    }


def _overcorrection_record() -> ReasoningMemoryRecord:
    return ReasoningMemoryRecord(
        memory_record_id="memory-overcorrection-001",
        collection_name="modeler_memory",
        target_agent="modeler",
        source_type="reasoning_postmortem",
        run_id="nasa-ims-synth-agentic-qwen-fase3-retry-attempt-02",
        postmortem_id="postmortem-retry-02",
        decision_id="modeler-retry-02",
        dataset="nasa_ims_bearing",
        source_agent_name="modeler",
        outcome="overcorrected",
        human_verdict="partially_correct",
        memory_role="boundary_case",
        reusable_as_context=True,
        summary="Threshold reduction improved recall but caused unsafe FPR.",
        content=(
            "The modeler lowered the anomaly threshold to catch false negatives. "
            "Recall improved to 1.0, but false positive rate also reached 1.0. "
            "This is an overcorrection boundary case."
        ),
        metrics={"recall": 1.0, "false_positive_rate": 1.0, "f1_score": 0.8333},
        tags=["threshold", "recall", "false_positive_rate", "overcorrection"],
    )


def _unsafe_warning_record() -> ReasoningMemoryRecord:
    return ReasoningMemoryRecord(
        memory_record_id="memory-unsafe-warning-001",
        collection_name="modeler_memory",
        target_agent="modeler",
        source_type="human_review",
        run_id="nasa-ims-synth-agentic-qwen-fase3-retry-attempt-02",
        postmortem_id="postmortem-retry-02",
        decision_id="modeler-retry-02",
        dataset="nasa_ims_bearing",
        source_agent_name="modeler",
        outcome="overcorrected",
        human_verdict="unsafe",
        memory_role="warning",
        reusable_as_context=True,
        summary="Unsafe retry pattern: recall-only optimization.",
        content=(
            "A human reviewer marked this threshold change unsafe because it "
            "optimized recall while ignoring the false positive rate."
        ),
        metrics={"recall": 1.0, "false_positive_rate": 1.0},
        tags=["unsafe", "threshold", "overcorrection"],
    )


def _cleaner_record() -> ReasoningMemoryRecord:
    return ReasoningMemoryRecord(
        memory_record_id="memory-cleaner-001",
        collection_name="cleaner_memory",
        target_agent="cleaner",
        source_type="reasoning_postmortem",
        dataset="nasa_ims_bearing",
        source_agent_name="cleaner",
        outcome="partially_supported",
        human_verdict="partially_correct",
        memory_role="boundary_case",
        reusable_as_context=True,
        summary="Channel selection needed extra evidence.",
        content="The cleaner selected a channel but required stronger evidence.",
        tags=["channel_selection"],
    )


def _shared_methodology_record() -> ReasoningMemoryRecord:
    return ReasoningMemoryRecord(
        memory_record_id="memory-shared-methodology-001",
        collection_name="shared_methodology_memory",
        target_agent="shared_methodology",
        source_type="methodology_note",
        dataset=None,
        source_agent_name=None,
        outcome=None,
        human_verdict="correct",
        memory_role="methodology",
        reusable_as_context=True,
        summary="Do not optimize a single metric without checking trade-offs.",
        content=(
            "For industrial anomaly detection, recall improvements must be "
            "interpreted together with false positive rate and precision."
        ),
        tags=["methodology", "tradeoff"],
    )


def _evaluator_record() -> ReasoningMemoryRecord:
    return ReasoningMemoryRecord(
        memory_record_id="memory-evaluator-001",
        collection_name="evaluator_memory",
        target_agent="evaluator",
        source_type="reasoning_postmortem",
        dataset="nasa_ims_bearing",
        source_agent_name="evaluator",
        outcome="supported",
        human_verdict="correct",
        memory_role="positive_example",
        reusable_as_context=True,
        summary="Approval should consider recall and false positive rate together.",
        content=(
            "The evaluator accepted only configurations that improved recall "
            "without making the false positive rate operationally unsafe."
        ),
        tags=["evaluation", "tradeoff"],
    )


def _memory_usage_audit() -> MemoryUsageAudit:
    return MemoryUsageAudit(
        audit_id="memory-audit-001",
        run_id="retry-run",
        decision_id="modeler-retry-001",
        memory_context_id="ctx-001",
        used_memory_context=True,
        memory_usage_summary=(
            "The agent cited the warning but repeated an excessive threshold shift."
        ),
        retrieved_memory_record_ids=["postmortem-retry-02:memory:modeler"],
        cited_memory_record_ids=["postmortem-retry-02:memory:modeler"],
        before_metrics={"recall": 0.65, "false_positive_rate": 0.21},
        after_metrics={"recall": 1.0, "false_positive_rate": 1.0},
        outcome="memory_repeated_boundary_failure",
        summary=(
            "The retrieved boundary memory was cited, but the retry reproduced "
            "the same high false_positive_rate failure."
        ),
    )


def _decision_episode() -> DecisionEpisode:
    return DecisionEpisode(
        episode_id="episode-modeler-threshold-095",
        run_id="nasa-memory-fed",
        decision_id="modeler-retry-001",
        agent_name="modeler",
        target_agent="modeler",
        decision_type="modeling",
        dataset="nasa_ims_bearing",
        data_provenance="synthetic",
        context_summary="Low recall with false negatives close to the threshold.",
        options_considered=[
            DecisionOption(
                option_id="iforest-threshold-095",
                option_type="model_config",
                description="Isolation Forest with threshold_quantile=0.95.",
                parameters={"model": "isolation_forest", "threshold_quantile": 0.95},
                expected_effect="Improve recall without repeating FPR=1.0.",
                risk_notes=["FPR can still rise above the evaluator target."],
                selected=True,
            ),
        ],
        chosen_action="Use isolation_forest with threshold_quantile=0.95.",
        expected_effect="Improve recall moderately and avoid threshold_quantile=0.50.",
        evidence_used=["failure_analysis", "retrieved_memory_context"],
        retrieved_memory_record_ids=[
            "postmortem-overcorrection:memory:modeler",
            "memory-audit-warning:memory:modeler",
        ],
        execution_result_summary="Recall and F1 improved, but FPR still exceeded target.",
        before_metrics={"recall": 0.6, "false_positive_rate": 0.1429},
        after_metrics={"recall": 0.6571, "false_positive_rate": 0.2143},
        tradeoffs_observed=["recall_improved_fpr_worsened"],
        failure_modes=["partial_recall_gain_with_fpr_increase"],
        outcome="partially_supported",
        lesson_learned=(
            "Memory warning avoided the radical threshold change, but threshold "
            "tuning alone was insufficient."
        ),
        reusable_lessons=["compare_model_family_after_threshold_plateau"],
        when_to_reuse=["low recall and prior warning against radical threshold shifts"],
        when_not_to_reuse=["FPR target is strict and model alternatives are available"],
        risk_if_misused="May keep tuning thresholds instead of comparing model families.",
    )


if __name__ == "__main__":
    unittest.main()
