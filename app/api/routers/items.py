import base64
import json

from boto3.dynamodb.conditions import Attr
from fastapi import APIRouter, HTTPException, Query

from clients import S3_BUCKET, items_table, s3
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
    kwargs = {"Limit": limit}
    if type:
        kwargs["FilterExpression"] = Attr("type").eq(type)
    if cursor:
        kwargs["ExclusiveStartKey"] = _decode_cursor(cursor)

    response = items_table.scan(**kwargs)
    result = {"items": clean(response.get("Items", []))}
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

    result = clean(item)
    result["body"] = body.strip()
    result["connections"] = connections
    return result
