import argparse
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from codigo.scripts import run_dataset_pipeline_with_memory
from codigo.scripts import run_nasa_ims_agentic_retry
from codigo.app.services.vector_memory import (
    QdrantVectorMemoryStore,
)


class MemoryBackendScriptSelectionTests(unittest.TestCase):
    def test_dataset_runner_memory_config_can_select_qdrant(self):
        args = argparse.Namespace(
            use_memory=True,
            memory_dir=Path("codigo/reports/reasoning_memory"),
            embedding_provider="local_hash",
            embedding_model="qwen3-embedding:0.6b",
            ollama_host="http://127.0.0.1:11434",
            embedding_timeout_seconds=60.0,
            hash_dimension=16,
        )

        with patch.dict(
            os.environ,
            {
                "TFM_MEMORY_BACKEND": "qdrant",
                "TFM_QDRANT_HOST": "http://qdrant.test",
            },
            clear=True,
        ):
            config = run_dataset_pipeline_with_memory._memory_config(
                args,
                "codigo/reports",
            )

        self.assertIsNotNone(config)
        self.assertIsInstance(config.memory_store, QdrantVectorMemoryStore)
        self.assertEqual(config.memory_store.host, "http://qdrant.test")

    def test_nasa_retry_memory_store_can_select_qdrant(self):
        args = argparse.Namespace(
            memory_dir="codigo/reports/reasoning_memory",
            embedding_provider="local_hash",
            embedding_model="qwen3-embedding:0.6b",
            ollama_host="http://127.0.0.1:11434",
            embedding_timeout_seconds=60.0,
            hash_dimension=16,
        )

        with patch.dict(
            os.environ,
            {
                "TFM_MEMORY_BACKEND": "qdrant",
                "TFM_QDRANT_HOST": "http://qdrant.test",
            },
            clear=True,
        ):
            store = run_nasa_ims_agentic_retry._memory_store_from_args(args)

        self.assertIsInstance(store, QdrantVectorMemoryStore)
        self.assertEqual(store.host, "http://qdrant.test")


if __name__ == "__main__":
    unittest.main()
