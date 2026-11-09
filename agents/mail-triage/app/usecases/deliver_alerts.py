"""Alert delivery: send each open alert once, honour the hourly cap, release held alerts after quiet hours.

Spec AC-3, AC-5, AC-12, AC-22, AC-26, AC-32. A failed Telegram call raises before anything is marked as sent, so the
alert stays open and the next run sends it once. (A crash between the send and ``mark_sent`` can send it twice; that
is the price of never losing an alert.)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Protocol

from app.core.alert_text import AlertMessage, AuthResults, DigestEntry, MailMeta, build_alert, build_digest
from app.core.time_policy import in_quiet_hours
from schedule_policy.policy import DEFAULT_POLICY

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from datetime import datetime

    from app.core.alert_state import AlertState
    from app.core.judgement import Judgement

DEFAULT_HOURLY_CAP = 5


@dataclass(frozen=True, slots=True)
class PendingAlert:
    """An alert with everything needed to build its message."""

    alert_id: str
    state: AlertState
    meta: MailMeta
    judgement: Judgement
    auth: AuthResults


class AlertStore(Protocol):
    """Persistence for delivery."""

    async def held(self) -> list[PendingAlert]:
        """Alerts waiting for quiet hours to end."""
        ...

    async def release(self, alert_id: str) -> None:
        """Move a held alert to open."""
        ...

    async def unsent(self) -> list[PendingAlert]:
        """Open alerts that have no Telegram message yet."""
        ...

    async def mark_sent(self, alert_id: str, telegram_message_id: int, *, at: datetime) -> None:
        """Store the Telegram message id; the alert is never sent again."""
        ...

    async def sent_since(self, since: datetime) -> int:
        """How many alerts were sent individually since ``since``."""
        ...

    async def record_audit(self, kind: str, alert_id: str) -> None:
        """Write an audit entry: kind and alert id only, no mail content."""
        ...


class Outbox(Protocol):
    """Telegram, sending to the owner's chat."""

    async def send(self, message: AlertMessage) -> int:
        """Send and return the Telegram message id."""
        ...


def _entries(alerts: Sequence[PendingAlert]) -> list[DigestEntry]:
    return [DigestEntry(sender=a.meta.sender, subject=a.meta.subject) for a in alerts]


class AlertDelivery:
    """Sends alerts to Marco."""

    def __init__(
        self,
        store: AlertStore,
        outbox: Outbox,
        now: Callable[[], datetime],
        hourly_cap: int = DEFAULT_HOURLY_CAP,
    ) -> None:
        """Wire the store, the Telegram outbox, the clock and the cap."""
        self._store = store
        self._outbox = outbox
        self._now = now
        self._cap = hourly_cap

    async def deliver_open_alerts(self) -> None:
        """Release held alerts when quiet hours are over, then send what is open and unsent."""
        now = self._now()
        if not in_quiet_hours(now, DEFAULT_POLICY):
            await self._release_held()
        unsent = await self._store.unsent()
        if not unsent:
            return
        used = await self._store.sent_since(now - timedelta(hours=1))
        room = max(0, self._cap - used)
        for alert in unsent[:room]:
            await self._send(alert, now)
        excess = unsent[room:]
        if excess:
            await self._send_summary(excess, now)

    async def _release_held(self) -> None:
        held = await self._store.held()
        for alert in held:
            await self._store.release(alert.alert_id)
        if len(held) > 1:
            await self._outbox.send(build_digest(_entries(held), held=True))

    async def _send(self, alert: PendingAlert, now: datetime) -> None:
        message = build_alert(alert.alert_id, alert.meta, alert.judgement, alert.auth)
        message_id = await self._outbox.send(message)
        await self._store.mark_sent(alert.alert_id, message_id, at=now)
        await self._store.record_audit("alert_sent", alert.alert_id)

    async def _send_summary(self, alerts: Sequence[PendingAlert], now: datetime) -> None:
        message_id = await self._outbox.send(build_digest(_entries(alerts), held=False))
        for alert in alerts:
            await self._store.mark_sent(alert.alert_id, message_id, at=now)
            await self._store.record_audit("alert_batched", alert.alert_id)
