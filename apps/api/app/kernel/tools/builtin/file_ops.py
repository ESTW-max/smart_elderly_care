"""
Built-in file operation tools.

Each tool is a single ITool implementation with one responsibility.
They delegate to IExecutionEnvironment so the actual I/O strategy
(local, remote, sandbox) is swapped without touching tool logic — DIP.
"""

from __future__ import annotations

from typing import Any

from app.kernel.interfaces.environment import FilePatch, IExecutionEnvironment
from app.kernel.interfaces.tool import ITool, ToolParameter, ToolResult, ToolRisk, ToolSchema


class ReadFileTool(ITool):
    """Read a file from the execution environment."""

    def __init__(self, env: IExecutionEnvironment) -> None:
        self._env = env

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="read_file",
            description=(
                "Read the contents of a file. Large files are truncated with "
                "head and tail preserved."
            ),
            parameters=(
                ToolParameter(
                    name="path",
                    type="string",
                    description="Absolute or workspace-relative file path.",
                ),
                ToolParameter(
                    name="max_tokens",
                    type="integer",
                    description="Maximum tokens to return (default 8000).",
                    required=False,
                    default=8000,
                ),
            ),
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            result = await self._env.read_file(
                path=arguments["path"],
                max_tokens=arguments.get("max_tokens", 8000),
            )
            return ToolResult(
                success=True,
                output=result.content,
                metadata={"truncated": result.truncated, "size_bytes": result.size_bytes},
            )
        except FileNotFoundError:
            return ToolResult(
                success=False,
                output=None,
                error=f"File not found: {arguments.get('path')}",
            )
        except Exception as exc:
            return ToolResult(success=False, output=None, error=str(exc))


class WriteFileTool(ITool):
    """Create or overwrite a file with new content."""

    def __init__(self, env: IExecutionEnvironment) -> None:
        self._env = env

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="write_file",
            description="Create or fully overwrite a file. Prefer patch_file for partial edits.",
            risk=ToolRisk.HIGH,
            parameters=(
                ToolParameter(
                    name="path",
                    type="string",
                    description="File path to write.",
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="Full file content to write.",
                ),
            ),
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            patch = FilePatch(
                path=arguments["path"],
                old_text=None,  # None = create/overwrite
                new_text=arguments["content"],
            )
            await self._env.apply_patch(patch)
            return ToolResult(success=True, output=f"Wrote {arguments['path']}")
        except Exception as exc:
            return ToolResult(success=False, output=None, error=str(exc))


class PatchFileTool(ITool):
    """
    Apply a targeted text replacement to a file.

    Using structured patches (old → new) instead of full overwrites
    reduces token cost and enables conflict detection.
    """

    def __init__(self, env: IExecutionEnvironment) -> None:
        self._env = env

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="patch_file",
            description=(
                "Replace exact text in a file. old_text must match the current content exactly. "
                "Raises an error if the text is not found — no silent partial edits."
            ),
            risk=ToolRisk.HIGH,
            parameters=(
                ToolParameter(
                    name="path",
                    type="string",
                    description="File path to patch.",
                ),
                ToolParameter(
                    name="old_text",
                    type="string",
                    description="The exact text to replace.",
                ),
                ToolParameter(
                    name="new_text",
                    type="string",
                    description="Replacement text.",
                ),
            ),
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            patch = FilePatch(
                path=arguments["path"],
                old_text=arguments["old_text"],
                new_text=arguments["new_text"],
            )
            await self._env.apply_patch(patch)
            return ToolResult(success=True, output=f"Patched {arguments['path']}")
        except (FileNotFoundError, ValueError) as exc:
            return ToolResult(
                success=False,
                output=None,
                error=f"{type(exc).__name__}: {exc}",
            )
        except Exception as exc:
            return ToolResult(success=False, output=None, error=str(exc))


class ListDirTool(ITool):
    """List the contents of a directory."""

    def __init__(self, env: IExecutionEnvironment) -> None:
        self._env = env

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="list_dir",
            description="List files and directories at the given path.",
            parameters=(
                ToolParameter(
                    name="path",
                    type="string",
                    description="Directory path to list.",
                ),
            ),
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            entries = await self._env.list_dir(arguments["path"])
            return ToolResult(success=True, output=entries)
        except Exception as exc:
            return ToolResult(success=False, output=None, error=str(exc))
