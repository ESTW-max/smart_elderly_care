# API 与类型契约

## 示例接口

服务根路径：`/api/v1`

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/health` | 健康检查 |
| GET | `/items` | 按创建时间倒序读取任务 |
| POST | `/items` | 创建任务，`title` 长度 1–80 |
| PUT | `/items/{item_id}` | 更新 `completed` |
| DELETE | `/items/{item_id}` | 删除任务 |

完整契约见 `packages/api-contract/openapi.yaml`，运行中的交互式文档见 `/docs`。

## 请求示例

```bash
curl http://127.0.0.1:8000/api/v1/health

curl -X POST http://127.0.0.1:8000/api/v1/items \
  -H 'Content-Type: application/json' \
  -d '{"title":"完成接口联调"}'

curl -X PUT http://127.0.0.1:8000/api/v1/items/1 \
  -H 'Content-Type: application/json' \
  -d '{"completed":true}'
```

## 错误处理

- `400`：无法解析的 HTTP 请求；常规字段/业务参数校验使用 `422`。
- `401/403`：后续接入认证/权限后使用。
- `404`：资源不存在。
- `422`：Pydantic 参数校验失败。
- `5xx`：服务端异常，生产环境应记录 request id 并避免返回堆栈。

前端的 `src/utils/request.ts` 将非 2xx 响应统一转换为 `ApiError`。真实项目可在这里加入 token 注入、刷新、重试和 request id。

## OpenAPI 类型生成

```bash
pnpm --filter @miniapp/api-contract generate
```

生成结果写入 `packages/api-contract/src/schema.d.ts`。前端通过 `@miniapp/api-contract` 引用类型，不要在页面中复制接口模型。
