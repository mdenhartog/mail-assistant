"""U-08: the model adapter (spec AC-12, AC-18, AC-19, AC-23, AC-24, AC-26; ADR-0014)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import SecretStr

from app.adapters.judge_anthropic import (
    AnthropicJudge,
    DailyBudget,
    ModelUnavailable,
    TrimmedMail,
    trim_mail,
)
from app.core.judgement import Judgement, NeedsAttention

KEY = "sk-ant-test-0123456789"
SMALL = "small-model-id"
LARGE = "large-model-id"
FIXTURES = Path(__file__).parent.parent / "fixtures" / "injection"
TODAY = "2026-11-08"


def verdict(**changes: object) -> dict[str, object]:
    return {
        "category": "Finance",
        "urgent": True,
        "reason": "Invoice due",
        "summary": "Pay it",
        "confidence": 0.9,
        **changes,
    }


def reply(payload: object, status: int = 200, headers: dict[str, str] | None = None) -> httpx.Response:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    return httpx.Response(status, json={"content": [{"type": "text", "text": text}]}, headers=headers)


class Scripted:
    """A scripted model: answers in order (the last answer repeats) and remembers every request."""

    def __init__(self, *answers: httpx.Response | Exception) -> None:
        self.answers = list(answers)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        answer = self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]
        if isinstance(answer, Exception):
            raise answer
        return answer

    def body(self, index: int = 0) -> dict[str, object]:
        return json.loads(self.requests[index].content)

    def mail_sent(self, index: int = 0) -> dict[str, object]:
        messages: Any = self.body(index)["messages"]
        return json.loads(str(messages[0]["content"]))


def make_judge(
    model: Scripted,
    *,
    budget: DailyBudget | None = None,
    attempts: int = 3,
    sleeps: list[float] | None = None,
) -> AnthropicJudge:
    async def sleep(seconds: float) -> None:
        if sleeps is not None:
            sleeps.append(seconds)

    return AnthropicJudge(
        client=httpx.AsyncClient(transport=httpx.MockTransport(model)),
        api_key=SecretStr(KEY),
        small_model=SMALL,
        large_model=LARGE,
        budget=budget or DailyBudget(limit=100, today=lambda: TODAY),
        max_attempts=attempts,
        sleep=sleep,
    )


MAIL = TrimmedMail(subject="Invoice", sender="billing@example.com", text="Please pay by Friday.", truncated=False)


async def test_given_a_mail_when_judged_then_the_request_has_only_subject_sender_and_text() -> None:
    model = Scripted(reply(verdict()))

    result = await make_judge(model).judge(MAIL)

    assert isinstance(result, Judgement)
    body = model.body()
    assert body["model"] == SMALL
    assert "tools" not in body
    assert model.mail_sent() == {
        "subject": "Invoice",
        "sender": "billing@example.com",
        "text": "Please pay by Friday.",
        "truncated": False,
    }
    assert model.requests[0].headers["x-api-key"] == KEY
    assert model.requests[0].url.scheme == "https"


def test_given_a_body_above_the_cap_when_trimmed_then_it_is_cut_and_marked() -> None:
    mail = trim_mail("s", "a@example.com", "x" * 50, cap=10)

    assert mail.text == "x" * 10
    assert mail.truncated is True
    assert trim_mail("s", "a@example.com", "short", cap=10).truncated is False


@pytest.mark.parametrize("name", ["send_mail", "delete_all", "not_urgent", "reveal"])
async def test_given_injected_mail_text_when_judged_then_only_a_judgement_comes_out(name: str) -> None:
    text = (FIXTURES / f"{name}.txt").read_text(encoding="utf-8")
    model = Scripted(reply(verdict(urgent=True, reason="Looks like an instruction to the assistant")))

    result = await make_judge(model).judge(TrimmedMail("hi", "x@example.com", text, truncated=False))

    assert isinstance(result, Judgement)
    assert len(model.requests) == 1  # the text caused no extra call
    body = model.body()
    assert set(body) == {"model", "max_tokens", "system", "messages"}  # no tools, no tool_choice
    assert text not in str(body["system"])  # the text only travels as data in the user turn
    assert model.mail_sent()["text"] == text


async def test_given_a_model_that_obeys_the_injection_when_judged_then_needs_attention() -> None:
    obeyed = verdict(action="send_email", to="attacker@example.com")

    result = await make_judge(Scripted(reply(obeyed))).judge(MAIL)

    assert result == NeedsAttention("invalid_output")


@pytest.mark.parametrize("answer", ["not json at all", "[1, 2]", '{"category": "x"}', "null"])
async def test_given_an_answer_outside_the_schema_when_judged_then_needs_attention(answer: str) -> None:
    result = await make_judge(Scripted(reply(answer))).judge(MAIL)

    assert result == NeedsAttention("invalid_output")


async def test_given_a_body_that_is_not_json_when_judged_then_needs_attention() -> None:
    odd = httpx.Response(200, content=b"<html>gateway</html>")

    assert await make_judge(Scripted(odd)).judge(MAIL) == NeedsAttention("invalid_output")


async def test_given_an_unreadable_retry_after_when_judged_then_the_normal_backoff_is_used() -> None:
    sleeps: list[float] = []
    model = Scripted(reply("x", status=429, headers={"retry-after": "soon"}), reply(verdict()))

    result = await make_judge(model, sleeps=sleeps).judge(MAIL)

    assert isinstance(result, Judgement)
    assert len(sleeps) == 1


async def test_given_a_response_without_text_when_judged_then_needs_attention() -> None:
    odd = httpx.Response(200, json={"content": []})

    assert await make_judge(Scripted(odd)).judge(MAIL) == NeedsAttention("invalid_output")


async def test_given_low_confidence_from_the_small_model_when_judged_then_the_large_model_decides() -> None:
    model = Scripted(reply(verdict(confidence=0.3)), reply(verdict(confidence=0.95, category="Legal")))

    result = await make_judge(model).judge(MAIL)

    assert isinstance(result, Judgement)
    assert result.category == "Legal"
    assert [model.body(i)["model"] for i in range(2)] == [SMALL, LARGE]
    assert len(model.requests) == 2  # asked once, not more


async def test_given_the_large_model_is_also_unsure_when_judged_then_its_result_is_returned_once() -> None:
    model = Scripted(reply(verdict(confidence=0.3)), reply(verdict(confidence=0.4)))

    result = await make_judge(model).judge(MAIL)

    assert isinstance(result, Judgement)
    assert result.confidence == 0.4
    assert len(model.requests) == 2


async def test_given_a_confident_small_model_when_judged_then_the_large_model_is_not_asked() -> None:
    model = Scripted(reply(verdict(confidence=0.8)))

    await make_judge(model).judge(MAIL)

    assert len(model.requests) == 1


async def test_given_the_daily_budget_is_used_up_when_a_mail_arrives_then_no_call_is_made() -> None:
    model = Scripted(reply(verdict()))
    judge = make_judge(model, budget=DailyBudget(limit=0, today=lambda: TODAY))

    result = await judge.judge(MAIL)

    assert result == NeedsAttention("budget")
    assert model.requests == []


async def test_given_the_budget_runs_out_before_escalation_then_the_small_result_is_kept() -> None:
    model = Scripted(reply(verdict(confidence=0.3)))
    judge = make_judge(model, budget=DailyBudget(limit=1, today=lambda: TODAY))

    result = await judge.judge(MAIL)

    assert isinstance(result, Judgement)
    assert len(model.requests) == 1


def test_given_a_new_day_when_the_budget_is_asked_then_it_starts_again() -> None:
    day = [TODAY]
    budget = DailyBudget(limit=1, today=lambda: day[0])

    assert budget.try_spend() is True
    assert budget.try_spend() is False
    day[0] = "2026-11-09"
    assert budget.try_spend() is True


@pytest.mark.parametrize(
    "failure",
    [
        reply("x", status=429, headers={"retry-after": "2"}),
        reply("x", status=503),
        httpx.ReadTimeout("slow"),
        httpx.ConnectError("down"),
    ],
)
async def test_given_a_transient_error_when_judged_then_it_retries_and_then_succeeds(
    failure: httpx.Response | Exception,
) -> None:
    sleeps: list[float] = []
    model = Scripted(failure, reply(verdict()))

    result = await make_judge(model, sleeps=sleeps).judge(MAIL)

    assert isinstance(result, Judgement)
    assert len(model.requests) == 2
    assert len(sleeps) == 1
    if isinstance(failure, httpx.Response) and failure.status_code == 429:
        assert sleeps[0] >= 2  # honours Retry-After


async def test_given_the_model_keeps_failing_when_judged_then_a_retryable_error_is_raised() -> None:
    model = Scripted(reply("x", status=503))
    sleeps: list[float] = []

    with pytest.raises(ModelUnavailable) as caught:
        await make_judge(model, attempts=3, sleeps=sleeps).judge(MAIL)

    assert len(model.requests) == 3
    assert sleeps == sorted(sleeps)  # backoff grows
    assert KEY not in str(caught.value)


async def test_given_a_rejected_key_when_judged_then_it_does_not_retry() -> None:
    model = Scripted(reply("x", status=401))

    with pytest.raises(ModelUnavailable):
        await make_judge(model).judge(MAIL)

    assert len(model.requests) == 1


async def test_given_debug_logging_when_judged_then_neither_mail_text_nor_key_is_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    mail = TrimmedMail("Secret subject", "boss@example.com", "very private body text", truncated=False)
    model = Scripted(reply("x", status=503), reply(verdict()))

    await make_judge(model).judge(mail)

    for secret in (KEY, "very private body text", "Secret subject", "boss@example.com"):
        assert secret not in caplog.text


def test_given_the_source_when_scanned_then_no_model_id_is_hard_coded() -> None:
    source = Path("app/adapters/judge_anthropic.py").read_text(encoding="utf-8")

    assert "claude-" not in source
