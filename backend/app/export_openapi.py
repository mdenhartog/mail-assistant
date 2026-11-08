"""Export the OpenAPI document that the API reference (``docs/api``) is generated from.

Run ``uv run python -m app.export_openapi`` to write ``docs/api/openapi.json`` (the path is resolved
from the repository root) or add ``--check`` to fail when the file on disk is out of date.
"""

import argparse
import json
import sys
from pathlib import Path

from app.config import Settings
from app.main import create_app

DEFAULT_TARGET = Path(__file__).resolve().parents[2] / "docs" / "api" / "openapi.json"


def build_document() -> str:
    """Render the OpenAPI document of the application as stable JSON.

    Returns:
        The document with sorted keys, two-space indentation and a trailing newline.
    """
    app = create_app(Settings(environment="test"))
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
