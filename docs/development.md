# 本地开发指南

## 工具准备

```bash
node --version       # 建议 >= 20
python3 --version    # 建议 >= 3.11
pnpm --version       # 建议 >= 10
uv --version
```

本仓库声明了 `packageManager: pnpm@10.15.0`。如果系统没有 pnpm：

```bash
corepack enable
corepack prepare pnpm@10.15.0 --activate
```

## 安装依赖

```bash
pnpm install
cd apps/api && uv sync && cd ../..
```

## 启动 API

```bash
pnpm dev:api
```

也可以直接运行：

```bash
cd apps/api
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

默认数据库为 SQLite。若要使用 PostgreSQL，复制 `.env.example` 到 `apps/api/.env` 并设置：

```dotenv
DATABASE_URL=postgresql+asyncpg://miniapp:miniapp-dev-only@127.0.0.1:5432/miniapp
```

然后启动数据库：

```bash
docker compose up -d postgres
```

## 启动 UniApp

```bash
pnpm dev:miniapp       # H5
pnpm dev:weixin        # 微信小程序编译监听
```

H5 默认地址由 Vite 输出；微信开发者工具选择 `apps/miniapp/dist/dev/mp-weixin` 作为项目目录。

如果真机或微信开发者工具无法访问本机 API：

- H5 可使用 `http://127.0.0.1:8000`（浏览器端需满足 CORS）。
- 手机和微信开发者工具不能把 `127.0.0.1` 当作电脑地址，应改为局域网 IP 或 HTTPS 测试域名。
- 微信小程序正式版必须配置 request 合法域名，并使用 HTTPS。

## 接口契约

后端的 `/openapi.json` 是运行时真源；仓库摘要契约位于 `packages/api-contract/openapi.yaml`。接口变更后：

1. 更新 FastAPI 路由和 Pydantic 模型。
2. 更新 `packages/api-contract/openapi.yaml`。
3. 执行 `pnpm --filter @miniapp/api-contract generate`。
4. 运行 API 测试和前端类型检查。

## 常用检查

```bash
pnpm run check:api
pnpm run lint:api
pnpm run test:api
pnpm run check:miniapp
```

## 新增一个业务模块

复制 `items` 模块的模式，保持以下顺序：model → schema → service → route → test → OpenAPI。每个模块的认证、权限、分页和错误码应在 `.trellis/spec` 中记录约定。
