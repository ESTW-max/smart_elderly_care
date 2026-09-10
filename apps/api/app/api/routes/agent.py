"""Agent test endpoint for verifying the DeepSeek-backed kernel."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import AgentAuth, require_agent_auth
from app.kernel.approval import ApprovalRequest, ApprovalStatus, SQLiteApprovalStore
from app.kernel.audit import SQLiteAuditStore
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


def _to_approval_read(record: ApprovalRequest) -> AgentApprovalRead:
    """Convert an approval record into its public representation."""
    return AgentApprovalRead(
        id=record.id,
        tool_name=record.tool_name,
        arguments=record.arguments,
        status=record.status.value,
        created_at=record.created_at.isoformat(),
        decided_at=record.decided_at.isoformat() if record.decided_at else None,
        decided_by=record.decided_by,
    )


@router.get(
    "/agent/approvals",
    response_model=list[AgentApprovalRead],
    operation_id="listAgentApprovals",
    summary="List pending Agent approvals",
)
async def list_agent_approvals(
    auth: AgentAuth = Depends(require_agent_auth),
) -> list[AgentApprovalRead]:
    """List approval requests for exact high-risk actions."""
    records = SQLiteApprovalStore(auth.settings.agent_state_database_path).list(
        ApprovalStatus.PENDING
    )
    return [_to_approval_read(record) for record in records]


@router.post(
    "/agent/approvals/{approval_id}/decision",
    response_model=AgentApprovalRead,
    operation_id="decideAgentApproval",
    summary="Approve or deny an Agent action",
)
async def decide_agent_approval(
    approval_id: str,
    payload: AgentApprovalDecision,
    auth: AgentAuth = Depends(require_agent_auth),
) -> AgentApprovalRead:
    """Record a user decision for one exact pending tool action."""
    record = SQLiteApprovalStore(auth.settings.agent_state_database_path).decide(
        approval_id, payload.approved, decided_by=auth.actor
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Pending approval not found")
    SQLiteAuditStore(auth.settings.agent_state_database_path).record(
        "agent_approval_decided",
        task_id=record.task_id,
        tool_name=record.tool_name,
        decision="allow" if payload.approved else "deny",
        details={"approval_id": approval_id, "actor": auth.actor},
    )
    return _to_approval_read(record)


@router.get(
    "/agent/tasks/{task_id}",
    response_model=AgentTestResponse,
    operation_id="getAgentTask",
    summary="Get a persisted Agent task",
)
async def get_agent_task(
    task_id: str,
    auth: AgentAuth = Depends(require_agent_auth),
) -> AgentTestResponse:
    """Read the latest persisted snapshot without calling the model."""
    task = SQLiteTaskStore(auth.settings.agent_state_database_path).get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Agent task not found")
    return _to_response(task, auth.settings.deepseek_model)


@router.post(
    "/agent/tasks/{task_id}/resume",
    response_model=AgentTestResponse,
    operation_id="resumeAgentTask",
    summary="Resume a persisted Agent task",
)
async def resume_agent_task(
    task_id: str,
    auth: AgentAuth = Depends(require_agent_auth),
) -> AgentTestResponse:
    """Resume a paused or failed task from the latest persisted snapshot."""
    settings = auth.settings
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
async def test_agent(
    payload: AgentTestRequest,
    auth: AgentAuth = Depends(require_agent_auth),
) -> AgentTestResponse:
    """Run a natural-language goal with the configured DeepSeek Agent."""
    settings = auth.settings
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
