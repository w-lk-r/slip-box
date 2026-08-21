import json
import uuid

from fastapi import APIRouter, HTTPException

from clients import WORKER_FUNCTION_NAME, lambda_client
from models import IngestRequest, IngestResponse

router = APIRouter()


def _build_prompt(req: IngestRequest) -> str:
    if req.text:
        return req.text
    return f"Ingest this URL: {req.url}"


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
