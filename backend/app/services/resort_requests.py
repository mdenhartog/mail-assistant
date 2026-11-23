"""The use cases of the sort-again routes for one mailbox (U-label-structure-21, ADR-0056)."""

import uuid
from typing import TYPE_CHECKING

from app.schemas.resort_requests import DEFAULT_THRESHOLD

if TYPE_CHECKING:
    from app.clock import Clock
    from app.resort_repo import ResortRepository


class ResortRequests:
    """Asks for a new sort and tells what the threshold field shows."""

    def __init__(self, repository: "ResortRepository", clock: "Clock", requests_per_hour: int) -> None:
        """Keep the repository, the clock and the hourly limit (the one of list saves)."""
        self._repository = repository
        self._clock = clock
        self._requests_per_hour = requests_per_hour

    async def ask(self, threshold: int) -> uuid.UUID:
        """Make one request; see ``ResortRepository.request`` for the refusals it raises.

        Args:
            threshold: The validated threshold.

        Returns:
            The id of the request.
        """
        return await self._repository.request(threshold, self._clock.now(), self._requests_per_hour)

    async def latest_threshold(self) -> int:
        """Return the threshold of the latest request, or 50 on the first visit."""
        stored = await self._repository.latest_threshold()
        return DEFAULT_THRESHOLD if stored is None else stored
