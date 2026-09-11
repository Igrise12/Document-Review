# Invoice Review frontend checkpoint

The frontend is a small Vite + React + TypeScript harness for the current
normalization and merge checkpoint. It checks the local API health, validates
one fictional PDF/PNG/JPEG upload up to 4 MB, and previews the selected file in
the browser.

```bash
pnpm install --frozen-lockfile
pnpm exec tsc -b --pretty false
pnpm lint
pnpm build
```

Processing and review endpoints are intentionally not connected yet. The
harness does not simulate extraction, confidence, conflicts, or approval.
