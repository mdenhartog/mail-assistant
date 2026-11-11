"""Export the OpenAPI document that the API reference (``docs/api``) is generated from.

Run ``uv run python -m app.export_openapi`` to write ``docs/api/openapi.json`` (the path is resolved
from the repository root) or add ``--check`` to fail when the file on disk is out of date.
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from pydantic import SecretStr

from app.clock import SystemClock
from app.codes import SecretsCodeSource
from app.config import Settings
from app.ids import SecretsIdSource
from app.main import create_app

DEFAULT_TARGET = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json"


class _NoMailer:
    """Mailer for the export: the document is built, no request is served."""

    async def send_code(self, _address: str, _code: str, _expires_at: datetime, /) -> None:
        raise NotImplementedError


def _document_settings() -> Settings:
    """Placeholder configuration that passes the start-up check; it never leaves this process."""
    return Settings(
        environment="test",
        username="export",
        email_address="export@example.invalid",
        smtp_host="smtp.example.invalid",
        smtp_port=587,
        smtp_user="export",
        smtp_password=SecretStr("export"),
        code_hash_key=SecretStr("a" * 32),
        csrf_key=SecretStr("b" * 32),
        username_hash_key=SecretStr("c" * 32),
        public_origin="https://export.example.invalid",
    )


def build_document() -> str:
    """Render the OpenAPI document of the application as stable JSON.

    Returns:
        The document with sorted keys, two-space indentation and a trailing newline.
    """
    app = create_app(
        _document_settings(), clock=SystemClock(), ids=SecretsIdSource(), codes=SecretsCodeSource(), mailer=_NoMailer()
    )
    return json.dumps(app.openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write the document, or with ``--check`` compare it with the file on disk.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv``.

    Returns:
        ``0`` when the file was written or is current, ``1`` when ``--check`` finds it stale or missing.
    """
    parser = argparse.ArgumentParser(description="Export the OpenAPI document.")
    parser.add_argument("target", nargs="?", type=Path, default=DEFAULT_TARGET)
    parser.add_argument("--check", action="store_true", help="fail when the file is not up to date")
    args = parser.parse_args(argv)
    document = build_document()
    if args.check:
        current = args.target.read_text(encoding="utf-8") if args.target.exists() else None
        if current == document:
            return 0
        sys.stderr.write(f"{args.target} is out of date: run 'node scripts/docs.mjs api'\n")
        return 1
    args.target.parent.mkdir(parents=True, exist_ok=True)
    args.target.write_text(document, encoding="utf-8", newline="\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
