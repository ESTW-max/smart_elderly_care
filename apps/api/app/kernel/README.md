# Agent Kernel - Skeleton Layer

Core orchestration framework for autonomous agents, implementing the skeleton layer capabilities from `agent-core-capabilities.md`.

## Architecture

The kernel follows **SOLID principles** with clean separation between interfaces and implementations:

```
kernel/
├── interfaces/        # Abstract contracts (Dependency Inversion Principle)
│   ├── loop.py       # Orchestration loop abstractions
│   ├── tool.py       # Tool system abstractions
│   └── environment.py # Execution environment abstractions
├── loop/             # Orchestration loop implementation
│   ├── orchestrator.py
│   ├── step.py
│   ├── termination.py
│   └── turn.py
├── tools/            # Tool system implementation
│   ├── registry.py
│   ├── executor.py
│   ├── schema.py
│   └── builtin/      # Built-in tools
├── environment/      # Execution environment implementation
│   └── local.py
```

## Core Capabilities

### 1. Orchestration Loop

The main agent cycle: **sample → decide → act → observe**, hierarchically structured:

```
Task (complete goal)
  └─ Turn (user-visible interaction)
       └─ Step (model request + tool execution)
```

**Key features:**
- ✅ Four termination conditions (no tool calls, goal reached, budget exhausted, external signal)
- ✅ Mid-run interrupt support
- ✅ Mid-run steering (instruction injection)
- ✅ Immutable settings snapshot per turn
- ✅ Event streaming for real-time observation

### 2. Tool Invocation

Translates model intents to executable actions:

**Lifecycle:**
```
Define → Register → Discover → Validate → Execute → Observe
```

**Features:**
- ✅ JSON Schema-based tool definitions
- ✅ Dynamic tool exposure control
- ✅ Parallel execution of independent calls
- ✅ Structured error reporting for model self-correction
- ✅ Namespace isolation (prevents name collisions)

### 3. Execution Environment

Abstraction over command execution and filesystem operations:

**Interface:**
- `IExecutionEnvironment` - Unified contract for local/remote/sandbox
- Persistent shell sessions (not one-shot `bash -c`)
- Structured file patches (not full-file rewrites)
- Token-aware output truncation

**Current implementation:**
- `LocalEnvironment` - Runs on the local machine
- Future: `RemoteEnvironment`, `SandboxEnvironment`

## DeepSeek 配置

复制 `apps/api/.env.example` 为 `apps/api/.env`，然后填写：

```env
DEEPSEEK_API_KEY=your-real-api-key
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TEMPERATURE=0.2
DEEPSEEK_MAX_OUTPUT_TOKENS=4096
DEEPSEEK_TIMEOUT_SECONDS=60

AGENT_SYSTEM_PROMPT=You are a helpful coding agent.
AGENT_MAX_STEPS=100
AGENT_MAX_TOKENS=100000
AGENT_MAX_SECONDS=3600
```

真实 `.env` 已被 Git 忽略，不要把 API Key 写入源码或提交到仓库。通过
`create_deepseek_agent(get_settings(), workspace=...)` 创建的 Agent 会自动使用以上配置。


### Basic Example

```python
from app.kernel.environment.local import LocalEnvironment
from app.kernel.interfaces.loop import AgentTask, Budget, TurnSettings
from app.kernel.loop.orchestrator import Orchestrator
from app.kernel.tools.builtin import ReadFileTool, ShellExecTool
from app.kernel.tools.executor import ToolExecutor
from app.kernel.tools.registry import ToolRegistry

# 1. Set up environment
env = LocalEnvironment(workspace="/path/to/workspace")
await env.start()

# 2. Register tools
registry = ToolRegistry()
registry.register(ReadFileTool(env))
registry.register(ShellExecTool(env))

# 3. Create executor and orchestrator
executor = ToolExecutor(registry)
orchestrator = Orchestrator(
    executor=executor,
    registry=registry,
    default_settings=TurnSettings(
        model="gpt-4o",
        system_prompt="You are a helpful coding assistant.",
        budget=Budget(max_steps=50, max_tokens=100_000),
        tool_names=frozenset(),  # empty = all tools
    ),
)

# 4. Run a task
task = AgentTask(
    id="task-1",
    goal="List all Python files in the current directory.",
)
completed_task = await orchestrator.run(task)

print(f"Task status: {completed_task.status}")
print(f"Turns: {len(completed_task.turns)}")

await env.stop()
```

### Custom Tool

```python
from app.kernel.interfaces.tool import ITool, ToolParameter, ToolResult, ToolSchema

class MyCustomTool(ITool):
    @property
    def schema(self) -> ToolSchema:
        return ToolSchema(
            name="my_tool",
            description="Does something custom.",
            parameters=(
                ToolParameter(
                    name="input",
                    type="string",
                    description="Input parameter.",
                ),
            ),
        )
    
    async def execute(self, arguments: dict) -> ToolResult:
        try:
            result = do_something(arguments["input"])
            return ToolResult(success=True, output=result)
        except Exception as exc:
            return ToolResult(
                success=False,
                output=None,
                error=str(exc),
            )

# Register it
registry.register(MyCustomTool())
```

### Event Streaming

```python
# Subscribe to task events
async for event in orchestrator.event_stream(task.id):
    if event["type"] == "step_started":
        print(f"Starting step in turn {event['turn_id']}")
    elif event["type"] == "step_completed":
        print(f"Completed step {event['step_id']}, tool calls: {event['tool_calls']}")
    elif event["type"] == "terminated":
        print(f"Task terminated: {event['reason']}")
        break
```

### Interrupt and Steering

```python
# Interrupt a running task
await orchestrator.interrupt(task.id)

# Inject new instructions mid-run
from app.kernel.interfaces.loop import SteeringMessage
await orchestrator.steer(
    task.id,
    SteeringMessage(content="Actually, focus on .ts files instead."),
)
```

## 安全策略

Agent 的本地执行环境默认采用 fail-closed 策略：Shell 只允许执行
`AGENT_ALLOWED_COMMANDS` 中的命令，工作区之外的路径始终拒绝，文件写入由
`AGENT_FILE_WRITE_ENABLED` 独立控制且默认关闭。测试接口应仅在本地通过
`AGENT_TEST_ENDPOINT_ENABLED=true` 显式启用，不应直接暴露给不可信用户。

## Testing

Run the test suite:

```bash
cd apps/api
pytest tests/test_kernel.py -v
```

The tests cover:
- ✅ Tool registration and discovery
- ✅ Tool execution (success, failure, not found)
- ✅ Environment operations (exec, read, write, patch, list)
- ✅ Orchestrator lifecycle (run, interrupt)
- ✅ Termination conditions
- ✅ Schema validation

## Design Principles

### SOLID Compliance

1. **Single Responsibility (SRP)**
   - `Orchestrator`: loop orchestration only
   - `ToolRegistry`: tool discovery only
   - `ToolExecutor`: tool execution only
   - `LocalEnvironment`: local I/O only

2. **Open/Closed (OCP)**
   - New tools: implement `ITool`, call `registry.register()`
   - New termination conditions: implement `ITerminationCondition`
   - No need to modify existing classes

3. **Liskov Substitution (LSP)**
   - All `ITool` implementations are interchangeable
   - All `IExecutionEnvironment` implementations are interchangeable

4. **Interface Segregation (ISP)**
   - `ITool` (execution) separate from `IToolValidator` (validation)
   - `IToolRegistry` (discovery) separate from `IToolExecutor` (dispatch)

5. **Dependency Inversion (DIP)**
   - `Orchestrator` depends on `IToolExecutor`, not concrete `ToolExecutor`
   - Tools depend on `IExecutionEnvironment`, not concrete `LocalEnvironment`
   - Inject dependencies at construction time

### Testability

Every component is testable in isolation:
- Mock `IExecutionEnvironment` for tool tests
- Mock `IToolExecutor` for orchestrator tests
- Mock tools for executor tests

## Limitations (Current Implementation)

The skeleton layer provides a **minimal viable foundation**. Known limitations:

1. **Orchestrator**
   - Model integration is stubbed (returns empty tool_calls)
   - Context compression not implemented
   - Resume from pause not yet supported

2. **LocalEnvironment**
   - Uses subprocess instead of persistent pty session
   - Token truncation is char-based, not tiktoken-aware
   - No sandbox policy enforcement

3. **Missing Features (Future Layers)**
   - Context management (compression, budgets)
   - State persistence (database-backed task storage)
   - Multi-agent (task delegation)
   - Sandbox isolation (platform-specific constraints)
   - Authorization (approval workflows)
   - Model interface (multi-provider abstraction)

These will be addressed in subsequent iterations as we build out the capability, constraint, and support layers.

## Next Steps

After completing the skeleton layer, evolve in this order:

1. **Capability Layer**
   - Context manager with compression
   - Persistent task storage
   - Multi-agent coordination

2. **Constraint Layer**
   - Sandbox policies
   - Authorization workflows
   - Network and credential management

3. **Support Layer**
   - Model provider abstraction
   - Extension/plugin system
   - Observability (tracing, metrics)

## References

- [agent-core-capabilities.md](../../../../agent-core-capabilities.md) - Source material
- [openai/codex](https://github.com/openai/codex) - Reference implementation
- Clean Architecture by Robert C. Martin
- Design Patterns (Gang of Four)
