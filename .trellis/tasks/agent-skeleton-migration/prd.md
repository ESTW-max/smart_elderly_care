# Agent Skeleton Layer Migration - PRD

## 项目背景

基于对 [openai/codex](https://github.com/openai/codex) 源码的实读分析，我们提炼出了一份通用的 Agent 核心能力模型 (`agent-core-capabilities.md`)。该模型将 Agent 能力分为四层:

1. **骨架层** - 定义 Agent 基本形态
2. **能力层** - 决定任务复杂度上限
3. **约束层** - 决定可否放手自动执行
4. **支撑层** - 决定长期演进空间

本项目聚焦**骨架层**，将其核心能力蒸馏迁移到当前项目的 `backend/kernel` 模块。

## 项目目标

### 主要目标
将 Agent 骨架层的三大核心能力实现到 `apps/api/app/kernel/`:
1. **编排循环** (Orchestration Loop) - 采样→决策→行动→观测的闭环
2. **工具调用** (Tool Invocation) - 模型意图到可执行动作的转换
3. **执行环境** (Execution Environment) - 命令执行、文件操作的抽象层

### 非目标
- ❌ 能力层 (上下文管理、状态持久化、多 Agent)
- ❌ 约束层 (沙箱隔离、授权审批、网络管控)
- ❌ 支撑层 (模型接入、扩展机制、可观测性)
- ❌ 生产级性能优化

## 成功标准

### 功能性
- ✅ 循环可以运行并正确终止 (四类终止条件全覆盖)
- ✅ 工具可以注册、发现、并行执行
- ✅ 环境可以执行命令和文件操作
- ✅ 支持运行中打断和转向
- ✅ 所有测试通过 (覆盖率 > 80%)

### 架构质量
- ✅ 严格遵循 SOLID 原则
- ✅ 接口与实现完全分离
- ✅ 依赖方向单向 (向内)
- ✅ 可测试性 (所有核心组件可 mock)

### 代码质量
- ✅ 类型注解覆盖率 100%
- ✅ 文档字符串覆盖率 100%
- ✅ 通过 ruff lint 检查

## 核心用户场景

### 场景 1: 基础任务执行
**角色**: 开发者  
**目标**: 运行一个简单的 Agent 任务  
**流程**:
1. 创建 `LocalEnvironment` 和 `ToolRegistry`
2. 注册内置工具 (read_file, shell_exec 等)
3. 创建 `Orchestrator` 并注入依赖
4. 定义 `AgentTask` 并运行
5. 任务自动执行到终止条件

**验收**: 任务成功完成，状态为 `COMPLETED`

### 场景 2: 自定义工具开发
**角色**: 扩展开发者  
**目标**: 添加一个自定义工具供 Agent 使用  
**流程**:
1. 实现 `ITool` 接口
2. 定义 `ToolSchema` (参数、描述)
3. 实现 `execute()` 方法，返回 `ToolResult`
4. 调用 `registry.register(my_tool)`
5. Agent 可以发现并调用该工具

**验收**: 自定义工具可被发现、验证、执行

### 场景 3: 运行中控制
**角色**: 前端应用  
**目标**: 监控任务进度并在需要时干预  
**流程**:
1. 启动长任务并订阅事件流
2. 实时接收 step_started, step_completed 等事件
3. 用户点击"暂停"，调用 `orchestrator.interrupt()`
4. 或用户发送新指令，调用 `orchestrator.steer()`
5. 任务响应并调整行为

**验收**: 中断生效，工作不丢失；转向消息被应用

## 技术规格

### 接口层 (interfaces/)

#### `IOrchestrator`
```python
async def run(task: AgentTask) -> AgentTask
async def interrupt(task_id: str) -> None
async def steer(task_id: str, message: SteeringMessage) -> None
def event_stream(task_id: str) -> AsyncIterator[dict]
```

#### `ITool`
```python
@property
def schema(self) -> ToolSchema

async def execute(arguments: dict) -> ToolResult
```

#### `IExecutionEnvironment`
```python
async def start() -> None
async def stop() -> None
async def exec(command: str, ...) -> ExecResult
async def read_file(path: str, ...) -> FileReadResult
async def apply_patch(patch: FilePatch) -> None
async def list_dir(path: str) -> list[str]
```

### 数据模型

```python
AgentTask
  ├─ id: str
  ├─ goal: str
  ├─ turns: list[Turn]
  └─ status: TaskStatus

Turn
  ├─ id: str
  ├─ settings_snapshot: TurnSettings  # frozen
  ├─ steps: list[Step]
  └─ user_input: str | None

Step
  ├─ id: str
  ├─ model_request: dict
  ├─ model_response: dict
  ├─ tool_calls: list[ToolCall]
  └─ observations: list[Observation]
```

### 终止条件

1. **NoToolCallsCondition** - 模型响应无工具调用
2. **GoalReachedCondition** - 显式完成标记
3. **BudgetExhaustedCondition** - 步数/Token/时间超限
4. **ExternalSignalCondition** - 外部中断信号

### 内置工具

1. **ReadFileTool** - 读取文件，支持 token 截断
2. **WriteFileTool** - 创建/覆写文件
3. **PatchFileTool** - 结构化修改 (old_text → new_text)
4. **ListDirTool** - 列出目录内容
5. **ShellExecTool** - 执行 shell 命令

## 实现计划

### Phase 1: 接口层 (Day 1)
- [x] 定义 `loop.py` - 循环相关接口
- [x] 定义 `tool.py` - 工具相关接口
- [x] 定义 `environment.py` - 环境相关接口

### Phase 2: 编排循环 (Day 2)
- [x] 实现 `Orchestrator` 主循环
- [x] 实现 `StepRunner` 步骤执行
- [x] 实现四类终止条件
- [x] 实现中断与转向

### Phase 3: 工具系统 (Day 2-3)
- [x] 实现 `ToolRegistry`
- [x] 实现 `ToolExecutor` (并行执行)
- [x] 实现 `SchemaValidator`
- [x] 实现 5 个内置工具

### Phase 4: 执行环境 (Day 3)
- [x] 实现 `LocalEnvironment`
- [x] 命令执行 (subprocess, 待升级 pty)
- [x] 文件操作 (read, patch, list)

### Phase 5: 测试与文档 (Day 3-4)
- [x] 编写单元测试 (覆盖率 > 80%)
- [x] 编写集成测试
- [x] 编写 README 和使用示例
- [x] 编写架构设计文档

## 风险与对策

### 风险 1: 过度设计
**描述**: 过早优化或抽象过度导致复杂度飙升  
**对策**: 从最小可用集开始，每个抽象都有明确用例验证

### 风险 2: 抽象泄漏
**描述**: 接口抽象不当，实现细节泄漏到上层  
**对策**: 充分的集成测试，验证接口在多实现下的正确性

### 风险 3: 性能开销
**描述**: 分层和抽象带来的性能损失  
**对策**: 关键路径性能测试，避免过度封装 (例如: 工具执行不走多层代理)

## 后续演进路线

完成骨架层后，按以下顺序演进:

### 能力层 (Iteration 2)
- 上下文管理 (压缩、摘要、token 预算)
- 状态持久化 (数据库存储、会话恢复)
- 任务委派 (多 Agent 协作)

### 约束层 (Iteration 3)
- 沙箱隔离 (平台原生实现)
- 授权审批 (规则引擎 + 模型审查)
- 网络与凭据管控

### 支撑层 (Iteration 4)
- 模型接入 (多 provider 抽象)
- 扩展机制 (MCP 双向)
- 可观测性 (分布式追踪、指标)

## 参考资料

- [agent-core-capabilities.md](../../agent-core-capabilities.md) - 能力参考框架
- [openai/codex](https://github.com/openai/codex) - 源码参考 (commit `0a12b855a0`)
- Clean Architecture - Robert C. Martin
- Design Patterns - Gang of Four
