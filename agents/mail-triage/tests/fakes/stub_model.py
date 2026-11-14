"""A judging model double that replays scripted answers, including a hostile-output corpus."""

from __future__ import annotations

from typing import Self

# What a manipulated or broken model may return where a single known category id is expected.
HOSTILE_CORPUS: tuple[str, ...] = (
    "cat-9999",  # an unknown id
    "cat-1 cat-2",  # two ids
    "<script>alert(1)</script> <b>cat-1</b>",  # markup
    "approve",  # an instruction word, not a category
    "",  # empty
    "x" * 1001,  # one character over the 1 000 limit
)


class StubModel:
    """Returns the scripted answers in order; asking beyond the script fails loudly."""

    def __init__(self, answers: list[str]) -> None:
        self._answers = list(answers)
        self.prompts: list[str] = []

    @classmethod
    def hostile(cls) -> Self:
        """A model that answers with the hostile corpus, in order."""
        return cls(list(HOSTILE_CORPUS))

    def answer(self, prompt: str) -> str:
        """The next scripted answer; the prompt is kept so tests can assert what the model saw."""
        self.prompts.append(prompt)
        if not self._answers:
            raise AssertionError("no scripted answer left for the stub model")
        return self._answers.pop(0)
