# Trellis 工作流

Trellis 是本项目的工程管理层，不负责编译 UniApp，也不负责运行 FastAPI。它把需求、规范、任务和会话记忆放进仓库，让不同 AI 编码工具在同一套约定下工作。

## 初始化

当前目录已预留 `.trellis/` 结构。首次在本机使用官方 CLI 时执行：

```bash
npm install -g @mindfoldhq/trellis@latest
trellis init --codex -u your-name
```

如果 CLI 发现已有 `.trellis` 文件，请先备份本模板中的规范，再选择合并；不要覆盖业务代码。

## 本项目的职责边界

| 工具 | 负责什么 |
| --- | --- |
| pnpm workspace | JavaScript/TypeScript 包、脚本和前端依赖 |
| uv | Python 虚拟环境、锁文件和后端依赖 |
| Docker Compose | 本地 PostgreSQL/API 基础设施 |
| Trellis | PRD、技术规范、任务生命周期、开发记忆 |

## 规范位置

- `.trellis/spec/miniapp/frontend/index.md`：UniApp 页面、平台差异和请求层。
- `.trellis/spec/api/backend/index.md`：FastAPI 分层、校验、数据库和测试。
- `.trellis/spec/api-contract/shared/index.md`：OpenAPI 与共享类型。
- `.trellis/spec/guides/index.md`：跨包开发检查清单。

## 任务流程

```text
需求澄清 → PRD → 技术设计 → 实现 → API/类型同步 → 测试 → 更新规范 → 归档
```

官方 CLI 的典型命令：

```bash
python3 ./.trellis/scripts/task.py create "功能名称" --slug feature-name
python3 ./.trellis/scripts/task.py start <task-name>
python3 ./.trellis/scripts/task.py validate <task-name>
python3 ./.trellis/scripts/task.py finish
```

本次框架初始化的需求记录在 `.trellis/tasks/08-28-bootstrap-framework/`，后续业务功能请新建独立任务，不要把多个功能混在一个 PRD 中。
