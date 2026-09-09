"""Minimal OpenAI-compatible chat-completions client (tool calling included).

Works against OpenAI, DeepSeek, Qwen, OpenRouter, LM Studio, Ollama, vLLM —
any endpoint that implements POST {base}/chat/completions.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

import httpx

log = logging.getLogger("harness.llm")


class ProviderError(Exception):
    pass


class ChatProvider:
    def __init__(
        self,
        base_url: str,
        api_key: Optional[str],
        model: str,
        timeout_s: float = 180.0,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_s = timeout_s
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout_s)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def _headers(self) -> Dict[str, str]:
        h = {"Content-Type": "application/json"}
        if self.api_key:
            h["Authorization"] = f"Bearer {self.api_key}"
        return h

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        temperature: float = 0.2,
    ) -> Dict[str, Any]:
        """Returns {"message": {...}, "finish_reason": str} for the first choice."""
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            body["tools"] = tools
        url = f"{self.base_url}/chat/completions"
        try:
            resp = await self._client.post(url, headers=self._headers(), json=body)
        except httpx.HTTPError as exc:  # pragma: no cover - network
            raise ProviderError(f"LLM request failed: {exc}") from exc

        if resp.status_code >= 400:
            detail = resp.text[:800]
            raise ProviderError(f"LLM API error {resp.status_code}: {detail}")

        try:
            data = resp.json()
            choice = data["choices"][0]
        except (ValueError, KeyError, IndexError) as exc:
            raise ProviderError(f"Unexpected LLM response: {resp.text[:800]}") from exc

        msg = choice.get("message") or {}
        return {"message": msg, "finish_reason": choice.get("finish_reason", "")}

    @staticmethod
    def parse_tool_calls(message: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Normalize an assistant message's tool_calls into
        [{id, name, arguments(dict)}]. Arguments arrive as JSON strings."""
        calls: List[Dict[str, Any]] = []
        for tc in message.get("tool_calls") or []:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            raw_args = fn.get("arguments") or "{}"
            try:
                arguments = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
            except ValueError:
                arguments = {"_raw": raw_args}
            calls.append({"id": tc.get("id") or f"call_{len(calls)}", "name": name, "arguments": arguments})
        return calls
