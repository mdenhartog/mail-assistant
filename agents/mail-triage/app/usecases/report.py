"""The success numbers of the list structure (INT-008, spec D22, AC-63), worded for the daily re-file report.

Counts only: no sender, no subject, no message id. The numbers are of the mail filed in the period:

- the share filed by a sender rule (the newest filing of each mail names its source);
- model calls per day: the mails the model filed, one call each. An urgency-only call on a sender-rule mail is not
  counted, as no ledger of calls is kept; the number is a lower bound;
- always-notify alerts per day (an alert whose causes name an always-notify category, ADR-0057);
- the share filed under "Other";
- the Move-back rate of system-approved items: of the items applied from automatic plans in the period, the share the
  user later moved back. A move back is counted only for a mail that was really restored, so the rate is a lower bound.
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
    system_applied: int  # items applied from automatic plans in the period
    system_moved_back: int  # of those, the items a move back restored

    def __post_init__(self) -> None:
        """Refuse a period without days (every per-day number divides by it) and a rate above the whole."""
        if self.days < 1:
            raise ValueError("days must be at least 1")
        if self.system_moved_back > self.system_applied:
            raise ValueError("more items moved back than applied")


def _share(part: int, whole: int) -> str:
    return f"{100.0 * part / whole:.1f}% of {whole} new mails" if whole else "no new mail"


def _move_back_line(counts: SuccessCounts) -> str:
    prefix = "Moved back after system approval: "
    if not counts.system_applied:
        return f"{prefix}no system-approved items"
    rate = 100.0 * counts.system_moved_back / counts.system_applied
    return f"{prefix}at least {rate:.1f}% of {counts.system_applied} system-approved items"


def success_text(counts: SuccessCounts) -> str:
    """The fixed wording, one line per number."""
    return "\n".join(
        (
            f"Success numbers (last {counts.days} days):",
            f"Filed by a sender rule: {_share(counts.by_rule, counts.filed)}",
            f"At least {counts.by_model / counts.days:.1f} model calls per day (filing calls only)",
            f"Always-notify alerts per day: {counts.always_notify_alerts / counts.days:.1f}",
            f"Filed under Other: {_share(counts.in_other, counts.filed)}",
            _move_back_line(counts),
        )
    )
