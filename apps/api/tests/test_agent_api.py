"""API tests for the opt-in Agent capability test endpoint."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.kernel.interfaces.loop import (
    AgentTask,
    Budget,
    Observation,
    Step,
    TaskStatus,
    ToolCall,
    Turn,
    TurnSettings,
)
from app.main import create_app


def _settings(tmp_path, *, enabled: bool) -> Settings:
    # Pin every field the assertions depend on: Settings() otherwise reads the
    # developer's real .env, so a local DEEPSEEK_MODEL override leaks in here.
    return Settings(
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'agent-test.db'}",
        cors_origins="http://localhost:5173",
        deepseek_api_key="test-key",
        deepseek_model="deepseek-chat",
        agent_test_endpoint_enabled=enabled,
        agent_workspace=str(tmp_path),
        agent_state_database_path=str(tmp_path / "agent-state.db"),
    )


def _completed_task(goal: str) -> AgentTask:
    settings = TurnSettings(
        model="deepseek-chat",
        system_prompt="test",
        budget=Budget(),
        tool_names=frozenset(),
    )
    step = Step(
        id="step-1",
        turn_id="turn-1",
        model_request={},
        model_response={"content": "读取完成"},
        tool_calls=[ToolCall("call-1", "read_file", {"path": "README.md"})],
        observations=[Observation("call-1", True, "README content")],
        tokens_used=42,
    )
    turn = Turn(id="turn-1", task_id="task-1", settings_snapshot=settings, steps=[step])
    return AgentTask(
        id="task-1",
        goal=goal,
        turns=[turn],
        status=TaskStatus.COMPLETED,
        completed_at=datetime.utcnow(),
    )


def test_agent_endpoint_is_disabled_by_default(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path, enabled=False))) as client:
        response = client.post("/api/v1/agent/test", json={"goal": "读取 README"})

    assert response.status_code == 404
    assert response.json()["detail"] == "Agent test endpoint is disabled"


def test_agent_endpoint_validates_request(tmp_path) -> None:
    with TestClient(create_app(_settings(tmp_path, enabled=True))) as client:
        response = client.post("/api/v1/agent/test", json={"goal": ""})

    assert response.status_code == 422


def test_agent_endpoint_returns_execution_summary(tmp_path) -> None:
    goal = "读取 README.md"
    orchestrator = AsyncMock()
    orchestrator.run.return_value = _completed_task(goal)
    environment = AsyncMock()

    with patch(
        "app.api.routes.agent.create_deepseek_agent",
        return_value=(orchestrator, environment),
    ):
        with TestClient(create_app(_settings(tmp_path, enabled=True))) as client:
            response = client.post("/api/v1/agent/test", json={"goal": goal})

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["model"] == "deepseek-chat"
    assert body["total_tokens"] == 42
    assert body["turns"][0]["steps"][0]["tool_calls"] == ["read_file"]
    assert body["turns"][0]["steps"][0]["observations"][0]["success"] is True
    environment.start.assert_awaited_once()
    environment.stop.assert_awaited_once()



def test_get_persisted_agent_task(tmp_path):
    from app.kernel.persistence import SQLiteTaskStore

    settings = _settings(tmp_path, enabled=True)
    task = _completed_task("已保存任务")
    store = SQLiteTaskStore(settings.agent_state_database_path)
    store.save(task)

    with TestClient(create_app(settings)) as client:
        response = client.get(f"/api/v1/agent/tasks/{task.id}")

    assert response.status_code == 200
    assert response.json()["goal"] == "已保存任务"
    assert response.json()["status"] == "completed"



def test_list_and_decide_agent_approval(tmp_path):
    from app.kernel.approval import ApprovalStatus, SQLiteApprovalStore

    settings = _settings(tmp_path, enabled=True)
    store = SQLiteApprovalStore(settings.agent_state_database_path)

    class ApprovalTool:
        class Schema:
            qualified_name = "shell_exec"

        schema = Schema()

    import asyncio

    assert asyncio.run(store.approve(ApprovalTool(), {"command": "pwd"})) is False
    pending = store.list(ApprovalStatus.PENDING)
    assert len(pending) == 1

    with TestClient(create_app(settings)) as client:
        listed = client.get("/api/v1/agent/approvals")
        assert listed.status_code == 200
        assert listed.json()[0]["tool_name"] == "shell_exec"

        decision = client.post(
            f"/api/v1/agent/approvals/{pending[0].id}/decision",
            json={"approved": True},
        )
        assert decision.status_code == 200
        assert decision.json()["status"] == "approved"
