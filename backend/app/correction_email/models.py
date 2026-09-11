from pydantic import BaseModel, ConfigDict, Field

from app.document_review.models import ProviderRunMetadata


class CorrectionEmailDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)


class CorrectionDraftResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft: CorrectionEmailDraft
    provider_run: ProviderRunMetadata
