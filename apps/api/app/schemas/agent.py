"""Pydantic schemas for Agent test execution."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentTestRequest(BaseModel):
    """User-provided goal for a one-off Agent capability test."""

    model_config = ConfigDict(extra="forbid")

    goal: str = Field(min_length=1, description="自然语言任务目标")


class AgentToolObservation(BaseModel):
    """Structured result of one Agent tool call."""

    call_id: str
    success: bool
    result: Any = None
    error: str | None = None


class AgentStepRead(BaseModel):
    """Public representation of one Agent execution step."""

    id: str
    tool_calls: list[str]
    observations: list[AgentToolObservation]
    content: str
    tokens_used: int


class AgentTurnRead(BaseModel):
    """Public representation of one Agent turn."""

    id: str
    steps: list[AgentStepRead]


class AgentTestResponse(BaseModel):
    """Execution summary returned by the Agent test endpoint."""

    task_id: str
    status: str
    goal: str
    model: str
    turns: list[AgentTurnRead]
    total_tokens: int
    error: str | None = None


class AgentApprovalDecision(BaseModel):
    """Approve or deny one exact high-risk tool action."""

    model_config = ConfigDict(extra="forbid")

    approved: bool


class AgentApprovalRead(BaseModel):
    """Public approval record."""

    id: str
    tool_name: str
    arguments: dict[str, Any]
    status: str
    created_at: str
    decided_at: str | None = None
    decided_by: str | None = None
