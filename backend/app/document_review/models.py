from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    AwareDatetime,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)


def _reject_float(value: object) -> object:
    if isinstance(value, (bool, float)):
        raise ValueError("exact decimal values cannot be supplied as float")
    return value


Money = Annotated[Decimal, BeforeValidator(_reject_float)]
Probability = Annotated[
    Decimal,
    BeforeValidator(_reject_float),
    Field(ge=Decimal("0"), le=Decimal("1")),
]
IssueCode = Annotated[str, StringConstraints(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")]


class DocumentType(StrEnum):
    INVOICE = "invoice"
    RECEIPT = "receipt"


class CurrencyCode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
    display: str = Field(min_length=1)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        return value.strip().upper() if isinstance(value, str) else value


class VatId(BaseModel):
    model_config = ConfigDict(extra="forbid")

    normalized: str = Field(min_length=2)
    display: str = Field(min_length=1)

    @field_validator("normalized", mode="before")
    @classmethod
    def normalize_vat_id(cls, value: object) -> object:
        return "".join(value.split()).upper() if isinstance(value, str) else value


class SourceDocumentMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1)
    media_type: Literal["application/pdf", "image/png", "image/jpeg"]
    size_bytes: int = Field(gt=0)
    page_count: int = Field(gt=0)
    uploaded_at: AwareDatetime
    processed_at: AwareDatetime | None = None


class InvoiceFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    vendor_name: str | None = None
    vendor_vat_id: VatId | None = None
    customer_name: str | None = None
    customer_vat_id: VatId | None = None
    invoice_number: str | None = None
    invoice_date: date | None = None
    due_date: date | None = None
    purchase_order: str | None = None
    currency: CurrencyCode | None = None
    subtotal: Money | None = None
    total_tax: Money | None = None
    invoice_total: Money | None = None


class ReceiptFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    merchant: str | None = None
    transaction_date: date | None = None
    expense_category: str | None = None
    currency: CurrencyCode | None = None
    subtotal: Money | None = None
    vat_total: Money | None = None
    total: Money | None = None


class InvoiceDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal["invoice"] = "invoice"
    source: SourceDocumentMetadata
    fields: InvoiceFields


class ReceiptDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal["receipt"] = "receipt"
    source: SourceDocumentMetadata
    fields: ReceiptFields


NormalizedFinancialDocument = Annotated[
    InvoiceDocument | ReceiptDocument,
    Field(discriminator="document_type"),
]


class EvidenceSource(StrEnum):
    PRIMARY = "primary"
    VLM = "vlm"
    MANUAL = "manual"


class EvidenceStatus(StrEnum):
    PRIMARY = "primary"
    VLM_FALLBACK = "vlm_fallback"
    MERGED = "merged"
    MISSING = "missing"
    CONFLICT = "conflict"


class BoundingBox(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: float = Field(ge=0)
    y: float = Field(ge=0)
    width: float = Field(ge=0)
    height: float = Field(ge=0)


class FieldEvidence[EvidenceValue](BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: EvidenceValue | None = None
    confidence: Probability | None = None
    source: EvidenceSource | None = None
    status: EvidenceStatus
    page: int | None = Field(default=None, gt=0)
    bounding_box: BoundingBox | None = None
    text_context: str | None = None
    primary_value: EvidenceValue | None = None
    vlm_value: EvidenceValue | None = None

    @model_validator(mode="after")
    def validate_status(self) -> "FieldEvidence[EvidenceValue]":
        if self.status is EvidenceStatus.MISSING and self.value is not None:
            raise ValueError("missing evidence cannot contain a value")
        if self.status is EvidenceStatus.CONFLICT and (
            self.primary_value is None or self.vlm_value is None
        ):
            raise ValueError("conflict evidence must preserve primary and VLM values")
        if self.status is EvidenceStatus.PRIMARY and self.source is not EvidenceSource.PRIMARY:
            raise ValueError("primary evidence must use the primary source")
        if self.status is EvidenceStatus.VLM_FALLBACK and self.source is not EvidenceSource.VLM:
            raise ValueError("VLM fallback evidence must use the VLM source")
        return self


class IssueSeverity(StrEnum):
    ERROR = "error"
    WARNING = "warning"


class DocumentIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: IssueCode
    severity: IssueSeverity
    message: str = Field(min_length=1)
    field: str | None = None


class ReviewState(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY_FOR_REVIEW = "ready_for_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    CORRECTION_REQUESTED = "correction_requested"
    FAILED = "failed"


class ProviderRunMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str = Field(min_length=1)
    model_name: str | None = None
    model_version: str | None = None
    prompt_version: str | None = None
    schema_version: str = Field(min_length=1)
    runtime: str | None = None
    started_at: AwareDatetime
    finished_at: AwareDatetime | None = None
    duration_ms: int | None = Field(default=None, ge=0)


class DocumentClassification(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType
    confidence: Probability
    reasoning: str = Field(min_length=1)


class DocumentClassificationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    classification: DocumentClassification
    provider_run: ProviderRunMetadata


class VLMExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: NormalizedFinancialDocument
    field_confidence: dict[str, Probability]
    provider_run: ProviderRunMetadata


class PrimaryExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: NormalizedFinancialDocument
    evidence: dict[str, FieldEvidence[object]]
    provider_run: ProviderRunMetadata


class MergedExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document: NormalizedFinancialDocument
    evidence: dict[str, FieldEvidence[object]]
