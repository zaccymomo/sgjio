"""The OpenAI-compatible client against a stub transport (no network), and the parsing."""

import json

import httpx
import pytest

from app.config import Settings
from app.llm import (
    BadOutput,
    FakeLLM,
    OpenAICompatibleLLM,
    ProviderError,
    UnconfiguredLLM,
    build_llm,
    extract_json,
    parse_verdict,
)

KEY = "sk-test-not-a-real-key"


def client(handler, check_model="", fallback_model="") -> OpenAICompatibleLLM:
    return OpenAICompatibleLLM(
        "https://llm.example/v1/",
        KEY,
        "write-model",
        check_model,
        timeout=5,
        transport=httpx.MockTransport(handler),
        fallback_model=fallback_model,
    )


def completion(content) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_posts_chat_completions_with_the_key_and_model():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return completion('{"ok": true}')

    llm = client(handler, check_model="check-model")
    messages = [{"role": "user", "content": "hi"}]
    assert llm.write(messages, {}, {}) == '{"ok": true}'
    llm.judge(messages)
    assert str(seen[0].url) == "https://llm.example/v1/chat/completions"
    assert seen[0].headers["authorization"] == f"Bearer {KEY}"
    body = json.loads(seen[0].content)
    assert body["model"] == "write-model"
    assert body["messages"] == messages
    assert body["temperature"] == 0.4
    assert "response_format" not in body
    assert json.loads(seen[1].content)["model"] == "check-model"


def test_a_failing_model_falls_back_once_to_the_fallback_model():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        model = json.loads(req.content)["model"]
        seen.append(model)
        return httpx.Response(503) if model == "write-model" else completion("{}")

    assert client(handler, fallback_model="spare").write([], {}, {}) == "{}"
    assert seen == ["write-model", "spare"]


def test_without_a_fallback_the_provider_error_stands():
    with pytest.raises(ProviderError):
        client(lambda r: httpx.Response(503)).write([], {}, {})


def test_judge_model_defaults_to_the_write_model():
    seen = []
    client(lambda r: seen.append(json.loads(r.content)) or completion("{}")).judge([])
    assert seen[0]["model"] == "write-model"


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(500, text="boom"),
        lambda r: httpx.Response(401, json={"error": "bad key"}),
        lambda r: httpx.Response(200, text="not json"),
        lambda r: httpx.Response(200, json={"choices": []}),
        lambda r: completion(None),
        lambda r: completion("   "),
    ],
)
def test_provider_problems_raise_provider_error(handler):
    with pytest.raises(ProviderError) as caught:
        client(handler).write([], {}, {})
    assert KEY not in str(caught.value)


def test_a_timeout_raises_provider_error():
    def handler(req):
        raise httpx.ReadTimeout("slow", request=req)

    with pytest.raises(ProviderError, match="ReadTimeout"):
        client(handler).write([], {}, {})


def test_extract_json_strips_fences_and_chatter():
    assert extract_json('Here:\n```json\n{"a": {"b": 1}}\n```\nbye') == {"a": {"b": 1}}
    assert extract_json('{broken {"a": 1} {"b": 2}') == {"a": 1}
    with pytest.raises(BadOutput):
        extract_json("no braces here")
    with pytest.raises(BadOutput):
        parse_verdict('{"problems": []}')


def test_extract_json_skips_a_reasoning_models_think_block():
    reply = '<think>Shape is {"ok": false}? No, check again.</think>\n{"ok": true, "problems": []}'
    assert extract_json(reply) == {"ok": True, "problems": []}


def test_build_llm_choices():
    assert isinstance(build_llm(Settings(generation_fake=True)), FakeLLM)
    unconfigured = Settings(generation_fake=False, generation_base_url="", generation_api_key="")
    assert isinstance(build_llm(unconfigured), UnconfiguredLLM)
    real = Settings(
        generation_fake=False,
        generation_base_url="https://llm.example/v1",
        generation_api_key=KEY,
        generation_model="m",
    )
    assert isinstance(build_llm(real), OpenAICompatibleLLM)
