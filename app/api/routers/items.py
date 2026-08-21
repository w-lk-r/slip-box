import base64
import json

from boto3.dynamodb.conditions import Attr
from fastapi import APIRouter, Query

from clients import items_table
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
