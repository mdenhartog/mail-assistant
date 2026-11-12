"""U-web-settings-24: the in-process guard, the client address and the body limit through the whole app (api level)."""

import ast
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.core.security import public
from app.limit_guard import InProcessLimitGuard, limit
from tests.fakes import FakeClock, make_app, make_settings

PROXY = "10.42.1.7"
APP = Path(__file__).resolve().parents[1] / "app"


class RecordingEvents:
    """Stands in for the security event store: remembers what was recorded."""

    def __init__(self) -> None:
        self.recorded: list[tuple[str, str, str]] = []

    async def record(self, kind: str, request_id: str, client: str, username_hash: str | None = None) -> None:
        self.recorded.append((kind, request_id, client))


def _build(**overrides: object) -> tuple[FastAPI, FakeClock, RecordingEvents]:
    app = make_app(make_settings(**overrides))
    clock: FakeClock = app.state.clock
    events = RecordingEvents()
    app.state.security_events = events
    calls: list[int] = []
    app.state.parsed = calls

    @app.get("/t/signin", dependencies=[Depends(public), Depends(limit("signin"))])
    async def signin() -> dict[str, str]:
        return {"ok": "signin"}

    @app.get("/t/api", dependencies=[Depends(public), Depends(limit("api"))])
    async def api() -> dict[str, str]:
        return {"ok": "api"}

    @app.post("/t/echo", dependencies=[Depends(public)])
    async def echo(payload: dict[str, str]) -> dict[str, int]:
        calls.append(1)
        return {"keys": len(payload)}

    @app.post("/t/raw", dependencies=[Depends(public)])
    async def raw(request: Request) -> dict[str, int]:
        length = len(await request.body())
        calls.append(1)
        return {"length": length}

    return app, clock, events


def _http(app: FastAPI, peer: str = "203.0.113.50") -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app, client=(peer, 5000)), base_url="http://test")


def _json_of_size(size: int) -> bytes:
    prefix, suffix = b'{"a":"', b'"}'
    return prefix + b"x" * (size - len(prefix) - len(suffix)) + suffix


# ---- criterion 1: the window edge ----


async def test_given_30_requests_when_the_31st_arrives_then_429_with_an_integer_retry_after() -> None:
    app, clock, _ = _build()
    async with _http(app) as http:
        statuses = [(await http.get("/t/signin")).status_code for _ in range(30)]
        refused = await http.get("/t/signin")

    assert statuses == [200] * 30
    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "60"
    assert refused.json() == {"type": "about:blank", "title": "Too many requests", "status": 429}
    assert clock.now().second == 0


async def test_given_a_full_window_when_59_9_seconds_pass_then_still_refused_and_at_60_a_new_one_passes() -> None:
    app, clock, _ = _build(rate_limit_per_minute=2)
    async with _http(app) as http:
        for _ in range(2):
            assert (await http.get("/t/signin")).status_code == 200
        clock.advance(timedelta(seconds=59.9))
        late = await http.get("/t/signin")
        clock.advance(timedelta(seconds=0.1))
        fresh = await http.get("/t/signin")

    assert late.status_code == 429
    assert late.headers["retry-after"] == "1"
    assert fresh.status_code == 200


# ---- criterion 2: buckets are separate ----


async def test_given_the_api_bucket_is_exhausted_when_the_signin_bucket_is_used_then_it_still_passes() -> None:
    app, _, _ = _build(rate_limit_per_minute=3)
    async with _http(app) as http:
        api = [(await http.get("/t/api")).status_code for _ in range(4)]
        signin = [(await http.get("/t/signin")).status_code for _ in range(4)]

    assert api == [200, 200, 200, 429]
    assert signin == [200, 200, 200, 429]


async def test_given_two_clients_when_one_is_exhausted_then_the_other_passes() -> None:
    app, _, _ = _build(rate_limit_per_minute=1)
    async with _http(app, "203.0.113.50") as first, _http(app, "203.0.113.51") as second:
        assert (await first.get("/t/api")).status_code == 200
        assert (await first.get("/t/api")).status_code == 429
        assert (await second.get("/t/api")).status_code == 200


# ---- criterion 4 at api level: the key is the real client ----


async def test_given_a_trusted_proxy_when_the_leftmost_value_changes_then_the_bucket_is_the_same() -> None:
    app, _, events = _build(rate_limit_per_minute=2, trusted_proxy_cidrs=["10.42.0.0/16"])
    async with _http(app, PROXY) as http:
        statuses = [
            (await http.get("/t/api", headers={"X-Forwarded-For": f"{spoof}, 203.0.113.9"})).status_code
            for spoof in ("1.1.1.1", "2.2.2.2", "3.3.3.3")
        ]
        other = await http.get("/t/api", headers={"X-Forwarded-For": "1.1.1.1, 203.0.113.10"})

    assert statuses == [200, 200, 429]
    assert other.status_code == 200
    assert [client for _, _, client in events.recorded] == ["203.0.113.9"]


async def test_given_two_forwarded_headers_when_keyed_then_they_count_as_one_list() -> None:
    app, _, _ = _build(rate_limit_per_minute=1, trusted_proxy_cidrs=["10.42.0.0/16"])
    async with _http(app, PROXY) as http:
        first = await http.get("/t/api", headers=[("X-Forwarded-For", "1.1.1.1"), ("X-Forwarded-For", "203.0.113.9")])
        second = await http.get("/t/api", headers=[("X-Forwarded-For", "2.2.2.2"), ("X-Forwarded-For", "203.0.113.9")])

    assert (first.status_code, second.status_code) == (200, 429)


async def test_given_an_untrusted_peer_when_it_sends_the_header_then_its_own_address_is_the_key() -> None:
    app, _, events = _build(rate_limit_per_minute=1, trusted_proxy_cidrs=["10.42.0.0/16"])
    async with _http(app, "198.51.100.4") as http:
        first = await http.get("/t/api", headers={"X-Forwarded-For": "1.1.1.1"})
        second = await http.get("/t/api", headers={"X-Forwarded-For": "2.2.2.2"})

    assert (first.status_code, second.status_code) == (200, 429)
    assert [client for _, _, client in events.recorded] == ["198.51.100.4"]


# ---- criterion 6 without a database: one event per client and window ----


async def test_given_a_flood_when_refused_then_one_event_is_recorded_per_client_and_window() -> None:
    app, clock, events = _build(rate_limit_per_minute=2)
    async with _http(app) as http:
        for _ in range(10):
            await http.get("/t/api")
        for _ in range(5):
            await http.get("/t/signin")
        first_window = list(events.recorded)
        clock.advance(timedelta(seconds=60))
        for _ in range(10):
            await http.get("/t/api")

    assert [(kind, client) for kind, _, client in first_window] == [
        ("rate_limited", "203.0.113.50"),
        ("rate_limited", "203.0.113.50"),
    ]
    assert len(events.recorded) == 3
    assert all(request_id for _, request_id, _ in events.recorded)


async def test_given_no_event_store_when_a_request_is_refused_then_it_is_still_a_429() -> None:
    app, _, _ = _build(rate_limit_per_minute=1)
    del app.state.security_events
    async with _http(app) as http:
        await http.get("/t/api")
        refused = await http.get("/t/api")

    assert refused.status_code == 429


# ---- criterion 7: limits come from the settings ----


async def test_given_a_lowered_limit_and_window_in_the_settings_when_the_guard_runs_then_they_take_effect() -> None:
    app, clock, _ = _build(rate_limit_per_minute=3, rate_window_seconds=10)
    async with _http(app) as http:
        first = [(await http.get("/t/api")).status_code for _ in range(4)]
        clock.advance(timedelta(seconds=10))
        later = (await http.get("/t/api")).status_code

    assert first == [200, 200, 200, 429]
    assert later == 200


def test_given_the_build_when_the_guard_is_read_then_it_is_the_in_process_guard() -> None:
    app, _, _ = _build()

    assert isinstance(app.state.limit_guard, InProcessLimitGuard)


def test_given_the_app_modules_when_read_then_the_body_limit_number_is_defined_only_in_the_settings() -> None:
    offenders = [
        path.relative_to(APP).as_posix()
        for path in APP.rglob("*.py")
        if path.name != "config.py"
        and any(
            isinstance(node, ast.Constant) and node.value == 8192
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        )
    ]

    assert offenders == []


# ---- criterion 5: the body limit ----


async def test_given_bodies_of_8192_and_8193_bytes_when_sent_then_accepted_and_413_and_not_parsed() -> None:
    app, _, _ = _build()
    parsed: list[int] = app.state.parsed
    async with _http(app) as http:
        ok = await http.post("/t/echo", content=_json_of_size(8192), headers={"Content-Type": "application/json"})
        calls_after_ok = len(parsed)
        big = await http.post("/t/echo", content=_json_of_size(8193), headers={"Content-Type": "application/json"})

    assert ok.status_code == 200
    assert ok.json() == {"keys": 1}
    assert big.status_code == 413
    assert big.json() == {"type": "about:blank", "title": "Payload too large", "status": 413}
    assert big.headers["content-type"] == "application/problem+json"
    assert big.headers["x-request-id"]
    assert len(parsed) == calls_after_ok == 1


async def test_given_a_chunked_body_over_the_limit_when_sent_then_413_and_the_handler_never_runs() -> None:
    app, _, _ = _build()
    parsed: list[int] = app.state.parsed

    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(9):
            yield b"x" * 1024

    async with _http(app) as http:
        response = await http.post("/t/raw", content=chunks())

    assert response.status_code == 413
    assert parsed == []


async def test_given_a_chunked_body_within_the_limit_when_sent_then_it_is_accepted() -> None:
    app, _, _ = _build()

    async def chunks() -> AsyncIterator[bytes]:
        for _ in range(8):
            yield b"x" * 1024

    async with _http(app) as http:
        response = await http.post("/t/raw", content=chunks())

    assert response.status_code == 200
    assert response.json() == {"length": 8192}


async def test_given_a_lowered_body_limit_in_the_settings_when_sent_then_it_takes_effect() -> None:
    app, _, _ = _build(body_limit_bytes=100)
    async with _http(app) as http:
        ok = await http.post("/t/raw", content=b"x" * 100)
        big = await http.post("/t/raw", content=b"x" * 101)

    assert (ok.status_code, big.status_code) == (200, 413)


async def test_given_a_wrong_content_length_header_when_sent_then_400_and_nothing_runs() -> None:
    app, _, _ = _build()
    parsed: list[int] = app.state.parsed
    async with _http(app) as http:
        response = await http.post("/t/raw", content=b"x", headers={"Content-Length": "lots"})

    assert response.status_code == 400
    assert parsed == []


async def test_given_the_sign_in_route_when_the_body_is_over_the_limit_then_413_before_any_limit_is_counted() -> None:
    app, _, events = _build(rate_limit_per_minute=1)
    async with _http(app) as http:
        big = await http.post(
            "/auth/verify-code", content=b"x" * 8193, headers={"Origin": "https://settings.example.test"}
        )
        again = await http.get("/t/signin")

    assert big.status_code == 413
    assert again.status_code == 200
    assert events.recorded == []
