"""Compose the agent: build every part from the settings and hand back a ``Runner``.

``build_runner`` takes what touches the outside world (database sessions, one shared HTTP client, the Gmail ports) as
arguments, so the whole agent can be run against fakes. ``serve`` supplies the real ones and holds the single-replica
lock for as long as the agent runs.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import signal
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.adapters.gmail_read import GmailReader
from app.adapters.gmail_send import GmailSender
from app.adapters.judge_anthropic import AnthropicJudge, DailyBudget
from app.adapters.telegram_inbox import TelegramInbox
from app.adapters.telegram_outbox import TelegramOutbox
from app.adapters.token_store import TokenCipher, TokenStore
from app.db import repos
from app.db.engine import make_engine
from app.db.migrate import ROLES, RuntimeRoleNotSafe, SchemaNotReady, check_schema, migrate_database
from app.db.pg_conversation import ConversationStore
from app.db.pg_overview_log import PgOverviewLog
from app.db.pg_policy_source import PgPolicySource
from app.db.pg_security_events import PgSecurityEvents
from app.db.pg_settings_store import PgSettingsStore
from app.db.pg_store import PgStore
from app.db.pg_update_cursor import PgUpdateCursor
from app.db.pg_web_lock import PgWebLock
from app.db.pg_web_notice import PgWebNotice
from app.runner import FailureNotice, Runner
from app.usecases.catchup import CatchUp
from app.usecases.code_alert import CodeAlert
from app.usecases.deliver_alerts import AlertDelivery
from app.usecases.dispatch import CommandRouter
from app.usecases.overview import OverviewService
from app.usecases.policy_notice import PolicyNotice
from app.usecases.reply import ReplyService
from app.usecases.settings_dialog import SettingsDialog
from app.usecases.snooze import SnoozeService
from app.usecases.triage import TriagePipeline
from app.usecases.web_notice import WebNotice
from app.usecases.web_notice_actions import WebNoticeActions

if TYPE_CHECKING:
    from collections.abc import Callable

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from app.adapters.gmail_read import FetchedMail
    from app.adapters.gmail_send import ConfirmedDraft
    from app.settings import MigrateSettings, Settings

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
EXIT_SCHEMA_NOT_READY = 5
EXIT_MIGRATION_FAILED = 6


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
    new_token: Callable[[], str] = lambda: secrets.token_urlsafe(16),  # 22 characters: the notice's own Undo token
    today: Callable[[], str] | None = None,
) -> Runner:
    """Wire the store, the adapters and the use cases into a runner."""
    conversations = ConversationStore(sessions, now)  # the one: PgStore and the router judge expiry with this clock
    store = PgStore(sessions, conversations)
    outbox = TelegramOutbox(client, settings.telegram_bot_token, settings.telegram_allowed_chat_id)
    cursor = PgUpdateCursor(sessions)  # the last handled Telegram update; it survives a restart
    inbox = TelegramInbox(
        client,
        settings.telegram_bot_token,
        settings.telegram_allowed_user_id,
        settings.telegram_allowed_chat_id,
        cursor,
    )
    budget = DailyBudget(settings.daily_model_budget, today)  # one budget: the catch-up only gets what new mail leaves
    judge = AnthropicJudge(client, settings.anthropic_api_key, settings.model_small, settings.model_large, budget)
    settings_store = PgSettingsStore(sessions)
    policy = PgPolicySource(settings_store, PolicyNotice(outbox))  # one per process: it holds the last good values
    snooze = SnoozeService(store, outbox, now, policy)
    reply = ReplyService(store, mailbox, sender, outbox, own_address=own_address, now=now, new_id=new_id)  # type: ignore[arg-type]
    router = CommandRouter(reply, snooze, store, outbox, conversations, cursor)
    router.register(
        SettingsDialog(settings_store, outbox, conversations, settings.telegram_allowed_user_id, now, policy.in_use)
    )
    web_notices = PgWebNotice(sessions)
    web_lock = PgWebLock(sessions)
    router.register_web_actions(
        WebNoticeActions(
            web_notices,
            web_lock,
            settings_store,
            outbox,
            chat_id=settings.telegram_allowed_chat_id,
            by=str(settings.telegram_allowed_user_id),
            now=now,
        )
    )
    return Runner(
        pipeline=TriagePipeline(mailbox, judge, store, FailureNotice(outbox), now, policy),  # type: ignore[arg-type]
        catchup=CatchUp(mailbox, judge, store, FailureNotice(outbox), budget, now, policy),  # type: ignore[arg-type]
        delivery=AlertDelivery(store, outbox, now, policy, hourly_cap=settings.alerts_per_hour),
        snooze=snooze,
        overview=OverviewService(store, PgOverviewLog(sessions), outbox, now, policy),
        web_notice=WebNotice(web_notices, outbox, new_token),
        code_alert=CodeAlert(PgSecurityEvents(sessions), web_lock, outbox),
        store=store,
        inbox=inbox,
        router=router,
        heartbeat=heartbeat,
        interval_seconds=settings.poll_interval_seconds,
        now=now,
    )


def _utc_now() -> datetime:
    return datetime.now(UTC)


async def verify_schema(engine: AsyncEngine) -> int | None:
    """The agent's readiness check: None when the schema is at the expected head, else the exit code to stop with."""
    try:
        await check_schema(engine)
    except SchemaNotReady as error:
        logger.error("%s", error)  # the message holds revisions only, a traceback adds nothing
        return EXIT_SCHEMA_NOT_READY
    return None


async def migrate(settings: MigrateSettings) -> int:
    """The migrate command: schema, runtime role and grants, as the owner role. Returns an exit code."""
    try:
        passwords = {role.name: getattr(settings, role.password_setting).get_secret_value() for role in ROLES}
        await migrate_database(settings.database_owner_url.get_secret_value(), passwords, settings.database_tls)
    except RuntimeRoleNotSafe as error:
        logger.error("migration failed: %s", error)  # names the role only, never a password or a URL
        return EXIT_MIGRATION_FAILED
    except Exception as error:  # whatever failed, the job must end non-zero without echoing a value
        logger.error("migration failed: %s", type(error).__name__)  # no traceback: it may carry the URL
        return EXIT_MIGRATION_FAILED
    logger.info("migration finished; the database is at the head this build expects")
    return EXIT_OK


async def serve(settings: Settings) -> int:  # pragma: no cover - needs the real Google, Telegram and database
    """Run the agent until it is told to stop. Returns an exit code."""
    from google.oauth2.credentials import Credentials  # noqa: PLC0415
    from googleapiclient.discovery import build  # noqa: PLC0415

    engine = make_engine(settings.database_url.get_secret_value(), settings.database_tls)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.connect() as lock_connection:
        if not await repos.try_lock(lock_connection):
            logger.error("another copy of the agent holds the lock; exiting")
            return EXIT_LOCKED
        not_ready = await verify_schema(engine)  # the migrate job owns the schema; the agent only checks it
        if not_ready is not None:
            return not_ready
        refresh_token = await TokenStore(sessions, TokenCipher(settings.token_encryption_key)).load()
        if refresh_token is None:
            logger.error("no Google consent stored; after the migrate job has run, run: python -m app.consent")
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
