from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.invoices.repository import InvoiceReviewRepository
from app.invoices.routes import router as invoice_router
from app.invoices.storage import LocalFileStorage


def create_app() -> FastAPI:
    settings = get_settings()
    repository = InvoiceReviewRepository(settings.database_path)
    repository.initialize()
    storage = LocalFileStorage(settings.uploads_dir)
    app = FastAPI(title="Invoice Review")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=False,
        allow_methods=["GET"],
        allow_headers=[],
    )
    app.state.settings = settings
    app.state.repository = repository
    app.state.storage = storage
    app.include_router(invoice_router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
