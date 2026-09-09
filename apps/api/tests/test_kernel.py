"""
Integration tests for the agent kernel skeleton layer.

Tests the orchestration loop, tool execution, and environment abstraction
following the interfaces defined in app.kernel.interfaces.
"""

import asyncio
import uuid
from typing import Any

import pytest

from app.kernel.environment.local import LocalEnvironment
from app.kernel.interfaces.loop import AgentTask, Budget, TaskStatus, TurnSettings
from app.kernel.interfaces.tool import ITool, ToolParameter, ToolResult, ToolSchema
from app.kernel.loop.orchestrator import Orchestrator
from app.kernel.tools.executor import ToolExecutor
from app.kernel.tools.registry import ToolRegistry
from app.kernel.tools.schema import SchemaValidator

# ----------------------------------------------------------------------------
# Mock tools for testing
# ----------------------------------------------------------------------------


class EchoTool(ITool):
    """Simple tool that echoes its input."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="echo",
            description="Echo the input message.",
            parameters=(
                ToolParameter(name="message", type="string", description="Message to echo."),
            ),
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, output=arguments.get("message", ""))


class FailTool(ITool):
    """Tool that always fails to test error handling."""

    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="fail",
            description="Always fails.",
            parameters=(),
        )

    async def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=False,
            output=None,
            error="This tool is designed to fail for testing purposes.",
        )


# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------


@pytest.fixture
def registry():
    """Create a ToolRegistry with test tools."""
    reg = ToolRegistry()
    reg.register(EchoTool())
    reg.register(FailTool())
    return reg


@pytest.fixture
def executor(registry):
    """Create a ToolExecutor backed by the test registry."""
    return ToolExecutor(registry, validator=SchemaValidator())


@pytest.fixture
def environment(tmp_path):
    """Create a LocalEnvironment in a temporary directory."""
    return LocalEnvironment(workspace=tmp_path)


# ----------------------------------------------------------------------------
# Tests: ToolRegistry
# ----------------------------------------------------------------------------


def test_registry_register_and_get(registry):
    tool = registry.get("echo")
    assert tool is not None
    assert tool.schema.name == "echo"


def test_registry_duplicate_raises():
    reg = ToolRegistry()
    reg.register(EchoTool())
    with pytest.raises(ValueError, match="already registered"):
        reg.register(EchoTool())


def test_registry_list_schemas(registry):
    schemas = registry.list_schemas()
    names = [s.name for s in schemas]
    assert "echo" in names
    assert "fail" in names


def test_registry_unregister(registry):
    registry.unregister("echo")
    assert registry.get("echo") is None


# ----------------------------------------------------------------------------
# Tests: ToolExecutor
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_executor_execute_many(executor):
    calls = [
        ("call-1", "echo", {"message": "hello"}),
        ("call-2", "echo", {"message": "world"}),
    ]
    results = await executor.execute_many(calls)

    assert len(results) == 2
    assert results[0][0] == "call-1"
    assert results[0][1].success is True
    assert results[0][1].output == "hello"

    assert results[1][0] == "call-2"
    assert results[1][1].success is True
    assert results[1][1].output == "world"


@pytest.mark.asyncio
async def test_executor_tool_not_found(executor):
    calls = [("call-1", "nonexistent", {})]
    results = await executor.execute_many(calls)

    assert len(results) == 1
    assert results[0][1].success is False
    assert "not found" in results[0][1].error


@pytest.mark.asyncio
async def test_executor_tool_failure(executor):
    calls = [("call-1", "fail", {})]
    results = await executor.execute_many(calls)

    assert len(results) == 1
    assert results[0][1].success is False
    assert "designed to fail" in results[0][1].error


# ----------------------------------------------------------------------------
# Tests: LocalEnvironment
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_environment_exec(environment):
    await environment.start()
    result = await environment.exec("echo hello")
    await environment.stop()

    assert result.exit_code == 0
    assert "hello" in result.stdout


@pytest.mark.asyncio
async def test_environment_read_write_file(environment, tmp_path):
    await environment.start()

    # Write a file
    from app.kernel.interfaces.environment import FilePatch

    patch = FilePatch(path="test.txt", old_text=None, new_text="Hello, kernel!")
    await environment.apply_patch(patch)

    # Read it back
    read_result = await environment.read_file("test.txt")
    assert read_result.content == "Hello, kernel!"
    assert not read_result.truncated

    await environment.stop()


@pytest.mark.asyncio
async def test_environment_patch_file(environment, tmp_path):
    await environment.start()

    from app.kernel.interfaces.environment import FilePatch

    # Create initial file
    await environment.apply_patch(
        FilePatch(path="test.txt", old_text=None, new_text="Hello, world!")
    )

    # Patch it
    await environment.apply_patch(
        FilePatch(path="test.txt", old_text="world", new_text="kernel")
    )

    # Verify
    read_result = await environment.read_file("test.txt")
    assert read_result.content == "Hello, kernel!"

    await environment.stop()


@pytest.mark.asyncio
async def test_environment_list_dir(environment, tmp_path):
    await environment.start()

    from app.kernel.interfaces.environment import FilePatch

    # Create some files
    await environment.apply_patch(FilePatch(path="a.txt", old_text=None, new_text="A"))
    await environment.apply_patch(FilePatch(path="b.txt", old_text=None, new_text="B"))

    # List them
    entries = await environment.list_dir(".")
    assert "a.txt" in entries
    assert "b.txt" in entries

    await environment.stop()


# ----------------------------------------------------------------------------
# Tests: Orchestrator
# ----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_runs_task(executor, registry):
    """Test that the orchestrator can run a simple task to completion."""
    orchestrator = Orchestrator(
        executor=executor,
        registry=registry,
        default_settings=TurnSettings(
            model="test-model",
            system_prompt="You are a test agent.",
            budget=Budget(max_steps=10),
            tool_names=frozenset(),
        ),
    )

    task = AgentTask(id=str(uuid.uuid4()), goal="Test goal")

    # Run the task (will terminate immediately with NO_TOOL_CALLS since
    # the stub _call_model returns an empty tool_calls list)
    completed = await orchestrator.run(task)

    assert completed.status.value in ["completed", "cancelled"]
    assert len(completed.turns) >= 1


@pytest.mark.asyncio
async def test_orchestrator_interrupt(executor, registry):
    """Test that interrupt pauses the task cleanly."""
    orchestrator = Orchestrator(executor=executor, registry=registry)
    task = AgentTask(id=str(uuid.uuid4()), goal="Long-running task")

    # Start the task in the background
    run_task = asyncio.create_task(orchestrator.run(task))

    # Let it start
    await asyncio.sleep(0.1)

    # Interrupt it
    await orchestrator.interrupt(task.id)

    # Wait for it to finish
    completed = await run_task

    # Should be paused (or completed if it finished before interrupt)
    assert completed.status.value in ["paused", "completed"]


# ----------------------------------------------------------------------------
# Tests: Termination conditions
# ----------------------------------------------------------------------------


def test_no_tool_calls_condition():
    from app.kernel.interfaces.loop import Step, TerminationReason
    from app.kernel.loop.termination import NoToolCallsCondition

    condition = NoToolCallsCondition()
    task = AgentTask(id="test", goal="test")
    step = Step(
        id="step-1",
        turn_id="turn-1",
        model_request={},
        model_response={},
        tool_calls=[],  # No tool calls
    )

    reason = condition.should_terminate(task, step)
    assert reason == TerminationReason.NO_TOOL_CALLS


def test_budget_exhausted_condition():
    from app.kernel.interfaces.loop import Step, TerminationReason, Turn
    from app.kernel.loop.termination import BudgetExhaustedCondition

    condition = BudgetExhaustedCondition()
    task = AgentTask(id="test", goal="test")

    # Add a turn with a restrictive budget
    turn = Turn(
        id="turn-1",
        task_id="test",
        settings_snapshot=TurnSettings(
            model="test",
            system_prompt="test",
            budget=Budget(max_steps=1),  # Only 1 step allowed
            tool_names=frozenset(),
        ),
    )
    step = Step(
        id="step-1",
        turn_id="turn-1",
        model_request={},
        model_response={},
    )
    turn.steps.append(step)
    task.turns.append(turn)

    # First step should not terminate
    reason = condition.should_terminate(task, step)
    assert reason == TerminationReason.BUDGET_EXHAUSTED


# ----------------------------------------------------------------------------
# Tests: Schema validation
# ----------------------------------------------------------------------------


def test_schema_validator():
    from app.kernel.tools.schema import SchemaValidator

    validator = SchemaValidator()
    schema = ToolSchema(
        name="test",
        description="test",
        parameters=(
            ToolParameter(name="required_str", type="string", description="test", required=True),
            ToolParameter(
                name="optional_int", type="integer", description="test", required=False
            ),
        ),
    )

    # Valid arguments
    errors = validator.validate(schema, {"required_str": "hello"})
    assert len(errors) == 0

    # Missing required parameter
    errors = validator.validate(schema, {})
    assert len(errors) > 0
    assert "required_str" in errors[0]

    # Wrong type
    errors = validator.validate(schema, {"required_str": 123})
    assert len(errors) > 0
    assert "type" in errors[0].lower()


# ----------------------------------------------------------------------------
# Tests: model history replay
#
# Regression coverage for the multi-step path. Earlier tests only exercised the
# stub provider that returns no tool calls, so the loop always terminated after
# one step and the rebuilt history was never sent back to a provider.
# ----------------------------------------------------------------------------


class RecordingProvider:
    """Model provider that replays queued responses and records each request."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.requests: list[dict[str, Any]] = []

    async def complete(self, request: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(request)
        return self._responses.pop(0) if self._responses else {
            "content": "done",
            "tool_calls": [],
            "usage": {"total_tokens": 0},
        }


def _tool_call_response() -> dict[str, Any]:
    """First-step response shaped like DeepSeek's thinking-model output."""
    raw_message = {
        "role": "assistant",
        "content": "",
        "reasoning_content": "The user wants the working directory.",
        "tool_calls": [
            {
                "index": 0,
                "id": "call-1",
                "type": "function",
                # The API returns (and requires back) a JSON *string* here.
                "function": {"name": "echo", "arguments": '{"message": "hi"}'},
            }
        ],
    }
    return {
        "content": "",
        "tool_calls": [
            {
                "id": "call-1",
                "type": "function",
                # Normalized for the kernel: arguments parsed into a dict.
                "function": {"name": "echo", "arguments": {"message": "hi"}},
            }
        ],
        "raw_message": raw_message,
        "usage": {"total_tokens": 10},
    }


@pytest.mark.asyncio
async def test_history_replays_raw_provider_message(executor, registry):
    """The raw assistant message must be replayed verbatim, not reconstructed."""
    provider = RecordingProvider([_tool_call_response()])
    orchestrator = Orchestrator(
        executor=executor,
        registry=registry,
        model_provider=provider,
        default_settings=TurnSettings(
            model="deepseek-v4-pro",
            system_prompt="You are a helpful agent.",
            budget=Budget(max_steps=5),
            tool_names=frozenset(),
        ),
    )

    await orchestrator.run(AgentTask(id=str(uuid.uuid4()), goal="print cwd"))

    assert len(provider.requests) >= 2, "expected a follow-up call with tool results"
    replayed = provider.requests[1]["messages"]
    assistant = next(m for m in replayed if m["role"] == "assistant")

    # Regression 1: arguments must stay a JSON string. Sending the parsed dict
    # made DeepSeek reject the request with "invalid type: map, expected a string".
    arguments = assistant["tool_calls"][0]["function"]["arguments"]
    assert isinstance(arguments, str), f"arguments must be a JSON string, got {type(arguments)}"
    assert arguments == '{"message": "hi"}'

    # Regression 2: thinking models require reasoning_content back in the history.
    assert assistant.get("reasoning_content") == "The user wants the working directory."

    # The tool result must still follow, linked by tool_call_id.
    tool_message = next(m for m in replayed if m["role"] == "tool")
    assert tool_message["tool_call_id"] == "call-1"


@pytest.mark.asyncio
async def test_history_falls_back_when_provider_omits_raw_message(executor, registry):
    """Providers that return no raw_message keep the reconstructed shape."""
    response = _tool_call_response()
    del response["raw_message"]
    provider = RecordingProvider([response])
    orchestrator = Orchestrator(
        executor=executor,
        registry=registry,
        model_provider=provider,
        default_settings=TurnSettings(
            model="test-model",
            system_prompt="You are a helpful agent.",
            budget=Budget(max_steps=5),
            tool_names=frozenset(),
        ),
    )

    await orchestrator.run(AgentTask(id=str(uuid.uuid4()), goal="print cwd"))

    assert len(provider.requests) >= 2
    assistant = next(m for m in provider.requests[1]["messages"] if m["role"] == "assistant")
    assert assistant["tool_calls"][0]["function"]["name"] == "echo"


@pytest.mark.asyncio
async def test_executor_rejects_invalid_arguments(executor):
    results = await executor.execute_many([("call-1", "echo", {})])

    assert results[0][1].success is False
    assert "Missing required parameter" in results[0][1].error


@pytest.mark.asyncio
async def test_environment_rejects_path_outside_workspace(environment):
    await environment.start()

    with pytest.raises(PermissionError, match="outside the configured workspace"):
        await environment.read_file("../outside.txt")

    await environment.stop()


@pytest.mark.asyncio
async def test_environment_kills_timed_out_process(environment):
    await environment.start()

    result = await environment.exec("sleep 10", timeout_ms=20)

    assert result.status.value == "timeout"
    assert result.exit_code == -1

    await environment.stop()


# ----------------------------------------------------------------------------
# Tests: context management
# ----------------------------------------------------------------------------


def test_context_manager_preserves_system_and_current_goal():
    from app.kernel.context import ContextBudget, ContextManager

    manager = ContextManager(ContextBudget(max_total_tokens=20, max_tool_output_tokens=4))
    messages = [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "goal"},
        {"role": "tool", "tool_call_id": "old", "content": "old output " * 20},
        {"role": "assistant", "content": "new answer"},
    ]

    result, compacted = manager.build(messages)

    assert result[0]["role"] == "system"
    assert result[1]["content"] == "goal"
    assert result[-1]["content"] == "new answer"
    assert compacted is True


def test_context_manager_truncates_tool_output_head_and_tail():
    from app.kernel.context import ContextBudget, ContextManager

    manager = ContextManager(ContextBudget(max_total_tokens=100, max_tool_output_tokens=10))
    content = "HEAD-" + ("x" * 100) + "-TAIL"
    result, compacted = manager.build([
        {"role": "system", "content": "system"},
        {"role": "user", "content": "goal"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "call-1", "type": "function"}],
        },
        {"role": "tool", "tool_call_id": "call-1", "content": content},
    ])

    tool_content = result[-1]["content"]
    assert compacted is True
    assert "HEAD-" in tool_content
    assert "-TAIL" in tool_content
    assert "context truncated" in tool_content


# ----------------------------------------------------------------------------
# Tests: durable task persistence
# ----------------------------------------------------------------------------


def test_sqlite_task_store_round_trip(tmp_path):
    from app.kernel.interfaces.loop import TaskStatus
    from app.kernel.persistence import SQLiteTaskStore

    store = SQLiteTaskStore(tmp_path / "agent-state.db")
    task = AgentTask(id="task-persisted", goal="persist this")
    task.status = TaskStatus.PAUSED
    store.save(task)

    restored = store.get("task-persisted")
    assert restored is not None
    assert restored.id == task.id
    assert restored.goal == task.goal
    assert restored.status == TaskStatus.PAUSED
    assert store.list_ids() == ["task-persisted"]

    store.delete(task.id)
    assert store.get(task.id) is None


@pytest.mark.asyncio
async def test_orchestrator_resume_loads_persisted_task(executor, registry, tmp_path):
    from app.kernel.persistence import SQLiteTaskStore

    store = SQLiteTaskStore(tmp_path / "agent-state.db")
    task = AgentTask(id="resume-task", goal="resume me")
    task.status = TaskStatus.PAUSED
    store.save(task)

    orchestrator = Orchestrator(
        executor=executor,
        registry=registry,
        task_store=store,
    )
    resumed = await orchestrator.resume("resume-task")

    assert resumed.id == "resume-task"
    assert resumed.status == TaskStatus.COMPLETED
    assert len(resumed.turns) >= 1


# ----------------------------------------------------------------------------
# Tests: constraint layer
# ----------------------------------------------------------------------------


def test_safe_command_policy_allows_configured_command():
    from app.kernel.security import AccessDecision, SafeCommandPolicy

    result = SafeCommandPolicy(allowed_commands={"pwd"}).check("pwd")

    assert result.decision == AccessDecision.ALLOW


def test_safe_command_policy_denies_unlisted_and_dangerous_commands():
    from app.kernel.security import SafeCommandPolicy

    policy = SafeCommandPolicy(allowed_commands={"pwd"})

    assert policy.check("whoami").allowed is False
    assert policy.check("pwd; cat .env").allowed is False
    assert policy.check("sudo pwd").allowed is False


@pytest.mark.asyncio
async def test_environment_policy_returns_denied_result(environment):
    from app.kernel.security import SafeCommandPolicy, WorkspaceFilePolicy

    restricted = LocalEnvironment(
        workspace=environment._workspace,
        command_policy=SafeCommandPolicy(allowed_commands={"pwd"}),
        file_policy=WorkspaceFilePolicy(can_read=True, can_write=False),
    )
    await restricted.start()

    command_result = await restricted.exec("whoami")
    assert command_result.status.value == "denied"
    assert "allow-list" in command_result.stderr

    from app.kernel.interfaces.environment import FilePatch

    with pytest.raises(PermissionError, match="File write denied"):
        await restricted.apply_patch(FilePatch("blocked.txt", None, "blocked"))

    await restricted.stop()


@pytest.mark.asyncio
async def test_high_risk_tool_requires_one_time_approval(tmp_path):
    from app.kernel.approval import ApprovalStatus, SQLiteApprovalStore
    from app.kernel.interfaces.tool import ToolRisk

    class HighRiskTool(ITool):
        @property
        def schema(self) -> ToolSchema:
            return ToolSchema(name="danger", description="danger", risk=ToolRisk.HIGH)

        async def execute(self, arguments: dict[str, Any]) -> ToolResult:
            return ToolResult(success=True, output="executed")

    registry = ToolRegistry()
    registry.register(HighRiskTool())
    approval_store = SQLiteApprovalStore(tmp_path / "agent-state.db")
    executor = ToolExecutor(registry, approval=approval_store)

    first = await executor.execute_many([("call-1", "danger", {})])
    assert first[0][1].success is False
    assert first[0][1].metadata["approval_required"] is True
    pending = approval_store.list(ApprovalStatus.PENDING)
    assert len(pending) == 1

    approval_store.decide(pending[0].id, approved=True)
    second = await executor.execute_many([("call-2", "danger", {})])
    third = await executor.execute_many([("call-3", "danger", {})])
    assert second[0][1].success is True
    assert third[0][1].success is False


@pytest.mark.asyncio
async def test_environment_filters_provider_credentials(environment, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "must-not-leak")
    await environment.start()

    result = await environment.exec("python -c 'print(__import__(\"os\").getenv(\"DEEPSEEK_API_KEY\", \"missing\"))'")

    assert result.exit_code == 0
    assert "missing" in result.stdout
    assert "must-not-leak" not in result.stdout
    await environment.stop()


@pytest.mark.asyncio
async def test_environment_limits_output(environment):
    from app.kernel.environment.local import LocalEnvironment

    limited = LocalEnvironment(workspace=environment._workspace, max_output_chars=20)
    await limited.start()
    result = await limited.exec("python -c 'print(\"x\" * 100)'")

    assert result.truncated is True
    assert len(result.stdout) < 100
    await limited.stop()


def test_audit_store_redacts_sensitive_details(tmp_path):
    from app.kernel.audit import SQLiteAuditStore

    store = SQLiteAuditStore(tmp_path / "audit.db")
    store.record(
        "test",
        details={"api_key": "secret-value", "nested": {"password": "hidden", "safe": "ok"}},
    )

    event = store.list()[0]
    assert event["details"]["api_key"] == "[REDACTED]"
    assert event["details"]["nested"]["password"] == "[REDACTED]"
    assert event["details"]["nested"]["safe"] == "ok"


@pytest.mark.asyncio
async def test_environment_shell_cd_and_env_persist(tmp_path):
    from app.kernel.interfaces.environment import FilePatch
    from app.kernel.security import SafeCommandPolicy, WorkspaceFilePolicy

    environment = LocalEnvironment(
        workspace=tmp_path,
        command_policy=SafeCommandPolicy(allowed_commands={"cd", "pwd", "export", "python"}),
        file_policy=WorkspaceFilePolicy(can_read=True, can_write=True),
    )
    await environment.apply_patch(FilePatch("subdir/.keep", None, ""))
    await environment.start()
    assert (await environment.exec("cd subdir")).exit_code == 0
    assert (await environment.exec("pwd")).stdout.strip() == str(tmp_path / "subdir")
    assert (await environment.exec("export AGENT_TEST_VALUE=ok")).exit_code == 0
    result = await environment.exec("python -c 'print(__import__(\"os\").getenv(\"AGENT_TEST_VALUE\"))'")
    assert result.stdout.strip() == "ok"
    await environment.stop()
