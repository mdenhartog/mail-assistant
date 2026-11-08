"""FastAPI application factory."""

import importlib
import pkgutil
from dataclasses import dataclass

from fastapi import APIRouter, FastAPI

from app import routers
from app.config import Settings, get_settings

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


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the FastAPI application.

    Args:
        settings: Settings to use; defaults to the environment-based settings.

    Returns:
        The configured application.
    """
    settings = settings or get_settings()
    app = FastAPI(
        title=settings.app_name,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )
    for mounted in discover_routers():
        app.include_router(mounted.router, prefix=mounted.prefix)
    return app
