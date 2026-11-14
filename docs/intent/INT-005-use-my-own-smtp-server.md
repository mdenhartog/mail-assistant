---
id: INT-005
title: Send the app's mail to my own SMTP server
originator: Marco
status: confirmed
date: 2026-11-14
---

## What I want

(English version, approved by Marco on 2026-11-14; his own words are kept under *Original wording*.)

The mails of the app (for now the sign-in codes of the settings page) arrive in the SMTP server that already runs in my Docker stack, the container `smtp4dev`, so that I can check them there and see what they look like. I do not want a separate mail catcher of the project next to it. For this test week the current mail catcher may keep working, but the change belongs in the R2 variant and should happen as soon as possible.

## Why

I use my SMTP server (`smtp4dev`) for all my tests. The project now runs its own mail catcher (Mailpit) in its stacks, so the mails arrive in a program I did not want and I have too many new programs. I want to reuse what I already have. I did not say this clearly at the start, so I understand how it happened.

## How I will know it works

When the settings page sends a sign-in code, the mail arrives in my SMTP server `smtp4dev` in my Docker stack, where I can read it and see how it looks.

## What it must not do

It must not bring in a new program that I do not already use: the project reuses what I have.

## Open questions

- When exactly: as soon as possible and part of the R2 variant; the current Mailpit stays for the test week. How soon after the test week?
- How often does the second mail catcher get in the way and what does it cost (time, confusion)?
- Other limits, for example that no real mail leaves the computer and that the production mail setup stays as it is.
- `smtp4dev` on port 25 offers by default no TLS and no login, while the api today requires STARTTLS with a verified certificate and a login (threat W-14). How should the dev stacks connect to it, and how is it kept impossible in production? (decision-gate, threat model)
- `smtp4dev` runs in another Docker project. Does the project stack reach it through the host port 25 or through a shared Docker network?
- The automated tests (CI `prod-like` job and the journey) read the sign-in code from the catcher on port 8025, and CI has no `smtp4dev`. How do the tests keep reading the code?
- Touches an external system and the sign-in codes: phases 1 and 2 ask about the threat model.

## Original wording

Eerste bericht: "kan een feature bouwen want ik heb een smtpservier draaien in mijn docker stack waar ik de mails graag wil checken en zien hoe die eruit zien. De huidige oplossing doet dit niet en dat wil ik niet. nu is er een andere mail catcher actief dan die ik al had. dus maak een feature die dat later veranderd"

Tweede bericht: "SMTP server did write, is SMTP for dev. Dat is de container naam van de SMTP server die op dit moment in de Docker stack draait."

Derde bericht: "Nu komt de mail in de mailpit aan. Alleen ik wil dat die graag in de SMTP-S-dev aankomt. In die server. Want die gebruik ik voor al mijn testen. Dus die had daar op gelinkt moeten worden. Dus nu heb ik gewoon veel te veel een nieuw programma wat ik niet graag wil. Ik wil dingen hergebruiken. Maar dat heb ik niet goed aangegeven. Dus dat snap ik. Voor de rest wil ik wel dat SMTP-server mee wordt genomen in de R2-variant. Dus het mag nu zo even blijven werken voor deze testweek. Maar ik wil wel dat er zo snel mogelijk dat dit veranderd gaat worden."
