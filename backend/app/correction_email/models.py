from pydantic import BaseModel, ConfigDict, Field


class CorrectionEmailDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
