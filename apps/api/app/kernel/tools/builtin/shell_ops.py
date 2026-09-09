"""
Built-in shell execution tool.

Delegates to IExecutionEnvironment.exec so the persistent-session
vs one-shot strategy is an environment concern, not a tool concern.
"""

from __future__ import annotations

from typing import Any

from app.kernel.interfaces.environment import IExecutionEnvironment
from app.kernel.interfaces.tool import ITool, ToolParameter, ToolResult, ToolRisk, ToolSchema


class ShellExecTool(ITool):
    """
    Run a shell command in the persistent execution environment.

    stdout/stderr are token-truncated with head+tail preserved.
    Sandbox violations return a structured DENIED result the model
    can use to adjust the command rather than blindly retrying.
    """

    def __init__(self, env: IExecutionEnvironment) -> None:
        self._env = env

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="shell_exec",
            description=(
                "Execute a shell command. "
                "Use for build, test, grep, git, and other CLI operations. "
                "The session is persistent — environment variables and working "
                "directory carry over between calls."
            ),
            risk=ToolRisk.HIGH,
            parameters=(
                ToolParameter(
                    name="command",
                    type="string",
                    description="Shell command to run.",
                ),
                ToolParameter(
                    name="timeout_ms",
                    type="number",
                    description="Max milliseconds to wait (default 30000).",
                    required=False,
                    default=30_000,
                ),
                ToolParameter(
                    name="stdin",
                    type="string",
                    description="Optional text to pipe to stdin.",
                    required=False,
                ),
            ),
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            result = await self._env.exec(
                command=arguments["command"],
                timeout_ms=float(arguments.get("timeout_ms", 30_000)),
                stdin=arguments.get("stdin"),
            )
            return ToolResult(
                success=result.exit_code == 0,
                output=result.to_model_content(),
                error=None if result.exit_code == 0 else f"exit {result.exit_code}",
                metadata={
                    "exit_code": result.exit_code,
                    "duration_ms": result.duration_ms,
                    "truncated": result.truncated,
                    "status": result.status,
                },
            )
        except Exception as exc:
            return ToolResult(success=False, output=None, error=str(exc))
