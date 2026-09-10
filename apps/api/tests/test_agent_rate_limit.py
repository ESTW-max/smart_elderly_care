"""Rate limiting tests for the Agent endpoints."""

import time

import pytest
from fastapi.testclient import TestClient

from app.api.rate_limit import SlidingWindowLimiter
from app.core.config import Settings
from app.kernel.audit import SQLiteAuditStore
from app.main import create_app

VALID_TOKEN = "s3cret-agent-token"


def _settings(tmp_path, **overrides) -> Settings:
    values = {
        "database_url": f"sqlite+aiosqlite:///{tmp_path / 'limit.db'}",
        "cors_origins": "http://localhost:5173",
        "deepseek_api_key": "test-key",
        "agent_test_endpoint_enabled": True,
        "agent_api_token": f"alice:{VALID_TOKEN}",
        "agent_workspace": str(tmp_path),
        "agent_state_database_path": str(tmp_path / "agent-state.db"),
    }
    values.update(overrides)
    return Settings(**values)


def test_repeated_bad_tokens_are_throttled(tmp_path) -> None:
    """Token guessing gets 429 instead of an unbounded stream of 401s."""
    settings = _settings(tmp_path, agent_rate_limit_auth_failures=3)
    with TestClient(create_app(settings)) as client:
        codes = [
            client.get("/api/v1/agent/approvals", headers={"X-Agent-Token": "bad"}).status_code
            for _ in range(5)
        ]

    assert codes == [401, 401, 401, 429, 429]


def test_throttled_caller_is_blocked_even_with_a_valid_token(tmp_path) -> None:
    """The failure quota is checked before the comparison, so it is not bypassable.

    Locking out the real token for the rest of the window is the intended
    trade-off: these endpoints run shell commands.
    """
    settings = _settings(tmp_path, agent_rate_limit_auth_failures=2)
    with TestClient(create_app(settings)) as client:
        for _ in range(2):
            client.get("/api/v1/agent/approvals", headers={"X-Agent-Token": "bad"})
        response = client.get(
            "/api/v1/agent/approvals", headers={"X-Agent-Token": VALID_TOKEN}
        )

    assert response.status_code == 429
    assert int(response.headers["Retry-After"]) >= 1


def test_successful_calls_are_throttled_per_actor(tmp_path) -> None:
    """Bounds runaway agent loops, which cost real model spend."""
    settings = _settings(tmp_path, agent_rate_limit_requests=2)
    with TestClient(create_app(settings)) as client:
        codes = [
            client.get(
                "/api/v1/agent/approvals", headers={"X-Agent-Token": VALID_TOKEN}
            ).status_code
            for _ in range(4)
        ]

    assert codes == [200, 200, 429, 429]


def test_throttling_is_audited_once_per_window_not_once_per_request(tmp_path) -> None:
    """A flood must not cost one disk write per rejected request.

    Auditing every rejection would turn the rate limiter into an amplification
    vector: cheap for the attacker, a SQLite insert for us.
    """
    settings = _settings(tmp_path, agent_rate_limit_auth_failures=1)
    with TestClient(create_app(settings)) as client:
        for _ in range(30):
            client.get("/api/v1/agent/approvals", headers={"X-Agent-Token": "bad"})

    events = SQLiteAuditStore(settings.agent_state_database_path).list()
    limited = [event for event in events if event["event_type"] == "agent_rate_limited"]

    assert len(limited) == 1
    assert limited[0]["decision"] == "deny"
    assert limited[0]["details"]["scope"] == "auth_failures"
    assert "bad" not in str(limited[0]["details"].values())


def test_zero_limit_disables_throttling(tmp_path) -> None:
    """Both quotas off restores the pre-rate-limit behaviour."""
    settings = _settings(
        tmp_path, agent_rate_limit_auth_failures=0, agent_rate_limit_requests=0
    )
    with TestClient(create_app(settings)) as client:
        codes = [
            client.get("/api/v1/agent/approvals", headers={"X-Agent-Token": "bad"}).status_code
            for _ in range(20)
        ]

    assert set(codes) == {401}


def test_disabled_endpoint_is_not_rate_limited_into_view(tmp_path) -> None:
    """404 still precedes 429, so throttling cannot reveal a disabled endpoint."""
    settings = _settings(
        tmp_path, agent_test_endpoint_enabled=False, agent_rate_limit_auth_failures=1
    )
    with TestClient(create_app(settings)) as client:
        codes = [
            client.get("/api/v1/agent/approvals", headers={"X-Agent-Token": "bad"}).status_code
            for _ in range(3)
        ]

    assert set(codes) == {404}


def test_quota_frees_up_after_the_window() -> None:
    limiter = SlidingWindowLimiter(limit=2, window_seconds=0.05)
    limiter.record("k")
    limiter.record("k")

    assert limiter.retry_after("k") is not None
    time.sleep(0.06)
    assert limiter.retry_after("k") is None


def test_limiter_keys_do_not_interfere() -> None:
    limiter = SlidingWindowLimiter(limit=1, window_seconds=60)
    limiter.record("a")

    assert limiter.retry_after("a") is not None
    assert limiter.retry_after("b") is None


@pytest.mark.parametrize("limit", [0, -1])
def test_non_positive_limit_never_blocks(limit: int) -> None:
    limiter = SlidingWindowLimiter(limit=limit, window_seconds=60)
    for _ in range(100):
        limiter.record("k")

    assert limiter.enabled is False
    assert limiter.retry_after("k") is None


def test_expired_keys_are_swept_so_memory_stays_bounded() -> None:
    """Client addresses are attacker-chosen; the key map must not grow forever."""
    limiter = SlidingWindowLimiter(limit=5, window_seconds=0.01)
    for index in range(1200):
        limiter.record(f"ip-{index}")
    time.sleep(0.02)
    limiter.record("trigger-sweep")

    assert len(limiter._events) < 1200
