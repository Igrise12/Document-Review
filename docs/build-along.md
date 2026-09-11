# Build-along guide

The complete guided build lives at <https://learn.datalumina.com/docs/invoice-review>. This local guide records the first checkpoint represented by the `main` branch and the local-provider direction used by the project.

## Starter outcome

The repository installs reproducibly, starts a minimal FastAPI service and React interface, and includes the business brief plus fictional source documents.

## Why this boundary exists

The starter removes the completed workflow while preserving every prerequisite needed to build it. You begin with the user, the source documents, and explicit service boundaries instead of reverse-engineering a finished application. The completed workflow uses PaddleOCR as the primary parser and a local Qwen VLM through Ollama or vLLM; no Azure account is required.

## Commands

```bash
cd backend
uv sync --locked

cd ../frontend
pnpm install --frozen-lockfile

cd ..
cp frontend/.env.example frontend/.env
./scripts/dev.sh --check
./scripts/dev.sh
```

The starter does not need backend provider credentials. Add the local provider settings only when the provider implementation stage begins.

## Important locations

- `docs/client-brief.md`: the recurring finance problem and definition of done
- `docs/architecture.md`: the intended boundaries and data flow
- `docs/open-source-alternatives.md`: the provider decision, trade-offs, and source links
- `samples/`: the fictional evaluation corpus and manifest
- `backend/app/main.py`: the initial API boundary
- `frontend/src/App.tsx`: the initial interface boundary

## What you should observe

- `GET http://localhost:8000/health` returns `{"status":"ok"}`.
- `http://localhost:5173` shows the Invoice Review starter screen.
- No OCR or VLM request occurs at this checkpoint.

## Local provider checkpoint

The provider checkpoint uses the approved backend lockfile. The CPU smoke-test setup is:

```bash
cd backend
uv sync --locked
# If the host uv cache is read-only:
UV_CACHE_DIR=/tmp/invoice-review-uv-cache uv sync --locked
```

Verify the parser against a fictional invoice:

```bash
paddleocr pp_structurev3 \
  -i ../samples/generated/01-en-happy-classic.pdf \
  --engine paddle \
  --save_path /tmp/paddleocr-output
```

The direct versions are pinned in `backend/pyproject.toml` and `backend/uv.lock`. `paddlepaddle==3.2.0` is resolved only from the explicit Paddle CPU index; the package-specific cooldown exception is documented beside the uv setting because this exact wheel is approved for the checkpoint. GPU remains a host-dependent alternative using a matching `paddlepaddle-gpu` wheel.

Use the matching `paddlepaddle-gpu` wheel for an NVIDIA setup. Then run a local Qwen2.5-VL model through Ollama for development or vLLM for GPU-backed serving. Keep model weights and runtime data outside the repository; do not commit them.

## Playground smoke test

The raw PaddleOCR experiment remains in `playground/analyze_sample_invoice.py` for inspecting provider JSON/Markdown. The application mapping now lives in `backend/app/providers/paddleocr.py`; third-party result objects and package errors stop there.

Run the raw inspection script from the repository environment:

```bash
cd backend
PYTHONPATH=. UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  uv run --locked --no-sync python ../playground/analyze_sample_invoice.py --device cpu
```

The default input is `samples/generated/01-en-happy-classic.pdf`. To inspect another fictional document or print the structured result to the terminal:

```bash
PYTHONPATH=. UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  uv run --locked --no-sync python ../playground/analyze_sample_invoice.py \
  ../samples/generated/13-nl-fuel-receipt.png --device cpu --print-results
```

The script writes PaddleOCR JSON and Markdown artifacts to `/tmp/paddleocr-output`. Use `--device gpu` or `--device gpu:0` when the environment has a working NVIDIA setup. No uploaded document, model output, or model weight is written to the repository.

## Checkpoint

- [ ] Locked backend and frontend installs succeed.
- [ ] Backend lint passes.
- [ ] Frontend type-check, lint, and production build pass.
- [ ] `./scripts/dev.sh --check` reports that Invoice Review is ready to start.
- [ ] The health endpoint and starter screen load locally.
- [ ] The local provider setup is documented before any corpus evaluation is run.
- [ ] The PaddleOCR playground runs against at least one fictional document and produces JSON/Markdown output under `/tmp`.

Continue with the [online tutorial](https://learn.datalumina.com/docs/invoice-review).

## Stage 1 checkpoint — starter reconciled

Completed on 2026-09-11. The missing starter boundary was restored: `GET /health` is available, the React starter screen builds and serves, and `scripts/dev.sh` can supervise both processes. README and environment guidance now describe the local PaddleOCR/Qwen stack, model-cache placement, hardware expectations, and the absence of per-document API charges.

The exact direct PaddleOCR pins were approved for the later Stage 4 checkpoint: `paddleocr[doc-parser]==3.7.0` with `paddlepaddle==3.2.0`. Stage 1 itself remains a historical starter checkpoint and did not include provider dependencies.

Commands run:

```bash
cd backend
uv sync --locked

cd ../frontend
pnpm install --frozen-lockfile

cd ..
cd backend
uv run --locked --no-sync ruff check app
cd ../frontend
pnpm exec tsc -b --pretty false
pnpm lint
pnpm build
cd ..
./scripts/dev.sh --check
```

The locked installs, backend lint, frontend type-check, ESLint, and production build passed. The readiness check correctly reported that port 8000 was already occupied by an unrelated local Uvicorn process, so `./scripts/dev.sh` could not claim the default API port without stopping it. The starter API was instead run on port 18000 and returned `{"status":"ok"}`; the Vite page was fetched successfully from port 5173. No provider request occurred.

Checkpoint: starter code and documentation were ready for provider implementation; Stage 4 below records the later approved provider slice.

## Playground checkpoint — corpus document types

The first pre-provider check lives in `playground/check_document_types.py`. It uses the existing locked Pydantic v2 dependency to validate `samples/manifest.json`, enforce `invoice`/`receipt` as the only document types, confirm the expected type-specific fields, and verify that all 13 fictional files exist. It checks the corpus contract; it is not an OCR classifier.

Run it with the existing backend environment:

```bash
cd backend
PYTHONPATH=. uv run --locked --no-sync python ../playground/check_document_types.py
```

The observable result is `PASS: 12 invoices, 1 receipt`, followed by one line per sample. A provider classifier can later feed its structured output into the same `DocumentType` boundary.

Checkpoint: the golden corpus labels and Pydantic shape are validated before provider implementation begins.

## Stage 2 checkpoint — provider-independent contracts

Stage 2 adds the canonical Pydantic v2 contracts under `backend/app/`. The normalized financial document is a discriminated `invoice`/`receipt` union. Invoice-only fields are not accepted by receipt models. Money uses exact `Decimal` values and rejects float input; currency and VAT models retain both normalized and display values.

The same contract boundary now describes typed field evidence, primary/VLM fallback/conflict states, review issues and states, provider run metadata, GL suggestions versus Maya's selection, and copyable correction-email drafts. These models contain no provider SDK types, business-policy decisions, database code, or email-sending behavior.

Run the playground contract check and backend lint:

```bash
cd backend
PYTHONPATH=. uv run --locked --no-sync python ../playground/check_document_types.py
uv run --locked --no-sync ruff check app ../playground/check_document_types.py
```

The observable result is `PASS: 12 invoices, 1 receipt; stage 2 contracts valid`, followed by the corpus classification. Ruff reports no errors. No provider request or dependency installation is required.

Checkpoint: provider adapters, deterministic validation, persistence, and routes can now depend on one provider-independent Pydantic contract.

## Stage 3 checkpoint — configuration and local persistence

Stage 3 adds the local runtime configuration boundary, original-upload storage, and the first SQLite repository. Configuration is read through `backend/app/config.py`; the default data directory is outside the repository at `~/.invoice-review`. Upload bytes are validated against the fixed PDF/PNG/JPEG and 4 MB contract, stored unchanged under an internal UUID key, and never addressed by the client filename.

The repository creates `uploaded_documents` and `reviews` for a fresh checkout. Review payloads that will evolve with later provider stages are stored as JSON, while state, document type, duplicate key, timestamps, and file metadata remain directly queryable. Deletion is a hard delete: it removes duplicate participation and returns the exact storage key for file cleanup. Provider failures will retain the original file for retry when orchestration is added.

Run the stage 3 smoke check and static verification:

```bash
cd backend
PYTHONPATH=. uv run --locked --no-sync python ../playground/check_persistence.py
uv run --locked --no-sync ruff check app ../playground/check_persistence.py

cd ../frontend
pnpm exec tsc -b --pretty false
pnpm lint
pnpm build
```

The observable result is `PASS: local configuration, file storage, and SQLite persistence`, followed by clean Ruff, TypeScript, ESLint, and production-build checks. The smoke check uses a temporary directory, so it leaves no sample upload or SQLite database in the repository. No PaddleOCR, Qwen, or external provider request occurs.

Checkpoint: settings, safe original-file storage, and repository round-trips are ready for provider orchestration and HTTP routes.

## Stage 4 checkpoint — primary parser and frontend harness

Completed on 2026-09-11. PP-StructureV3 is now behind `backend/app/providers/paddleocr.py`. The adapter validates the original bytes again, writes only a temporary file for synchronous inference, unwraps the provider result, aggregates PDF pages, and returns only normalized financial-document models, field evidence, and provider metadata. The mapper uses a deliberately small multilingual label-window heuristic for the fictional English, Dutch, German, and French corpus; missing values remain missing.

The provider boundary matters because raw PaddleOCR result objects, NumPy arrays, and package-specific exceptions must not leak into domain models, persistence, or the frontend. The adapter records `paddleocr`, `PP-StructureV3`, `paddleocr==3.7.0`, the schema version, CPU/device runtime, duration, confidence, page, box, and text context for primary fields. It does not create VLM fallback, merge, conflict, validation, or approval state yet.

Exact dependency and verification commands:

```bash
cd backend
UV_CACHE_DIR=/tmp/invoice-review-uv-cache uv sync --locked
UV_CACHE_DIR=/tmp/invoice-review-uv-cache uv run --locked --no-sync ruff check app ../playground
PYTHONPATH=. UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  uv run --locked --no-sync python ../playground/check_paddleocr.py

cd ../frontend
pnpm install --frozen-lockfile
pnpm exec tsc -b --pretty false
pnpm lint
pnpm build
```

The observable provider result is:

```text
PASS 01-en-happy-classic.pdf: invoice, vendor, total 121.00, primary evidence
PASS 13-nl-fuel-receipt.png: receipt, total 60.50, VAT 10.50
PASS 12-en-two-page.pdf: two pages combined with page evidence
PaddleOCR adapter smoke check passed.
```

The React page is a developer harness named “Primary Parser Checkpoint”. It checks `GET /health`, validates one local PDF/PNG/JPEG up to 4 MB, previews the selected file with a browser object URL, and explicitly says processing is not available. It does not call a provider on page load, invent extraction values, or simulate confidence/approval. VLM review, merge/provenance conflicts, deterministic validation, GL selection, upload/process API orchestration, and the full Maya review UI remain future stages.

Checkpoint: the primary parser has a real CPU smoke path and the frontend can show the evidence document plus backend readiness before the API stage begins.

## Stage 5 checkpoint — local Qwen VLM adapters

Stage 5 adds `backend/app/providers/qwen.py` as the only boundary for the local Qwen model. It uses the existing OpenAI-compatible dependency and supports both the default Ollama endpoint and vLLM through the settings already defined in `backend/app/config.py`. The adapter accepts the original upload, renders every PDF page to an image inside the provider boundary, and never sends only the primary parser's extracted values to the independent review path.

The provider exposes four focused operations: structured invoice/receipt classification, document review with typed invoice/receipt fields and per-field confidence, GL suggestion from normalized fields plus a supplied catalog, and on-demand correction-draft generation. Each response uses a strict JSON Schema, is validated by Pydantic, records model/runtime/prompt/schema metadata, and retries invalid structured output only within the configured bound. Invalid GL account IDs are discarded rather than becoming business policy. The correction operation returns text only and has no email-sending capability.

No new dependency was added. PDF rendering reuses the locked `pypdfium2` and Pillow environment already present through the existing provider setup. The domain models now carry classification results, raw VLM extraction results, GL suggestion results, and correction-draft results without leaking OpenAI or PDF-renderer types.

Run the deterministic adapter smoke check and backend lint:

```bash
cd backend
PYTHONPATH=. UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  uv run --locked --no-sync python ../playground/check_qwen.py
UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  uv run --locked --no-sync ruff check app ../playground/check_qwen.py
```

The observable result is `PASS: Qwen offline schema, retry, PDF rendering, GL validation, and draft checks`. The smoke check uses a fake OpenAI-compatible client, so it does not require a running model and does not upload documents. A live check was run against the available Ollama-compatible endpoint and model:

```bash
LOCAL_VLM_BASE_URL=http://localhost:7869/v1 \
LOCAL_VLM_MODEL=qwen2.5vl:3b \
PYTHONPATH=. UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  uv run --locked --no-sync python ../playground/check_qwen.py --live
```

The observable result is `PASS: Qwen live checks via ollama (qwen2.5vl:3b)`. The endpoint exposed `qwen2.5vl:3b` rather than the default `qwen2.5vl:7b`, so the model and port were supplied as command-local overrides; the repository defaults remain unchanged. The provider also normalizes harmless model formatting such as currency-prefixed decimal strings before strict domain validation. The full service orchestration, deterministic policy validation, API routes, persistence wiring, and UI remain later stages.

Checkpoint: the Qwen provider boundary and all four structured adapter contracts pass both offline verification and a live local-model smoke check.

## Stage 6 checkpoint — deterministic normalization and merge

Completed on 2026-09-11. `backend/app/document_review/reconciliation.py` now canonicalizes provider-independent dates, exact decimal values, currencies, VAT IDs, whitespace, and known empty markers. It returns new validated document models, so normalization does not mutate provider results or evidence context.

`merge_extractions` accepts `PrimaryExtractionResult` and `VLMExtractionResult` and returns `MergedExtractionResult`. Primary values remain authoritative. A VLM value fills only a missing primary field; equal values are marked `MERGED`; disagreements are marked `CONFLICT` while preserving both candidates. The original primary evidence context and source page count remain intact. The module contains no HTTP, SQLite, or provider SDK code and does not perform VAT or approval policy decisions.

Run the reconciliation smoke check and backend lint:

```bash
cd backend
PYTHONPATH=. UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  uv run --locked --no-sync python ../playground/check_reconciliation.py
UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  uv run --locked --no-sync ruff check app ../playground/check_reconciliation.py
```

The observable result is `PASS: normalization, merge precedence, provenance, conflict, and two-page checks`. The check uses fictional corpus metadata and typed fixtures; it does not call PaddleOCR, Qwen, or an HTTP endpoint.

The React surface is now named “Normalize & merge checkpoint”. It keeps the health request, one-file validation, and local PDF/image preview while showing the six checkpoints with Stage 6 active. It intentionally does not simulate extracted fields, confidence, conflicts, approval, or processing because the upload/process API is still a later stage.

Checkpoint: deterministic merge behavior and multi-page provenance are verified independently, while the React harness accurately represents the current backend boundary.

## Stage 7 checkpoint — deterministic VAT and finance validation

Stage 7 adds `backend/app/invoices/validation.py`, a pure policy module with no
HTTP, SQLite, provider, or VIES dependency. It validates EU VAT IDs locally with
the already locked `python-stdnum==2.2` package, while preserving the original
review-friendly VAT display value. The fixed Northstar customer VAT ID,
`NL00449544B01`, the EUR 0.01 reconciliation tolerance, and the 0.80 primary
confidence threshold remain immutable tutorial policy rather than environment
settings.

Invoice and receipt requirements are intentionally separate. The invoice policy
returns blocking errors for required identity, VAT, money, date, and duplicate
conditions, and warnings for a missing purchase order or each low-confidence
primary field. The receipt policy requires only its receipt-specific fields and
reconciles subtotal, VAT, and total when all three are present. A duplicate key
is built only from a valid canonical supplier VAT ID and invoice number; later
orchestration will query SQLite and pass the result into this pure module.
`approval_allowed` permits a human approval only when no blocking issue remains
and the catalog layer has supplied a valid selected GL account. It does not
change a review state or select an account.

Run the self-check and lint with the locked environment:

```bash
cd backend
PYTHONPATH=. UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  uv run --locked --no-sync python ../playground/check_validation.py
UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  uv run --locked --no-sync ruff check app ../playground
```

The observable self-check result is:

```text
PASS: offline EU VAT, invoice and receipt policy, duplicate keys, and approval checks
```

The check uses only fictional corpus metadata and in-memory Pydantic models. It
does not call a local model, send email, query VIES, or create a committed test
suite.

Checkpoint: deterministic policy and human approval eligibility are ready for
the GL catalog and workflow orchestration stages.

## Stage 8 checkpoint — fixed Northstar GL catalog

Stage 8 adds the fixed Northstar GL catalog under `backend/app/accounting/`. It
contains six immutable accounts covering cleaning, maintenance, electrical,
plumbing, equipment, and fuel. Stable IDs keep provider suggestions and human
selections comparable across reviews; the catalog is application policy, not
model output, environment configuration, or database data.

`validate_gl_selection()` accepts only an exact catalog ID and returns the
provider-independent `GLSelectionValidation` result for the approval gate.
Missing and unknown IDs are invalid with a user-facing reason. The read-only
`GET /gl-catalog` endpoint exposes the same fixed entries to the future review
UI without calling a provider or accepting account definitions from the
client. Existing `GLReview` persistence stores a VLM suggestion and a distinct
human selection, so Maya can override the suggestion without changing the
catalog.

No dependency or database schema change is needed. The Qwen smoke check now
passes the actual Northstar catalog rather than a script-local catalog.

Run the stage 8 checks with the locked backend environment:

```bash
cd backend
PYTHONPATH=. uv run --locked --no-sync python ../playground/check_validation.py
PYTHONPATH=. uv run --locked --no-sync python ../playground/check_persistence.py
PYTHONPATH=. uv run --locked --no-sync python ../playground/check_qwen.py
uv run --locked --no-sync ruff check app ../playground
```

The observable result includes clean validation, persistence, and Qwen smoke
checks. To inspect the HTTP contract locally:

```bash
uv run --locked --no-sync uvicorn app.main:create_app --factory --port 18000
curl http://localhost:18000/gl-catalog
```

The response is a six-entry JSON array in stable catalog order. The review
selection action and UI control remain part of the later API and React stages;
this checkpoint supplies their fixed policy boundary.

Checkpoint: the fixed account catalog, server-side selection validation,
provider catalog input, and suggestion/selection persistence are ready for
workflow orchestration.

## Stage 9 checkpoint — synchronous review orchestration

Completed on 2026-09-11. `backend/app/invoices/service.py` now owns the
single-document workflow that was previously spread across future route and
provider boundaries. Upload first validates and stores the original bytes, then
processing moves the review through classification, primary PaddleOCR parsing,
document-type reconciliation, independent Qwen review of the original file,
deterministic merge, offline policy validation, GL suggestion, and SQLite
persistence.

The service receives provider dependencies explicitly, so the workflow is
testable without a live model and `/health` remains free of PaddleOCR model
initialization. Stage 10 wraps those dependencies in lazy factories so app
construction and non-processing routes stay lightweight. Qwen classification
must agree with the primary parser before the review path continues. A
disagreement or any provider failure produces a retryable `failed` review. When
safe, primary or merged fields, evidence, issues, duplicate keys, and provider
metadata remain available as partial data; partial data can never become an
approval-ready review.

The repository processing write now accepts nullable page counts and an
optional failure message, allowing the same persistence path to clear stale
payloads at retry start and retain actionable failed results. No provider
response body, upload content, credential, or full document text is logged or
stored as a failure message.

Run the offline service check and backend lint:

```bash
cd backend
UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  PYTHONPATH=. uv run --locked --no-sync python ../playground/check_service.py
UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  uv run --locked --no-sync ruff check app ../playground
```

The observable result is:

```text
PASS: service order, partial failures, retry state, and upload cleanup
```

The check uses fictional PDF bytes and fake provider objects. It verifies the
provider call order, primary/VLM fallback, policy warning persistence,
classification conflict handling, GL-provider failure handling, and cleanup
when database upload creation fails. It does not call PaddleOCR, Qwen, or any
network endpoint.

Checkpoint: the local review pipeline has one explicit synchronous orchestration
boundary and a recoverable persistence contract; FastAPI endpoints and the
React review experience remain stage 10 and later.

## Stage 10 checkpoint — minimal FastAPI review API

Completed on 2026-09-11. FastAPI now exposes the complete local review boundary:
single-file upload, synchronous processing, compact history, full detail,
original-file preview, fixed GL selection, approval, rejection, correction
request, on-demand correction draft, and explicit deletion. `GET /health` and
`GET /gl-catalog` remain available. The API is intentionally unversioned and
local because there is one teaching client and no external integration contract.

`POST /reviews` accepts exactly one multipart `file`, reads no more than the 4 MB
limit plus one byte, and delegates signature validation and safe storage to the
existing service/storage boundary. Detail responses expose normalized values,
evidence, explicit conflicts, deterministic issues, GL suggestion and human
selection, approval eligibility, provider/action metadata, and safe original
metadata. Internal storage and duplicate keys never cross the HTTP boundary.
`GET /reviews/{id}/original` returns the unchanged bytes needed by the next
React preview slice.

Review actions remain server-controlled. GL selection, approval, rejection, and
correction request accept only `ready_for_review`; approval reruns the pure gate,
and correction requires a blocking issue. A correction request records state
without sending anything. Draft generation calls Qwen only when requested,
returns copyable text, and is not persisted. Provider factories are lazy and
cached, so app startup, health, upload, history, detail, and original reads do
not initialize PaddleOCR or Qwen.

Handled failures use one response shape, `{"error":{"code":"...","message":"..."}}`.
Missing reviews return 404, invalid transitions return 409, invalid requests,
uploads, or GL selections return 422, and an on-demand draft provider failure
returns 502. A processing provider failure remains an HTTP 200 review result
with state `failed`, because the recoverable failure was persisted successfully.
Local CORS permits the Vite origins at `localhost:5173` and `127.0.0.1:5173`.

Run the offline API and existing backend checks:

```bash
cd backend
UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  PYTHONPATH=. uv run --locked --no-sync python ../playground/check_persistence.py
UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  PYTHONPATH=. uv run --locked --no-sync python ../playground/check_validation.py
UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  PYTHONPATH=. uv run --locked --no-sync python ../playground/check_service.py
UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  PYTHONPATH=. uv run --locked --no-sync python ../playground/check_api.py
UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  uv run --locked --no-sync ruff check app ../playground
```

The observable API result is:

```text
PASS: minimal API upload, processing, review actions, errors, CORS, and deletion
```

`check_api.py` starts the app on an ephemeral loopback port with a temporary
SQLite database, temporary upload directory, and fictional provider doubles.
It exercises real HTTP and multipart parsing without calling PaddleOCR, Qwen,
VIES, email, or any external network endpoint. It verifies provider laziness,
upload boundaries, history/detail contracts, provenance conflicts, original
bytes, GL override, approval/rejection/correction states, draft failures, CORS,
consistent errors, and stored-file deletion.

Checkpoint: the backend contract required by the Stage 11 React experience is
complete and verified; the current React checkpoint remains unchanged until
that next slice.

## Stage 11 checkpoint — React review experience and console logging

Completed on 2026-09-11. The Stage 6 harness is replaced with Maya's complete
local review surface: select and preview one supported document, upload it,
run the synchronous local pipeline, inspect the original beside the normalized
review, choose or override the GL account, decide, create a no-send correction
draft, reopen history, and explicitly delete a local review so the sample can
be uploaded again.

The implementation uses checked-in shadcn/ui source primitives rather than a
second UI framework. `components.json`, the `@/*` alias, neutral semantic CSS
tokens, and the selected primitives make the system inspectable and reusable
while keeping application workflow components focused. The desktop view pairs
the original document with the review decision; mobile stacks those panels.

`src/lib/api.ts` is the single typed HTTP boundary. It converts the existing
handled API error shape into a safe UI error, uses browser `FormData`, fetches
the original only when a history review is opened, and keeps approval under the
server's existing gate. `src/lib/logger.ts` emits structured browser-console
events for operation results, safe error codes, validation, actions, and
clipboard outcomes. It deliberately excludes filenames, document contents,
financial values, VAT IDs, drafts, preview URLs, provider payloads, and
credentials.

The added direct dependencies are pinned exactly in `frontend/package.json`
and `frontend/pnpm-lock.yaml`: Radix Alert Dialog, Dialog, Select, Separator,
Slot, and Tooltip; `class-variance-authority`, `clsx`, `tailwind-merge`, and
`tw-animate-css`; plus `lucide-react@1.40.0`. The originally proposed
`lucide-react@1.45.0` was published within the required seven-day release
cooldown, so pnpm rejected it and the mature 1.40.0 release was used instead.
No cooldown exception, router, state manager, form library, HTTP wrapper,
analytics, remote error service, or automated test suite was added.

Run the locked frontend verification:

```bash
cd frontend
pnpm install --frozen-lockfile
pnpm exec tsc -b --pretty false
pnpm lint
pnpm build
```

The observable result is a clean type check and lint run followed by a Vite
production bundle. In the browser, the welcome/upload state, empty history,
backend-unavailable recovery state, and redacted structured console events are
visible without a provider request. With the standard local API and provider
setup running, walk through upload/preview, ready and failed processing,
invoice and receipt review, conflict/provenance, GL override and approval,
rejection, correction draft generation/copy/close, history reopening, and
deletion/re-upload. The app never sends the correction draft or claims a live
VIES lookup or background worker.

Checkpoint: the frontend now consumes the complete Stage 10 API contract with
accessible local review controls and console-only, redacted frontend logging.
