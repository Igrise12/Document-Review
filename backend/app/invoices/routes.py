from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Request, Response, UploadFile, status
from pydantic import BaseModel, ConfigDict, TypeAdapter

from app.accounting.catalog import get_northstar_gl_catalog
from app.accounting.models import GLAccount, GLReview
from app.correction_email.models import CorrectionDraftResult
from app.document_review.models import (
    DocumentIssue,
    DocumentType,
    EvidenceStatus,
    FieldEvidence,
    InvoiceDocument,
    IssueSeverity,
    NormalizedFinancialDocument,
    ReceiptDocument,
    ReviewState,
)
from app.invoices.repository import ReviewSnapshot
from app.invoices.service import InvoiceReviewService
from app.invoices.storage import MAX_UPLOAD_BYTES, UploadValidationError
from app.invoices.validation import approval_allowed as policy_allows_approval

router = APIRouter()
_DOCUMENT_ADAPTER = TypeAdapter(NormalizedFinancialDocument)


class ApiErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str


class ApiErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ApiErrorDetail


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class OriginalFileMetadataResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str
    media_type: Literal["application/pdf", "image/png", "image/jpeg"]
    size_bytes: int
    page_count: int | None
    uploaded_at: datetime


class ReviewSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str
    state: ReviewState
    document_type: DocumentType | None
    counterparty: str | None
    document_date: date | None
    currency: str | None
    total: Decimal | None
    blocking_issue_count: int
    updated_at: datetime
    failure_message: str | None


class ReviewDetailResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    review_id: str
    state: ReviewState
    document_type: DocumentType | None
    original_file: OriginalFileMetadataResponse
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None
    normalized_document: NormalizedFinancialDocument | None
    evidence: dict[str, FieldEvidence[object]]
    conflicts: dict[str, FieldEvidence[object]]
    issues: list[DocumentIssue]
    blocking_issue_count: int
    gl_review: GLReview | None
    approval_allowed: bool
    provider_runs: dict[str, object]
    action_metadata: dict[str, object] | None
    failure_message: str | None


class GLSelectionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str | None


def get_review_service(request: Request) -> InvoiceReviewService:
    return request.app.state.review_service


ReviewService = Annotated[InvoiceReviewService, Depends(get_review_service)]
UploadedFiles = Annotated[list[UploadFile], File(alias="file")]


@router.get("/gl-catalog", response_model=list[GLAccount])
def get_gl_catalog() -> list[GLAccount]:
    return list(get_northstar_gl_catalog())


@router.post(
    "/reviews",
    response_model=ReviewDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_review(file: UploadedFiles, service: ReviewService) -> ReviewDetailResponse:
    if len(file) != 1:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_upload",
            "Upload exactly one PDF, PNG, or JPEG file.",
        )
    upload = file[0]
    filename = (upload.filename or "").strip()
    if not filename or len(filename) > 255:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_upload",
            "The uploaded file must have a filename of at most 255 characters.",
        )
    content = upload.file.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_upload",
            "Upload exceeds the 4 MB limit.",
        )
    try:
        review = service.upload_document(
            original_filename=filename,
            media_type=upload.content_type or "",
            content=content,
        )
    except (UploadValidationError, ValueError) as error:
        raise ApiError(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "invalid_upload",
            str(error),
        ) from error
    except OSError as error:
        raise _storage_error() from error
    return _review_detail(review)


@router.get("/reviews", response_model=list[ReviewSummaryResponse])
def list_reviews(service: ReviewService) -> list[ReviewSummaryResponse]:
    return [_review_summary(review) for review in service.list_reviews()]


@router.post("/reviews/{review_id}/process", response_model=ReviewDetailResponse)
def process_review(review_id: str, service: ReviewService) -> ReviewDetailResponse:
    return _review_detail(service.process_review(review_id))


@router.get("/reviews/{review_id}/original")
def get_original(review_id: str, service: ReviewService) -> Response:
    try:
        review, content = service.read_original(review_id)
    except (OSError, ValueError) as error:
        raise _storage_error() from error
    return Response(
        content=content,
        media_type=review.media_type,
        headers={"Cache-Control": "no-store"},
    )


@router.put("/reviews/{review_id}/gl-selection", response_model=ReviewDetailResponse)
def select_gl(
    review_id: str,
    selection: GLSelectionRequest,
    service: ReviewService,
) -> ReviewDetailResponse:
    return _review_detail(service.select_gl(review_id, selection.account_id))


@router.post("/reviews/{review_id}/approve", response_model=ReviewDetailResponse)
def approve_review(review_id: str, service: ReviewService) -> ReviewDetailResponse:
    return _review_detail(service.approve_review(review_id))


@router.post("/reviews/{review_id}/reject", response_model=ReviewDetailResponse)
def reject_review(review_id: str, service: ReviewService) -> ReviewDetailResponse:
    return _review_detail(service.reject_review(review_id))


@router.post("/reviews/{review_id}/correction-request", response_model=ReviewDetailResponse)
def request_correction(review_id: str, service: ReviewService) -> ReviewDetailResponse:
    return _review_detail(service.request_correction(review_id))


@router.post("/reviews/{review_id}/correction-draft", response_model=CorrectionDraftResult)
def draft_correction(review_id: str, service: ReviewService) -> CorrectionDraftResult:
    return service.draft_correction(review_id)


@router.delete("/reviews/{review_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_review(review_id: str, service: ReviewService) -> Response:
    try:
        service.delete_review(review_id)
    except (OSError, ValueError) as error:
        raise _storage_error() from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/reviews/{review_id}", response_model=ReviewDetailResponse)
def get_review(review_id: str, service: ReviewService) -> ReviewDetailResponse:
    return _review_detail(service.get_review(review_id))


def _review_summary(review: ReviewSnapshot) -> ReviewSummaryResponse:
    document = _normalized_document(review)
    counterparty: str | None = None
    document_date: date | None = None
    currency: str | None = None
    total: Decimal | None = None
    if isinstance(document, InvoiceDocument):
        counterparty = document.fields.vendor_name
        document_date = document.fields.invoice_date
        total = document.fields.invoice_total
        currency = document.fields.currency.code if document.fields.currency else None
    elif isinstance(document, ReceiptDocument):
        counterparty = document.fields.merchant
        document_date = document.fields.transaction_date
        total = document.fields.total
        currency = document.fields.currency.code if document.fields.currency else None
    issues = _issues(review)
    return ReviewSummaryResponse(
        review_id=review.review_id,
        state=review.state,
        document_type=review.document_type,
        counterparty=counterparty,
        document_date=document_date,
        currency=currency,
        total=total,
        blocking_issue_count=_blocking_issue_count(issues),
        updated_at=review.updated_at,
        failure_message=review.failure_message,
    )


def _review_detail(review: ReviewSnapshot) -> ReviewDetailResponse:
    document = _normalized_document(review)
    evidence = _evidence(review)
    issues = _issues(review)
    gl_review = GLReview.model_validate(review.gl_review) if review.gl_review is not None else None
    return ReviewDetailResponse(
        review_id=review.review_id,
        state=review.state,
        document_type=review.document_type,
        original_file=OriginalFileMetadataResponse(
            filename=review.original_filename,
            media_type=review.media_type,
            size_bytes=review.size_bytes,
            page_count=review.page_count,
            uploaded_at=review.uploaded_at,
        ),
        created_at=review.created_at,
        updated_at=review.updated_at,
        processed_at=review.processed_at,
        normalized_document=document,
        evidence=evidence,
        conflicts={
            name: field
            for name, field in evidence.items()
            if field.status is EvidenceStatus.CONFLICT
        },
        issues=issues,
        blocking_issue_count=_blocking_issue_count(issues),
        gl_review=gl_review,
        approval_allowed=(
            review.state is ReviewState.READY_FOR_REVIEW
            and policy_allows_approval(
                issues,
                gl_review.validation if gl_review is not None else None,
            )
        ),
        provider_runs=_mapping(review.provider_runs),
        action_metadata=(
            _mapping(review.action_metadata) if review.action_metadata is not None else None
        ),
        failure_message=review.failure_message,
    )


def _normalized_document(
    review: ReviewSnapshot,
) -> InvoiceDocument | ReceiptDocument | None:
    if review.normalized is None:
        return None
    return _DOCUMENT_ADAPTER.validate_python(review.normalized)


def _evidence(review: ReviewSnapshot) -> dict[str, FieldEvidence[object]]:
    if not isinstance(review.evidence, Mapping):
        return {}
    return {
        str(name): FieldEvidence[object].model_validate(value)
        for name, value in review.evidence.items()
    }


def _issues(review: ReviewSnapshot) -> list[DocumentIssue]:
    if not isinstance(review.issues, list):
        return []
    return [DocumentIssue.model_validate(issue) for issue in review.issues]


def _blocking_issue_count(issues: list[DocumentIssue]) -> int:
    return sum(issue.severity is IssueSeverity.ERROR for issue in issues)


def _mapping(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _storage_error() -> ApiError:
    return ApiError(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "storage_failure",
        "The local review data could not be read or updated.",
    )
