# frontend

React 19 + Vite + TypeScript (strict) web dashboard, styled with Tailwind 4 and shadcn/ui.

```sh
npm ci
npm run dev        # http://127.0.0.1:5173, proxies /api to the backend on :8000
npm run typecheck
npm run lint
npm test           # vitest; add -- --coverage for a report
npm run gen:api    # regenerate src/api/schema.d.ts from the running backend's OpenAPI
```

TypeScript is pinned to 5.9: typescript-eslint and openapi-typescript don't support TypeScript 7 yet.
