from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from datetime import date
from decimal import Decimal, InvalidOperation

from pydantic import TypeAdapter

from app.document_review.models import (
    CurrencyCode,
    EvidenceSource,
    EvidenceStatus,
    FieldEvidence,
    MergedExtractionResult,
    NormalizedFinancialDocument,
    PrimaryExtractionResult,
    VatId,
    VLMExtractionResult,
)

_DOCUMENT_ADAPTER = TypeAdapter(NormalizedFinancialDocument)
_MONEY_FIELDS = {"subtotal", "total_tax", "vat_total", "total", "invoice_total"}
_DATE_FIELDS = {"invoice_date", "due_date", "transaction_date"}
_VAT_FIELDS = {"vendor_vat_id", "customer_vat_id"}
_EMPTY_MARKERS = {
    "",
    "n a",
    "n v t",
    "na",
    "nvt",
    "nicht zutreffend",
    "niet van toepassing",
    "non applicable",
    "not applicable",
}
_DATE_PATTERN = re.compile(r"^(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})$")


def normalize_document(
    document: NormalizedFinancialDocument,
) -> NormalizedFinancialDocument:
    """Return a canonical copy of a provider-independent document."""
    payload = document.model_dump(mode="json")
    fields = payload["fields"]
    if not isinstance(fields, Mapping):
        raise ValueError("financial document fields must be a mapping")
    payload["fields"] = {
        field_name: _normalize_field(field_name, value)
        for field_name, value in fields.items()
    }
    return _DOCUMENT_ADAPTER.validate_python(payload)


def merge_extractions(
    primary: PrimaryExtractionResult,
    vlm: VLMExtractionResult,
) -> MergedExtractionResult:
    """Normalize and merge two extractions while keeping primary evidence authoritative."""
    primary_document = normalize_document(primary.document)
    vlm_document = normalize_document(vlm.document)
    if primary_document.document_type != vlm_document.document_type:
        raise ValueError("primary and VLM document types must match before merging")

    field_names = tuple(type(primary_document.fields).model_fields)
    merged_fields = primary_document.fields.model_dump(mode="python")
    merged_evidence: dict[str, FieldEvidence[object]] = {}

    for field_name in field_names:
        primary_value = getattr(primary_document.fields, field_name)
        vlm_value = getattr(vlm_document.fields, field_name)
        merged_fields[field_name] = primary_value if primary_value is not None else vlm_value
        merged_evidence[field_name] = _merge_field_evidence(
            field_name,
            primary_value,
            vlm_value,
            primary.evidence.get(field_name),
            vlm.field_confidence.get(field_name),
        )

    merged_payload = primary_document.model_dump(mode="python")
    merged_payload["fields"] = merged_fields
    merged_document = _DOCUMENT_ADAPTER.validate_python(merged_payload)
    return MergedExtractionResult(document=merged_document, evidence=merged_evidence)


def _normalize_field(field_name: str, value: object) -> object:
    if value is None:
        return None
    if field_name in _MONEY_FIELDS:
        return _normalize_money(value)
    if field_name in _DATE_FIELDS:
        return _normalize_date(value)
    if field_name == "currency":
        return _normalize_currency(value)
    if field_name in _VAT_FIELDS:
        return _normalize_vat(value)
    return _normalize_text(value)


def _normalize_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    cleaned = " ".join(value.split())
    return None if _fold(cleaned) in _EMPTY_MARKERS else cleaned


def _normalize_money(value: object) -> object:
    if isinstance(value, Decimal):
        return value
    if not isinstance(value, str):
        return value
    cleaned = _normalize_text(value)
    if cleaned is None or not isinstance(cleaned, str):
        return cleaned
    cleaned = re.sub(r"(?i)\b(?:EUR|USD|GBP|CHF)\b|€", "", cleaned)
    cleaned = cleaned.replace("'", "").replace(" ", "")
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return cleaned


def _normalize_date(value: object) -> object:
    if isinstance(value, date):
        return value.isoformat()
    if not isinstance(value, str):
        return value
    cleaned = _normalize_text(value)
    if cleaned is None or not isinstance(cleaned, str):
        return cleaned
    try:
        return date.fromisoformat(cleaned).isoformat()
    except ValueError:
        pass
    match = _DATE_PATTERN.fullmatch(cleaned)
    if not match:
        return cleaned
    day, month, year = (int(part) for part in match.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return cleaned


def _normalize_currency(value: object) -> object:
    if isinstance(value, str):
        display = _normalize_text(value)
        raw_code = display
    elif isinstance(value, Mapping):
        display = _normalize_text(value.get("display"))
        raw_code = _normalize_text(value.get("code"))
    else:
        return value
    if display is None or not isinstance(display, str):
        return display
    if raw_code is None or not isinstance(raw_code, str):
        raw_code = display
    code = "EUR" if _fold(raw_code) in {"eur", "euro"} or raw_code == "€" else raw_code.upper()
    return {"code": code, "display": display}


def _normalize_vat(value: object) -> object:
    if isinstance(value, str):
        display = _normalize_text(value)
        normalized = display
    elif isinstance(value, Mapping):
        display = _normalize_text(value.get("display"))
        normalized = _normalize_text(value.get("normalized"))
    else:
        return value
    if display is None or normalized is None:
        return None
    if not isinstance(display, str) or not isinstance(normalized, str):
        return value
    return {
        "normalized": "".join(normalized.split()).upper(),
        "display": display,
    }


def _merge_field_evidence(
    field_name: str,
    primary_value: object | None,
    vlm_value: object | None,
    primary_evidence: FieldEvidence[object] | None,
    vlm_confidence: Decimal | None,
) -> FieldEvidence[object]:
    if primary_value is None and vlm_value is None:
        return _evidence(
            primary_evidence,
            value=None,
            status=EvidenceStatus.MISSING,
            source=None,
            confidence=None,
        )
    if primary_value is None:
        return _evidence(
            primary_evidence,
            value=vlm_value,
            status=EvidenceStatus.VLM_FALLBACK,
            source=EvidenceSource.VLM,
            confidence=vlm_confidence,
        )
    if vlm_value is None:
        return _evidence(
            primary_evidence,
            value=primary_value,
            status=EvidenceStatus.PRIMARY,
            source=EvidenceSource.PRIMARY,
            confidence=primary_evidence.confidence if primary_evidence else None,
        )
    if _equivalent(field_name, primary_value, vlm_value):
        return _evidence(
            primary_evidence,
            value=primary_value,
            status=EvidenceStatus.MERGED,
            source=EvidenceSource.PRIMARY,
            confidence=primary_evidence.confidence if primary_evidence else None,
        )
    return _evidence(
        primary_evidence,
        value=primary_value,
        status=EvidenceStatus.CONFLICT,
        source=EvidenceSource.PRIMARY,
        confidence=primary_evidence.confidence if primary_evidence else None,
        primary_value=primary_value,
        vlm_value=vlm_value,
    )


def _evidence(
    primary_evidence: FieldEvidence[object] | None,
    *,
    value: object | None,
    status: EvidenceStatus,
    source: EvidenceSource | None,
    confidence: Decimal | None,
    primary_value: object | None = None,
    vlm_value: object | None = None,
) -> FieldEvidence[object]:
    return FieldEvidence(
        value=value,
        confidence=confidence,
        source=source,
        status=status,
        page=primary_evidence.page if primary_evidence else None,
        bounding_box=primary_evidence.bounding_box if primary_evidence else None,
        text_context=primary_evidence.text_context if primary_evidence else None,
        primary_value=primary_value,
        vlm_value=vlm_value,
    )


def _equivalent(field_name: str, primary_value: object, vlm_value: object) -> bool:
    if field_name == "currency" and isinstance(primary_value, CurrencyCode) and isinstance(
        vlm_value, CurrencyCode
    ):
        return primary_value.code == vlm_value.code
    if (
        field_name in _VAT_FIELDS
        and isinstance(primary_value, VatId)
        and isinstance(vlm_value, VatId)
    ):
        return primary_value.normalized == vlm_value.normalized
    if isinstance(primary_value, str) and isinstance(vlm_value, str):
        return _fold(primary_value) == _fold(vlm_value)
    return primary_value == vlm_value


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()
