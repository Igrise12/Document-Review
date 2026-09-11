import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from uuid import uuid4

from pydantic import BaseModel
from sqlalchemy import JSON, ForeignKey, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from app.accounting.models import GLReview
from app.document_review.models import (
    DocumentType,
    InvoiceDocument,
    ReceiptDocument,
    ReviewState,
)
from app.invoices.storage import ALLOWED_MEDIA_TYPES, MAX_UPLOAD_BYTES


class Base(DeclarativeBase):
    pass


class UploadedDocumentRow(Base):
    __tablename__ = "uploaded_documents"

    document_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    storage_key: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(40), nullable=False)
    size_bytes: Mapped[int] = mapped_column(nullable=False)
    page_count: Mapped[int | None] = mapped_column(nullable=True)
    uploaded_at: Mapped[str] = mapped_column(String(40), nullable=False)


class ReviewRow(Base):
    __tablename__ = "reviews"

    review_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        ForeignKey("uploaded_documents.document_id"), unique=True, nullable=False
    )
    state: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    document_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at: Mapped[str] = mapped_column(String(40), nullable=False)
    processed_at: Mapped[str | None] = mapped_column(String(40), nullable=True)
    normalized_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    evidence_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    issues_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    gl_review_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    provider_runs_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    duplicate_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    action_metadata_json: Mapped[object | None] = mapped_column(JSON, nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)


@dataclass(frozen=True)
class ReviewSnapshot:
    review_id: str
    document_id: str
    storage_key: str
    original_filename: str
    media_type: str
    size_bytes: int
    page_count: int | None
    uploaded_at: datetime
    state: ReviewState
    document_type: DocumentType | None
    created_at: datetime
    updated_at: datetime
    processed_at: datetime | None
    normalized: object | None
    evidence: object | None
    issues: object | None
    gl_review: object | None
    provider_runs: object | None
    duplicate_key: str | None
    action_metadata: object | None
    failure_message: str | None


_MISSING: Final = object()


def _utc_iso(value: datetime | None = None) -> str:
    value = value or datetime.now(UTC)
    if value.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    return value.astimezone(UTC).isoformat()


def _from_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("stored timestamps must be timezone-aware")
    return parsed


def _json_ready(value: object) -> object:
    if isinstance(value, BaseModel):
        return _json_ready(value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(key): _json_ready(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_ready(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"value of type {type(value).__name__} is not JSON serializable")


def _serialize_payload(value: object | None) -> object | None:
    if value is None:
        return None
    return json.loads(json.dumps(_json_ready(value), allow_nan=False))


class InvoiceReviewRepository:
    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path.expanduser().resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.database_path}",
            connect_args={"check_same_thread": False},
        )
        self._session_factory = sessionmaker(self.engine, expire_on_commit=False)

    def initialize(self) -> None:
        Base.metadata.create_all(self.engine)

    def close(self) -> None:
        self.engine.dispose()

    def create_uploaded_review(
        self,
        *,
        storage_key: str,
        original_filename: str,
        media_type: str,
        size_bytes: int,
        uploaded_at: datetime | None = None,
        page_count: int | None = None,
    ) -> ReviewSnapshot:
        self._validate_upload_record(storage_key, original_filename, media_type, size_bytes)
        self._validate_page_count(page_count)
        timestamp = _utc_iso(uploaded_at)
        review_id = str(uuid4())
        document_id = str(uuid4())
        document = UploadedDocumentRow(
            document_id=document_id,
            storage_key=storage_key,
            original_filename=original_filename,
            media_type=media_type,
            size_bytes=size_bytes,
            page_count=page_count,
            uploaded_at=timestamp,
        )
        review = ReviewRow(
            review_id=review_id,
            document_id=document_id,
            state=ReviewState.UPLOADED.value,
            created_at=timestamp,
            updated_at=timestamp,
        )
        with self._session_factory() as session:
            try:
                session.add_all([document, review])
                session.commit()
                return self._snapshot(review, document)
            except Exception:
                session.rollback()
                raise

    def get(self, review_id: str) -> ReviewSnapshot | None:
        with self._session_factory() as session:
            review = session.get(ReviewRow, review_id)
            if review is None:
                return None
            document = session.get(UploadedDocumentRow, review.document_id)
            if document is None:
                raise ValueError("review refers to a missing uploaded document")
            return self._snapshot(review, document)

    def list_reviews(self) -> list[ReviewSnapshot]:
        with self._session_factory() as session:
            reviews = session.scalars(
                select(ReviewRow).order_by(ReviewRow.created_at.desc())
            ).all()
            snapshots = []
            for review in reviews:
                document = session.get(UploadedDocumentRow, review.document_id)
                if document is None:
                    raise ValueError("review refers to a missing uploaded document")
                snapshots.append(self._snapshot(review, document))
            return snapshots

    def find_by_duplicate_key(self, duplicate_key: str) -> list[ReviewSnapshot]:
        if not duplicate_key.strip():
            return []
        with self._session_factory() as session:
            reviews = session.scalars(
                select(ReviewRow)
                .where(ReviewRow.duplicate_key == duplicate_key)
                .order_by(ReviewRow.created_at.asc())
            ).all()
            snapshots = []
            for review in reviews:
                document = session.get(UploadedDocumentRow, review.document_id)
                if document is None:
                    raise ValueError("review refers to a missing uploaded document")
                snapshots.append(self._snapshot(review, document))
            return snapshots

    def save_processing_result(
        self,
        review_id: str,
        *,
        state: ReviewState,
        normalized_document: InvoiceDocument | ReceiptDocument | None,
        evidence: object | None,
        issues: object | None,
        gl_review: GLReview | None,
        provider_runs: object | None,
        duplicate_key: str | None,
        page_count: int | None,
        processed_at: datetime | None = None,
        failure_message: str | None = None,
    ) -> ReviewSnapshot:
        self._validate_page_count(page_count)
        if duplicate_key is not None and not duplicate_key.strip():
            duplicate_key = None
        with self._session_factory() as session:
            try:
                review, document = self._required_rows(session, review_id)
                review.state = state.value
                review.document_type = (
                    normalized_document.document_type if normalized_document else None
                )
                review.normalized_json = _serialize_payload(normalized_document)
                review.evidence_json = _serialize_payload(evidence)
                review.issues_json = _serialize_payload(issues)
                review.gl_review_json = _serialize_payload(gl_review)
                review.provider_runs_json = _serialize_payload(provider_runs)
                review.duplicate_key = duplicate_key
                review.processed_at = _utc_iso(processed_at) if processed_at else None
                review.failure_message = failure_message
                review.updated_at = _utc_iso()
                document.page_count = page_count
                session.commit()
                return self._snapshot(review, document)
            except Exception:
                session.rollback()
                raise

    def update_gl_review(self, review_id: str, gl_review: GLReview | None) -> ReviewSnapshot:
        with self._session_factory() as session:
            try:
                review, document = self._required_rows(session, review_id)
                review.gl_review_json = _serialize_payload(gl_review)
                review.updated_at = _utc_iso()
                session.commit()
                return self._snapshot(review, document)
            except Exception:
                session.rollback()
                raise

    def update_state(
        self,
        review_id: str,
        *,
        state: ReviewState,
        action_metadata: object = _MISSING,
        failure_message: str | None = None,
    ) -> ReviewSnapshot:
        with self._session_factory() as session:
            try:
                review, document = self._required_rows(session, review_id)
                review.state = state.value
                review.failure_message = failure_message
                if action_metadata is not _MISSING:
                    review.action_metadata_json = _serialize_payload(action_metadata)
                review.updated_at = _utc_iso()
                session.commit()
                return self._snapshot(review, document)
            except Exception:
                session.rollback()
                raise

    def delete_review(self, review_id: str) -> str | None:
        with self._session_factory() as session:
            try:
                review = session.get(ReviewRow, review_id)
                if review is None:
                    return None
                document = session.get(UploadedDocumentRow, review.document_id)
                storage_key = document.storage_key if document else None
                session.delete(review)
                session.flush()
                if document is not None:
                    session.delete(document)
                session.commit()
                return storage_key
            except Exception:
                session.rollback()
                raise

    @staticmethod
    def _required_rows(
        session: Session, review_id: str
    ) -> tuple[ReviewRow, UploadedDocumentRow]:
        review = session.get(ReviewRow, review_id)
        if review is None:
            raise KeyError(f"review not found: {review_id}")
        document = session.get(UploadedDocumentRow, review.document_id)
        if document is None:
            raise ValueError("review refers to a missing uploaded document")
        return review, document

    @staticmethod
    def _validate_upload_record(
        storage_key: str, original_filename: str, media_type: str, size_bytes: int
    ) -> None:
        if (
            not storage_key
            or "/" in storage_key
            or "\\" in storage_key
            or Path(storage_key).name != storage_key
        ):
            raise ValueError("invalid storage key")
        if not original_filename.strip():
            raise ValueError("original filename is required")
        if media_type not in ALLOWED_MEDIA_TYPES:
            raise ValueError("unsupported media type")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool):
            raise ValueError("size must be an integer")
        if not 0 < size_bytes <= MAX_UPLOAD_BYTES:
            raise ValueError("size is outside the upload limit")

    @staticmethod
    def _validate_page_count(page_count: int | None) -> None:
        if page_count is not None and (
            not isinstance(page_count, int) or isinstance(page_count, bool) or page_count <= 0
        ):
            raise ValueError("page count must be a positive integer")

    @staticmethod
    def _snapshot(
        review: ReviewRow, document: UploadedDocumentRow
    ) -> ReviewSnapshot:
        return ReviewSnapshot(
            review_id=review.review_id,
            document_id=document.document_id,
            storage_key=document.storage_key,
            original_filename=document.original_filename,
            media_type=document.media_type,
            size_bytes=document.size_bytes,
            page_count=document.page_count,
            uploaded_at=_from_iso(document.uploaded_at),
            state=ReviewState(review.state),
            document_type=(DocumentType(review.document_type) if review.document_type else None),
            created_at=_from_iso(review.created_at),
            updated_at=_from_iso(review.updated_at),
            processed_at=(_from_iso(review.processed_at) if review.processed_at else None),
            normalized=review.normalized_json,
            evidence=review.evidence_json,
            issues=review.issues_json,
            gl_review=review.gl_review_json,
            provider_runs=review.provider_runs_json,
            duplicate_key=review.duplicate_key,
            action_metadata=review.action_metadata_json,
            failure_message=review.failure_message,
        )
