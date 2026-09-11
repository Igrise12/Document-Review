from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="Invoice Review")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
