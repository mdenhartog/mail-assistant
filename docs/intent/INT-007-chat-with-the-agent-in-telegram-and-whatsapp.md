---
id: INT-007
title: Chat with the agent in Telegram and WhatsApp
originator: Marco
status: confirmed
date: 2026-11-14
---

## What I want

I want to be able to chat with the agent in Telegram, and possibly also use the agent through WhatsApp. The chat is about the connected mailbox(es) and calendars, and the agent must be able to answer questions about their content.

## Why (the problem, who has it, how often)

Today the agent can only show a mail that I can read, and I can then say that I want to make a reply, or switch an alarm on or off. I cannot ask it anything about my mail or calendar.

The current functionality is too limited when I want to look up a mail quickly. It only signals the most important mail.

## How I will know it works

I can search in everything that is connected in the mailbox, by chatting, and get an answer based on the content.

## What it must not do

Only the user who uses the solution may chat with the agent, and the agent may only show that user's own mail and calendar. Nobody may reach another person's data.

## Open questions

- Several people can use the system, each with their own mailbox. How does the chat know which user is writing, in Telegram and in WhatsApp, so that it never shows someone else's data?
- Chat answers are based on mail and calendar content. Which of that content may go to the model provider and to Telegram or WhatsApp? ADR-0018 accepts only the current disclosures, so more data going out needs a new decision.
- "Everything that is connected" includes calendars. Google Calendar is named in ADR-0011 but is not built yet. Is it part of this intent?
- May the chat do more than read and search (for example send a reply or change settings), or is it read-only? The current Telegram buttons already confirm before sending.
- WhatsApp needs a public address for incoming messages. The system has no public inbound traffic (ADR-0019, ADR-0037). Is WhatsApp part of the first version, or later?
- Telegram has one owner of the bot's updates today (the mail-triage agent). Who may own it once chat is added?

## Original wording

"Wat ik wil is dat je kan chatten in Telegram, maar ook eventueel de agent via WhatsApp wilt kunnen gebruiken."

"chat gaat over de mailbox(en) en agenda's die geconnect zijn en moet antwoord op de inhoud kunnen geven."

"Nu is het alleen een mail die je kan lezen en zeggen dat je een reply wilt maken of een alarm aan / uit zetten"

"Gewoon kunnen zoeken in alles wat geconnect is in de mailox"

"de gebruiker die de oplossing gebruikt"

"dat de huidige functionaliteit te beperkt is als ik snel een mail wilt opzoeken. Signaleert nu alleen de meest belangrijke mail"
