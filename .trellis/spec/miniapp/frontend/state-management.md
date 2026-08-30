# State Management

- Local form/loading/display state stays in the page component.
- Use Pinia for state shared across pages, such as authenticated user and session state.
- Persist only durable values with `uni.setStorage`; never store AppSecret, payment keys, or sensitive server credentials.
- API responses are not automatically global state. Cache only when multiple consumers or offline behavior justify it.
- Clear user-scoped persisted state on logout and account switching.
