# Client brief

## The company

Northstar Facilities B.V. is a fictional facilities-management company based in Amsterdam. It buys cleaning, maintenance, electrical, plumbing, and equipment services from suppliers across the European Union.

Maya works in finance and administration. Supplier invoices and employee expense receipts arrive as digital PDFs, scans, screenshots, and phone photos. They may be written in English, Dutch, German, or French. Before a document enters bookkeeping, Maya needs to know what it is, confirm the important values, check VAT and totals, and assign the correct account.

All product copy, source code, documentation, and teaching content is English. Only the example supplier documents vary in language.

## User story

> As a finance administrator at a European company, I want to upload a multilingual invoice or receipt and receive a prepared review containing the best combined extraction, VAT and policy results, and a suggested GL account so I can approve valid documents quickly and turn supplier errors into a clear correction request.

## What's included in the build

- One PDF or image per upload, with a 4 MB limit.
- Automatic invoice/receipt recognition with strict local VLM output.
- Primary document parsing with PaddleOCR PP-StructureV3, with PaddleOCR-VL available for difficult multilingual layouts.
- An independent Qwen2.5-VL extraction of the same PDF/PNG/JPEG, served locally through Ollama during development or vLLM for a GPU-backed service.
- A deterministic merge that keeps primary parser values and fills only missing fields from the VLM, with visible provenance and conflicts.
- Invoice supplier/customer details and VAT IDs, dates, PO, currency, and totals.
- Receipt merchant, transaction date, expense category, subtotal, VAT, and total.
- Offline EU invoice VAT format/checksum validation plus receipt VAT-total reconciliation.
- Separate deterministic invoice and receipt policies, duplicate detection, corrections, approval, and rejection.
- A fixed Northstar GL catalog plus a local VLM structured suggestion that a reviewer can override.
- SQLite, local file storage, and a guided welcome → upload/preview → process → review flow.
- Review history with explicit local deletion so the same invoice can be demonstrated again.
- An on-demand local VLM correction-email draft with Copy and Close; the app never sends it.
- A 13-document fictional multilingual corpus containing 12 invoices and one imperfect Dutch fuel receipt.

## Northstar policy

The Northstar policy is simply the fictional company's rulebook expressed as ordinary Python. It decides what must be fixed before approval; local providers extract evidence, but they do not own these rules.

### Invoice rules

Errors block approval: missing vendor/customer identity, missing or malformed supplier VAT, missing/mismatched customer VAT, missing invoice number/date/total/currency, non-positive total, invalid date order, total mismatch over EUR 0.01, and duplicate vendor/invoice keys. Missing PO and primary-extraction confidence below 0.80 are warnings.

### Receipt rules

A receipt records an expense that was already paid, so it does not need an invoice number, customer VAT, PO, or due date. Merchant, transaction date, currency, positive total, and VAT total are required. When subtotal and VAT are present, they must reconcile to the total within EUR 0.01. Low primary confidence is a warning.

A valid selected Northstar GL account is also required for approval. The model may suggest one, but Maya remains responsible for the selection.

The PaddleOCR parser stays primary. A VLM value can fill a missing field, but it cannot replace a conflicting primary value, validate VAT, or decide approval. Maya sees where every fallback came from.

## Local provider stack

- **Primary parser:** PaddleOCR PP-StructureV3 for OCR, layout, tables, bounding boxes, and confidence values. PaddleOCR-VL may be used when its multilingual document parsing is a better fit for a specific document.
- **Independent reviewer:** Qwen2.5-VL-7B-Instruct, or a newer Qwen-VL checkpoint only after it passes the fictional corpus evaluation.
- **Inference runtime:** Ollama for local development; vLLM for a GPU-backed OpenAI-compatible service.
- **Structured output:** every VLM response is constrained by the shared Pydantic schema and validated before it reaches the domain.

The local parser is not a drop-in replacement for Azure's pretrained invoice schema. A provider adapter must map OCR/layout evidence into the normalized invoice and receipt fields. PDF pages may be rendered to images inside the provider adapter before the independent VLM review; the original upload remains the source document.
