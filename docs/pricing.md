# Pricing

Invoice Review uses local open-source components rather than metered Azure services. The application has no per-document OCR or VLM API charge when PaddleOCR and Qwen run on the developer's machine or an organisation-controlled GPU server.

## Cost of this local setup

| Component | Local cost model | Usage in this project |
| --- | --- | --- |
| PaddleOCR PP-StructureV3 / PaddleOCR-VL | No per-call fee; consumes CPU/GPU, RAM, and model-cache storage | One primary parse per uploaded document |
| Qwen2.5-VL | No per-call fee; consumes CPU/GPU, RAM, and model-cache storage | One independent review per uploaded document |
| Ollama | Local runtime; no per-call fee | Recommended for development |
| vLLM | Local server; no per-call fee | Optional GPU-backed serving runtime |
| FastAPI, React, SQLite, uploaded files | Local disk and machine resources | Application runtime and review history |
| Hosting, managed database, object storage | Not deployed | €0 in the starter |

The real cost depends on the selected hardware, electricity, storage, concurrency, and model size. Keep model weights, caches, uploaded invoices, and SQLite runtime data outside the repository. Check the license of each selected model checkpoint and transitive runtime dependency before commercial deployment.

## Cost of one extraction evaluation

The fictional corpus contains 13 documents and 14 pages:

```bash
jq '{documents: length, pages: ([.[].pages] | add)}' samples/manifest.json
```

Expected:

```json
{
  "documents": 13,
  "pages": 14
}
```

Running the complete local workflow performs, per document:

1. One PaddleOCR primary parse.
2. One Qwen VLM independent review.
3. One local Qwen GL suggestion using normalized fields.
4. No correction-email generation unless explicitly requested.

The evaluation therefore has no token-meter or page-meter charge. Its measurable cost is elapsed time and machine resource usage. Record the machine, runtime, model name, model version, and total duration when comparing provider configurations.

## Optional correction-email cost

The correction-email draft is generated locally only when a reviewer requests it. It has no external email-provider or per-token charge. The call returns copyable text only; it never sends an email.

## What to benchmark

Cost alone is not enough for this workflow. Compare each local configuration on:

- supplier and customer VAT ID accuracy;
- decimal separator, date, currency, subtotal, VAT, and total accuracy;
- invoice versus receipt classification;
- primary-parser confidence and field provenance;
- end-to-end latency and peak memory use;
- failure behavior when a PDF is multi-page, rotated, blurred, or missing a field.

Use the fictional corpus before selecting a default model or runtime. A newer model is not adopted automatically; it must preserve the deterministic merge, VAT checks, policy rules, and human approval boundary.
