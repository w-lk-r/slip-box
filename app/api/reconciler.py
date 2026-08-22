"""
S3 -> DynamoDB reconciliation — review-todo.md #9's Stage 1. Deterministic,
no agent/model call involved on purpose: this is what guarantees DynamoDB's
items table never silently drifts from what's actually in S3, regardless of
write origin (the agent's own tools, a hand-edit, aws s3 sync). Triggered by
an S3 event notification on slip-box-notes, suffix-filtered to .md so the
.md.metadata.json sidecar never triggers this on its own writes.

Semantic reclassification (do this note's connections still make sense after
an edit?) is a separate, optional Stage 2 — not built here, and deliberately
not a dependency of this Lambda's own correctness.
"""
import datetime
import json
import logging
import urllib.parse
import uuid

from boto3.dynamodb.conditions import Attr, Key

from clients import S3_BUCKET, edges_table, items_table, s3
from linkgen import parse_frontmatter, regenerate_note_links, render_frontmatter, slugify

log = logging.getLogger(__name__)

REQUIRED_LINK_FIELDS = ("supports", "contradicts", "extends", "related_to")


def handler(event, context):
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"])
        if record["eventName"].startswith("ObjectRemoved"):
            _handle_delete(bucket, key)
        else:
            _handle_upsert(bucket, key)


def _handle_upsert(bucket: str, key: str) -> None:
    try:
        content = s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode()
        fields, body = parse_frontmatter(content)
    except Exception:
        log.exception(f"Skipping unparseable note at {key}")
        return

    note_id = fields.get("note_id") or ""
    if not note_id:
        # Note created entirely outside the system (e.g. a hand-written
        # Obsidian file pushed up via aws s3 sync) — backfill everything the
        # rest of the system assumes exists, same shape write_note produces.
        title = fields.get("title") or key.rsplit("/", 1)[-1].removesuffix(".md")
        note_id = f"{slugify(title)}-{uuid.uuid4().hex[:8]}"
        fields["note_id"] = note_id
        fields.setdefault("title", title)
        fields.setdefault("type", "literature-note")
        fields.setdefault("authored_by", "user")
        fields.setdefault("date", datetime.date.today().isoformat())
        if not isinstance(fields.get("tags"), list):
            fields["tags"] = []
        for link_field in REQUIRED_LINK_FIELDS:
            fields.setdefault(link_field, [])

        s3.put_object(Bucket=bucket, Key=key, Body=(render_frontmatter(fields) + body).encode(), ContentType="text/markdown")
        metadata = {
            "note_id": note_id,
            "type": fields["type"],
            "authored_by": fields["authored_by"],
            "date": fields["date"],
            "tags": ", ".join(fields["tags"]),
        }
        s3.put_object(Bucket=bucket, Key=f"{key}.metadata.json", Body=json.dumps(metadata).encode(), ContentType="application/json")

    # Preserve created_at on a re-upsert — a trivial hand-edit must not bump
    # the note to the top of the Recent list. Only a genuinely new row gets
    # "now". Not re-deriving source_id from the frontmatter's source
    # wikilink here, and not touching the typed link-list fields at all —
    # those are edge-derived from DynamoDB, never the reverse; see the
    # design note in docs/review-todo.md #9.
    existing = items_table.get_item(Key={"note_id": note_id}).get("Item")
    created_at = existing["created_at"] if existing else datetime.datetime.now(datetime.timezone.utc).isoformat()

    # A partial update, not put_item — regenerate_note_links (called from
    # _handle_delete, and from the agent's own write_edge/update_summary)
    # rewrites this same file to S3, which re-triggers this same handler on
    # the same key. A full put_item there would silently wipe attributes
    # Stage 1 doesn't manage (grounded_in, a real one caught live) on that
    # redundant re-trigger. update_item only touches the fields listed here,
    # leaving everything else on the row alone — making the self-retrigger
    # idempotent instead of destructive.
    tags = fields.get("tags")
    values = {
        "type": fields.get("type", "literature-note"),
        "authored_by": fields.get("authored_by", "user"),
        "title": fields.get("title", ""),
        "s3_key": key,
        "date": fields.get("date", ""),
        "tags": tags if isinstance(tags, list) else [],
        "created_at": created_at,
        "gsi_pk": "item",
    }
    items_table.update_item(
        Key={"note_id": note_id},
        UpdateExpression="SET " + ", ".join(f"#{k} = :{k}" for k in values),
        ExpressionAttributeNames={f"#{k}": k for k in values},
        ExpressionAttributeValues={f":{k}": v for k, v in values.items()},
    )
    log.info(f"Reconciled {note_id} from {key}")


def _handle_delete(bucket: str, key: str) -> None:
    matches = items_table.scan(FilterExpression=Attr("s3_key").eq(key)).get("Items", [])
    if not matches:
        log.info(f"No item found for deleted key {key}, nothing to clean up")
        return
    note_id = matches[0]["note_id"]

    outgoing = edges_table.query(KeyConditionExpression=Key("from_id").eq(note_id)).get("Items", [])
    for edge in outgoing:
        edges_table.delete_item(Key={"from_id": note_id, "edge_id": edge["edge_id"]})

    incoming = edges_table.query(IndexName="to_id-index", KeyConditionExpression=Key("to_id").eq(note_id)).get("Items", [])
    affected_from_ids = set()
    for edge in incoming:
        edges_table.delete_item(Key={"from_id": edge["from_id"], "edge_id": edge["edge_id"]})
        affected_from_ids.add(edge["from_id"])

    for from_id in affected_from_ids:
        source = items_table.get_item(Key={"note_id": from_id}).get("Item")
        if source and source.get("type") == "summary-card" and note_id in source.get("grounded_in", []):
            grounded_in = [n for n in source["grounded_in"] if n != note_id]
            items_table.update_item(
                Key={"note_id": from_id},
                UpdateExpression="SET grounded_in = :g",
                ExpressionAttributeValues={":g": grounded_in},
            )
        regenerate_note_links(from_id)

    items_table.delete_item(Key={"note_id": note_id})
    log.info(f"Cleaned up deleted note {note_id} ({key}): {len(outgoing)} outgoing, {len(incoming)} incoming edges removed")
