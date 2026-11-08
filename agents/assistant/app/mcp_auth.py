"""Calling MCP servers that are hosted on AgentCore Runtime: the URL of a runtime and SigV4 signing of every request."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import quote

import boto3
import httpx
from botocore.auth import SigV4Auth
from botocore.awsrequest import AWSRequest

from app.settings import RUNTIME_ARN, SettingsError

if TYPE_CHECKING:
    from collections.abc import Generator

SIGNING_NAME = "bedrock-agentcore"


def runtime_url(arn: str) -> str:
    """The invocation URL of an AgentCore runtime: the ARN is URL-encoded and the default endpoint is used."""
    match = RUNTIME_ARN.match(arn)
    if match is None:
        raise SettingsError("not an AgentCore runtime ARN")
    host = f"bedrock-agentcore.{match['region']}.amazonaws.com"
    return f"https://{host}/runtimes/{quote(arn, safe='')}/invocations?qualifier=DEFAULT"


class SigV4(httpx.Auth):
    """Signs each request with the credentials of the environment (execution role, IRSA, profile)."""

    requires_request_body = True

    def __init__(self, region: str, session: boto3.Session | None = None) -> None:
        """``region`` is the region of the runtime; ``session`` is injectable for tests."""
        self._region = region
        self._session = session or boto3.Session()

    def auth_flow(self, request: httpx.Request) -> Generator[httpx.Request, httpx.Response, None]:
        """Add the SigV4 headers (Authorization, X-Amz-Date, security token) to the outgoing request."""
        credentials = self._session.get_credentials()
        if credentials is None:
            raise SettingsError("no AWS credentials to sign the MCP request with")
        unsigned = AWSRequest(
            method=request.method,
            url=str(request.url),
            data=request.content,
            headers={"Content-Type": request.headers.get("content-type", "application/json")},
        )
        SigV4Auth(credentials.get_frozen_credentials(), SIGNING_NAME, self._region).add_auth(unsigned)
        request.headers.update(dict(unsigned.headers.items()))
        yield request
