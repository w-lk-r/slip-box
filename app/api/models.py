from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

EdgeType = Literal["SUPPORTS", "CONTRADICTS", "EXTENDS", "RELATED_TO", "GROUNDED_IN"]
ItemType = Literal["literature-note", "summary-card", "permanent-note"]


IngestMode = Literal["auto", "single", "all"]


class IngestRequest(BaseModel):
    text: str | None = Field(None, max_length=200_000)
    url: HttpUrl | None = None
    research: bool = False
    # auto: agent's own single-vs-multi-idea judgment (default, unchanged behavior).
    # single: force exactly one note — `topic` picks the angle, or the agent
    #   picks the single most central idea if `topic` is omitted.
    # all: force extracting every distinct idea into its own note.
    mode: IngestMode = "auto"
    topic: str | None = Field(None, max_length=200)

    @model_validator(mode="after")
    def one_of_text_or_url(self):
        if not self.text and not self.url:
            raise ValueError("one of text or url is required")
        if self.text and self.url:
            raise ValueError("provide only one of text or url")
        return self


class IngestResponse(BaseModel):
    session_id: str
    status: Literal["processing"] = "processing"


class EdgePatch(BaseModel):
    type: EdgeType | None = None
    confidence: float | None = Field(None, ge=0, le=1)
    reason: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def at_least_one_field(self):
        if self.type is None and self.confidence is None:
            raise ValueError("provide at least one of type or confidence to update")
        return self
