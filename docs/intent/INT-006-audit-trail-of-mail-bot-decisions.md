---
id: INT-006
title: Audit trail of the mail bot's decisions
originator: Marco
status: draft
date: 2026-11-14
---

## What I want

(English version, to be approved by Marco; his own words are kept under *Original wording*.)

I want a complete audit trail of everything the mail bot does. For every mail I want to see what the bot saw, why it decided what it did (for example, why it put the mail in a certain category), and what the decision was. I want to read this as a clear log trail in the web application, so it has to be stored in the application. That lets us look back later at what goes well and what does not, and steer on the categories or other things to make the bot work better.

As answered by Marco on 2026-11-14:

- The log can be **switched on and off**. It does not have to be on all the time.
- We must be able to **see why the bot makes its decisions**, and to **actually inspect those decisions** in the web application.
- We must be able to **steer the bot later when it makes a wrong decision**.

## Why (the problem, who has it, how often)

Marco, as the owner of the mail bot. I want to be able to see that the bot works and that it works correctly; that is the goal of the log.

TODO (ask Marco): what goes wrong or is missing today, how often he looks at it, and what it costs him that he cannot see it.

## How I will know it works

- I can see, per mail, what the bot saw, why it decided, and what the decision was, in the web application.
- I can switch the log on and off.
- When the bot decided wrongly, I can see that and steer it afterwards.

TODO (ask Marco): what he will concretely open or count to say "it works" (for example, open any mail and read the reason for its category; filter on category, "other" or period).

## What it must not do

TODO (ask Marco): limits on what the log may contain (full mail text, or only sender, subject and a fragment), how long it is kept, and who may see it. Same limits as before: it must not delete or send any mail (INT-001).

## Open questions

- Is "steering later when a decision was wrong" part of this intent, or a separate intent that builds on the log? Today this intent would be the log and the screen; steering would be a second intent. (Marco)
- What is "the decision" exactly: only the category, or also other actions of the bot (alerts via Telegram, quiet hours, moving mail)? (Marco)
- What does "what he sees" mean: the full mail, or a reduced version? The log may then hold personal data from mail and the prompts and answers of the language model (ADR-0018). (threat-model, decision-gate)
- Who may see the log when several accounts and mailboxes exist (INT-004)? (Marco, design)
- When the log is switched off, is anything kept at all (for example only the decision, without the reasoning)? Is the switch global or per mailbox? (Marco)
- The agent runs as a separate service with its own database; where is the log stored and how does the web application read it? (design)
- How is the log kept trustworthy as an audit trail: can entries be changed or deleted afterwards? (spec, threat-model)

## Original wording

> Deze intent gaat over het volgende en registreer die. Wat ik graag zou willen is dat er een complete audit trail komt wat deze mailbot precies allemaal doet. Dus wat ik wil weten is wat hij kiest, waarom hij tot iets besluit, om in een bepaalde categorie te stoppen. Dus ik wil zien wat hij ziet, waarom dat hij besluit neemt en wat het besluit is. En dat wil ik in een nette logtrail zien. Die logtrail wil ik kunnen inzien gewoon in de webapplicatie. Dus die moet uiteindelijk gestoord worden in de applicatie, zodat we later kunnen kijken welke zaken wel en niet goed gaan. En zo kunnen wij gaan sturen op de categorieën of op andere zaken om die bot beter te laten werken.
>
> (Antwoord, 2026-11-14:) Ik wil gewoon kunnen zien dat het werkt en dat het correct werkt. Dat is eigenlijk het doel van de log. De log die moet aan of uitgeschakeld kunnen worden. Dus het hoeft niet altijd aan te staan, maar uiteindelijk moeten we wel kunnen zien waarom dat die besluiten neemt en dat we die besluiten ook gewoon daadwerkelijk kunnen inzien en ook later kunnen bijsturen als die een besluit verkeerd neemt.
