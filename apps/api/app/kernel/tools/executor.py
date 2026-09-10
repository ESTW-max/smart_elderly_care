"""
ToolExecutor - Dispatches tool calls with parallel execution support.

Single Responsibility: execute a batch of calls and return ordered results.
Cancellation signals propagate to all in-flight tasks.
"""

from __future__ import annotations

import asyncio
from typing import Any

from app.kernel.audit import SQLiteAuditStore
from app.kernel.interfaces.tool import (
    IToolApproval,
    IToolExecutor,
    IToolRegistry,
    IToolValidator,
    ToolResult,
    ToolRisk,
)


class ToolExecutor(IToolExecutor):
    """
    Concurrent tool executor backed by a ToolRegistry.

    Independent calls within a batch run in parallel via asyncio.gather.
    If the registry has no entry for a name, a structured ToolResult
    with success=False is returned so the model can self-correct.
    """

    def __init__(
        self,
        registry: IToolRegistry,
        validator: IToolValidator | None = None,
        approval: IToolApproval | None = None,
        approval_required_risk: ToolRisk = ToolRisk.HIGH,
        audit_store: SQLiteAuditStore | None = None,
    ) -> None:
        self._registry = registry
        self._validator = validator
        self._approval = approval
        self._approval_required_risk = approval_required_risk
        self._audit_store = audit_store

    async def execute_many(
        self,
        calls: list[tuple[str, str, dict[str, Any]]],
        task_id: str | None = None,
    ) -> list[tuple[str, ToolResult]]:
        """
        Execute a batch of (call_id, tool_name, arguments) triples.

        All calls are dispatched concurrently; results are returned in
        the same order as the input list regardless of completion order.
        A failed call never cancels sibling calls.
        """
        if not calls:
            return []

        tasks = [
            asyncio.create_task(self._dispatch(call_id, tool_name, arguments, task_id))
            for call_id, tool_name, arguments in calls
        ]

        # return_exceptions=True means one failure won't cancel others
        raw = await asyncio.gather(*tasks, return_exceptions=True)

        results: list[tuple[str, ToolResult]] = []
        # gather preserves order and returns one outcome per task, so the two
        # sequences are equal-length by construction; strict= locks that in.
        for (call_id, _, _), outcome in zip(calls, raw, strict=True):
            if isinstance(outcome, BaseException):
                results.append((
                    call_id,
                    ToolResult(
                        success=False,
                        output=None,
                        error=f"Unhandled exception during execution: {outcome}",
                    ),
                ))
            else:
                results.append((call_id, outcome))

        return results

    async def _dispatch(
        self,
        call_id: str,
        tool_name: str,
        arguments: dict[str, Any],
        task_id: str | None = None,
    ) -> ToolResult:
        """Look up and execute a single tool call."""
        tool = self._registry.get(tool_name)
        if tool is None:
            if self._audit_store:
                self._audit_store.record(
                    "tool_not_found",
                    task_id=task_id,
                    tool_name=tool_name,
                    decision="deny",
                )
            return ToolResult(
                success=False,
                output=None,
                error=(
                    f"Tool '{tool_name}' not found in registry. "
                    "Available tools: "
                    + ", ".join(s.qualified_name for s in self._registry.list_schemas())
                ),
            )
        if self._validator is not None:
            errors = self._validator.validate(tool.schema, arguments)
            if errors:
                if self._audit_store:
                    self._audit_store.record(
                        "tool_validation_failed",
                        task_id=task_id,
                        tool_name=tool_name,
                        decision="deny",
                        details={"errors": errors},
                    )
                return ToolResult(
                    success=False,
                    output=None,
                    error="Invalid tool arguments: " + "; ".join(errors),
                )
        if self._requires_approval(tool.schema.risk):
            if self._approval is None:
                if self._audit_store:
                    self._audit_store.record(
                        "approval_missing",
                        task_id=task_id,
                        tool_name=tool_name,
                        decision="deny",
                    )
                return ToolResult(
                    success=False,
                    output=None,
                    error=(
                        f"Tool '{tool_name}' requires approval, "
                        "but no approval service is configured"
                    ),
                    metadata={"approval_required": True},
                )
            if not await self._approval.approve(tool, arguments, task_id=task_id):
                if self._audit_store:
                    self._audit_store.record(
                        "approval_required",
                        task_id=task_id,
                        tool_name=tool_name,
                        decision="pending",
                    )
                return ToolResult(
                    success=False,
                    output=None,
                    error=f"Tool '{tool_name}' is pending or denied by the approval policy",
                    metadata={"approval_required": True},
                )
        result = await tool.execute(arguments)
        if self._audit_store:
            self._audit_store.record(
                "tool_executed",
                task_id=task_id,
                tool_name=tool_name,
                decision="allow" if result.success else "error",
            )
        return result

    def _requires_approval(self, risk: ToolRisk) -> bool:
        """Compare ordered risk tiers without relying on enum ordering."""
        levels = {ToolRisk.LOW: 0, ToolRisk.MEDIUM: 1, ToolRisk.HIGH: 2}
        return levels[risk] >= levels[self._approval_required_risk]
