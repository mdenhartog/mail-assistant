"""U-web-settings-42 (AC-20, W-15): the failure paths that `scripts/prodlike-checks.sh logs` greps the logs for.

Image level, run by the `prod-like` CI job with the other tests of this folder. It walks a successful sign-in and the
failure paths through the edge: a request for an unknown canary username, a wrong code, a rejected zone. It writes what
the logs must never contain (the codes, the canary username and zone) to the file named by ``E2E_CANARY_FILE``, one
value per line; the script adds the SMTP password and the session cookie value. Needs ``E2E_PROD_LIKE=1``.
"""

import os
import re
import time
from pathlib import Path

import httpx
import pytest

pytestmark = pytest.mark.skipif(not os.environ.get("E2E_PROD_LIKE"), reason="needs the running prod-like stack")

ROOT = Path(__file__).resolve().parents[3]
CA = ROOT / "deploy" / "prod-like" / "certs" / "ca.crt"
EDGE = f"https://mail-assistant.localhost:{os.environ.get('EDGE_HTTPS_PORT', '8443')}"
MAILBOX = f"http://127.0.0.1:{os.environ.get('MAIL_PORT', '8025')}"
USERNAME = os.environ.get("E2E_USERNAME", "e2e-owner")
CANARY_USERNAME = "canary-user-7f3a9c1e"
CANARY_ZONE = "Canary/Zone-Rejected-4b2d"
CODE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
WRONG_CODE = "718293"


def _newest_code() -> str:
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        messages = httpx.get(f"{MAILBOX}/api/v1/messages?limit=1", timeout=10).json()["messages"]
        if messages:
            text = httpx.get(f"{MAILBOX}/api/v1/message/{messages[0]['ID']}", timeout=10).json()["Text"]
            found = CODE.search(text)
            if found:
                return found.group(1)
        time.sleep(0.5)
    pytest.fail("no sign-in mail arrived")


def _remember(*values: str) -> None:
    target = os.environ.get("E2E_CANARY_FILE")
    if target:
        with Path(target).open("a", encoding="utf-8") as handle:
            handle.writelines(f"{value}\n" for value in values)


def test_given_the_failure_paths_and_a_sign_in_when_walked_through_the_edge_then_each_answers_as_planned() -> None:
    headers = {"Origin": EDGE}
    httpx.delete(f"{MAILBOX}/api/v1/messages", timeout=10)
    with httpx.Client(verify=str(CA), base_url=EDGE, timeout=20) as edge:
        unknown = edge.post("/auth/request-code", json={"username": CANARY_USERNAME}, headers=headers)
        time.sleep(1.5)  # the resend cooldown of the prod-like profile is one second
        asked = edge.post("/auth/request-code", json={"username": USERNAME}, headers=headers)
        wrong = edge.post("/auth/verify-code", json={"code": WRONG_CODE}, headers=headers)
        code = _newest_code()
        signed_in = edge.post("/auth/verify-code", json={"code": code}, headers=headers)
        info = edge.get("/api/session", headers={"Sec-Fetch-Site": "same-origin"})
        current = edge.get("/api/settings").json()
        rejected = edge.put(
            "/api/settings",
            json={"values": {**current["values"], "timeZone": CANARY_ZONE}, "version": current["version"]},
            headers={**headers, "X-CSRF-Token": info.json()["csrfToken"]},
        )
        edge.post("/auth/logout", headers={**headers, "X-CSRF-Token": info.json()["csrfToken"]})
    _remember(code, WRONG_CODE, CANARY_USERNAME, CANARY_ZONE)

    assert unknown.status_code == asked.status_code == 200  # the same answer for every username (ADR-0036)
    assert wrong.status_code == 400
    assert signed_in.status_code == 204
    assert rejected.status_code == 422
