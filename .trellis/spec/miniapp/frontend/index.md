# UniApp Frontend Guidelines

Applies to `apps/miniapp`, which builds the same Vue 3 code for H5, WeChat Mini Program, Android, and iOS.

## Pre-Development Checklist

- Can the feature be expressed with `uni.*` APIs on every target platform?
- Does API data use types exported by `@miniapp/api-contract`?
- Are loading, empty, network-error, and duplicate-submit states designed?
- Is platform-only behavior isolated with UniApp conditional compilation?
- Does the proposed dependency support the UniApp runtime rather than only browser DOM?

## Guides

- [Directory Structure](./directory-structure.md)
- [Component Guidelines](./component-guidelines.md)
- [Request and Lifecycle Guidelines](./hook-guidelines.md)
- [State Management](./state-management.md)
- [Quality Guidelines](./quality-guidelines.md)
- [Type Safety](./type-safety.md)

## Quality Check

```bash
pnpm --filter @miniapp/miniapp type-check
pnpm build:h5
pnpm build:weixin
```

Test affected pages in H5 and WeChat DevTools. App-only capabilities also require an HBuilderX device/build check.
