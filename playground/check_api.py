"""Exercise the minimal FastAPI contract with fictional local provider doubles."""

import json as json_module
import socket
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from http.client import HTTPConnection
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic, sleep

import uvicorn
from check_document_types import load_manifest, normalized_document
from check_service import _primary_result, _provider_run, _vlm_result
from fastapi import FastAPI

from app.accounting.models import GLAccount, GLSuggestion, GLSuggestionResult
from app.config import Settings
from app.correction_email.models import CorrectionDraftResult, CorrectionEmailDraft
from app.document_review.models import (
    DocumentClassification,
    DocumentClassificationResult,
    DocumentIssue,
    DocumentType,
    InvoiceDocument,
    InvoiceFields,
)
from app.invoices.service import InvoiceReviewService
from app.main import create_app

PDF_BYTES = b"%PDF-1.7\nfictional invoice\n%%EOF"
type UploadPart = tuple[str, bytes, str]
type UploadParts = Mapping[str, UploadPart] | list[tuple[str, UploadPart]]


@dataclass(frozen=True)
class ApiResponse:
    status_code: int
    headers: dict[str, str]
    content: bytes

    @property
    def text(self) -> str:
        return self.content.decode()

    def json(self) -> object:
        return json_module.loads(self.content)


class ApiClient:
    """Run the app on an ephemeral loopback port for real HTTP checks."""

    def __init__(self, app: FastAPI) -> None:
        self._app = app
        self._socket: socket.socket | None = None
        self._server: uvicorn.Server | None = None
        self._thread: Thread | None = None
        self._port: int | None = None

    def __enter__(self) -> "ApiClient":
        self._socket = socket.socket()
        self._socket.bind(("127.0.0.1", 0))
        self._port = self._socket.getsockname()[1]
        self._server = uvicorn.Server(
            uvicorn.Config(self._app, log_level="error", access_log=False)
        )
        self._thread = Thread(
            target=self._server.run,
            kwargs={"sockets": [self._socket]},
            daemon=True,
        )
        self._thread.start()
        deadline = monotonic() + 5
        while not self._server.started and self._thread.is_alive() and monotonic() < deadline:
            sleep(0.01)
        assert self._server.started, "temporary API server did not start"
        return self

    def __exit__(self, *args: object) -> None:
        assert self._server is not None
        assert self._thread is not None
        self._server.should_exit = True
        self._thread.join(timeout=5)
        assert not self._thread.is_alive(), "temporary API server did not stop"

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        files: UploadParts | None = None,
        json: object | None = None,
    ) -> ApiResponse:
        assert self._port is not None
        request_headers = dict(headers or {})
        body: bytes | None = None
        if files is not None:
            body, content_type = _multipart_body(files)
            request_headers["Content-Type"] = content_type
        elif json is not None:
            body = json_module.dumps(json).encode()
            request_headers["Content-Type"] = "application/json"
        connection = HTTPConnection("127.0.0.1", self._port, timeout=5)
        try:
            connection.request(method, url, body=body, headers=request_headers)
            response = connection.getresponse()
            return ApiResponse(
                status_code=response.status,
                headers={key.lower(): value for key, value in response.getheaders()},
                content=response.read(),
            )
        finally:
            connection.close()

    def get(self, url: str, **kwargs: object) -> ApiResponse:
        return self.request("GET", url, **kwargs)  # type: ignore[arg-type]

    def post(self, url: str, **kwargs: object) -> ApiResponse:
        return self.request("POST", url, **kwargs)  # type: ignore[arg-type]

    def put(self, url: str, **kwargs: object) -> ApiResponse:
        return self.request("PUT", url, **kwargs)  # type: ignore[arg-type]

    def options(self, url: str, **kwargs: object) -> ApiResponse:
        return self.request("OPTIONS", url, **kwargs)  # type: ignore[arg-type]

    def delete(self, url: str, **kwargs: object) -> ApiResponse:
        return self.request("DELETE", url, **kwargs)  # type: ignore[arg-type]


def _multipart_body(files: UploadParts) -> tuple[bytes, str]:
    boundary = "invoice-review-check"
    parts = files.items() if isinstance(files, Mapping) else files
    body = bytearray()
    for field_name, (filename, content, media_type) in parts:
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(
            (
                f'Content-Disposition: form-data; name="{field_name}"; '
                f'filename="{filename}"\r\n'
            ).encode()
        )
        body.extend(f"Content-Type: {media_type}\r\n\r\n".encode())
        body.extend(content)
        body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())
    return bytes(body), f"multipart/form-data; boundary={boundary}"


class FakePrimaryParser:
    def __init__(self, documents: dict[str, InvoiceDocument], calls: list[str]) -> None:
        self._documents = documents
        self._calls = calls

    def parse(self, **kwargs: object):  # type: ignore[no-untyped-def]
        filename = str(kwargs["filename"])
        self._calls.append(f"primary:{filename}")
        return _primary_result(self._documents[filename])


class FakeVLMProvider:
    def __init__(self, documents: dict[str, InvoiceDocument], calls: list[str]) -> None:
        self._documents = documents
        self._calls = calls
        self.fail_draft = False

    def classify_document(self, **kwargs: object) -> DocumentClassificationResult:
        filename = str(kwargs["filename"])
        self._calls.append(f"classification:{filename}")
        if filename == "failed.pdf":
            raise RuntimeError("fictional provider failure")
        return DocumentClassificationResult(
            classification=DocumentClassification(
                document_type=DocumentType.INVOICE,
                confidence=Decimal("0.96"),
                reasoning="Fictional offline classification.",
            ),
            provider_run=_provider_run("qwen-classifier"),
        )

    def review_document(self, **kwargs: object):  # type: ignore[no-untyped-def]
        filename = str(kwargs["filename"])
        self._calls.append(f"review:{filename}")
        return _vlm_result(self._documents[filename])

    def suggest_gl(
        self,
        *,
        document: InvoiceDocument,
        catalog: tuple[GLAccount, ...],
    ) -> GLSuggestionResult:
        assert document.document_type == "invoice"
        assert len(catalog) == 6
        self._calls.append("gl")
        return GLSuggestionResult(
            suggestion=GLSuggestion(
                account_id="6100",
                rationale="Fictional cleaning supplier.",
                confidence=Decimal("0.90"),
            ),
            provider_run=_provider_run("qwen-gl"),
        )

    def draft_correction(
        self,
        *,
        document: InvoiceDocument,
        issues: list[DocumentIssue],
        evidence: object,
    ) -> CorrectionDraftResult:
        assert document.document_type == "invoice"
        assert issues
        assert evidence
        self._calls.append("draft")
        if self.fail_draft:
            raise RuntimeError("fictional draft failure")
        return CorrectionDraftResult(
            draft=CorrectionEmailDraft(
                text="Please correct the supplier VAT ID on this fictional invoice."
            ),
            provider_run=_provider_run("qwen-correction"),
        )


def _error_code(response: ApiResponse) -> str:
    payload = response.json()
    assert isinstance(payload, dict)
    return str(payload["error"]["code"])


def _upload(client: ApiClient, filename: str) -> str:
    response = client.post(
        "/reviews",
        files={"file": (filename, PDF_BYTES, "application/pdf")},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["review_id"])


def _process(client: ApiClient, review_id: str) -> dict[str, object]:
    response = client.post(f"/reviews/{review_id}/process")
    assert response.status_code == 200, response.text
    return response.json()


def run_checks() -> None:
    source = normalized_document(load_manifest()[0])
    assert isinstance(source, InvoiceDocument)
    conflicting_vlm = source.model_copy(
        update={
            "fields": source.fields.model_copy(update={"invoice_number": "VLM-CONFLICT"})
        }
    )
    blocking_fields = source.fields.model_dump(mode="python")
    blocking_fields["vendor_vat_id"] = None
    blocking = source.model_copy(update={"fields": InvoiceFields(**blocking_fields)})
    documents = {
        "valid.pdf": source,
        "reject.pdf": source,
        "blocking.pdf": blocking,
    }
    vlm_documents = {**documents, "valid.pdf": conflicting_vlm}

    with TemporaryDirectory() as temporary_directory:
        settings = Settings(
            _env_file=None,
            invoice_review_data_dir=Path(temporary_directory) / "data",
        )
        app = create_app(settings)
        provider_creations: list[str] = []
        provider_calls: list[str] = []
        fake_vlm = FakeVLMProvider(vlm_documents, provider_calls)

        def primary_factory():  # type: ignore[no-untyped-def]
            provider_creations.append("primary")
            return FakePrimaryParser(documents, provider_calls)

        def vlm_factory():  # type: ignore[no-untyped-def]
            provider_creations.append("vlm")
            return fake_vlm

        app.state.review_service = InvoiceReviewService(
            repository=app.state.repository,
            storage=app.state.storage,
            primary_parser_factory=primary_factory,
            vlm_provider_factory=vlm_factory,
        )

        with ApiClient(app) as client:
            assert client.get("/health").json() == {"status": "ok"}
            assert len(client.get("/gl-catalog").json()) == 6
            for origin in ("http://localhost:5173", "http://127.0.0.1:5173"):
                preflight = client.options(
                    "/reviews",
                    headers={
                        "Origin": origin,
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "content-type",
                    },
                )
                assert preflight.status_code == 200
                assert preflight.headers["access-control-allow-origin"] == origin
            assert provider_creations == []

            missing = client.post("/reviews")
            assert missing.status_code == 422
            assert _error_code(missing) == "request_validation"
            multiple = client.post(
                "/reviews",
                files=[
                    ("file", ("one.pdf", PDF_BYTES, "application/pdf")),
                    ("file", ("two.pdf", PDF_BYTES, "application/pdf")),
                ],
            )
            assert multiple.status_code == 422
            assert _error_code(multiple) == "invalid_upload"
            invalid_uploads = (
                ("empty.pdf", b"", "application/pdf"),
                ("notes.txt", b"not a document", "text/plain"),
                ("renamed.pdf", b"not a pdf", "application/pdf"),
                ("large.pdf", b"%PDF-" + b"x" * (4 * 1024 * 1024), "application/pdf"),
            )
            for filename, content, media_type in invalid_uploads:
                response = client.post(
                    "/reviews",
                    files={"file": (filename, content, media_type)},
                )
                assert response.status_code == 422
                assert _error_code(response) == "invalid_upload"
            assert provider_creations == []

            valid_id = _upload(client, "valid.pdf")
            uploaded = client.get(f"/reviews/{valid_id}").json()
            assert uploaded["state"] == "uploaded"
            assert "storage_key" not in uploaded
            assert "duplicate_key" not in uploaded
            original = client.get(f"/reviews/{valid_id}/original")
            assert original.content == PDF_BYTES
            assert original.headers["content-type"] == "application/pdf"
            assert provider_creations == []

            invalid_state = client.post(f"/reviews/{valid_id}/approve")
            assert invalid_state.status_code == 409
            assert _error_code(invalid_state) == "invalid_review_state"
            processed = _process(client, valid_id)
            assert processed["state"] == "ready_for_review"
            assert processed["conflicts"]["invoice_number"]["status"] == "conflict"
            assert processed["approval_allowed"] is False
            assert provider_creations == ["vlm", "primary"]
            assert client.get("/reviews").json()[0]["counterparty"]

            blocked = client.post(f"/reviews/{valid_id}/approve")
            assert blocked.status_code == 409
            assert _error_code(blocked) == "approval_blocked"
            invalid_gl = client.put(
                f"/reviews/{valid_id}/gl-selection",
                json={"account_id": "9999"},
            )
            assert invalid_gl.status_code == 422
            assert _error_code(invalid_gl) == "invalid_gl_selection"
            assert client.get(f"/reviews/{valid_id}").json()["gl_review"]["selection"] == {
                "account_id": None
            }
            selected = client.put(
                f"/reviews/{valid_id}/gl-selection",
                json={"account_id": "6100"},
            ).json()
            assert selected["gl_review"]["suggestion"]["account_id"] == "6100"
            assert selected["approval_allowed"] is True
            approved = client.post(f"/reviews/{valid_id}/approve").json()
            assert approved["state"] == "approved"
            assert approved["action_metadata"]["action"] == "approved"
            assert approved["approval_allowed"] is False

            stored = app.state.repository.get(valid_id)
            assert stored is not None
            original_path = settings.uploads_dir / stored.storage_key
            assert original_path.exists()
            assert client.delete(f"/reviews/{valid_id}").status_code == 204
            assert not original_path.exists()
            missing_review = client.get(f"/reviews/{valid_id}")
            assert missing_review.status_code == 404
            assert _error_code(missing_review) == "review_not_found"

            failed_id = _upload(client, "failed.pdf")
            failed = _process(client, failed_id)
            assert failed["state"] == "failed"
            assert failed["failure_message"].startswith("Document classification")
            assert client.delete(f"/reviews/{failed_id}").status_code == 204

            reject_id = _upload(client, "reject.pdf")
            assert _process(client, reject_id)["state"] == "ready_for_review"
            rejected = client.post(f"/reviews/{reject_id}/reject").json()
            assert rejected["state"] == "rejected"
            assert rejected["action_metadata"]["action"] == "rejected"
            assert client.delete(f"/reviews/{reject_id}").status_code == 204

            blocking_id = _upload(client, "blocking.pdf")
            blocking_review = _process(client, blocking_id)
            assert blocking_review["blocking_issue_count"] > 0
            draft = client.post(f"/reviews/{blocking_id}/correction-draft")
            assert draft.status_code == 200
            assert "supplier VAT ID" in draft.json()["draft"]["text"]
            assert client.get(f"/reviews/{blocking_id}").json()["state"] == "ready_for_review"
            fake_vlm.fail_draft = True
            failed_draft = client.post(f"/reviews/{blocking_id}/correction-draft")
            assert failed_draft.status_code == 502
            assert _error_code(failed_draft) == "provider_failure"
            fake_vlm.fail_draft = False
            correction = client.post(f"/reviews/{blocking_id}/correction-request").json()
            assert correction["state"] == "correction_requested"
            assert correction["action_metadata"]["action"] == "correction_requested"
            assert client.post(f"/reviews/{blocking_id}/correction-draft").status_code == 200
            assert client.delete(f"/reviews/{blocking_id}").status_code == 204
            assert client.get("/reviews").json() == []

        app.state.repository.close()


if __name__ == "__main__":
    run_checks()
    print("PASS: minimal API upload, processing, review actions, errors, CORS, and deletion")
