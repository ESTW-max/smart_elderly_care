# Agent Skeleton Layer Migration - 技术设计文档

## 概述

将 Codex agent 的骨架层核心能力蒸馏迁移到当前项目的 `backend/kernel` 模块中，遵循 SOLID 面向对象设计原则。

## 目标

实现 Agent 核心骨架层的三大能力：
1. **编排循环 (Orchestration Loop)** - 采样→决策→行动→观测的闭环
2. **工具调用 (Tool Invocation)** - 模型意图到可执行动作的转换
3. **执行环境 (Execution Environment)** - 命令执行、文件操作的抽象层

## 架构设计

### 分层结构

```
apps/api/app/kernel/
├── interfaces/          # 抽象接口层 (依赖倒置原则)
│   ├── __init__.py
│   ├── loop.py         # 循环相关接口
│   ├── tool.py         # 工具相关接口
│   └── environment.py  # 环境相关接口
├── loop/               # 编排循环实现
│   ├── __init__.py
│   ├── orchestrator.py # 主循环编排器
│   ├── turn.py         # 回合管理
│   ├── step.py         # 步骤执行
│   └── termination.py  # 终止条件
├── tools/              # 工具调用系统
│   ├── __init__.py
│   ├── registry.py     # 工具注册表
│   ├── executor.py     # 工具执行器
│   ├── schema.py       # 工具定义与验证
│   └── builtin/        # 内置工具
│       ├── __init__.py
│       ├── file_ops.py
│       └── shell_ops.py
├── environment/        # 执行环境
│   ├── __init__.py
│   ├── shell.py        # Shell 会话管理
│   ├── filesystem.py   # 文件系统操作
│   └── context.py      # 执行上下文
└── __init__.py
```

### SOLID 原则应用

#### 1. 单一职责原则 (SRP)
- `Orchestrator`: 只负责循环编排逻辑
- `ToolRegistry`: 只负责工具注册与查找
- `ToolExecutor`: 只负责工具执行
- `ShellSession`: 只负责 shell 会话管理

#### 2. 开闭原则 (OCP)
- 通过接口定义扩展点
- 新工具通过注册机制添加，无需修改核心代码
- 终止条件可插拔

#### 3. 里氏替换原则 (LSP)
- 所有工具实现 `ITool` 接口
- 所有环境实现 `IExecutionEnvironment` 接口
- 子类可安全替换父类

#### 4. 接口隔离原则 (ISP)
- `ITool`: 工具执行接口
- `IToolValidator`: 工具验证接口
- `ITerminationCondition`: 终止条件接口
- 避免臃肿的大接口

#### 5. 依赖倒置原则 (DIP)
- 高层模块 (Orchestrator) 依赖抽象 (ITool, IEnvironment)
- 低层模块 (具体工具) 实现抽象
- 通过依赖注入组装

## 核心组件设计

### 1. 编排循环 (Orchestration Loop)

#### 循环分层
```python
Task (任务)
  └─ Turn (回合) - 用户感知的一次交互
       └─ Step (步) - 一次模型请求 + 工具执行
            └─ Stream (流) - 逐事件消费模型输出
```

#### 终止条件 (四类)
1. **无工具调用**: 模型输出不包含工具调用
2. **目标达成**: 显式完成信号
3. **预算耗尽**: Token/时间/步数限制
4. **外部信号**: 用户中断/超时

#### 关键特性
- ✅ 支持运行中打断
- ✅ 支持运行中转向 (steering)
- ✅ 回合内设置不可变快照
- ✅ 支持断点恢复

### 2. 工具调用系统

#### 工具生命周期
```
定义 → 注册 → 发现 → 验证 → 执行 → 结果处理
```

#### 核心功能
- **Schema 定义**: JSON Schema 描述工具签名
- **动态暴露**: 根据上下文控制工具可见性
- **并行执行**: 无依赖工具并发执行
- **结构化报错**: 错误信息可被模型理解和自愈
- **命名空间**: 避免工具名冲突

### 3. 执行环境

#### 环境抽象层次
```
IExecutionEnvironment (接口)
  ├─ LocalEnvironment (本地执行)
  ├─ RemoteEnvironment (远程执行)
  └─ SandboxEnvironment (沙箱执行)
```

#### 核心能力
- **持久 Shell 会话**: 非一次性 `bash -c`
- **真 TTY 支持**: 支持 REPL、调试器
- **结构化文件修改**: 补丁而非全文覆写
- **环境继承**: 复用用户 shell 环境

## 数据模型

### 核心实体

```python
@dataclass
class Task:
    """完整任务"""
    id: str
    goal: str
    context: dict
    turns: list[Turn]
    status: TaskStatus
    created_at: datetime

@dataclass
class Turn:
    """一次交互回合"""
    id: str
    task_id: str
    user_input: str | None
    steps: list[Step]
    settings_snapshot: dict  # 不可变配置快照
    started_at: datetime

@dataclass
class Step:
    """一次执行步骤"""
    id: str
    turn_id: str
    model_request: dict
    model_response: dict
    tool_calls: list[ToolCall]
    observations: list[Observation]
    
@dataclass
class ToolCall:
    """工具调用"""
    tool_name: str
    arguments: dict
    call_id: str
    
@dataclass
class Observation:
    """工具执行结果"""
    call_id: str
    success: bool
    result: Any
    error: str | None
```

## 实现计划

### Phase 1: 接口层 (interfaces/)
- [x] 定义核心抽象接口
- [x] 建立类型系统
- [x] 文档化接口契约

### Phase 2: 编排循环 (loop/)
- [ ] 实现 Orchestrator 主循环
- [ ] 实现 Turn 管理
- [ ] 实现 Step 执行
- [ ] 实现四类终止条件
- [ ] 实现中断与转向

### Phase 3: 工具系统 (tools/)
- [ ] 实现 ToolRegistry
- [ ] 实现 ToolExecutor
- [ ] 实现 Schema 验证
- [ ] 实现内置工具 (file_ops, shell_ops)
- [ ] 实现并行执行

### Phase 4: 执行环境 (environment/)
- [ ] 实现 ShellSession (持久会话)
- [ ] 实现 FileSystem (结构化修改)
- [ ] 实现 ExecutionContext
- [ ] 环境继承与隔离

### Phase 5: 集成测试
- [ ] 端到端循环测试
- [ ] 工具调用测试
- [ ] 环境执行测试
- [ ] 边界条件测试

## 技术选型

### 依赖库
```toml
[dependencies]
pydantic = ">=2.0"        # 数据验证
jsonschema = ">=4.0"      # 工具 Schema 验证
asyncio = "*"             # 异步执行
structlog = ">=24.0"      # 结构化日志
```

### 测试框架
- pytest
- pytest-asyncio
- pytest-mock

## 质量标准

### 代码质量
- ✅ 类型注解覆盖率 100%
- ✅ 文档字符串覆盖率 100%
- ✅ 单元测试覆盖率 > 80%
- ✅ 集成测试覆盖核心路径

### 架构质量
- ✅ 严格遵循 SOLID 原则
- ✅ 依赖方向单向 (向内)
- ✅ 接口与实现分离
- ✅ 可测试性 (通过 mock 接口)

### 性能目标
- 单步执行延迟 < 100ms (不含模型调用)
- 工具并行执行提升 > 2x
- 内存占用 < 100MB (10k turns)

## 风险与对策

### 风险1: 过度设计
**对策**: 从最小可用集开始，迭代演进

### 风险2: 抽象泄漏
**对策**: 充分的集成测试验证抽象正确性

### 风险3: 性能开销
**对策**: 关键路径性能测试，避免过度封装

## 参考资料

- [agent-core-capabilities.md](../../agent-core-capabilities.md) - 能力参考框架
- [openai/codex](https://github.com/openai/codex) - 源码参考
- Clean Architecture - Robert C. Martin
- Design Patterns - Gang of Four

## 后续演进

完成骨架层后，按以下顺序演进：
1. **能力层**: 上下文管理、状态持久化、任务委派
2. **约束层**: 沙箱隔离、授权审批、网络管控
3. **支撑层**: 模型接入、扩展机制、可观测性
