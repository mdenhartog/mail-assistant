---
feature: adjustable-quiet-hours
intent: INT-002
extends: mail-triage
status: approved
date: 2026-11-09
approver: Marco
---

# Adjustable quiet hours

## Summary

The first release of `mail-triage` keeps four values fixed in the code (`agents/mail-triage/app/core/time_policy.py`, base spec C7): quiet hours 23:00 to 07:00, the daily overview at 18:00, the snooze default "tomorrow" at 09:00 and the time zone Europe/Amsterdam. This feature lets Marco change and see these four values, first in Telegram (part 1), then in the web UI (part 2).

Why: Marco sometimes travels (for example to the USA) and a fixed Amsterdam clock then does not fit his day (INT-002).

## Who it is for

Marco, the single owner. No other users and no roles.

## Goals

1. Marco can see and change the four values in Telegram through a guided conversation (part 1).
2. Marco can see and change the same four values in the web UI after signing in with Google (part 2).
3. The agent uses the current values for every alert that arises after a change.
4. With no change made, the agent behaves exactly like the first release.

## Non-goals

- No other settings, and no alert overview in the web UI in this feature. The settings page is only the first page of a web UI that grows later.
- No automatic time-zone detection (location, phone). Marco sets the zone himself.
- No several users, no several profiles, no schedule per weekday.
- Alerts that are already snoozed or already held are not re-planned (see C-4).

## Anti-goals (a failure even if it technically works)

- A nonsensical value is stored and the agent stops alerting, or alerts all night.
- Someone other than Marco changes a value (another Telegram user or an unsigned web visitor).
- The agent stops working when the web backend is down, or when the settings cannot be read.
- Part 1 cannot ship without part 2.

## Decisions made by Marco

| # | Decision | Source |
| --- | --- | --- |
| S1 | Adjustable values: quiet hours (start and end), daily overview time, snooze default, time zone. | INT-002 |
| S2 | Both Telegram and the web UI can change and show all four. | INT-002 |
| S3 | Telegram first, web UI second, both in this intent. | brainstorm, 2026-11-09 |
| S4 | Telegram uses a guided conversation with buttons, not typed commands. | brainstorm, 2026-11-09 |
| S5 | The time zone is chosen by typing a city or a country. | brainstorm, 2026-11-09 |
| S6 | Times are clock times in the chosen time zone: after a zone change the hours stay 23:00 to 07:00 on the clock there. | brainstorm, 2026-11-09 |
| S7 | A change applies only to alerts that arise after it. | INT-002 |
| S8 | Values are validated; nonsensical values are refused. | INT-002 |
| S9 | The settings are one table in the existing PostgreSQL, read by the agent every run and written by Telegram (part 1) and by the web backend (part 2). | brainstorm, 2026-11-09 (ADR-0023) |

## My calls (Marco may change these)

- C-1: Defaults. With no stored row the agent uses 23:00, 07:00, 18:00, 09:00 and Europe/Amsterdam, so the first release behaviour is unchanged (AC-1).
- C-2: Valid values (S8): times are whole minutes (HH:MM); quiet start differs from quiet end; the quiet window is between 1 and 12 hours long; the overview time and the snooze default are outside quiet hours (they would be held anyway); the time zone is a name from the IANA time-zone database.
- C-3: Typing a city or country (S5) is matched against a bundled list of city and country names that maps to IANA zones. A country with several zones shows its zones as buttons. No network call is made for this. The list and its source are a decision for phase 3 (ADR).
- C-4: "Only new alerts" (S7) means: a snoozed alert keeps its fixed due time, and the hour an alert arose in is judged with the values at that moment. A held alert is released when quiet hours are not active, judged live with the current values, as today (`deliver_alerts.py`). So shortening the quiet hours can release held alerts earlier. Marco confirms this reading.
- C-5: The first web UI version is one settings page with the four values and the Google sign-in it needs (ADR-0008). Only Marco's Google account may sign in.
- C-6: A change is stored with the time and the channel (Telegram or web) it came from, so it can be seen later. No history screen.
- C-7: After each change the agent confirms the new value and shows the local time in the chosen zone, so Marco sees at once that it is right.

## Behaviour

### Part 1: Telegram

1. `/settings` shows the four current values, each with a "Change" button.
2. A tap on "Change" starts a short conversation for that value. For a time the bot asks for `HH:MM`; for the quiet hours it asks for the start, then the end; for the time zone it asks for a city or a country.
3. The bot validates the answer (C-2). On a problem it says why and asks again. "Cancel" leaves the old value.
4. The bot stores the value, confirms it with the local time in the chosen zone (C-7) and shows the settings again.
5. Only the allowed Telegram user and chat can use this (as for all other commands).
6. The agent reads the stored values at the start of each run and uses them for quiet hours, the overview time and the snooze default.

### Part 2: Web UI

1. Marco signs in with Google. Anyone else is refused.
2. The settings page shows the four values and lets Marco change them with the same validation (C-2). A change in Telegram shows on the page after a reload, and the other way round.
3. The page works on mobile, tablet and desktop and is accessible (WCAG 2.2 AA).

## Acceptance criteria

| # | Criterion |
| --- | --- |
| AC-1 | **Given** no stored settings, **when** the agent runs, **then** quiet hours are 23:00 to 07:00, the overview is at 18:00, "tomorrow" is 09:00 and the zone is Europe/Amsterdam, as in the first release. |
| AC-2 | **Given** the allowed user, **when** they send `/settings`, **then** the four current values are shown, each with a "Change" button. |
| AC-3 | **Given** a user or chat that is not allowed, **when** they send `/settings` or tap a button, **then** nothing is shown or changed. |
| AC-4 | **Given** the quiet-hours change started, **when** Marco answers a start and an end time, **then** both are stored and confirmed. |
| AC-5 | **Given** a start equal to the end, or a window longer than 12 hours or shorter than 1 hour, **when** Marco answers, **then** it is refused with the reason and nothing is stored. |
| AC-6 | **Given** an overview time or snooze default inside the quiet hours, **when** Marco answers, **then** it is refused with the reason. |
| AC-7 | **Given** text that is not a time, **when** Marco answers, **then** the bot asks again and nothing is stored. |
| AC-8 | **Given** the city "New York", **when** Marco answers, **then** the zone America/New_York is stored and the confirmation shows the local time there. |
| AC-9 | **Given** a country with several zones (for example the USA), **when** Marco answers, **then** the zones are offered as buttons and the chosen one is stored. |
| AC-10 | **Given** a city or country that is not in the list, **when** Marco answers, **then** the bot says it found nothing, asks again and stores nothing. |
| AC-11 | **Given** a stored change, **when** the agent runs the next time, **then** quiet hours, overview time and snooze default use the new values. |
| AC-12 | **Given** the zone is changed to America/New_York with quiet hours 23:00 to 07:00, **when** an urgent mail arrives at 23:30 New York time, **then** its alert is held. |
| AC-13 | **Given** an alert snoozed before a change, **when** the change is stored, **then** its due time does not move. |
| AC-14 | **Given** the settings cannot be read (database error), **when** the agent runs, **then** it uses the last values it read, or the defaults if there were none, and logs the error without a value. |
| AC-15 | **Given** "Cancel" in a conversation, **when** Marco taps it, **then** the old value stays. |
| AC-16 | **Given** a signed-in Marco, **when** he opens the settings page, **then** the four values are shown. |
| AC-17 | **Given** a visitor who is not signed in, or a Google account other than Marco's, **when** they open the page or call the settings API, **then** access is refused and nothing is shown or changed. |
| AC-18 | **Given** a valid change on the page, **when** Marco saves, **then** it is stored and the agent uses it at its next run (AC-11). |
| AC-19 | **Given** an invalid value on the page, **when** Marco saves, **then** the field shows the reason and nothing is stored (same rules as AC-5 to AC-7). |
| AC-20 | **Given** the page at 375, 768 and 1280 px wide, **when** it is checked, **then** it has no horizontal scroll and no accessibility violations (axe). |
| AC-21 | **Given** the web backend is down, **when** the agent runs, **then** it keeps working with the stored values. |

## Security (preliminary; the threat model in phase 2 completes this)

- Settings change alert timing, so an attacker who changes them can hide urgent mail by setting very long quiet hours. The limit of 12 hours and the access rules (AC-3, AC-17) are the first controls.
- The web UI is the first public-facing page of the project: sign-in, session, CSRF and the access check on the settings API need the threat model and `guardrail-oauth2-oidc`.
- The shared table is written by two components; each write validates (C-2) so one cannot store what the other would refuse.

## Open points for later phases

- Source of the city and country list (C-3): ADR in phase 3.
- Whether the table is migrated by the agent or by the backend, and where its contract lives: phase 3 (ADR-0023 fixes only that it is shared).
- Clickable prototype for the web page (ADR-0009): decide in phase 3.
