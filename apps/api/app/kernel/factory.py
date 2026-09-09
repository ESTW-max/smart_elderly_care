"""Environment-configured assembly for the agent kernel."""

from __future__ import annotations

from pathlib import Path

from app.core.config import Settings
from app.kernel.approval import SQLiteApprovalStore
from app.kernel.audit import SQLiteAuditStore
from app.kernel.context import ContextBudget, ContextManager
from app.kernel.environment.local import LocalEnvironment
from app.kernel.interfaces.loop import Budget, TurnSettings
from app.kernel.interfaces.tool import ToolRisk
from app.kernel.loop.orchestrator import Orchestrator
from app.kernel.model.deepseek import DeepSeekProvider
from app.kernel.persistence import SQLiteTaskStore
from app.kernel.security import SafeCommandPolicy, WorkspaceFilePolicy
from app.kernel.tools.builtin import (
    ListDirTool,
    PatchFileTool,
    ReadFileTool,
    ShellExecTool,
    WriteFileTool,
)
from app.kernel.tools.executor import ToolExecutor
from app.kernel.tools.registry import ToolRegistry
from app.kernel.tools.schema import SchemaValidator


def create_deepseek_agent(
    settings: Settings,
    workspace: str | Path = ".",
) -> tuple[Orchestrator, LocalEnvironment]:
    """Build a DeepSeek-backed agent using only environment-derived settings."""
    if not settings.deepseek_api_key:
        raise ValueError("DEEPSEEK_API_KEY must be configured in the environment")

    environment = LocalEnvironment(
        workspace=workspace,
        command_policy=SafeCommandPolicy(
            allowed_commands={
                command.strip()
                for command in settings.agent_allowed_commands.split(",")
                if command.strip()
            }
        ),
        file_policy=WorkspaceFilePolicy(
            can_read=settings.agent_file_read_enabled,
            can_write=settings.agent_file_write_enabled,
        ),
        max_output_chars=settings.agent_max_output_chars,
        max_cpu_seconds=settings.agent_max_cpu_seconds,
        max_file_size_bytes=settings.agent_max_file_size_bytes,
        blocked_env_prefixes=tuple(
            prefix.strip()
            for prefix in settings.agent_blocked_env_prefixes.split(",")
            if prefix.strip()
        ),
    )
    registry = ToolRegistry()
    registry.register_many(
        [
            ReadFileTool(environment),
            WriteFileTool(environment),
            PatchFileTool(environment),
            ListDirTool(environment),
            ShellExecTool(environment),
        ]
    )
    executor = ToolExecutor(
        registry,
        validator=SchemaValidator(),
        approval=SQLiteApprovalStore(settings.agent_state_database_path),
        approval_required_risk=ToolRisk(settings.agent_approval_required_risk.lower()),
        audit_store=SQLiteAuditStore(settings.agent_state_database_path),
    )
    provider = DeepSeekProvider(
        api_key=settings.deepseek_api_key,
        model=settings.deepseek_model,
        base_url=settings.deepseek_base_url,
        temperature=settings.deepseek_temperature,
        max_tokens=settings.deepseek_max_output_tokens,
        timeout_seconds=settings.deepseek_timeout_seconds,
        max_retries=settings.deepseek_max_retries,
    )
    orchestrator = Orchestrator(
        executor=executor,
        registry=registry,
        model_provider=provider,
        task_store=SQLiteTaskStore(settings.agent_state_database_path),
        context_manager=ContextManager(
            ContextBudget(
                max_total_tokens=settings.agent_context_max_tokens,
                max_message_tokens=settings.agent_message_max_tokens,
                max_tool_output_tokens=settings.agent_tool_output_max_tokens,
            )
        ),
        default_settings=TurnSettings(
            model=settings.deepseek_model,
            system_prompt=settings.agent_system_prompt,
            budget=Budget(
                max_steps=settings.agent_max_steps,
                max_tokens=settings.agent_max_tokens,
                max_seconds=settings.agent_max_seconds,
            ),
            tool_names=frozenset(),
        ),
    )
    return orchestrator, environment
