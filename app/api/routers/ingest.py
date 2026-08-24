import json
import uuid

from fastapi import APIRouter, HTTPException

from clients import S3_BUCKET, WORKER_FUNCTION_NAME, ingest_sessions_table, items_table, lambda_client, s3
from linkgen import parse_frontmatter
from models import IngestRequest, IngestResponse, IngestStatusResponse, SummarizeRequest

router = APIRouter()


def _mode_instruction(req: IngestRequest) -> str:
    if req.mode == "single":
        if req.topic:
            return (
                f"The user selected single-note mode for this ingestion, focused on the topic: {req.topic}. "
                "Summarize the source into one atomic note about that topic specifically, skipping other "
                "ideas in the source that aren't related to it. If the source doesn't cover this topic, "
                "even tangentially, write nothing and briefly say why."
            )
        return (
            "The user selected single-note mode for this ingestion. Summarize the source into one atomic "
            "note focused on its single most important or central idea, rather than covering every idea "
            "the source touches on."
        )
    if req.mode == "all":
        return "Extract ALL the distinct key ideas from this source and create one atomic note per idea."
    return ""  # auto — agent's own default judgment, unchanged


def _build_prompt(req: IngestRequest) -> str:
    if req.text:
        source = (
            f"Source URL (pass this as source_url to write_note — do not fetch it, "
            f"the content below is already the full source): {req.source_url}\n\n{req.text}"
            if req.source_url else req.text
        )
    elif req.pdf_key:
        source = (
            f'Ingest this uploaded PDF: call read_pdf(pdf_key="{req.pdf_key}") first to read it, '
            f'then write notes from its content. Pass source_pdf_key="{req.pdf_key}" to write_note '
            f"(not source_url) so the citation resolves to this PDF."
        )
    else:
        source = f"Ingest this URL: {req.url}"
    instruction = _mode_instruction(req)
    return f"{instruction}\n\n{source}" if instruction else source


@router.post("/ingest", status_code=202, response_model=IngestResponse)
def ingest(req: IngestRequest):
    if req.research:
        raise HTTPException(status_code=501, detail="research mode not yet supported via the API")

    session_id = f"session-{uuid.uuid4()}"
    payload = {"prompt": _build_prompt(req), "session_id": session_id}
    lambda_client.invoke(
        FunctionName=WORKER_FUNCTION_NAME,
        InvocationType="Event",
        Payload=json.dumps(payload).encode(),
    )
    return IngestResponse(session_id=session_id)


def _fetch_note_text(note_id: str) -> tuple[str, str] | None:
    """(title, body) for one note, same S3+frontmatter read items.py's
    get_item already does — inlined here rather than imported across
    routers, since this is the only other place that needs it. Returns None
    if the note doesn't exist, so the caller can collect all missing ids
    before failing, rather than 404ing on the first one."""
    item = items_table.get_item(Key={"note_id": note_id}).get("Item")
    if not item:
        return None
    raw = s3.get_object(Bucket=S3_BUCKET, Key=item["s3_key"])["Body"].read().decode()
    _frontmatter, body = parse_frontmatter(raw)
    return item["title"], body.strip()


def _build_summarize_prompt(note_ids: list[str]) -> str:
    notes = {note_id: _fetch_note_text(note_id) for note_id in note_ids}
    missing = [note_id for note_id, text in notes.items() if text is None]
    if missing:
        raise HTTPException(status_code=404, detail=f"note(s) not found: {', '.join(missing)}")

    # Declarative, not imperative-commanding — this project hit a real
    # Guardrails PROMPT_ATTACK false positive earlier from command-shaped
    # ingestion phrasing (see _mode_instruction above); describing the
    # situation rather than issuing orders avoided it. Also explicit that
    # this bypasses the "4 or more" threshold: that guardrail in main.py's
    # system prompt is scoped to the agent's own automatic-discovery bullet,
    # not this direct, already-curated request.
    intro = (
        "This is a direct request from the user, who has already selected these specific notes to "
        "synthesize. Write a summary card now via write_summary, grounding it in exactly these note_ids, "
        "without waiting for the usual four-or-more-notes threshold — that threshold is for your own "
        "automatic cluster discovery, not a request where the selection has already been made."
    )
    body_sections = "\n\n".join(
        f"Note ({note_id}): {title}\n{text}" for note_id, (title, text) in notes.items()
    )
    return f"{intro}\n\n{body_sections}"


@router.post("/summarize", status_code=202, response_model=IngestResponse)
def summarize(req: SummarizeRequest):
    session_id = f"session-{uuid.uuid4()}"
    payload = {"prompt": _build_summarize_prompt(req.note_ids), "session_id": session_id, "mode": "summarize"}
    lambda_client.invoke(
        FunctionName=WORKER_FUNCTION_NAME,
        InvocationType="Event",
        Payload=json.dumps(payload).encode(),
    )
    return IngestResponse(session_id=session_id)


@router.get("/ingest/{session_id}", response_model=IngestStatusResponse)
def get_ingest_status(session_id: str):
    item = ingest_sessions_table.get_item(Key={"session_id": session_id}).get("Item")
    if item is None:
        # POST /ingest invokes the Worker asynchronously and returns 202
        # immediately, so a client can poll before the Worker's own seed
        # write lands — that's still "processing", not a 404.
        return IngestStatusResponse(session_id=session_id, status="processing")
    return IngestStatusResponse(
        session_id=session_id,
        status=item["status"],
        notes_created=item.get("notes_created", []),
        skipped_reason=item.get("skipped_reason"),
        error=item.get("error"),
    )
