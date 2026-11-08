---
id: INT-004
title: Let me choose the mail categories myself
originator: Marco
status: draft
date: 2026-11-08
---

## What I want

(English version, to be approved by Marco; his own words are kept under *Original wording*.)

Before the agent creates a category label for a mail, the mail goes through a categorisation layer. In that layer I state which categories I want to have. The agent then follows them, so that my mail ends up in the right places.

As answered by Marco on 2026-11-08:

- I set the categories **only in the web application**, not through Telegram.
- A category has a **name and a description**. The description tells the language model why a mail belongs there, so it can choose the right category.
- A mail that fits none of my categories goes into the **"other" category**.
- When I change the list, the agent **sorts the mail it has already filed again**, so old mail follows the new list too.
- I **always see what is going to be moved before it is moved**. I can approve it **all at once and also mail by mail**; both must be possible.
- Sorting again covers **all mail**, not only the mail the agent has filed itself.
- I sign in to the web application with **Google (OAuth2)**. My own account must work, **and signing in with another account must also be possible**.
- When I change or delete a category, **the language model decides where each mail of that category goes**.

## Why (the problem, who has it, how often)

Marco, for his personal mailbox. Today the agent invents the categories itself. On the first real run (2026-11-08) some mails were filed in places Marco does not want, and 36 of 75 old unread mails ended under "Other" because the agent had already reached its limit of 15 self-made categories. The list of categories is therefore not what Marco would choose.

## How I will know it works

- I can see my list of categories, with their descriptions, and change it in the web application.
- After I change the list, the next mails follow it: a mail is only filed under a category from my list, or under "other".
- Mail that was filed before is sorted again according to the changed list, and I see what will move before anything moves.
- The mails I looked at and did not like in the first run end up where I want them.

## What it must not do

- It must not delete mail (as in INT-001).
- It must not send any mail on its own (as in INT-001).

## Open questions

- "All mail" is a large scope: sorting again may touch every mail in the mailbox, including mail I already read and mail that is old. Is that what is meant, or does "all" mean all mail of the agent's own labels and the inbox? Is there any mail that must never be moved (for example starred or important mail)? (Marco)
- What does the overview of what will move show (the mail, from which category, to which category), and how does it stay readable when many mails move? (design, with Marco)
- "Another account" can mean two things: (a) another Google account of mine that also signs in to the same mailbox and categories, or (b) another person with their own mailbox and their own categories (several users). The base spec has no multi-user support (non-goal). Which one is meant? Who exactly may sign in (an allow-list of accounts)? (Marco)
- Signing in with Google touches identity (ADR-0008, Google OAuth2) and the threat model; the Gmail permission of the agent stays separate from the sign-in of the web application. (decision-gate, threat-model)
- The web application and the agent must share the list of categories. Which of them owns it, and how does the agent get changes (it runs as a separate service with its own database)? (design)
- Descriptions are sent to the language model together with the mail. The same limits as today apply (ADR-0018), but the text of my descriptions becomes part of what the model reads. (threat-model)
- This reverses two decisions of the base spec: D1 (the agent chooses categories itself) and the non-goal "No rules editor", and it replaces the fixed maximum of 15 categories (C2). It also adds a screen, which the base spec excluded (non-goal "No web or mobile screen"). The change goes into a new spec. (spec phase)
- Is this one intent, or several (the category list and the web screen, the categorisation layer, sorting existing mail again)? (Marco)

## Original wording

> Ik wil dat je een intent maakt opnieuw. En dat er een soort categorisatie moet plaatsvinden voordat de mail een categorielabel aanmaakt. Dus ik wil dat een soort categorisatielaag komt waarin ik kan aangeven welke categorieën ik graag zou willen hebben. En dat moet ik ook aan de agent mee kunnen geven via een user interface. Zodat ik ook zodat de agent daarop gaat reageren en dat ik op die manier alles meer kan categoriseren in de juiste dingen. Want ik zie nu een aantal zaken al gecategoriseerd zijn op plekken die ik niet zo zou willen hebben.
>
> (Antwoorden op de vragen, 2026-11-08:) 1. alleen in te stellen via de web applicatie niet via telegram. 2. Naam plus ook een beschrijving waarom de LLM de juiste categorie kan bepalen. 3. Dan valt deze in de overige categorie. 4. ja
>
> (Tweede ronde, 2026-11-08:) 1. wil altijd zien wat er verplaatst gaat worden. 2. Dan moet de LLM bepalen waar de mail naartoe gaat
>
> (Derde ronde, 2026-11-08:) 1. alles. 2. beide moet mogelijk zijn. 3. OAuth2 van Google mijn account moet kunnen maar ook met een ander account
