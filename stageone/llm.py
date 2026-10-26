"""One door to the model. Every call returns a validated pydantic object."""

from __future__ import annotations

from typing import Protocol, TypeVar

from anthropic import Anthropic
from anthropic.types import ToolParam, ToolUseBlock
from pydantic import BaseModel, ValidationError

from stageone.errors import LLMError

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
