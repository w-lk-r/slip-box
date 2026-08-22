import json
import uuid

from fastapi import APIRouter, HTTPException

from clients import WORKER_FUNCTION_NAME, ingest_sessions_table, lambda_client
from models import IngestRequest, IngestResponse, IngestStatusResponse

router = APIRouter()


def _mode_instruction(req: IngestRequest) -> str:
    if req.mode == "single":
        if req.topic:
            return (
                f"Create exactly ONE atomic note from this source, focused specifically on: {req.topic}. "
                "Ignore other ideas in the source that aren't about this topic. If the source doesn't "
                "actually cover this topic — not even tangentially — don't force a note about it; say so "
                "briefly instead and write nothing."
            )
        return (
            "Create exactly ONE atomic note from this source. Pick the single most important or central "
            "idea and write about only that one — do not create multiple notes even if the source touches "
            "on several ideas."
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
