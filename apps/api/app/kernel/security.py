"""Pluggable, fail-closed execution policies for Agent tools and environments."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class AccessDecision(str, Enum):
    """Policy decision for an Agent action."""

    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class PolicyResult:
    """Structured policy result that can be returned to the model."""

    decision: AccessDecision
    reason: str

    @property
    def allowed(self) -> bool:
        """Whether the action is allowed."""
        return self.decision == AccessDecision.ALLOW


class ICommandPolicy(ABC):
    """Contract for command authorization strategies."""

    @abstractmethod
    def check(self, command: str) -> PolicyResult:
        """Return an allow/deny decision for a shell command."""
        ...


class IFilePolicy(ABC):
    """Contract for filesystem authorization strategies."""

    @abstractmethod
    def check_read(self, path: str) -> PolicyResult:
        """Return an allow/deny decision for reading a path."""
        ...

    @abstractmethod
    def check_write(self, path: str) -> PolicyResult:
        """Return an allow/deny decision for writing a path."""
        ...


class SafeCommandPolicy(ICommandPolicy):
    """Allow-list command policy with explicit deny rules.

    Commands are denied by default unless their executable is present in
    ``allowed_commands``. Dangerous shell metacharacters and privilege,
    destructive, or secret-disclosure patterns are always denied.
    """

    _DANGEROUS_PATTERNS = (
        r"[;&|`$<>]",
        r"(^|\s)(sudo|su|doas)(\s|$)",
        r"(^|\s)(rm|rmdir|mkfs|dd|shutdown|reboot|killall)(\s|$)",
        r"(^|\s)(chmod|chown)\s+(-R\s+)?(/|\.\.)",
        r"(^|\s)(curl|wget)\s+.*\|\s*(sh|bash|zsh)(\s|$)",
        r"(^|\s)(env|printenv)(\s|$)",
        r"(^|\s)(cat|less|more)\s+.*(\.env|id_rsa|credentials|secret)",
    )

    def __init__(
        self,
        allowed_commands: frozenset[str] | set[str] | None = None,
        deny_patterns: tuple[str, ...] = (),
    ) -> None:
        default_commands = {"pwd", "ls", "find", "grep", "git", "python", "pytest", "ruff"}
        self._allowed_commands = frozenset(allowed_commands or default_commands)
        self._patterns = tuple(self._DANGEROUS_PATTERNS) + deny_patterns

    def check(self, command: str) -> PolicyResult:
        command = command.strip()
        if not command:
            return PolicyResult(AccessDecision.DENY, "Empty shell command is not allowed")
        for pattern in self._patterns:
            if re.search(pattern, command, re.IGNORECASE):
                return PolicyResult(
                    AccessDecision.DENY,
                    f"Command denied by security policy: matched '{pattern}'",
                )
        executable = command.split(maxsplit=1)[0].rsplit("/", maxsplit=1)[-1]
        if executable not in self._allowed_commands:
            return PolicyResult(
                AccessDecision.DENY,
                f"Command '{executable}' is not in the configured command allow-list",
            )
        return PolicyResult(AccessDecision.ALLOW, "Command allowed by security policy")


class WorkspaceFilePolicy(IFilePolicy):
    """Combine workspace boundary and independent read/write permissions."""

    def __init__(self, can_read: bool = True, can_write: bool = False) -> None:
        self._can_read = can_read
        self._can_write = can_write

    def check_read(self, path: str) -> PolicyResult:
        if not self._can_read:
            return PolicyResult(AccessDecision.DENY, f"File read denied by policy: {path}")
        return PolicyResult(AccessDecision.ALLOW, "File read allowed by policy")

    def check_write(self, path: str) -> PolicyResult:
        if not self._can_write:
            return PolicyResult(AccessDecision.DENY, f"File write denied by policy: {path}")
        return PolicyResult(AccessDecision.ALLOW, "File write allowed by policy")
