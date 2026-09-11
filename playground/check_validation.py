"""Check deterministic VAT, document policy, and approval behavior."""

from datetime import date
from decimal import Decimal

from check_document_types import load_manifest, normalized_document

from app.accounting.models import GLSelectionValidation
from app.document_review.models import (
    DocumentIssue,
    EvidenceSource,
    EvidenceStatus,
    FieldEvidence,
    InvoiceDocument,
    ReceiptDocument,
)
from app.invoices.validation import (
    approval_allowed,
    invoice_duplicate_key,
    validate_document,
)


def _primary_evidence(
    document: InvoiceDocument | ReceiptDocument,
    *,
    confidence: Decimal = Decimal("0.92"),
) -> dict[str, FieldEvidence[object]]:
    evidence: dict[str, FieldEvidence[object]] = {}
    for field_name in type(document.fields).model_fields:
        value = getattr(document.fields, field_name)
        if value is None:
            evidence[field_name] = FieldEvidence(status=EvidenceStatus.MISSING)
            continue
        evidence[field_name] = FieldEvidence(
            value=value,
            confidence=confidence,
            source=EvidenceSource.PRIMARY,
            status=EvidenceStatus.PRIMARY,
        )
    return evidence


def _issue_codes(issues: list[DocumentIssue]) -> set[str]:
    return {issue.code for issue in issues}


def run_checks() -> None:
    documents = load_manifest()
    invoice = normalized_document(documents[0])
    receipt = normalized_document(documents[-1])
    assert isinstance(invoice, InvoiceDocument)
    assert isinstance(receipt, ReceiptDocument)

    valid_issues = validate_document(invoice, _primary_evidence(invoice))
    assert not valid_issues
    assert invoice_duplicate_key(invoice) == "fr61954506077|en-2026-1001"
    valid_selection = GLSelectionValidation(account_id="6100", valid=True)
    assert approval_allowed(valid_issues, valid_selection)
    assert not approval_allowed(valid_issues, None)
    assert not approval_allowed(
        valid_issues,
        GLSelectionValidation(account_id=None, valid=True),
    )

    missing_vendor_vat = normalized_document(documents[4])
    invalid_vendor_vat = normalized_document(documents[5])
    wrong_customer_vat = normalized_document(documents[6])
    total_mismatch = normalized_document(documents[7])
    missing_purchase_order = normalized_document(documents[8])
    duplicate = normalized_document(documents[9])
    for document in (
        missing_vendor_vat,
        invalid_vendor_vat,
        wrong_customer_vat,
        total_mismatch,
        missing_purchase_order,
        duplicate,
    ):
        assert isinstance(document, InvoiceDocument)

    assert _issue_codes(
        validate_document(missing_vendor_vat, _primary_evidence(missing_vendor_vat))
    ) == {"vendor_vat_id_required"}
    assert invoice_duplicate_key(missing_vendor_vat) is None
    assert _issue_codes(
        validate_document(invalid_vendor_vat, _primary_evidence(invalid_vendor_vat))
    ) == {"vendor_vat_id_invalid"}
    assert invoice_duplicate_key(invalid_vendor_vat) is None
    assert _issue_codes(
        validate_document(wrong_customer_vat, _primary_evidence(wrong_customer_vat))
    ) == {"customer_vat_id_mismatch"}
    assert _issue_codes(validate_document(total_mismatch, _primary_evidence(total_mismatch))) == {
        "invoice_total_mismatch"
    }
    assert _issue_codes(
        validate_document(missing_purchase_order, _primary_evidence(missing_purchase_order))
    ) == {"purchase_order_missing"}
    duplicate_issues = validate_document(
        duplicate,
        _primary_evidence(duplicate),
        duplicate_key_exists=True,
    )
    assert _issue_codes(duplicate_issues) == {"duplicate_invoice"}
    assert not approval_allowed(duplicate_issues, valid_selection)

    invalid_due_date = invoice.model_copy(
        update={"fields": invoice.fields.model_copy(update={"due_date": date(2026, 6, 30)})}
    )
    assert _issue_codes(
        validate_document(invalid_due_date, _primary_evidence(invalid_due_date))
    ) == {
        "due_date_before_invoice_date"
    }

    low_confidence = _primary_evidence(invoice)
    low_confidence["invoice_total"] = FieldEvidence(
        value=invoice.fields.invoice_total,
        confidence=Decimal("0.79"),
        source=EvidenceSource.PRIMARY,
        status=EvidenceStatus.PRIMARY,
    )
    low_confidence_issues = validate_document(invoice, low_confidence)
    assert _issue_codes(low_confidence_issues) == {"primary_confidence_low"}
    assert low_confidence_issues[0].field == "invoice_total"

    assert not validate_document(receipt, _primary_evidence(receipt))
    missing_receipt_fields = receipt.model_copy(
        update={
            "fields": receipt.fields.model_copy(
                update={
                    "merchant": None,
                    "transaction_date": None,
                    "currency": None,
                    "vat_total": None,
                    "total": None,
                }
            )
        }
    )
    assert _issue_codes(
        validate_document(missing_receipt_fields, _primary_evidence(missing_receipt_fields))
    ) == {
        "currency_required",
        "merchant_required",
        "receipt_total_required",
        "transaction_date_required",
        "vat_total_required",
    }
    receipt_total_mismatch = receipt.model_copy(
        update={"fields": receipt.fields.model_copy(update={"total": Decimal("60.52")})}
    )
    assert _issue_codes(
        validate_document(receipt_total_mismatch, _primary_evidence(receipt_total_mismatch))
    ) == {"receipt_total_mismatch"}

    print("PASS: offline EU VAT, invoice and receipt policy, duplicate keys, and approval checks")


if __name__ == "__main__":
    run_checks()
