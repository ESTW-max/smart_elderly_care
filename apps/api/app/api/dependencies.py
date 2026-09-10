import secrets
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.kernel.audit import SQLiteAuditStore

AGENT_TOKEN_HEADER = "X-Agent-Token"


async def get_session(request: Request) -> AsyncGenerator[AsyncSession, None]:
    async with request.app.state.session_factory() as session:
        yield session


@dataclass(frozen=True)
class AgentAuth:
    """Authenticated caller of an Agent endpoint, with its settings."""

    actor: str
    settings: Settings


def require_agent_auth(request: Request) -> AgentAuth:
    """Authenticate an Agent request via the ``X-Agent-Token`` header.

    Checks run in order: the endpoint must be enabled (404 otherwise, so a
    disabled deployment looks absent rather than merely locked), credentials
    must be configured (503), and the presented token must match (401).
    Refusing to serve when no token is configured is deliberate: these
    endpoints run shell commands, so enabling them for debugging must not
    silently expose them.
    """
    settings: Settings = request.app.state.settings
    if not settings.agent_test_endpoint_enabled:
        raise HTTPException(status_code=404, detail="Agent test endpoint is disabled")

    tokens = settings.agent_api_token_map
    if not tokens:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AGENT_API_TOKEN is not configured",
        )

    presented = request.headers.get(AGENT_TOKEN_HEADER, "")
    actor: str | None = None
    # Compare against every entry without short-circuiting, so response time
    # does not reveal which actor matched or how many are configured.
    for candidate, token in tokens.items():
        if secrets.compare_digest(presented, token):
            actor = candidate
    if actor is None:
        _record_denied(settings, request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing agent token",
            headers={"WWW-Authenticate": AGENT_TOKEN_HEADER},
        )
    return AgentAuth(actor=actor, settings=settings)


def _record_denied(settings: Settings, request: Request) -> None:
    """Audit a rejected call, recording the reason but never the token."""
    SQLiteAuditStore(settings.agent_state_database_path).record(
        "agent_auth_denied",
        decision="deny",
        details={
            "path": request.url.path,
            "method": request.method,
            "reason": "missing_header"
            if not request.headers.get(AGENT_TOKEN_HEADER)
            else "token_mismatch",
        },
    )
