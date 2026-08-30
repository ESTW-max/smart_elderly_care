# Project Instructions

This repository is a multi-platform UniApp client plus a Python FastAPI service.

- Keep platform-neutral client code in `apps/miniapp/src` and use `uni.*` APIs.
- Put Python API code in `apps/api/app`; keep route handlers thin and move business logic into services.
- Treat `packages/api-contract/openapi.yaml` as the API contract. Update it when an endpoint changes.
- Prefer generated TypeScript API types from FastAPI OpenAPI over hand-maintained duplicate models.
- Never commit `.env`, credentials, certificates, or generated platform packages.
- Run `pnpm run check` and `pnpm run test:api` before finishing a task.
- Record feature requirements and decisions in `.trellis/spec` and `.trellis/tasks`.
- Before editing a package, run `python3 ./.trellis/scripts/get_context.py --mode packages` and read that package's spec index.
