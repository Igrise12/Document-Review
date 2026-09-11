from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.invoices.repository import InvoiceReviewRepository
from app.invoices.routes import ApiError, ApiErrorDetail, ApiErrorResponse
from app.invoices.routes import router as invoice_router
from app.invoices.service import (
    CorrectionDraftProviderError,
    InvoiceReviewService,
    ReviewNotFoundError,
    ReviewWorkflowError,
)
from app.invoices.storage import LocalFileStorage
from app.providers.paddleocr import PaddleOCRParser
from app.providers.qwen import QwenVLMProvider


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    repository = InvoiceReviewRepository(settings.database_path)
    repository.initialize()
    storage = LocalFileStorage(settings.uploads_dir)
    review_service = InvoiceReviewService(
        repository=repository,
        storage=storage,
        primary_parser_factory=lambda: PaddleOCRParser(settings),
        vlm_provider_factory=lambda: QwenVLMProvider(settings),
    )
    app = FastAPI(title="Invoice Review")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )
    app.state.settings = settings
    app.state.repository = repository
    app.state.storage = storage
    app.state.review_service = review_service
    app.include_router(invoice_router)

    @app.exception_handler(ApiError)
    def api_error(_request: Request, error: ApiError) -> JSONResponse:
        return _error_response(error.status_code, error.code, str(error))

    @app.exception_handler(ReviewNotFoundError)
    def review_not_found(_request: Request, _error: ReviewNotFoundError) -> JSONResponse:
        return _error_response(
            status.HTTP_404_NOT_FOUND,
            "review_not_found",
            "Review was not found.",
        )

    @app.exception_handler(ReviewWorkflowError)
    def review_workflow_error(
        _request: Request,
        error: ReviewWorkflowError,
    ) -> JSONResponse:
        status_code = (
            status.HTTP_422_UNPROCESSABLE_CONTENT
            if error.code == "invalid_gl_selection"
            else status.HTTP_409_CONFLICT
        )
        return _error_response(status_code, error.code, str(error))

    @app.exception_handler(CorrectionDraftProviderError)
    def correction_provider_error(
        _request: Request,
        error: CorrectionDraftProviderError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_502_BAD_GATEWAY,
            "provider_failure",
            str(error),
        )

    @app.exception_handler(RequestValidationError)
    def request_validation_error(
        _request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "request_validation",
            "The request does not match the API contract.",
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    payload = ApiErrorResponse(error=ApiErrorDetail(code=code, message=message))
    return JSONResponse(status_code=status_code, content=payload.model_dump())
