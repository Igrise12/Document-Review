from pydantic import BaseModel, ConfigDict, Field

from app.document_review.models import Probability, ProviderRunMetadata


class GLAccount(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    account_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    category: str = Field(min_length=1)


class GLSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str = Field(min_length=1)
    rationale: str = Field(min_length=1)
    confidence: Probability


class GLSuggestionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion: GLSuggestion | None = None
    provider_run: ProviderRunMetadata


class GLSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str | None = None


class GLSelectionValidation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str | None = None
    valid: bool
    reason: str | None = None


class GLReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    suggestion: GLSuggestion | None = None
    selection: GLSelection | None = None
    validation: GLSelectionValidation | None = None
