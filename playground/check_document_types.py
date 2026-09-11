"""Validate the fictional corpus document types with Pydantic."""

from collections import Counter
from datetime import date
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, model_validator

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = REPO_ROOT / "samples/manifest.json"
SAMPLES_DIR = REPO_ROOT / "samples/generated"


class DocumentType(StrEnum):
    INVOICE = "invoice"
    RECEIPT = "receipt"


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

    invalid = documents[-1].model_dump(mode="json")
    invalid["document_type"] = "memo"
    try:
        SampleDocument.model_validate(invalid)
    except ValidationError:
        pass
    else:
        raise AssertionError("Pydantic should reject document types outside invoice/receipt")

    print(f"PASS: {counts[DocumentType.INVOICE]} invoices, {counts[DocumentType.RECEIPT]} receipt")
    for document in documents:
        print(f"- {document.filename}: {document.document_type.value}")


if __name__ == "__main__":
    run_checks()
