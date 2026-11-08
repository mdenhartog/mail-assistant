---
id: INT-004
title: Let me choose the mail categories myself
originator: Marco
status: draft
date: 2026-11-08
---

## What I want

(English version, to be approved by Marco; his own words are kept under *Original wording*.)

Before the agent creates a category label for a mail, the mail goes through a categorisation layer. In that layer I state which categories I want to have. I can give these categories to the agent through a user interface, and the agent then follows them, so that my mail ends up in the right places.

## Why (the problem, who has it, how often)

Marco, for his personal mailbox. Today the agent invents the categories itself. On the first real run (2026-11-08) some mails were filed in places Marco does not want, and 36 of 75 old unread mails ended under "Other" because the agent had already reached its limit of 15 self-made categories. The list of categories is therefore not what Marco would choose.

## How I will know it works

- I can see my list of categories and change it in a user interface.
- After I change the list, the next mails follow it: a mail is only filed under a category from my list.
- The mails I looked at and did not like in the first run end up where I want them.

## What it must not do

- It must not delete mail (as in INT-001).
- It must not send any mail on its own (as in INT-001).

## Open questions

- Which user interface: Telegram (the only interface today, spec non-goal "No web or mobile screen"), a small web page in the existing web app, or both? (Marco)
- What does a category consist of: only a name, or a name with a short description or examples that tell the agent what belongs there? (Marco)
- What happens to a mail that fits none of my categories: a fixed fallback category, or an alert asking me? (Marco)
- Should the agent re-sort the mails it has already filed when I change the list? (Marco)
- This reverses two decisions of the base spec: D1 (the agent chooses categories itself) and the non-goal "No rules editor", and it replaces the fixed maximum of 15 categories (C2). The spec of mail-triage is to be changed through a new spec. (spec phase)
- A web interface means login, so it touches identity (ADR-0008, Google OAuth2) and the threat model. (decision-gate, threat-model)
- Is this one intent, or several (the category list, the interface, re-sorting existing mail)? (Marco)

## Original wording

> Ik wil dat je een intent maakt opnieuw. En dat er een soort categorisatie moet plaatsvinden voordat de mail een categorielabel aanmaakt. Dus ik wil dat een soort categorisatielaag komt waarin ik kan aangeven welke categorieën ik graag zou willen hebben. En dat moet ik ook aan de agent mee kunnen geven via een user interface. Zodat ik ook zodat de agent daarop gaat reageren en dat ik op die manier alles meer kan categoriseren in de juiste dingen. Want ik zie nu een aantal zaken al gecategoriseerd zijn op plekken die ik niet zo zou willen hebben.
