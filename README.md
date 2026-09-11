# Invoice Review

This is the clean starter for an end-to-end invoice and receipt review application. You will build a workflow for Northstar Facilities B.V. that combines local PaddleOCR and Qwen document review, deterministic finance rules, SQLite persistence, and a human review interface.

> You are on `main`, the learner starter. Active work is visible on `development`; the reviewed finished application is on `solution`.

Tutorial: <https://learn.datalumina.com/docs/invoice-review>

## What is included

- The client brief and target architecture
- A fictional 13-document multilingual corpus
- Safe environment templates
- Exact dependency pins and lockfiles
- Minimal FastAPI service, a Stage 4 PaddleOCR adapter, and a React checkpoint harness
- An install-free development supervisor and readiness check

The upload/process API and completed review workflow are intentionally absent. The tutorial builds the remaining workflow from this verified parser checkpoint.

## Prerequisites

- Python 3.12 or newer
- uv
- Node.js 22 or newer
- pnpm 11

## Local provider direction

- PaddleOCR PP-StructureV3 is the primary parser for OCR, layout, tables, boxes, and confidence.
- Qwen2.5-VL-7B-Instruct is the independent reviewer and generator.
- Ollama is the local development runtime; vLLM is the optional GPU-backed runtime.
- Model weights and caches belong outside this repository, for example Ollama's configured model directory or PaddleX's external model cache.
- CPU works for a smoke test but is slow; an NVIDIA GPU with matching PaddlePaddle and vLLM/Ollama support is recommended for repeated corpus runs.
- Local execution has no per-document API charge; it uses machine compute, storage, electricity, and model download time instead.

The approved CPU pins are `paddleocr[doc-parser]==3.7.0` and `paddlepaddle==3.2.0`; they are installed from the locked backend environment. GPU remains an alternative after a compatible NVIDIA driver/CUDA host and matching PaddlePaddle GPU wheel are available.

## Install

```bash
cd backend
uv sync --locked

cd ../frontend
pnpm install --frozen-lockfile
```

Copy `backend/.env.example` to `backend/.env` for later provider configuration, and copy `frontend/.env.example` to `frontend/.env` for local frontend configuration. The health/checkpoint UI does not call PaddleOCR or Qwen and does not require provider credentials.

## Run and verify the local checkpoint

```bash
cd backend
uv sync --locked

cd ../frontend
pnpm install --frozen-lockfile

cd ..
./scripts/dev.sh --check
./scripts/dev.sh
```

Open <http://localhost:5173>. The checkpoint UI checks the API health endpoint at <http://localhost:8000/health>, previews one local document, and clearly leaves processing for the next stage.

Run the real primary-parser smoke check:

```bash
cd backend
PYTHONPATH=. uv run --locked --no-sync python ../playground/check_paddleocr.py
```

For static verification:

```bash
cd backend
uv run --locked --no-sync ruff check app

cd ../frontend
pnpm exec tsc -b --pretty false
pnpm lint
pnpm build
```

## Choose a branch

- `main`: clone this branch to follow the tutorial from the prepared starting point.
- `development`: inspect the public working branch and later experiments.
- `solution`: inspect the reviewed end product.

To switch to the finished application:

```bash
git switch solution
```

Start with [the client brief](docs/client-brief.md), then follow the [complete tutorial](https://learn.datalumina.com/docs/invoice-review).
