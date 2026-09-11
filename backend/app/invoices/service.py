from __future__ import annotations

from datetime import UTC, datetime

from app.accounting.catalog import get_northstar_gl_catalog, validate_gl_selection
from app.accounting.models import GLReview, GLSelection
from app.document_review.models import (
    DocumentIssue,
    DocumentType,
    IssueSeverity,
    MergedExtractionResult,
    NormalizedFinancialDocument,
    PrimaryExtractionResult,
    ReviewState,
)
from app.document_review.reconciliation import merge_extractions
from app.invoices.repository import InvoiceReviewRepository, ReviewSnapshot
from app.invoices.storage import LocalFileStorage, StoredFile
from app.invoices.validation import invoice_duplicate_key, validate_document
from app.providers.paddleocr import PaddleOCRParser
from app.providers.qwen import QwenVLMProvider


class InvoiceReviewService:
    """Coordinate one synchronous local review from upload through persistence."""

    def __init__(
        self,
        *,
        repository: InvoiceReviewRepository,
        storage: LocalFileStorage,
        primary_parser: PaddleOCRParser,
        vlm_provider: QwenVLMProvider,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._primary_parser = primary_parser
        self._vlm_provider = vlm_provider

    def upload_document(
        self,
        *,
        original_filename: str,
        media_type: str,
        content: bytes,
        uploaded_at: datetime | None = None,
    ) -> ReviewSnapshot:
        stored: StoredFile | None = None
        try:
            stored = self._storage.save(media_type, content)
            return self._repository.create_uploaded_review(
                storage_key=stored.storage_key,
                original_filename=original_filename,
                media_type=stored.media_type,
                size_bytes=stored.size_bytes,
                uploaded_at=uploaded_at or datetime.now(UTC),
            )
        except Exception:
            if stored is not None:
                try:
                    self._storage.delete(stored.storage_key)
                except (OSError, ValueError):
                    pass
            raise

    def process_review(self, review_id: str) -> ReviewSnapshot:
        review = self._repository.get(review_id)
        if review is None:
            raise KeyError(f"review not found: {review_id}")
        if review.state not in {ReviewState.UPLOADED, ReviewState.FAILED}:
            raise ValueError(f"review cannot be processed from state {review.state.value}")

        self._repository.save_processing_result(
            review_id,
            state=ReviewState.PROCESSING,
            normalized_document=None,
            evidence=None,
            issues=None,
            gl_review=None,
            provider_runs={},
            duplicate_key=None,
            page_count=review.page_count,
        )

        provider_runs: dict[str, object] = {}
        primary: PrimaryExtractionResult | None = None
        merged: MergedExtractionResult | None = None
        issues: list[DocumentIssue] | None = None
        gl_review: GLReview | None = None
        duplicate_key: str | None = None

        try:
            content = self._storage.read(review.storage_key)
        except Exception as error:
            return self._save_failure(
                review,
                stage="Reading the original document",
                error=error,
                provider_runs=provider_runs,
            )

        try:
            classification = self._vlm_provider.classify_document(
                filename=review.original_filename,
                media_type=review.media_type,
                content=content,
            )
            provider_runs["classification"] = classification
        except Exception as error:
            return self._save_failure(
                review,
                stage="Document classification",
                error=error,
                provider_runs=provider_runs,
            )

        try:
            primary = self._primary_parser.parse(
                filename=review.original_filename,
                media_type=review.media_type,
                content=content,
                uploaded_at=review.uploaded_at,
            )
            provider_runs["primary"] = primary.provider_run
        except Exception as error:
            return self._save_failure(
                review,
                stage="Primary document parsing",
                error=error,
                provider_runs=provider_runs,
            )

        if classification.classification.document_type.value != primary.document.document_type:
            conflict = DocumentIssue(
                code="document_type_conflict",
                severity=IssueSeverity.ERROR,
                message=(
                    "Independent document classification disagrees with the primary parser. "
                    "Retry processing after checking the document and local providers."
                ),
            )
            return self._save_failure(
                review,
                stage="Document type reconciliation",
                error=None,
                normalized_document=primary.document,
                evidence=primary.evidence,
                issues=[conflict],
                provider_runs=provider_runs,
                duplicate_key=self._duplicate_key(primary.document),
                page_count=primary.document.source.page_count,
            )

        try:
            vlm = self._vlm_provider.review_document(
                filename=review.original_filename,
                media_type=review.media_type,
                content=content,
                uploaded_at=review.uploaded_at,
                document_type=classification.classification.document_type,
            )
            provider_runs["vlm_review"] = vlm.provider_run
            merged = merge_extractions(primary, vlm)
        except Exception as error:
            return self._save_failure(
                review,
                stage="Independent VLM review and merge",
                error=error,
                normalized_document=primary.document,
                evidence=primary.evidence,
                provider_runs=provider_runs,
                duplicate_key=self._duplicate_key(primary.document),
                page_count=primary.document.source.page_count,
            )

        duplicate_key = self._duplicate_key(merged.document)
        duplicate_exists = bool(
            duplicate_key
            and any(
                existing.review_id != review.review_id
                for existing in self._repository.find_by_duplicate_key(duplicate_key)
            )
        )

        try:
            issues = validate_document(
                merged.document,
                merged.evidence,
                duplicate_key_exists=duplicate_exists,
            )
        except Exception as error:
            return self._save_failure(
                review,
                stage="Deterministic policy validation",
                error=error,
                normalized_document=merged.document,
                evidence=merged.evidence,
                provider_runs=provider_runs,
                duplicate_key=duplicate_key,
                page_count=merged.document.source.page_count,
            )

        try:
            gl_result = self._vlm_provider.suggest_gl(
                document=merged.document,
                catalog=get_northstar_gl_catalog(),
            )
            provider_runs["gl_suggestion"] = gl_result
            gl_review = GLReview(
                suggestion=gl_result.suggestion,
                selection=GLSelection(account_id=None),
                validation=validate_gl_selection(None),
            )
        except Exception as error:
            return self._save_failure(
                review,
                stage="GL account suggestion",
                error=error,
                normalized_document=merged.document,
                evidence=merged.evidence,
                issues=issues,
                provider_runs=provider_runs,
                duplicate_key=duplicate_key,
                page_count=merged.document.source.page_count,
            )

        return self._repository.save_processing_result(
            review_id,
            state=ReviewState.READY_FOR_REVIEW,
            normalized_document=merged.document,
            evidence=merged.evidence,
            issues=issues,
            gl_review=gl_review,
            provider_runs=provider_runs,
            duplicate_key=duplicate_key,
            page_count=merged.document.source.page_count,
            processed_at=datetime.now(UTC),
        )

    @staticmethod
    def _duplicate_key(document: NormalizedFinancialDocument) -> str | None:
        if document.document_type != DocumentType.INVOICE.value:
            return None
        return invoice_duplicate_key(document)

    def _save_failure(
        self,
        review: ReviewSnapshot,
        *,
        stage: str,
        error: Exception | None,
        normalized_document: NormalizedFinancialDocument | None = None,
        evidence: object | None = None,
        issues: object | None = None,
        gl_review: GLReview | None = None,
        provider_runs: object | None = None,
        duplicate_key: str | None = None,
        page_count: int | None = None,
    ) -> ReviewSnapshot:
        if error is None:
            failure_message = (
                stage + " found a conflict. Retry processing after checking the document."
            )
        else:
            failure_message = stage + " failed. Check the local provider setup and try again."
        return self._repository.save_processing_result(
            review.review_id,
            state=ReviewState.FAILED,
            normalized_document=normalized_document,
            evidence=evidence,
            issues=issues,
            gl_review=gl_review,
            provider_runs=provider_runs,
            duplicate_key=duplicate_key,
            page_count=page_count if page_count is not None else review.page_count,
            processed_at=datetime.now(UTC),
            failure_message=failure_message,
        )
