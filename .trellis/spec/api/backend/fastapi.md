# FastAPI and Database Conventions

## 1. Scope / Trigger

Applies to `apps/api` whenever a route, environment key, transaction, database
model, or runtime/deployment behavior changes.

```text
app/api/routes       HTTP protocol, status codes, dependency injection
app/services         business use cases and transaction intent
app/models           SQLAlchemy persistence models
app/schemas          Pydantic input/output models
app/db               engine and session infrastructure
app/core             environment configuration
```

## 2. Signatures

```python
create_app(settings: Settings | None = None) -> FastAPI
create_engine(database_url: str) -> AsyncEngine
create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]
init_db(engine: AsyncEngine) -> None
get_item(session: AsyncSession, item_id: int) -> Item | None
```

`items` has integer `id`, `title VARCHAR(80) NOT NULL`, boolean `completed NOT
NULL` defaulting false, and timezone-aware `created_at NOT NULL`.

## 3. Contracts

`Settings` reads these uppercase environment keys through pydantic-settings:

| Key | Required | Default / rule |
| --- | --- | --- |
| `APP_NAME` | no | `MiniApp API` |
| `ENVIRONMENT` | no | `development` |
| `DATABASE_URL` | no | local async SQLite URL |
| `CORS_ORIGINS` | no | comma-separated local H5 origins |
| `JWT_SECRET` | production | local placeholder must be replaced |
| `DEEPSEEK_API_KEY` | when Agent is enabled | secret; never commit |
| `DEEPSEEK_MODEL` | no | `deepseek-chat` |
| `DEEPSEEK_BASE_URL` | no | official DeepSeek API URL |
| `DEEPSEEK_TEMPERATURE` | no | `0.2` |
| `DEEPSEEK_MAX_OUTPUT_TOKENS` | no | `4096` |
| `DEEPSEEK_TIMEOUT_SECONDS` | no | `60` |
| `DEEPSEEK_MAX_RETRIES` | no | `2`; only network/timeout errors retry |
| `AGENT_SYSTEM_PROMPT` | no | coding-agent prompt |
| `AGENT_WORKSPACE` | no | `.`; restrict test Agent filesystem scope |
| `AGENT_TEST_ENDPOINT_ENABLED` | no | `false`; must be explicitly enabled |
| `AGENT_MAX_STEPS` | no | `100` |
| `AGENT_MAX_TOKENS` | no | `100000` |
| `AGENT_MAX_SECONDS` | no | `3600` |
| `AGENT_ALLOWED_COMMANDS` | no | comma-separated command allow-list |
| `AGENT_FILE_READ_ENABLED` | no | `true` |
| `AGENT_FILE_WRITE_ENABLED` | no | `false`; least privilege default |

All new runtime and deployment configuration must be declared in `Settings`,
documented in `.env.example`, and supplied through environment variables. Do
not hard-code environment-specific values or secrets in routes, services, or
the agent kernel.

- Keep `create_app()` as the application factory so tests inject isolated
  settings and databases.
- Every request gets an async SQLAlchemy session from app state.
- Routes translate HTTP concerns. Reusable lookup, mutation, and transaction
  logic belongs to services.
- Pydantic owns input normalization/validation. SQLAlchemy expressions must be
  parameterized; never concatenate input into SQL.

## 4. Validation & Error Matrix

| Condition | Behavior |
| --- | --- |
| Invalid body/path type, extra input field, `item_id < 1` | `422` |
| Whitespace-only or >80-character title | `422` |
| Valid item lookup misses | `404`, `Item not found` |
| Create/update transaction succeeds | commit then refresh returned model |
| Delete succeeds | commit and return `204` |
| Database/internal failure | rollback/close through session lifecycle; do not expose internals |

## 5. Good / Base / Bad Cases

- Good: schema validates, service commits, route returns the declared response.
- Base: an empty database returns an empty list and the health endpoint remains
  independent of item data.
- Bad: route code queries `session` directly for reusable behavior, production
  starts with an unchanged placeholder secret, or raw SQL includes user input.

## 6. Tests Required

- Lifecycle: health, create, list, update, and delete with response assertions.
- Validation: whitespace/oversize title, extra fields, bad types, and ID zero.
- Missing resource: update and delete return the stable `404` response.
- Run `pnpm run lint:api`, `pnpm run test:api`, and `pnpm run check:api`.
- A schema change additionally needs a production migration rehearsal.

## 7. Wrong vs Correct

Wrong—put persistence and normalization in the route:

```python
item = Item(title=payload.title.strip())
session.add(item)
await session.commit()
```

Correct—validate in the Pydantic schema and delegate the use case:

```python
return await item_service.create_item(session, payload)
```

Development may use SQLite and `metadata.create_all`. Production uses
PostgreSQL plus Alembic migrations; Alembic is not scaffolded yet and must be
initialized before the first production deployment. Never rely on automatic
schema creation for upgrades. Never commit `.env`, JWT secrets, database
credentials, or WeChat AppSecret.
