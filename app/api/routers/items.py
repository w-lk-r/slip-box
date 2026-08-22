import base64
import json

from boto3.dynamodb.conditions import Attr, Key
from fastapi import APIRouter, HTTPException, Query

from clients import S3_BUCKET, items_table, s3, sources_table
from linkgen import parse_frontmatter
from models import ItemType
from serialize import clean

router = APIRouter()


def _encode_cursor(key: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(key).encode()).decode()


def _decode_cursor(cursor: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())


@router.get("/items")
def list_items(type: ItemType | None = None, limit: int = Query(100, ge=1, le=500), cursor: str | None = None):
    # Query recent-index (gsi_pk is a constant — see app-stack.ts) instead of
    # Scan, which has no ordering guarantee at all. Sorted newest-first via
    # the index's created_at sort key.
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
