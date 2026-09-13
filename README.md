# Invoice Review

Invoice Review is a local, end-to-end workspace for reviewing invoices and
expense receipts. It is built around a fictional facilities company,
Northstar Facilities B.V., and combines document parsing, independent model
review, deterministic finance rules, and a human approval step.

The project is also a guided build-along:

- [Online tutorial](https://learn.datalumina.com/docs/invoice-review)
- [Client brief](docs/client-brief.md)
- [Target architecture](docs/architecture.md)
- [Build-along checkpoints](docs/build-along.md)

> Northstar and all sample documents are fictional. The app does not query
> VIES, send email, or call a metered cloud OCR/VLM API.

## What the application does

1. Upload one PDF, PNG, or JPEG document up to 4 MB.
2. Classify it as an invoice or receipt.
3. Parse the original document with PaddleOCR PP-StructureV3.
4. Review the same original file independently with a local Qwen VLM.
5. Merge the results while preserving primary-parser values, filling only
   missing fields from the VLM, and exposing provenance and conflicts.
6. Apply deterministic VAT, total, date, duplicate, and document-specific
   policy checks.
7. Suggest an account from the fixed Northstar GL catalog and let a reviewer
   override it.
8. Approve, reject, or request a supplier correction from the review screen.
9. Generate a copyable correction-email draft on demand; the app never sends
   it.

Review history, original-file preview, explicit deletion, and re-upload are
included so the same fictional document can be demonstrated repeatedly.

## Technology and boundaries

- **Frontend:** Vite, React, TypeScript, and Tailwind CSS
- **Backend:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy, and SQLite
- **Primary parser:** PaddleOCR PP-StructureV3; PaddleOCR-VL is an optional
  path for difficult multilingual layouts
- **Independent reviewer:** Qwen2.5-VL-7B-Instruct, or a newer Qwen-VL model
  after it passes the fictional corpus evaluation
- **Local runtimes:** Ollama for development or vLLM for GPU-backed serving
- **Storage:** SQLite plus local files under `~/.invoice-review` by default

Provider-specific types stay inside `backend/app/providers/`. The rest of the
application works with normalized document models, evidence, and metadata.
Finance rules live in a pure policy module, while HTTP, orchestration, and
SQLite access remain in their own layers.

## Requirements

- Python 3.12 or newer
- [uv](https://docs.astral.sh/uv/)
- Node.js 22 or newer
- pnpm 11
- A local Qwen-compatible endpoint for processing documents
- CPU works for a smoke test; a compatible NVIDIA GPU is recommended for
  repeated corpus evaluations

## Install

From the repository root:

```bash
cd backend
uv sync --locked

cd ../frontend
pnpm install --frozen-lockfile
```

Create local environment files when you want to customize the defaults:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

The default provider settings use Ollama at
`http://localhost:11434/v1` with `qwen2.5vl:7b` and run PaddleOCR on the CPU.
Use the environment examples as the starting point for an Ollama or vLLM
setup. Keep model weights, provider caches, uploaded documents, and SQLite
runtime data outside Git.

## Run locally

The supervisor checks the existing locked environments and starts both
services:

```bash
./scripts/dev.sh --check
./scripts/dev.sh
```

Then open [http://localhost:5173](http://localhost:5173). The API is available
at [http://localhost:8000/health](http://localhost:8000/health).

The UI and health check do not initialize PaddleOCR or Qwen. Uploading a file
works without a running model, but processing requires the local parser setup
and a reachable Qwen endpoint.

## Verify

Run the static checks with the locked environments:

```bash
cd backend
uv run --locked --no-sync ruff check app ../playground

cd ../frontend
pnpm exec tsc -b --pretty false
pnpm lint
pnpm build
```

Validate the fictional manifest before a provider run:

```bash
cd backend
PYTHONPATH=. uv run --locked --no-sync python ../playground/check_document_types.py
```

To evaluate the complete local pipeline, start the configured Qwen endpoint
and run the corpus evaluator from the same host/network context:

```bash
cd backend
PYTHONPATH=. uv run --locked --no-sync python ../playground/evaluate_corpus.py
```

Use `--only FILENAME` for a representative subset. The evaluator stores
runtime data in a temporary directory and exits non-zero when the strict
manifest expectations are not met. See [samples/README.md](samples/README.md)
for the full corpus workflow and endpoint notes.

## Fictional corpus

The corpus contains 13 documents across English, Dutch, German, and French:
12 invoices and one imperfect Dutch fuel receipt. The manifest records the
expected document type, normalized fields, issue codes, and page counts.

Sample documents are test data only. Their VAT values are fictional checksum
examples, not live business registrations.

## Branches

- `main` is the prepared starter for following the tutorial.
- `development` contains the public working implementation.
- `solution` is the reviewed reference branch when available.

## Further reading

- [Open-source provider alternatives](docs/open-source-alternatives.md)
- [Local pricing and resource costs](docs/pricing.md)
- [Sample corpus guide](samples/README.md)
