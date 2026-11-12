#!/usr/bin/env bash
# Checks over the running prod-like stack (U-web-settings-42, AC-20, W-15). Run by the `prod-like` CI job.
#
#   scripts/prodlike-checks.sh logs
#
# `logs` collects the logs of api, web, edge and db (and reads migrate.log, which the job wrote when it ran the migrate
# service) into $PRODLIKE_LOG_DIR (default prodlike-logs/), then greps all of them for what must never be logged: the
# sign-in codes, `code=`, the canary username and zone of backend/tests/e2e/test_log_canaries.py, the SMTP password
# and the value of the session cookie. A hit names the file and the kind of secret, never the value.
#
# Inputs, all from the job and none printed: .env (MAIL_SMTP_PASSWORD), $E2E_CANARY_FILE (one value per line, written by
# the canary test), apps/web/playwright/.auth/user.json (the saved session of the setup project) and the mail catcher.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$root"
mode="${1:-}"
out="${PRODLIKE_LOG_DIR:-prodlike-logs}"
mail_url="http://127.0.0.1:${MAIL_PORT:-8025}"

if [ "$mode" != "logs" ]; then
  echo "usage: $0 logs" >&2
  exit 2
fi

mkdir -p "$out"
for service in api web edge db; do
  docker compose --profile prod-like logs --no-color "$service" > "$out/$service.log"
done
test -s "$out/migrate.log" || { echo "migrate.log is missing: the job must write it when it runs the migrate service"; exit 1; }

secrets="$(mktemp)"
trap 'rm -f "$secrets"' EXIT
# A line is "kind<TAB>value"; the kind is what a hit prints.
if [ -n "${E2E_CANARY_FILE:-}" ] && [ -f "$E2E_CANARY_FILE" ]; then
  while IFS= read -r value; do if [ -n "$value" ]; then printf 'canary\t%s\n' "$value"; fi; done < "$E2E_CANARY_FILE" >> "$secrets"
fi
if [ -f .env ]; then
  smtp_password="$(sed -n 's/^MAIL_SMTP_PASSWORD=//p' .env | head -n 1)"
  [ -n "$smtp_password" ] && printf 'smtp-password\t%s\n' "$smtp_password" >> "$secrets"
fi
state=apps/web/playwright/.auth/user.json
if [ -f "$state" ]; then
  jq -r '.cookies[] | select(.name == "__Host-session") | .value' "$state" | while IFS= read -r value; do
    if [ -n "$value" ]; then printf 'session-cookie\t%s\n' "$value"; fi
  done >> "$secrets"
fi
# The codes still in the catcher (the one the setup project used).
for id in $(curl -fsS "$mail_url/api/v1/messages" | jq -r '.messages[].ID'); do
  curl -fsS "$mail_url/api/v1/message/$id" | jq -r '.Text' | grep -oE '(^|[^0-9])[0-9]{6}([^0-9]|$)' | grep -oE '[0-9]{6}' | while IFS= read -r value; do
    printf 'sign-in-code\t%s\n' "$value"
  done >> "$secrets" || true
done

if [ "$(grep -c 'session-cookie' "$secrets" || true)" -eq 0 ]; then
  echo "no session cookie in $state: the setup project did not run, so the cookie cannot be checked"
  exit 1
fi

failed=0
while IFS=$'\t' read -r kind value; do
  [ -n "$value" ] || continue
  if [ "$kind" = "sign-in-code" ]; then
    pattern="(^|[^0-9])$value([^0-9]|\$)"
    matches="$(grep -lE -- "$pattern" "$out"/*.log || true)"
  else
    matches="$(grep -lF -- "$value" "$out"/*.log || true)"
  fi
  if [ -n "$matches" ]; then
    echo "a $kind appears in: $matches"
    failed=1
  fi
done < "$secrets"

# The key=value form of a code, wherever it comes from (a logged query string or form).
if grep -nE '(^|[^A-Za-z0-9_])code=' "$out"/*.log | sed -E 's/code=[^ &"]*/code=<hidden>/'; then
  echo "a log line has code="
  failed=1
fi

if [ "$failed" -ne 0 ]; then
  exit 1
fi
echo "no secret in the logs of api, web, edge, db and migrate ($(wc -l < "$secrets") values checked)"
