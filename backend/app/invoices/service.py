from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from functools import cached_property

from pydantic import TypeAdapter

from app.accounting.catalog import get_northstar_gl_catalog, validate_gl_selection
from app.accounting.models import GLReview, GLSelection
from app.correction_email.models import CorrectionDraftResult
from app.document_review.models import (
    DocumentIssue,
    DocumentType,
    FieldEvidence,
    InvoiceDocument,
    IssueSeverity,
    MergedExtractionResult,
    NormalizedFinancialDocument,
    PrimaryExtractionResult,
    ReceiptDocument,
    ReviewState,
)
from app.document_review.reconciliation import merge_extractions
from app.invoices.repository import InvoiceReviewRepository, ReviewSnapshot
from app.invoices.storage import LocalFileStorage, StoredFile
from app.invoices.validation import approval_allowed, invoice_duplicate_key, validate_document
from app.providers.paddleocr import PaddleOCRParser
from app.providers.qwen import QwenVLMProvider

type PrimaryParserFactory = Callable[[], PaddleOCRParser]
type VLMProviderFactory = Callable[[], QwenVLMProvider]
_DOCUMENT_ADAPTER = TypeAdapter(NormalizedFinancialDocument)


class ReviewWorkflowError(ValueError):
    """Raised when a requested review transition is not allowed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ReviewNotFoundError(LookupError):
    """Raised when a requested review does not exist."""


class CorrectionDraftProviderError(RuntimeError):
    """Raised when the local VLM cannot produce an on-demand draft."""


class InvoiceReviewService:
    """Coordinate one synchronous local review from upload through persistence."""

    def __init__(
        self,
        *,
        repository: InvoiceReviewRepository,
        storage: LocalFileStorage,
        primary_parser_factory: PrimaryParserFactory,
        vlm_provider_factory: VLMProviderFactory,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._primary_parser_factory = primary_parser_factory
        self._vlm_provider_factory = vlm_provider_factory

    @cached_property
    def _primary_parser(self) -> PaddleOCRParser:
        return self._primary_parser_factory()

    @cached_property
    def _vlm_provider(self) -> QwenVLMProvider:
        return self._vlm_provider_factory()

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
        review = self.get_review(review_id)
        if review.state not in {ReviewState.UPLOADED, ReviewState.FAILED}:
            raise ReviewWorkflowError(
                "invalid_review_state",
                f"Review cannot be processed from state {review.state.value}.",
            )

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

    def list_reviews(self) -> list[ReviewSnapshot]:
        return self._repository.list_reviews()

    def get_review(self, review_id: str) -> ReviewSnapshot:
        review = self._repository.get(review_id)
        if review is None:
            raise ReviewNotFoundError(f"review not found: {review_id}")
        return review

    def read_original(self, review_id: str) -> tuple[ReviewSnapshot, bytes]:
        review = self.get_review(review_id)
        return review, self._storage.read(review.storage_key)

    def select_gl(self, review_id: str, account_id: str | None) -> ReviewSnapshot:
        review = self._ready_review(review_id, "select a GL account")
        gl_review = self._gl_review(review)
        normalized_account_id = account_id.strip() if account_id is not None else None
        validation = validate_gl_selection(normalized_account_id)
        if account_id is not None and not validation.valid:
            raise ReviewWorkflowError(
                "invalid_gl_selection",
                validation.reason or "Select a valid Northstar GL account.",
            )
        return self._repository.update_gl_review(
            review_id,
            gl_review.model_copy(
                update={
                    "selection": GLSelection(account_id=validation.account_id),
                    "validation": validation,
                }
            ),
        )

    def approve_review(self, review_id: str) -> ReviewSnapshot:
        review = self._ready_review(review_id, "approve")
        issues = self._issues(review)
        gl_review = self._gl_review(review)
        if not approval_allowed(issues, gl_review.validation):
            raise ReviewWorkflowError(
                "approval_blocked",
                "Resolve blocking issues and select a valid Northstar GL account before approval.",
            )
        return self._record_action(review_id, ReviewState.APPROVED, "approved")

    def reject_review(self, review_id: str) -> ReviewSnapshot:
        self._ready_review(review_id, "reject")
        return self._record_action(review_id, ReviewState.REJECTED, "rejected")

    def request_correction(self, review_id: str) -> ReviewSnapshot:
        review = self._ready_review(review_id, "request a correction")
        if not self._blocking_issues(review):
            raise ReviewWorkflowError(
                "correction_not_available",
                "A correction request requires at least one blocking issue.",
            )
        return self._record_action(
            review_id,
            ReviewState.CORRECTION_REQUESTED,
            "correction_requested",
        )

    def draft_correction(self, review_id: str) -> CorrectionDraftResult:
        review = self.get_review(review_id)
        if review.state not in {
            ReviewState.READY_FOR_REVIEW,
            ReviewState.CORRECTION_REQUESTED,
        }:
            raise ReviewWorkflowError(
                "invalid_review_state",
                f"A correction draft is not available from state {review.state.value}.",
            )
        issues = self._blocking_issues(review)
        if not issues:
            raise ReviewWorkflowError(
                "correction_not_available",
                "A correction draft requires at least one blocking issue.",
            )
        document = self._document(review)
        evidence = self._evidence(review)
        try:
            return self._vlm_provider.draft_correction(
                document=document,
                issues=issues,
                evidence=evidence,
            )
        except Exception as error:
            raise CorrectionDraftProviderError(
                "The local VLM could not produce a correction draft."
            ) from error

    def delete_review(self, review_id: str) -> None:
        storage_key = self._repository.delete_review(review_id)
        if storage_key is None:
            raise ReviewNotFoundError(f"review not found: {review_id}")
        # ponytail: local SQLite/file deletion is not atomic; add tombstones only if
        # real cleanup failures justify recovery machinery.
        self._storage.delete(storage_key)

    def _ready_review(self, review_id: str, action: str) -> ReviewSnapshot:
        review = self.get_review(review_id)
        if review.state is not ReviewState.READY_FOR_REVIEW:
            raise ReviewWorkflowError(
                "invalid_review_state",
                f"Review cannot {action} from state {review.state.value}.",
            )
        return review

    def _record_action(
        self,
        review_id: str,
        state: ReviewState,
        action: str,
    ) -> ReviewSnapshot:
        return self._repository.update_state(
            review_id,
            state=state,
            action_metadata={
                "action": action,
                "recorded_at": datetime.now(UTC).isoformat(),
            },
        )

    @staticmethod
    def _document(review: ReviewSnapshot) -> InvoiceDocument | ReceiptDocument:
        if review.normalized is None:
            raise ReviewWorkflowError(
                "correction_not_available",
                "The review has no normalized document for a correction draft.",
            )
        return _DOCUMENT_ADAPTER.validate_python(review.normalized)

    @staticmethod
    def _evidence(review: ReviewSnapshot) -> dict[str, FieldEvidence[object]]:
        if not isinstance(review.evidence, Mapping):
            raise ReviewWorkflowError(
                "correction_not_available",
                "The review has no evidence for a correction draft.",
            )
        return {
            str(name): FieldEvidence[object].model_validate(evidence)
            for name, evidence in review.evidence.items()
        }

    @staticmethod
    def _issues(review: ReviewSnapshot) -> list[DocumentIssue]:
        if not isinstance(review.issues, list):
            return []
        return [DocumentIssue.model_validate(issue) for issue in review.issues]

    @classmethod
    def _blocking_issues(cls, review: ReviewSnapshot) -> list[DocumentIssue]:
        return [
            issue
            for issue in cls._issues(review)
            if issue.severity is IssueSeverity.ERROR
        ]

    @staticmethod
    def _gl_review(review: ReviewSnapshot) -> GLReview:
        if review.gl_review is None:
            raise ReviewWorkflowError(
                "invalid_review_state",
                "The review has no GL review data.",
            )
        return GLReview.model_validate(review.gl_review)

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
