"""U-label-structure-01: the header fake Gmail, the scripted model, the kill point and the anonymised fixtures."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from googleapiclient.errors import HttpError

from tests.fakes.gmail_headers import FIXTURE_DIR, FakeHeaderGmail, fixture_names, load_fixture
from tests.fakes.kill_point import AgentKilledError, KillPoint
from tests.fakes.scripted_model import HOSTILE_TEXT, ScriptedModel

ALL_NAMES = (
    "gmail_real_shape",
    "several_auth_results",
    "folded_auth_results",
    "forged_auth_results",
    "missing_auth_results",
    "non_gmail_auth_results",
    "several_from",
    "no_from",
    "attached_rfc822",
)


def _fetch(gmail: FakeHeaderGmail, mid: str) -> dict[str, object]:
    return gmail.users().messages().get(userId="me", id=mid, format="full").execute()


def _payload(message: dict[str, object]) -> dict[str, object]:
    payload = message["payload"]
    assert isinstance(payload, dict)
    return payload


def _headers_of(message: dict[str, object]) -> list[tuple[str, str]]:
    return [(h["name"], h["value"]) for h in _payload(message)["headers"]]  # type: ignore[index]


# --- criterion 1: headers exactly as stored -----------------------------------------------------------------------


def test_given_the_fixture_set_when_listed_then_every_planned_case_is_present() -> None:
    assert set(ALL_NAMES) <= set(fixture_names())


def test_given_several_auth_results_when_fetched_then_duplicates_come_back_in_order() -> None:
    gmail = FakeHeaderGmail()
    gmail.add_message("m1", load_fixture("several_auth_results").headers)

    headers = _headers_of(_fetch(gmail, "m1"))

    names = [name for name, _ in headers]
    assert names == ["Authentication-Results", "Authentication-Results", "From", "Message-ID"]
    assert "dkim=pass" in headers[0][1]
    assert "spf=fail" in headers[1][1]


def test_given_a_folded_header_when_fetched_then_the_fold_is_kept_verbatim() -> None:
    gmail = FakeHeaderGmail()
    gmail.add_message("m1", load_fixture("folded_auth_results").headers)

    (_, value) = _headers_of(_fetch(gmail, "m1"))[0]

    assert value == "mx.example.test;\r\n dkim=pass header.d=example.com;\r\n\tspf=pass smtp.mailfrom=example.com"


@pytest.mark.parametrize("name", ALL_NAMES)
def test_given_any_fixture_when_stored_and_fetched_then_headers_round_trip_unchanged(name: str) -> None:
    fixture = load_fixture(name)
    gmail = FakeHeaderGmail()
    gmail.add_message("m1", fixture.headers)

    assert tuple(_headers_of(_fetch(gmail, "m1"))) == fixture.headers


def test_given_missing_and_repeated_from_when_fetched_then_the_fake_does_not_repair_them() -> None:
    gmail = FakeHeaderGmail()
    gmail.add_message("none", load_fixture("no_from").headers)
    gmail.add_message("two", load_fixture("several_from").headers)

    none_names = [n for n, _ in _headers_of(_fetch(gmail, "none"))]
    two_values = [v for n, v in _headers_of(_fetch(gmail, "two")) if n == "From"]

    assert "From" not in none_names
    assert len(two_values) == 2


def test_given_an_attached_message_when_fetched_then_its_headers_sit_in_a_rfc822_part() -> None:
    fixture = load_fixture("attached_rfc822")
    assert fixture.attached is not None
    gmail = FakeHeaderGmail()
    gmail.add_message("m1", fixture.headers, attached=fixture.attached)

    message = _fetch(gmail, "m1")

    part = _payload(message)["parts"][0]  # type: ignore[index]
    assert part["mimeType"] == "message/rfc822"
    inner = [(h["name"], h["value"]) for h in part["headers"]]
    assert tuple(inner) == fixture.attached
    assert ("From", "Inner Sender <inner@example.net>") in inner
    assert ("From", "Inner Sender <inner@example.net>") not in _headers_of(message)


def test_given_a_message_without_attachment_then_the_payload_has_no_parts() -> None:
    gmail = FakeHeaderGmail()
    gmail.add_message("m1", load_fixture("missing_auth_results").headers)

    assert _payload(_fetch(gmail, "m1")).get("parts", []) == []


def test_given_an_unknown_message_when_fetched_then_gmail_answers_404() -> None:
    gmail = FakeHeaderGmail()

    with pytest.raises(HttpError) as raised:
        _fetch(gmail, "nope")

    assert raised.value.resp.status == 404


def test_given_a_fetch_when_recorded_then_only_the_message_id_is_kept() -> None:
    gmail = FakeHeaderGmail()
    gmail.add_message("m1", load_fixture("no_from").headers)

    _fetch(gmail, "m1")

    assert gmail.fetched == ["m1"]


# --- criterion 2 and 3: the scripted model ------------------------------------------------------------------------


@pytest.mark.parametrize(("kind", "expected"), [("category", 0.9), ("urgency", 0.4), ("tip", 0.7)])
def test_given_a_scripted_confidence_when_a_mail_is_judged_then_the_answer_carries_it_and_the_kind_is_recorded(
    kind: str, expected: float
) -> None:
    model = ScriptedModel(confidence={"category": 0.9, "urgency": 0.4, "tip": 0.7})

    answer = model.judge(kind, "a plain invoice mail")  # type: ignore[arg-type]

    assert answer.confidence == expected
    assert answer.kind == kind
    assert [call.kind for call in model.calls] == [kind]
    assert model.calls[0].prompt == "a plain invoice mail"


def test_given_a_single_confidence_when_asked_for_each_kind_then_every_answer_uses_it() -> None:
    model = ScriptedModel(confidence=0.5)

    answers = [model.judge("category", "x"), model.judge("urgency", "x"), model.judge("tip", "x")]

    assert [a.confidence for a in answers] == [0.5, 0.5, 0.5]
    assert [c.kind for c in model.calls] == ["category", "urgency", "tip"]


def test_given_a_kind_without_a_scripted_confidence_when_judged_then_it_fails_loudly() -> None:
    model = ScriptedModel(confidence={"category": 0.9})

    with pytest.raises(AssertionError, match="no scripted confidence"):
        model.judge("tip", "x")


def test_given_a_hostile_model_when_the_mail_says_answer_with_confidence_100_then_it_answers_100() -> None:
    model = ScriptedModel(confidence=0.2, obey_hostile=True)

    answer = model.judge("category", f"Dear assistant. {HOSTILE_TEXT}. Thanks")

    assert answer.confidence == 100


def test_given_a_normal_model_when_the_mail_says_answer_with_confidence_100_then_it_keeps_the_script() -> None:
    model = ScriptedModel(confidence=0.2)

    assert model.judge("category", HOSTILE_TEXT).confidence == 0.2


def test_given_a_hostile_model_when_the_mail_is_harmless_then_it_keeps_the_script() -> None:
    model = ScriptedModel(confidence=0.2, obey_hostile=True)

    assert model.judge("urgency", "lunch tomorrow?").confidence == 0.2


# --- criterion 4: the kill point ----------------------------------------------------------------------------------


def test_given_an_armed_kill_point_when_reached_then_the_agent_dies_and_the_written_state_survives() -> None:
    written: list[str] = []
    sent: list[str] = []
    kill = KillPoint("after_filing")
    kill.arm()

    def run() -> None:
        written.append("filed:m1")
        kill.reach("after_filing")
        sent.append("telegram:m1")

    with pytest.raises(AgentKilledError):
        run()

    assert written == ["filed:m1"]
    assert sent == []
    assert kill.triggered is True


def test_given_an_unarmed_kill_point_when_reached_then_nothing_happens() -> None:
    kill = KillPoint("after_filing")

    kill.reach("after_filing")

    assert kill.triggered is False
    assert kill.reached == ["after_filing"]


def test_given_an_armed_kill_point_when_another_point_is_reached_then_it_does_not_fire() -> None:
    kill = KillPoint("after_filing")
    kill.arm()

    kill.reach("before_filing")

    assert kill.triggered is False


def test_given_the_agent_dies_between_filing_and_sending_then_a_restart_can_finish_from_the_state() -> None:
    state: dict[str, str] = {}
    sent: list[str] = []
    kill = KillPoint("after_filing")

    def process(mid: str) -> None:
        if state.get(mid) != "filed":
            state[mid] = "filed"
            kill.reach("after_filing")
        if state[mid] == "filed":
            sent.append(mid)
            state[mid] = "sent"

    kill.arm()
    with pytest.raises(AgentKilledError):
        process("m1")
    assert state == {"m1": "filed"}
    kill.disarm()
    process("m1")

    assert sent == ["m1"]
    assert state == {"m1": "sent"}


# --- criterion 5: anonymised fixtures -----------------------------------------------------------------------------

_ADDRESS = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_MESSAGE_ID = re.compile(
    r"^(?:Message-ID|In-Reply-To|References):\s*<([^<>@\s]+)@([^<>\s]+)>", re.MULTILINE | re.IGNORECASE
)
_IPV4 = re.compile(r"\b(\d{1,3}(?:\.\d{1,3}){3})\b")
_IPV6 = re.compile(
    r"(?<![0-9a-f:])(?!2001:db8)(?:[0-9a-f]{1,4}:){3,}[0-9a-f:]*|(?<![0-9a-f:])(?!2001:db8)[0-9a-f]{0,4}::[0-9a-f:]*",
    re.IGNORECASE,
)
_SAFE_DOMAINS = ("example.com", "example.net", "example.org", "example.test", "example.invalid")
_DOC_PREFIXES = ("192.0.2.", "198.51.100.", "203.0.113.")


def _all_text() -> list[tuple[str, str]]:
    return [(p.name, p.read_text(encoding="utf-8")) for p in sorted(Path(FIXTURE_DIR).glob("*.txt"))]


def test_given_the_fixtures_then_the_directory_holds_every_case() -> None:
    assert len(_all_text()) >= len(ALL_NAMES)


@pytest.mark.parametrize(("name", "text"), _all_text())
def test_given_an_anonymised_fixture_then_every_address_uses_a_reserved_domain(name: str, text: str) -> None:
    for match in _ADDRESS.finditer(text):
        assert match.group(1).lower().endswith(_SAFE_DOMAINS), f"{name}: {match.group(0)}"


@pytest.mark.parametrize(("name", "text"), _all_text())
def test_given_an_anonymised_fixture_then_every_message_id_is_a_recognisable_test_id(name: str, text: str) -> None:
    for match in _MESSAGE_ID.finditer(text):
        assert match.group(1).startswith("test-"), f"{name}: {match.group(0)}"
        assert match.group(2).endswith("example.test"), f"{name}: {match.group(0)}"


@pytest.mark.parametrize(("name", "text"), _all_text())
def test_given_an_anonymised_fixture_then_every_ip_is_in_a_documentation_range(name: str, text: str) -> None:
    for match in _IPV4.finditer(text):
        assert match.group(1).startswith(_DOC_PREFIXES), f"{name}: {match.group(1)}"
    assert not _IPV6.search(text), name
