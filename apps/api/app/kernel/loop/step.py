"""
Step executor - Runs one model-request / tool-execution unit.

Single Responsibility: StepRunner owns the logic for a single step inside a turn.
The Orchestrator delegates here instead of doing this inline, keeping the loop body thin.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.kernel.interfaces.loop import (
    Observation,
    Step,
    StepStatus,
    ToolCall,
    Turn,
)
from app.kernel.interfaces.tool import IToolExecutor, IToolRegistry


def _parse_tool_calls(response: dict[str, Any]) -> list[ToolCall]:
    """
    Extract tool calls from a model response dict.

    Supports both OpenAI 'tool_calls' format and a legacy
    'function_call' format for backwards compatibility.
    """
    calls: list[ToolCall] = []

    # OpenAI chat-completions style
    for raw in response.get("tool_calls") or []:
        fn = raw.get("function", {})
        calls.append(
            ToolCall(
                call_id=raw.get("id", str(uuid.uuid4())),
                tool_name=fn.get("name", ""),
                arguments=fn.get("arguments") or {},
            )
        )

    # Legacy single function_call style
    if not calls and (fc := response.get("function_call")):
        calls.append(
            ToolCall(
                call_id=str(uuid.uuid4()),
                tool_name=fc.get("name", ""),
                arguments=fc.get("arguments") or {},
            )
        )

    return calls


class StepRunner:
    """
    Executes a single step: parse tool calls → dispatch → collect observations.

    Injected with IToolExecutor so the parallel-execution strategy is
    swappable without changing the step logic (Dependency Inversion).
    """

    def __init__(self, executor: IToolExecutor, registry: IToolRegistry) -> None:
        self._executor = executor
        self._registry = registry

    async def run(
        self,
        turn: Turn,
        model_request: dict[str, Any],
        model_response: dict[str, Any],
        tokens_used: int = 0,
    ) -> Step:
        """
        Build a Step from a model exchange and execute any tool calls it contains.

        Returns the completed Step with all observations attached.
        The Step is COMPLETED on success; FAILED if execution raises.
        """
        step = Step(
            id=str(uuid.uuid4()),
            turn_id=turn.id,
            model_request=model_request,
            model_response=model_response,
            status=StepStatus.RUNNING,
            started_at=datetime.utcnow(),
            tokens_used=tokens_used,
        )

        tool_calls = _parse_tool_calls(model_response)
        step.tool_calls = tool_calls

        if tool_calls:
            call_specs = [
                (tc.call_id, tc.tool_name, tc.arguments) for tc in tool_calls
            ]
            results = await self._executor.execute_many(call_specs, task_id=turn.task_id)
            step.observations = [
                Observation(
                    call_id=call_id,
                    success=result.success,
                    result=result.output,
                    error=result.error,
                    metadata=result.metadata,
                )
                for call_id, result in results
            ]

        step.status = StepStatus.COMPLETED
        step.finished_at = datetime.utcnow()
        return step
