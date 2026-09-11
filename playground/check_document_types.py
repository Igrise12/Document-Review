"""Validate the fictional corpus document types with Pydantic."""

from collections import Counter
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

from app.accounting.models import (
    GLAccount,
    GLReview,
    GLSelection,
    GLSelectionValidation,
    GLSuggestion,
)
from app.correction_email.models import CorrectionEmailDraft
from app.document_review.models import (
    CurrencyCode,
    DocumentIssue,
    DocumentType,
    EvidenceSource,
    EvidenceStatus,
    FieldEvidence,
    InvoiceDocument,
    InvoiceFields,
    IssueSeverity,
    NormalizedFinancialDocument,
    ProviderRunMetadata,
    ReceiptDocument,
    ReceiptFields,
    ReviewState,
    SourceDocumentMetadata,
    VatId,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "samples/manifest.json"
SAMPLES_DIR = REPO_ROOT / "samples/generated"
DOCUMENT_ADAPTER = TypeAdapter(NormalizedFinancialDocument)


class ExpectedFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType
    currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")]
    customer_name: str | None
    customer_vat_id: str | None
    due_date: date | None
    invoice_date: date | None
    invoice_number: str | None
    invoice_total: Decimal | None
    purchase_order: str | None
    subtotal: Decimal | None
    total_tax: Decimal | None
    vendor_name: str | None
    vendor_vat_id: str | None


class SampleDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType
    expected: ExpectedFields
    expected_issue_codes: list[str]
    filename: str
    language: Literal["en", "nl", "de", "fr"]
    layout: str
    pages: int = Field(gt=0)
    scenario: str

    @model_validator(mode="after")
    def labels_must_agree(self) -> "SampleDocument":
        if self.document_type != self.expected.document_type:
            raise ValueError("top-level and expected document types must agree")
        return self


MANIFEST_ADAPTER = TypeAdapter(list[SampleDocument])


def load_manifest() -> list[SampleDocument]:
    return MANIFEST_ADAPTER.validate_json(MANIFEST_PATH.read_bytes())


def classify_expected_document(raw_document: dict[str, object]) -> DocumentType:
    """Return the validated corpus classification for one document."""
    return SampleDocument.model_validate(raw_document).document_type


def source_metadata(document: SampleDocument) -> SourceDocumentMetadata:
    media_types = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }
    path = SAMPLES_DIR / document.filename
    return SourceDocumentMetadata(
        filename=document.filename,
        media_type=media_types[path.suffix.lower()],
        size_bytes=path.stat().st_size,
        page_count=document.pages,
        uploaded_at=datetime(2026, 9, 11, tzinfo=UTC),
    )


def vat_id(value: str | None) -> VatId | None:
    if value is None:
        return None
    return VatId(normalized=value, display=value)


def normalized_payload(document: SampleDocument) -> dict[str, object]:
    expected = document.expected
    source = source_metadata(document).model_dump()
    currency = CurrencyCode(code=expected.currency, display=expected.currency)

    if document.document_type is DocumentType.INVOICE:
        fields = InvoiceFields(
            vendor_name=expected.vendor_name,
            vendor_vat_id=vat_id(expected.vendor_vat_id),
            customer_name=expected.customer_name,
            customer_vat_id=vat_id(expected.customer_vat_id),
            invoice_number=expected.invoice_number,
            invoice_date=expected.invoice_date,
            due_date=expected.due_date,
            purchase_order=expected.purchase_order,
            currency=currency,
            subtotal=expected.subtotal,
            total_tax=expected.total_tax,
            invoice_total=expected.invoice_total,
        )
        return {"document_type": "invoice", "source": source, "fields": fields.model_dump()}

    fields = ReceiptFields(
        merchant=expected.vendor_name,
        transaction_date=expected.invoice_date,
        expense_category="fuel",
        currency=currency,
        subtotal=expected.subtotal,
        vat_total=expected.total_tax,
        total=expected.invoice_total,
    )
    return {"document_type": "receipt", "source": source, "fields": fields.model_dump()}


def normalized_document(document: SampleDocument) -> NormalizedFinancialDocument:
    return DOCUMENT_ADAPTER.validate_python(normalized_payload(document))


def run_contract_checks(documents: list[SampleDocument]) -> None:
    invoice = normalized_document(documents[0])
    receipt = normalized_document(documents[-1])
    assert isinstance(invoice, InvoiceDocument)
    assert isinstance(receipt, ReceiptDocument)
    assert invoice.fields.invoice_total == Decimal("121.00")
    assert receipt.fields.total == Decimal("60.50")
    assert "invoice_number" not in receipt.model_dump()["fields"]

    normalized_currency = CurrencyCode(code=" eur ", display="EUR ")
    assert normalized_currency.code == "EUR"
    assert normalized_currency.display == "EUR "
    normalized_vat = VatId(normalized=" fr 61954506077 ", display="FR 61 954 06077")
    assert normalized_vat.normalized == "FR61954506077"
    assert normalized_vat.display == "FR 61 954 06077"

    conflict = FieldEvidence[Decimal](
        value=Decimal("100.00"),
        confidence=Decimal("0.90"),
        source=EvidenceSource.PRIMARY,
        status=EvidenceStatus.CONFLICT,
        primary_value=Decimal("100.00"),
        vlm_value=Decimal("110.00"),
        page=1,
        text_context="Total EUR 100.00",
    )
    assert conflict.primary_value != conflict.vlm_value

    fallback = FieldEvidence[Decimal](
        value=Decimal("10.50"),
        confidence=Decimal("0.80"),
        source=EvidenceSource.VLM,
        status=EvidenceStatus.VLM_FALLBACK,
    )
    assert fallback.value == Decimal("10.50")

    issue = DocumentIssue(
        code="purchase_order_missing",
        severity=IssueSeverity.WARNING,
        message="Purchase order is missing.",
        field="purchase_order",
    )
    assert issue.severity is IssueSeverity.WARNING
    assert ReviewState.READY_FOR_REVIEW.value == "ready_for_review"

    account = GLAccount(account_id="6100", label="Cleaning services", category="cleaning")
    gl_review = GLReview(
        suggestion=GLSuggestion(
            account_id=account.account_id,
            rationale="Supplier provides cleaning services.",
            confidence=Decimal("0.95"),
        ),
        selection=GLSelection(account_id=account.account_id),
        validation=GLSelectionValidation(account_id=account.account_id, valid=True),
    )
    assert gl_review.selection.account_id == account.account_id
    assert CorrectionEmailDraft(text="Please correct the VAT number.").text

    try:
        InvoiceFields(invoice_total=1.1)
    except ValidationError:
        pass
    else:
        raise AssertionError("money fields should reject float input")

    invalid_type = dict(normalized_payload(documents[0]), document_type="memo")
    try:
        DOCUMENT_ADAPTER.validate_python(invalid_type)
    except ValidationError:
        pass
    else:
        raise AssertionError("the document union should reject unknown document types")

    invalid_receipt = normalized_payload(documents[-1])
    invalid_receipt["fields"] = {
        **invalid_receipt["fields"],
        "invoice_number": "NOT-APPLICABLE",
    }
    try:
        DOCUMENT_ADAPTER.validate_python(invalid_receipt)
    except ValidationError:
        pass
    else:
        raise AssertionError("receipt fields should reject invoice-only values")

    ProviderRunMetadata(
        provider="fictional-provider",
        model_name="fictional-model",
        model_version="1",
        prompt_version="1",
        schema_version="1",
        runtime="local",
        started_at=datetime(2026, 9, 11, tzinfo=UTC),
    )


def run_checks() -> None:
    documents = load_manifest()
    assert len(documents) == 13, "the fictional corpus should contain 13 documents"

    counts = Counter(document.document_type for document in documents)
    assert counts == Counter({DocumentType.INVOICE: 12, DocumentType.RECEIPT: 1})

    for document in documents:
        assert (SAMPLES_DIR / document.filename).is_file(), document.filename
        assert classify_expected_document(document.model_dump()) == document.document_type

        if document.document_type is DocumentType.RECEIPT:
            assert document.expected.invoice_number is None
            assert document.expected.customer_vat_id is None
            assert document.expected.vendor_name
        else:
            assert document.expected.invoice_number
            assert document.expected.customer_name
            assert document.expected.customer_vat_id

    run_contract_checks(documents)

    invalid = documents[-1].model_dump(mode="json")
    invalid["document_type"] = "memo"
    try:
        SampleDocument.model_validate(invalid)
    except ValidationError:
        pass
    else:
        raise AssertionError("Pydantic should reject document types outside invoice/receipt")

    print(
        f"PASS: {counts[DocumentType.INVOICE]} invoices, "
        f"{counts[DocumentType.RECEIPT]} receipt; stage 2 contracts valid"
    )
    for document in documents:
        print(f"- {document.filename}: {document.document_type.value}")


if __name__ == "__main__":
    run_checks()
