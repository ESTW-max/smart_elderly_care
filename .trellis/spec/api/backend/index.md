# FastAPI Backend Guidelines

Applies to `apps/api`.

## Pre-Development Checklist

- Are Pydantic request/response models and error semantics defined first?
- Is the route thin, with business logic in `services`?
- Does database work use the async SQLAlchemy session and an explicit transaction boundary?
- Are success, validation, and not-found paths covered by tests?
- Does an API change also update `packages/api-contract/openapi.yaml`?

## Guides

- [FastAPI and Database Conventions](./fastapi.md)

## Quality Check

```bash
pnpm run lint:api
pnpm run test:api
pnpm run check:api
```

Production schema changes require Alembic migrations. `metadata.create_all` is development-only.
