# Open-source alternatives to Azure

## Recommendation

For the current invoice-review brief, use a two-stage local pipeline:

1. **Primary document parsing:** PaddleOCR-VL 0.9B for multilingual document parsing, or PP-StructureV3 when layout/table output and OCR confidence are more important.
2. **Independent review, GL suggestion, and correction draft:** Qwen2.5-VL-7B-Instruct (or a newer Qwen3-VL checkpoint after corpus evaluation), served by Ollama for development and vLLM for a GPU-backed service.
3. **Business rules:** keep `python-stdnum`, deterministic VAT/total checks, merge logic, SQLite, and the human approval step unchanged.

This keeps the existing provider boundaries: only the provider adapters change. PaddleOCR should produce evidence, text/layout, boxes, and OCR confidence; the VLM should return the existing Pydantic schemas; neither model should own VAT validation or approval policy.

## Dependency gate

The proposed direct application dependency is `paddleocr[doc-parser]==3.7.0`, paired with `paddlepaddle==3.2.0` for the documented CPU smoke test. The package is not added to `backend/pyproject.toml` or `backend/uv.lock` until Dave approves the exact versions. See the [PaddleOCR package release](https://pypi.org/project/paddleocr/) before making that change.

## Mapping from the brief

| Azure responsibility | Local replacement | Important caveat |
| --- | --- | --- |
| `prebuilt-invoice` / `prebuilt-receipt` | PaddleOCR-VL or PP-StructureV3 plus a thin invoice/receipt field-mapping layer | This is document parsing, not an exact drop-in replacement for Azure's pretrained invoice schema. Validate against the fictional corpus. |
| Independent Azure OpenAI extraction | Qwen2.5-VL-7B or Qwen3-VL through Ollama/vLLM | Render PDF pages to images or pass the parser's page assets; validate every response with Pydantic. |
| Strict structured output | Ollama JSON Schema output or vLLM structured outputs | Keep retries and schema validation in the adapter. |
| GL categorization | Same local VLM, normalized fields only | The fixed GL catalog and selection validation remain application policy. |
| Correction-email draft | Same local text/VLM model | Draft only; never send. |

## Why this stack

PaddleOCR-VL is a compact 0.9B document parser with claimed support for 109 languages and complex elements such as tables; PP-StructureV3 exposes structured JSON/Markdown output, bounding boxes, and OCR confidence values. Those outputs fit the brief's provenance and conflict UI better than a single end-to-end VLM call.

Qwen2.5-VL explicitly supports structured extraction for invoices, forms, and tables, and its model card lists Apache 2.0. Ollama accepts a JSON Schema in `format`; vLLM supports JSON-schema-constrained structured outputs and an OpenAI-compatible serving API. This means the current OpenAI adapter can remain conceptually similar while its base URL/model configuration changes.

Docling with Granite Docling is a reasonable alternative when the main goal becomes high-fidelity PDF-to-structured-document conversion. It is less direct for the current invoice/receipt field schema, so it should not be the first replacement here.

## Risks to test before implementation

- Compare field accuracy, not just OCR quality: supplier/customer VAT IDs, decimal separators, dates, totals, receipt VAT, and invoice/receipt classification.
- Confirm PDF rendering and multi-page behavior locally; the VLM endpoint usually consumes page images rather than Azure's PDF input abstraction.
- Record model name, version, prompt/schema version, and confidence/provenance with each review.
- Check the license of every selected model checkpoint and transitive runtime dependency before commercial deployment; “open source” is not one uniform license category.

## Sources

- [PaddleOCR-VL documentation](https://www.paddleocr.ai/main/en/version3.x/algorithm/PaddleOCR-VL/PaddleOCR-VL.html)
- [PP-StructureV3 documentation](https://www.paddleocr.ai/main/en/version3.x/algorithm/PP-StructureV3/PP-StructureV3.html)
- [PaddleOCR license](https://github.com/PaddlePaddle/PaddleOCR/blob/main/LICENSE)
- [Qwen2.5-VL-7B-Instruct model card](https://huggingface.co/Qwen/Qwen2.5-VL-7B-Instruct)
- [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)
- [vLLM structured outputs](https://docs.vllm.ai/en/latest/features/structured_outputs/)
- [Granite Docling](https://www.ibm.com/granite/docs/models/docling)
