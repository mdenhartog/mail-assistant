---
intent: INT-002
feature: web-settings
---

# U-web-settings-14: Logging hygiene (R1)

- Layer: backend
- Contract: the uvicorn access log is off (image command without `--access-log`), request logging records method, path template, status and request id and never the query string, and the `httpx`, `httpcore` and `aiosmtplib` loggers are pinned to WARNING in `app/logging_setup.py`.
- Files: `backend/app/logging_setup.py`, `backend/app/main.py`, `backend/Dockerfile`, `backend/tests/test_logging_hygiene.py`
- Depends on: U-web-settings-05
- Parallel: yes (with U-12, U-13)
- Guardrails: guardrail-fastapi, guardrail-docker
- Criteria:
  1. Given `GET /auth/anything?code=424242&q=Pacific/Kiritimati`, When served, Then no captured log line contains a canary, `code=`, `q=` or any query-parameter name after a `?` (AC-20, W-13, W-15) (type: security; level: api).
  2. Given a request with a cookie holding a canary value, When served, Then the cookie value is in no log line (W-15) (type: security; level: api).
  3. Given the image command, When read, Then the access log is disabled (type: security; level: ci).
  4. Given the app is created, When the loggers are read, Then `httpx`, `httpcore` and `aiosmtplib` are at WARNING (type: security; level: unit).
  5. Given an unhandled error on a request with a canary body, When logged, Then the line has the class and request id only (AC-15) (type: security; level: api).
  6. Given one request, When served, Then exactly one request line is logged with the request id and the matched path template, not the raw path with ids (type: happy; level: api).
