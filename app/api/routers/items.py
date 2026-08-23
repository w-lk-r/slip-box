import base64
import datetime
import json

from boto3.dynamodb.conditions import Attr, Key
from fastapi import APIRouter, HTTPException, Query

from clients import S3_BUCKET, edges_table, items_table, s3, sources_table
from linkgen import parse_frontmatter
from models import ItemType
from serialize import clean

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


@router.get("/sources")
def list_sources():
    response = sources_table.scan()
    return {"sources": clean(response.get("Items", []))}


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
        note_id = item["note_id"]
        outgoing = edges_table.query(KeyConditionExpression=Key("from_id").eq(note_id)).get("Items", [])
        incoming = edges_table.query(
            IndexName="to_id-index", KeyConditionExpression=Key("to_id").eq(note_id)
        ).get("Items", [])

        other_ids = {e["to_id"] for e in outgoing} | {e["from_id"] for e in incoming}
        titles = {}
        for other_id in other_ids:
            other = items_table.get_item(Key={"note_id": other_id}).get("Item")
            titles[other_id] = other["title"] if other else other_id

        entry = clean(item)
        entry.pop("gsi_pk", None)
        entry["outgoing_edges"] = [
            {
                "edge_id": e["edge_id"],
                "to_id": e["to_id"],
                "to_title": titles.get(e["to_id"], e["to_id"]),
                "type": e.get("type"),
                "confidence": clean(e.get("confidence")),
            }
            for e in outgoing
        ]
        entry["incoming_edges"] = [
            {
                "edge_id": e["edge_id"],
                "from_id": e["from_id"],
                "from_title": titles.get(e["from_id"], e["from_id"]),
                "type": e.get("type"),
                "confidence": clean(e.get("confidence")),
            }
            for e in incoming
        ]
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

    result = clean(item)
    result["body"] = body.strip()
    result["connections"] = connections
    result["source"] = source
    return result
