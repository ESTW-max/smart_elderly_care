# 技术设计

- `apps/miniapp`：平台无关的 UniApp 页面和请求封装。
- `apps/api`：FastAPI 应用工厂、异步 SQLAlchemy Session、分层服务和测试。
- `packages/api-contract`：OpenAPI YAML 与导出的 TypeScript schema 类型。
- 开发期默认 SQLite，Docker Compose 提供 PostgreSQL 运行路径。
- Trellis 配置在根目录，按 frontend、api、api-contract 划分 package。
