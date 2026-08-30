# Request and Lifecycle Guidelines

- Send HTTP calls through `src/utils/request.ts`; pages do not concatenate API hosts or duplicate status handling.
- Use methods supported by `UniApp.RequestOptions`. For update endpoints prefer `PUT`; the current cross-platform request typings do not accept `PATCH`.
- Read the API base URL from `VITE_API_BASE_URL`, with a local development fallback only.
- Use UniApp/Vue lifecycle hooks rather than browser events.
- Show actionable user feedback at the page layer; preserve the underlying status code in `ApiError`.
- Add token refresh, retry, and request-id behavior centrally when authentication is introduced.
