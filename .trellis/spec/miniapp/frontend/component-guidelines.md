# Component Guidelines

- Use Vue 3 `<script setup lang="ts">` and typed props/emits.
- Prefer UniApp components (`view`, `text`, `image`, `button`) over browser-only elements in portable UI.
- Use `rpx` for mini-program-oriented responsive spacing; verify H5 rendering before shipping.
- Components emit intent; pages/stores perform API operations.
- Do not access `window`, `document`, raw DOM APIs, or browser-only component libraries in shared code.
- Platform APIs (`wx.*`, `plus.*`) must be isolated behind conditional compilation and have a fallback.
