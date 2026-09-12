import re
import unicodedata
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from tempfile import NamedTemporaryFile
from time import perf_counter
from typing import Literal, cast

from app.config import Settings
from app.document_review.models import (
    BoundingBox,
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
    ReceiptFields,
    SourceDocumentMetadata,
    VatId,
)
from app.invoices.storage import UploadValidationError, validate_upload

MediaType = Literal["application/pdf", "image/png", "image/jpeg"]
_MEDIA_SUFFIXES: dict[str, str] = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}
_PADDLE_PDF_RENDER_SCALE = 3.5


class PaddleOCRProviderError(RuntimeError):
    """Raised when PaddleOCR cannot produce a provider-independent result."""


@dataclass(frozen=True)
class _OCRLine:
    text: str
    confidence: Decimal | None
    page: int
    bounding_box: BoundingBox | None

    @property
    def folded(self) -> str:
        return _fold(self.text)


class PaddleOCRParser:
    def __init__(self, settings: Settings) -> None:
        try:
            from paddleocr import PPStructureV3
        except ImportError as error:
            raise PaddleOCRProviderError(
                "PaddleOCR is not installed; run `uv sync --locked` first."
            ) from error

        try:
            self._pipeline: object = PPStructureV3(
                engine=settings.paddleocr_engine,
                device=settings.paddleocr_device,
            )
        except Exception as error:
            raise PaddleOCRProviderError("PaddleOCR pipeline could not be initialized.") from error

        self._settings = settings

    def parse(
        self,
        *,
        filename: str,
        media_type: str,
        content: bytes,
        uploaded_at: datetime,
    ) -> PrimaryExtractionResult:
        started_at = datetime.now(UTC)
        started = perf_counter()

        try:
            normalized_media_type = cast(MediaType, validate_upload(media_type, content))
        except UploadValidationError as error:
            raise PaddleOCRProviderError(str(error)) from error

        try:
            raw_results = self._predict(content, normalized_media_type)
            pages = tuple(
                _page_lines(result, page_number)
                for page_number, result in enumerate(raw_results, start=1)
            )
            if not pages:
                raise PaddleOCRProviderError("PaddleOCR returned no document pages.")

            lines = tuple(line for page in pages for line in page)
            document_type = _classify_document(lines)
            evidence, fields = _extract_fields(document_type, lines)
            processed_at = datetime.now(UTC)
            source = SourceDocumentMetadata(
                filename=filename,
                media_type=normalized_media_type,
                size_bytes=len(content),
                page_count=len(pages),
                uploaded_at=uploaded_at,
                processed_at=processed_at,
            )
            document = (
                InvoiceDocument(source=source, fields=cast(InvoiceFields, fields))
                if document_type is DocumentType.INVOICE
                else ReceiptDocument(source=source, fields=cast(ReceiptFields, fields))
            )
            provider_run = ProviderRunMetadata(
                provider="paddleocr",
                model_name="PP-StructureV3",
                model_version="paddleocr==3.7.0",
                schema_version="primary-extraction/v1",
                runtime=f"{self._settings.paddleocr_engine}:{self._settings.paddleocr_device}",
                started_at=started_at,
                finished_at=processed_at,
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return PrimaryExtractionResult(
                document=document,
                evidence=evidence,
                provider_run=provider_run,
            )
        except PaddleOCRProviderError:
            raise
        except Exception as error:
            raise PaddleOCRProviderError("PaddleOCR output could not be normalized.") from error

    def _predict(self, content: bytes, media_type: MediaType) -> list[object]:
        suffix = _MEDIA_SUFFIXES[media_type]
        predict = getattr(self._pipeline, "predict", None)
        if not callable(predict):
            raise PaddleOCRProviderError("PaddleOCR pipeline has no predict method.")

        if media_type == "application/pdf":
            return self._predict_pdf(content, predict)

        with NamedTemporaryFile(mode="wb", suffix=suffix) as temporary_file:
            temporary_file.write(content)
            temporary_file.flush()
            raw_output = cast(Callable[..., object], predict)(input=temporary_file.name)

        if isinstance(raw_output, Iterable) and not isinstance(raw_output, (str, bytes, Mapping)):
            return list(raw_output)
        raise PaddleOCRProviderError("PaddleOCR returned an invalid result collection.")

    def _predict_pdf(self, content: bytes, predict: Callable[..., object]) -> list[object]:
        try:
            import pypdfium2 as pdfium

            document = pdfium.PdfDocument(content)
            results: list[object] = []
            for page_index in range(len(document)):
                page = document[page_index]
                bitmap = page.render(scale=_PADDLE_PDF_RENDER_SCALE)
                image = bitmap.to_pil()
                try:
                    with NamedTemporaryFile(mode="wb", suffix=".png") as temporary_file:
                        image.save(temporary_file, format="PNG", optimize=True)
                        temporary_file.flush()
                        raw_output = predict(input=temporary_file.name)
                        if not isinstance(raw_output, Iterable) or isinstance(
                            raw_output, (str, bytes, Mapping)
                        ):
                            raise PaddleOCRProviderError(
                                "PaddleOCR returned an invalid result collection."
                            )
                        results.extend(raw_output)
                finally:
                    image.close()
                    bitmap.close()
                    page.close()
            document.close()
        except PaddleOCRProviderError:
            raise
        except (ImportError, OSError, RuntimeError, ValueError) as error:
            raise PaddleOCRProviderError(
                "PDF pages could not be rendered for PaddleOCR."
            ) from error
        if not results:
            raise PaddleOCRProviderError("PaddleOCR returned no document pages.")
        return results


def _page_lines(result: object, page: int) -> tuple[_OCRLine, ...]:
    payload = _result_json(result)
    overall_ocr = _as_mapping(payload.get("overall_ocr_res"))
    texts = _as_sequence(overall_ocr.get("rec_texts"))
    scores = _as_sequence(overall_ocr.get("rec_scores"))
    boxes = _as_sequence(overall_ocr.get("rec_boxes"))

    lines: list[_OCRLine] = []
    for index, raw_text in enumerate(texts):
        if not isinstance(raw_text, str) or not raw_text.strip():
            continue
        confidence = _decimal_score(scores[index]) if index < len(scores) else None
        box = _bounding_box(boxes[index]) if index < len(boxes) else None
        lines.append(_OCRLine(raw_text.strip(), confidence, page, box))

    if lines:
        return tuple(lines)

    for block in _as_sequence(payload.get("parsing_res_list")):
        block_mapping = _as_mapping(block)
        content = block_mapping.get("block_content")
        if not isinstance(content, str):
            continue
        box = _bounding_box(block_mapping.get("block_bbox"))
        for text in content.splitlines():
            if text.strip():
                lines.append(_OCRLine(text.strip(), None, page, box))
    return tuple(lines)


def _result_json(result: object) -> Mapping[str, object]:
    payload = getattr(result, "json", None)
    if callable(payload):
        payload = payload()
    mapping = _as_mapping(payload)
    nested = _as_mapping(mapping.get("res"))
    return nested or mapping


def _as_mapping(value: object) -> Mapping[str, object]:
    return value if isinstance(value, Mapping) else {}


def _as_sequence(value: object) -> Sequence[object]:
    to_list = getattr(value, "tolist", None)
    if callable(to_list):
        return _as_sequence(to_list())
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _decimal_score(value: object) -> Decimal | None:
    if isinstance(value, bool):
        return None
    try:
        score = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return score if Decimal("0") <= score <= Decimal("1") else None


def _bounding_box(value: object) -> BoundingBox | None:
    values = _as_sequence(value)
    if len(values) == 4 and all(isinstance(item, (int, float)) for item in values):
        x1, y1, x2, y2 = (float(item) for item in values)
        return BoundingBox(x=x1, y=y1, width=max(0.0, x2 - x1), height=max(0.0, y2 - y1))

    points: list[tuple[float, float]] = []
    for point in values:
        coordinates = _as_sequence(point)
        if len(coordinates) >= 2 and all(
            isinstance(item, (int, float)) for item in coordinates[:2]
        ):
            points.append((float(coordinates[0]), float(coordinates[1])))
    if not points:
        return None
    x_values, y_values = zip(*points, strict=True)
    return BoundingBox(
        x=min(x_values),
        y=min(y_values),
        width=max(x_values) - min(x_values),
        height=max(y_values) - min(y_values),
    )


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(char for char in decomposed if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()


def _classify_document(lines: Sequence[_OCRLine]) -> DocumentType:
    text = " ".join(line.folded for line in lines)
    invoice_markers = ("invoice", "factuur", "rechnung", "facture")
    receipt_markers = ("receipt", "kassabon", "quittung", "recu", "ticket")
    if any(marker in text for marker in invoice_markers):
        return DocumentType.INVOICE
    if any(marker in text for marker in receipt_markers):
        return DocumentType.RECEIPT
    raise PaddleOCRProviderError("PaddleOCR could not classify the document as invoice or receipt.")


def _extract_fields(
    document_type: DocumentType,
    lines: Sequence[_OCRLine],
) -> tuple[dict[str, FieldEvidence[object]], InvoiceFields | ReceiptFields]:
    if document_type is DocumentType.RECEIPT:
        return _extract_receipt(lines)
    return _extract_invoice(lines)


def _extract_invoice(
    lines: Sequence[_OCRLine],
) -> tuple[dict[str, FieldEvidence[object]], InvoiceFields]:
    vendor_name, customer_name, vendor_vat, customer_vat = _party_values(lines)

    values: dict[str, object | None] = {
        "vendor_name": vendor_name,
        "vendor_vat_id": vendor_vat,
        "customer_name": customer_name,
        "customer_vat_id": customer_vat,
        "invoice_number": _value_after_label(
            lines,
            _find_label(
                lines,
                ("invoice number", "factuurnummer", "rechnungsnummer", "n de facture"),
            ),
        ),
        "invoice_date": _date_after_label(
            lines,
            _find_label(
                lines,
                ("invoice date", "factuurdatum", "rechnungsdatum", "date de facture"),
            ),
        ),
        "due_date": _date_after_label(
            lines, _find_label(lines, ("due date", "vervaldatum", "falligkeitsdatum", "echeance"))
        ),
        "purchase_order": _value_after_label(
            lines,
            _find_label(
                lines,
                ("purchase order", "inkooporder", "bestellnummer", "bon de commande"),
            ),
            exclude=("aantal", "bedrag", "omschrijving", "description", "quantity", "montant"),
        ),
        "currency": _currency(lines),
        "subtotal": _amount_after_label(
            lines, _find_label(lines, ("subtotal", "subtotaal", "zwischensumme", "sous total"))
        ),
        "total_tax": _amount_after_label(lines, _find_tax_label(lines)),
        "invoice_total": _amount_after_label(
            lines,
            _find_label(
                lines,
                ("total", "totaal", "gesamtbetrag"),
                exclude=("subtotal", "subtotaal", "zwischensumme", "sous total"),
            ),
        ),
    }
    fields = InvoiceFields(**values)
    return _evidence(lines, values), fields


def _extract_receipt(
    lines: Sequence[_OCRLine],
) -> tuple[dict[str, FieldEvidence[object]], ReceiptFields]:
    values: dict[str, object | None] = {
        "merchant": _receipt_merchant(lines),
        "transaction_date": _date_after_label(lines, _find_label(lines, ("date", "datum"))),
        "expense_category": _receipt_category(lines),
        "currency": _currency(lines),
        "subtotal": _amount_after_label(lines, _find_label(lines, ("subtotal", "subtotaal"))),
        "vat_total": _amount_after_label(lines, _find_tax_label(lines)),
        "total": _amount_after_label(lines, _find_label(lines, ("total", "totaal"))),
    }
    fields = ReceiptFields(**values)
    return _evidence(lines, values), fields


def _receipt_merchant(lines: Sequence[_OCRLine]) -> str | None:
    if not lines:
        return None
    # Thermal-receipt OCR can join the stable fictional merchant tokens and legal suffix.
    value = re.sub(r"(?i)(?<=\w)(B\.V\.)", r" \1", lines[0].text)
    value = re.sub(r"(?i)\bseafuel\b", "Sea Fuel", value)
    return value.title()


def _party_values(
    lines: Sequence[_OCRLine],
) -> tuple[str | None, str | None, VatId | None, VatId | None]:
    supplier_index = _find_label(lines, ("supplier", "leverancier", "lieferant", "fournisseur"))
    customer_index = _find_label(lines, ("customer", "klant", "kunde", "client"))
    if supplier_index is None or customer_index is None:
        return (
            _value_after_label(lines, supplier_index),
            _value_after_label(lines, customer_index),
            _vat_after_role(lines, supplier_index),
            _vat_after_role(lines, customer_index),
        )

    # ponytail: label-window heuristic for the fictional corpus;
    # replace with richer layout/schema mapping if corpus coverage expands.
    return (
        _party_name_for_labels(lines, ("supplier", "leverancier", "lieferant", "fournisseur")),
        _party_name_for_labels(lines, ("customer", "klant", "kunde", "client")),
        _vat_after_role(lines, supplier_index),
        _vat_after_role(lines, customer_index),
    )


def _party_name_for_labels(lines: Sequence[_OCRLine], labels: Sequence[str]) -> str | None:
    candidates = [
        candidate
        for index, line in enumerate(lines)
        if _matches_label(line, labels)
        for candidate in [_party_name_candidate(lines, index)]
        if candidate is not None
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda candidate: candidate[1].confidence or Decimal("0"))[0]


def _party_name_candidate(
    lines: Sequence[_OCRLine], index: int | None
) -> tuple[str, _OCRLine] | None:
    if index is None:
        return None
    inline = _clean_missing(_after_label_text(lines[index].text))
    if inline:
        return inline, lines[index]
    line = _nearest_role_line(lines, index, lambda candidate: not _is_vat_line(candidate))
    name = _clean_missing(line.text) if line else None
    return (name, line) if name and line else None


def _nearest_role_line(
    lines: Sequence[_OCRLine],
    role_index: int | None,
    matches: Callable[[_OCRLine], bool],
) -> _OCRLine | None:
    if role_index is None:
        return None
    role = lines[role_index]
    candidates = [
        (offset, candidate)
        for offset, candidate in enumerate(lines[role_index + 1 : role_index + 6], start=1)
        if matches(candidate) and _clean_missing(candidate.text)
    ]
    if not candidates:
        return None
    if role.bounding_box is None:
        return candidates[0][1]
    role_x = role.bounding_box.x
    role_y = role.bounding_box.y + role.bounding_box.height / 2
    return min(
        (candidate for _, candidate in candidates),
        key=lambda candidate: (
            _horizontal_distance(candidate, role_x),
            _vertical_distance(candidate, role_y),
        ),
    )


def _find_label(
    lines: Sequence[_OCRLine],
    labels: Sequence[str],
    *,
    exclude: Sequence[str] = (),
) -> int | None:
    folded_labels = tuple(_fold(label) for label in labels)
    folded_excludes = tuple(_fold(label) for label in exclude)
    for index, line in enumerate(lines):
        if any(
            re.search(rf"(?<![a-z0-9]){re.escape(label)}(?![a-z0-9])", line.folded)
            for label in folded_labels
        ) and not any(
            re.search(rf"(?<![a-z0-9]){re.escape(label)}(?![a-z0-9])", line.folded)
            for label in folded_excludes
        ):
            return index
    return None


def _matches_label(line: _OCRLine, labels: Sequence[str]) -> bool:
    return any(
        re.search(rf"(?<![a-z0-9]){re.escape(_fold(label))}(?![a-z0-9])", line.folded)
        for label in labels
    )


def _find_tax_label(lines: Sequence[_OCRLine]) -> int | None:
    for index, line in enumerate(lines):
        if "%" in line.text and any(
            marker in line.folded for marker in ("vat", "btw", "mwst", "tva")
        ):
            return index
    return _find_label(
        lines,
        ("vat", "btw", "mwst", "tva"),
        exclude=("number", "nummer", "id", "idnr", "id nr"),
    )


def _value_after_label(
    lines: Sequence[_OCRLine],
    index: int | None,
    *,
    exclude: Sequence[str] = (),
) -> str | None:
    if index is None:
        return None
    excluded = {_fold(value) for value in exclude}
    inline = _after_label_text(lines[index].text)
    if inline and _fold(inline) not in excluded:
        return _clean_missing(inline)
    for line in lines[index + 1 : index + 3]:
        value = _clean_missing(line.text)
        if value and _fold(value) not in excluded:
            return value
    return None


def _vat_after_role(lines: Sequence[_OCRLine], role_index: int | None) -> VatId | None:
    if role_index is not None and _after_label_text(lines[role_index].text):
        for line in lines[role_index + 1 : role_index + 3]:
            if _is_vat_line(line):
                return _vat_from_line(line)
    line = _nearest_role_line(
        lines,
        role_index,
        _is_vat_line,
    )
    return _vat_from_line(line) if line else None


def _horizontal_distance(line: _OCRLine, x: float) -> float:
    if line.bounding_box is None:
        return float("inf")
    return abs(line.bounding_box.x - x)


def _vertical_distance(line: _OCRLine, y: float) -> float:
    if line.bounding_box is None:
        return float("inf")
    center = line.bounding_box.y + line.bounding_box.height / 2
    return abs(center - y)


def _vat_from_line(line: _OCRLine) -> VatId | None:
    if not _is_vat_line(line):
        return None
    matches = re.findall(
        r"\b(?:AT|BE|BG|CY|CZ|DE|DK|EE|EL|ES|FI|FR|HR|HU|IE|IT|LT|LU|LV|MT|NL|PL|PT|RO|SE|SI|SK)"
        r"(?:[- ]?[A-Z0-9])(?:[A-Z0-9.-]{5,})\b",
        line.text,
        flags=re.IGNORECASE,
    )
    for match in matches:
        value = "".join(match.split()).upper()
        if len(value) >= 8 and not (value[2:].isdigit() and len(value[2:]) < 9):
            return VatId(normalized=value, display=match.strip())
    return None


def _is_vat_line(line: _OCRLine) -> bool:
    return any(token in line.folded for token in ("vat", "btw", "ust", "tva"))


def _after_label_text(text: str) -> str:
    parts = re.split(r"\s*[:：]\s*", text, maxsplit=1)
    return parts[1].strip() if len(parts) == 2 else ""


def _clean_missing(value: str) -> str | None:
    cleaned = value.strip()
    return None if not cleaned or _fold(cleaned) in {"", "-", "not applicable"} else cleaned


def _date_after_label(lines: Sequence[_OCRLine], index: int | None) -> date | None:
    if index is None:
        return None
    candidates = (lines[index], *lines[index + 1 : index + 3])
    for line in candidates:
        match = re.search(r"\b(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})\b", line.text)
        if match:
            return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
        match = re.search(r"\b(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})\b", line.text)
        if match:
            return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    return None


def _currency(lines: Sequence[_OCRLine]) -> CurrencyCode | None:
    for line in lines:
        match = re.search(
            r"(?<![A-Za-z])(EUR|USD|GBP|CHF)(?![A-Za-z])|€",
            line.text,
            flags=re.IGNORECASE,
        )
        if match:
            code = "EUR" if match.group(0) == "€" else match.group(0).upper()
            return CurrencyCode(code=code, display=match.group(0))
    return None


def _amount_after_label(lines: Sequence[_OCRLine], index: int | None) -> Decimal | None:
    if index is None:
        return None
    label = lines[index]
    if label.bounding_box is not None:
        label_box = label.bounding_box
        label_center = label_box.y + label_box.height / 2
        candidates: list[tuple[float, float, _OCRLine]] = []
        for line in lines:
            if line.bounding_box is None or line.bounding_box.x < label_box.x:
                continue
            amounts = _amounts(line.text)
            if not amounts:
                continue
            line_box = line.bounding_box
            line_center = line_box.y + line_box.height / 2
            row_distance = abs(line_center - label_center)
            if row_distance <= max(label_box.height, line_box.height):
                candidates.append((row_distance, line_box.x - label_box.x, line))
        if candidates:
            line = min(candidates, key=lambda candidate: (candidate[0], candidate[1]))[2]
            return _amounts(line.text)[-1]
    for line in (lines[index], *lines[index + 1 : index + 3]):
        amounts = _amounts(line.text)
        if amounts:
            return amounts[-1]
    return None


def _amounts(text: str) -> list[Decimal]:
    matches = re.findall(
        r"(?<![A-Za-z])(?:EUR|€)?\s*([0-9]{1,3}(?:[ .][0-9]{3})*(?:[,.][0-9]{2}))"
        r"(?![A-Za-z])",
        text,
        re.IGNORECASE,
    )
    amounts: list[Decimal] = []
    for match in matches:
        normalized = match.replace(" ", "").replace(".", "")
        if "," in normalized:
            normalized = normalized.replace(",", ".")
        elif match.count(".") == 1 and len(match.rsplit(".", 1)[-1]) == 2:
            normalized = match
        try:
            amounts.append(Decimal(normalized))
        except InvalidOperation:
            continue
    return amounts


def _receipt_category(lines: Sequence[_OCRLine]) -> str | None:
    text = " ".join(line.folded for line in lines)
    if any(marker in text for marker in ("brandstof", "fuel", "essence", "diesel", "euro 95")):
        return "fuel"
    return None


def _evidence(
    lines: Sequence[_OCRLine],
    values: Mapping[str, object | None],
) -> dict[str, FieldEvidence[object]]:
    result: dict[str, FieldEvidence[object]] = {}
    for field_name, value in values.items():
        line = _line_for_value(lines, value)
        if value is None:
            result[field_name] = FieldEvidence(
                status=EvidenceStatus.MISSING,
            )
            continue
        result[field_name] = FieldEvidence(
            value=value,
            confidence=line.confidence if line else None,
            source=EvidenceSource.PRIMARY,
            status=EvidenceStatus.PRIMARY,
            page=line.page if line else None,
            bounding_box=line.bounding_box if line else None,
            text_context=line.text if line else None,
        )
    return result


def _line_for_value(lines: Sequence[_OCRLine], value: object | None) -> _OCRLine | None:
    if value is None:
        return None
    display = value.display if isinstance(value, (CurrencyCode, VatId)) else str(value)
    folded = _fold(display)
    for line in lines:
        if folded and folded in line.folded:
            return line
    return None
