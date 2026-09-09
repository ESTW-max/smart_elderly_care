"""
ToolRegistry - In-memory registry for tool discovery and lifecycle.

Open/Closed: new tools are registered via register(), not by
modifying any consumer. Namespace isolation prevents name collisions
across plugins or extensions.
"""

from __future__ import annotations

from app.kernel.interfaces.tool import ITool, IToolRegistry, ToolSchema


class ToolRegistry(IToolRegistry):
    """
    Thread-safe (GIL-protected for CPython) in-memory tool registry.

    Tools are keyed by their qualified name (namespace.name or just name
    for the default namespace) so extensions can't shadow built-ins.
    """

    def __init__(self) -> None:
        self._tools: dict[str, ITool] = {}

    # ------------------------------------------------------------------
    # IToolRegistry implementation
    # ------------------------------------------------------------------

    def register(self, tool: ITool) -> None:
        """
        Add a tool to the registry.

        Raises ValueError if the qualified name is already taken, which
        forces intentional overriding via unregister → register.
        """
        qname = tool.schema.qualified_name
        if qname in self._tools:
            raise ValueError(
                f"Tool '{qname}' is already registered. "
                "Call unregister() first if you intend to replace it."
            )
        self._tools[qname] = tool

    def unregister(self, qualified_name: str) -> None:
        """Remove a tool. Silently ignores unknown names."""
        self._tools.pop(qualified_name, None)

    def get(self, qualified_name: str) -> ITool | None:
        """Look up by qualified name, return None if absent."""
        return self._tools.get(qualified_name)

    def list_schemas(self, namespace: str | None = None) -> list[ToolSchema]:
        """
        Return all tool schemas, optionally filtered to one namespace.

        The model only sees tools returned here, so narrowing by
        namespace gives dynamic tool-exposure control at the call site.
        """
        schemas = [t.schema for t in self._tools.values()]
        if namespace is not None:
            schemas = [s for s in schemas if s.namespace == namespace]
        return schemas

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def register_many(self, tools: list[ITool]) -> None:
        """Bulk-register a list of tools in one call."""
        for tool in tools:
            self.register(tool)

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, qualified_name: str) -> bool:
        return qualified_name in self._tools
