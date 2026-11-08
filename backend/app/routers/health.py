"""Liveness and readiness endpoints used by Docker and Kubernetes probes."""

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict

from app.core.security import public

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


@router.get("/readyz", response_model=HealthResponse, dependencies=[Depends(public)])
async def readiness() -> HealthResponse:
    """Report that the service can accept traffic.

    Returns:
        A fixed ``ok`` status until real dependencies (database, IdP) are added.
    """
    return HealthResponse(status="ok")
