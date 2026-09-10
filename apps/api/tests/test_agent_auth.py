"""Authentication tests for the Agent endpoints."""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.kernel.approval import ApprovalStatus, SQLiteApprovalStore
from app.kernel.audit import SQLiteAuditStore
from app.main import create_app

VALID_TOKEN = "s3cret-agent-token"


def _settings(tmp_path, *, enabled: bool = True, token: str = f"alice:{VALID_TOKEN}") -> Settings:
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'auth.db'}",
        cors_origins="http://localhost:5173",
        deepseek_api_key="test-key",
        agent_test_endpoint_enabled=enabled,
        agent_api_token=token,
        agent_workspace=str(tmp_path),
        agent_state_database_path=str(tmp_path / "agent-state.db"),
    )


def test_disabled_endpoint_hides_itself_even_with_a_valid_token(tmp_path) -> None:
    """The enabled check runs first, so a disabled deployment looks absent."""
    with TestClient(create_app(_settings(tmp_path, enabled=False))) as client:
        response = client.get(
            "/api/v1/agent/approvals", headers={"X-Agent-Token": VALID_TOKEN}
        )

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent test endpoint is disabled"


def test_enabled_without_configured_token_refuses_to_serve(tmp_path) -> None:
    """Fail closed: enabling the endpoint must not expose it unauthenticated."""
    with TestClient(create_app(_settings(tmp_path, token=""))) as client:
        response = client.get("/api/v1/agent/approvals")

    assert response.status_code == 503
    assert response.json()["detail"] == "AGENT_API_TOKEN is not configured"


def test_missing_token_header_is_rejected(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get("/api/v1/agent/approvals")

    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid or missing agent token"


def test_wrong_token_is_rejected(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get(
            "/api/v1/agent/approvals", headers={"X-Agent-Token": "wrong"}
        )

    assert response.status_code == 401


def test_valid_token_is_accepted(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path))) as client:
        response = client.get(
            "/api/v1/agent/approvals", headers={"X-Agent-Token": VALID_TOKEN}
        )

    assert response.status_code == 200
    assert response.json() == []


def test_bare_token_without_a_name_is_attributed_to_default(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path, token=VALID_TOKEN))) as client:
        response = client.get(
            "/api/v1/agent/approvals", headers={"X-Agent-Token": VALID_TOKEN}
        )

    assert response.status_code == 200


def test_rejected_call_is_audited_without_leaking_the_token(tmp_path) -> None:
    settings = _settings(tmp_path)
    with TestClient(create_app(settings)) as client:
        client.post(
            "/api/v1/agent/test",
            json={"goal": "pwd"},
            headers={"X-Agent-Token": "wrong-token"},
        )

    events = SQLiteAuditStore(settings.agent_state_database_path).list()
    denied = [event for event in events if event["event_type"] == "agent_auth_denied"]

    assert len(denied) == 1
    assert denied[0]["decision"] == "deny"
    assert denied[0]["details"]["path"] == "/api/v1/agent/test"
    assert denied[0]["details"]["reason"] == "token_mismatch"
    assert "wrong-token" not in str(denied[0])
    assert VALID_TOKEN not in str(denied[0])


def test_decision_records_the_authenticated_actor(tmp_path) -> None:
    import asyncio

    settings = _settings(tmp_path)
    store = SQLiteApprovalStore(settings.agent_state_database_path)

    class ApprovalTool:
        class Schema:
            qualified_name = "shell_exec"

        schema = Schema()

    assert asyncio.run(store.approve(ApprovalTool(), {"command": "rm -rf /"})) is False
    pending = store.list(ApprovalStatus.PENDING)

    with TestClient(create_app(settings)) as client:
        response = client.post(
            f"/api/v1/agent/approvals/{pending[0].id}/decision",
            json={"approved": False},
            headers={"X-Agent-Token": VALID_TOKEN},
        )

    assert response.status_code == 200
    assert response.json()["decided_by"] == "alice"
    assert store.list(ApprovalStatus.DENIED)[0].decided_by == "alice"

    events = SQLiteAuditStore(settings.agent_state_database_path).list()
    decided = [event for event in events if event["event_type"] == "agent_approval_decided"]
    assert decided[0]["details"]["actor"] == "alice"
    assert decided[0]["decision"] == "deny"
