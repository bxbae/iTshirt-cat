from types import SimpleNamespace

import pytest

from app.copilot.llm.anthropic_provider import AnthropicProvider
from app.copilot.llm.base import LLMError


def reply(text, stop="end_turn", thinking=True):
    blocks = ([SimpleNamespace(type="thinking", thinking="", signature="sig")] if thinking else []) + [SimpleNamespace(type="text", text=text)]
    return SimpleNamespace(content=blocks, stop_reason=stop, usage=SimpleNamespace(input_tokens=100, output_tokens=40))


class FakeMessages:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.replies.pop(0)


def make(replies, effort="low"):
    p = AnthropicProvider.__new__(AnthropicProvider)
    p.model, p.effort, p.usage = "claude-sonnet-5-5", effort, {}
    p._client = SimpleNamespace(messages=FakeMessages(replies))
    return p


def test_request_shape_fits_5_5_models():
    p = make([reply('```json\n{"category": "refund"}\n```')])
    assert p.complete_json("analyze", "SYS", "USER", {}) == {"category": "refund"}
    call = p._client.messages.calls[0]
    assert call["system"] == "SYS" and call["model"] == "claude-sonnet-5-5"
    assert call["messages"] == [{"role": "user", "content": "USER"}]
    assert not {"temperature", "top_p", "top_k", "thinking"} & call.keys()  # 400 on 5.5 models
    assert call["extra_body"] == {"output_config": {"effort": "low"}}
    assert p.usage["analyze"]["calls"] == 1 and p.usage["analyze"]["output_tokens"] == 40


def test_effort_can_be_left_to_model_default():
    p = make([reply('{"ok": 1}')], effort="")
    p.complete_json("summary", "S", "U", {})
    assert p._client.messages.calls[0]["extra_body"] is None


def test_retries_when_reply_is_not_json():
    p = make([reply("Sorry, here you go"), reply('{"ok": true}')])
    assert p.complete_json("summary", "S", "U", {}) == {"ok": True}
    assert "ONLY one valid JSON" in p._client.messages.calls[1]["messages"][0]["content"]


def test_max_tokens_stop_retries_with_bigger_limit():
    p = make([reply("", stop="max_tokens", thinking=True), reply('{"drafts": []}')])
    assert p.complete_json("drafts", "S", "U", {}) == {"drafts": []}
    assert p._client.messages.calls[1]["max_tokens"] == 2 * p._client.messages.calls[0]["max_tokens"]
    assert p.usage["drafts"]["stop_reasons"] == {"max_tokens": 1, "end_turn": 1}


def test_refusal_raises():
    p = make([reply("", stop="refusal")])
    with pytest.raises(LLMError, match="declined"):
        p.complete_json("analyze", "S", "U", {})
