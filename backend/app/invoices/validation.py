"""Pure Northstar VAT, document-policy, and approval checks."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from stdnum.eu import vat as eu_vat
from stdnum.exceptions import ValidationError

from app.accounting.models import GLSelectionValidation
from app.document_review.models import (
    DocumentIssue,
    EvidenceSource,
    FieldEvidence,
    InvoiceDocument,
    IssueSeverity,
    NormalizedFinancialDocument,
    ReceiptDocument,
    VatId,
)


@dataclass(frozen=True)
class NorthstarValidationPolicy:
    customer_vat_id: str = "NL00449544B01"
    total_tolerance: Decimal = Decimal("0.01")
    minimum_primary_confidence: Decimal = Decimal("0.80")


NORTHSTAR_POLICY: Final = NorthstarValidationPolicy()
NORTHSTAR_COMPARISON_VAT_ID: Final = eu_vat.compact(NORTHSTAR_POLICY.customer_vat_id)


def validate_document(
    document: NormalizedFinancialDocument,
    evidence: Mapping[str, FieldEvidence[object]],
    *,
    duplicate_key_exists: bool = False,
) -> list[DocumentIssue]:
    """Return deterministic issues for one normalized invoice or receipt."""
    if isinstance(document, InvoiceDocument):
        return validate_invoice(
            document,
            evidence,
            duplicate_key_exists=duplicate_key_exists,
        )
    return validate_receipt(document, evidence)


def validate_invoice(
    document: InvoiceDocument,
    evidence: Mapping[str, FieldEvidence[object]],
    *,
    duplicate_key_exists: bool,
) -> list[DocumentIssue]:
    """Return invoice-policy issues without accessing persistence or providers."""
    fields = document.fields
    issues: list[DocumentIssue] = []

    if _missing(fields.vendor_name):
        issues.append(_error("vendor_name_required", "Vendor identity is required.", "vendor_name"))

    vendor_vat_id = fields.vendor_vat_id
    if vendor_vat_id is None:
        issues.append(
            _error("vendor_vat_id_required", "Vendor VAT ID is required.", "vendor_vat_id")
        )
    elif _canonical_vat_id(vendor_vat_id) is None:
        issues.append(_error("vendor_vat_id_invalid", "Vendor VAT ID is invalid.", "vendor_vat_id"))

    if _missing(fields.customer_name):
        issues.append(
            _error("customer_name_required", "Customer identity is required.", "customer_name")
        )

    customer_vat_id = fields.customer_vat_id
    if customer_vat_id is None:
        issues.append(
            _error("customer_vat_id_required", "Customer VAT ID is required.", "customer_vat_id")
        )
    elif _canonical_vat_id(customer_vat_id) != NORTHSTAR_COMPARISON_VAT_ID:
        issues.append(
            _error(
                "customer_vat_id_mismatch",
                "Customer VAT ID does not match Northstar.",
                "customer_vat_id",
            )
        )

    if _missing(fields.invoice_number):
        issues.append(
            _error("invoice_number_required", "Invoice number is required.", "invoice_number")
        )
    if fields.invoice_date is None:
        issues.append(_error("invoice_date_required", "Invoice date is required.", "invoice_date"))
    if fields.currency is None:
        issues.append(_error("currency_required", "Currency is required.", "currency"))

    if fields.invoice_total is None:
        issues.append(
            _error("invoice_total_required", "Invoice total is required.", "invoice_total")
        )
    elif fields.invoice_total <= 0:
        issues.append(
            _error("invoice_total_non_positive", "Invoice total must be positive.", "invoice_total")
        )

    if (
        fields.invoice_date is not None
        and fields.due_date is not None
        and fields.due_date < fields.invoice_date
    ):
        issues.append(
            _error(
                "due_date_before_invoice_date",
                "Due date cannot be earlier than the invoice date.",
                "due_date",
            )
        )

    if _total_mismatch(fields.subtotal, fields.total_tax, fields.invoice_total):
        issues.append(
            _error(
                "invoice_total_mismatch",
                "Invoice total does not reconcile with subtotal and tax.",
                "invoice_total",
            )
        )

    if duplicate_key_exists and invoice_duplicate_key(document) is not None:
        issues.append(
            _error("duplicate_invoice", "An invoice with this vendor and number already exists.")
        )

    if _missing(fields.purchase_order):
        issues.append(
            _warning("purchase_order_missing", "Purchase order is missing.", "purchase_order")
        )
    issues.extend(_primary_confidence_issues(evidence))
    return issues


def validate_receipt(
    document: ReceiptDocument,
    evidence: Mapping[str, FieldEvidence[object]],
) -> list[DocumentIssue]:
    """Return receipt-policy issues without applying invoice-only requirements."""
    fields = document.fields
    issues: list[DocumentIssue] = []

    if _missing(fields.merchant):
        issues.append(_error("merchant_required", "Merchant identity is required.", "merchant"))
    if fields.transaction_date is None:
        issues.append(
            _error("transaction_date_required", "Transaction date is required.", "transaction_date")
        )
    if fields.currency is None:
        issues.append(_error("currency_required", "Currency is required.", "currency"))
    if fields.vat_total is None:
        issues.append(_error("vat_total_required", "VAT total is required.", "vat_total"))

    if fields.total is None:
        issues.append(_error("receipt_total_required", "Receipt total is required.", "total"))
    elif fields.total <= 0:
        issues.append(
            _error("receipt_total_non_positive", "Receipt total must be positive.", "total")
        )

    if _total_mismatch(fields.subtotal, fields.vat_total, fields.total):
        issues.append(
            _error(
                "receipt_total_mismatch",
                "Receipt total does not reconcile with subtotal and VAT.",
                "total",
            )
        )

    issues.extend(_primary_confidence_issues(evidence))
    return issues


def invoice_duplicate_key(document: InvoiceDocument) -> str | None:
    """Return the canonical vendor/invoice duplicate key when both parts are valid."""
    if document.fields.vendor_vat_id is None or _missing(document.fields.invoice_number):
        return None
    vendor_vat_id = _canonical_vat_id(document.fields.vendor_vat_id)
    if vendor_vat_id is None:
        return None
    invoice_number = "".join(document.fields.invoice_number.split()).casefold()
    return f"{vendor_vat_id.casefold()}|{invoice_number}"


def approval_allowed(
    issues: Sequence[DocumentIssue],
    gl_selection_validation: GLSelectionValidation | None,
) -> bool:
    """Return whether policy issues and the human GL selection permit approval."""
    return (
        gl_selection_validation is not None
        and gl_selection_validation.valid
        and bool(gl_selection_validation.account_id)
        and not any(issue.severity is IssueSeverity.ERROR for issue in issues)
    )


def _canonical_vat_id(vat_id: VatId) -> str | None:
    try:
        compacted = eu_vat.compact(vat_id.normalized)
    except ValidationError:
        return None
    return compacted if eu_vat.is_valid(compacted) else None


def _total_mismatch(
    subtotal: Decimal | None,
    tax: Decimal | None,
    total: Decimal | None,
) -> bool:
    return (
        subtotal is not None
        and tax is not None
        and total is not None
        and abs(subtotal + tax - total) > NORTHSTAR_POLICY.total_tolerance
    )


def _primary_confidence_issues(
    evidence: Mapping[str, FieldEvidence[object]],
) -> list[DocumentIssue]:
    return [
        _warning(
            "primary_confidence_low",
            f"Primary extraction confidence for {field_name.replace('_', ' ')} is below 0.80.",
            field_name,
        )
        for field_name, field_evidence in sorted(evidence.items())
        if field_evidence.source is EvidenceSource.PRIMARY
        and field_evidence.confidence is not None
        and field_evidence.confidence < NORTHSTAR_POLICY.minimum_primary_confidence
    ]


def _missing(value: str | None) -> bool:
    return value is None or not value.strip()


def _error(code: str, message: str, field: str | None = None) -> DocumentIssue:
    return DocumentIssue(code=code, severity=IssueSeverity.ERROR, message=message, field=field)


def _warning(code: str, message: str, field: str | None = None) -> DocumentIssue:
    return DocumentIssue(code=code, severity=IssueSeverity.WARNING, message=message, field=field)
