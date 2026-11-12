"""Liveness and readiness endpoints used by Docker and Kubernetes probes."""

import logging
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict

from app.core.security import public
from app.db import EXPECTED_CONTRACT_VERSION, Database, DatabaseUnavailable, read_contract_version

logger = logging.getLogger(__name__)

ROUTER_PREFIX = ""  # probes are called by Kubernetes on the pod itself, outside /api
router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    """Probe result."""

    model_config = ConfigDict(frozen=True)

    status: Literal["ok"]


@router.get("/healthz", response_model=HealthResponse, dependencies=[Depends(public)])
async def liveness() -> HealthResponse:
    """Report that the process is alive.

    Returns:
        A fixed ``ok`` status.
    """
    return HealthResponse(status="ok")


@router.get(
    "/readyz",
    response_model=HealthResponse,
    dependencies=[Depends(public)],
    responses={503: {"description": "Not ready"}},
)
async def readiness(request: Request) -> HealthResponse:
    """Report that the service can accept traffic: the database answers and speaks the expected contract.

    An app without a database is not ready: readiness is never fail-open.

    Args:
        request: The request, whose app holds the database access.

    Returns:
        A fixed ``ok`` status.

    Raises:
        HTTPException: 503 with a generic body when the database is down or its contract version differs.
    """
    database: Database | None = getattr(request.app.state, "database", None)
    if database is None:
        raise HTTPException(status_code=503, detail="Service unavailable")
    try:
        version = await read_contract_version(database)
    except DatabaseUnavailable:
        raise HTTPException(status_code=503, detail="Service unavailable") from None
    if version != EXPECTED_CONTRACT_VERSION:
        logger.error("database.contract_mismatch expected=%s found=%s", EXPECTED_CONTRACT_VERSION, version)
        raise HTTPException(status_code=503, detail="Service unavailable")
    return HealthResponse(status="ok")
