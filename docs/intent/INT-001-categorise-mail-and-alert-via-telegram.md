---
id: INT-001
title: Categorise mail and alert me via Telegram
originator: Marco
status: confirmed
date: 2026-11-08
---

## What I want

Incoming email is read and categorised by what it is for, so that I get a better overview of my mailbox. The agent chooses useful categories itself, based on the kinds of mail that actually arrive. When a mail arrives that needs my attention immediately, the agent warns me via Telegram. Through Telegram I can then give a reply, which the agent sends on automatically and neatly to the person who should receive it, or to the sender I need to reply to quickly.

## Why (the problem, who has it, how often)

I very often do not have time for my personal mail. Because of that I sometimes miss mails, which is not handy. I want to improve that. (Who: me, Marco, for my personal mailbox. How often: "very often"; the cost is missed mails.)

## How I will know it works

I am warned only when a mail really arrives that I have to respond to.

## What it must not do

- It must not delete mails.
- It may move a mail to the correct category so that I can look at it later.

## Open questions

- Is this one intent or several (categorising; warning on urgent mail; replying through Telegram)? To be decided by the originator.
- What makes a mail "needs my attention immediately"? Who or what decides this, and how is a wrong call (missed or false alarm) handled?
- Should the agent ask for my confirmation before it sends a reply on my behalf, or send it fully automatically?
- Who may use the Telegram channel (only me)?
- Which mailbox and which account(s) are in scope (Gmail is already named in ADR-0011)?
- The mailbox holds personal data and the reply goes out in my name: what may be sent to external services (including the model), and what must stay local? (To be covered in the threat model.)

## Original wording

> Wat ik graag wil met het nieuwe intent is dat de mail die binnenkomt gelezen wordt en gecategoriseerd wordt naar hetgeen waar deze voor nodig is. Je mag zelf categorieën verzinnen die handig zijn bij alle categorieën die binnenkomen. In mijn mail, zodat ik een beter overzicht ga krijgen van mijn mail. Op het moment dat er een mail binnenkomt, wil ik dat de agent mij waarschuwt als deze mail direct mijn aandacht nodig heeft. Dit waarschuwen moet gebeuren via Telegram en via Telegram moet ik een mail kunnen opgeven wat daarna de agent automatisch weer netjes verstuurt naar degene die de mail zou moeten ontvangen of waar ik snel zou op moeten replyen.

> Wat er nu misgaat met mijn mail is dat ik heel vaak daar geen tijd voor heb. Mijn persoonlijke mail. En daardoor soms mailtjes mis. Dat is niet heel handig. En dat wil ik verbeteren. Of dat ik weet of dat het werkt, is gewoon alleen wanneer er echt mail komt waarop ik moet reageren. Als ik dat niet mag doen, is mails verwijderen. Wat wel mag gebeuren, is een mail verplaatsen naar een correcte categorie, zodat ik die later kan bekijken.
