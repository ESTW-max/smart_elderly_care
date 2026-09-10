# Agent 能力蒸馏进度

更新时间：2026-09-10

## 总览

当前项目已完成 DeepSeek 驱动的单 Agent 基础闭环，并完成部分能力层与约束层能力。当前不是所有 Agent 平台能力都已完成。

## 已完成

### 骨架层（agent-skeleton-migration）

- `AgentTask -> Turn -> Step` 编排循环。
- DeepSeek Provider 和 OpenAI 兼容 HTTP 调用。
- 工具注册、Schema 校验、并行执行和结构化错误。
- 文件、Shell、目录等内置工具。
- 工作区路径边界和文件读写权限。
- Shell 命令白名单、危险命令拦截、超时进程组清理。
- 持久 Bash 会话，支持跨调用保持工作目录和环境变量。
- `.env` / `Settings` 配置加载，禁止把环境配置硬编码到业务代码。
- Agent 测试接口：`POST /api/v1/agent/test`。

### 能力层（agent-capability-layer）

- 上下文总量、单消息和工具输出预算。
- 超限历史裁剪、工具输出头尾截断和 `context_compacted` 事件。
- SQLite JSON 任务快照：保存 `Task/Turn/Step/ToolCall/Observation`。
- 任务查询：`GET /api/v1/agent/tasks/{task_id}`。
- 任务断点恢复：`POST /api/v1/agent/tasks/{task_id}/resume`。

### 约束层（agent-constraints-layer）

- 工具风险等级：低、中、高。
- 高风险工具精确参数审批，审批记录单次消费。
- 审批查询和决策 API。
- Shell 子进程过滤 DeepSeek/OpenAI/Anthropic 等凭据环境变量。
- Shell 输出、CPU、文件大小限制。
- SQLite 安全审计事件和敏感字段脱敏。
- 持久 Shell 进程组管理。
- `/agent/*` 全量 API Key 鉴权（`X-Agent-Token`），常量时间比对，未配置 token 时失败关闭。
- 具名 token（`name:token`）落 `agent_approvals.decided_by` 与审计事件 actor。
- 审批记录按 `task_id` 作用域隔离：A 任务的审批不能被 B 任务复用。

## 验证

- 后端测试：`59 passed`（2026-09-10 实测）。
- Ruff：`All checks passed!`。此前 15 项已全部清理：
  - `UP042` ×7：已改 `StrEnum`。改前确认全仓一律用 `.value` 取值（`persistence.py`、`routes/agent.py`），且当时库内仅 2 行测试残留数据，是迁移成本最低的时点。
  - `E501` ×5：已换行。
  - `B905` ×1：`tools/executor.py` 的 `zip()` 已加 `strict=True`；`asyncio.gather` 保证等长，注释已说明。
- 测试仍有既有的 `datetime.utcnow()` 和 Starlette/httpx 弃用警告，不影响通过结果。
- 真实 DeepSeek Agent 已成功执行 `pwd` 工具调用并返回最终回答。
- 持久 Shell、审批、审计、凭据过滤相关测试均通过，此前记录的持久 Shell 回归已消除。
- 孤立 `tool` 消息（无配对 `assistant.tool_calls`）行为确定为**保留并计入预算**，docstring 已订正并补充说明：OpenAI 兼容 Provider 会拒收此类消息，直接回放的调用方需自行清洗。经查 `Step` 的 `model_response` 与 `observations` 是同一对象的字段、在 `step_runner.run()` 内一次性组装后才落库，本代码库不会产出孤立消息，无需额外改动。
- 服务端生成的 OpenAPI 与 `packages/api-contract/openapi.yaml` 已逐字段对拍一致。
- 审批 `task_id` 绑定已有回归测试。该用例做过变异验证：把 `approve()` 的 `task_id IS ?` 条件去掉后用例确实失败，不是空测。

## 未完成

### 能力层

- 多 Agent 委派、父子任务关系和结果合并。
- 正式 SQLAlchemy Agent 数据模型和迁移。
- 任务分叉、事件流持久化和并发恢复冲突控制。
- 基于模型 Tokenizer 的准确预算。
- 自动摘要、长期记忆和多模态上下文管理。

### 约束层

- 操作系统原生沙箱（macOS/Linux/容器）。
- 网络域名白名单、逐请求网络治理和网络审计。
- 凭据代理、短期凭据和系统钥匙串。
- 面向真实用户的认证与租户隔离（当前 API Key 只区分运维 actor，没有用户模型、登录流程和数据隔离）。
- `/agent/*` 速率限制。

### 支撑层

- OpenAI/Anthropic/Ollama 等 Provider 工厂和降级链。
- SSE Token/工具调用流式输出。
- MCP Client/Server、插件和技能系统。
- OpenTelemetry、Prometheus、成本和延迟指标。

## 当前配置

- Agent 测试接口由 `AGENT_TEST_ENDPOINT_ENABLED` 控制，默认关闭。
- `/agent/*` 鉴权由 `AGENT_API_TOKEN` 控制，格式 `name:token[,name:token]`。**接口启用但未配该值时全部返回 503**，避免"为调试打开一次"造成裸奔。
- 工作目录由 `AGENT_WORKSPACE` 控制。
- 文件写入由 `AGENT_FILE_WRITE_ENABLED` 控制，默认关闭。
- Shell 命令由 `AGENT_ALLOWED_COMMANDS` 控制。
- 状态、审批和审计默认共享 `AGENT_STATE_DATABASE_PATH`。
- DeepSeek API Key 只从 `.env` / 环境变量读取，不得提交或打印。

## 下一步顺序

1. 增加 `/agent/*` 速率限制。
2. 增加网络域名白名单与网络访问策略。
3. 迁移正式 SQLAlchemy Agent 状态模型。
4. 实现 SSE 流式事件。
5. 实现上下文自动摘要、多 Agent、MCP 和可观测性。
6. 在明确运行平台后接入原生沙箱；应用层过滤不能替代 OS 隔离。
7. 若要面向真实用户开放，再引入用户模型与登录流程；当前 `JWT_SECRET` 仍是未使用的死配置。
