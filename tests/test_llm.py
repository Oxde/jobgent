import httpx
import pytest
import respx
from pydantic import BaseModel

from stageone.errors import LLMError
from stageone.llm import AnthropicLLM, FakeLLM


class Out(BaseModel):
    answer: int


def test_fake_llm_returns_queued_responses():
    llm = FakeLLM([Out(answer=1), Out(answer=2)])
    assert llm.complete_json(model="m", system="s", user="u", schema=Out).answer == 1
    assert llm.complete_json(model="m", system="s", user="u", schema=Out).answer == 2
    assert llm.calls == 2


def test_anthropic_llm_parses_tool_use_block():
    llm = AnthropicLLM(api_key="sk")
    body = {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "m",
        "content": [{"type": "tool_use", "id": "tu_1", "name": "emit", "input": {"answer": 42}}],
        "stop_reason": "tool_use", "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    with respx.mock as m:
        route = m.post("https://api.anthropic.com/v1/messages").mock(return_value=httpx.Response(200, json=body))
        out = llm.complete_json(model="m", system="s", user="u", schema=Out)
    assert out.answer == 42
    sent = route.calls[0].request.content
    assert b'"tool_choice"' in sent and b'"emit"' in sent


def test_anthropic_llm_raises_llm_error_on_bad_payload():
    llm = AnthropicLLM(api_key="sk")
    body = {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "m",
        "content": [{"type": "text", "text": "I refuse"}],
        "stop_reason": "end_turn", "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    with respx.mock as m:
        m.post("https://api.anthropic.com/v1/messages").mock(return_value=httpx.Response(200, json=body))
        with pytest.raises(LLMError, match="I refuse"):
            llm.complete_json(model="m", system="s", user="u", schema=Out)
