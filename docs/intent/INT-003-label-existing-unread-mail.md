---
id: INT-003
title: Label the unread mail already in my inbox
originator: Marco
status: confirmed
date: 2026-11-08
---

## What I want

(English version, to be approved by Marco; his own words are kept under *Original wording*.)

The agent also labels the unread mails that were already in my inbox when it was first started, not only the mails that arrive afterwards. I expected those mails to be categorised and could not see that happening.

Scope, as chosen by Marco: all **unread** mail in the inbox, handled once, started automatically by the agent on its first start (no command and no switch). If a mail among them looks urgent, I may get a Telegram alert for it, at most 5 alerts; the other urgent ones appear in the overview instead.

## Why (the problem, who has it, how often)

Marco, for his personal mailbox. After starting the agent, his inbox shows little change: plenty of unread mails that he expected to be labelled stay as they were, so he still misses mails among them. This was seen on the first real run, on 2026-11-08. It touches the goal of INT-001 (a better overview of the mailbox) because the mails that matter most today are the old unread ones.

## How I will know it works

- After the first start, every unread mail that was in my inbox carries exactly one `Assistant/...` label and has left the inbox, without me doing anything.
- I do not get a flood of Telegram alerts: at most 5 for old mail, the rest in the overview.
- Starting the agent again does not process those mails a second time.

## What it must not do

- It must not delete mail (as in INT-001).
- It must not touch mail that is already read.
- It must not send more than 5 Telegram alerts for old mail.
- It must not send a reply or any mail without my confirmation (as in INT-001).

## Open questions

- The agent is already running here with a stored Gmail position, so "first start" has already passed. How does the one-time catch-up run for an installation that already started? (design)
- How many unread mails can there be, and does the daily model budget (`MAIL_TRIAGE_DAILY_MODEL_BUDGET`) cover them? What happens to the rest: wait for the next day, or stop? (Marco)
- The old mails are sent to the Anthropic API in bulk. Does this change the threat model and the data-retention choice of ADR-0017? (threat-model)
- Which 5 alerts are sent when more urgent mails are found: the newest, or the ones the agent is most sure about? (Marco)
- Is this one intent or part of INT-001? It adds a missing rule to the same feature (the spec only covers "mail that arrived since the last run"); the spec of mail-triage is to be changed, not a new feature started. (Marco)

## Original wording

> Ik zie tot op heden niet dat mijn mail gelabeld wordt want er gebeurt niet zo heel veel in mijn inbox. Er zijn zat niet gelezen mailtjes die ik eigenlijk verwacht had dat die gelabeld zouden worden. Wat is er aan de hand kan je daar dan ook anders een intent voor maken om dit te verbeteren en om aan te geven dat dit een bug is of kan je hier een bug van maken die je daarna kan oplossen?
