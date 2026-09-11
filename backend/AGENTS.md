# Backend agent instructions

Read [../AGENTS.md](../AGENTS.md) first. The root file contains the project-wide product boundaries, dependency policy, teaching rules, and verification policy. This file adds backend-specific conventions.

## Stack

- Python 3.12 or newer.
- `uv` for dependency and project management.
- FastAPI and uvicorn for the HTTP service.
- Pydantic v2 and pydantic-settings for typed boundaries and provider settings.
- SQLAlchemy 2 with local SQLite persistence.
- PaddleOCR behind the primary document-parser adapter.
- A local Qwen VLM behind the reviewer/generation adapter, served by Ollama for development or vLLM for GPU-backed serving.
- Ruff for linting and import/style checks.

The stack is locked unless Dave explicitly approves a change.

## Layout

The current checkpoint contains configuration, persistence, provider adapters, deterministic reconciliation and policy, synchronous workflow orchestration, and the minimal review API. Continue adding workflow code using these boundaries:

```text
backend/
├── app/
│   ├── main.py              # FastAPI construction and dependency wiring
│   ├── config.py            # Provider settings and fixed application config
│   ├── invoices/            # HTTP, service orchestration, persistence, and policy by module
│   ├── accounting/          # Fixed GL catalog and validated selections
│   ├── document_review/     # Provider-independent review, normalization, and reconciliation
│   ├── correction_email/    # Eligibility and provider-independent draft models
│   └── providers/           # PaddleOCR and local VLM adapters; raw SDK/runtime types stop here
├── scripts/                 # Explicit provider checks and corpus evaluations
├── pyproject.toml
└── uv.lock
```

Do not create empty architectural layers before the tutorial reaches them.

## Boundaries and code style

- Routes own HTTP parsing, response models, and status-code translation.
- Services orchestrate the user workflow and depend on explicit interfaces.
- Repositories own SQLAlchemy and SQLite access.
- Provider adapters are the only modules allowed to expose third-party SDK and runtime types.
- `backend/app/providers/paddleocr.py` is the only module allowed to import PaddleOCR, inspect its result payloads, or raise package-specific provider errors. Only `PrimaryExtractionResult` and other provider-independent Pydantic models may cross into the domain.
- `backend/app/document_review/reconciliation.py` owns typed normalization and primary/VLM merging. Keep it pure and provider-independent: primary values remain authoritative, VLM values fill only missing fields, and disagreements preserve both candidates as conflicts.
- Deterministic validation and reconciliation remain separate from AI extraction or generation.
- Keep public functions typed and modules focused. Prefer dataclasses, enums, `pathlib`, and other standard-library capabilities over helper packages.
- Validate files, HTTP input, provider output, and database writes at their boundaries. Do not repeatedly validate trusted internal calls.
- PaddleOCR parsing and SQLite access are synchronous. Keep parser execution out of `/health`; the health route must not instantiate a model or download weights. Use normal FastAPI `def` handlers for synchronous request paths instead of blocking an async event loop.
- Do not add auth, queues, workers, caching, analytics, deployment code, or accounting integrations unless the user story changes.

## Stage 9 workflow

- `backend/app/invoices/service.py` owns the synchronous single-document workflow. Construct it with the repository, local file storage, and lazy primary/VLM provider factories; keep routes as callers, not orchestrators.
- `upload_document()` validates and stores the original before creating the uploaded review record. If record creation fails, remove the newly stored file.
- `process_review()` accepts only `uploaded` or retryable `failed` reviews, clears stale processing payloads, and runs: classification → primary parse → type reconciliation → original-document VLM review → deterministic merge → policy validation → GL suggestion → persistence.
- Require Qwen classification and PaddleOCR document types to agree before VLM extraction. A disagreement becomes the blocking `document_type_conflict` issue and a recoverable `failed` review.
- Persist safe partial normalized data, evidence, issues, and provider metadata when a later provider fails. A partial result stays `failed`; only the complete pipeline becomes `ready_for_review`. GL suggestion failure also remains retryable `failed`.
- Keep provider run metadata structured and omit uploaded content, secrets, and full document text from logs and failure messages.
- Keep provider factories lazy and cached. App construction, `/health`, upload, history, detail, and original-file reads must not load PaddleOCR or create the Qwen client.

## Stage 10 minimal API

- Keep the unversioned local contract small: `POST /reviews`; `GET /reviews`; `GET /reviews/{id}`; `GET /reviews/{id}/original`; `POST /reviews/{id}/process`; `PUT /reviews/{id}/gl-selection`; `POST /reviews/{id}/approve`; `POST /reviews/{id}/reject`; `POST /reviews/{id}/correction-request`; `POST /reviews/{id}/correction-draft`; `DELETE /reviews/{id}`; and `GET /gl-catalog`.
- `POST /reviews` accepts multipart field `file` and rejects zero or multiple files, empty content, unsupported media types, false file signatures, and content over 4 MB. The service/storage boundary validates the bytes again.
- History responses stay compact. Detail responses expose normalized fields, evidence, conflicts, issues, GL review data, provider/action metadata, approval eligibility, and safe original-file metadata. Never expose storage keys or duplicate keys.
- Original-file responses use the persisted media type and exact bytes for the Stage 11 preview. Resolve the storage key through the service/repository; never accept it from the client.
- GL selection, approval, rejection, and correction request are allowed only from `ready_for_review`. Approval always reruns the deterministic approval gate. Correction request and draft require a blocking issue.
- Correction request records state only. Correction draft calls Qwen on demand, is not persisted, has Copy/Close consumers only, and must never send email.
- Record action kind and a UTC timestamp without claiming an actor identity; this local build has no authentication.
- Return handled errors as `{"error":{"code":"...","message":"..."}}`: 404 for missing reviews, 409 for invalid transitions or blocked actions, 422 for invalid requests/uploads/GL selections, and 502 for correction-draft provider failures. A pipeline provider failure that was safely persisted returns HTTP 200 with review state `failed`.
- Local CORS permits only `http://localhost:5173` and `http://127.0.0.1:5173`, the implemented methods, and `Content-Type`.

## Configuration

- `app/config.py` is the only backend configuration boundary.
- Local VLM base URL, model name, optional API key, PaddleOCR engine, and device are read through its Pydantic `Settings` model.
- Fixed tutorial policy belongs in its immutable application configuration, not environment variables.
- Never call `os.getenv`, read `os.environ`, or call `load_dotenv` in application modules or scripts.
- Fail clearly when required local provider configuration is absent. Do not hide configuration failures behind silent fallbacks.
- Never commit `.env`, provider credentials, uploaded documents, SQLite databases, model weights, or generated runtime data.

## Dependencies

- Never add a dependency without Dave's explicit approval.
- Use exact direct versions and commit `uv.lock` with every approved dependency change.
- Keep `add-bounds = "exact"` and `exclude-newer = "7 days"` under `[tool.uv]`.
- Keep `paddleocr[doc-parser]==3.7.0` and `paddlepaddle==3.2.0` exact-pinned. PaddlePaddle is resolved through the explicit CPU index; the package-scoped cooldown exception is approved only for this exact dependency.
- Install with `uv sync --locked`.
- Commands that must use the existing environment run through `uv run --locked --no-sync`.
- Prefer a small local function when a dependency would only replace a few clear standard-library lines.

## Verification

Verify the current backend checkpoint with:

```bash
uv sync --locked
PYTHONPATH=. uv run --locked --no-sync python ../playground/check_paddleocr.py
PYTHONPATH=. uv run --locked --no-sync python ../playground/check_qwen.py
PYTHONPATH=. uv run --locked --no-sync python ../playground/check_reconciliation.py
PYTHONPATH=. uv run --locked --no-sync python ../playground/check_service.py
PYTHONPATH=. uv run --locked --no-sync python ../playground/check_api.py
uv run --locked --no-sync ruff check app ../playground
```

If the default uv cache is read-only, set `UV_CACHE_DIR=/tmp/invoice-review-uv-cache` on each command. The API check opens an ephemeral loopback port and uses fictional provider doubles; it makes no external network or model calls. The provider smoke check uses fictional invoice, receipt, and two-page PDF samples and the external model cache; it does not write provider output to the repository.

Provider checks and corpus evaluations consume local compute and model-cache storage. Document the runtime, exact model version, expected calls, hardware, and cleanup command before running them. Complete verification also includes startup readiness and the manual end-to-end workflow.

Do not add `tests/`, `pytest`, or committed automated test files. This weekly teaching project uses linting, explicit provider/corpus checks, and manual workflow verification as defined by the root instructions.
