---
id: INT-011
title: Higher daily model budget and a reviewable partial plan
originator: Marco
status: draft
date: 2026-11-25
---

## What I want

Raise the daily model budget to 500. When there are too many mails for one day, I want to be able to process
the 500 that were checked, and the next day the other mails are picked up.

## Why (the problem, who has it, how often)

I use the web app and the "Review moves" screen. The agent allows 200 model calls per day and keeps 50 of them
for new mail. New mail uses most of the budget (about 170 mails a day), so the plan for older mail is paused
almost every day and the screen stays on "checked so far" without saying why. I cannot review or apply
anything until the whole plan is built.

## How I will know it works

- The daily budget is 500.
- When the budget runs out during a plan, the screen says the plan is paused because of the daily budget and
  shows what has been checked so far.
- I can review and apply the part that has been checked, without waiting for the rest.
- The next day the agent goes on with the mails that were not checked yet.

## What it must not do

- It must not lose or re-check mails that were already checked.
- It must not use up the budget that new mail needs: new mail keeps its reserve.
- It must not move mail before I have approved the part I review.
- No secrets, mail text or label names in logs, notices or URLs.

## Open questions

- Does "process the 500" mean the 500 mails that were checked, or the 500 model calls (one mail can take two calls)? (Marco)
- Should a Telegram message tell me once a day that the plan is paused and will go on tomorrow? (Marco)
- After I applied a part, does the next day's part become a new plan to review, or does it join the open one? (spec phase)
- The budget is kept in the agent's memory and starts again on a restart; is that acceptable at 500 a day? (spec phase)
- Raising the budget raises the cost with the model provider: is a spending limit wanted? (Marco)

## Original wording

"Verhoog het tot 500. Maar zorg als er teveel mails zijn dat ik de 500 kan verwerken en dat de volgende dag de andere mails worden opgepakt"
