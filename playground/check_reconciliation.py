"""Check deterministic normalization, merge precedence, and provenance."""

from datetime import UTC, datetime
from decimal import Decimal

from check_document_types import load_manifest, normalized_document

from app.document_review.models import (
    CurrencyCode,
    DocumentType,
    EvidenceSource,
    EvidenceStatus,
    FieldEvidence,
    InvoiceDocument,
    InvoiceFields,
    PrimaryExtractionResult,
    ProviderRunMetadata,
    ReceiptDocument,
    VatId,
    VLMExtractionResult,
)
from app.document_review.reconciliation import merge_extractions


def _provider_run(provider: str) -> ProviderRunMetadata:
    timestamp = datetime(2026, 9, 11, tzinfo=UTC)
    return ProviderRunMetadata(
        provider=provider,
        model_name="fictional-model",
        model_version="1",
        prompt_version="1",
        schema_version="1",
        runtime="offline",
        started_at=timestamp,
        finished_at=timestamp,
        duration_ms=1,
    )


def _primary_result(document: InvoiceDocument | ReceiptDocument) -> PrimaryExtractionResult:
    evidence: dict[str, FieldEvidence[object]] = {}
    for field_name in type(document.fields).model_fields:
        value = getattr(document.fields, field_name)
        if value is None:
            evidence[field_name] = FieldEvidence(status=EvidenceStatus.MISSING)
            continue
        evidence[field_name] = FieldEvidence(
            value=value,
            confidence=Decimal("0.92"),
            source=EvidenceSource.PRIMARY,
            status=EvidenceStatus.PRIMARY,
            text_context=("Total EUR 121.00" if field_name == "invoice_total" else None),
        )
    return PrimaryExtractionResult(
        document=document,
        evidence=evidence,
        provider_run=_provider_run("primary"),
    )


def _vlm_result(document: InvoiceDocument | ReceiptDocument) -> VLMExtractionResult:
    confidence = {
        field_name: Decimal("0.84")
        for field_name in type(document.fields).model_fields
        if getattr(document.fields, field_name) is not None
    }
    return VLMExtractionResult(
        document=document,
        field_confidence=confidence,
        provider_run=_provider_run("vlm"),
    )


def run_checks() -> None:
    documents = load_manifest()
    source_document = normalized_document(documents[11])
    assert isinstance(source_document, InvoiceDocument)
    assert source_document.source.page_count == 2

    primary_fields = source_document.fields.model_dump(mode="python")
    primary_fields.update(
        {
            "vendor_name": "  Bright   Spark Europe S.A.S.  ",
            "vendor_vat_id": VatId(
                normalized=" fr61954506077 ",
                display=" FR 61 954 06077 ",
            ),
            "invoice_number": None,
            "purchase_order": None,
            "currency": CurrencyCode(code=" eur ", display=" eur "),
            "invoice_total": Decimal("121.00"),
            "due_date": None,
        }
    )
    vlm_fields = source_document.fields.model_dump(mode="python")
    vlm_fields.update(
        {
            "vendor_name": "Bright Spark Europe S.A.S.",
            "vendor_vat_id": VatId(
                normalized="FR 61954506077",
                display="FR61954506077",
            ),
            "invoice_number": " EN-2026-1001 ",
            "purchase_order": " PO-4001 ",
            "total_tax": None,
            "invoice_total": Decimal("122.00"),
            "due_date": None,
        }
    )

    primary = _primary_result(
        InvoiceDocument(source=source_document.source, fields=InvoiceFields(**primary_fields))
    )
    vlm = _vlm_result(
        InvoiceDocument(source=source_document.source, fields=InvoiceFields(**vlm_fields))
    )
    merged = merge_extractions(primary, vlm)
    assert isinstance(merged.document, InvoiceDocument)
    assert merged.document.document_type == DocumentType.INVOICE
    assert merged.document.source.page_count == 2
    assert merged.document.fields.vendor_name == "Bright Spark Europe S.A.S."
    assert merged.document.fields.invoice_number == "EN-2026-1001"
    assert merged.document.fields.purchase_order == "PO-4001"
    assert merged.document.fields.currency == CurrencyCode(code="EUR", display="eur")
    assert merged.document.fields.invoice_total == Decimal("121.00")

    assert merged.evidence["vendor_name"].status is EvidenceStatus.MERGED
    assert merged.evidence["invoice_number"].status is EvidenceStatus.VLM_FALLBACK
    assert merged.evidence["invoice_number"].source is EvidenceSource.VLM
    assert merged.evidence["total_tax"].status is EvidenceStatus.PRIMARY
    assert merged.evidence["due_date"].status is EvidenceStatus.MISSING

    conflict = merged.evidence["invoice_total"]
    assert conflict.status is EvidenceStatus.CONFLICT
    assert conflict.value == Decimal("121.00")
    assert conflict.primary_value == Decimal("121.00")
    assert conflict.vlm_value == Decimal("122.00")
    assert conflict.text_context == "Total EUR 121.00"

    receipt = normalized_document(documents[-1])
    assert isinstance(receipt, ReceiptDocument)
    try:
        merge_extractions(primary, _vlm_result(receipt))
    except ValueError as error:
        assert str(error) == "primary and VLM document types must match before merging"
    else:
        raise AssertionError("merge should reject different document types")

    print("PASS: normalization, merge precedence, provenance, conflict, and two-page checks")


if __name__ == "__main__":
    run_checks()
