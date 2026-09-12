from __future__ import annotations

import base64
import io
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from time import perf_counter
from typing import Any, Literal, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from openai import OpenAI, OpenAIError
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from app.accounting.models import GLAccount, GLSuggestion, GLSuggestionResult
from app.config import Settings
from app.correction_email.models import CorrectionDraftResult, CorrectionEmailDraft
from app.document_review.models import (
    DocumentClassification,
    DocumentClassificationResult,
    DocumentIssue,
    DocumentType,
    FieldEvidence,
    InvoiceDocument,
    InvoiceFields,
    IssueSeverity,
    ProviderRunMetadata,
    ReceiptDocument,
    ReceiptFields,
    SourceDocumentMetadata,
    VLMExtractionResult,
)
from app.invoices.storage import UploadValidationError, validate_upload

MediaType = Literal["application/pdf", "image/png", "image/jpeg"]

_PDF_RENDER_SCALE = 1.5
_CLASSIFICATION_PROMPT_VERSION = "qwen-classification/v1"
_REVIEW_PROMPT_VERSION = "qwen-document-review/v1"
_GL_PROMPT_VERSION = "qwen-gl-suggestion/v1"
_CORRECTION_PROMPT_VERSION = "qwen-correction-draft/v1"


class QwenProviderError(RuntimeError):
    """Raised when the local Qwen adapter cannot return a valid result."""


class _OllamaRequestError(RuntimeError):
    """Raised when the native Ollama endpoint cannot return a response."""


class _ClassificationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: DocumentType
    confidence: str = Field(min_length=1)
    reasoning: str = Field(min_length=1)

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: str) -> str:
        return _confidence_string(value)


class _InvoiceReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal["invoice"]
    fields: InvoiceFields
    field_confidence: dict[str, str]

    @field_validator("field_confidence")
    @classmethod
    def validate_field_confidence(cls, value: dict[str, str]) -> dict[str, str]:
        return {
            name: _confidence_string(confidence)
            for name, confidence in value.items()
            if confidence.strip()
        }


class _ReceiptReviewPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_type: Literal["receipt"]
    fields: ReceiptFields
    field_confidence: dict[str, str]

    @field_validator("field_confidence")
    @classmethod
    def validate_field_confidence(cls, value: dict[str, str]) -> dict[str, str]:
        return {
            name: _confidence_string(confidence)
            for name, confidence in value.items()
            if confidence.strip()
        }


class _GLSuggestionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    confidence: str = Field(min_length=1)

    @field_validator("confidence")
    @classmethod
    def validate_confidence(cls, value: str) -> str:
        return _confidence_string(value)


class _CorrectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)


def _confidence_string(value: str) -> str:
    value = value.strip().lstrip(":").strip()
    try:
        confidence = Decimal(value)
    except (InvalidOperation, ValueError):
        raise ValueError("confidence must be a decimal string") from None
    if not Decimal("0") <= confidence <= Decimal("1"):
        raise ValueError("confidence must be between 0 and 1")
    return value


def _normalize_review_payload(value: object) -> object:
    if not isinstance(value, Mapping):
        return value
    fields = value.get("fields")
    if not isinstance(fields, Mapping):
        return value
    normalized_fields = dict(fields)
    for field_name in ("subtotal", "total_tax", "vat_total", "total", "invoice_total"):
        if field_name in normalized_fields:
            normalized_fields[field_name] = _money_string(normalized_fields[field_name])
    for field_name in ("invoice_date", "due_date", "transaction_date"):
        if field_name in normalized_fields:
            normalized_fields[field_name] = _iso_date_string(normalized_fields[field_name])
    currency = normalized_fields.get("currency")
    if isinstance(currency, str):
        display = currency.strip()
        code = "EUR" if display.casefold() in {"€", "eur", "euro"} else display.upper()
        normalized_fields["currency"] = {"code": code, "display": display}
    return {**value, "fields": normalized_fields}


def _money_string(value: object) -> object:
    if not isinstance(value, str):
        return value
    cleaned = re.sub(r"(?i)\b(?:EUR|USD|GBP|CHF)\b|€", "", value).strip()
    if "," in cleaned and "." in cleaned:
        cleaned = (
            cleaned.replace(".", "")
            if cleaned.rfind(",") > cleaned.rfind(".")
            else cleaned.replace(",", "")
        )
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")
    return cleaned.replace(" ", "")


def _iso_date_string(value: object) -> object:
    if not isinstance(value, str):
        return value
    match = re.fullmatch(r"(\d{1,2})[-/.](\d{1,2})[-/.](20\d{2})", value.strip())
    if match:
        day, month, year = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d}"
    return value


@dataclass(frozen=True)
class _PreparedMedia:
    parts: tuple[dict[str, Any], ...]
    page_count: int


class QwenVLMProvider:
    """Provider boundary for the local Qwen model."""

    def __init__(self, settings: Settings, *, client: Any | None = None) -> None:
        self._settings = settings
        self._native_ollama = client is None and settings.local_vlm_runtime == "ollama"
        self._client = client or OpenAI(
            api_key=settings.local_vlm_api_key or "local-vlm",
            base_url=str(settings.local_vlm_base_url),
            timeout=settings.local_vlm_timeout_seconds,
            max_retries=0,
        )

    def classify_document(
        self,
        *,
        filename: str,
        media_type: str,
        content: bytes,
    ) -> DocumentClassificationResult:
        prepared = self._prepare_media(media_type, content)
        payload, provider_run = self._request_structured(
            response_model=_ClassificationPayload,
            schema_name="document_classification",
            schema_version="qwen-classification/v1",
            prompt_version=_CLASSIFICATION_PROMPT_VERSION,
            system_prompt=(
                "Classify the supplied financial document as exactly one of invoice or receipt. "
                "A receipt is proof of payment, including a fuel-station slip or a multilingual "
                "kassabon. An invoice usually has an invoice number, supplier/customer details, "
                "and payment terms. "
                "Return only the requested JSON schema. Confidence is a rough signal, not a "
                "calibrated probability, and must be a decimal string between 0 and 1."
            ),
            user_content=self._media_content(
                prepared,
                "Identify whether this document is an invoice or a receipt. "
                "Use a confidence string such as \"0.95\" and give concise "
                "evidence-based reasoning. "
                "Do not call a proof-of-payment slip an invoice.",
            ),
        )
        try:
            classification = DocumentClassification(
                document_type=payload.document_type,
                confidence=payload.confidence,
                reasoning=payload.reasoning,
            )
        except ValidationError as error:
            raise QwenProviderError(
                "Qwen returned an invalid classification confidence."
            ) from error
        return DocumentClassificationResult(
            classification=classification,
            provider_run=provider_run,
        )

    def review_document(
        self,
        *,
        filename: str,
        media_type: str,
        content: bytes,
        uploaded_at: datetime,
        document_type: DocumentType,
    ) -> VLMExtractionResult:
        prepared = self._prepare_media(media_type, content)
        response_model: type[BaseModel]
        if document_type is DocumentType.INVOICE:
            response_model = _InvoiceReviewPayload
        else:
            response_model = _ReceiptReviewPayload
        payload, provider_run = self._request_structured(
            response_model=response_model,
            schema_name=f"{document_type.value}_document_review",
            schema_version="qwen-document-review/v1",
            prompt_version=_REVIEW_PROMPT_VERSION,
            system_prompt=self._review_system_prompt(document_type),
            user_content=self._media_content(
                prepared,
                self._review_user_prompt(document_type),
            ),
        )
        if payload.document_type != document_type.value:
            raise QwenProviderError(
                "Qwen document review returned a different document type than requested."
            )

        fields = cast(InvoiceFields | ReceiptFields, payload.fields)
        field_confidence = self._validate_field_confidence(fields, payload.field_confidence)
        processed_at = provider_run.finished_at or datetime.now(UTC)
        try:
            normalized_media_type = cast(MediaType, validate_upload(media_type, content))
            source = SourceDocumentMetadata(
                filename=filename,
                media_type=normalized_media_type,
                size_bytes=len(content),
                page_count=prepared.page_count,
                uploaded_at=uploaded_at,
                processed_at=processed_at,
            )
        except (UploadValidationError, ValidationError) as error:
            raise QwenProviderError("Qwen review metadata could not be normalized.") from error
        document = (
            InvoiceDocument(source=source, fields=cast(InvoiceFields, fields))
            if document_type is DocumentType.INVOICE
            else ReceiptDocument(source=source, fields=cast(ReceiptFields, fields))
        )
        try:
            return VLMExtractionResult(
                document=document,
                field_confidence=field_confidence,
                provider_run=provider_run,
            )
        except ValidationError as error:
            raise QwenProviderError("Qwen returned invalid field confidence values.") from error

    def suggest_gl(
        self,
        *,
        document: InvoiceDocument | ReceiptDocument,
        catalog: Sequence[GLAccount],
    ) -> GLSuggestionResult:
        if not catalog:
            raise QwenProviderError("GL suggestion requires a non-empty account catalog.")
        catalog_payload = [account.model_dump(mode="json") for account in catalog]
        document_payload = self._normalized_document_payload(document)
        payload, provider_run = self._request_structured(
            response_model=_GLSuggestionPayload,
            schema_name="gl_suggestion",
            schema_version="qwen-gl-suggestion/v1",
            prompt_version=_GL_PROMPT_VERSION,
            system_prompt=(
                "Suggest exactly one account from the supplied fixed catalog for the normalized "
                "financial document. Never invent an account ID. Return only the requested JSON "
                "schema. Confidence must be a decimal string between 0 and 1."
            ),
            user_content=json.dumps(
                {
                    "document": document_payload,
                    "allowed_catalog": catalog_payload,
                },
                ensure_ascii=False,
            ),
        )
        allowed_ids = {account.account_id for account in catalog}
        if payload.account_id not in allowed_ids:
            return GLSuggestionResult(provider_run=provider_run)
        try:
            suggestion = GLSuggestion(
                account_id=payload.account_id,
                rationale=payload.rationale,
                confidence=payload.confidence,
            )
        except ValidationError as error:
            raise QwenProviderError("Qwen returned an invalid GL confidence.") from error
        return GLSuggestionResult(suggestion=suggestion, provider_run=provider_run)

    def draft_correction(
        self,
        *,
        document: InvoiceDocument | ReceiptDocument,
        issues: Sequence[DocumentIssue],
        evidence: Mapping[str, FieldEvidence[Any]],
    ) -> CorrectionDraftResult:
        payload, provider_run = self._request_structured(
            response_model=_CorrectionPayload,
            schema_name="correction_email_draft",
            schema_version="qwen-correction-draft/v1",
            prompt_version=_CORRECTION_PROMPT_VERSION,
            system_prompt=(
                "Write a concise professional English correction request to the supplier. "
                "Return only the requested JSON schema and text. Do not claim that VIES or any "
                "live external registration service was checked. Do not send email."
            ),
            user_content=json.dumps(
                {
                    "document": document.model_dump(mode="json"),
                    "blocking_issues": [
                        issue.model_dump(mode="json")
                        for issue in issues
                        if issue.severity is IssueSeverity.ERROR
                    ],
                    "relevant_evidence": {
                        name: field.model_dump(mode="json") for name, field in evidence.items()
                    },
                },
                ensure_ascii=False,
            ),
        )
        return CorrectionDraftResult(
            draft=CorrectionEmailDraft(text=payload.text),
            provider_run=provider_run,
        )

    def _request_structured(
        self,
        *,
        response_model: type[BaseModel],
        schema_name: str,
        schema_version: str,
        prompt_version: str,
        system_prompt: str,
        user_content: str | list[dict[str, Any]],
    ) -> tuple[Any, ProviderRunMetadata]:
        started_at = datetime.now(UTC)
        started = perf_counter()
        last_error: Exception | None = None
        attempts = self._settings.local_vlm_max_structured_output_retries + 1
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": schema_name,
                "strict": True,
                "schema": response_model.model_json_schema(),
            },
        }
        for attempt in range(attempts):
            request_content = self._retry_content(user_content, attempt)
            try:
                if self._native_ollama:
                    content = self._request_ollama(
                        response_schema=response_model.model_json_schema(),
                        system_prompt=system_prompt,
                        user_content=request_content,
                    )
                else:
                    response = self._client.chat.completions.create(
                        model=self._settings.local_vlm_model,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": request_content},
                        ],
                        response_format=response_format,
                        temperature=0,
                    )
                    content = response.choices[0].message.content
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("Qwen returned an empty structured response.")
                raw_payload = json.loads(content)
                if response_model in {_InvoiceReviewPayload, _ReceiptReviewPayload}:
                    raw_payload = _normalize_review_payload(raw_payload)
                parsed = response_model.model_validate(raw_payload)
                finished_at = datetime.now(UTC)
                metadata = ProviderRunMetadata(
                    provider="qwen_vlm",
                    model_name=self._settings.local_vlm_model,
                    model_version=self._settings.local_vlm_model,
                    prompt_version=prompt_version,
                    schema_version=schema_version,
                    runtime=self._settings.local_vlm_runtime,
                    started_at=started_at,
                    finished_at=finished_at,
                    duration_ms=int((perf_counter() - started) * 1000),
                )
                return parsed, metadata
            except (
                OpenAIError,
                IndexError,
                json.JSONDecodeError,
                TypeError,
                ValidationError,
                ValueError,
                _OllamaRequestError,
            ) as error:
                last_error = error

        if isinstance(last_error, (OpenAIError, _OllamaRequestError)):
            raise QwenProviderError(
                f"Qwen endpoint failed after {attempts} attempts; check the local runtime."
            ) from last_error
        raise QwenProviderError(
            f"Qwen returned invalid structured output after {attempts} attempts."
        ) from last_error

    def _request_ollama(
        self,
        *,
        response_schema: dict[str, Any],
        system_prompt: str,
        user_content: str | list[dict[str, Any]],
    ) -> str:
        request_body = {
            "model": self._settings.local_vlm_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                self._ollama_user_message(user_content),
            ],
            "format": response_schema,
            "stream": False,
            "think": False,
            "options": {"temperature": 0},
        }
        request = Request(
            self._ollama_chat_url(),
            data=json.dumps(request_body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._settings.local_vlm_timeout_seconds) as response:
                payload = json.load(response)
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as error:
            raise _OllamaRequestError("Native Ollama request failed.") from error
        message = payload.get("message") if isinstance(payload, Mapping) else None
        content = message.get("content") if isinstance(message, Mapping) else None
        if not isinstance(content, str):
            raise _OllamaRequestError("Native Ollama response had no message content.")
        return content

    @staticmethod
    def _ollama_user_message(user_content: str | list[dict[str, Any]]) -> dict[str, Any]:
        if isinstance(user_content, str):
            return {"role": "user", "content": user_content}
        text_parts = [part["text"] for part in user_content if part.get("type") == "text"]
        images = [
            part["image_url"]["url"].split(",", maxsplit=1)[1]
            for part in user_content
            if part.get("type") == "image_url"
        ]
        return {"role": "user", "content": "\n".join(text_parts), "images": images}

    def _ollama_chat_url(self) -> str:
        base_url = str(self._settings.local_vlm_base_url).rstrip("/")
        return f"{base_url.removesuffix('/v1')}/api/chat"

    @staticmethod
    def _retry_content(
        user_content: str | list[dict[str, Any]], attempt: int
    ) -> str | list[dict[str, Any]]:
        if attempt == 0:
            return user_content
        reminder = {
            "type": "text",
            "text": (
                "The previous response was invalid. Return only JSON matching the requested schema."
            ),
        }
        if isinstance(user_content, str):
            return f"{user_content}\n\n{reminder['text']}"
        return [*user_content, reminder]

    @staticmethod
    def _media_content(
        prepared: _PreparedMedia,
        instruction: str,
    ) -> list[dict[str, Any]]:
        return [{"type": "text", "text": instruction}, *prepared.parts]

    def _prepare_media(self, media_type: str, content: bytes) -> _PreparedMedia:
        try:
            normalized_media_type = cast(MediaType, validate_upload(media_type, content))
        except UploadValidationError as error:
            raise QwenProviderError(str(error)) from error

        if normalized_media_type != "application/pdf":
            encoded = base64.b64encode(content).decode("ascii")
            return _PreparedMedia(
                parts=(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{normalized_media_type};base64,{encoded}",
                            "detail": "high",
                        },
                    },
                ),
                page_count=1,
            )

        try:
            import pypdfium2 as pdfium

            document = pdfium.PdfDocument(content)
            parts: list[dict[str, Any]] = []
            for page_index in range(len(document)):
                page = document[page_index]
                bitmap = page.render(scale=_PDF_RENDER_SCALE)
                image = bitmap.to_pil()
                buffer = io.BytesIO()
                image.save(buffer, format="PNG", optimize=True)
                encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
                parts.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{encoded}",
                            "detail": "high",
                        },
                    }
                )
                image.close()
                bitmap.close()
                page.close()
            document.close()
        except (ImportError, OSError, RuntimeError, ValueError) as error:
            raise QwenProviderError("PDF pages could not be rendered for Qwen.") from error
        if not parts:
            raise QwenProviderError("PDF contains no renderable pages for Qwen.")
        return _PreparedMedia(parts=tuple(parts), page_count=len(parts))

    @staticmethod
    def _review_system_prompt(document_type: DocumentType) -> str:
        fields = "invoice fields" if document_type is DocumentType.INVOICE else "receipt fields"
        return (
            f"Extract only the requested {fields} from the supplied original document. "
            f"The document_type must be exactly {document_type.value}. Preserve missing values as "
            "null. Use ISO dates, uppercase three-letter currency codes, and decimal strings for "
            "money and confidence values. Include field_confidence for every non-null field; "
            "never use an empty confidence string. Return only the requested JSON schema."
        )

    @staticmethod
    def _review_user_prompt(document_type: DocumentType) -> str:
        if document_type is DocumentType.INVOICE:
            return (
                "Return vendor/customer identity and VAT IDs, invoice number and dates, purchase "
                "order, currency, subtotal, total tax, and invoice total. Include confidence for "
                "every non-null field using decimal strings, including both party names."
            )
        return (
            "Return merchant, transaction date, expense category, currency, subtotal, VAT total, "
            "and total. Include confidence for every non-null field using decimal strings."
        )

    @staticmethod
    def _validate_field_confidence(
        fields: InvoiceFields | ReceiptFields,
        confidence: Mapping[str, str],
    ) -> dict[str, str]:
        field_names = set(type(fields).model_fields)
        unknown = set(confidence) - field_names
        if unknown:
            raise QwenProviderError(
                f"Qwen returned confidence for unknown fields: {', '.join(sorted(unknown))}."
            )
        missing = {
            name
            for name in field_names
            if getattr(fields, name) is not None and name not in confidence
        }
        if missing:
            raise QwenProviderError(
                f"Qwen omitted confidence for fields: {', '.join(sorted(missing))}."
            )
        return {
            name: value for name, value in confidence.items() if getattr(fields, name) is not None
        }

    @staticmethod
    def _normalized_document_payload(
        document: InvoiceDocument | ReceiptDocument,
    ) -> dict[str, Any]:
        return {
            "document_type": document.document_type,
            "fields": document.fields.model_dump(mode="json"),
        }
