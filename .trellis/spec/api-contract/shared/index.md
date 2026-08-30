# API Contract Guidelines

Applies to `packages/api-contract` and every HTTP change shared by `apps/api`
and `apps/miniapp`.

## Pre-Development Checklist

- Do FastAPI routes/Pydantic models and `openapi.yaml` describe the same fields,
  method, validation limits, and status codes?
- Does the frontend import generated types instead of copying interfaces?
- Is the HTTP method supported by `UniApp.RequestOptions` on every target?
- Is compatibility impact documented before removing or renaming a field?

## 1. Scope / Trigger

Use this contract whenever an endpoint, request/response field, validation rule,
status code, or API base path changes. One change must update the FastAPI model,
`openapi.yaml`, generated TypeScript declarations, client call, and tests together.

## 2. Signatures

The current API base path is `/api/v1`:

```text
GET    /health                   -> 200 HealthResponse
GET    /items                    -> 200 ItemRead[]
POST   /items ItemCreate         -> 201 ItemRead
PUT    /items/{item_id} ItemUpdate -> 200 ItemRead | 404
DELETE /items/{item_id}          -> 204 | 404
```

Use `PUT` for the current completion update. The UniApp request typings used by
this repository do not accept `PATCH` as a portable method.

## 3. Contracts

```text
HealthResponse = { status: string; service: string }
ItemCreate     = { title: string (1..80 characters) }
ItemUpdate     = { completed: boolean }
ItemRead       = {
  id: integer;
  title: string;
  completed: boolean;
  created_at: RFC 3339 date-time string;
}
```

- `VITE_API_BASE_URL` is optional at build time and must include `/api/v1` when
  overriding the local default.
- `src/schema.d.ts` is generated; never hand-edit it.
- `src/index.ts` owns stable aliases consumed by the client.
- The checked-in YAML is the reviewable client contract. FastAPI
  `/openapi.json` remains the runtime description; both must express equivalent
  operations and payloads even though the YAML factors `/api/v1` into `servers`.

## 4. Validation & Error Matrix

| Condition | Expected result |
| --- | --- |
| Missing field or wrong JSON type | `422` validation response |
| Empty or whitespace-only `title` | `422` |
| `title` longer than 80 characters | `422` |
| Unknown item for update/delete | `404`, detail `Item not found` |
| Successful delete | `204`, empty response body |
| Successful read/create/update | JSON matching the declared response type |
| Network failure or non-2xx in client | rejected as `ApiError` |

Do not expose stack traces, secrets, or database error text in public errors.

## 5. Good / Base / Bad Cases

- Good: create `{"title":"完成接口联调"}`, update the returned ID with
  `{"completed":true}`, then delete it.
- Base: list an empty database and receive `[]`; health returns stable status
  and service fields.
- Bad: create with `{"title":"   "}`, omit `completed`, send a non-boolean,
  or mutate an unknown ID; each must use the matrix above.

## 6. Tests Required

For every contract change:

1. Run `pnpm --filter @miniapp/api-contract generate` and assert the generated
   declaration contains the changed field/path.
2. Run `pnpm run test:api` and assert success status, response body, validation
   failure, and not-found behavior for the affected endpoint.
3. Run `pnpm run check:miniapp` and assert all consumers compile against the
   generated aliases.
4. Run H5 and WeChat builds when request code or a consumed shape changes.

## 7. Wrong vs Correct

Wrong—duplicate a response model in a page and let it drift:

```ts
interface Item { id: string; name: string }
```

Correct—consume the generated contract alias:

```ts
import type { Item } from '@miniapp/api-contract'
```

Wrong—change only a Pydantic model. Correct—update FastAPI, YAML, generated
types, client use, and tests as one vertical slice.

## Quality Check

```bash
pnpm --filter @miniapp/api-contract generate
pnpm run check
pnpm run test:api
```
