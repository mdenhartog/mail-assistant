---
intent: INT-002
feature: web-settings
---

# U-web-settings-61: Conflict marks name where the other change came from (R1; challenge fix; RT-08)

- Layer: web
- Contract: the conflict marks and buttons derive their wording from `updatedVia` (web or Telegram).
- Files: `apps/web/src/features/settings/ConflictLayer.tsx`, `apps/web/src/features/settings/useConflict.ts`, `apps/web/src/features/settings/ConflictLayer.test.tsx`
- Depends on: U-web-settings-35
- Parallel: yes
- Guardrails: guardrail-react, guardrail-vitest-rtl, guardrail-a11y
- Criteria:
  1. Given a 409 whose row has `updatedVia` web, When the marks render, Then they say the web now has the value and the button says to keep the stored value (W-11, W-12) (type: security; level: component).
  2. Given `updatedVia` Telegram, When rendered, Then the wording names Telegram (type: happy; level: component).
  3. Given both, When axe runs, Then no violation (type: a11y; level: component).
