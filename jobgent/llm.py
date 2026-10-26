"""One door to the model. Every call returns a validated pydantic object."""

from __future__ import annotations

from typing import Protocol, TypeVar

import httpx
from anthropic import Anthropic
from anthropic.types import ToolParam, ToolUseBlock
from pydantic import BaseModel, ValidationError

from jobgent.errors import LLMError

T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    def complete_json(
        self, *, model: str, system: str, user: str, schema: type[T], max_tokens: int = 2048
    ) -> T: ...


class AnthropicLLM:
    def __init__(self, api_key: str) -> None:
        self.client = Anthropic(api_key=api_key)

    def complete_json(
        self, *, model: str, system: str, user: str, schema: type[T], max_tokens: int = 2048
    ) -> T:
        tool: ToolParam = {
            "name": "emit",
            "description": "Return the result in the required structure.",
            "input_schema": schema.model_json_schema(),
        }
        message = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            tools=[tool],
            tool_choice={"type": "tool", "name": "emit"},
        )
        for block in message.content:
            if isinstance(block, ToolUseBlock):
                try:
                    return schema.model_validate(block.input)
                except ValidationError as e:
                    raise LLMError(f"model output failed validation for {schema.__name__}: {e}", str(block.input)) from e
        texts = " ".join(getattr(b, "text", "") for b in message.content)
        raise LLMError(f"model returned no structured output for {schema.__name__}", texts)


KIE_BASE_URL = "https://api.kie.ai/claude"


class KieLLM:
    """Claude through KIE (https://docs.kie.ai): Anthropic Messages format at api.kie.ai/claude/v1/messages,
    Bearer auth, streaming on by default (we turn it off), errors returned as HTTP 200 with a `code` in the body."""

    def __init__(self, api_key: str, base_url: str = KIE_BASE_URL) -> None:
        self.url = base_url.rstrip("/") + "/v1/messages"
        self.headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", "anthropic-version": "2023-06-01"}

    def complete_json(
        self, *, model: str, system: str, user: str, schema: type[T], max_tokens: int = 2048
    ) -> T:
        body = {
            "model": model,
            "max_tokens": max_tokens,
            "stream": False,
            "system": system + "\n\nAnswer by calling the `emit` tool exactly once.",
            "messages": [{"role": "user", "content": user}],
            "tools": [{"name": "emit", "description": "Return the result in the required structure.", "input_schema": schema.model_json_schema()}],
            "tool_choice": {"type": "tool", "name": "emit"},
        }
        try:
            resp = httpx.post(self.url, headers=self.headers, json=body, timeout=180)
        except httpx.HTTPError as e:
            raise LLMError(f"KIE request failed: {e}", "") from e
        if resp.status_code >= 400:
            raise LLMError(f"KIE answered HTTP {resp.status_code}", resp.text[:500])
        data = resp.json()
        if "content" not in data:
            raise LLMError(f"KIE error {data.get('code')}: {data.get('msg') or data.get('message')}", resp.text[:500])
        for block in data["content"]:
            if block.get("type") == "tool_use":
                try:
                    return schema.model_validate(block.get("input"))
                except ValidationError as e:
                    raise LLMError(f"model output failed validation for {schema.__name__}: {e}", str(block.get("input"))) from e
        texts = " ".join(str(b.get("text", "")) for b in data["content"])
        raise LLMError(f"model returned no structured output for {schema.__name__}", texts)


class FakeLLM:
    """Test double: returns queued responses in order."""

    def __init__(self, responses: list[BaseModel]) -> None:
        self.responses = list(responses)
        self.calls = 0
        self.prompts: list[tuple[str, str]] = []

    def complete_json(
        self, *, model: str, system: str, user: str, schema: type[T], max_tokens: int = 2048
    ) -> T:
        self.calls += 1
        self.prompts.append((system, user))
        if not self.responses:
            raise AssertionError(f"FakeLLM has no response left for {schema.__name__}")
        response = self.responses.pop(0)
        if not isinstance(response, schema):
            raise AssertionError(f"FakeLLM queued {type(response).__name__}, caller wanted {schema.__name__}")
        return response
