"""LLM provider + vision reviewer tests with a mocked HTTP transport."""

from __future__ import annotations

import json

import httpx
import pytest

from harness_server.config import Settings
from harness_server.llm.provider import ChatProvider, ProviderError


def _transport(responses):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content or b"{}")
        if isinstance(responses, list):
            resp = responses.pop(0)
        else:
            resp = responses
        return httpx.Response(resp["status"], json=resp.get("json"), text=resp.get("text"))

    return httpx.AsyncClient(transport=httpx.MockTransport(handler)), captured


async def test_chat_tool_calling_request_and_parse():
    llm_reply = {
        "choices": [{
            "message": {
                "content": None,
                "tool_calls": [{
                    "id": "call_abc",
                    "type": "function",
                    "function": {"name": "create_cube", "arguments": '{"name": "X", "dimensions_mm": [10, 20, 30]}'},
                }],
            },
            "finish_reason": "tool_calls",
        }]
    }
    client, captured = _transport({"status": 200, "json": llm_reply})
    provider = ChatProvider(base_url="https://llm.example/v1", api_key="k",
                            model="model-x", client=client)
    try:
        out = await provider.chat(
            [{"role": "user", "content": "hi"}],
            tools=[{"type": "function", "function": {"name": "create_cube", "parameters": {}}}],
        )
        assert captured["url"].endswith("/chat/completions")
        auth = captured["headers"].get("authorization") or captured["headers"].get("Authorization")
        assert auth == "Bearer k"
        assert captured["body"]["model"] == "model-x"
        assert captured["body"]["tools"][0]["function"]["name"] == "create_cube"

        calls = provider.parse_tool_calls(out["message"])
        assert len(calls) == 1
        assert calls[0]["name"] == "create_cube"
        assert calls[0]["arguments"]["dimensions_mm"] == [10, 20, 30]
        assert out["finish_reason"] == "tool_calls"
    finally:
        await client.aclose()


async def test_chat_error_raises_provider_error():
    client, _ = _transport({"status": 401, "json": {"error": "bad key"}})
    provider = ChatProvider(base_url="https://llm.example/v1", api_key="bad", model="m", client=client)
    try:
        with pytest.raises(ProviderError):
            await provider.chat([{"role": "user", "content": "hi"}])
    finally:
        await client.aclose()


def test_parse_tool_calls_bad_json():
    provider = ChatProvider(base_url="x", api_key=None, model="m")
    calls = provider.parse_tool_calls({"tool_calls": [
        {"id": "1", "function": {"name": "n", "arguments": "{not json"}}]})
    assert calls[0]["arguments"].get("_raw")


# ---------------------------------------------------------------------------
# vision reviewer
# ---------------------------------------------------------------------------


def _settings(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_vision_skipped_without_model():
    from harness_server.vision.reviewer import VisionReviewer

    s = _settings(ai_model=None, ai_base_url="http://127.0.0.1:1/v1")
    reviewer = VisionReviewer(s)
    out = None

    async def _run():
        nonlocal out
        out = await reviewer.review("make it rounder", "facts", [])

    import asyncio

    asyncio.run(_run())
    assert out["verdict"] == "SKIPPED"


def test_vision_parse_verdicts():
    from harness_server.vision.reviewer import VisionReviewer

    parsed = VisionReviewer._parse('{"verdict": "PASS", "issues": [], "comment": "ok"}')
    assert parsed["verdict"] == "PASS"
    parsed = VisionReviewer._parse('```json\n{"verdict": "REFINE", "issues": ["big gap"], "comment": "c"}\n```')
    assert parsed["verdict"] == "REFINE" and parsed["issues"] == ["big gap"]
    parsed = VisionReviewer._parse("REFINE because corners are sharp")
    assert parsed["verdict"] == "REFINE"


def test_settings_vision_falls_back_to_chat():
    s = _settings(ai_model="gpt-4o", ai_base_url="https://api.openai.com/v1", ai_api_key="k")
    assert s.vision_configured is True
    assert s.vision_model == "gpt-4o"

    s2 = _settings(ai_model="gpt-4o", ai_base_url="https://api.openai.com/v1", ai_api_key=None)
    assert s2.vision_configured is False  # no key and remote base -> cannot review

    s3 = _settings(ai_model="llama3", ai_base_url="http://127.0.0.1:11434/v1", ai_api_key="ollama")
    assert s3.vision_configured is True  # local endpoints need no key
