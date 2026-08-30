# 部署与安全

## Docker Compose（开发/测试）

```bash
docker compose up --build -d
curl http://127.0.0.1:8000/api/v1/health
```

Compose 启动 PostgreSQL 和 API。生产环境不要直接使用仓库里的开发密码，应通过服务器 Secret、环境变量管理器或云平台密钥服务注入配置。

## 手工部署 FastAPI

本模板不能未经补充就直接用于生产：它尚未附带 Alembic 配置。请先集成
Alembic、创建并执行首个迁移，再在生产 `.env`/密钥配置中设置
`ENVIRONMENT=production`、正式 `DATABASE_URL`、`CORS_ORIGINS` 和
`JWT_SECRET`。不要沿用默认的 development 环境。完成迁移后再启动：

```bash
cd apps/api
uv sync --frozen --no-dev
uv run --frozen --no-dev uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

建议在前面放 Nginx/Caddy，负责 TLS、压缩、限流和访问日志。数据库迁移请使用 Alembic；本模板的自动建表仅用于开发。
本模板尚未初始化 Alembic 配置，第一次生产部署前必须先添加迁移环境和首个版本。

## 必做安全项

- 修改 `JWT_SECRET`，并使用长度足够的随机值。
- 生产环境 `CORS_ORIGINS` 只列出实际前端域名，禁止 `*` 搭配凭据。
- 不提交 `.env`、微信 AppSecret、支付私钥、Android/iOS 证书。
- 对上传文件做大小、扩展名、MIME 和病毒扫描限制。
- 所有写操作增加认证、授权、审计和幂等保护。
- 对登录、短信、支付和高成本接口限流。
- 定期备份数据库并演练恢复。

## 监控建议

至少采集：请求耗时、状态码、异常堆栈、数据库连接池、CPU/内存、慢查询和业务关键指标。日志中不要记录 token、密码或完整身份证/手机号。
