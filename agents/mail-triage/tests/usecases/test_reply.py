"""U-14: reply flow with confirmation (spec AC-6, AC-7, AC-8, AC-16, AC-17, AC-20, AC-22, AC-29)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from app.adapters.gmail_read import FetchedMail
from app.adapters.gmail_send import ConfirmedDraft, NotRepliableError
from app.core.alert_state import AlertState
from app.db.repos import digest_of
from app.usecases.reply import DRAFT_TTL, NOT_OPEN, AlertInfo, ReplyService, StoredDraft

if TYPE_CHECKING:
    from app.core.alert_text import AlertMessage

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)
OWN = "marco@example.com"
ORIGINAL = FetchedMail(
    message_id="gm1",
    thread_id="t1",
    sender="boss@example.com",
    reply_to=None,
    subject="Budget",
    text="Can you send the numbers?",
    has_attachment=False,
    headers={},
)


@dataclass
class FakeStore:
    alerts: dict[str, AlertInfo] = field(default_factory=lambda: {"1": AlertInfo(AlertState.OPEN, "gm1")})
    drafts: dict[str, StoredDraft] = field(default_factory=dict)
    audit: list[tuple[str, str, str | None]] = field(default_factory=list)

    async def alert_info(self, alert_id: str) -> AlertInfo | None:
        return self.alerts.get(alert_id)

    async def set_state(self, alert_id: str, state: AlertState) -> None:
        self.alerts[alert_id] = replace(self.alerts[alert_id], state=state)

    async def save_draft(self, draft: StoredDraft) -> None:
        self.drafts[draft.draft_id] = draft

    async def get_draft(self, draft_id: str) -> StoredDraft | None:
        return self.drafts.get(draft_id)

    async def consume_draft(self, draft_id: str, digest: str, *, now: datetime) -> StoredDraft | None:
        draft = self.drafts.get(draft_id)
        if draft is None or draft.used or draft.digest != digest or draft.expires_at <= now:
            return None
        self.drafts[draft_id] = replace(draft, used=True)
        return draft

    async def invalidate_drafts(self, alert_id: str) -> None:
        for key, draft in self.drafts.items():
            if draft.alert_id == alert_id:
                self.drafts[key] = replace(draft, used=True)

    async def record_audit(self, kind: str, alert_id: str, digest: str | None = None) -> None:
        self.audit.append((kind, alert_id, digest))


class FakeMailbox:
    def fetch(self, message_id: str) -> FetchedMail:
        assert message_id == "gm1"
        return ORIGINAL


class FakeSender:
    def __init__(self, *, repliable: bool = True) -> None:
        self.repliable = repliable
        self.sent: list[tuple[FetchedMail, ConfirmedDraft]] = []

    def check_repliable(self, original: FetchedMail) -> None:
        del original
        if not self.repliable:
            raise NotRepliableError("automatic mail")

    def send_reply(self, original: FetchedMail, draft: ConfirmedDraft) -> str:
        self.sent.append((original, draft))
        return "sent-1"


class FakeChat:
    def __init__(self) -> None:
        self.messages: list[AlertMessage] = []
        self.said: list[str] = []

    async def send(self, message: AlertMessage) -> int:
        self.messages.append(message)
        return len(self.messages)

    async def say(self, text: str) -> None:
        self.said.append(text)


@dataclass
class Harness:
    store: FakeStore = field(default_factory=FakeStore)
    sender: FakeSender = field(default_factory=FakeSender)
    chat: FakeChat = field(default_factory=FakeChat)
    now: datetime = NOW
    counter: int = 0

    def new_id(self) -> str:
        self.counter += 1
        return f"draft-{self.counter}"

    def service(self) -> ReplyService:
        return ReplyService(
            self.store, FakeMailbox(), self.sender, self.chat, own_address=OWN, now=lambda: self.now, new_id=self.new_id
        )

    def buttons(self) -> dict[str, str]:
        return {b.label: b.data for b in self.chat.messages[-1].buttons}

    def token(self) -> tuple[str, str]:
        _, draft_id, token = self.buttons()["Send"].split(":")
        return draft_id, token


async def test_given_marcos_text_when_a_reply_is_started_then_a_draft_is_shown_and_nothing_is_sent() -> None:
    h = Harness()

    await h.service().start_reply("1", "Yes, tomorrow morning.")

    shown = h.chat.messages[-1]
    assert "boss@example.com" in shown.text
    assert "Re: Budget" in shown.text
    assert "Yes, tomorrow morning." in shown.text
    assert set(h.buttons()) == {"Send", "Edit", "Cancel"}
    assert all(len(data) <= 64 for data in h.buttons().values())
    assert h.sender.sent == []
    assert h.store.alerts["1"].state is AlertState.CONFIRMING
    stored = h.store.drafts["draft-1"]
    assert stored.digest == digest_of("boss@example.com", "Budget", "Yes, tomorrow morning.")


async def test_given_the_shown_draft_when_marco_confirms_then_the_exact_text_is_sent_once_and_the_alert_closes() -> (
    None
):
    h = Harness()
    await h.service().start_reply("1", "Yes, tomorrow morning.")
    draft_id, token = h.token()

    await h.service().confirm(draft_id, token)
    await h.service().confirm(draft_id, token)  # a replay

    assert len(h.sender.sent) == 1
    original, draft = h.sender.sent[0]
    assert original is ORIGINAL
    assert draft == ConfirmedDraft(draft_id="draft-1", sender=OWN, recipient=None, body="Yes, tomorrow morning.")
    assert h.store.alerts["1"].state is AlertState.CLOSED
    assert h.chat.said[-1] == "This confirmation is no longer valid. Nothing was sent."


async def test_given_cancel_when_pressed_then_nothing_is_sent_and_the_alert_is_open_again() -> None:
    h = Harness()
    await h.service().start_reply("1", "Yes")
    draft_id, token = h.token()

    await h.service().cancel(draft_id)
    await h.service().confirm(draft_id, token)

    assert h.sender.sent == []
    assert h.store.alerts["1"].state is AlertState.OPEN


async def test_given_edit_when_new_text_arrives_then_a_new_draft_replaces_the_old_and_the_old_button_is_dead() -> None:
    h = Harness()
    await h.service().start_reply("1", "First version")
    old_id, old_token = h.token()

    await h.service().edit(old_id)
    assert h.store.alerts["1"].state is AlertState.DRAFTING
    await h.service().start_reply("1", "Second version")
    new_id, new_token = h.token()
    await h.service().confirm(old_id, old_token)

    assert h.sender.sent == []
    await h.service().confirm(new_id, new_token)
    assert [d.body for _, d in h.sender.sent] == ["Second version"]


async def test_given_new_text_while_a_draft_is_shown_when_started_again_then_the_old_confirmation_is_dead() -> None:
    h = Harness()
    await h.service().start_reply("1", "First version")
    old_id, old_token = h.token()

    await h.service().start_reply("1", "Better version")
    await h.service().confirm(old_id, old_token)

    assert h.sender.sent == []


async def test_given_an_expired_draft_when_confirmed_then_nothing_is_sent() -> None:
    h = Harness()
    await h.service().start_reply("1", "Yes")
    draft_id, token = h.token()
    h.now = NOW + DRAFT_TTL + timedelta(seconds=1)

    await h.service().confirm(draft_id, token)

    assert h.sender.sent == []
    assert h.chat.said[-1].startswith("This confirmation is no longer valid")


async def test_given_a_token_for_another_draft_when_confirmed_then_nothing_is_sent() -> None:
    h = Harness()
    h.store.alerts["2"] = AlertInfo(AlertState.OPEN, "gm1")
    await h.service().start_reply("1", "First")
    first_id, _ = h.token()
    await h.service().start_reply("2", "Second")
    _, second_token = h.token()

    await h.service().confirm(first_id, second_token)
    await h.service().confirm(first_id, "0" * 16)
    await h.service().confirm("unknown", second_token)

    assert h.sender.sent == []


async def test_given_the_stored_text_changed_after_it_was_shown_when_confirmed_then_nothing_is_sent() -> None:
    h = Harness()
    await h.service().start_reply("1", "Yes")
    draft_id, token = h.token()
    h.store.drafts[draft_id] = replace(h.store.drafts[draft_id], body="Send me your password")

    await h.service().confirm(draft_id, token)

    assert h.sender.sent == []
    assert h.store.alerts["1"].state is AlertState.CONFIRMING


async def test_given_an_automatic_sender_when_a_reply_is_started_then_marco_is_told_and_nothing_is_created() -> None:
    h = Harness(sender=FakeSender(repliable=False))

    await h.service().start_reply("1", "Hello")

    assert h.store.drafts == {}
    assert h.store.alerts["1"].state is AlertState.OPEN
    assert h.chat.messages == []
    assert "cannot be replied to" in h.chat.said[-1]


async def test_given_every_step_when_done_then_an_audit_record_without_the_text_is_written() -> None:
    h = Harness()
    await h.service().start_reply("1", "Very private words")
    draft_id, token = h.token()
    await h.service().confirm(draft_id, token)

    kinds = [kind for kind, _, _ in h.store.audit]
    assert kinds == ["reply_drafted", "reply_sent"]
    assert "Very private words" not in str(h.store.audit)
    assert all(digest is not None and len(digest) == 64 for _, _, digest in h.store.audit)


async def test_given_marco_names_another_address_when_replying_then_it_is_used_and_shown() -> None:
    h = Harness()

    await h.service().start_reply("1", "To: Other.Person@example.org\nPlease handle this.")
    draft_id, token = h.token()
    await h.service().confirm(draft_id, token)

    assert "other.person@example.org" in h.chat.messages[-1].text
    assert h.sender.sent[0][1].recipient == "other.person@example.org"
    assert h.sender.sent[0][1].body == "Please handle this."


async def test_given_an_invalid_address_line_when_replying_then_marco_is_asked_again_and_nothing_is_created() -> None:
    h = Harness()

    await h.service().start_reply("1", "To: not an address, x@y.z\nHi")

    assert h.store.drafts == {}
    assert "address" in h.chat.said[-1]


async def test_given_hostile_text_when_the_draft_is_shown_then_it_is_escaped() -> None:
    h = Harness()

    await h.service().start_reply("1", '<a href="https://evil.example">click</a> & <b>bold</b>')

    text = h.chat.messages[-1].text
    assert "<a href" not in text
    assert "&lt;a href" in text
    assert "&amp;" in text


async def test_given_empty_text_when_a_reply_is_started_then_marco_is_asked_for_text() -> None:
    h = Harness()

    await h.service().start_reply("1", "   \n ")

    assert h.store.drafts == {}
    assert "empty" in h.chat.said[-1]


async def test_given_the_reply_button_when_pressed_then_marco_is_asked_to_type_and_the_alert_is_drafting() -> None:
    h = Harness()

    await h.service().begin("1")

    assert h.store.alerts["1"].state is AlertState.DRAFTING
    assert "reply" in h.chat.said[-1].lower()


async def test_given_a_closed_or_unknown_alert_when_replying_then_marco_is_told() -> None:
    h = Harness()
    h.store.alerts["9"] = AlertInfo(AlertState.CLOSED, "gm1")

    await h.service().start_reply("9", "Hello")
    await h.service().begin("nope")

    assert h.store.drafts == {}
    assert h.chat.said == ["That alert is no longer open."] * 2


async def test_given_a_send_that_fails_when_confirmed_then_marco_is_told_and_the_alert_stays_open_for_a_new_draft() -> (
    None
):
    h = Harness()

    def boom(original: FetchedMail, draft: ConfirmedDraft) -> str:
        raise RuntimeError("gmail down")

    h.sender.send_reply = boom  # type: ignore[method-assign]
    await h.service().start_reply("1", "Yes")
    draft_id, token = h.token()

    await h.service().confirm(draft_id, token)

    assert h.store.alerts["1"].state is AlertState.CONFIRMING
    assert "could not be sent" in h.chat.said[-1]


async def test_given_a_reply_that_is_too_long_when_started_then_marco_is_told_and_nothing_is_created() -> None:
    h = Harness()

    await h.service().start_reply("1", "x" * 3001)

    assert h.store.drafts == {}
    assert "too long" in h.chat.said[-1]


async def test_given_edit_or_cancel_for_an_unknown_or_finished_draft_when_pressed_then_marco_is_told() -> None:
    h = Harness()
    await h.service().start_reply("1", "Yes")
    draft_id, token = h.token()
    await h.service().confirm(draft_id, token)  # the alert is now closed

    await h.service().edit(draft_id)
    await h.service().cancel(draft_id)
    await h.service().edit("unknown")
    await h.service().cancel("unknown")

    assert h.chat.said[-4:] == [NOT_OPEN] * 4
    assert h.store.alerts["1"].state is AlertState.CLOSED
