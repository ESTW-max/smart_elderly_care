"""
Termination conditions - Four required stop triggers for the orchestration loop.

Open/Closed design: each condition is its own class. New conditions are added by
implementing ITerminationCondition; the Orchestrator is never modified.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

from app.kernel.interfaces.loop import (
    AgentTask,
    ITerminationCondition,
    Step,
    TerminationReason,
)


class NoToolCallsCondition(ITerminationCondition):
    """
    Stop when the model's last response contained no tool calls.

    This is the normal 'I am done' signal: the model has answered
    the goal without requesting further actions.
    """

    @property
    def name(self) -> str:
        return "no_tool_calls"

    def should_terminate(
        self, task: AgentTask, last_step: Step | None
    ) -> TerminationReason | None:
        if last_step is not None and not last_step.tool_calls:
            return TerminationReason.NO_TOOL_CALLS
        return None


class GoalReachedCondition(ITerminationCondition):
    """
    Stop when the model emits an explicit 'goal_reached' marker.

    Concrete implementations may look for a special tool call
    (e.g. `finish(reason=...)`) or a keyword in the response.
    This base implementation checks for a `_goal_reached` flag
    that the orchestrator sets on the response metadata.
    """

    MARKER_KEY = "_goal_reached"

    @property
    def name(self) -> str:
        return "goal_reached"

    def should_terminate(
        self, task: AgentTask, last_step: Step | None
    ) -> TerminationReason | None:
        if last_step is not None:
            if last_step.model_response.get(self.MARKER_KEY):
                return TerminationReason.GOAL_REACHED
        return None


class BudgetExhaustedCondition(ITerminationCondition):
    """
    Stop when any resource budget limit is hit.

    Checks steps, tokens, and wall-clock seconds independently so that
    any one limit is sufficient to trigger termination.
    """

    @property
    def name(self) -> str:
        return "budget_exhausted"

    def should_terminate(
        self, task: AgentTask, last_step: Step | None
    ) -> TerminationReason | None:
        if not task.turns:
            return None

        settings = task.turns[-1].settings_snapshot
        budget = settings.budget

        # Count total steps across all turns
        total_steps = sum(len(t.steps) for t in task.turns)
        if total_steps >= budget.max_steps:
            return TerminationReason.BUDGET_EXHAUSTED

        # Count total tokens
        total_tokens = sum(
            step.tokens_used
            for turn in task.turns
            for step in turn.steps
        )
        if total_tokens >= budget.max_tokens:
            return TerminationReason.BUDGET_EXHAUSTED

        # Check wall-clock time
        elapsed = (datetime.utcnow() - task.created_at).total_seconds()
        if elapsed >= budget.max_seconds:
            return TerminationReason.BUDGET_EXHAUSTED

        return None


class ExternalSignalCondition(ITerminationCondition):
    """
    Stop when an external interrupt signal has been set.

    The signal is a threading/asyncio Event so it can be set from
    outside the running loop (e.g. user cancellation over HTTP).
    """

    def __init__(self) -> None:
        self._signal: asyncio.Event = asyncio.Event()

    @property
    def name(self) -> str:
        return "external_signal"

    def signal(self) -> None:
        """Set the interrupt flag from any coroutine."""
        self._signal.set()

    def clear(self) -> None:
        """Reset so the condition can be reused for a resumed task."""
        self._signal.clear()

    def should_terminate(
        self, task: AgentTask, last_step: Step | None
    ) -> TerminationReason | None:
        if self._signal.is_set():
            return TerminationReason.EXTERNAL_SIGNAL
        return None


class TerminationChain:
    """
    Composite evaluator: the first condition that fires wins.

    The default ordering (no_tool_calls → goal_reached → budget → external)
    matches the priority described in agent-core-capabilities.md, but
    callers can supply any ordered list.
    """

    def __init__(self, conditions: list[ITerminationCondition] | None = None) -> None:
        if conditions is None:
            conditions = [
                NoToolCallsCondition(),
                GoalReachedCondition(),
                BudgetExhaustedCondition(),
                ExternalSignalCondition(),
            ]
        self._conditions = conditions

    def should_terminate(
        self, task: AgentTask, last_step: Step | None
    ) -> TerminationReason | None:
        for condition in self._conditions:
            reason = condition.should_terminate(task, last_step)
            if reason is not None:
                return reason
        return None

    def get(self, name: str) -> ITerminationCondition | None:
        """Retrieve a condition by name for runtime manipulation."""
        return next((c for c in self._conditions if c.name == name), None)
