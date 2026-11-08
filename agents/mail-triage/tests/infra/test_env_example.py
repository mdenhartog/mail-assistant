"""``.env.example`` documents every setting of mail-triage, and the compose service passes every one on."""

from __future__ import annotations

import re
from pathlib import Path

import yaml

from app.settings import Settings

ROOT = Path(__file__).resolve().parents[4]
EXAMPLE = (ROOT / ".env.example").read_text(encoding="utf-8")
COMPOSE = yaml.safe_load((ROOT / "agents" / "mail-triage" / "compose.yaml").read_text(encoding="utf-8"))
ENVIRONMENT: dict[str, str] = COMPOSE["services"]["mail-triage"]["environment"]
SECRET_SHAPES = (
    re.compile(r"sk-ant-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{30,}\b"),
    re.compile(r"GOCSPX-[A-Za-z0-9_-]+"),
)


def documented(name: str) -> bool:
    """The variable has a line in the example, active or as a commented default."""
    return re.search(rf"^#?\s*{re.escape(name)}=", EXAMPLE, re.MULTILINE) is not None


def test_given_the_settings_when_compared_then_the_compose_service_passes_every_one_on() -> None:
    assert {name.upper() for name in Settings.model_fields} <= set(ENVIRONMENT)


def test_given_the_compose_variables_when_compared_then_each_host_variable_is_documented_in_the_example() -> None:
    host_variables = {match for value in ENVIRONMENT.values() for match in re.findall(r"\$\{([A-Z_]+)", value)}

    missing = sorted(name for name in host_variables if not documented(name))

    assert not missing, f".env.example lacks: {missing}"


def test_given_the_example_when_read_then_it_holds_no_real_secret_and_explains_the_hard_parts() -> None:
    for pattern in SECRET_SHAPES:
        assert not pattern.search(EXAMPLE), pattern.pattern
    for hint in ("BotFather", "Fernet", "python -m app.consent", "userinfobot"):
        assert hint in EXAMPLE, f"the example should explain: {hint}"


def test_given_the_required_settings_when_listed_then_the_example_lines_are_empty_not_filled() -> None:
    for name in ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "GOOGLE_CLIENT_SECRET", "MAIL_TRIAGE_TOKEN_ENCRYPTION_KEY"):
        assert re.search(rf"^{name}=$", EXAMPLE, re.MULTILINE), f"{name} must be an empty placeholder"
