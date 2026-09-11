# Invoice Review TODO

This checklist turns the client brief, target architecture, local-provider decision, pricing notes, and build-along checkpoint into an implementation plan. Product copy, source code, documentation, and teaching content remain in English; only fictional sample documents vary by language.

## Definition of done

- [ ] A finance administrator can upload one PDF, PNG, or JPEG up to 4 MB.
- [ ] The application processes the document as an invoice or receipt through the local provider pipeline.
- [ ] PaddleOCR remains the primary evidence source; the Qwen VLM only fills missing values and produces explicitly marked suggestions/drafts.
- [ ] The review shows normalized values, confidence, provenance, and conflicts before a decision is made.
- [ ] Deterministic VAT, arithmetic, duplicate, and document-policy checks produce blocking errors and non-blocking warnings.
- [ ] A valid Northstar GL account is selected before approval.
- [ ] Maya can approve, reject, request a correction draft, copy the draft, and close the draft without sending email.
- [ ] Review history can be reopened and explicitly deleted so a sample can be processed again.
- [ ] The complete fictional corpus passes the agreed extraction and policy evaluation thresholds.
- [ ] Backend lint, frontend type-check/lint/build, local provider checks, and the manual browser walkthrough pass.
- [ ] The build-along documentation records every completed working slice.

## Scope guardrails

- [ ] Keep the build local: PaddleOCR plus Qwen2.5-VL through Ollama during development or vLLM for GPU-backed serving.
- [ ] Keep provider-specific SDKs, response types, rendering, and runtime details inside `backend/app/providers/`.
- [ ] Allow only normalized provider-independent models to cross into the domain layer.
- [ ] Keep business rules pure in `backend/app/invoices/validation.py`.
- [ ] Keep HTTP concerns in `routes.py`, orchestration in `service.py`, and SQLite access in `repository.py`.
- [ ] Read backend settings only through `backend/app/config.py` and frontend settings only through `frontend/src/lib/env.ts`.
- [ ] Keep uploaded documents, model weights, runtime caches, generated provider output, and SQLite runtime data outside Git.
- [ ] Do not add authentication, queues, workers, deployment, batch processing, email ingestion/sending, or accounting integrations.
- [ ] Do not use live VIES registration lookup; VAT checks stay offline and deterministic.
- [ ] Do not add an automated test suite, `tests/` directory, or `*.test.*` files; use the corpus evaluator and small runnable self-checks instead.

## 1. Reconcile and verify the starter

- [x] Keep the starter checkpoint intact: `GET /health` returns `{"status":"ok"}` and the React starter screen loads.
- [x] Update the root README and environment guidance so they agree with the local PaddleOCR/Qwen direction documented in `docs/`.
- [x] Document the local runtime choices, model-cache location, hardware expectations, and the fact that local execution has no per-document API charge.
- [x] Approve and document the direct PaddleOCR package/version before adding it: `paddleocr[doc-parser]==3.7.0` with `paddlepaddle==3.2.0` for the CPU checkpoint.
- [x] Preserve exact dependency pins and lockfiles.
- [x] Verify the starter with:
  - [x] `cd backend && uv sync --locked`
  - [x] `cd frontend && pnpm install --frozen-lockfile`
  - [ ] `./scripts/dev.sh --check` — blocked by an unrelated process already using port 8000.
  - [ ] `./scripts/dev.sh` — blocked by the same port conflict.
- [x] Record the starter verification result in `docs/build-along.md` before beginning the provider stage.

## 2. Define provider-independent domain contracts

### Normalized financial document

- [x] Add a strict Pydantic v2 model for the normalized financial document.
- [x] Represent the document type as `invoice` or `receipt`.
- [x] Represent money with exact decimal values, never binary floating-point arithmetic.
- [x] Normalize dates to an unambiguous ISO date representation.
- [x] Normalize currency codes and VAT IDs while retaining the display value needed for review.
- [x] Include source-document metadata needed for file name, media type, size, page count, and processing timestamps.

### Invoice fields

- [x] Model vendor name and supplier VAT ID.
- [x] Model customer name and customer VAT ID.
- [x] Model invoice number, invoice date, due date, purchase order, and currency.
- [x] Model subtotal, total tax, and invoice total.

### Receipt fields

- [x] Model merchant, transaction date, expense category, currency, subtotal, VAT total, and total.
- [x] Make invoice-only fields inapplicable rather than treating them as missing receipt requirements.

### Evidence and uncertainty

- [x] Define a provider-neutral field evidence shape containing value, confidence, source, and optional page/box or text context.
- [x] Distinguish primary-parser values, VLM fallback values, merged values, missing values, and conflicts.
- [x] Store the primary value and VLM value when they conflict so the UI can show both.
- [x] Store provider/model name, model version, prompt version, schema version, and processing metadata with each review.
- [x] Define structured issue codes, severity, message, and affected field.
- [x] Define review states needed by the flow: uploaded, processing, ready for review, approved, rejected, correction requested, and failed.
- [x] Define a correction-email draft response containing copyable text and no send operation.

### GL selection

- [x] Define a provider-independent GL account model with stable ID, label, and Northstar category.
- [x] Define the distinction between a model suggestion and Maya's selected account.
- [x] Define the validation result that makes a selected account eligible for approval.

## 3. Establish configuration and local persistence

### Settings

- [x] Add `backend/app/config.py` as the single backend settings entry point.
- [x] Configure provider runtime (`ollama` or `vllm`), base URL, model name, device/engine, timeout, and bounded structured-output retry settings.
- [x] Keep local API keys optional where the runtime does not require one.
- [x] Add safe defaults and fail clearly when a provider setting required for processing is absent.
- [x] Add `frontend/src/lib/env.ts` as the single frontend environment entry point for `VITE_API_BASE_URL`.
- [x] Ensure secrets and real provider credentials are never committed.

### File storage

- [x] Create a small local file-storage component for original uploads.
- [ ] Enforce one file per upload, PDF/PNG/JPEG media types, and the 4 MB limit at the HTTP boundary and in the service.
- [x] Validate content sufficiently to reject a renamed or unsupported file.
- [x] Generate safe internal filenames/IDs instead of trusting the client filename for paths.
- [x] Preserve the original upload unchanged for preview and independent VLM review.
- [x] Keep storage location configurable and outside the repository by default.
- [x] Define cleanup behavior for failed processing and explicit review deletion without deleting an unrelated file.

### SQLite repository

- [x] Add the minimum SQLAlchemy 2 models/tables needed for uploaded documents and reviews.
- [x] Persist normalized fields, raw/merged evidence needed by the UI, conflicts, policy issues, GL suggestion, GL selection, review state, action metadata, and provider metadata.
- [x] Persist the normalized duplicate key used for invoice duplicate detection.
- [x] Keep all SQLite reads/writes in `repository.py`; do not access the database from routes or provider adapters.
- [x] Initialize the local database safely for a fresh checkout.
- [x] Support list, detail, action update, and explicit deletion operations.
- [x] Ensure a deleted local review no longer participates in duplicate detection and can be uploaded again.

## 4. Implement the primary PaddleOCR adapter

- [x] Create the PaddleOCR provider adapter under `backend/app/providers/`.
- [x] Integrate PP-StructureV3 as the default primary parser for OCR, layout, tables, page assets, bounding boxes, and confidence values.
- [x] Keep PaddleOCR raw response types and package-specific errors inside the adapter.
- [x] Map OCR/layout output into the normalized invoice/receipt extraction contract.
- [x] Handle multilingual English, Dutch, German, and French labels in the deterministic mapper.
- [x] Pass PDF files directly to PP-StructureV3 and aggregate its page results inside the provider adapter; render only when a later provider requires images.
- [x] Preserve page numbers and bounding-box/text context where available for evidence display.
- [x] Preserve primary confidence per field and expose it to the domain.
- [ ] Add PaddleOCR-VL only as an approved, evaluated option for difficult multilingual layouts; do not make it a second untracked business-rules path.
- [x] Document the CPU smoke test using the locked environment and the matching NVIDIA GPU alternative.
- [x] Verify PP-StructureV3 against fictional invoice, receipt, and two-page PDF samples before wiring the full workflow.

## 5. Implement the independent Qwen VLM adapters

### Document classification

- [x] Add a small structured Qwen classifier for the original upload that reuses `DocumentType` and returns the document kind, bounded confidence, and concise reasoning.
- [x] Validate the classifier response with Pydantic before routing invoice/receipt review or extraction.
- [x] Keep classification separate from VAT, finance policy, GL selection, and approval decisions; record its provider/model metadata.
- [ ] Keep the PaddleOCR marker-based classifier as an explicit diagnostic/fallback path and surface disagreements instead of silently changing the document type.

### Document review and extraction

- [x] Create the document-review adapter under `backend/app/providers/`.
- [x] Send the same original PDF/PNG/JPEG to the independent review path; do not send only the primary parser's already-extracted values.
- [x] Render PDF pages to images inside the provider boundary when the selected local endpoint requires images.
- [x] Use Qwen2.5-VL-7B-Instruct as the initial model; consider a newer Qwen-VL checkpoint only after it passes the fictional corpus evaluation.
- [x] Support Ollama for local development and vLLM's OpenAI-compatible endpoint for GPU-backed serving.
- [x] Constrain every response with the shared structured schema/JSON Schema.
- [x] Validate every response with Pydantic before it reaches normalization or merge logic.
- [x] Add a small bounded retry path for invalid structured output and return a clear provider failure when the bound is exhausted.
- [x] Record the model/runtime/prompt/schema metadata for every response.
- [x] Keep VLM confidence and extracted values as evidence, not as policy decisions.

### GL suggestion

- [x] Create a separate GL suggestion adapter method that receives normalized invoice/receipt fields only.
- [x] Pass the fixed Northstar catalog as the allowed suggestion context.
- [x] Require structured output containing a suggested account ID, short rationale, and confidence.
- [x] Reject or safely display suggestions that do not map to a catalog account.
- [x] Never allow model text to create a new account or change the catalog.

### Correction-email draft

- [x] Create an on-demand correction-draft adapter method.
- [x] Provide only the normalized review, blocking issues, and relevant evidence needed to write a clear supplier correction request.
- [x] Request concise professional English addressed to the supplier; do not claim that VIES was checked.
- [x] Return copyable draft text only.
- [x] Ensure the adapter has no email-sending capability or integration.

## 6. Normalize, merge, and preserve provenance

- [x] Add a deterministic normalization step for provider-independent dates, decimals, currency, VAT IDs, whitespace, and empty values.
- [x] Normalize decimal separators and common multilingual labels without changing the original evidence.
- [x] Merge the primary and VLM results deterministically.
- [x] Keep a primary value whenever it exists, even when the VLM proposes a different value.
- [x] Use a VLM value only to fill a missing primary field.
- [x] Record fallback provenance for every field filled by the VLM.
- [x] Record both values and a visible conflict for every primary/VLM disagreement.
- [x] Do not let the VLM replace primary values, validate VAT, calculate approval, or invent missing business facts.
- [x] Keep the merge logic independent from HTTP, SQLite, and provider SDK types.
- [x] Add one small runnable assert-based self-check for merge precedence, missing-field fallback, and conflict recording.
- [x] Verify multi-page invoices are merged into one normalized review without changing the original page count.

## 7. Implement deterministic VAT and finance validation

### VAT checks

- [x] Add local EU VAT structure and checksum validation with the approved `python-stdnum` dependency.
- [x] Normalize country prefixes and spacing before validation while retaining a review-friendly display value.
- [x] Validate supplier VAT IDs for invoices and distinguish missing from malformed/invalid values.
- [x] Require the Northstar customer VAT ID on invoices and flag a missing or mismatched value.
- [x] Do not make a live VIES registration claim or add a VIES network dependency.
- [x] Reconcile receipt VAT and totals locally when the necessary values are present.

### Invoice policy

- [x] Make the invoice policy a pure function in `backend/app/invoices/validation.py`.
- [x] Produce blocking errors for:
  - [x] missing vendor identity;
  - [x] missing vendor VAT ID;
  - [x] malformed/invalid vendor VAT ID;
  - [x] missing customer identity;
  - [x] missing customer VAT ID;
  - [x] mismatched customer VAT ID;
  - [x] missing invoice number;
  - [x] missing invoice date;
  - [x] missing invoice total;
  - [x] missing currency;
  - [x] non-positive total;
  - [x] invalid invoice/due-date order;
  - [x] total mismatch greater than EUR 0.01;
  - [x] duplicate vendor/invoice key.
- [x] Produce warnings for missing purchase order and primary-extraction confidence below `0.80`.
- [x] Keep the EUR 0.01 tolerance deterministic and use exact decimal arithmetic.

### Receipt policy

- [x] Make the receipt policy separate from the invoice policy and keep it pure.
- [x] Require merchant, transaction date, currency, positive total, and VAT total.
- [x] Do not require invoice number, customer VAT, purchase order, or due date for receipts.
- [x] When subtotal and VAT are present, require reconciliation to total within EUR 0.01.
- [x] Turn low primary confidence into a warning.
- [x] Define the receipt expense category as review data and ensure it does not bypass GL selection validation.

### Approval gate

- [x] Combine deterministic document issues with GL selection validation into one approval decision.
- [x] Disable/deny approval when any blocking issue remains.
- [x] Require a valid selected Northstar GL account even when extraction and policy checks pass.
- [x] Allow warnings to remain visible without blocking approval.
- [x] Ensure approval is a human action after the evidence and uncertainty are visible.
- [x] Add an assert-based self-check covering the invoice and receipt policy edge cases without introducing a test suite.

## 8. Build the fixed Northstar GL catalog

- [x] Define a small fixed catalog for Northstar's facilities-management purchasing and expense categories.
- [x] Cover the brief's supplier areas: cleaning, maintenance, electrical, plumbing, and equipment.
- [x] Cover the fuel receipt scenario and any other receipt categories needed by the fictional corpus.
- [x] Give every account a stable ID and human-readable label.
- [x] Keep the catalog and selection validation in `backend/app/accounting/`.
- [x] Expose catalog entries to the UI through a backend endpoint or review payload.
- [x] Validate selected IDs against the fixed catalog on the server.
- [x] Allow Maya to override the local VLM suggestion.
- [x] Store both the suggestion and the final human selection.

## 9. Orchestrate the review workflow

- [ ] Add `service.py` to orchestrate upload, provider calls, normalization, merge, validation, GL suggestion, and persistence.
- [ ] Keep the orchestration synchronous and local; do not introduce queues, workers, or batch processing.
- [ ] Define the order clearly: save original → document classification → primary parse → independent VLM review → deterministic merge → policy checks → GL suggestion → persist review.
- [ ] Ensure provider failures produce a recoverable failed state and an actionable user-facing message.
- [ ] Keep partial provider results available when safe, without presenting an incomplete review as approved.
- [ ] Avoid logging uploaded content, provider secrets, or full sensitive document text unnecessarily.
- [ ] Ensure repeated processing after explicit deletion starts from a clean review record.

## 10. Expose the minimal FastAPI API

- [ ] Keep `GET /health` working.
- [ ] Add an upload endpoint that validates file count, media type, size, and creates a review/document record.
- [ ] Add a process endpoint that runs the local pipeline and returns the review state/result.
- [ ] Add a review-history endpoint with compact status, document type, supplier/merchant, date, total, and blocking-state summary.
- [ ] Add a review-detail endpoint containing normalized fields, evidence, provenance, conflicts, policy issues, GL suggestion/selection, and original-file metadata.
- [ ] Add an approval endpoint that rechecks the approval gate server-side before changing state.
- [ ] Add a rejection endpoint and persist the decision.
- [ ] Add a correction-request action that records the request without sending email.
- [ ] Add an on-demand correction-email-draft endpoint.
- [ ] Add an explicit local deletion endpoint for review history and stored original data.
- [ ] Add a GL-catalog endpoint or include the catalog in a stable API response.
- [ ] Use Pydantic request/response models and return consistent validation/provider errors.
- [ ] Keep routes thin: no provider calls, SQLAlchemy queries, or business-policy branches directly in route handlers.
- [ ] Confirm the frontend can use the API without CORS or environment surprises in local development.

## 11. Build the React review experience

### Welcome and upload

- [ ] Replace the starter screen with a guided welcome state explaining the Northstar workflow.
- [ ] Add a single-file upload control with PDF/PNG/JPEG and 4 MB guidance.
- [ ] Show client-side validation errors before upload and server-side errors after upload.
- [ ] Show a preview of the original uploaded document before processing.

### Processing

- [ ] Show a clear processing state while the primary parser, VLM review, merge, validation, and GL suggestion run.
- [ ] Make provider failure and incomplete-result states understandable and recoverable.
- [ ] Do not imply that an external email, VIES lookup, or background worker ran.

### Review

- [ ] Show invoice and receipt fields with document-type-specific labels.
- [ ] Show supplier/customer information, IDs, dates, PO, currency, and totals for invoices.
- [ ] Show merchant, transaction date, expense category, subtotal, VAT, and total for receipts.
- [ ] Show field provenance and confidence, including primary, VLM fallback, and conflict states.
- [ ] Make conflicts visible with both candidate values and enough evidence context for Maya to decide.
- [ ] Show blocking errors separately from warnings and explain the action needed.
- [ ] Show the original document beside or alongside the extracted review where the layout permits.
- [ ] Add a fixed-catalog GL selector, clearly marking the VLM suggestion and allowing an override.
- [ ] Disable approval until policy errors are resolved and a valid GL account is selected.
- [ ] Provide approve and reject actions with clear confirmation/state feedback.
- [ ] Provide a request-correction action that opens the draft flow.

### Correction draft and history

- [ ] Generate the correction draft only when requested.
- [ ] Show the draft in a modal/panel with Copy and Close actions.
- [ ] Use the browser clipboard API for Copy and show success/failure feedback.
- [ ] Make it explicit that the app never sends the draft.
- [ ] Add review history with statuses and enough summary data to reopen a review.
- [ ] Add explicit delete confirmation and refresh the history after deletion.
- [ ] Make it possible to upload the same fictional invoice again after deletion.

### Frontend quality

- [ ] Keep TypeScript strict and route all environment access through `frontend/src/lib/env.ts`.
- [ ] Use semantic controls, labels, keyboard navigation, visible focus, readable error states, and accessible status announcements.
- [ ] Cover empty, uploading, processing, ready, blocked, warning-only, approved, rejected, correction-requested, failed, and deleted/reloaded states.
- [ ] Keep the UI focused on the review decision; do not add dashboards or unrelated settings.

## 12. Evaluate the fictional corpus

- [ ] Treat `samples/manifest.json` as the source of expected normalized fields and issue codes.
- [ ] Verify the corpus remains 13 documents and 14 pages: 12 invoices plus one Dutch fuel receipt.
- [ ] Create/update an explicit evaluator script that continues after an individual provider failure and reports per-document results.
- [ ] Compare normalized values rather than only raw OCR text.
- [ ] Evaluate provider invoice/receipt classification, including confidence, disagreements, and failure behavior; do not treat manifest labels alone as provider classification.
- [x] Add a playground Pydantic smoke check for the golden corpus's invoice/receipt labels; this does not replace provider classification.
- [ ] Evaluate supplier/customer names and VAT IDs.
- [ ] Evaluate invoice/transaction dates, due date, invoice number, PO, currency, subtotal, VAT, and total.
- [ ] Evaluate policy issue codes and approval/warning outcomes.
- [ ] Evaluate provenance: primary fields, VLM fallbacks, conflicts, and primary confidence.
- [ ] Evaluate GL suggestions against the fixed catalog without treating a suggestion as a final selection.
- [ ] Cover the committed scenarios:
  - [ ] `01-en-happy-classic.pdf`: English happy-path invoice.
  - [ ] `02-nl-happy-compact.pdf`: Dutch happy-path invoice.
  - [ ] `03-de-happy-modern.pdf`: German happy-path invoice.
  - [ ] `04-fr-happy-classic.pdf`: French happy-path invoice.
  - [ ] `05-nl-missing-vendor-vat.pdf`: missing supplier VAT blocking error.
  - [ ] `06-de-invalid-vendor-vat.pdf`: invalid supplier VAT blocking error.
  - [ ] `07-fr-wrong-customer-vat.pdf`: customer VAT mismatch blocking error.
  - [ ] `08-en-total-mismatch.pdf`: invoice total mismatch blocking error.
  - [ ] `09-nl-missing-po.pdf`: missing PO warning.
  - [ ] `10-de-duplicate.pdf`: duplicate vendor/invoice blocking error.
  - [ ] `11-fr-scan-quality.png`: scan-quality confidence warning behavior.
  - [ ] `12-en-two-page.pdf`: multi-page invoice handling.
  - [ ] `13-nl-fuel-receipt.png`: receipt-specific policy and fuel category handling.
- [ ] Add a hybrid evaluator for representative documents to report primary fields, VLM fallbacks, conflicts, final status, and provider call counts.
- [ ] Record machine, device, runtime, model name/version, prompt/schema versions, duration, and peak resource observations for comparisons.
- [ ] Compare at least the approved PP-StructureV3/Qwen configuration and any proposed PaddleOCR-VL or newer Qwen configuration before changing defaults.
- [ ] Check model licenses and transitive runtime licenses before any commercial deployment decision.
- [ ] Do not add external/private documents or scraped data to the repository.

## 13. Verification and manual walkthrough

- [ ] Run backend Ruff with the locked environment.
- [ ] Run frontend TypeScript build/type-check, ESLint, and production build.
- [x] Run the local provider smoke test against a fictional invoice.
- [ ] Run the corpus evaluator when local providers are available.
- [ ] Verify the health endpoint and starter/build application locally.
- [ ] Manually walk through the complete browser story:
  - [ ] welcome → upload/preview;
  - [ ] valid invoice → process → review → select GL → approve;
  - [ ] missing/invalid data → blocking issue visible → approval prevented;
  - [ ] missing PO/low confidence → warning visible;
  - [ ] receipt → receipt policy instead of invoice policy;
  - [ ] primary/VLM disagreement → conflict and provenance visible;
  - [ ] correction draft → Copy → Close, with no send action;
  - [ ] history → delete → upload the same sample again.
- [ ] Check that no provider request occurs on the starter checkpoint before processing is invoked.
- [ ] Confirm model weights, caches, uploads, `.env`, and SQLite files are ignored and absent from the commit.

## 14. Keep the teaching documentation current

- [ ] Update `docs/build-along.md` in the same commit as each working slice.
- [ ] For every slice, record the outcome, why the boundary exists, exact commands, observable result, and checkpoint.
- [ ] Document provider installation only after the direct versions are approved and locked.
- [ ] Document the difference between primary extraction, independent VLM review, deterministic policy, and human approval.
- [ ] Document the no-live-VIES limitation and the no-send correction-draft behavior.
- [ ] Keep the README, environment examples, architecture document, pricing notes, and provider alternatives consistent with the implemented local stack.
- [ ] Add final run instructions for a fresh checkout without exposing secrets or requiring private documents.

## Explicitly not planned

- [ ] No user authentication or authorization.
- [ ] No asynchronous job queue, worker fleet, scheduler, or batch upload.
- [ ] No deployment, hosted database, managed object storage, or production operations work.
- [ ] No email ingestion, SMTP/provider integration, or automatic email sending.
- [ ] No live VIES registration lookup.
- [ ] No accounting/ERP integration or automatic posting to bookkeeping.
- [ ] No metered Azure dependency in the local-provider build unless the project brief is deliberately changed first.
