"""The production application factory: the running api with every part attached (U-web-settings-38).

``uvicorn app.production:create_production_app --factory`` runs it. The settings come from the environment; a wrong
configuration stops the start naming the fields (AC-4), before any connection is opened.
"""

from datetime import timedelta

from fastapi import FastAPI

from app.auth.login_requests import LoginRequests
from app.auth.request_code import attach_request_code
from app.auth.session import SessionStore, attach_sessions
from app.auth.verify_code import attach_verify_code
from app.clock import SystemClock
from app.codes import SecretsCodeSource
from app.config import get_settings
from app.db import Database
from app.ids import SecretsIdSource
from app.mail.smtp import SmtpMailSender
from app.main import build_app
from app.security_events import SecurityEvents
from app.startup import attach_database


def create_production_app() -> FastAPI:
    """Build the running api from the environment.

    Returns:
        The application with its database, stores, mail sender and use cases attached.

    Raises:
        ConfigurationError: Raised by the start-up check, naming the offending fields and no value.
    """
    settings = get_settings()
    clock = SystemClock()
    ids = SecretsIdSource()
    app = build_app(settings, clock=clock, ids=ids, codes=SecretsCodeSource(), mailer=SmtpMailSender(settings, clock))
    database = Database.from_settings(settings)
    events = SecurityEvents(database, clock, settings.username_hash_key.get_secret_value().encode("utf-8"))
    logins = LoginRequests(
        database,
        ids,
        hash_key=settings.code_hash_key.get_secret_value().encode("utf-8"),
        ttl=timedelta(seconds=settings.code_ttl_seconds),
        max_attempts=settings.max_attempts,
    )
    sessions = SessionStore(database, ids, events)
    attach_database(app, database, clock, idle=timedelta(seconds=settings.idle_seconds))
    attach_sessions(app, sessions, events)
    attach_request_code(app, logins, events)
    attach_verify_code(app, logins, sessions, events)
    return app
