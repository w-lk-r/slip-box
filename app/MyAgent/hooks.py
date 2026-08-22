import datetime
import json
import logging
import os

import boto3
from strands.hooks import HookProvider, HookRegistry
from strands.hooks.events import AfterInvocationEvent, AfterToolCallEvent

log = logging.getLogger(__name__)

INGEST_SESSIONS_TABLE = os.environ["INGEST_SESSIONS_TABLE"]
REGION = os.environ.get("AWS_REGION", os.environ.get("REGION", "ap-southeast-2"))

ddb = boto3.resource("dynamodb", region_name=REGION)
ingest_sessions_table = ddb.Table(INGEST_SESSIONS_TABLE)

# Tool names whose successful result counts as "a note got created" for this
# turn's outcome. Kept in sync by hand with the @tool functions in tools/notes.py.
_TRACKED_TOOLS = {"write_note", "write_summary"}
_SKIPPED_REASON_MAX_CHARS = 500


def _extract_note_ref(result: dict) -> dict | None:
    """Pull {note_id, title} out of a write_note/write_summary ToolResult.

    write_note/write_summary return a plain dict, so Strands' @tool decorator
    JSON-serializes it into a single text content block rather than wrapping
    it in the {status, content} shape a tool can return directly — see
    strands/tools/decorator.py's _wrap_tool_result.
    """
    for block in result.get("content", []):
        text = block.get("text")
        if text is None:
            continue
        try:
            data = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict) and "note_id" in data:
            return {"note_id": data["note_id"], "title": data.get("title", "")}
    return None


def _extract_skipped_reason(message: dict | None) -> str:
    if not message:
        return ""
    for block in message.get("content", []):
        text = block.get("text")
        if text:
            return text[:_SKIPPED_REASON_MAX_CHARS]
    return ""


def _update_session(session_id: str, fields: dict) -> None:
    names = {f"#{k}": k for k in fields}
    values = {f":{k}": v for k, v in fields.items()}
    ingest_sessions_table.update_item(
        Key={"session_id": session_id},
        UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in fields),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


class IngestOutcomeTracker(HookProvider):
    """Tracks whether a turn actually created any notes, and why not when it
    didn't, writing the outcome to slip-box-ingest-sessions. Replaces grepping
    a 2000-char-truncated Worker log line with structured, in-process data —
    see the strands-agents-sdk skill's Lifecycle hooks section.

    One instance per agent invocation — construct with the session_id being
    served, same lifetime as the Agent object in main.py's agent_factory().
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.notes_created: list[dict] = []

    def register_hooks(self, registry: HookRegistry) -> None:
        registry.add_callback(AfterToolCallEvent, self._on_tool_call)
        registry.add_callback(AfterInvocationEvent, self._on_turn_end)

    def _on_tool_call(self, event: AfterToolCallEvent) -> None:
        if event.tool_use["name"] not in _TRACKED_TOOLS or event.exception is not None:
            return
        if event.result.get("status") != "success":
            return
        note_ref = _extract_note_ref(event.result)
        if note_ref:
            self.notes_created.append(note_ref)

    def _on_turn_end(self, event: AfterInvocationEvent) -> None:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        fields = {
            "status": "complete",
            "notes_created": self.notes_created,
            "completed_at": now,
        }
        if not self.notes_created:
            message = event.result.message if event.result else None
            fields["skipped_reason"] = _extract_skipped_reason(message)
        try:
            _update_session(self.session_id, fields)
        except Exception:
            log.exception("Failed to write ingest outcome for session %s", self.session_id)
