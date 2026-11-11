import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"
ALLOWED = {"clock.py", "ids.py", "codes.py"}

# (module, attribute) pairs; "*" matches any attribute of the module.
FORBIDDEN_ATTRIBUTES = {
    ("datetime", "now"),
    ("datetime", "utcnow"),
    ("time", "time"),
    ("date", "today"),
    ("uuid", "uuid4"),
    ("random", "*"),
    ("secrets", "*"),
}
FORBIDDEN_BARE = {"uuid4"}
FORBIDDEN_IMPORTED_MODULES = {"random", "secrets"}


def _dotted(node: ast.expr) -> list[str]:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return list(reversed(parts))


def find_violations(source: str) -> list[str]:
    """Return the forbidden time and randomness calls found in the source."""
    tree = ast.parse(source)
    imported_from_forbidden: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in FORBIDDEN_IMPORTED_MODULES:
            imported_from_forbidden.update(alias.asname or alias.name for alias in node.names)
    found: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        parts = _dotted(node.func)
        if len(parts) >= 2 and (
            (parts[-2], parts[-1]) in FORBIDDEN_ATTRIBUTES or (parts[-2], "*") in FORBIDDEN_ATTRIBUTES
        ):
            found.append(".".join(parts))
        elif len(parts) == 1 and (parts[0] in FORBIDDEN_BARE or parts[0] in imported_from_forbidden):
            found.append(parts[0])
    return found


def test_app_modules_use_time_and_randomness_only_through_the_sources() -> None:
    offenders: dict[str, list[str]] = {}
    for path in APP_DIR.rglob("*.py"):
        if path.name in ALLOWED:
            continue
        violations = find_violations(path.read_text(encoding="utf-8"))
        if violations:
            offenders[str(path.relative_to(APP_DIR))] = violations
    assert offenders == {}


def test_the_allowed_modules_exist_and_do_use_the_sources() -> None:
    for name in ALLOWED:
        assert (APP_DIR / name).is_file()
    assert find_violations((APP_DIR / "clock.py").read_text(encoding="utf-8")) == ["datetime.now"]
    assert find_violations((APP_DIR / "ids.py").read_text(encoding="utf-8")) == ["secrets.token_urlsafe"]
    assert find_violations((APP_DIR / "codes.py").read_text(encoding="utf-8")) == ["secrets.randbelow"]


def test_a_planted_call_is_detected() -> None:
    planted = [
        ("import datetime\ndatetime.datetime.now()", "datetime.datetime.now"),
        ("from datetime import datetime\ndatetime.utcnow()", "datetime.utcnow"),
        ("import time\ntime.time()", "time.time"),
        ("from datetime import date\ndate.today()", "date.today"),
        ("import uuid\nuuid.uuid4()", "uuid.uuid4"),
        ("from uuid import uuid4\nuuid4()", "uuid4"),
        ("import random\nrandom.choice([1])", "random.choice"),
        ("import secrets\nsecrets.token_hex(4)", "secrets.token_hex"),
        ("from secrets import token_hex\ntoken_hex(4)", "token_hex"),
    ]
    for source, expected in planted:
        assert find_violations(source) == [expected], source


def test_a_clean_module_has_no_violations() -> None:
    assert find_violations("import hmac\nhmac.compare_digest(b'a', b'a')") == []
