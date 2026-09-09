"""Abstract model provider contract used by the orchestration loop."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class IModelProvider(ABC):
    """Provider-neutral interface for chat completion and tool calling."""

    @abstractmethod
    async def complete(self, request: dict[str, Any]) -> dict[str, Any]:
        """Return the kernel-normalized model response."""
        ...
