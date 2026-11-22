"""The success numbers of the list structure (INT-008, spec D22, AC-63), worded for the daily re-file report.

Counts only: no sender, no subject, no message id. The numbers are of the mail filed in the period:

- the share filed by a sender rule (the newest filing of each mail names its source);
- model calls per day: the mails the model filed, one call each. An urgency-only call on a sender-rule mail is not
  counted, as no ledger of calls is kept; the number is a lower bound;
- always-notify alerts per day (an alert whose causes name an always-notify category, ADR-0057);
- the share filed under "Other".

The Move-back rate of system-approved items is not shown: system approval arrives with R2, so there is nothing to count
yet. It joins these lines in that release.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["SuccessCounts", "success_text"]


@dataclass(frozen=True, slots=True)
class SuccessCounts:
    """The raw counts of one period of ``days`` days."""

    days: int
    filed: int  # mails filed in the period, by the model or by a sender rule
    by_rule: int
    by_model: int
    in_other: int
    always_notify_alerts: int

    def __post_init__(self) -> None:
        """Refuse a period without days: every per-day number divides by it."""
        if self.days < 1:
            raise ValueError("days must be at least 1")


def _share(part: int, whole: int) -> str:
    return f"{100.0 * part / whole:.1f}% of {whole} new mails" if whole else "no new mail"


def success_text(counts: SuccessCounts) -> str:
    """The fixed wording, one line per number."""
    return "\n".join(
        (
            f"Success numbers (last {counts.days} days):",
            f"Filed by a sender rule: {_share(counts.by_rule, counts.filed)}",
            f"Model calls per day: {counts.by_model / counts.days:.1f}",
            f"Always-notify alerts per day: {counts.always_notify_alerts / counts.days:.1f}",
            f"Filed under Other: {_share(counts.in_other, counts.filed)}",
        )
    )
