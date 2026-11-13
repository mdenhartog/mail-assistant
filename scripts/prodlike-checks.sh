#!/usr/bin/env bash
# Checks over the running prod-like stack (U-web-settings-42, AC-20, W-15). Run by the `prod-like` CI job.
#
#   scripts/prodlike-checks.sh logs
#   scripts/prodlike-checks.sh headers
#
# `headers` requests pages, assets, errors and API routes through the TLS edge and checks the security headers of each
# answer (U-web-settings-59): the SPA policy, nosniff, Referrer-Policy, Permissions-Policy, COOP and CORP from nginx,
# and `default-src 'none'; frame-ancestors 'none'`, COOP and CORP from the API, including on 401 and 404.
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

edge_host="mail-assistant.localhost"
edge_port="${EDGE_HTTPS_PORT:-8443}"

# headers_of PATH: the response headers, lower-cased, without carriage returns.
headers_of() {
  curl -sS -D - -o /dev/null --cacert deploy/prod-like/certs/ca.crt     --resolve "$edge_host:$edge_port:127.0.0.1" "https://$edge_host:$edge_port$1" | tr -d '' | tr 'A-Z' 'a-z'
}

# expect_header PATH STATUS NAME VALUE: the answer has the status and the header with exactly the value.
expect_header() {
  local headers
  headers="$(headers_of "$1")"
  echo "$headers" | head -n 1 | grep -q " $2" || { echo "$1 did not answer $2"; return 1; }
  echo "$headers" | grep -qxF -- "$3: $4" || { echo "$1 ($2) lacks the header $3: $4"; return 1; }
}

check_headers() {
  local spa_csp="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
  local api_csp="default-src 'none'; frame-ancestors 'none'"
  local failed=0 path status
  # The web image: every page, the assets location (a missing file is a 404) and the fallback 404.
  for target in "/ 200" "/login 200" "/settings 200" "/assets/missing.js 404" "/anything 404"; do
    path="${target% *}"
    status="${target#* }"
    expect_header "$path" "$status" content-security-policy "$spa_csp" || failed=1
    expect_header "$path" "$status" x-content-type-options nosniff || failed=1
    expect_header "$path" "$status" referrer-policy strict-origin-when-cross-origin || failed=1
    expect_header "$path" "$status" permissions-policy "camera=(), microphone=(), geolocation=()" || failed=1
    expect_header "$path" "$status" cross-origin-opener-policy same-origin || failed=1
    expect_header "$path" "$status" cross-origin-resource-policy same-origin || failed=1
  done
  # The API: a 401 (no session) and a 404 (unknown route).
  for target in "/api/settings 401" "/api/anything 404" "/auth/anything-unknown 404"; do
    path="${target% *}"
    status="${target#* }"
    expect_header "$path" "$status" content-security-policy "$api_csp" || failed=1
    expect_header "$path" "$status" cross-origin-opener-policy same-origin || failed=1
    expect_header "$path" "$status" cross-origin-resource-policy same-origin || failed=1
    expect_header "$path" "$status" x-content-type-options nosniff || failed=1
  done
  return "$failed"
}

if [ "$mode" = "headers" ]; then
  check_headers
  exit $?
fi
if [ "$mode" != "logs" ]; then
  echo "usage: $0 logs|headers" >&2
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
