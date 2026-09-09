"""
Tool interfaces - Abstractions for tool definition, registration, and execution.

Interface Segregation: ITool (execution), IToolValidator (validation),
IToolRegistry (discovery) are separate — callers depend only on what they use.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Tool schema / metadata
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolParameter:
    """Describes one parameter of a tool's callable signature."""

    name: str
    type: str          # JSON Schema type string: "string", "integer", …
    description: str
    required: bool = True
    enum: tuple[str, ...] | None = None
    default: Any = None


class ToolRisk(str, Enum):
    """Risk tier used by authorization policies."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


@dataclass(frozen=True)
class ToolSchema:
    """
    JSON-Schema-compatible description of a tool.

    Used both to expose the tool to the model and to validate
    incoming arguments before execution.
    """

    name: str
    description: str
    parameters: tuple[ToolParameter, ...] = field(default_factory=tuple)
    namespace: str = "default"
    risk: ToolRisk = ToolRisk.LOW

    @property
    def qualified_name(self) -> str:
        """Namespace-prefixed name prevents collisions across extensions."""
        return f"{self.namespace}.{self.name}" if self.namespace != "default" else self.name

    def to_openai_function(self) -> dict[str, Any]:
        """Render as an OpenAI function-call compatible dict."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for p in self.parameters:
            prop: dict[str, Any] = {"type": p.type, "description": p.description}
            if p.enum:
                prop["enum"] = list(p.enum)
            if p.default is not None:
                prop["default"] = p.default
            properties[p.name] = prop
            if p.required:
                required.append(p.name)
        return {
            "type": "function",
            "function": {
                "name": self.qualified_name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


# ---------------------------------------------------------------------------
# Execution result
# ---------------------------------------------------------------------------


@dataclass
class ToolResult:
    """
    Structured outcome of a tool execution.

    The error field is intentionally descriptive: 'denied by sandbox
    because path /etc is outside workspace' gives the model enough
    context to self-correct without a retry loop.
    """

    success: bool
    output: Any
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Interfaces
# ---------------------------------------------------------------------------


class ITool(ABC):
    """
    Single-Responsibility: one tool, one action.

    All concrete tools implement this interface so the executor
    can treat them uniformly (LSP).
    """

    @property
    @abstractmethod
    def schema(self) -> ToolSchema:
        """Static description exposed to the model and validator."""
        ...

    @abstractmethod
    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """
        Run the tool with the given arguments.

        Must never raise unhandled exceptions — return a ToolResult
        with success=False and a descriptive error instead.
        """
        ...


class IToolValidator(ABC):
    """
    Single-Responsibility: validate tool arguments against schema.

    Separated from ITool so validation can be swapped (e.g. strict
    JSON Schema vs. Pydantic) without touching execution logic.
    """

    @abstractmethod
    def validate(self, schema: ToolSchema, arguments: dict[str, Any]) -> list[str]:
        """
        Return a list of validation error messages.

        An empty list means the arguments are valid.
        """
        ...


class IToolRegistry(ABC):
    """
    Single-Responsibility: tool discovery and lifecycle management.

    Open/Closed: new tools are added via register(), not by modifying
    the orchestrator or executor.
    """

    @abstractmethod
    def register(self, tool: ITool) -> None:
        """Add a tool. Raises ValueError on name collision within a namespace."""
        ...

    @abstractmethod
    def unregister(self, qualified_name: str) -> None:
        """Remove a tool by its qualified name."""
        ...

    @abstractmethod
    def get(self, qualified_name: str) -> ITool | None:
        """Look up a tool by qualified name, or return None."""
        ...

    @abstractmethod
    def list_schemas(self, namespace: str | None = None) -> list[ToolSchema]:
        """
        Return schemas for all visible tools, optionally filtered by namespace.

        Dynamic exposure: callers control which tools the model sees
        at each stage of the loop.
        """
        ...


class IToolApproval(ABC):
    """Contract for explicit user or policy approval of risky actions."""

    @abstractmethod
    async def approve(
        self,
        tool: ITool,
        arguments: dict[str, Any],
        task_id: str | None = None,
    ) -> bool:
        """Return true only when the exact action is approved for this task."""
        ...


class IToolExecutor(ABC):
    """
    Single-Responsibility: dispatch tool calls and collect results.

    Parallel execution of independent calls is an implementation detail
    hidden behind this interface.
    """

    @abstractmethod
    async def execute_many(
        self,
        calls: list[tuple[str, str, dict[str, Any]]],
        task_id: str | None = None,
        # (call_id, tool_qualified_name, arguments)
    ) -> list[tuple[str, ToolResult]]:
        """
        Execute a batch of tool calls.

        Independent calls may run concurrently; cancellation signals
        propagate to all in-flight calls.

        Returns a list of (call_id, result) pairs in the same order.
        """
        ...
