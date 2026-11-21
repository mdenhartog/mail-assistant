---
id: INT-009
title: Scan a mailbox into a category file
originator: the user
status: draft
date: 2026-11-21
---

## What I want

(English version, to be approved by the user; their own words are kept under *Original wording*.)

When someone else installs this agent, they can have a Claude skill scan their own mailbox and write the category file (the YAML format and template of INT-008) for them, the way the user's own structure was researched with Claude.

## Why (the problem, who has it, how often)

TODO (ask the user): who else would install the agent, and how do they get a good first list today?

## How I will know it works

TODO (ask the user): what will you see or be able to do, for example "a new person scans their mailbox in Claude and uploads the result without editing it by hand"?

## What it must not do

TODO (ask the user). The skill reads a person's mailbox, so it must not store mail text or addresses outside that person's own machine without their say; to confirm.

## Open questions

- Where does the skill run (Claude Code, Claude in the browser) and which Gmail access does it use, separate from the agent's own access? (design, threat-model)
- A mailbox scan reads personal data of third parties; what may the skill keep or send, and how is the sample cut? (threat-model)
- It builds on the file format, template and example of INT-008 (`schema: 1`). It cannot start before INT-008's spec is approved. (spec phase)

## Original wording

> 11 mee eens maar maak ook een template mocht deze agent ook door anderen geinstalleerd worden met een skill die hun emailbox kan scannen in Claude.
