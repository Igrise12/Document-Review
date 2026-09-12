# Fictional corpus

The repository contains 12 fictional invoices and one Dutch fuel receipt in English, Dutch, German, and French. `manifest.json` is the evaluation oracle for document type, normalized fields, expected issue codes, and page counts. VAT values are fictional checksum examples and are never presented as verified business registrations.

Validate the manifest contract:

```bash
cd backend
PYTHONPATH=. UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  uv run --locked --no-sync python ../playground/check_document_types.py
```

Evaluate the complete local PaddleOCR and Qwen pipeline:

```bash
PYTHONPATH=. UV_CACHE_DIR=/tmp/invoice-review-uv-cache \
  LOCAL_VLM_BASE_URL=http://localhost:7869/v1 LOCAL_VLM_MODEL=qwen3.5:9b \
  uv run --locked --no-sync python ../playground/evaluate_corpus.py
```

Run this command from the same host/network context as the local Qwen endpoint. A restricted Codex sandbox has its own `localhost`, so it cannot reach a Podman service bound to the host loopback; verify access first with `curl http://localhost:7869/v1/models`. The evaluator processes the manifest in order, compares normalized values, reports provenance and provider metadata, continues after individual failures, and exits non-zero when the strict manifest gate fails. Use `--only FILENAME` repeatedly for a representative subset; all runtime data is written to a temporary directory outside the repository.

The committed set contains eleven PDFs and two PNG images. Keep model weights, provider caches, uploaded documents, and SQLite data outside Git.
