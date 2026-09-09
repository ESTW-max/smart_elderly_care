"""Local execution environment with a persistent, policy-controlled shell."""

from __future__ import annotations

import asyncio
import os
import shlex
import signal
import time
import uuid
from pathlib import Path

try:
    import resource
except ImportError:  # pragma: no cover - unavailable on Windows
    resource = None

from app.kernel.interfaces.environment import (
    EnvironmentSnapshot,
    ExecResult,
    ExecStatus,
    FilePatch,
    FileReadResult,
    IExecutionEnvironment,
)
from app.kernel.security import ICommandPolicy, IFilePolicy


class LocalEnvironment(IExecutionEnvironment):
    """Persistent Bash environment with filesystem and command policies."""

    def __init__(
        self,
        workspace: str | Path = ".",
        command_policy: ICommandPolicy | None = None,
        file_policy: IFilePolicy | None = None,
        max_output_chars: int = 8_000,
        blocked_env_prefixes: tuple[str, ...] = ("DEEPSEEK_", "OPENAI_", "ANTHROPIC_"),
        max_cpu_seconds: int | None = None,
        max_file_size_bytes: int = 10_000_000,
    ) -> None:
        self._workspace = Path(workspace).resolve()
        self._workspace.mkdir(parents=True, exist_ok=True)
        self._command_policy = command_policy
        self._file_policy = file_policy
        self._max_output_chars = max_output_chars
        self._blocked_env_prefixes = blocked_env_prefixes
        self._max_cpu_seconds = max_cpu_seconds
        self._max_file_size_bytes = max_file_size_bytes
        self._cwd = self._workspace
        self._env_vars = self._safe_environment(os.environ)
        self._running = False
        self._shell: asyncio.subprocess.Process | None = None
        self._shell_lock = asyncio.Lock()

    async def start(self) -> None:
        """Start the long-lived Bash process used by non-stdin commands."""
        if self._running and self._shell and self._shell.returncode is None:
            return
        self._shell = await asyncio.create_subprocess_exec(
            "/bin/bash",
            "--noprofile",
            "--norc",
            "-s",
            cwd=self._cwd,
            env=self._env_vars,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            start_new_session=True,
            preexec_fn=self._set_resource_limits if resource is not None else None,
        )
        self._running = True

    async def stop(self) -> None:
        """Terminate the shell and its complete process group."""
        self._running = False
        if self._shell is not None and self._shell.returncode is None:
            self._terminate_process_group(self._shell)
            await self._shell.wait()
        self._shell = None

    async def snapshot(self) -> EnvironmentSnapshot:
        """Capture the current working directory and safe environment."""
        return EnvironmentSnapshot(
            cwd=str(self._cwd),
            env_vars=dict(self._env_vars),
            shell_aliases={},
        )

    async def restore(self, snapshot: EnvironmentSnapshot) -> None:
        """Restore a snapshot and restart the shell in the saved directory."""
        restored_cwd = Path(snapshot.cwd).resolve()
        restored_cwd.relative_to(self._workspace)
        self._cwd = restored_cwd
        self._env_vars = self._safe_environment(snapshot.env_vars)
        if self._running:
            await self.stop()
            await self.start()

    async def exec(
        self,
        command: str,
        timeout_ms: float = 30_000,
        stdin: str | None = None,
    ) -> ExecResult:
        """Execute a command, preserving shell state when stdin is absent."""
        start = time.time()
        if self._command_policy is not None:
            decision = self._command_policy.check(command)
            if not decision.allowed:
                return ExecResult(ExecStatus.DENIED, "", decision.reason, -1, 0)
        try:
            if stdin is not None:
                return await self._exec_with_stdin(command, timeout_ms, stdin, start)
            return await self._exec_persistent(command, timeout_ms, start)
        except Exception as exc:
            return ExecResult(
                ExecStatus.FAILURE,
                "",
                str(exc),
                -1,
                (time.time() - start) * 1000,
            )

    async def _exec_persistent(
        self, command: str, timeout_ms: float, start: float
    ) -> ExecResult:
        await self.start()
        assert self._shell is not None
        assert self._shell.stdin is not None
        assert self._shell.stdout is not None
        marker = f"__AGENT_RESULT_{uuid.uuid4().hex}__"
        async with self._shell_lock:
            payload = (
                f"{command}\n"
                f"__agent_status=$?\n"
                f"printf '\\n{marker}:%s:%s\\n' \"$__agent_status\" \"$PWD\"\n"
            )
            self._shell.stdin.write(payload.encode())
            await self._shell.stdin.drain()
            output = bytearray()
            deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
            try:
                while True:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise TimeoutError
                    line = await asyncio.wait_for(
                        self._shell.stdout.readline(), timeout=remaining
                    )
                    if not line:
                        raise RuntimeError("Persistent shell exited unexpectedly")
                    if line.startswith(marker.encode()):
                        break
                    output.extend(line)
            except TimeoutError:
                self._terminate_process_group(self._shell)
                await self._shell.wait()
                self._shell = None
                self._running = False
                return ExecResult(
                    ExecStatus.TIMEOUT,
                    "",
                    "Command timed out",
                    -1,
                    (time.time() - start) * 1000,
                )

        fields = line.decode("utf-8", errors="replace").strip().split(":", 2)
        if len(fields) != 3:
            raise RuntimeError("Invalid persistent shell completion marker")
        exit_code = int(fields[1])
        new_cwd = Path(fields[2]).resolve()
        try:
            new_cwd.relative_to(self._workspace)
            self._cwd = new_cwd
        except ValueError:
            # A command may cd outside the workspace; keep the shell usable but
            # force the next command back into the configured workspace.
            await self.stop()
            self._cwd = self._workspace
        stdout, truncated = self._limit_output(
            bytes(output).decode("utf-8", errors="replace")
        )
        return ExecResult(
            ExecStatus.SUCCESS if exit_code == 0 else ExecStatus.FAILURE,
            stdout,
            "",
            exit_code,
            (time.time() - start) * 1000,
            truncated,
        )

    async def _exec_with_stdin(
        self, command: str, timeout_ms: float, stdin: str, start: float
    ) -> ExecResult:
        proc = await asyncio.create_subprocess_shell(
            f"printf '%s' {shlex.quote(stdin)} | {command}",
            cwd=self._cwd,
            env=self._env_vars,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
            preexec_fn=self._set_resource_limits if resource is not None else None,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                proc.communicate(), timeout=timeout_ms / 1000
            )
        except TimeoutError:
            self._terminate_process_group(proc)
            await proc.wait()
            return ExecResult(
                ExecStatus.TIMEOUT,
                "",
                "Command timed out",
                -1,
                (time.time() - start) * 1000,
            )
        stdout, stdout_truncated = self._limit_output(
            stdout_bytes.decode("utf-8", errors="replace")
        )
        stderr, stderr_truncated = self._limit_output(
            stderr_bytes.decode("utf-8", errors="replace")
        )
        return ExecResult(
            ExecStatus.SUCCESS if proc.returncode == 0 else ExecStatus.FAILURE,
            stdout,
            stderr,
            proc.returncode or 0,
            (time.time() - start) * 1000,
            stdout_truncated or stderr_truncated,
        )

    def _limit_output(self, value: str) -> tuple[str, bool]:
        if len(value) <= self._max_output_chars:
            return value, False
        return value[: self._max_output_chars] + "\n[... truncated ...]", True

    async def read_file(self, path: str, max_tokens: int = 8_000) -> FileReadResult:
        resolved = self._resolve_path(path)
        self._check_read(resolved)
        try:
            size = resolved.stat().st_size
            if size > self._max_file_size_bytes:
                raise ValueError(f"File '{path}' exceeds the configured size limit")
            content = resolved.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Failed to read {path}: {exc}") from exc
        max_chars = max(1, max_tokens) * 4
        if len(content) > max_chars:
            half = max_chars // 2
            content = content[:half] + "\n\n[... middle truncated ...]\n\n" + content[-half:]
            return FileReadResult(str(resolved), content, True, size)
        return FileReadResult(str(resolved), content, False, size)

    async def apply_patch(self, patch: FilePatch) -> None:
        resolved = self._resolve_path(patch.path)
        self._check_write(resolved)
        if patch.old_text is None:
            resolved.parent.mkdir(parents=True, exist_ok=True)
            resolved.write_text(patch.new_text, encoding=patch.encoding)
            return
        if not resolved.exists():
            raise FileNotFoundError(f"Cannot patch non-existent file: {patch.path}")
        current = resolved.read_text(encoding=patch.encoding)
        count = current.count(patch.old_text)
        if count == 0:
            raise ValueError(f"old_text not found in {patch.path}")
        if count > 1:
            raise ValueError(f"old_text appears {count} times in {patch.path}")
        resolved.write_text(current.replace(patch.old_text, patch.new_text, 1), encoding=patch.encoding)

    async def list_dir(self, path: str) -> list[str]:
        resolved = self._resolve_path(path)
        self._check_read(resolved)
        if not resolved.is_dir():
            raise NotADirectoryError(f"{path} is not a directory")
        return sorted(entry.name for entry in resolved.iterdir())

    async def exists(self, path: str) -> bool:
        return self._resolve_path(path).exists()

    def _check_read(self, path: Path) -> None:
        if self._file_policy is not None:
            decision = self._file_policy.check_read(str(path))
            if not decision.allowed:
                raise PermissionError(decision.reason)

    def _check_write(self, path: Path) -> None:
        if self._file_policy is not None:
            decision = self._file_policy.check_write(str(path))
            if not decision.allowed:
                raise PermissionError(decision.reason)

    def _safe_environment(self, environment: dict[str, str]) -> dict[str, str]:
        blocked = {"DEEPSEEK_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"}
        return {
            key: value
            for key, value in environment.items()
            if key not in blocked
            and not any(key.startswith(prefix) for prefix in self._blocked_env_prefixes)
        }

    def _set_resource_limits(self) -> None:
        if resource is None:
            return
        if self._max_cpu_seconds is not None:
            resource.setrlimit(resource.RLIMIT_CPU, (self._max_cpu_seconds, self._max_cpu_seconds))
        resource.setrlimit(resource.RLIMIT_FSIZE, (self._max_file_size_bytes, self._max_file_size_bytes))

    @staticmethod
    def _terminate_process_group(proc: asyncio.subprocess.Process) -> None:
        if proc.pid is None:
            return
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def _resolve_path(self, path: str) -> Path:
        candidate = Path(path)
        if not candidate.is_absolute():
            candidate = self._cwd / candidate
        resolved = candidate.resolve()
        try:
            resolved.relative_to(self._workspace)
        except ValueError as exc:
            raise PermissionError(
                f"Path '{path}' is outside the configured workspace '{self._workspace}'"
            ) from exc
        return resolved
