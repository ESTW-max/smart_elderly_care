# Type Safety

- TypeScript strict mode remains enabled; avoid `any`, broad assertions, and duplicated API interfaces.
- Import request/response models from `@miniapp/api-contract`.
- Regenerate `packages/api-contract/src/schema.d.ts` after OpenAPI changes.
- Static types do not validate untrusted runtime data; important compatibility/security boundaries require explicit validation.
- Narrow errors before reading fields. Shared request errors use `ApiError` with an optional status code.
