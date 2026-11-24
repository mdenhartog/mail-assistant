"""INT-010 U-18: the two mail errors live in a neutral module, so the adapter never imports a use case (cycle fix)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from app.core import mail_errors
from app.usecases import resort_apply

ROOT = Path(__file__).resolve().parents[1]


def test_the_errors_keep_their_names_and_the_use_case_still_exports_them() -> None:
    assert mail_errors.MailFailed is resort_apply.MailFailed
    assert mail_errors.MailGone is resort_apply.MailGone
    assert issubclass(mail_errors.MailFailed, Exception)
    assert not issubclass(mail_errors.MailGone, mail_errors.MailFailed)


def test_the_adapter_imports_without_loading_the_apply_use_case() -> None:
    code = (
        "import sys; import app.adapters.gmail_apply; sys.exit(1 if 'app.usecases.resort_apply' in sys.modules else 0)"
    )

    done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=False, capture_output=True, text=True)  # noqa: S603

    assert done.returncode == 0, done.stderr
