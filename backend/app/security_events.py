"""Security event store (U-web-settings-13)."""

from app.clock import Clock
from app.db import Database


class SecurityEvents:
    """Writes `web_auth.security_event` as the web role."""

    def __init__(self, database: Database, clock: Clock) -> None:
        """Keep the database access and the clock."""
        self._database = database
        self._clock = clock

    async def record(self, kind: str, request_id: str, client: str, username_hash: str | None = None) -> None:
        """Record one event."""
        raise NotImplementedError
