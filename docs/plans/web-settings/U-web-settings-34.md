---
intent: INT-002
feature: web-settings
---

# U-web-settings-34: Save feedback: last-change line, saved banner, zone preview (R1)

- Layer: web
- Contract: rebuild of `SaveFeedback.tsx`: `LastChangeLine` ("Last changed from Telegram at 14:02" with `<time datetime>`, from the web, or "Using the default settings." at version 0); the saved banner with what is true now and `noticeIntervalMinutes` from `GET /api/session` (D-1); the permanent sentence under the times and the zone hint; the zone-change preview computed from the form values and the injected clock. The zone is the first field (U-32).
- Files: `apps/web/src/features/settings/SaveFeedback.tsx`, `apps/web/src/features/settings/LastChangeLine.tsx`, `apps/web/src/features/settings/ZonePreview.tsx`, `apps/web/src/features/settings/zoneMath.ts`, `apps/web/src/features/settings/SaveFeedback.test.tsx`
- Depends on: U-web-settings-32, U-web-settings-33
- Parallel: yes (with U-35)
- Guardrails: guardrail-react, guardrail-a11y, guardrail-vitest-rtl
- Criteria:
  1. Given the last change from Telegram at 14:02 Amsterdam time, When shown, Then "Last changed from Telegram at 14:02" with `<time datetime>`; from the web "from the web"; at version 0 "Using the default settings." (AC-1, C-6) (type: happy; level: component).
  2. Given a successful save at 21:42 in Bangkok and `noticeIntervalMinutes` 5, When the banner shows, Then "Saved at 21:42. Quiet hours are 23:00 to 07:00 (Bangkok time). A message with an Undo button follows on Telegram within about 5 minutes." with `role="status"`, focus staying on Save, and the line now says "from the web" (AC-28, AC-13) (type: happy; level: component).
  3. Given `noticeIntervalMinutes` 1 and 5, When rendered, Then "about 1 minute" and "about 5 minutes" (type: edge; level: unit).
  4. Given the zone changed from Europe/Amsterdam to Asia/Bangkok before saving, When previewed, Then "Quiet hours will now be 22:00 to 07:00 Bangkok time (16:00 to 01:00 Amsterdam time)." and the form's clock times are unchanged (AC-28) (type: happy; level: component).
  5. Given the zone changed back to the saved one, When previewed, Then the preview disappears (type: edge; level: component).
  6. Given Asia/Kolkata, a day boundary and a date inside a clock change, When previewed, Then converted times are correct for the injected date (AC-28) (type: edge; level: unit).
  7. Given the page, When rendered, Then the zone is first in DOM and tab order, the sentence "Quiet hours, the overview and reminders follow this time zone." and the hint "The times below are local times in this zone." are present (AC-28) (type: happy; level: component).
  8. Given the preview and the banner, When read by a screen reader, Then neither is `role="alert"` and the success banner is the only live announcement of the save (AC-23) (type: a11y; level: component).
