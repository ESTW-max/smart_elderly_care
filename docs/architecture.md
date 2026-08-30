# 架构与目录

## 总体关系

```text
┌──────────────────────────────────────────┐
│ apps/miniapp                              │
│ UniApp + Vue 3 + TypeScript + Pinia       │
│  ├─ 微信小程序                            │
│  ├─ H5 网站                               │
│  └─ Android / iOS App                     │
└──────────────────┬───────────────────────┘
                   │ HTTPS / JSON
┌──────────────────▼───────────────────────┐
│ apps/api                                  │
│ FastAPI + SQLAlchemy + Pydantic            │
└──────────────────┬───────────────────────┘
                   │
        SQLite（开发）/ PostgreSQL（生产）
```

## 为什么采用同仓库

- 前端、后端和接口契约可以在同一个提交中演进。
- `packages/api-contract` 集中保存 OpenAPI 与 TypeScript 类型，减少字段漂移。
- Trellis 的规范和任务与代码一起版本化，新的 AI 会话可以复用项目上下文。
- `pnpm workspace` 只管理 JavaScript/TypeScript 包，`uv` 只管理 Python 环境，职责清晰。

## 后端分层约定

```text
apps/api/app/
├── api/routes       # HTTP 参数、状态码和依赖注入
├── services         # 业务用例和事务边界
├── models           # SQLAlchemy 持久化模型
├── schemas          # Pydantic 输入/输出模型
├── db               # 引擎、Session 和建表/迁移入口
└── core             # 环境配置和基础设施
```

路由保持薄：不要在路由函数里堆积数据库查询和业务规则。生产项目应以 Alembic 替代开发期的 `metadata.create_all`。

## 前端分层约定

```text
apps/miniapp/src/
├── pages             # 页面入口
├── components        # 跨页面组件
├── stores            # Pinia 状态
├── utils/request.ts  # 统一请求和错误处理
├── config            # 环境配置
└── types             # 仅保留平台适配类型；业务类型来自共享契约
```

优先调用 `uni.*` API。必须调用平台专属 API 时，使用 UniApp 条件编译：

```ts
// #ifdef MP-WEIXIN
// 微信小程序代码
// #endif

// #ifdef APP-PLUS
// 原生 App 代码
// #endif
```

## 环境变量

根目录 `.env.example` 是总览；后端使用 `apps/api/.env`，前端使用 `apps/miniapp/.env`。密钥、微信 AppSecret、证书和生产数据库地址禁止提交到 Git。
