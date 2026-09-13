# LinkedIn post — Invoice Review

I built a local-first invoice review application to explore a practical question:

**How can AI make finance document review faster without taking accounting decisions away from people?**

The project is based on a fictional company, Northstar Facilities B.V., an Amsterdam-based facilities-management business. Its finance team receives invoices and expense receipts as PDFs, scans, screenshots, and phone photos—often in English, Dutch, German, or French.

The application gives a finance administrator one guided workflow to:

- upload and preview an invoice or receipt;
- extract normalized supplier, customer, VAT, date, currency, and total fields;
- see evidence, confidence, and conflicts between extraction sources;
- validate VAT formats and financial rules locally;
- review a suggested General Ledger account and override it when needed;
- approve, reject, or request a supplier correction; and
- generate a correction-email draft that can be copied, but is never sent by the app.

The most important design decision was separating **extraction from policy**. PaddleOCR is the primary parser, while a local Qwen vision-language model independently reviews the original document. A deterministic merge keeps primary values authoritative and lets the VLM fill only missing fields. Conflicts remain visible instead of being silently overwritten.

The finance rules are ordinary, inspectable Python: required-field checks, offline EU VAT format and checksum validation, total reconciliation, duplicate invoice detection, receipt-specific rules, and approval eligibility. The model can suggest a GL account, but it cannot define the catalog or approve a document. The final decision stays with the reviewer.

## Tech stack

- **Backend:** Python 3.12+, FastAPI, Pydantic v2, SQLAlchemy 2, SQLite, and `uv`
- **Document intelligence:** PaddleOCR PP-StructureV3 for OCR, layout, tables, bounding boxes, and confidence; PaddleOCR-VL is available for difficult multilingual layouts
- **Independent review:** Qwen2.5-VL through Ollama for local development or vLLM for GPU-backed serving
- **Frontend:** Vite, React, strict TypeScript, Tailwind CSS, and accessible shadcn/ui primitives
- **Storage and validation:** local original-file storage, exact decimal money values, and `python-stdnum` for offline EU VAT validation
- **Verification:** Ruff, TypeScript, ESLint, production builds, fictional corpus evaluation, and a manual browser walkthrough

This project has been a useful reminder that reliable AI features are not only about choosing a capable model. They also need clear boundaries, structured outputs, deterministic business rules, provenance, recoverable failures, and a human-friendly review experience.

The result is intentionally local and self-contained: no uploaded documents leave the application, there is no live VIES lookup, and the correction draft is never sent automatically. It is a fictional end-to-end project, but the engineering questions are very real.

#AI #OCR #AccountingAutomation #Python #React
