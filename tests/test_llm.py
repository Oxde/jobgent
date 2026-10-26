import httpx
import pytest
import respx
from pydantic import BaseModel

from jobgent.errors import LLMError
from jobgent.llm import AnthropicLLM, FakeLLM


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


def test_kie_provider_uses_bearer_auth_non_streaming_and_parses_tool_use():
    import json as _json

    from jobgent.llm import KieLLM

    llm = KieLLM(api_key="kie-key")
    body = {
        "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-sonnet-4-5",
        "content": [{"type": "tool_use", "id": "tu_1", "name": "emit", "input": {"answer": 7}}],
        "stop_reason": "tool_use", "stop_sequence": None, "usage": {"input_tokens": 1, "output_tokens": 1},
    }
    with respx.mock as m:
        route = m.post("https://api.kie.ai/claude/v1/messages").mock(return_value=httpx.Response(200, json=body))
        out = llm.complete_json(model="claude-sonnet-4-5", system="s", user="u", schema=Out)
    assert out.answer == 7
    req = route.calls[0].request
    assert req.headers["authorization"] == "Bearer kie-key"
    sent = _json.loads(req.content)
    assert sent["stream"] is False and sent["tools"][0]["name"] == "emit"


def test_kie_error_code_in_a_200_body_is_reported():
    from jobgent.llm import KieLLM

    with respx.mock as m:
        m.post("https://api.kie.ai/claude/v1/messages").mock(return_value=httpx.Response(200, json={"code": 402, "msg": "Insufficient credits"}))
        with pytest.raises(LLMError, match="Insufficient credits"):
            KieLLM(api_key="k").complete_json(model="m", system="s", user="u", schema=Out)
