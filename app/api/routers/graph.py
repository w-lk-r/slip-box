from fastapi import APIRouter

from clients import edges_table, items_table
from serialize import clean

router = APIRouter()


@router.get("/graph")
def get_graph():
    items = clean(items_table.scan().get("Items", []))
    edges = clean(edges_table.scan().get("Items", []))

    nodes = [
        {
            "id": item["note_id"],
            "label": item.get("title", item["note_id"]),
            "type": item.get("type"),
            "authored_by": item.get("authored_by"),
            "created_at": item.get("created_at"),
        }
        for item in items
    ]
    links = [
        {
            "source": edge["from_id"],
            "target": edge["to_id"],
            "edge_id": edge["edge_id"],
            "type": edge.get("type"),
            "confidence": edge.get("confidence"),
            "authored_by": edge.get("authored_by"),
        }
        for edge in edges
    ]
    return {"nodes": nodes, "edges": links}
