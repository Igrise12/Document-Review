# Frontend agent instructions

Read [../AGENTS.md](../AGENTS.md) first. The root file contains the project-wide product boundaries, dependency policy, teaching rules, and verification policy. This file adds frontend-specific conventions.

## Stack

- Vite with a plain React single-page application.
- Strict TypeScript.
- Tailwind CSS for styling and shared theme tokens.
- Native browser APIs and `fetch` for client behavior and HTTP.
- `pnpm` for dependency management.

This is not a Next.js application. Do not introduce Next.js, SSR, server components, file-based routing, or a Node application server. The stack is locked unless Dave explicitly approves a change.

## Layout

The current checkpoint contains a single React developer harness. Keep the interface small and add application components only when a real workflow slice needs them:

```text
frontend/
├── src/
│   ├── components/          # Small application components
│   │   └── ui/              # Reusable visual primitives
│   ├── lib/                 # API client, environment, types, and pure helpers
│   ├── App.tsx              # Application-level workflow
│   ├── main.tsx             # React entry point
│   └── index.css            # Tailwind and global theme tokens
├── index.html
├── vite.config.ts
├── tsconfig.json
├── package.json
└── pnpm-lock.yaml
```

Do not create route, state, form, or component frameworks before the workflow needs them.

## Code style

- Keep TypeScript strict. Prefer `unknown` plus narrowing over `any`.
- Keep components small, focused, and manually inspectable. One component per file is the default.
- Prefer `useState`, `useReducer`, and derived values before adding an external state library.
- Prefer native forms, `FormData`, `Date`, `Intl`, `URL`, and collection methods over helper packages.
- Keep HTTP behind the thin typed client in `src/lib/api.ts` once that module exists. Use native `fetch`; do not add Axios or another HTTP wrapper.
- Keep provider and API response shapes behind types in `src/lib`. Components should consume application-facing types.
- Use Tailwind classes and the shared global stylesheet. Do not add CSS modules, styled-components, Emotion, or another styling system.
- Make loading, provider failure, validation issues, review state, and destructive actions visible to the user.
- Do not add authentication, routing, analytics, or global state unless the user story changes.

## Configuration

- `src/lib/env.ts` is the only frontend environment boundary once implementation begins.
- Keep `VITE_API_BASE_URL` as the public backend URL and validate it at application startup.
- Never read `import.meta.env` directly from components or unrelated helpers.
- Only `VITE_`-prefixed values are exposed to browser code. Never put secrets in frontend environment files.

## Dependencies and package manager

- Use `pnpm` only. Do not create `package-lock.json` or `yarn.lock`.
- Never add a dependency without Dave's explicit approval.
- Pin direct dependencies exactly and commit `pnpm-lock.yaml` with every approved dependency change.
- Keep `savePrefix: ""`, `minimumReleaseAge: 10080`, and `minimumReleaseAgeStrict: true` in `pnpm-workspace.yaml`.
- Install with `pnpm install --frozen-lockfile`.
- Prefer browser and React platform capabilities when a package would only replace a small amount of clear code.

## Verification

Verify the current harness with:

```bash
pnpm install --frozen-lockfile
pnpm exec tsc -b --pretty false
pnpm lint
pnpm build
```

The harness uses `src/lib/api.ts` for the health request, browser `URL.createObjectURL` for local PDF/image preview, and revokes object URLs when the selected file changes or the component unmounts. It has no upload/process endpoint yet and must not invent extraction, confidence, or approval results.

As implementation is added, keep all documented frontend checks green:

```bash
pnpm exec tsc -b --pretty false
pnpm lint
pnpm build
```

Complete verification includes a manual browser walkthrough of the full upload, processing, review, correction, decision, history, and deletion workflow.

Do not add Vitest, Jest, Playwright, Cypress, `*.test.*`, or another automated frontend test setup. This weekly teaching project uses strict typing, linting, production builds, and manual browser verification as defined by the root instructions.
