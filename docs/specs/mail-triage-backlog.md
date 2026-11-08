---
feature: mail-triage-backlog
intent: INT-003
extends: mail-triage
status: approved
date: 2026-11-08
approver: Marco
---

# Mail triage: label the unread mail already in the inbox

## Summary

Today the agent only handles mail that arrives after it first started (`docs/specs/mail-triage.md`, Behaviour 1: "mail that arrived since the last run"). The unread mail that was already in Marco's inbox is never categorised. This feature adds a **one-time catch-up** that files that unread mail with the same labels as new mail, without flooding Marco with alerts and without starving new mail of model budget.

Why: Marco expected his unread mail to be labelled and could not see it happen (INT-003). On 2026-11-08 the first real run left 213 unread mails untouched; after Marco cleared advertising, 75 were left.

## Who it is for

Marco, the single owner of the mailbox. No new screen and no new Telegram command.

## Goals

1. Every mail that was unread in the inbox when the catch-up started is filed under exactly one `Assistant/...` label and leaves the inbox.
2. The catch-up runs once and starts by itself, also on an installation that is already running.
3. New mail always comes first: the catch-up never delays or starves a mail that arrives today.
4. Marco is not flooded: at most 5 Telegram alerts come from the catch-up.

## Non-goals

- Read mail in the inbox is not touched. Mail outside the inbox (archive, other labels, spam, trash) is not touched.
- No Telegram command, no switch and no setting to start or repeat the catch-up (Marco chose "automatic at start").
- No change to how new mail is categorised, judged or alerted.
- No new category set: the catch-up uses the same labels and the same judging as new mail.

## Anti-goals (a failure even if it technically works)

- An old mail is deleted, trashed, marked as spam or sent anywhere.
- An old mail is filed as "needs attention" or alerted only because the model budget ran out.
- A new urgent mail waits behind old mail.
- More than 5 alerts arrive from the catch-up, or the same old mail is processed twice.

## Decisions made by Marco

| # | Decision | Source |
| --- | --- | --- |
| B1 | Scope is all **unread** mail in the inbox. Read mail is out of scope. | INT-003 |
| B2 | The catch-up starts automatically, once. No command, no switch. | INT-003 |
| B3 | At most 5 Telegram alerts for old urgent mail; the other urgent old mail appears in the overview. | INT-003 |
| B4 | New mail has priority over the catch-up; if the daily budget runs out, the catch-up continues the next day. | brainstorm, 2026-11-08 |
| B5 | The catch-up works newest first. | brainstorm, 2026-11-08 |

## My calls (Marco may change these)

- C-B1: The set to process is a snapshot: the unread inbox mails at the moment the catch-up starts. Mail that arrives later is normal new mail, not backlog.
- C-B2: "Done" is stored as one marker in PostgreSQL (ADR-0007). No marker means the catch-up has not finished, so an installation that already runs will do it once after the update, and a fresh installation does it on its first start.
- C-B3: The 5 alerts go to the **newest** 5 urgent old mails, because those are the ones Marco can still act on. Alerts follow the existing rules (quiet hours, one alert per mail, three actions).
- C-B4: New mail is handled first in every run, and the catch-up may only use the daily model budget **above a reserve of 50 calls** (of the 200 a day), so a mail that arrives later in the day always still has budget. The reserve is fixed in the code, like the quiet hours. Added in phase 3 (design); needs Marco's approval.
- C-B5: Old urgent mail that gets no alert is written to the daily overview (D10) once, and is not alerted later.

## Behaviour

1. **Snapshot.** When no "catch-up done" marker exists, the agent lists the unread inbox mails once (excluding mail the agent itself sent, AC-29 of the base spec) and keeps that list, newest first.
2. **Normal run first.** Each polling run first handles new mail exactly as before. Only then does it take mails from the catch-up list while budget is left.
3. **Categorise.** An old mail is read, judged and filed like a new mail: one label, moved out of the inbox, stays unread.
4. **Budget out.** When the daily budget is used up the catch-up stops for that day. The remaining old mails stay untouched in the inbox and are picked up the next day. Nothing is labelled `Assistant/Other` because of the budget.
5. **Alerts.** An old urgent mail gets a Telegram alert while fewer than 5 old-mail alerts were sent. After that, urgent old mail is listed in the daily overview instead.
6. **Finish.** When the list is empty the marker is stored. Restarting the agent does not start a second catch-up.
7. **Failure.** A mail that fails is retried and abandoned after the same number of attempts as new mail, then skipped, so one bad mail cannot block the rest.

## Acceptance criteria

| # | Criterion | Traces to |
| --- | --- | --- |
| AC-B1 | **Given** unread mail in the inbox that arrived before the agent started, **when** the catch-up runs, **then** each of those mails carries exactly one `Assistant/...` label, has left the inbox and is still unread. | B1 |
| AC-B2 | **Given** read mail in the inbox, mail outside the inbox, or mail the agent sent itself, **when** the catch-up runs, **then** none of it is changed. | B1, non-goals |
| AC-B3 | **Given** the catch-up runs, **when** it handles any mail, **then** nothing is deleted, trashed, marked as spam or sent. | INT-003 |
| AC-B4 | **Given** no "catch-up done" marker, **when** the agent starts (also on an installation that already runs), **then** the catch-up starts without any command or setting. | B2 |
| AC-B5 | **Given** the catch-up finished, **when** the agent restarts, **then** it does not process those mails again and does not start a second catch-up. | INT-003 |
| AC-B6 | **Given** a mail that was already filed earlier, **when** the catch-up meets it, **then** it is skipped and not judged again. | INT-003 |
| AC-B7 | **Given** a catch-up in progress and a new mail arriving, **when** the next run happens, **then** the new mail is handled before any remaining old mail. | B4 |
| AC-B8 | **Given** the daily model budget is used up, **when** the catch-up runs, **then** it stops for that day, the remaining old mails stay untouched in the inbox, none is labelled `Assistant/Other`, none gets an alert, and it resumes the next day. | B4 |
| AC-B9 | **Given** the old mails are processed newest first, **when** the list is worked through, **then** a newer mail is filed before an older one. | B5 |
| AC-B10 | **Given** more than 5 old mails are judged urgent, **when** the catch-up runs, **then** exactly 5 Telegram alerts are sent (the newest urgent ones) and the others appear once in the next daily overview. | B3 |
| AC-B11 | **Given** old urgent mail inside quiet hours, **when** it would be alerted, **then** the alert is held like any other alert until the quiet hours end. | base spec D13 |
| AC-B15 | **Given** the catch-up has used the part of the daily budget above the reserve of 50 calls, **when** it runs again that day, **then** it stops, and a new mail that arrives afterwards is still judged with the reserved calls. | B4, C-B4 |
| AC-B12 | **Given** an old mail that fails repeatedly, **when** the attempts are used up, **then** it is abandoned with one error notice and the rest of the catch-up continues. | base spec |

### Security acceptance criteria

| # | Criterion |
| --- | --- |
| AC-B13 | Old mail is sent to the Anthropic API under the same limits as new mail (trimmed text, no attachments, one mail per call; ADR-0018 A-1). Logs and the audit log hold counts and ids only, never mail text. |
| AC-B14 | **Given** an old mail that contains instructions to the assistant, **when** it is judged, **then** the same defences as for new mail apply, and the cap of 5 alerts limits what such a mail could cause. |

## Constraints from existing decisions

- ADR-0007 PostgreSQL holds the marker and the list state; ADR-0014 routing and the budget stay as they are; ADR-0018 accepts sending Marco's own mail to the model; ADR-0011 grants only the Gmail scopes that are already in use (reading unread inbox mail needs no new scope).
- Hard rule 2 (rebuild-not-patch): the "budget out" outcome of the judge changes from "needs attention" to "stop" only for catch-up mail. This must be a clean second path in the use case, not a flag on the existing one.

## Approaches considered

| | Approach | Trade-off |
| --- | --- | --- |
| A (my call) | A separate catch-up pass in the polling run with its own marker, working from a snapshot of the unread inbox mails. | Clean, testable, does not touch the new-mail path; adds one marker and one list of state. |
| B | Move the stored Gmail history position back in time. | Gmail history only reaches back a limited time and includes read mail, so it cannot express "unread only" and cannot be bounded. Rejected. |
| C | A Telegram command (for example `/catchup`) that starts it. | Marco chose automatic; a command is a new interaction and a bigger change. Rejected. |

## Open questions (not blockers)

- None for Marco right now. C-B3 (which 5 alerts) and C-B5 are my calls; say if you want another rule.
- For the design phase: how to pass "budget used up" from the judge to the catch-up without a flag, and where the snapshot list is stored.
