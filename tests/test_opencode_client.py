"""Unit tests for opencode_client — no live server, httpx.MockTransport only.

Run: .venv\\Scripts\\python -m unittest tests.test_opencode_client -v
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import httpx

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from opencode_client import (  # noqa: E402
    OpencodeServer, _SessionEvents, extract_text, split_model,
)


SESSION = {"id": "ses_test123", "title": "t"}
MESSAGE_OK = {
    "info": {"id": "msg_1", "tokens": {"input": 10, "output": 5}, "cost": 0.001},
    "parts": [
        {"type": "step-start"},
        {"type": "text", "text": "hello "},
        {"type": "reasoning"},
        {"type": "text", "text": "world"},
        {"type": "step-finish"},
    ],
}


def make_server(handler) -> OpencodeServer:
    client = httpx.Client(transport=httpx.MockTransport(handler),
                          base_url="http://testserver")
    return OpencodeServer(Path("."), port=1, client=client)


class TestPureHelpers(unittest.TestCase):
    def test_split_model(self):
        self.assertEqual(split_model("kimi/kimi-k3"),
                         {"providerID": "kimi", "modelID": "kimi-k3"})
        self.assertEqual(split_model("openai/gpt-4o"),
                         {"providerID": "openai", "modelID": "gpt-4o"})

    def test_extract_text(self):
        self.assertEqual(extract_text(MESSAGE_OK), "hello world")
        self.assertEqual(extract_text({"parts": []}), "")
        self.assertEqual(extract_text({}), "")


class TestSessionEvents(unittest.TestCase):
    def test_filters_other_sessions(self):
        cap = _SessionEvents("ses_A")
        cap.feed({"type": "session.error", "properties": {
            "sessionID": "ses_B", "error": {"name": "ProviderError"}}})
        self.assertIsNone(cap.first_error)
        self.assertEqual(cap.lines, [])

    def test_api_error_captured(self):
        cap = _SessionEvents("ses_A")
        cap.feed({"type": "session.error", "properties": {
            "sessionID": "ses_A",
            "error": {"name": "ProviderError", "data": {"message": "401 unauthorized"}}}})
        self.assertEqual(cap.first_error["name"], "ProviderError")

    def test_abort_sets_flag_not_error(self):
        cap = _SessionEvents("ses_A")
        cap.feed({"type": "session.error", "properties": {
            "sessionID": "ses_A", "error": {"name": "MessageAbortedError"}}})
        self.assertTrue(cap.aborted.is_set())
        self.assertIsNone(cap.first_error)

    def test_permission_queued(self):
        cap = _SessionEvents("ses_A")
        cap.feed({"type": "permission.asked", "properties": {
            "id": "per_1", "sessionID": "ses_A", "permission": "bash"}})
        self.assertEqual(len(cap.permission_requests), 1)


class TestRunStep(unittest.TestCase):
    def test_happy_path(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/session":
                return httpx.Response(200, json=SESSION)
            if request.url.path.endswith("/message"):
                body = json.loads(request.content)
                assert body["model"] == {"providerID": "kimi", "modelID": "kimi-k3"}
                assert body["agent"] == "source_processor"
                return httpx.Response(200, json=MESSAGE_OK)
            return httpx.Response(404)

        srv = make_server(handler)
        res = srv.run_step(agent="source_processor", model="kimi/kimi-k3",
                           prompt="p", slug="s", timeout_s=10, use_sse=False)
        self.assertTrue(res.success)
        self.assertEqual(res.final_text, "hello world")
        self.assertEqual(res.session_id, "ses_test123")
        self.assertEqual(res.tokens, {"input": 10, "output": 5})
        self.assertEqual(res.cost, 0.001)

    def test_http_500_is_process_error(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/session":
                return httpx.Response(200, json=SESSION)
            return httpx.Response(500, text="boom")

        srv = make_server(handler)
        res = srv.run_step(agent="a", model="kimi/kimi-k3", prompt="p",
                           slug="s", timeout_s=10, use_sse=False)
        self.assertFalse(res.success)
        self.assertEqual(res.error_kind, "process")
        self.assertIn("500", res.error)

    def test_timeout_calls_abort(self):
        aborted = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/session":
                return httpx.Response(200, json=SESSION)
            if request.url.path.endswith("/abort"):
                aborted.append(True)
                return httpx.Response(200, json=True)
            if request.url.path.endswith("/message"):
                raise httpx.ReadTimeout("simulated", request=request)
            return httpx.Response(404)

        srv = make_server(handler)
        res = srv.run_step(agent="a", model="kimi/kimi-k3", prompt="p",
                           slug="s", timeout_s=10, use_sse=False)
        self.assertFalse(res.success)
        self.assertEqual(res.error_kind, "timeout")
        self.assertTrue(aborted, "abort must be called on timeout")

    def test_parent_id_passed(self):
        seen = {}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/session":
                seen.update(json.loads(request.content))
                return httpx.Response(200, json=SESSION)
            if request.url.path.endswith("/message"):
                return httpx.Response(200, json=MESSAGE_OK)
            return httpx.Response(404)

        srv = make_server(handler)
        srv.run_step(agent="a", model="kimi/kimi-k3", prompt="p", slug="s",
                     timeout_s=10, parent_id="ses_root", use_sse=False)
        self.assertEqual(seen.get("parentID"), "ses_root")


if __name__ == "__main__":
    unittest.main()
