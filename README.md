# UniApp + FastAPI 全栈小程序框架

这是一个面向微信小程序、H5、Android 和 iOS 的全栈起始项目：

- 前端：UniApp + Vue 3 + TypeScript + Pinia
- 后端：Python 3.12 + FastAPI + SQLAlchemy 2.0
- 数据库：开发环境 SQLite；生产环境建议 PostgreSQL
- 包管理：前端使用 pnpm workspace，Python 使用 uv
- API 契约：OpenAPI YAML + 共享 TypeScript 类型
- 工程管理：Trellis（需求、规范、任务和开发记忆）

## 目录

```text
.
├── apps/
│   ├── miniapp/                 # UniApp 客户端
│   └── api/                     # FastAPI Python 服务
├── packages/
│   └── api-contract/            # OpenAPI 契约和共享 TS 类型
├── .trellis/                    # Trellis 规范、任务和工作记录
├── docs/                        # 中文开发与部署文档
├── docker-compose.yml           # PostgreSQL + API 本地环境
├── pnpm-workspace.yaml
└── package.json
```

## 快速开始

### 1. 安装工具

- Node.js 20 LTS 或更高版本
- pnpm 10（`corepack enable` 后执行 `corepack prepare pnpm@10 --activate`）
- Python 3.11 或更高版本
- uv
- 微信开发者工具（调试小程序时需要）

### 2. 安装依赖

```bash
pnpm install
cd apps/api
uv sync
cd ../..
```

### 3. 启动 FastAPI

```bash
pnpm dev:api
```

启动后访问：

- 健康检查：<http://127.0.0.1:8000/api/v1/health>
- Swagger：<http://127.0.0.1:8000/docs>
- OpenAPI：<http://127.0.0.1:8000/openapi.json>

开发环境默认使用 `apps/api/data/app.db`，首次启动会自动创建示例 `items` 表。

### 4. 启动前端

另开终端执行：

```bash
# H5 网站
pnpm dev:miniapp

# 微信小程序
pnpm dev:weixin
```

微信开发者工具导入 UniApp 编译输出目录（不是仓库根目录）：

```text
apps/miniapp/dist/dev/mp-weixin
```

首次使用时，将 `apps/miniapp/src/manifest.json` 中的 `wx-your-app-id` 换成自己的 AppID；没有 AppID 可先使用测试号。

## 构建目标

```bash
pnpm build:h5       # apps/miniapp/dist/build/h5
pnpm build:weixin   # apps/miniapp/dist/build/mp-weixin
pnpm build:app      # App Web 资源，随后用 HBuilderX 生成 APK/AAB/IPA
```

H5 产物可以部署到 Nginx、对象存储或 CDN。Android/iOS 证书、包名和原生插件配置请参考 [多平台发布](docs/platforms.md)。

## 质量检查

```bash
pnpm run check
pnpm run test:api
pnpm run lint:api
```

## 文档索引

- [架构与目录](docs/architecture.md)
- [本地开发](docs/development.md)
- [API 与类型契约](docs/api.md)
- [H5、小程序、Android、iOS 发布](docs/platforms.md)
- [部署与安全](docs/deployment.md)
- [Trellis 工作流](docs/trellis.md)

## 从示例到真实业务

示例 `items` 接口只用于验证前后端联通。开发真实功能时，建议按业务模块拆分：

1. 在 `apps/api/app/models` 定义数据库模型。
2. 在 `apps/api/app/schemas` 定义 Pydantic 请求/响应模型。
3. 在 `apps/api/app/services` 编写业务逻辑。
4. 在 `apps/api/app/api/routes` 暴露接口。
5. 更新 `packages/api-contract/openapi.yaml`，再生成或同步前端类型。
6. 为接口添加 `apps/api/tests` 测试，并把决策记录在 `.trellis/`。

生产环境请补充 Alembic 数据库迁移、正式 JWT/OAuth 登录、对象存储、日志、监控和限流配置。
# smart_elderly_care
