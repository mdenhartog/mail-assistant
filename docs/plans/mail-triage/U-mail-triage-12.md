---
intent: INT-001
feature: mail-triage
---

# U-mail-triage-12: Alert text

- Layer: backend (pure core)
- Contract: `build_alert(mail_meta, judgement, auth_results) -> AlertMessage` (text and the three buttons) and `build_digest(...)`.
- Files: `app/core/alert_text.py`, `tests/core/test_alert_text.py`
- Depends on: U-04
- Parallel: yes (after U-04)
- Guardrails: guardrail-telegram
- Criteria:
  1. Given a judgement, When built, Then the text has sender, subject, summary, reason and exactly the three buttons (happy; AC-3).
  2. Given text with Telegram markup or link syntax, When built, Then it is escaped and links are plain text (security; AC-21).
  3. Given a very long subject or summary, When built, Then it is cut at the cap (edge; AC-21).
  4. Given `Reply-To` differs from `From`, When built, Then a warning line is shown (security; AC-16).
  5. Given SPF, DKIM or DMARC failed, When built, Then a visible warning line is added (security).
  6. Given an attachment is present, When built, Then it says "has an attachment" and shows nothing of its content (edge; AC-23).
