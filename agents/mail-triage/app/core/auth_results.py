"""Read SPF, DKIM and DMARC results from an ``Authentication-Results`` header.

Only the results the receiving server wrote at the start of each ``;`` separated part count, so text inside a comment
or a value cannot forge a result for another method. The first result per method wins.
"""

from __future__ import annotations

import re

from app.core.alert_text import AuthResults

_PART = re.compile(r"^\s*(?P<method>spf|dkim|dmarc)\s*=\s*(?P<result>[a-z]+)", re.IGNORECASE)


def parse_auth_results(header: str | None) -> AuthResults:
    """The three results, ``None`` for a method that is absent or unreadable."""
    found: dict[str, str] = {}
    for part in (header or "").split(";"):
        match = _PART.match(part)
        if match:
            found.setdefault(match.group("method").lower(), match.group("result").lower())
    return AuthResults(spf=found.get("spf"), dkim=found.get("dkim"), dmarc=found.get("dmarc"))
