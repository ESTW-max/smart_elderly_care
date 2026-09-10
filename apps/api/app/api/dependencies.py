import secrets
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from fastapi import HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.rate_limit import AgentRateLimiters, SlidingWindowLimiter
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
    """Authenticate and rate-limit an Agent request via ``X-Agent-Token``.

    Checks run in order: the endpoint must be enabled (404 otherwise, so a
    disabled deployment looks absent rather than merely locked), credentials
    must be configured (503), the caller must not be hammering the endpoint
    (429), and the presented token must match (401). Refusing to serve when no
    token is configured is deliberate: these endpoints run shell commands, so
    enabling them for debugging must not silently expose them.
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

    limiters: AgentRateLimiters = request.app.state.agent_rate_limiters
    client = _client_key(request)
    # Checked before the comparison so a client that is already over its
    # failure quota costs nothing to reject. A client that exhausts the quota
    # stays blocked for the rest of the window even if it then presents a
    # valid token; for endpoints that run shell commands, that is the side to
    # err on.
    _reject_if_limited(limiters.auth_failures, client, settings, request, scope="auth_failures")

    presented = request.headers.get(AGENT_TOKEN_HEADER, "")
    actor: str | None = None
    # Compare against every entry without short-circuiting, so response time
    # does not reveal which actor matched or how many are configured.
    for candidate, token in tokens.items():
        if secrets.compare_digest(presented, token):
            actor = candidate
    if actor is None:
        limiters.auth_failures.record(client)
        _record_denied(settings, request)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing agent token",
            headers={"WWW-Authenticate": AGENT_TOKEN_HEADER},
        )

    _reject_if_limited(limiters.requests, actor, settings, request, scope="requests")
    limiters.requests.record(actor)
    return AgentAuth(actor=actor, settings=settings)


def _client_key(request: Request) -> str:
    """Identify the calling host for failure accounting.

    Uses the peer address rather than ``X-Forwarded-For``, which any client can
    forge. Behind a proxy, run uvicorn with ``--proxy-headers`` so that the
    peer address is the real client.
    """
    return request.client.host if request.client else "unknown"


def _reject_if_limited(
    limiter: SlidingWindowLimiter,
    key: str,
    settings: Settings,
    request: Request,
    scope: str,
) -> None:
    retry_after = limiter.retry_after(key)
    if retry_after is None:
        return
    if limiter.should_report(key):
        SQLiteAuditStore(settings.agent_state_database_path).record(
            "agent_rate_limited",
            decision="deny",
            details={"path": request.url.path, "method": request.method, "scope": scope},
        )
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Rate limit exceeded",
        headers={"Retry-After": str(max(int(retry_after + 0.999), 1))},
    )


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
