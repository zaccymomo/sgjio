"""The model: one small interface, a fake and an OpenAI-compatible client.

    llm.write(messages, brief, grounding) -> str   the write call: lesson JSON (or a refusal)
    llm.judge(messages) -> str                     the check call: {"ok": bool, "problems": [...]}

Both return the model's raw text; `parse_lesson` and `parse_verdict` turn it into the
pydantic models below (code fences stripped, the first {...} object taken). Anything that
goes wrong talking to the provider (timeout, HTTP error, a reply without content) raises
ProviderError, which the pipeline turns into a `provider` failure.

FakeLLM (GENERATION_FAKE=true, the default) needs no key or network. It ignores the
messages and builds a valid lesson from the brief: the requested number of cards and
questions, using the topic name, the learner's ask, and, for focus = mistakes, the
correct answers of the mistakes. It refuses (as the real model would for an off-topic or
hostile request) when the ask or the notes contain any of REFUSAL_MARKERS, ignoring
case. The end-to-end tests rely on these markers. Its judge always says ok.
"""

import json
import logging
import re
from typing import Protocol

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings

log = logging.getLogger("sgjio.generation")

# FakeLLM refuses a request whose ask or notes contain one of these (case-insensitive).
REFUSAL_MARKERS = ("pr application", "essay", "ignore previous", "ignore all", "password", "hack")

TEMPERATURE = 0.4


class ProviderError(Exception):
    """The model could not be reached or gave no usable reply. Never carries the key."""


# --- What the model returns -----------------------------------------------------------


class OptionOut(BaseModel):
    text: str
    correct: bool
    why_not: str = ""


class QuestionOut(BaseModel):
    explanation: str
    options: list[OptionOut]


class CardOut(BaseModel):
    text: str
    question: QuestionOut | None = None


class Refusal(BaseModel):
    reason: str


class LessonOut(BaseModel):
    refused: Refusal | None = None
    title: str = ""
    summary: str = ""
    learning_points: list[str] = []
    cards: list[CardOut] = []


class Verdict(BaseModel):
    ok: bool
    problems: list[str] = []


class BadOutput(ValueError):
    """The model's text is not JSON in the expected shape."""


def extract_json(text: str) -> dict:
    """The first JSON object in `text`, after stripping a reasoning model's <think> block and
    Markdown code fences."""
    text = re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL)
    text = re.sub(r"```[a-zA-Z]*", "", text)
    start = text.find("{")
    while start != -1:
        try:
            value, _ = json.JSONDecoder().raw_decode(text, start)
        except json.JSONDecodeError:
            start = text.find("{", start + 1)
            continue
        if isinstance(value, dict):
            return value
        start = text.find("{", start + 1)
    raise BadOutput("no JSON object in the reply")


def parse_lesson(text: str) -> LessonOut:
    try:
        return LessonOut.model_validate(extract_json(text))
    except ValidationError as error:
        raise BadOutput(f"not in the lesson shape ({error.error_count()} errors)") from error


def parse_verdict(text: str) -> Verdict:
    try:
        return Verdict.model_validate(extract_json(text))
    except ValidationError as error:
        raise BadOutput("not in the verdict shape") from error


# --- The interface ----------------------------------------------------------------------


class LLM(Protocol):
    def write(self, messages: list[dict], brief: dict, grounding: dict) -> str: ...

    def judge(self, messages: list[dict]) -> str: ...

    def screen(self, messages: list[dict]) -> str: ...


class FakeLLM:
    """Deterministic lessons from the brief, no network. See the module docstring."""

    def write(self, messages: list[dict], brief: dict, grounding: dict) -> str:
        said = " ".join(filter(None, [brief.get("ask"), brief.get("notes")])).lower()
        if any(marker in said for marker in REFUSAL_MARKERS):
            return json.dumps({"refused": {"reason": "Not about everyday life in Singapore."}})
        return json.dumps(fake_lesson(brief, grounding))

    def judge(self, messages: list[dict]) -> str:
        return json.dumps({"ok": True, "problems": []})

    def screen(self, messages: list[dict]) -> str:
        # The fake refuses in write() instead (REFUSAL_MARKERS), as the e2e tests expect.
        return json.dumps({"ok": True, "problems": []})


def _clean(text: str, limit: int) -> str:
    """Learner or grounding text made safe to drop into a fake card: no Markdown or HTML
    syntax, one line, cut to `limit` characters."""
    text = " ".join(re.sub(r"[{}\[\]<>*_`#|]", "", text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def fake_lesson(brief: dict, grounding: dict) -> dict:
    topic = _clean(brief["topic"]["name"], 40)
    ask = _clean(brief.get("ask") or brief.get("notes") or "", 120)
    n_cards, n_questions = brief["cards"], brief["questions"]
    answers = [
        _clean(m["correct"], 100)
        for m in grounding.get("mistakes", [])
        if brief["focus"] == "mistakes" and _clean(m["correct"], 100)
    ]

    cards: list[dict] = []
    first = f"This lesson is about **{topic}** in everyday life in Singapore."
    if ask:
        first += f' You asked about: "{ask}"'
    cards.append({"text": first, "question": None})
    for i in range(1, n_cards - n_questions):
        cards.append(
            {
                "text": f"Idea {i}: many people here keep it short and friendly. "
                f"Watch what others do, then try it yourself.",
                "question": None,
            }
        )
    for q in range(n_questions):
        right = answers[q % len(answers)] if answers else f"A short, friendly reply ({q + 1})"
        cards.append(
            {
                "text": f"Situation {q + 1}: a neighbour starts a chat about {topic}. "
                "The most natural reply is {{blank}}.",
                "question": {
                    "explanation": f"In {topic}, a short and friendly reply fits best.",
                    "options": [
                        {"text": right, "correct": True, "why_not": ""},
                        {
                            "text": "A long, formal speech",
                            "correct": False,
                            "why_not": "Too formal for a quick chat.",
                        },
                        {
                            "text": "Say nothing at all",
                            "correct": False,
                            "why_not": "It can seem unfriendly.",
                        },
                    ],
                },
            }
        )
    return {
        "refused": None,
        "title": f"{topic}: a quick practice",
        "summary": f"A short practice lesson about {topic}.",
        "learning_points": [f"Use {topic} in a short, everyday situation"],
        "cards": cards,
    }


class UnconfiguredLLM:
    """Fake is off but the base URL or key is missing: every call fails as `provider`."""

    def write(self, messages, brief, grounding) -> str:
        raise ProviderError("GENERATION_BASE_URL or GENERATION_API_KEY is not set")

    def judge(self, messages) -> str:
        raise ProviderError("GENERATION_BASE_URL or GENERATION_API_KEY is not set")

    def screen(self, messages) -> str:
        raise ProviderError("GENERATION_BASE_URL or GENERATION_API_KEY is not set")


class OpenAICompatibleLLM:
    """POST {base_url}/chat/completions with a bearer key. Asks for JSON in the prompt
    only; no response_format, so it works with any OpenAI-compatible provider."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        check_model: str = "",
        timeout: float = 60.0,
        transport: httpx.BaseTransport | None = None,
        fallback_model: str = "",
    ):
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model = model
        self.check_model = check_model or model
        # Tried once when a call to the main model fails (down, withdrawn, timed out), so a
        # trial model disappearing doesn't stop lessons being made.
        self.fallback_model = fallback_model
        self.client = httpx.Client(
            headers={"Authorization": f"Bearer {api_key}"}, timeout=timeout, transport=transport
        )

    def _chat(self, model: str, messages: list[dict]) -> str:
        try:
            response = self.client.post(
                self.url,
                json={"model": model, "messages": messages, "temperature": TEMPERATURE},
            )
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as error:
            raise ProviderError(f"HTTP {error.response.status_code} from the model") from error
        except httpx.HTTPError as error:
            raise ProviderError(f"{type(error).__name__} calling the model") from error
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise ProviderError("the model's reply was not a chat completion") from error
        if not isinstance(content, str) or not content.strip():
            raise ProviderError("the model's reply was empty")
        log.debug("model reply: %s", content)
        return content

    def _chat_or_fallback(self, model: str, messages: list[dict]) -> str:
        try:
            return self._chat(model, messages)
        except ProviderError as error:
            if not self.fallback_model or self.fallback_model == model:
                raise
            log.warning("model %s failed (%s); trying %s", model, error, self.fallback_model)
            return self._chat(self.fallback_model, messages)

    def write(self, messages: list[dict], brief: dict, grounding: dict) -> str:
        return self._chat_or_fallback(self.model, messages)

    def judge(self, messages: list[dict]) -> str:
        return self._chat_or_fallback(self.check_model, messages)

    def screen(self, messages: list[dict]) -> str:
        # The check model screens the learner's text: it follows refusal rules more reliably
        # than a fast writer (docs/ai-model-evaluation.md).
        return self._chat_or_fallback(self.check_model, messages)


def build_llm(settings: Settings) -> LLM:
    if settings.generation_fake:
        return FakeLLM()
    if not settings.generation_base_url or not settings.generation_api_key:
        log.warning(
            "GENERATION_FAKE is false but GENERATION_BASE_URL or GENERATION_API_KEY is not "
            "set: every request will fail with code 'provider'"
        )
        return UnconfiguredLLM()
    return OpenAICompatibleLLM(
        settings.generation_base_url,
        settings.generation_api_key,
        settings.generation_model,
        settings.generation_check_model,
        settings.generation_timeout_seconds,
        fallback_model=settings.generation_fallback_model,
    )
