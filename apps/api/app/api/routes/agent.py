"""Agent test endpoint for verifying the DeepSeek-backed kernel."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, status

from app.core.config import Settings
from app.kernel.approval import ApprovalStatus, SQLiteApprovalStore
from app.kernel.factory import create_deepseek_agent
from app.kernel.interfaces.loop import AgentTask
from app.kernel.persistence import SQLiteTaskStore
from app.schemas.agent import (
    AgentApprovalDecision,
    AgentApprovalRead,
    AgentStepRead,
    AgentTestRequest,
    AgentTestResponse,
    AgentToolObservation,
    AgentTurnRead,
)

router = APIRouter()


def _to_response(task: AgentTask, model: str) -> AgentTestResponse:
    """Convert internal dataclasses into a safe public response."""
    turns: list[AgentTurnRead] = []
    total_tokens = 0
    for turn in task.turns:
        steps: list[AgentStepRead] = []
        for step in turn.steps:
            total_tokens += step.tokens_used
            steps.append(
                AgentStepRead(
                    id=step.id,
                    tool_calls=[call.tool_name for call in step.tool_calls],
                    observations=[
                        AgentToolObservation(
                            call_id=observation.call_id,
                            success=observation.success,
                            result=observation.result,
                            error=observation.error,
                        )
                        for observation in step.observations
                    ],
                    content=str(step.model_response.get("content") or ""),
                    tokens_used=step.tokens_used,
                )
            )
        turns.append(AgentTurnRead(id=turn.id, steps=steps))

    return AgentTestResponse(
        task_id=task.id,
        status=task.status.value,
        goal=task.goal,
        model=model,
        turns=turns,
        total_tokens=total_tokens,
        error=task.context.get("error"),
    )


def _require_enabled(request: Request) -> Settings:
    """Return settings when the opt-in Agent endpoint is enabled."""
    settings: Settings = request.app.state.settings
    if not settings.agent_test_endpoint_enabled:
        raise HTTPException(status_code=404, detail="Agent test endpoint is disabled")
    return settings


@router.get(
    "/agent/approvals",
    response_model=list[AgentApprovalRead],
    operation_id="listAgentApprovals",
    summary="List pending Agent approvals",
)
async def list_agent_approvals(request: Request) -> list[AgentApprovalRead]:
    """List approval requests for exact high-risk actions."""
    settings = _require_enabled(request)
    records = SQLiteApprovalStore(settings.agent_state_database_path).list(
        ApprovalStatus.PENDING
    )
    return [
        AgentApprovalRead(
            id=record.id,
            tool_name=record.tool_name,
            arguments=record.arguments,
            status=record.status.value,
            created_at=record.created_at.isoformat(),
            decided_at=record.decided_at.isoformat() if record.decided_at else None,
        )
        for record in records
    ]


@router.post(
    "/agent/approvals/{approval_id}/decision",
    response_model=AgentApprovalRead,
    operation_id="decideAgentApproval",
    summary="Approve or deny an Agent action",
)
async def decide_agent_approval(
    approval_id: str,
    payload: AgentApprovalDecision,
    request: Request,
) -> AgentApprovalRead:
    """Record a user decision for one exact pending tool action."""
    settings = _require_enabled(request)
    record = SQLiteApprovalStore(settings.agent_state_database_path).decide(
        approval_id, payload.approved
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Pending approval not found")
    return AgentApprovalRead(
        id=record.id,
        tool_name=record.tool_name,
        arguments=record.arguments,
        status=record.status.value,
        created_at=record.created_at.isoformat(),
        decided_at=record.decided_at.isoformat() if record.decided_at else None,
    )


@router.get(
    "/agent/tasks/{task_id}",
    response_model=AgentTestResponse,
    operation_id="getAgentTask",
    summary="Get a persisted Agent task",
)
async def get_agent_task(task_id: str, request: Request) -> AgentTestResponse:
    """Read the latest persisted snapshot without calling the model."""
    settings = _require_enabled(request)
    task = SQLiteTaskStore(settings.agent_state_database_path).get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Agent task not found")
    return _to_response(task, settings.deepseek_model)


@router.post(
    "/agent/tasks/{task_id}/resume",
    response_model=AgentTestResponse,
    operation_id="resumeAgentTask",
    summary="Resume a persisted Agent task",
)
async def resume_agent_task(task_id: str, request: Request) -> AgentTestResponse:
    """Resume a paused or failed task from the latest persisted snapshot."""
    settings = _require_enabled(request)
    try:
        orchestrator, environment = create_deepseek_agent(
            settings,
            workspace=settings.agent_workspace,
        )
        await environment.start()
        try:
            task = await orchestrator.resume(task_id)
        finally:
            await environment.stop()
        return _to_response(task, settings.deepseek_model)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Agent task not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/agent/test",
    response_model=AgentTestResponse,
    status_code=status.HTTP_200_OK,
    operation_id="testAgent",
    summary="Run a one-off Agent capability test",
)
async def test_agent(payload: AgentTestRequest, request: Request) -> AgentTestResponse:
    """Run a natural-language goal with the configured DeepSeek Agent."""
    settings = _require_enabled(request)
    try:
        orchestrator, environment = create_deepseek_agent(
            settings,
            workspace=settings.agent_workspace,
        )
        await environment.start()
        try:
            task = await orchestrator.run(AgentTask(id=str(uuid4()), goal=payload.goal))
        finally:
            await environment.stop()
        return _to_response(task, settings.deepseek_model)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
