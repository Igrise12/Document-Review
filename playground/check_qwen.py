import argparse
import json
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from app.accounting.catalog import get_northstar_gl_catalog
from app.config import Settings
from app.document_review.models import (
    DocumentIssue,
    DocumentType,
    EvidenceStatus,
    FieldEvidence,
    IssueSeverity,
)
from app.providers.qwen import QwenProviderError, QwenVLMProvider

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO_ROOT / "samples/generated"


class _FakeCompletions:
    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("fake client ran out of responses")
        content = self._responses.pop(0)
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
        )


class _FakeClient:
    def __init__(self, responses: list[str]) -> None:
        completions = _FakeCompletions(responses)
        self.chat = SimpleNamespace(completions=completions)
        self.completions = completions


def _settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None,
        local_vlm_max_structured_output_retries=1,
        **overrides,
    )


def _offline_check() -> None:
    invoice_content = (SAMPLE_DIR / "01-en-happy-classic.pdf").read_bytes()
    multipage_content = (SAMPLE_DIR / "12-en-two-page.pdf").read_bytes()
    receipt_content = (SAMPLE_DIR / "13-nl-fuel-receipt.png").read_bytes()
    responses = [
        "{}",
        json.dumps(
            {
                "document_type": "invoice",
                "confidence": "0.98",
                "reasoning": "The document contains an invoice number and payment terms.",
            }
        ),
        json.dumps(
            {
                "document_type": "invoice",
                "fields": {
                    "vendor_name": "Bright Spark Europe S.A.S.",
                    "vendor_vat_id": {
                        "normalized": "FR61954506077",
                        "display": "FR 61 954506077",
                    },
                    "customer_name": "Northstar Facilities B.V.",
                    "customer_vat_id": {
                        "normalized": "NL00449544B01",
                        "display": "NL00449544B01",
                    },
                    "invoice_number": "EN-2026-1001",
                    "invoice_date": "2026-07-01",
                    "due_date": "2026-07-31",
                    "purchase_order": "PO-4001",
                    "currency": {"code": "EUR", "display": "EUR"},
                    "subtotal": "100.00",
                    "total_tax": "21.00",
                    "invoice_total": "121.00",
                },
                "field_confidence": {
                    "vendor_name": "0.95",
                    "vendor_vat_id": "0.92",
                    "customer_name": "0.95",
                    "customer_vat_id": "0.94",
                    "invoice_number": "0.96",
                    "invoice_date": "0.94",
                    "due_date": "0.93",
                    "purchase_order": "0.90",
                    "currency": "0.99",
                    "subtotal": "0.91",
                    "total_tax": "0.91",
                    "invoice_total": "0.97",
                },
            }
        ),
        json.dumps(
            {
                "document_type": "receipt",
                "fields": {
                    "merchant": "Northstar Fuel Station",
                    "transaction_date": "2026-07-10",
                    "expense_category": "fuel",
                    "currency": {"code": "EUR", "display": "EUR"},
                    "subtotal": "50.00",
                    "vat_total": "10.50",
                    "total": "60.50",
                },
                "field_confidence": {
                    "merchant": "0.94",
                    "transaction_date": "0.92",
                    "expense_category": "0.89",
                    "currency": "0.99",
                    "subtotal": "0.90",
                    "vat_total": "0.90",
                    "total": "0.96",
                },
            }
        ),
        json.dumps(
            {
                "account_id": "6170",
                "rationale": "Fuel is a transport expense.",
                "confidence": "0.90",
            }
        ),
        json.dumps(
            {
                "account_id": "9999",
                "rationale": "This account is not in the supplied catalog.",
                "confidence": "0.99",
            }
        ),
        json.dumps({"text": "Please provide the missing supplier VAT number."}),
    ]
    client = _FakeClient(responses)
    provider = QwenVLMProvider(_settings(), client=client)

    classification = provider.classify_document(
        filename="01-en-happy-classic.pdf",
        media_type="application/pdf",
        content=invoice_content,
    )
    assert classification.classification.document_type is DocumentType.INVOICE
    assert classification.classification.confidence == Decimal("0.98")
    assert classification.provider_run.schema_version == "qwen-classification/v1"
    assert len(client.completions.calls[0]["messages"][1]["content"]) == 2
    assert len(client.completions.calls[1]["messages"][1]["content"]) == 3

    invoice_review = provider.review_document(
        filename="12-en-two-page.pdf",
        media_type="application/pdf",
        content=multipage_content,
        uploaded_at=datetime.now(UTC),
        document_type=DocumentType.INVOICE,
    )
    assert invoice_review.document.document_type == DocumentType.INVOICE.value
    assert invoice_review.document.source.page_count == 2
    assert invoice_review.field_confidence["invoice_total"] == Decimal("0.97")

    receipt_review = provider.review_document(
        filename="13-nl-fuel-receipt.png",
        media_type="image/png",
        content=receipt_content,
        uploaded_at=datetime.now(UTC),
        document_type=DocumentType.RECEIPT,
    )
    assert receipt_review.document.document_type == DocumentType.RECEIPT.value
    assert receipt_review.document.fields.total == Decimal("60.50")

    catalog = get_northstar_gl_catalog()
    valid_suggestion = provider.suggest_gl(
        document=receipt_review.document,
        catalog=catalog,
    )
    assert valid_suggestion.suggestion is not None
    assert valid_suggestion.suggestion.account_id == "6170"

    invalid_suggestion = provider.suggest_gl(
        document=receipt_review.document,
        catalog=catalog,
    )
    assert invalid_suggestion.suggestion is None

    draft = provider.draft_correction(
        document=invoice_review.document,
        issues=[
            DocumentIssue(
                code="vendor_vat_id_required",
                severity=IssueSeverity.ERROR,
                message="Supplier VAT number is required.",
                field="vendor_vat_id",
            )
        ],
        evidence={
            "vendor_vat_id": FieldEvidence(
                status=EvidenceStatus.MISSING,
            )
        },
    )
    assert draft.draft.text
    assert draft.provider_run.schema_version == "qwen-correction-draft/v1"

    exhausted = QwenVLMProvider(
        _settings(),
        client=_FakeClient(["not-json", "still-not-json"]),
    )
    try:
        exhausted.classify_document(
            filename="01-en-happy-classic.pdf",
            media_type="application/pdf",
            content=invoice_content,
        )
    except QwenProviderError as error:
        assert "after 2 attempts" in str(error)
    else:
        raise AssertionError("invalid structured output should exhaust bounded retries")

    print("PASS: Qwen offline schema, retry, PDF rendering, GL validation, and draft checks")


def _live_check() -> None:
    settings = Settings(_env_file=None)
    provider = QwenVLMProvider(settings)
    invoice_path = SAMPLE_DIR / "01-en-happy-classic.pdf"
    receipt_path = SAMPLE_DIR / "13-nl-fuel-receipt.png"
    multipage_path = SAMPLE_DIR / "12-en-two-page.pdf"

    invoice_classification = provider.classify_document(
        filename=invoice_path.name,
        media_type="application/pdf",
        content=invoice_path.read_bytes(),
    )
    assert invoice_classification.classification.document_type is DocumentType.INVOICE
    invoice_review = provider.review_document(
        filename=invoice_path.name,
        media_type="application/pdf",
        content=invoice_path.read_bytes(),
        uploaded_at=datetime.now(UTC),
        document_type=invoice_classification.classification.document_type,
    )
    assert invoice_review.document.document_type == DocumentType.INVOICE.value

    receipt_classification = provider.classify_document(
        filename=receipt_path.name,
        media_type="image/png",
        content=receipt_path.read_bytes(),
    )
    assert receipt_classification.classification.document_type is DocumentType.RECEIPT
    receipt_review = provider.review_document(
        filename=receipt_path.name,
        media_type="image/png",
        content=receipt_path.read_bytes(),
        uploaded_at=datetime.now(UTC),
        document_type=receipt_classification.classification.document_type,
    )
    assert receipt_review.document.document_type == DocumentType.RECEIPT.value

    multipage_classification = provider.classify_document(
        filename=multipage_path.name,
        media_type="application/pdf",
        content=multipage_path.read_bytes(),
    )
    multipage_review = provider.review_document(
        filename=multipage_path.name,
        media_type="application/pdf",
        content=multipage_path.read_bytes(),
        uploaded_at=datetime.now(UTC),
        document_type=multipage_classification.classification.document_type,
    )
    assert multipage_review.document.source.page_count == 2

    catalog = get_northstar_gl_catalog()
    suggestion = provider.suggest_gl(document=receipt_review.document, catalog=catalog)
    assert suggestion.suggestion is None or suggestion.suggestion.account_id in {
        account.account_id for account in catalog
    }
    draft = provider.draft_correction(
        document=invoice_review.document,
        issues=[],
        evidence={},
    )
    assert draft.draft.text
    print(
        f"PASS: Qwen live checks via {settings.local_vlm_runtime} "
        f"({settings.local_vlm_model})"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    _offline_check()
    if args.live:
        try:
            _live_check()
        except QwenProviderError as error:
            print(f"BLOCKED: {error}", file=sys.stderr)
            raise SystemExit(2) from error


if __name__ == "__main__":
    main()
