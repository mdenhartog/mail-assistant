"""U-17: logs and error reports never carry mail text, tokens or the API key (AC-14, AC-24; threat model T-09)."""

from __future__ import annotations

import logging

from app.obs.redaction import REDACTED, RedactionFilter, Redactor, sentry_before_send

API_KEY = "plain-api-key-value-123"
BOT_TOKEN = "123456:AAH-bot_token-Value"  # noqa: S105


def make_logger() -> tuple[logging.Logger, list[logging.LogRecord]]:
    records: list[logging.LogRecord] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            self.format(record)
            records.append(record)

    logger = logging.getLogger(f"test-{id(records)}")
    logger.handlers = [Capture()]
    logger.filters = [RedactionFilter(Redactor([API_KEY, BOT_TOKEN]))]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger, records


def test_given_a_log_record_with_a_mail_body_when_emitted_then_the_body_is_replaced() -> None:
    logger, records = make_logger()

    logger.info("processed mail %s", "m1", extra={"mail_body": "Dear Marco, my IBAN is NL00BANK0123456789"})

    assert records[0].mail_body == REDACTED  # type: ignore[attr-defined]
    assert "IBAN" not in records[0].getMessage()


def test_given_a_telegram_url_with_the_bot_token_when_logged_then_the_token_is_masked() -> None:
    logger, records = make_logger()

    logger.info("POST https://api.telegram.org/bot%s/sendMessage", BOT_TOKEN)
    logger.info("GET https://api.telegram.org/bot999999:SomeOtherToken-xyz/getUpdates")

    for record in records:
        message = record.getMessage()
        assert "AAH-bot_token-Value" not in message
        assert "SomeOtherToken" not in message
        assert "api.telegram.org/bot" in message
    assert "sendMessage" in records[0].getMessage()


def test_given_known_secrets_and_key_shapes_when_scrubbed_then_they_are_replaced_wherever_they_appear() -> None:
    redactor = Redactor([API_KEY])

    text = redactor.scrub(f"key={API_KEY} and sk-ant-api03-abcDEF_123-xyz and Authorization: Bearer abc.def.ghi")

    assert API_KEY not in text
    assert "sk-ant-api03" not in text
    assert "abc.def.ghi" not in text


def test_given_an_exception_with_the_api_key_when_sent_to_sentry_then_the_key_is_scrubbed() -> None:
    event = {
        "message": f"call failed with {API_KEY}",
        "exception": {"values": [{"type": "RuntimeError", "value": f"bad key {API_KEY}"}]},
        "breadcrumbs": {"values": [{"message": f"GET /bot{BOT_TOKEN}/getUpdates"}]},
        "request": {"url": f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"},
    }

    cleaned = sentry_before_send(Redactor([API_KEY, BOT_TOKEN]))(event, {})

    assert cleaned is not None
    dumped = str(cleaned)
    assert API_KEY not in dumped
    assert BOT_TOKEN not in dumped
    assert "RuntimeError" in dumped


def test_given_a_sentry_event_with_local_variables_when_sent_then_all_variable_values_are_removed() -> None:
    event = {
        "exception": {
            "values": [
                {
                    "type": "ValueError",
                    "value": "boom",
                    "stacktrace": {
                        "frames": [{"function": "judge", "lineno": 3, "vars": {"body": "secret mail text"}}]
                    },
                }
            ]
        }
    }

    cleaned = sentry_before_send(Redactor([]))(event, {})

    assert cleaned is not None
    frame = cleaned["exception"]["values"][0]["stacktrace"]["frames"][0]
    assert "vars" not in frame
    assert frame["function"] == "judge"
    assert "secret mail text" not in str(cleaned)


def test_given_normal_log_lines_when_emitted_then_ids_and_counts_stay_readable() -> None:
    logger, records = make_logger()

    logger.info("filed mail %s under %s (%d of %d)", "18c3f2a", "Assistant/Finance", 3, 10)

    assert records[0].getMessage() == "filed mail 18c3f2a under Assistant/Finance (3 of 10)"
