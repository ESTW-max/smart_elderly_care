"""
Environment interfaces - Abstractions for command execution and filesystem ops.

Separating the interface from LocalEnvironment / RemoteEnvironment / Sandbox
means the orchestrator and tools stay testable without a real shell.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

# ---------------------------------------------------------------------------
# Enumerations and value types
# ---------------------------------------------------------------------------


class ExecStatus(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    DENIED = "denied"     # Blocked by sandbox policy


@dataclass
class ExecResult:
    """
    Output of a shell command execution.

    stdout/stderr are token-truncated (not byte-truncated) so the
    head and tail of large outputs are always preserved when fed back
    to the model.
    """

    status: ExecStatus
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: float
    truncated: bool = False

    def to_model_content(self) -> str:
        """Render a concise, model-readable summary."""
        parts = []
        if self.stdout:
            parts.append(f"stdout:\n{self.stdout}")
        if self.stderr:
            parts.append(f"stderr:\n{self.stderr}")
        if self.status == ExecStatus.DENIED:
            parts.append("[DENIED by sandbox — adjust the command and retry]")
        elif self.exit_code != 0:
            parts.append(f"[exit {self.exit_code}]")
        if self.truncated:
            parts.append("[output was truncated; head and tail preserved]")
        return "\n".join(parts) if parts else "[no output]"


@dataclass
class FilePatch:
    """
    A structured file modification: old_text → new_text within a path.

    Using patches instead of full-file rewrites reduces token cost,
    makes diffs auditable, and enables conflict detection.
    """

    path: str
    old_text: str | None     # None means create new file
    new_text: str
    encoding: str = "utf-8"


@dataclass
class FileReadResult:
    """Result of reading a file, with token-budget-aware truncation."""

    path: str
    content: str
    truncated: bool = False
    size_bytes: int = 0


@dataclass
class EnvironmentSnapshot:
    """
    A point-in-time capture of the execution environment state.

    Used to resume sessions after interruption without losing
    working directory, environment variables, or shell aliases.
    """

    cwd: str
    env_vars: dict[str, str] = field(default_factory=dict)
    shell_aliases: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------


class IExecutionEnvironment(ABC):
    """
    Unified abstraction over local, remote, and sandboxed environments.

    Implementations (LocalEnvironment, RemoteEnvironment, SandboxEnvironment)
    are interchangeable — the orchestrator depends only on this interface (DIP).
    """

    # -- Session lifecycle --------------------------------------------------

    @abstractmethod
    async def start(self) -> None:
        """
        Initialise a persistent shell session.

        A persistent session (vs one-shot bash -c) is required for
        workflows like: start server → wait → send request → read logs.
        """
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Cleanly terminate the session and release resources."""
        ...

    @abstractmethod
    async def snapshot(self) -> EnvironmentSnapshot:
        """Capture current state for later resumption."""
        ...

    @abstractmethod
    async def restore(self, snapshot: EnvironmentSnapshot) -> None:
        """Resume from a previously captured snapshot."""
        ...

    # -- Command execution --------------------------------------------------

    @abstractmethod
    async def exec(
        self,
        command: str,
        timeout_ms: float = 30_000,
        stdin: str | None = None,
    ) -> ExecResult:
        """
        Run a command in the persistent session.

        stdout/stderr are token-truncated, preserving head and tail.
        Sandbox violations return ExecStatus.DENIED with a description
        the model can act on.
        """
        ...

    # -- Filesystem operations ----------------------------------------------

    @abstractmethod
    async def read_file(
        self,
        path: str,
        max_tokens: int = 8_000,
    ) -> FileReadResult:
        """Read a file, truncating to max_tokens while keeping head+tail."""
        ...

    @abstractmethod
    async def apply_patch(self, patch: FilePatch) -> None:
        """
        Apply a structured patch to a file.

        Raises FileNotFoundError if old_text is set but the file is missing.
        Raises ValueError if old_text does not match the current content.
        """
        ...

    @abstractmethod
    async def list_dir(self, path: str) -> list[str]:
        """Return the contents of a directory as relative path strings."""
        ...

    @abstractmethod
    async def exists(self, path: str) -> bool:
        """Check whether a path exists in this environment."""
        ...
