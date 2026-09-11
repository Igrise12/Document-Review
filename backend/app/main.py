from fastapi import FastAPI

from app.config import get_settings
from app.invoices.repository import InvoiceReviewRepository
from app.invoices.storage import LocalFileStorage


def create_app() -> FastAPI:
    settings = get_settings()
    repository = InvoiceReviewRepository(settings.database_path)
    repository.initialize()
    storage = LocalFileStorage(settings.uploads_dir)
    app = FastAPI(title="Invoice Review")
    app.state.settings = settings
    app.state.repository = repository
    app.state.storage = storage

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
