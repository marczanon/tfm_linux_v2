import json
import unittest
from unittest.mock import MagicMock, patch

from codigo.app.services.llm import (
    DEFAULT_OLLAMA_CHAT_MODEL,
    LLMCallError,
    LLMMessage,
    OllamaJSONClient,
    get_default_json_llm_client,
    parse_json_object,
)


class FakeOllamaJSONClient(OllamaJSONClient):
    def __init__(self, responses, *, max_json_repair_attempts=1):
        super().__init__(
            model="fake-model",
            host="http://127.0.0.1:11434",
            timeout_seconds=1.0,
            max_json_repair_attempts=max_json_repair_attempts,
        )
        object.__setattr__(self, "responses", list(responses))
        object.__setattr__(self, "requests", [])

    def _chat(self, messages, *, json_schema=None):
        self.requests.append((messages, json_schema))
        if not self.responses:
            raise LLMCallError("no fake responses left")
        return self.responses.pop(0)


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

    def test_ollama_client_repairs_invalid_json_once_when_schema_is_available(self):
        client = FakeOllamaJSONClient(
            [
                {"message": {"content": '{"ok": true'}},
                {"message": {"content": '{"ok": true, "value": 5}'}},
            ]
        )

        parsed = client.complete_json(
            [LLMMessage(role="user", content="Devuelve JSON.")],
            json_schema={"title": "Decision", "type": "object"},
        )

        self.assertEqual(parsed, {"ok": True, "value": 5})
        self.assertEqual(len(client.requests), 2)
        repair_messages = client.requests[1][0]
        self.assertIn("respuesta anterior no era JSON valido", repair_messages[-1].content)
        self.assertIn("Esquema JSON de referencia", repair_messages[-1].content)

    def test_ollama_client_does_not_repair_without_enabled_attempts(self):
        client = FakeOllamaJSONClient(
            [{"message": {"content": '{"ok": true'}}],
            max_json_repair_attempts=0,
        )

        with self.assertRaises(LLMCallError):
            client.complete_json(
                [LLMMessage(role="user", content="Devuelve JSON.")],
                json_schema={"title": "Decision", "type": "object"},
            )

        self.assertEqual(len(client.requests), 1)

    def test_ollama_chat_sends_json_schema_as_structured_output_format(self):
        schema = {
            "title": "Decision",
            "type": "object",
            "properties": {"ok": {"type": "boolean"}},
            "required": ["ok"],
        }
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"message":{"content":"{\\"ok\\":true}"}}'
        client = OllamaJSONClient(model="fake-model")

        with patch(
            "codigo.app.services.llm.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            client._chat(
                [LLMMessage(role="user", content="Devuelve JSON.")],
                json_schema=schema,
            )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["format"], schema)
        self.assertEqual(payload["options"]["temperature"], 0)

    def test_ollama_chat_keeps_generic_json_format_without_schema(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b'{"message":{"content":"{}"}}'
        client = OllamaJSONClient(model="fake-model")

        with patch(
            "codigo.app.services.llm.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            client._chat(
                [LLMMessage(role="user", content="Devuelve JSON.")],
                json_schema=None,
            )

        request = urlopen.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["format"], "json")

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
