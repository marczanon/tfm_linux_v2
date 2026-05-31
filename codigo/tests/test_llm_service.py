import unittest
from unittest.mock import patch

from codigo.app.services.llm import (
    DEFAULT_OLLAMA_CHAT_MODEL,
    LLMCallError,
    OllamaJSONClient,
    get_default_json_llm_client,
    parse_json_object,
)


class LLMServiceTests(unittest.TestCase):
    def test_parse_json_object_accepts_plain_json(self):
        parsed = parse_json_object('{"ok": true, "value": 3}')

        self.assertEqual(parsed, {"ok": True, "value": 3})

    def test_parse_json_object_extracts_object_from_text(self):
        parsed = parse_json_object('respuesta:\n{"ok": true}\nfin')

        self.assertEqual(parsed, {"ok": True})

    def test_parse_json_object_rejects_non_object_json(self):
        with self.assertRaises(LLMCallError):
            parse_json_object("[1, 2, 3]")

    def test_default_ollama_client_disables_thinking_for_strict_json(self):
        with patch.dict(
            "os.environ",
            {
                "TFM_LLM_PROVIDER": "ollama",
                "TFM_LLM_MODEL": "qwen3.5:4b",
            },
            clear=True,
        ):
            client = get_default_json_llm_client()

        self.assertIsInstance(client, OllamaJSONClient)
        self.assertFalse(client.think)

    def test_default_ollama_client_uses_project_qwen_model(self):
        with patch.dict("os.environ", {"TFM_LLM_PROVIDER": "ollama"}, clear=True):
            client = get_default_json_llm_client()

        self.assertIsInstance(client, OllamaJSONClient)
        self.assertEqual(client.model, DEFAULT_OLLAMA_CHAT_MODEL)

    def test_default_ollama_client_allows_thinking_override(self):
        with patch.dict(
            "os.environ",
            {
                "TFM_LLM_PROVIDER": "ollama",
                "TFM_LLM_MODEL": "qwen3.5:4b",
                "TFM_LLM_THINK": "true",
            },
            clear=True,
        ):
            client = get_default_json_llm_client()

        self.assertIsInstance(client, OllamaJSONClient)
        self.assertTrue(client.think)

    def test_default_ollama_client_can_omit_thinking_parameter(self):
        with patch.dict(
            "os.environ",
            {
                "TFM_LLM_PROVIDER": "ollama",
                "TFM_LLM_MODEL": "qwen3.5:4b",
                "TFM_LLM_THINK": "auto",
            },
            clear=True,
        ):
            client = get_default_json_llm_client()

        self.assertIsInstance(client, OllamaJSONClient)
        self.assertIsNone(client.think)


if __name__ == "__main__":
    unittest.main()
