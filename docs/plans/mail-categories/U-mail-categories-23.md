---
intent: INT-004
feature: mail-categories
---

# U-mail-categories-23: Connect the list notice and Telegram actions to PostgreSQL

- Component: mail-triage
- Layer: backend
- Release: R1
- Contract: the PostgreSQL implementations of the ports of U-07 (`ActionStore` on `categories.telegram_action`: one compare-and-set `UPDATE ... WHERE nonce_hash, chat_id, kind, used_at IS NULL, expires_at > now RETURNING target`; `ListNoticeStore`: pending versions and change from `categories.list_audit`, `restore` inserts a `list_version` with its `category` rows under the existing ids and raises `ListChanged` when the latest version differs; the web lock), a notice cursor (a new column such as `poll_state.list_notice_version` through a migration, or its own table; it is not the `list_cursor` of the label sync), routing of the callback prefixes `catundo:` and `catlock:` to `ListNoticeActions.on_button`, and the call of `ListNotice.run` each cycle with `secrets.token_urlsafe(16)` as nonce source.
- Files: agents/mail-triage/app/db/pg_list_notice.py, agents/mail-triage/migrations/versions/*, agents/mail-triage/app/db/grants.sql, agents/mail-triage/app/runner.py, agents/mail-triage/app/wiring.py, agents/mail-triage/tests/db/test_pg_list_notice.py, agents/mail-triage/tests/test_runner_list_notice.py
- Depends on: U-mail-categories-07, U-mail-categories-21
- Parallel: no
- Guardrails: guardrail-python, guardrail-pytest, guardrail-sqlalchemy-alembic, guardrail-telegram
- Criteria:
  1. Given a web change at night, When a cycle runs, Then one notice is sent from the real database as the agent role and the cursor advances only after the send (AC-48) (type: happy)
  2. Given a nonce, When it is pressed twice at once, Then exactly one press wins and the other sees "Already done" (type: edge)
  3. Given Undo, When the latest version is no longer the last of the burst, Then it is refused and nothing is written (type: error)
  4. Given Undo, When it runs, Then the restore is a new version with the old category ids and an audit row with channel and actor digest derived by the database (type: security)
  5. Given the grants matrix, Then the agent can neither update nor delete audit rows and the new cursor column follows the existing grants (type: security)
