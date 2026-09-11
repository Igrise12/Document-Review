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

The application is a single React review workflow. Keep the interface small and add application components only when a real workflow slice needs them:

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

## Design system

- Use the checked-in shadcn/ui configuration in `components.json`. Its source-owned primitives live in `src/components/ui/`; application workflow components stay directly under `src/components/`.
- Use the `@/*` alias rather than relative imports that climb across the source tree. Keep shadcn's neutral CSS-variable tokens in `src/index.css`; do not add another component or styling system.
- Add a shadcn primitive only when the working slice renders it. Current Stage 11 primitives are Button, Input, Label, Card, Badge, Alert, Alert Dialog, Dialog, Select, Separator, Skeleton, Table, Textarea, and Tooltip.
- Keep the review decision legible: show the original document beside the extracted review on desktop and stack the panels on smaller screens. Do not turn the local workflow into a dashboard.

## Code style

- Keep TypeScript strict. Prefer `unknown` plus narrowing over `any`.
- Keep components small, focused, and manually inspectable. One component per file is the default.
- Prefer `useState`, `useReducer`, and derived values before adding an external state library.
- Prefer native forms, `FormData`, `Date`, `Intl`, `URL`, and collection methods over helper packages.
- Keep HTTP behind the thin typed client in `src/lib/api.ts` once that module exists. Use native `fetch`; do not add Axios or another HTTP wrapper.
- Keep provider and API response shapes behind types in `src/lib`. Components should consume application-facing types.
- Use Tailwind classes and the shared global stylesheet. Do not add CSS modules, styled-components, Emotion, or another styling system.
- Make loading, provider failure, validation issues, review state, and destructive actions visible to the user.
- Send operational console logs only through `src/lib/logger.ts`. Log operation names, status codes, durations, safe outcomes, and API error codes; never log filenames, upload bytes, object URLs, invoice/receipt values, VAT IDs, totals, drafts, provider payloads, credentials, or raw response bodies.
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

Verify the frontend with:

```bash
pnpm install --frozen-lockfile
pnpm exec tsc -b --pretty false
pnpm lint
pnpm build
```

Use browser `URL.createObjectURL` for local and fetched-original preview, and revoke object URLs when the selected document changes or the component unmounts. Never invent extraction, confidence, conflicts, or approval results; render only API data.

Stage 11 uses the existing FastAPI review contract through `src/lib/api.ts`: upload, process, review history/detail/original, GL selection, approval, rejection, correction request/draft, and deletion. Preserve the API's server-controlled approval gate and its no-send correction-draft behavior.

As implementation is added, keep all documented frontend checks green:

```bash
pnpm exec tsc -b --pretty false
pnpm lint
pnpm build
```

Complete verification includes a manual browser walkthrough of the full upload, processing, review, correction, decision, history, and deletion workflow.

For the Stage 11 interface, also inspect the browser console: structured events must be present for API outcomes, validation, review actions, and clipboard copy results, while sensitive document data remains absent.

Do not add Vitest, Jest, Playwright, Cypress, `*.test.*`, or another automated frontend test setup. This weekly teaching project uses strict typing, linting, production builds, and manual browser verification as defined by the root instructions.
