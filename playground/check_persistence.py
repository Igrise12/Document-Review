from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from pydantic import ValidationError

from app.accounting.models import GLReview, GLSuggestion
from app.config import Settings
from app.document_review.models import (
    CurrencyCode,
    EvidenceSource,
    EvidenceStatus,
    FieldEvidence,
    InvoiceDocument,
    InvoiceFields,
    ProviderRunMetadata,
    ReviewState,
    SourceDocumentMetadata,
    VatId,
)
from app.invoices.repository import InvoiceReviewRepository
from app.invoices.storage import (
    MAX_UPLOAD_BYTES,
    LocalFileStorage,
    UploadValidationError,
    validate_upload,
)

PDF_BYTES = b"%PDF-1.7\nfictional invoice\n%%EOF"
PNG_BYTES = b"\x89PNG\r\n\x1a\nfictional png"


def expect_upload_error(media_type: str, content: bytes) -> None:
    try:
        validate_upload(media_type, content)
    except UploadValidationError:
        return
    raise AssertionError("invalid upload should be rejected")


def run_checks() -> None:
    try:
        Settings(_env_file=None, local_vlm_runtime="invalid")
    except ValidationError:
        pass
    else:
        raise AssertionError("invalid provider runtime should be rejected")

    expect_upload_error("image/png", PDF_BYTES)
    expect_upload_error("application/octet-stream", PDF_BYTES)
    expect_upload_error("application/pdf", b"not a PDF")
    expect_upload_error("application/pdf", b"%PDF-" + b"x" * MAX_UPLOAD_BYTES)

    with TemporaryDirectory() as temporary_directory:
        root = Path(temporary_directory)
        settings = Settings(_env_file=None, invoice_review_data_dir=root / "data")
        storage = LocalFileStorage(settings.uploads_dir)
        stored_pdf = storage.save("application/pdf", PDF_BYTES)
        stored_png = storage.save("image/png", PNG_BYTES)
        assert storage.read(stored_pdf.storage_key) == PDF_BYTES
        assert storage.read(stored_png.storage_key) == PNG_BYTES

        repository = InvoiceReviewRepository(settings.database_path)
        repository.initialize()
        try:
            first = repository.create_uploaded_review(
                storage_key=stored_pdf.storage_key,
                original_filename="sample.pdf",
                media_type=stored_pdf.media_type,
                size_bytes=stored_pdf.size_bytes,
                uploaded_at=datetime(2026, 9, 11, tzinfo=UTC),
            )
            second = repository.create_uploaded_review(
                storage_key=stored_png.storage_key,
                original_filename="sample.png",
                media_type=stored_png.media_type,
                size_bytes=stored_png.size_bytes,
                uploaded_at=datetime(2026, 9, 12, tzinfo=UTC),
                page_count=1,
            )
            assert first.state is ReviewState.UPLOADED
            assert len(repository.list_reviews()) == 2

            document = InvoiceDocument(
                source=SourceDocumentMetadata(
                    filename="sample.pdf",
                    media_type="application/pdf",
                    size_bytes=len(PDF_BYTES),
                    page_count=1,
                    uploaded_at=datetime(2026, 9, 11, tzinfo=UTC),
                ),
                fields=InvoiceFields(
                    vendor_name="Bright Spark Europe S.A.S.",
                    vendor_vat_id=VatId(
                        normalized="FR61954506077", display="FR 61 954 06077"
                    ),
                    customer_name="Northstar Facilities B.V.",
                    customer_vat_id=VatId(
                        normalized="NL00449544B01", display="NL00449544B01"
                    ),
                    invoice_number="EN-2026-1001",
                    invoice_date="2026-07-01",
                    currency=CurrencyCode(code="EUR", display="EUR"),
                    subtotal=Decimal("100.00"),
                    total_tax=Decimal("21.00"),
                    invoice_total=Decimal("121.00"),
                ),
            )
            evidence = {
                "invoice_total": FieldEvidence[Decimal](
                    value=Decimal("121.00"),
                    confidence=Decimal("0.95"),
                    source=EvidenceSource.PRIMARY,
                    status=EvidenceStatus.PRIMARY,
                )
            }
            issues = [{"code": "purchase_order_missing", "severity": "warning"}]
            gl_review = GLReview(
                suggestion=GLSuggestion(
                    account_id="6100",
                    rationale="Facilities cleaning supplier.",
                    confidence=Decimal("0.90"),
                )
            )
            provider_run = ProviderRunMetadata(
                provider="fictional-provider",
                model_name="fictional-model",
                model_version="1",
                prompt_version="1",
                schema_version="1",
                runtime="local",
                started_at=datetime(2026, 9, 11, tzinfo=UTC),
            )
            ready = repository.save_processing_result(
                first.review_id,
                state=ReviewState.READY_FOR_REVIEW,
                normalized_document=document,
                evidence=evidence,
                issues=issues,
                gl_review=gl_review,
                provider_runs=[provider_run],
                duplicate_key="fr61954506077|en-2026-1001",
                page_count=1,
                processed_at=datetime(2026, 9, 11, 0, 1, tzinfo=UTC),
            )
            assert ready.state is ReviewState.READY_FOR_REVIEW
            assert ready.document_type.value == "invoice"
            assert ready.normalized is not None
            assert ready.evidence is not None
            assert ready.gl_review is not None
            assert len(repository.find_by_duplicate_key("fr61954506077|en-2026-1001")) == 1

            approved = repository.update_state(
                first.review_id,
                state=ReviewState.APPROVED,
                action_metadata={"actor": "Maya"},
            )
            assert approved.state is ReviewState.APPROVED
            assert approved.action_metadata == {"actor": "Maya"}

            deleted_key = repository.delete_review(first.review_id)
            assert deleted_key == stored_pdf.storage_key
            assert repository.get(first.review_id) is None
            assert not repository.find_by_duplicate_key("fr61954506077|en-2026-1001")
            storage.delete(deleted_key)
            assert not (settings.uploads_dir / stored_pdf.storage_key).exists()
            assert (settings.uploads_dir / stored_png.storage_key).exists()
            assert repository.get(second.review_id) is not None
        finally:
            repository.close()
            storage.delete(stored_png.storage_key)


if __name__ == "__main__":
    run_checks()
    print("PASS: local configuration, file storage, and SQLite persistence")
