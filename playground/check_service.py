"""Check the synchronous review service with fictional in-memory providers."""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from check_document_types import load_manifest, normalized_document

from app.accounting.models import GLAccount, GLSuggestion, GLSuggestionResult
from app.config import Settings
from app.document_review.models import (
    DocumentClassification,
    DocumentClassificationResult,
    DocumentType,
    EvidenceSource,
    EvidenceStatus,
    FieldEvidence,
    InvoiceDocument,
    InvoiceFields,
    PrimaryExtractionResult,
    ProviderRunMetadata,
    ReviewState,
    VLMExtractionResult,
)
from app.invoices.repository import InvoiceReviewRepository
from app.invoices.service import InvoiceReviewService
from app.invoices.storage import LocalFileStorage

PDF_BYTES = b"%PDF-1.7\nfictional invoice\n%%EOF"
UPLOADED_AT = datetime(2026, 9, 11, tzinfo=UTC)


def _provider_run(provider: str) -> ProviderRunMetadata:
    return ProviderRunMetadata(
        provider=provider,
        model_name="fictional-model",
        model_version="1",
        prompt_version="1",
        schema_version="1",
        runtime="offline",
        started_at=UPLOADED_AT,
        finished_at=UPLOADED_AT,
        duration_ms=1,
    )


def _primary_result(document: InvoiceDocument) -> PrimaryExtractionResult:
    evidence: dict[str, FieldEvidence[object]] = {}
    for field_name in type(document.fields).model_fields:
        value = getattr(document.fields, field_name)
        if value is None:
            evidence[field_name] = FieldEvidence(status=EvidenceStatus.MISSING)
        else:
            evidence[field_name] = FieldEvidence(
                value=value,
                confidence=Decimal("0.92"),
                source=EvidenceSource.PRIMARY,
                status=EvidenceStatus.PRIMARY,
            )
    return PrimaryExtractionResult(
        document=document,
        evidence=evidence,
        provider_run=_provider_run("paddleocr"),
    )


def _vlm_result(document: InvoiceDocument) -> VLMExtractionResult:
    confidence = {
        field_name: Decimal("0.84")
        for field_name in type(document.fields).model_fields
        if getattr(document.fields, field_name) is not None
    }
    return VLMExtractionResult(
        document=document,
        field_confidence=confidence,
        provider_run=_provider_run("qwen"),
    )


class FakePrimaryParser:
    def __init__(self, document: InvoiceDocument, calls: list[str]) -> None:
        self.document = document
        self.calls = calls

    def parse(self, **kwargs: object) -> PrimaryExtractionResult:
        assert kwargs["content"] == PDF_BYTES
        self.calls.append("primary")
        return _primary_result(self.document)


class FakeVLMProvider:
    def __init__(
        self,
        *,
        vlm_document: InvoiceDocument,
        calls: list[str],
        classification_type: DocumentType = DocumentType.INVOICE,
        fail_gl: bool = False,
    ) -> None:
        self.vlm_document = vlm_document
        self.calls = calls
        self.classification_type = classification_type
        self.fail_gl = fail_gl

    def classify_document(self, **kwargs: object) -> DocumentClassificationResult:
        assert kwargs["content"] == PDF_BYTES
        self.calls.append("classification")
        return DocumentClassificationResult(
            classification=DocumentClassification(
                document_type=self.classification_type,
                confidence=Decimal("0.96"),
                reasoning="Fictional offline classification.",
            ),
            provider_run=_provider_run("qwen-classifier"),
        )

    def review_document(self, **kwargs: object) -> VLMExtractionResult:
        assert kwargs["content"] == PDF_BYTES
        assert kwargs["document_type"] is DocumentType.INVOICE
        self.calls.append("review")
        return _vlm_result(self.vlm_document)

    def suggest_gl(
        self,
        *,
        document: InvoiceDocument,
        catalog: tuple[GLAccount, ...],
    ) -> GLSuggestionResult:
        assert document.document_type == "invoice"
        assert len(catalog) == 6
        self.calls.append("gl")
        if self.fail_gl:
            raise RuntimeError("fictional GL provider failure")
        return GLSuggestionResult(
            suggestion=GLSuggestion(
                account_id="6100",
                rationale="Fictional cleaning supplier.",
                confidence=Decimal("0.90"),
            ),
            provider_run=_provider_run("qwen-gl"),
        )


def _service(
    root: Path,
    *,
    primary_document: InvoiceDocument,
    vlm_document: InvoiceDocument,
    calls: list[str],
    classification_type: DocumentType = DocumentType.INVOICE,
    fail_gl: bool = False,
) -> tuple[InvoiceReviewService, InvoiceReviewRepository, Settings, FakeVLMProvider]:
    settings = Settings(_env_file=None, invoice_review_data_dir=root / "data")
    storage = LocalFileStorage(settings.uploads_dir)
    repository = InvoiceReviewRepository(settings.database_path)
    repository.initialize()
    fake_vlm = FakeVLMProvider(
        vlm_document=vlm_document,
        calls=calls,
        classification_type=classification_type,
        fail_gl=fail_gl,
    )
    service = InvoiceReviewService(
        repository=repository,
        storage=storage,
        primary_parser=FakePrimaryParser(primary_document, calls),  # type: ignore[arg-type]
        vlm_provider=fake_vlm,  # type: ignore[arg-type]
    )
    return service, repository, settings, fake_vlm


def run_checks() -> None:
    source = normalized_document(load_manifest()[0])
    assert isinstance(source, InvoiceDocument)
    primary_document = source.model_copy(
        update={
            "fields": source.fields.model_copy(
                update={"invoice_number": None, "purchase_order": None}
            )
        }
    )
    vlm_fields = source.fields.model_dump(mode="python")
    vlm_fields["purchase_order"] = None
    vlm_document = source.model_copy(update={"fields": InvoiceFields(**vlm_fields)})

    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        calls: list[str] = []
        service, repository, settings, _ = _service(
            root,
            primary_document=primary_document,
            vlm_document=vlm_document,
            calls=calls,
        )
        try:
            review = service.upload_document(
                original_filename="fictional.pdf",
                media_type="application/pdf",
                content=PDF_BYTES,
                uploaded_at=UPLOADED_AT,
            )
            processed = service.process_review(review.review_id)
            assert calls == ["classification", "primary", "review", "gl"]
            assert processed.state is ReviewState.READY_FOR_REVIEW
            assert processed.normalized["fields"]["invoice_number"] == "EN-2026-1001"
            assert processed.issues[0]["code"] == "purchase_order_missing"
            assert processed.gl_review["suggestion"]["account_id"] == "6100"
            assert processed.gl_review["selection"]["account_id"] is None
            assert processed.gl_review["validation"]["valid"] is False
            assert set(processed.provider_runs) == {
                "classification",
                "primary",
                "vlm_review",
                "gl_suggestion",
            }
        finally:
            repository.close()
            LocalFileStorage(settings.uploads_dir).delete(review.storage_key)

    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        calls = []
        service, repository, settings, _ = _service(
            root,
            primary_document=primary_document,
            vlm_document=vlm_document,
            calls=calls,
            classification_type=DocumentType.RECEIPT,
        )
        try:
            review = service.upload_document(
                original_filename="conflict.pdf",
                media_type="application/pdf",
                content=PDF_BYTES,
                uploaded_at=UPLOADED_AT,
            )
            failed = service.process_review(review.review_id)
            assert calls == ["classification", "primary"]
            assert failed.state is ReviewState.FAILED
            assert failed.normalized is not None
            assert failed.issues[0]["code"] == "document_type_conflict"
            assert failed.failure_message.startswith("Document type reconciliation")
        finally:
            repository.close()
            LocalFileStorage(settings.uploads_dir).delete(review.storage_key)

    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        calls = []
        service, repository, settings, fake_vlm = _service(
            root,
            primary_document=primary_document,
            vlm_document=vlm_document,
            calls=calls,
            fail_gl=True,
        )
        try:
            review = service.upload_document(
                original_filename="gl-failure.pdf",
                media_type="application/pdf",
                content=PDF_BYTES,
                uploaded_at=UPLOADED_AT,
            )
            failed = service.process_review(review.review_id)
            assert failed.state is ReviewState.FAILED
            assert failed.normalized is not None
            assert failed.evidence is not None
            assert set(failed.provider_runs) == {"classification", "primary", "vlm_review"}
            assert failed.failure_message.startswith("GL account suggestion")
            fake_vlm.fail_gl = False
            retried = service.process_review(review.review_id)
            assert retried.state is ReviewState.READY_FOR_REVIEW
            assert retried.failure_message is None
        finally:
            repository.close()
            LocalFileStorage(settings.uploads_dir).delete(review.storage_key)

    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        calls = []
        service, repository, settings, _ = _service(
            root,
            primary_document=primary_document,
            vlm_document=vlm_document,
            calls=calls,
        )
        try:
            try:
                service.upload_document(
                    original_filename="",
                    media_type="application/pdf",
                    content=PDF_BYTES,
                    uploaded_at=UPLOADED_AT,
                )
            except ValueError:
                pass
            else:
                raise AssertionError("repository upload validation should fail")
            assert not any(settings.uploads_dir.iterdir())
        finally:
            repository.close()


if __name__ == "__main__":
    run_checks()
    print("PASS: service order, partial failures, retry state, and upload cleanup")
