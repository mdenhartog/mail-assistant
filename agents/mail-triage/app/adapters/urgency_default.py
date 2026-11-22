"""The default urgency judge: every sender-rule mail "needs attention" (ADR-0055 fail-safe).

The real urgency-only model call arrives in a later unit. Until then nothing may be silently dropped, so this adapter
makes no call and answers that the mail needs attention.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.sender_rules import UrgencyVerdict

if TYPE_CHECKING:
    from app.adapters.judge_anthropic import TrimmedMail

__all__ = ["AlwaysNeedsAttention"]


class AlwaysNeedsAttention:
    """An ``UrgencyJudge`` that never calls a model and always says the mail needs attention."""

    async def needs_attention(self, mail: TrimmedMail) -> UrgencyVerdict:
        """Needs attention, whatever the mail says."""
        del mail
        return UrgencyVerdict(needs_attention=True, reason="urgency not judged; treated as needing attention")
