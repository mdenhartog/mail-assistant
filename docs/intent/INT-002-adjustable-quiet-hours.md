---
id: INT-002
title: Adjustable quiet hours
originator: Marco
status: confirmed
date: 2026-11-08
---

## What I want

I want to be able to change the quiet hours. The first release of `mail-triage` keeps them fixed in the code (hardcoded): 23:00 to 07:00 in Europe/Amsterdam. The daily overview time (18:00) is fixed in the same way. This intent makes them adjustable.

Adjustable settings:

- quiet hours (start and end)
- daily overview time (now 18:00)
- snooze default (now 09:00)
- time zone (now Europe/Amsterdam)

Both the web UI and Telegram must be able to change and show these settings. Not every future setting will be available in Telegram, but these are. The web UI is the place where I want to manage more settings later.

## Why (the problem, who has it, how often)

I sometimes travel to other time zones, for example the USA. A fixed time in Europe/Amsterdam then does not match my day: alerts arrive at night or are held during the day. I am the only user.

## How I will know it works

- I can change the quiet hours, the overview time, the snooze default and the time zone in the web UI and in Telegram.
- I can see the current values in both.
- The next alert after a change respects the new values.

## What it must not do

- It must not apply a change to alerts that are already held. A change applies only to alerts that arise after it.
- It must not accept hours that make no sense (the change is validated).
- Until this intent is built, the hours stay fixed in the code and the behaviour of the first release of `mail-triage` does not change.

## Open questions

- What counts as "hours that make no sense" (for example start equal to end, or an invalid time zone)? To be decided in the spec.

## Original wording

> "Ik wil dat we ook de stille uren later zouden willen kunnen aanpassen. Maar dat is een feature of intent wat op een later tijdstip verder uitgewerkt kan worden. Voor nu blijft dit gewoon zoals je dat nu hebt neergezet. Hardcoded."

Answers of 2026-11-09 (summarised above): wants this because of travel across time zones; web UI and Telegram both; overview time, snooze default and time zone adjustable too; only new alerts affected; changes validated; no other limits.
