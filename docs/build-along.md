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
