from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).resolve().parents[1] / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    local_vlm_runtime: Literal["ollama", "vllm"] = "ollama"
    local_vlm_base_url: AnyHttpUrl = "http://localhost:11434/v1"
    local_vlm_model: str = Field(default="qwen2.5vl:7b", min_length=1)
    local_vlm_api_key: str | None = None
    local_vlm_timeout_seconds: float = Field(default=120, gt=0)
    local_vlm_max_structured_output_retries: int = Field(default=2, ge=0, le=3)

    paddleocr_engine: str = Field(default="paddle", min_length=1)
    paddleocr_device: str = Field(default="cpu", min_length=1)

    invoice_review_data_dir: Path = Field(
        default_factory=lambda: Path.home() / ".invoice-review"
    )

    @property
    def data_dir(self) -> Path:
        return self.invoice_review_data_dir.expanduser().resolve()

    @property
    def database_path(self) -> Path:
        return self.data_dir / "invoice-review.sqlite3"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
