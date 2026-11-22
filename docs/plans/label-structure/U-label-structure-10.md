---
intent: INT-008
feature: label-structure
---

# U-label-structure-10: The always-notify alert (R1)

- Component: mail-triage
- Layer: backend
- Contract: `core/alert_decision.py` (ADR-0057): an alert exists when the mail is urgent or a category it is filed under is ticked, with every cause; the alert text starts with "Always notify: <category>" or "Urgent: needs your attention"; a sender-rule alert shows the verified domain and "Category not chosen by the model; urgency read by the model" (reworded after the R1 challenge; the sender, subject and reason are shown in code spans and a reason that could become a link is refused) with no summary and no clickable or masked link; a model-filed mail in a ticked category without an authenticated sender says "sender not verified" and shows the real address; one alert per mail, written once keyed by the mail id; quiet hours, the hourly cap and the daily overview as today; no always-notify alert for re-sorted or backlog mail; the existing alert warning "sender could not be verified" and the `auth_*` columns stop using the weaker parser `core/auth_results.py` and use `authenticated_from_domain` (unit 07), after which `auth_results.py` and its test are removed (ADR-0054 decision 1; unit 07 kept them because this alert still needed them).
- Files: `agents/mail-triage/app/core/alert_decision.py`, `agents/mail-triage/app/core/alert_text.py`, `agents/mail-triage/app/usecases/triage.py`, `agents/mail-triage/app/usecases/deliver_alerts.py`, tests
- Depends on: U-label-structure-08, U-label-structure-09
- Parallel: yes
- Guardrails: guardrail-python, guardrail-telegram, guardrail-pytest
- Criteria:
  1. Given a new non-urgent mail filed in a ticked category, When processed, Then one alert starts with "Always notify: <category>" and has sender, subject, the three actions and the reason. (type: happy)
  2. Given a sender-rule mail, When its alert is built, Then it shows the verified domain, "Category not chosen by the model; urgency read by the model", no summary and no link (reason in a code span; a reason that could become a link is refused). (type: security)
  3. Given a model-filed mail in a ticked category without an authenticated sender, or with a missing or unparsable From, When the alert is built, Then it says "sender not verified" and shows the real address. (type: security)
  4. Given a mail that is urgent and in a ticked category, or in two ticked categories, When processed, Then exactly one alert exists and it names every cause. (type: edge)
  5. Given an unticked category and a non-urgent mail, Then no alert; Given an urgent mail, Then the urgency alert with the label "Urgent: needs your attention". (type: happy)
  6. Given quiet hours and the hourly cap at N and N+1, When alerts arise, Then they are held and batched as today (fake clock). (type: edge)
  7. Given a mail moved by a re-sort or handled by the backlog, When it is filed, Then no always-notify alert is created. (type: edge)
  8. Given the agent stops after filing and before the Telegram send, When it restarts, Then exactly one alert exists for the mail. (type: edge)
