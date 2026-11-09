---
feature: adjustable-quiet-hours
intent: INT-002
extends: mail-triage
status: approved
date: 2026-11-09
approver: Marco
sibling: web-settings
---

# Adjustable quiet hours (Telegram)

## Summary

The first release of `mail-triage` keeps four values fixed in the code (`agents/mail-triage/app/core/time_policy.py`, base spec C7): quiet hours 23:00 to 07:00, the daily overview at 18:00, the "tomorrow" default of a reminder at 09:00 and the time zone Europe/Amsterdam. This feature lets Marco see and change these four values in Telegram through a guided conversation. The settings are stored in a shared PostgreSQL schema so that the web UI (feature `web-settings`, same intent) can use the same values later.

Why: Marco travels (for example to the USA) and a fixed Amsterdam clock does not fit his day (INT-002). Changing the time zone is the must-have; the other three values are convenience and are cut first if the work has to shrink.

Success: during the next trip no alert arrives inside local quiet hours, and Marco changes the zone in Telegram alone, within 2 minutes.

Review: round table of 2026-11-09 (product owner, architect, security architect, UX critic, QA strategist). Its findings are folded into this version; INT-002 was split into this feature and `web-settings` at Marco's decision.

## Who it is for

Marco, the single owner. No other users and no roles.

## Goals

1. Marco can see and change the four values in Telegram.
2. Every alert that arises after a change is judged with the new values; alerts already held or snoozed keep the time they were given.
3. With no stored settings the agent behaves exactly like the first release.
4. A bad stored value can never silence the agent, and Marco is told when the agent falls back.

## Non-goals

- The web UI, the login and the web audit notice: feature `web-settings`.
- No automatic time-zone detection, no several users or profiles, no schedule per weekday, no history screen, no other settings.
- Alerts that are already snoozed or held are not re-planned (S7).

## Anti-goals (a failure even if it technically works)

- A nonsensical value is stored, and the agent stops alerting or alerts all night.
- Someone other than Marco changes a value.
- A change made in two places at once is lost or leaves a row that breaks the rules.
- Marco answers a question for one setting and changes another, or a snooze answer is read as a city.
- The agent falls back to Amsterdam times while Marco is abroad and he is not told.

## Decisions made by Marco

| # | Decision | Source |
| --- | --- | --- |
| S1 | Adjustable values: quiet hours (start and end), daily overview time, reminder default ("tomorrow"), time zone. | INT-002 |
| S2 | Telegram and the web UI can change and show all four; Telegram is built first. | INT-002, brainstorm |
| S3 | INT-002 is built as two features: this one (Telegram) and `web-settings`. | round table decision, 2026-11-09 |
| S4 | Telegram uses a guided conversation with buttons. | brainstorm |
| S5 | The time zone is chosen by typing a city or a country. | brainstorm |
| S6 | Times are clock times in the chosen zone: after a zone change the hours stay 23:00 to 07:00 on the clock there. | brainstorm |
| S7 | A change applies only to alerts that arise after it. A held alert keeps the release time it got when it was held. | INT-002, round table decision |
| S8 | Values are validated; nonsensical values are refused. | INT-002 |
| S9 | The settings live in the existing PostgreSQL, read by the agent and written by Telegram (here) and the web backend (later). | brainstorm (ADR-0023, ADR-0025) |

## My calls (Marco may change these)

- C-1: **Defaults.** With no row, or with the table absent, the agent uses 23:00, 07:00, 18:00, 09:00 and Europe/Amsterdam (first-release behaviour).
- C-2: **Valid values.** Times are whole minutes. The quiet window is 1 to 12 hours long, measured in clock minutes, start differs from end, and it may or may not cross midnight. The overview time and the reminder default must lie outside quiet hours (start inclusive, end exclusive, as `in_quiet_hours` does today). The zone is a name from the IANA database. One shared validation (package `packages/schedule-policy`) checks the whole row; every write is checked as a whole row, not per field.
- C-3: **Typed times.** Accepted: `7`, `7:00`, `07:00`, `0700`, `19.30`, `7am`, `7:30pm`; `00:00` and `24:00` mean midnight. Refused: anything else, including seconds, full-width digits, empty text and text over 64 characters.
- C-4: **Held and snoozed alerts.** A snoozed alert keeps its due moment (stored in UTC). A held alert gets, when it is held, a release moment: the next quiet end under the values valid then. It is released at that moment even if a later change puts that moment inside new quiet hours. A snooze that becomes due inside quiet hours is held and released at the quiet end valid at that moment.
- C-5: **Wall-clock rules (ADR-0027).** All scheduling compares UTC moments. A configured time that does not exist on a day (spring-forward gap) means the first valid moment after the gap. A time that occurs twice (autumn) means its first occurrence.
- C-6: **Time-zone lookup.** Typed text is matched without regard to case and accents against a bundled list of cities, countries and common aliases ("NYC", "Wien"), which maps to IANA zones. Several hits show at most 5 buttons labelled like "Paris, France (UTC+1)". A near miss offers "Did you mean New York?". A country with several zones shows its zones with city names. A typed IANA name (`Europe/Paris`) is also accepted if it is in the list. No network call. The source of the list is an ADR in phase 3.
- C-7: **Confirmation.** After a change the bot shows the full picture, for example: "Time zone: America/New_York (UTC-5). It is 17:05 there, 23:05 in Amsterdam. Quiet hours 23:00 to 07:00 New York time (05:00 to 13:00 Amsterdam). Next overview: today 18:00." It adds the next clock change within 14 days, and an **Undo** button.
- C-8: **Conversation.** One conversation at a time, held in one stored conversation state (ADR-0026) that also carries the existing snooze and reply questions. Starting a new one replaces the old one and says so. A settings question expires after 15 minutes; the old message is edited to "Expired" without buttons and offers "Start again". Snooze and reply questions keep their current behaviour. Buttons carry a random token and an index, never a value.
- C-9: **Fallback.** If the stored row cannot be read or is invalid, the agent uses the last good values, or the defaults if there were none, and sends Marco one Telegram notice per incident naming the values in use.
- C-10: **Wording.** English, 24-hour time. Terms: "Quiet hours", "Daily overview", "Remind-me-later default", "Time zone" (as in the alert texts). A change takes effect within one run interval.
- C-11: **Audit.** Every change writes an append-only record (time, channel, actor, old and new values) filled by a database trigger. No history screen.

## Behaviour

1. `/settings` shows the four values; each has a "Change" button.
2. A tap starts a question for that value. A time is typed; quiet hours ask start, then end (start is kept in the conversation and both are stored together); the time zone is typed as a city or a country. Every question has a Cancel button and names the value and the step ("Quiet hours, step 1 of 2: start time").
3. The answer is validated (C-2, C-3). On a problem the bot says which rule, shows the value given and a working example ("Quiet hours can be 1 to 12 hours. 22:00 to 11:00 is 13 hours. Try 22:00 to 10:00."), and asks again.
4. If a quiet-hours change would put the overview or the reminder default inside quiet hours, the bot says so and offers a one-tap move of that value outside the window.
5. The bot stores the whole row with a version check, shows the confirmation (C-7) and the settings again.
6. Undo restores the previous row if nobody changed it since; otherwise the bot says it changed.
7. The agent reads the row once per operation (a snapshot), so one decision never mixes old and new values. A held or snoozed alert is judged as in C-4.

## Acceptance criteria

| # | Criterion |
| --- | --- |
| AC-1 | **Given** no settings row (and, separately, no settings table), **when** the existing time_policy, deliver_alerts, overview and snooze tests run, **then** they pass unchanged (first-release behaviour). |
| AC-2 | **Given** the allowed user, **when** they send `/settings`, **then** the four values are shown with their labels and a "Change" button each. |
| AC-3 | **Given** a user or chat that is not allowed, **when** they send `/settings` or tap a button, **then** nothing is answered or changed. |
| AC-4 | **Given** a button from another chat's forward, or an old button whose token is not the current one, **when** it is tapped, **then** nothing changes and the bot says the card is out of date and shows a fresh one. |
| AC-5 | **Given** a pending snooze or reply question, **when** Marco sends `/settings` and starts a change, **then** the old question is replaced, the bot says "I dropped the question about alert X", and his next typed text is read only as the settings answer. |
| AC-6 | **Given** a settings question, **when** the answer comes at 14:59 it is used; at 15:00 or later it is not used, the question message shows "Expired" without buttons, and a "Start again" button is offered. |
| AC-7 | **Given** any question, **when** Marco taps Cancel, **then** the old value stays and no row is written. |
| AC-8 | **Given** the typed times `7`, `7:00`, `07:00`, `0700`, `19.30`, `7am`, `7:30pm`, `24:00`, **when** answered, **then** each is read as the right clock time (one test row each). |
| AC-9 | **Given** the texts `abc`, `25:00`, `07:00:30`, a full-width `０７:００`, empty text, a 65-character text, `../etc`, `'; DROP TABLE x;--`, a control character and an emoji, **when** answered, **then** each is refused, nothing is stored, and the zone lookup is never called with it. |
| AC-10 | **Given** quiet windows 23:00-07:00 (valid), 07:00-19:00 (valid, 12 h), 07:00-19:01 (refused), 07:00-07:30 (refused), 07:00-08:00 (valid, 1 h) and 23:00-23:00 (refused), **when** answered, **then** the result matches and the refusal names the rule and an example. |
| AC-11 | **Given** overview 06:00 and a new quiet window 23:00-07:00, or overview 18:00 and a new window 17:00-03:00, **when** the window is saved, **then** it is refused with the reason and a one-tap move of the overview is offered; taking it stores both together. |
| AC-12 | **Given** quiet hours 01:00-06:00, **when** an urgent mail arrives at 23:30, 03:00 and 06:00, **then** its alert is sent, held and sent. |
| AC-13 | **Given** the quiet-hours question, **when** the start is valid and Marco cancels, or the end is invalid, or a database fault occurs between the two steps, **then** neither value is stored. |
| AC-14 | **Given** the text "New York" (any case or accent), **when** answered, **then** America/New_York is stored. |
| AC-15 | **Given** "Paris", "Sydney" or "Georgia", **when** answered, **then** at most 5 labelled buttons are shown and the chosen one is stored. |
| AC-16 | **Given** "Nwe York", **when** answered, **then** the bot offers "Did you mean New York?". |
| AC-17 | **Given** text that matches nothing, **when** answered, **then** the bot says so, suggests the nearest big city or the country, shows Cancel and stores nothing. |
| AC-18 | **Given** "USA" or "Australia", **when** answered, **then** the zones are offered as buttons with city names. |
| AC-19 | **Given** "Europe/Paris" typed and in the list, **when** answered, **then** it is stored. |
| AC-20 | **Given** a stored change, **when** it succeeds, **then** the confirmation shows the zone with its UTC offset, the local time there and in the previous zone, the quiet hours in both, the next overview, the next clock change within 14 days if any, and an Undo button. |
| AC-21 | **Given** Undo is tapped and the row is unchanged since, **then** the previous values return; if the row changed since, nothing changes and the bot says so. |
| AC-22 | **Given** a stored change, **when** the next alert arises, **then** it is judged with the new values. |
| AC-23 | **Given** zone America/New_York with quiet hours 23:00-07:00, **when** an urgent mail arrives at 23:30 New York time, **then** its alert is held. |
| AC-24 | **Given** a snoozed alert, **when** a change is stored, **then** its due moment does not move. |
| AC-25 | **Given** an alert held at 02:00 with release at 07:00, **when** Marco sets quiet hours to 23:00-05:00 at 03:00, **then** that alert is still released at 07:00; an alert held after the change uses the new hours. |
| AC-26 | **Given** a snooze that becomes due inside the new quiet hours, **then** it is held and released at the quiet end valid at that moment. |
| AC-27 | **Given** the overview was sent today in Europe/Amsterdam, **when** the zone becomes America/New_York the same evening, **then** no second overview is sent for that local date, no filed mail is dropped, and the next overview is at 18:00 New York time. |
| AC-28 | **Given** Europe/Amsterdam and America/New_York on their spring and autumn clock-change days and one zone with a change at midnight, **when** `in_quiet_hours`, `next_quiet_end`, `next_overview` and the "tomorrow" due moment run for a time inside the gap and a time that occurs twice, **then** results follow C-5 (and a 12 h window on a 23 h or 25 h day validates in clock minutes). |
| AC-29 | **Given** two writers that read the same row version, **when** both save, **then** the second is refused with "changed elsewhere" and the stored row still passes C-2. |
| AC-30 | **Given** a stored change, **then** an audit record exists with fixed columns (time, channel, actor id, old, new) and no free text, written by a database trigger; the agent's runtime role can only insert into it, never update or delete. |
| AC-31 | **Given** a row with an invalid value (unknown zone, window of 13 h, overview inside the window, NULL), **when** the agent runs, **then** it ignores that row, uses the last good values or the defaults, logs `settings_invalid` with the key and no value, and sends one Telegram notice naming the values in use. |
| AC-32 | **Given** a read that fails by connection refused, timeout, permission error or missing table, or takes longer than 2 seconds, **then** the agent continues with the last good values or defaults within the timeout, logs the error class and sends one notice per incident. |
| AC-33 | **Given** any change or error, **when** it is logged, **then** the canary zone `Pacific/Kiritimati` never appears in any captured log record and no token appears. |
| AC-34 | **Given** a direct insert into the settings table that breaks a rule (minutes out of range, start equals end, window outside 60-720 minutes, a second row), **then** PostgreSQL refuses it. |
| AC-35 | **Given** the agent runs with no backend process, **then** it reads, applies and changes settings normally. |
| AC-36 | **Given** the migrated schema, **then** the agent and the shared validation package agree on it (one contract test fixture, shared with `web-settings`). |

## Security (see `docs/security/adjustable-quiet-hours-threat-model.md`)

Settings change alert timing, so every control that protects who may change them and what they may contain matters most: AC-3, AC-4, AC-9, AC-10, AC-29 to AC-34. Test numbers from the round table (fixed `now`, fake clock, fake Telegram port, real PostgreSQL for the table) are in the plan.

## Open points for phase 3 (design)

- Source of the city and country list (ADR).
- ADR-0025 (settings contract), ADR-0026 (one conversation state), ADR-0027 (wall-clock rules) are proposed and need approval with this spec.
- `TimePolicy` value object and `PolicySource` port replace the module constants; the old functions and the dead "yesterday" branch in `overview.py` are removed (rebuild-not-patch).
- Archify diagrams: C4 containers with the `settings` schema and grants; sequence of the quiet-hours dialogue.
