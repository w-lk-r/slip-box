import datetime
from decimal import Decimal

from fastapi import APIRouter, HTTPException

from clients import edges_table
from linkgen import regenerate_note_links
from models import EdgePatch
from serialize import clean

router = APIRouter()


@router.patch("/edges/{from_id}/{edge_id}")
def patch_edge(from_id: str, edge_id: str, patch: EdgePatch):
    existing = edges_table.get_item(Key={"from_id": from_id, "edge_id": edge_id}).get("Item")
    if not existing:
        raise HTTPException(status_code=404, detail="edge not found")

    type_changed = patch.type is not None and patch.type != existing.get("type")

    now = datetime.datetime.utcnow().isoformat()
    history_entry = {"action": "edited", "by": "user", "at": now}
    if patch.type is not None:
        history_entry["type"] = patch.type
    if patch.confidence is not None:
        history_entry["confidence"] = Decimal(str(patch.confidence))
    if patch.reason:
        history_entry["reason"] = patch.reason

    set_parts = ["history = list_append(history, :h)"]
    names = {}
    values = {":h": [history_entry]}
    if patch.type is not None:
        set_parts.append("#t = :type")
        names["#t"] = "type"
        values[":type"] = patch.type
    if patch.confidence is not None:
        set_parts.append("confidence = :confidence")
        values[":confidence"] = Decimal(str(patch.confidence))

    update_kwargs = {
        "Key": {"from_id": from_id, "edge_id": edge_id},
        "UpdateExpression": "SET " + ", ".join(set_parts),
        "ExpressionAttributeValues": values,
    }
    if names:
        update_kwargs["ExpressionAttributeNames"] = names
    edges_table.update_item(**update_kwargs)

    if type_changed:
        regenerate_note_links(from_id)

    updated = edges_table.get_item(Key={"from_id": from_id, "edge_id": edge_id}).get("Item")
    return clean(updated)


@router.delete("/edges/{from_id}/{edge_id}")
def delete_edge(from_id: str, edge_id: str):
    existing = edges_table.get_item(Key={"from_id": from_id, "edge_id": edge_id}).get("Item")
    if not existing:
        raise HTTPException(status_code=404, detail="edge not found")

    edges_table.delete_item(Key={"from_id": from_id, "edge_id": edge_id})
    regenerate_note_links(from_id)
    return {"deleted": True}
