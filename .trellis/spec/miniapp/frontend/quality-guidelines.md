# Quality Guidelines

Required before completion:

```bash
pnpm --filter @miniapp/miniapp type-check
pnpm build:h5
pnpm build:weixin
```

- Keep DCloud packages on one release number.
- Pin Vue and Vite to the peer versions declared by `@dcloudio/vite-plugin-uni`; do not use loose ranges for this toolchain.
- Do not commit generated platform output, `.env`, signing files, APK/AAB/IPA, or mini-program secrets.
- Verify network failure, empty data, duplicate submission, and long text for changed screens.
- A successful H5 build does not replace WeChat DevTools/device verification.
