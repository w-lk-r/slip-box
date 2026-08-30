import base64
import datetime
import json
import logging
import uuid

from boto3.dynamodb.conditions import Attr, Key
from fastapi import APIRouter, HTTPException, Query

from clients import S3_BUCKET, WORKER_FUNCTION_NAME, edges_table, items_table, lambda_client, s3, sources_table
from linkgen import parse_frontmatter, trigger_kb_sync, write_permanent_note
from models import IndexKeywordRequest, IngestResponse, ItemType, PermanentNoteCreateRequest
from serialize import clean

log = logging.getLogger(__name__)

router = APIRouter()


def _encode_cursor(key: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


def _decode_cursor(cursor: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())


@router.get("/items")
def list_items(
    type: ItemType | None = None,
    source_id: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    cursor: str | None = None,
):
    if source_id:
        # source-index has no sort key, so there's no "newest first" here —
        # fine for "everything from this source", a small, bounded set.
        kwargs = {"IndexName": "source-index", "KeyConditionExpression": Key("source_id").eq(source_id), "Limit": limit}
        if type:
            kwargs["FilterExpression"] = Attr("type").eq(type)
    else:
        # Query recent-index (gsi_pk is a constant — see app-stack.ts) instead
        # of Scan, which has no ordering guarantee at all. Sorted newest-first
        # via the index's created_at sort key.
        kwargs = {
            "IndexName": "recent-index",
            "KeyConditionExpression": Key("gsi_pk").eq("item"),
            "ScanIndexForward": False,
            "Limit": limit,
        }
        if type:
            kwargs["FilterExpression"] = Attr("type").eq(type)
    if cursor:
        kwargs["ExclusiveStartKey"] = _decode_cursor(cursor)

    response = items_table.query(**kwargs)
    items = clean(response.get("Items", []))
    for item in items:
        item.pop("gsi_pk", None)
    result = {"items": items}
    if "LastEvaluatedKey" in response:
        result["cursor"] = _encode_cursor(response["LastEvaluatedKey"])
    return result


@router.post("/items/permanent", status_code=201)
def create_permanent_note(req: PermanentNoteCreateRequest):
    """
    Direct write path for a PermanentNote — no agent in the loop (see
    CLAUDE.md's note-taxonomy section). Registered before GET /items/{note_id}
    so the literal "permanent" path segment isn't swallowed by that route's
    {note_id} match.
    """
    missing = [nid for nid in req.grounded_in if not items_table.get_item(Key={"note_id": nid}).get("Item")]
    if missing:
        raise HTTPException(status_code=404, detail=f"note(s) not found: {', '.join(missing)}")

    result = write_permanent_note(req.title, req.body, req.tags, req.grounded_in)
    try:
        trigger_kb_sync()
    except Exception:
        log.exception(f"KB sync trigger failed after writing permanent note {result['note_id']}")
    return result


@router.get("/sources")
def list_sources():
    response = sources_table.scan()
    return {"sources": clean(response.get("Items", []))}


def _edges_for_note(note_id: str) -> tuple[list[dict], list[dict]]:
    """Structured outgoing/incoming edges for one note, both directions,
    each carrying the other note's title so callers don't need a second
    round trip just to display a link. Shared by get_review_queue (bulk,
    unreviewed items only) and get_item (single note, always)."""
    outgoing = edges_table.query(KeyConditionExpression=Key("from_id").eq(note_id)).get("Items", [])
    incoming = edges_table.query(
        IndexName="to_id-index", KeyConditionExpression=Key("to_id").eq(note_id)
    ).get("Items", [])

    other_ids = {e["to_id"] for e in outgoing} | {e["from_id"] for e in incoming}
    titles = {}
    index_keywords_by_id = {}
    for other_id in other_ids:
        other = items_table.get_item(Key={"note_id": other_id}).get("Item")
        titles[other_id] = other["title"] if other else other_id
        # Surfaces "sub index cards" on the note detail screen: a neighbor
        # that's itself a curated entry point gets flagged, without a
        # separate endpoint — see docs/frontend-ux-spec.md's Index Cards
        # section.
        index_keywords_by_id[other_id] = other.get("index_keywords", []) if other else []

    outgoing_edges = [
        {
            "edge_id": e["edge_id"],
            "to_id": e["to_id"],
            "to_title": titles.get(e["to_id"], e["to_id"]),
            "to_index_keywords": clean(index_keywords_by_id.get(e["to_id"], [])),
            "type": e.get("type"),
            "confidence": clean(e.get("confidence")),
        }
        for e in outgoing
    ]
    incoming_edges = [
        {
            "edge_id": e["edge_id"],
            "from_id": e["from_id"],
            "from_title": titles.get(e["from_id"], e["from_id"]),
            "from_index_keywords": clean(index_keywords_by_id.get(e["from_id"], [])),
            "type": e.get("type"),
            "confidence": clean(e.get("confidence")),
        }
        for e in incoming
    ]
    return outgoing_edges, incoming_edges


@router.get("/items/review-queue")
def get_review_queue():
    # reviewed_at is absent (not null) when unreviewed — see
    # docs/frontend-ux-spec.md's "Reviewed status" section for why an
    # omitted attribute, not a stored false/null, is the deliberate shape.
    response = items_table.query(
        IndexName="recent-index",
        KeyConditionExpression=Key("gsi_pk").eq("item"),
        FilterExpression=Attr("reviewed_at").not_exists(),
        ScanIndexForward=False,
    )
    items = response.get("Items", [])

    result = []
    for item in items:
        outgoing_edges, incoming_edges = _edges_for_note(item["note_id"])
        entry = clean(item)
        entry.pop("gsi_pk", None)
        entry["outgoing_edges"] = outgoing_edges
        entry["incoming_edges"] = incoming_edges
        result.append(entry)

    return {"items": result}


@router.post("/items/{note_id}/review")
def mark_reviewed(note_id: str):
    if not items_table.get_item(Key={"note_id": note_id}).get("Item"):
        raise HTTPException(status_code=404, detail="item not found")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    items_table.update_item(
        Key={"note_id": note_id},
        UpdateExpression="SET reviewed_at = :r",
        ExpressionAttributeValues={":r": now},
    )
    updated = items_table.get_item(Key={"note_id": note_id}).get("Item")
    updated.pop("gsi_pk", None)
    return clean(updated)


@router.delete("/items/{note_id}/review")
def unmark_reviewed(note_id: str):
    if not items_table.get_item(Key={"note_id": note_id}).get("Item"):
        raise HTTPException(status_code=404, detail="item not found")
    items_table.update_item(Key={"note_id": note_id}, UpdateExpression="REMOVE reviewed_at")
    updated = items_table.get_item(Key={"note_id": note_id}).get("Item")
    updated.pop("gsi_pk", None)
    return clean(updated)


@router.get("/index")
def list_index():
    # index_keywords is absent (sparse), not [], on notes that aren't a
    # curated entry point for anything — see docs/frontend-ux-spec.md's
    # Index Cards section. A full scan is a real tradeoff on a growing
    # table, but entries stay sparse by design, so the matching-row count
    # stays small regardless of total corpus size — same reasoning
    # get_review_queue's own doc comment already states for its own scan.
    response = items_table.scan(FilterExpression=Attr("index_keywords").exists())
    entries: dict[str, list[dict]] = {}
    for item in response.get("Items", []):
        note_ref = {"note_id": item["note_id"], "title": item.get("title"), "type": item.get("type")}
        for keyword in item.get("index_keywords", []):
            entries.setdefault(keyword, []).append(note_ref)
    return {"entries": [{"keyword": k, "notes": clean(v)} for k, v in sorted(entries.items())]}


@router.post("/items/{note_id}/index-keywords")
def add_index_keyword(note_id: str, body: IndexKeywordRequest):
    item = items_table.get_item(Key={"note_id": note_id}).get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="item not found")
    keyword = body.keyword.strip()
    keywords = item.get("index_keywords", [])
    if keyword not in keywords:
        items_table.update_item(
            Key={"note_id": note_id},
            UpdateExpression="SET index_keywords = :k",
            ExpressionAttributeValues={":k": [*keywords, keyword]},
        )
    updated = items_table.get_item(Key={"note_id": note_id}).get("Item")
    updated.pop("gsi_pk", None)
    return clean(updated)


@router.delete("/items/{note_id}/index-keywords/{keyword}")
def remove_index_keyword(note_id: str, keyword: str):
    item = items_table.get_item(Key={"note_id": note_id}).get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="item not found")
    keywords = [k for k in item.get("index_keywords", []) if k != keyword]
    if keywords:
        items_table.update_item(
            Key={"note_id": note_id},
            UpdateExpression="SET index_keywords = :k",
            ExpressionAttributeValues={":k": keywords},
        )
    else:
        # Sparse convention: REMOVE the attribute entirely once its last
        # keyword is gone, rather than leaving a stored [] behind.
        items_table.update_item(Key={"note_id": note_id}, UpdateExpression="REMOVE index_keywords")
    updated = items_table.get_item(Key={"note_id": note_id}).get("Item")
    updated.pop("gsi_pk", None)
    return clean(updated)


@router.get("/items/{note_id}")
def get_item(note_id: str):
    item = items_table.get_item(Key={"note_id": note_id}).get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="item not found")

    existing = s3.get_object(Bucket=S3_BUCKET, Key=item["s3_key"])["Body"].read().decode()
    frontmatter, body = parse_frontmatter(existing)

    link_fields = ("supports", "contradicts", "extends", "related_to", "grounded_in")
    connections = {field: frontmatter.get(field, []) for field in link_fields if field in frontmatter}

    item.pop("gsi_pk", None)
    source = None
    source_id = item.pop("source_id", None)
    if source_id:
        source_item = sources_table.get_item(Key={"source_id": source_id}).get("Item")
        if source_item:
            source = clean({
                "source_id": source_id,
                "title": source_item.get("title"),
                "url": source_item.get("url") or None,
                "type": source_item.get("type"),
                "author": source_item.get("author") or None,
            })

    outgoing_edges, incoming_edges = _edges_for_note(note_id)

    result = clean(item)
    result["body"] = body.strip()
    result["connections"] = connections
    result["source"] = source
    result["outgoing_edges"] = outgoing_edges
    result["incoming_edges"] = incoming_edges
    return result


@router.post("/items/{note_id}/find-connections", status_code=202, response_model=IngestResponse)
def find_connections(note_id: str):
    """
    Triggers a reclassification pass for one already-existing permanent-note
    or summary-card, asking the classification agent to search for
    connections it wasn't given at creation time — the "Find more
    connections" button in the raw-write flow (CLAUDE.md's PermanentNote
    section). Reuses reconciler.py's exact Stage 2 mechanism (mode:
    "reclassify" via the Worker Lambda) rather than building new async
    infrastructure — the same GET /ingest/{session_id} polling endpoint
    every other async action in this API already uses reports the result.
    """
    item = items_table.get_item(Key={"note_id": note_id}).get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="item not found")
    if item.get("type") not in ("permanent-note", "summary-card"):
        raise HTTPException(status_code=400, detail="find-connections is only for a permanent-note or summary-card")

    existing = s3.get_object(Bucket=S3_BUCKET, Key=item["s3_key"])["Body"].read().decode()
    _frontmatter, body = parse_frontmatter(existing)
    title = item.get("title") or note_id

    # Declarative, not imperative — see ingest.py's _build_summarize_prompt
    # for the Guardrails PROMPT_ATTACK false positive this phrasing style
    # avoided. Explicitly names this note's own type so the classification
    # agent knows GROUNDED_IN is available here (see the conditional in its
    # own system prompt, app/MyAgent/agents/classification.py) — never for two literature notes.
    prompt = (
        f'This {item["type"]} ("{title}", note_id: {note_id}) already exists and was just asked to find more '
        f"connections for itself. Search the knowledge base for genuinely related notes and score any real "
        f"connections — including GROUNDED_IN toward a literature note this note is truly grounded in, not just "
        f"RELATED_TO. Existing connections don't need to be re-added.\n\n{body.strip()}"
    )
    session_id = f"session-{uuid.uuid4()}"
    lambda_client.invoke(
        FunctionName=WORKER_FUNCTION_NAME,
        InvocationType="Event",
        Payload=json.dumps({"prompt": prompt, "session_id": session_id, "mode": "reclassify"}).encode(),
    )
    return IngestResponse(session_id=session_id)


@router.delete("/items/{note_id}", status_code=202)
def delete_item(note_id: str):
    """Deletes only the S3 object(s) — deliberately does NOT touch the
    DynamoDB item/edges/summary-card state directly. reconciler.py's
    _handle_delete is triggered by the resulting S3 ObjectRemoved event and
    already does the full three-checks cascade (outgoing edges, incoming
    edges, grounded_in scrub) correctly; doing any of that here too would
    both duplicate it and risk deleting the item row before that handler
    gets a chance to look up its s3_key, which is exactly the dangling-
    reference bug docs/schema-change-checklist.md warns about."""
    item = items_table.get_item(Key={"note_id": note_id}).get("Item")
    if not item:
        raise HTTPException(status_code=404, detail="item not found")

    s3_key = item["s3_key"]
    s3.delete_object(Bucket=S3_BUCKET, Key=s3_key)
    # Sidecar isn't suffix-matched by the reconciler's S3 event filter, so
    # deleting it doesn't retrigger anything — best-effort cleanup only.
    s3.delete_object(Bucket=S3_BUCKET, Key=f"{s3_key}.metadata.json")

    return {"note_id": note_id, "status": "deleting"}
