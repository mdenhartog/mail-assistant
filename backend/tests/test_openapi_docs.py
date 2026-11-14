"""U-web-settings-60: the verify-code description matches AC-3 and the generated API file is current."""

import json
from pathlib import Path

from app.export_openapi import build_document

COMMITTED = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json"


def _verify_400() -> str:
    document = json.loads(build_document())
    return document["paths"]["/auth/verify-code"]["post"]["responses"]["400"]["description"]


def test_given_the_verify_code_route_when_described_then_attempts_left_covers_real_and_decoy_requests() -> None:
    description = _verify_400()

    assert "attemptsLeft" in description
    assert "real or decoy" in description
    assert "live request" not in description


def test_given_the_committed_openapi_file_when_compared_with_the_app_then_it_is_current() -> None:
    assert COMMITTED.read_text(encoding="utf-8") == build_document()
