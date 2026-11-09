"""Compose the agent: build every part from the settings and hand back a ``Runner``.

``build_runner`` takes what touches the outside world (database sessions, one shared HTTP client, the Gmail ports) as
arguments, so the whole agent can be run against fakes. ``serve`` supplies the real ones and holds the single-replica
lock for as long as the agent runs.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.adapters.gmail_read import GmailReader
from app.adapters.gmail_send import GmailSender
from app.adapters.judge_anthropic import AnthropicJudge, DailyBudget
from app.adapters.telegram_inbox import TelegramInbox
from app.adapters.telegram_outbox import TelegramOutbox
from app.adapters.token_store import TokenCipher, TokenStore
from app.db import repos
from app.db.migrate import upgrade
from app.db.pg_conversation import ConversationStore
from app.db.pg_store import PgStore
from app.runner import FailureNotice, Runner
from app.usecases.catchup import CatchUp
from app.usecases.deliver_alerts import AlertDelivery
from app.usecases.dispatch import CommandRouter
from app.usecases.overview import OverviewService
from app.usecases.reply import ReplyService
from app.usecases.snooze import SnoozeService
from app.usecases.triage import TriagePipeline
from schedule_policy.policy import DEFAULT_POLICY

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncSession

    from app.adapters.gmail_read import FetchedMail
    from app.adapters.gmail_send import ConfirmedDraft
    from app.settings import Settings

logger = logging.getLogger(__name__)

HEARTBEAT = Path("/tmp/heartbeat")  # noqa: S108  # nosec B108 - the container's own tmpfs; the probe reads it
GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"  # noqa: S105  # nosec B105 - a public endpoint
GMAIL_SCOPES = (
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
)
EXIT_OK = 0
EXIT_NO_CONSENT = 3
EXIT_LOCKED = 4


class MailPorts:
    """What the use cases need from Gmail, in one object (reading and sending)."""

    def __init__(self, reader: GmailReader, sender: GmailSender) -> None:
        """Keep both halves."""
        self._reader = reader
        self._sender = sender

    def list_new(self, history_id: str | None) -> tuple[list[str], str]:
        """New inbox mail ids and the new position."""
        return self._reader.list_new(history_id)

    def list_unread_before(self, cutoff: datetime) -> list[str]:
        """Ids of unread inbox mails older than the cut-off, newest first."""
        return self._reader.list_unread_before(cutoff)

    def fetch(self, message_id: str) -> FetchedMail:
        """Headers and text of one mail."""
        return self._reader.fetch(message_id)

    def ensure_label(self, name: str) -> str:
        """Id of the label, created when missing."""
        return self._reader.ensure_label(name)

    def file(self, message_id: str, label_id: str) -> None:
        """Add the category label and take the mail out of the inbox."""
        self._reader.file(message_id, label_id)

    def check_repliable(self, original: FetchedMail) -> None:
        """Refuse automatic, list and no-reply mail."""
        self._sender.check_repliable(original)

    def send_reply(self, original: FetchedMail, draft: ConfirmedDraft) -> str:
        """Send a confirmed reply."""
        return self._sender.send_reply(original, draft)


def build_runner(  # noqa: PLR0913 - the outside world is injected, nothing is read from the environment
    settings: Settings,
    *,
    sessions: async_sessionmaker[AsyncSession],
    client: httpx.AsyncClient,
    mailbox: object,
    sender: object,
    own_address: str,
    heartbeat: Path,
    now: Callable[[], datetime],
    new_id: Callable[[], str] = lambda: str(uuid.uuid4()),
    today: Callable[[], str] | None = None,
) -> Runner:
    """Wire the store, the adapters and the use cases into a runner."""
    store = PgStore(sessions)
    outbox = TelegramOutbox(client, settings.telegram_bot_token, settings.telegram_allowed_chat_id)
    inbox = TelegramInbox(
        client, settings.telegram_bot_token, settings.telegram_allowed_user_id, settings.telegram_allowed_chat_id
    )
    budget = DailyBudget(settings.daily_model_budget, today)  # one budget: the catch-up only gets what new mail leaves
    judge = AnthropicJudge(client, settings.anthropic_api_key, settings.model_small, settings.model_large, budget)
    snooze = SnoozeService(store, outbox, now)
    reply = ReplyService(store, mailbox, sender, outbox, own_address=own_address, now=now, new_id=new_id)  # type: ignore[arg-type]
    return Runner(
        pipeline=TriagePipeline(mailbox, judge, store, FailureNotice(outbox), now),  # type: ignore[arg-type]
        catchup=CatchUp(mailbox, judge, store, FailureNotice(outbox), budget, now),  # type: ignore[arg-type]
        delivery=AlertDelivery(store, outbox, now, hourly_cap=settings.alerts_per_hour),
        snooze=snooze,
        overview=OverviewService(store, outbox, now, DEFAULT_POLICY),
        store=store,
        inbox=inbox,
        router=CommandRouter(reply, snooze, store, outbox, ConversationStore(sessions, now)),
        heartbeat=heartbeat,
        interval_seconds=settings.poll_interval_seconds,
        now=now,
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def serve(settings: Settings) -> int:  # pragma: no cover - needs the real Google, Telegram and database
    """Run the agent until it is told to stop. Returns an exit code."""
    from google.oauth2.credentials import Credentials  # noqa: PLC0415
    from googleapiclient.discovery import build  # noqa: PLC0415

    engine = create_async_engine(settings.database_url.get_secret_value())
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.connect() as lock_connection:
        if not await repos.try_lock(lock_connection):
            logger.error("another copy of the agent holds the lock; exiting")
            return EXIT_LOCKED
        await upgrade(settings.database_url.get_secret_value())
        refresh_token = await TokenStore(sessions, TokenCipher(settings.token_encryption_key)).load()
        if refresh_token is None:
            logger.error("no Google consent stored; run: python -m app.consent")
            return EXIT_NO_CONSENT
        credentials = Credentials(  # type: ignore[no-untyped-call]
            None,
            refresh_token=refresh_token,
            token_uri=GMAIL_TOKEN_URL,
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret.get_secret_value(),
            scopes=list(GMAIL_SCOPES),
        )
        service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        address = str(service.users().getProfile(userId="me").execute()["emailAddress"])
        ports = MailPorts(GmailReader(service), GmailSender(service))
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for name in ("SIGINT", "SIGTERM"):
            if hasattr(signal, name):
                loop.add_signal_handler(getattr(signal, name), stop.set)
        async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
            runner = build_runner(
                settings,
                sessions=sessions,
                client=client,
                mailbox=ports,
                sender=ports,
                own_address=address,
                heartbeat=HEARTBEAT,
                now=_utc_now,
            )
            logger.info("mail-triage started")
            await runner.run(stop)
        await repos.release_lock(lock_connection)
    await engine.dispose()
    return EXIT_OK
