"""U-web-settings-79: the log check of the prod-like job must not mistake a number inside a longer number for a code.

`scripts/prodlike-checks.sh logs` greps the logs of the stack for the values that must never be logged. A sign-in code
has six digits, so a plain text match finds it by chance inside a response time such as 0.007834233 (it did, in CI).
The matching lives in `log_files_matching`, which these tests call on small log files.
"""

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prodlike-checks.sh"

EDGE_LINE = '{"msg":"handled request","ts":1795208747.4274948,"duration":0.007834233,"size":169,"status":200}'


def files_matching(tmp_path: Path, kind: str, value: str, log_text: str) -> list[str]:
    """The names of the log files in tmp_path that the check would report for this value."""
    bash = shutil.which("bash")
    assert bash is not None, "the log check is a bash script; bash must be on the PATH"
    (tmp_path / "edge.log").write_text(log_text + "\n", encoding="utf-8")
    (tmp_path / "api.log").write_text("nothing to see\n", encoding="utf-8")
    command = 'PRODLIKE_CHECKS_SOURCE_ONLY=1 source "$1" && log_files_matching "$2" "$3" "$4"'
    result = subprocess.run(  # noqa: S603  # fixed script and arguments, no shell input from outside
        [bash, "-c", command, "log-check", SCRIPT.as_posix(), kind, value, tmp_path.as_posix()],
        capture_output=True,
        text=True,
        check=True,
    )
    return [Path(line).name for line in result.stdout.splitlines() if line]


@pytest.mark.parametrize("kind", ["canary", "sign-in-code"])
def test_given_a_code_inside_a_response_time_when_checked_then_it_is_not_a_hit(tmp_path: Path, kind: str) -> None:
    assert files_matching(tmp_path, kind, "007834", EDGE_LINE) == []


@pytest.mark.parametrize("kind", ["canary", "sign-in-code"])
@pytest.mark.parametrize(
    "line",
    [
        "your code is 007834",
        'GET /verify?c=007834 HTTP/2.0 "007834"',
        "007834",
        "code:007834,",
    ],
)
def test_given_a_code_that_stands_alone_when_checked_then_it_is_a_hit(tmp_path: Path, kind: str, line: str) -> None:
    assert files_matching(tmp_path, kind, "007834", line) == ["edge.log"]


def test_given_a_username_canary_inside_a_longer_word_when_checked_then_it_is_still_a_hit(tmp_path: Path) -> None:
    # Only numbers need whole-number matching; a text secret must be found wherever it sits.
    assert files_matching(tmp_path, "canary", "canary-user", "user=xcanary-user1&") == ["edge.log"]
