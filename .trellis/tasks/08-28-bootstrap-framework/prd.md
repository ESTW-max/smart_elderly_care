# PRD：全栈小程序起始框架

## 目标

为后续业务开发提供一个前后端同仓库、Python 后端、可编译到微信小程序/H5/Android/iOS 的最小可运行起点。

## 约束

- 客户端使用 UniApp + Vue 3 + TypeScript。
- 服务端使用 Python FastAPI。
- 使用 pnpm workspace 管理 JS/TS 包，使用 uv 管理 Python 依赖。
- 使用 Trellis 保存规范、任务和开发记录。
- 项目整体放在 `agent/miniapp-python-fullstack` 独立目录中，不在 `agent` 顶层散放项目文件。

## 验收

- API 可通过健康检查和示例任务 CRUD 验证。
- 前端页面可以读取、创建、完成和删除任务。
- OpenAPI 契约、共享类型和中文文档齐全。
