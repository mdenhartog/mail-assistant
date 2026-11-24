"""``FakeGmail`` with the plan build's search modelled for managed labels (U-label-prefix-removal-05).

The base double answers every query it does not know with all mail. The build now searches
``(in:inbox OR label:"name" ...) -in:sent``, so this subclass models that shape (a label term also matches the labels
below it, as Gmail does) and records the queries. Spam and trash are never searched; ``-in:sent`` leaves sent mail out.
"""

from __future__ import annotations

import re
from typing import Any

from tests.fakes.fake_gmail import FakeGmail

_LABEL_TERM = re.compile(r'label:"([^"]*)"')


class QueryGmail(FakeGmail):
    """A Gmail double that understands ``in:inbox``, ``label:"name"`` and ``-in:sent``."""

    def __init__(self) -> None:
        super().__init__()
        self.queries: list[str] = []

    def answers_query(self, query: str, mail: Any) -> bool:
        self.queries.append(query)
        if {"SPAM", "TRASH"} & mail.labels or ("SENT" in mail.labels and "-in:sent" in query):
            return False
        wanted = [name.casefold() for name in _LABEL_TERM.findall(query)]
        names = [self.label_table[i].casefold() for i in mail.labels]
        by_label = any(n == w or n.startswith(f"{w}/") for w in wanted for n in names)
        if "in:inbox" not in query and not wanted:
            return True  # the wide search: everything that is not spam, trash or sent
        return ("in:inbox" in query and "INBOX" in mail.labels) or by_label
