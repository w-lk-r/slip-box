from typing import Literal

from pydantic import BaseModel, Field, HttpUrl, model_validator

EdgeType = Literal["SUPPORTS", "CONTRADICTS", "EXTENDS", "RELATED_TO", "GROUNDED_IN"]
ItemType = Literal["literature-note", "summary-card", "permanent-note"]


IngestMode = Literal["auto", "single", "all"]


class IngestRequest(BaseModel):
    text: str | None = Field(None, max_length=200_000)
    url: HttpUrl | None = None
    # S3 key of an uploaded PDF, from a prior POST /uploads/presign call
    # (e.g. "uploads/{upload_id}/{filename}.pdf") — mutually exclusive with
    # text/url, same as they are with each other.
    pdf_key: str | None = Field(None, max_length=1024)
    # Only valid alongside text — for a client that already fetched the
    # content itself (e.g. the Expo app pre-fetching a YouTube transcript
    # client-side, since AWS's own IPs are blocked by YouTube's transcript
    # endpoint) and wants the note's citation to still point at the source,
    # instead of losing attribution the way plain text ingestion would.
    source_url: HttpUrl | None = None
    research: bool = False
    # auto: agent's own single-vs-multi-idea judgment (default, unchanged behavior).
    # single: force exactly one note — `topic` picks the angle, or the agent
    #   picks the single most central idea if `topic` is omitted.
    # all: force extracting every distinct idea into its own note.
    mode: IngestMode = "auto"
    topic: str | None = Field(None, max_length=200)

    @model_validator(mode="after")
    def exactly_one_source(self):
        provided = [bool(self.text), self.url is not None, bool(self.pdf_key)]
        if sum(provided) != 1:
            raise ValueError("exactly one of text, url, or pdf_key is required")
        if self.source_url and not self.text:
            raise ValueError("source_url is only valid alongside text")
        return self


class IngestResponse(BaseModel):
    session_id: str
    status: Literal["processing"] = "processing"


class NoteRef(BaseModel):
    note_id: str
    title: str = ""


class IngestStatusResponse(BaseModel):
    session_id: str
    status: Literal["processing", "complete", "error"]
    notes_created: list[NoteRef] = []
    skipped_reason: str | None = None
    error: str | None = None


# 20MB is a pragmatic guardrail, not a verified Bedrock document-size limit —
# the Converse API's DocumentSource shape has no documented max in its
# service model (only a min:1 byte constraint), and the actual ceiling is
# presumably a runtime/model-side limit rather than a schema one. This just
# stops an accidental whole-book upload from silently failing deep inside an
# agent invocation instead of at the point of upload.
MAX_PDF_SIZE_BYTES = 20 * 1024 * 1024


class FileToPresign(BaseModel):
    filename: str
    size: int = Field(..., gt=0, le=MAX_PDF_SIZE_BYTES)


class PresignRequest(BaseModel):
    files: list[FileToPresign] = Field(..., min_length=1, max_length=50)


class PresignedFile(BaseModel):
    filename: str
    key: str
    upload_url: str


class PresignResponse(BaseModel):
    upload_id: str
    files: list[PresignedFile]


class EdgePatch(BaseModel):
    type: EdgeType | None = None
    confidence: float | None = Field(None, ge=0, le=1)
    reason: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def at_least_one_field(self):
        if self.type is None and self.confidence is None:
            raise ValueError("provide at least one of type or confidence to update")
        return self


class IndexKeywordRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=100)


class SummarizeRequest(BaseModel):
    # min 2: a "summary" of one note isn't a synthesis (CLAUDE.md's
    # SummaryCard is cluster-synthesis, not a single-note rollup). max 20 is
    # a pragmatic sanity cap, same shape as PresignRequest's max_length=50.
    note_ids: list[str] = Field(..., min_length=2, max_length=20)
