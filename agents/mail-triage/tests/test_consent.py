"""U-07: one-time Google consent for the owner (spec; ADR-0011; guardrail-oauth2-oidc)."""

from __future__ import annotations

import base64
import hashlib
import io
import logging
import threading
import urllib.request
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.consent import (
    REDIRECT_URI,
    SCOPES,
    WAIT_SECONDS,
    ConsentError,
    authorization_request,
    consent_bind_host,
    exchange_code,
    prompt_for_url,
    receive_redirect,
    run_consent,
)

REDIRECT = "http://127.0.0.1:8765/callback"
SECRET = "client-secret-value"  # noqa: S105 - fake
CODE = "4/0AX-authorisation-code"
REFRESH = "1//0g-refresh-token-value"


def test_given_a_request_when_built_then_it_uses_pkce_state_and_only_the_three_scopes() -> None:
    request = authorization_request("client-id", REDIRECT)

    query = parse_qs(urlparse(request.url).query)
    assert set(query["scope"][0].split()) == set(SCOPES)
    assert len(SCOPES) == 3
    assert {s.rsplit("/", 1)[-1] for s in SCOPES} == {"gmail.readonly", "gmail.send", "gmail.modify"}
    assert query["code_challenge_method"] == ["S256"]
    assert query["response_type"] == ["code"]
    assert query["access_type"] == ["offline"]
    assert query["state"] == [request.state]
    assert len(request.state) >= 32
    assert 43 <= len(request.verifier) <= 128
    expected = base64.urlsafe_b64encode(hashlib.sha256(request.verifier.encode()).digest()).rstrip(b"=").decode()
    assert query["code_challenge"] == [expected]
    assert request.verifier not in request.url
    assert "client_secret" not in request.url


def test_given_two_requests_when_built_then_state_and_verifier_differ() -> None:
    first, second = authorization_request("c", REDIRECT), authorization_request("c", REDIRECT)

    assert first.state != second.state
    assert first.verifier != second.verifier


def token_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


async def test_given_a_code_when_exchanged_then_the_refresh_token_is_returned_with_pkce_and_no_secret_in_the_url() -> (
    None
):
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"access_token": "a", "refresh_token": REFRESH, "scope": "x"})

    token = await exchange_code(
        token_client(httpx.MockTransport(handler)), "cid", SECRET, CODE, "verifier-123", REDIRECT
    )

    assert token == REFRESH
    body = parse_qs(seen[0].content.decode())
    assert body["code"] == [CODE]
    assert body["code_verifier"] == ["verifier-123"]
    assert body["grant_type"] == ["authorization_code"]
    assert seen[0].url.scheme == "https"
    assert SECRET not in str(seen[0].url)
    assert CODE not in str(seen[0].url)


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(400, json={"error": "invalid_grant", "error_description": f"bad code {CODE}"}),
        httpx.Response(200, json={"access_token": "a"}),  # no refresh token
        httpx.Response(200, content=b"<html>"),
    ],
)
async def test_given_a_failed_exchange_when_run_then_a_consent_error_without_secrets_is_raised(
    response: httpx.Response,
) -> None:
    client = token_client(httpx.MockTransport(lambda _request: response))

    with pytest.raises(ConsentError) as caught:
        await exchange_code(client, "cid", SECRET, CODE, "v", REDIRECT)

    for secret in (CODE, SECRET, REFRESH):
        assert secret not in str(caught.value)


class MemoryStore:
    def __init__(self) -> None:
        self.saved: list[str] = []

    async def save(self, refresh_token: str) -> None:
        self.saved.append(refresh_token)


def exchanging_client() -> httpx.AsyncClient:
    return token_client(httpx.MockTransport(lambda _r: httpx.Response(200, json={"refresh_token": REFRESH})))


async def test_given_a_matching_state_when_consent_runs_then_the_token_is_stored(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    store, shown = MemoryStore(), []

    async def wait(request_state: str) -> dict[str, str]:
        return {"code": CODE, "state": request_state}

    await run_consent(
        client=exchanging_client(),
        client_id="cid",
        client_secret=SECRET,
        redirect_uri=REDIRECT,
        store=store,
        show_url=shown.append,
        wait_for_redirect=wait,
    )

    assert store.saved == [REFRESH]
    assert len(shown) == 1
    for secret in (CODE, SECRET, REFRESH):
        assert secret not in caplog.text


@pytest.mark.parametrize("params", [{"code": CODE, "state": "forged"}, {"code": CODE}, {"error": "access_denied"}, {}])
async def test_given_a_wrong_state_or_a_denied_consent_when_run_then_nothing_is_stored(params: dict[str, str]) -> None:
    store = MemoryStore()

    async def wait(_state: str) -> dict[str, str]:
        return params

    with pytest.raises(ConsentError):
        await run_consent(
            client=exchanging_client(),
            client_id="cid",
            client_secret=SECRET,
            redirect_uri=REDIRECT,
            store=store,
            show_url=lambda _url: None,
            wait_for_redirect=wait,
        )

    assert store.saved == []


def test_given_a_browser_redirect_when_received_then_the_query_is_returned_and_nothing_else_is_served() -> None:
    result: list[dict[str, str]] = []
    ready = threading.Event()

    def serve() -> None:
        result.append(
            receive_redirect("127.0.0.1", 0, timeout=5, on_ready=lambda port: (ports.append(port), ready.set()))
        )

    ports: list[int] = []
    thread = threading.Thread(target=serve)
    thread.start()
    assert ready.wait(5)

    stray = urllib.request.Request(f"http://127.0.0.1:{ports[0]}/other?code=x")
    with pytest.raises(urllib.error.HTTPError):
        urllib.request.urlopen(stray, timeout=5)  # noqa: S310
    with urllib.request.urlopen(f"http://127.0.0.1:{ports[0]}/callback?code=abc&state=xyz", timeout=5) as page:
        assert page.status == 200
    thread.join(5)

    assert result == [{"code": "abc", "state": "xyz"}]


@pytest.mark.parametrize("host", ["192.0.2.1", "localhost", "::", ""])
def test_given_a_host_that_is_neither_loopback_nor_the_container_wildcard_when_receiving_then_it_is_refused(
    host: str,
) -> None:
    with pytest.raises(ConsentError):
        receive_redirect(host, 0, timeout=1, on_ready=lambda _port: None)


# -- U-76: the callback server inside the agent container ----------------------------------------------------------


def test_given_no_setting_when_the_bind_host_is_read_then_it_is_the_loopback() -> None:
    assert consent_bind_host({}) == "127.0.0.1"
    assert consent_bind_host({"CONSENT_BIND_HOST": ""}) == "127.0.0.1"


def test_given_the_container_setting_when_the_bind_host_is_read_then_it_is_the_wildcard() -> None:
    assert consent_bind_host({"CONSENT_BIND_HOST": "0.0.0.0"}) == "0.0.0.0"  # noqa: S104


@pytest.mark.parametrize("value", ["192.0.2.1", "localhost", "::", "0.0.0.0/0", "127.0.0.1 "])
def test_given_any_other_bind_host_when_read_then_it_is_refused_without_echoing_a_secret(value: str) -> None:
    with pytest.raises(ConsentError, match="CONSENT_BIND_HOST"):
        consent_bind_host({"CONSENT_BIND_HOST": value})


def test_given_the_container_setting_when_the_redirect_uri_is_built_then_google_sees_the_registered_loopback() -> None:
    assert REDIRECT_URI == "http://127.0.0.1:8765/callback"
    assert parse_qs(urlparse(authorization_request("cid", REDIRECT_URI).url).query)["redirect_uri"] == [REDIRECT]


def test_given_a_wildcard_server_when_the_browser_calls_back_on_the_loopback_then_the_query_is_received() -> None:
    result: list[dict[str, str]] = []
    ready, ports = threading.Event(), []

    def serve() -> None:
        result.append(
            receive_redirect("0.0.0.0", 0, timeout=5, on_ready=lambda port: (ports.append(port), ready.set()))  # noqa: S104
        )

    thread = threading.Thread(target=serve)
    thread.start()
    assert ready.wait(5)
    with urllib.request.urlopen(f"http://127.0.0.1:{ports[0]}/callback?code=abc&state=xyz", timeout=5) as page:
        assert page.status == 200
    thread.join(5)

    assert result == [{"code": "abc", "state": "xyz"}]


def test_given_no_browser_when_the_wait_ends_then_the_one_shot_server_gives_up_with_a_clear_error() -> None:
    assert WAIT_SECONDS == 300
    with pytest.raises(ConsentError, match="no redirect arrived in time"):
        receive_redirect("0.0.0.0", 0, timeout=0.2, on_ready=lambda _port: None)  # noqa: S104


def test_given_the_authorisation_url_when_prompted_then_the_url_is_the_only_value_printed_and_it_is_flushed() -> None:
    url = authorization_request("cid", REDIRECT).url

    class Terminal(io.StringIO):
        flushed = 0

        def flush(self) -> None:
            self.flushed += 1
            super().flush()

    out = Terminal()
    prompt_for_url(url, out)

    assert url in out.getvalue()
    assert out.flushed >= 1
    for secret in (SECRET, CODE, REFRESH):
        assert secret not in out.getvalue()
    assert "client_secret" not in out.getvalue()
    # nothing but the instruction line and the address itself
    assert [line for line in out.getvalue().splitlines() if line.strip() and url not in line] == [
        "Open this address in your browser and grant access:"
    ]
