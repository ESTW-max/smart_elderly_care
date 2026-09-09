"""
Loop interfaces - Abstractions for the orchestration cycle.

Following Interface Segregation Principle: small, focused interfaces
rather than one large orchestrator contract.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TerminationReason(str, Enum):
    NO_TOOL_CALLS = "no_tool_calls"       # Model output contained no tool calls
    GOAL_REACHED = "goal_reached"          # Explicit completion signal
    BUDGET_EXHAUSTED = "budget_exhausted"  # Token / step / time limit hit
    EXTERNAL_SIGNAL = "external_signal"   # User interrupt or timeout


# ---------------------------------------------------------------------------
# Core data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Budget:
    """Resource limits for a task run. Immutable to prevent drift."""

    max_steps: int = 100
    max_tokens: int = 100_000
    max_seconds: float = 3600.0


@dataclass(frozen=True)
class TurnSettings:
    """
    Immutable snapshot of configuration for one turn.

    Captured at turn start so mid-turn config changes cannot affect
    the current run — prevents configuration drift and makes turns
    safe to execute concurrently.
    """

    model: str
    system_prompt: str
    budget: Budget
    tool_names: frozenset[str]
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Ensure extra is hashable-compatible (copied on construction)
        object.__setattr__(self, "extra", dict(self.extra))


@dataclass
class ToolCall:
    """A single tool invocation requested by the model."""

    call_id: str
    tool_name: str
    arguments: dict[str, Any]


@dataclass
class Observation:
    """The structured result of executing a ToolCall."""

    call_id: str
    success: bool
    result: Any
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_model_content(self) -> str:
        """
        Render a description the model can use to self-correct on failure.

        Returning structured context (not just 'exit 1') lets the model
        understand why an action was denied and adjust its next call.
        """
        if self.success:
            return str(self.result)
        return f"[ERROR] {self.error or 'unknown error'}\nResult: {self.result}"


@dataclass
class Step:
    """One model-request / tool-execution unit inside a turn."""

    id: str
    turn_id: str
    model_request: dict[str, Any]
    model_response: dict[str, Any]
    tool_calls: list[ToolCall] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None
    tokens_used: int = 0


@dataclass
class Turn:
    """
    One user-visible interaction round.

    settings_snapshot is frozen at creation time so concurrent
    execution cannot observe config changes mid-turn.
    """

    id: str
    task_id: str
    settings_snapshot: TurnSettings
    user_input: str | None = None
    steps: list[Step] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    finished_at: datetime | None = None


@dataclass
class AgentTask:
    """A complete goal, potentially spanning multiple turns."""

    id: str
    goal: str
    context: dict[str, Any] = field(default_factory=dict)
    turns: list[Turn] = field(default_factory=list)
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None


# ---------------------------------------------------------------------------
# Steering (mid-run input injection)
# ---------------------------------------------------------------------------


@dataclass
class SteeringMessage:
    """
    New instruction injected while the loop is running.

    Delivery is deferred to safe checkpoints (turn boundary or after
    context compression) to avoid dropping in-flight tool chains.
    """

    content: str
    injected_at: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------


class ITerminationCondition(ABC):
    """
    Single-responsibility check: should the loop stop?

    Open/Closed: add new conditions by implementing this interface,
    not by modifying the orchestrator.
    """

    @abstractmethod
    def should_terminate(self, task: AgentTask, last_step: Step | None) -> TerminationReason | None:
        """Return a reason if the loop should stop, else None."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable identifier for logging."""
        ...


class IOrchestrator(ABC):
    """
    High-level contract for the agent orchestration loop.

    Depends on ITool and IExecutionEnvironment abstractions (DIP).
    Concrete implementations are injected at construction time.
    """

    @abstractmethod
    async def run(self, task: AgentTask) -> AgentTask:
        """
        Execute the full sample → decide → act → observe loop until
        a termination condition is met or the task is cancelled.
        """
        ...

    @abstractmethod
    async def resume(self, task_id: str) -> AgentTask:
        """Resume a persisted task from its last committed step."""
        ...

    @abstractmethod
    async def interrupt(self, task_id: str) -> None:
        """
        Signal the running loop to pause cleanly.

        Work completed so far must be preserved — the task can be
        resumed from the last committed step.
        """
        ...

    @abstractmethod
    async def steer(self, task_id: str, message: SteeringMessage) -> None:
        """
        Inject a new instruction into an already-running loop.

        Delivery is deferred to a safe checkpoint so that in-flight
        tool chains are not orphaned.
        """
        ...

    @abstractmethod
    def event_stream(self, task_id: str) -> AsyncIterator[dict[str, Any]]:
        """
        Yield structured events (step started, tool called, step done …)
        for real-time observation by callers.
        """
        ...
