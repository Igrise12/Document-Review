import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Final
from uuid import uuid4

MAX_UPLOAD_BYTES: Final = 4 * 1024 * 1024
ALLOWED_MEDIA_TYPES: Final = frozenset(
    {"application/pdf", "image/png", "image/jpeg"}
)
_PNG_SIGNATURE: Final = b"\x89PNG\r\n\x1a\n"
_SUFFIXES: Final = {
    "application/pdf": ".pdf",
    "image/png": ".png",
    "image/jpeg": ".jpg",
}


class UploadValidationError(ValueError):
    """Raised when an uploaded file fails the local upload contract."""


@dataclass(frozen=True)
class StoredFile:
    storage_key: str
    media_type: str
    size_bytes: int


def validate_upload(media_type: str, content: bytes) -> str:
    if not isinstance(media_type, str):
        raise UploadValidationError("media type is required")
    if not isinstance(content, bytes) or not content:
        raise UploadValidationError("upload must contain non-empty bytes")

    normalized_media_type = media_type.strip().lower()
    if normalized_media_type not in ALLOWED_MEDIA_TYPES:
        raise UploadValidationError("only PDF, PNG, and JPEG files are supported")
    if len(content) > MAX_UPLOAD_BYTES:
        raise UploadValidationError("upload exceeds the 4 MB limit")

    matches_signature = {
        "application/pdf": content.startswith(b"%PDF-"),
        "image/png": content.startswith(_PNG_SIGNATURE),
        "image/jpeg": content.startswith(b"\xff\xd8\xff"),
    }[normalized_media_type]
    if not matches_signature:
        raise UploadValidationError("file content does not match its media type")
    return normalized_media_type


class LocalFileStorage:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, media_type: str, content: bytes) -> StoredFile:
        normalized_media_type = validate_upload(media_type, content)
        storage_key = f"{uuid4().hex}{_SUFFIXES[normalized_media_type]}"
        target = self._path_for(storage_key)
        temporary_path: Path | None = None

        try:
            with NamedTemporaryFile(
                mode="wb",
                dir=self.root,
                prefix=".upload-",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(content)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, target)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

        return StoredFile(storage_key, normalized_media_type, len(content))

    def read(self, storage_key: str) -> bytes:
        return self._path_for(storage_key).read_bytes()

    def delete(self, storage_key: str) -> bool:
        path = self._path_for(storage_key)
        if not path.exists():
            return False
        if not path.is_file():
            raise ValueError("storage key does not identify a file")
        path.unlink()
        return True

    def _path_for(self, storage_key: str) -> Path:
        if (
            not storage_key
            or "/" in storage_key
            or "\\" in storage_key
            or Path(storage_key).name != storage_key
            or storage_key in {".", ".."}
        ):
            raise ValueError("invalid storage key")

        path = (self.root / storage_key).resolve()
        try:
            path.relative_to(self.root)
        except ValueError as error:
            raise ValueError("storage key escapes storage root") from error
        return path
