---
id: INT-002
title: Adjustable quiet hours
originator: Marco
status: draft
date: 2026-11-08
---

## What I want

Later, I want to be able to change the quiet hours. This is for a later time and can be worked out further then. For now the quiet hours stay as they are set in the first release of `mail-triage`: fixed in the code (hardcoded), 23:00 to 07:00 in Europe/Amsterdam. The daily overview time (18:00) is fixed in the code in the same way.

## Why (the problem, who has it, how often)

The originator wants to be able to change the quiet hours later. The first release fixes them in the code on purpose.

TODO (ask Marco): What goes wrong with fixed hours? Who has the problem and how often? What does it cost?

## How I will know it works

TODO (ask Marco)

## What it must not do

- It must not change the behaviour of the first release of `mail-triage`. Until this intent is worked out, the hours stay fixed in the code.

TODO (ask Marco): Any other limits?

## Open questions

- Who changes the hours (only Marco)? How does he do it? Where does he see the current hours?
- Should the daily overview time (now 18:00) be adjustable too?
- Should the snooze default (now 09:00) be adjustable too?
- Should the time zone (now Europe/Amsterdam) be adjustable too?
- Does a change apply at once to alerts that are already held? Or only to alerts that arise after the change?
- Is a change to the hours checked, for example against hours that make no sense?

## Original wording

> "Ik wil dat we ook de stille uren later zouden willen kunnen aanpassen. Maar dat is een feature of intent wat op een later tijdstip verder uitgewerkt kan worden. Voor nu blijft dit gewoon zoals je dat nu hebt neergezet. Hardcoded."
