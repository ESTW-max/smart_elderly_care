# Directory Structure

```text
apps/miniapp/
├── index.html          # required H5 Vite entry
├── src/
│   ├── pages/          # page entry components; register in pages.json
│   ├── components/     # reusable presentational components
│   ├── stores/         # Pinia stores for cross-page state
│   ├── config/         # build/runtime configuration
│   ├── utils/          # platform-neutral utilities such as request.ts
│   ├── App.vue
│   ├── main.ts
│   ├── manifest.json
│   └── pages.json
└── vite.config.ts
```

- Use lowercase kebab-case for feature directories and Vue component filenames in shared components.
- Keep pages thin; extract reusable UI to `components` and shared state to `stores` only when a second consumer exists.
- Never move `index.html` out of the app root: H5 production builds require it.
- Generated `dist`, `unpackage`, certificates, and platform packages stay untracked.
