---
feature: mail-triage
intent: INT-001
unit: U-mail-triage-19
status: draft
---

# Mail triage: end-to-end check with a test account

A manual run of the whole agent against a Gmail **test** account, a Telegram test bot and the real Anthropic API. It is
never run in CI. Automated tests already run the same flow against a real PostgreSQL with fake Gmail, Telegram and
Anthropic (`tests/db/test_end_to_end.py`); this run proves the real services behave the same.

## What you need (from Marco)

| Item | Where to get it | Goes into |
| --- | --- | --- |
| Anthropic API key and two model ids | console.anthropic.com | `ANTHROPIC_API_KEY`, `MAIL_TRIAGE_MODEL_SMALL`, `MAIL_TRIAGE_MODEL_LARGE` |
| Telegram bot token | chat with @BotFather, `/newbot` | `TELEGRAM_BOT_TOKEN` |
| Your Telegram user id | message @userinfobot | `TELEGRAM_ALLOWED_USER_ID`, `TELEGRAM_ALLOWED_CHAT_ID` |
| Google OAuth client (Desktop app) | Google Cloud console, Gmail API enabled, your test account added as test user | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET` |
| Encryption key for the stored token | `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` | `MAIL_TRIAGE_TOKEN_ENCRYPTION_KEY` |
| A second e-mail account | any account that can send mail to the test mailbox | used to send the seed mails |

All variables are listed with explanations in `.env.example`. Copy it to `.env` and fill it in. Use a Gmail account
that holds no real mail.

## Start

1. `docker compose --profile dev up -d db` and wait until it is healthy.
2. In `agents/mail-triage`, with `DATABASE_URL` pointing at the compose database and the other variables from `.env`
   exported: `uv run python -m app.consent`. It creates the tables when they are missing, opens your browser, and
   asks for the three Gmail permissions: sign in with the **test** Gmail account and accept them.
3. Check the database now holds one row in `oauth_token` and that its `ciphertext` is unreadable.
4. `docker compose --profile dev up -d --build mail-triage` and open the logs: `docker compose logs -f mail-triage`.
5. Send the Telegram bot a message once (Start) so it may write to you.

## Seed

`uv run python scripts/e2e_seed.py <test-mailbox> <second-account>` prints four mails. Send each one from the second
account to the test mailbox (paste subject, body and, where shown, the extra headers; plain Gmail cannot set custom
headers, so for the newsletter and the automatic notice the body text alone is judged).

## Checks

| # | Do | Expect | Criteria |
| --- | --- | --- | --- |
| 1 | Send the four seed mails | Within about 2 minutes all four carry exactly one `Assistant/...` label and have left the inbox; only the personal request produced a Telegram alert with Reply, Remind me later and No more reminders | AC-1, AC-3, AC-4 |
| 2 | Press **Reply**, type an answer, press **Send** on the draft | Nothing is sent until Send; the second account then receives the answer in the same thread; no reminder follows | AC-6, AC-7 |
| 3 | On a new urgent mail press **Remind me later**, answer `1` | One new alert arrives after an hour (or change the due time in the database for a quick test) | AC-9 |
| 4 | Press **No more reminders** on an alert | No alert for that mail ever again; the label stays | AC-10 |
| 5 | Look at the injection mail | It is filed (or flagged for attention); nothing was sent to `attacker@example.com`; nothing was deleted | AC-19, AC-2 |
| 6 | Send a Telegram message from a different account to the bot | No reply, no effect | AC-11 |
| 7 | Read `docker compose logs mail-triage` and `select * from audit_log` | No mail text, no tokens, no key; audit rows hold ids and hashes only | AC-22, AC-24 |
| 8 | In Gmail, check Trash and Spam | Nothing of the test mails was deleted | AC-2, AC-28 |
| 9 | Before the first start, leave a few unread mails in the test inbox; then start the agent and watch for two to five minutes | Each of those unread mails carries exactly one `Assistant/...` label, is out of the inbox and still unread; at most 5 Telegram alerts come from them (the rest of the urgent ones appear in the 18:00 overview); read mail and mail outside the inbox are untouched; `select started_at, finished_at from catchup_state` shows one row that finishes; a restart does not process the mails again | AC-B1 to AC-B6, AC-B10 |

## Clean up

`docker compose --profile dev down -v`, delete the `Assistant/*` labels in the test account, and revoke the app's access
at myaccount.google.com/permissions.

## Result

Fill in per check: date, pass or fail, and notes. Failures become bugs through the normal flow.
