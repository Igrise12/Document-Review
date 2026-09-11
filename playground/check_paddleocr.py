from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import cast

from app.config import Settings
from app.document_review.models import DocumentType, InvoiceDocument, ReceiptDocument
from app.providers.paddleocr import MediaType, PaddleOCRParser

REPO_ROOT = Path(__file__).resolve().parents[1]
SAMPLE_DIR = REPO_ROOT / "samples/generated"
MEDIA_TYPES: dict[str, MediaType] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def main() -> None:
    settings = Settings(_env_file=None, paddleocr_engine="paddle", paddleocr_device="cpu")
    parser = PaddleOCRParser(settings)

    invoice = parser.parse(
        filename="01-en-happy-classic.pdf",
        media_type="application/pdf",
        content=(SAMPLE_DIR / "01-en-happy-classic.pdf").read_bytes(),
        uploaded_at=datetime.now(UTC),
    )
    assert invoice.document.document_type == DocumentType.INVOICE
    invoice_document = cast(InvoiceDocument, invoice.document)
    assert invoice_document.fields.vendor_name == "Bright Spark Europe S.A.S."
    assert invoice_document.fields.invoice_total == Decimal("121.00")
    assert invoice.evidence["invoice_total"].source is not None
    assert invoice.evidence["invoice_total"].page == 1
    assert invoice.evidence["invoice_total"].text_context
    print("PASS 01-en-happy-classic.pdf: invoice, vendor, total 121.00, primary evidence")

    receipt_path = SAMPLE_DIR / "13-nl-fuel-receipt.png"
    receipt = parser.parse(
        filename=receipt_path.name,
        media_type=MEDIA_TYPES[receipt_path.suffix],
        content=receipt_path.read_bytes(),
        uploaded_at=datetime.now(UTC),
    )
    assert receipt.document.document_type == DocumentType.RECEIPT
    receipt_document = cast(ReceiptDocument, receipt.document)
    assert receipt_document.fields.total == Decimal("60.50")
    assert receipt_document.fields.vat_total == Decimal("10.50")
    print("PASS 13-nl-fuel-receipt.png: receipt, total 60.50, VAT 10.50")

    multipage_path = SAMPLE_DIR / "12-en-two-page.pdf"
    multipage = parser.parse(
        filename=multipage_path.name,
        media_type="application/pdf",
        content=multipage_path.read_bytes(),
        uploaded_at=datetime.now(UTC),
    )
    assert multipage.document.source.page_count == 2
    assert any(evidence.page == 2 for evidence in multipage.evidence.values())
    print("PASS 12-en-two-page.pdf: two pages combined with page evidence")

    print("PaddleOCR adapter smoke check passed.")


if __name__ == "__main__":
    main()
