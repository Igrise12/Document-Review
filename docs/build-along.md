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

When the provider stage begins, install PaddleOCR in a separate or approved locked environment. The CPU smoke-test setup is:

```bash
uv venv /tmp/invoice-paddleocr
source /tmp/invoice-paddleocr/bin/activate
uv pip install "paddlepaddle==3.2.0" \
  --index-url https://www.paddlepaddle.org.cn/packages/stable/cpu/
# Run only after Dave approves this exact direct package pin.
uv pip install "paddleocr[doc-parser]==3.7.0"
```

Verify the parser against a fictional invoice:

```bash
paddleocr pp_structurev3 \
  -i samples/generated/01-en-happy-classic.pdf \
  --engine paddle \
  --save_path /tmp/paddleocr-output
```

These commands are an isolated smoke test only. Once the provider is integrated, pin the approved direct versions in `backend/pyproject.toml` and commit the updated `backend/uv.lock`.

Use the matching `paddlepaddle-gpu` wheel for an NVIDIA setup. Then run a local Qwen2.5-VL model through Ollama for development or vLLM for GPU-backed serving. Keep model weights and runtime data outside the repository; do not commit them.

## Playground smoke test

The first PaddleOCR experiment lives in `playground/analyze_sample_invoice.py`. It is intentionally separate from the application provider adapter: the script is for inspecting raw PP-StructureV3 output, while production mapping will be promoted into `backend/app/providers/` after the output shape and corpus behavior are understood.

Run it from the isolated environment created above:

```bash
source /tmp/invoice-paddleocr/bin/activate
cd playground
python analyze_sample_invoice.py --device cpu
```

The default input is `samples/generated/01-en-happy-classic.pdf`. To inspect another fictional document or print the structured result to the terminal:

```bash
python analyze_sample_invoice.py samples/generated/13-nl-fuel-receipt.png --device cpu --print-results
```

The script writes PaddleOCR JSON and Markdown artifacts to `/tmp/paddleocr-output`. Use `--device gpu` or `--device gpu:0` when the isolated environment has a working NVIDIA setup. No uploaded document, model output, or model weight is written to the repository.

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

The proposed direct PaddleOCR pin is `paddleocr[doc-parser]==3.7.0` with `paddlepaddle==3.2.0` for the CPU smoke test. It remains pending Dave's approval, so stage 1 leaves `backend/pyproject.toml` and `backend/uv.lock` unchanged with respect to PaddleOCR.

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

Checkpoint: starter code and documentation are ready for provider implementation; run the two `scripts/dev.sh` commands again after freeing ports 8000 and 5173. Do not add PaddleOCR until the exact pin is approved.
