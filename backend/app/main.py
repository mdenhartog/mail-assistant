"""FastAPI application factory."""

import importlib
import pkgutil
from dataclasses import dataclass

from fastapi import APIRouter, FastAPI

from app import routers
from app.clock import Clock
from app.codes import CodeSource
from app.config import Settings, get_settings
from app.errors import install_error_handlers
from app.ids import IdSource
from app.limit_guard import NoopLimitGuard
from app.logging_setup import configure_logging
from app.mail.sender import MailSender
from app.middleware import HttpSurfaceMiddleware
from app.settings_models import declare_write_schemas
from app.startup import validate_startup

API_PREFIX = "/api"


@dataclass(frozen=True)
class MountedRouter:
    """A router module discovered in ``app.routers`` and the prefix it is mounted under."""

    prefix: str
    router: APIRouter


def discover_routers() -> list[MountedRouter]:
    """Find every module in ``app.routers`` that exposes a ``router``; business routes live under ``/api``.

    A router module may set ``ROUTER_PREFIX`` to override the prefix (the health probes use ``""``).

    Returns:
        The discovered routers in module-name order.
    """
    mounted: list[MountedRouter] = []
    for module_info in sorted(pkgutil.iter_modules(routers.__path__), key=lambda m: m.name):
        module = importlib.import_module(f"{routers.__name__}.{module_info.name}")
        mounted.append(MountedRouter(prefix=getattr(module, "ROUTER_PREFIX", API_PREFIX), router=module.router))
    return mounted


def build_app(settings: Settings, *, clock: Clock, ids: IdSource, codes: CodeSource, mailer: MailSender) -> FastAPI:
    """Build the FastAPI application after the start-up check.

    Args:
        settings: The settings to use.
        clock: Source of the current time.
        ids: Source of tokens and ids.
        codes: Source of sign-in codes.
        mailer: Port that sends the sign-in code.

    Returns:
        The configured application.
    """
    validate_startup(settings)
    configure_logging()
    app = FastAPI(
        title=settings.app_name,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    app.state.settings = settings
    app.state.clock = clock
    app.state.ids = ids
    app.state.codes = codes
    app.state.mailer = mailer
    app.state.limit_guard = NoopLimitGuard()  # replaced by the real guard in U-web-settings-24
    install_error_handlers(app)
    app.add_middleware(HttpSurfaceMiddleware, ids=ids)
    for mounted in discover_routers():
        app.include_router(mounted.router, prefix=mounted.prefix)
    declare_write_schemas(app)
    return app


def create_app() -> FastAPI:
    """Build the health-only application that ``uvicorn app.main:create_app --factory`` runs today.

    Legacy: kept so the ``api`` image keeps starting with only ``APP_ENVIRONMENT``. It does not run the
    start-up check. It is replaced by the production factory when the api service gets its ``APP_*`` values
    (U-web-settings-38); removing it is a criterion of that unit. Use ``build_app`` everywhere else.

    Returns:
        The application configured from the environment.
    """
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    for mounted in discover_routers():
        app.include_router(mounted.router, prefix=mounted.prefix)
    return app
