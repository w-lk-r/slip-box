"""
Frontmatter link regeneration — trimmed copy of the same-named functions in
app/MyAgent/tools/notes.py. Duplicated rather than shared because this package
and MyAgent are two separate deployable units (Lambda zip vs. AgentCore Runtime
CodeZip) with no shared-library convention in this repo. Keep in sync manually.
reconciler.py (review-todo #9's Stage 1) is a consumer of this module too, but
lives in this same package, so it imports these functions directly rather than
needing its own copy.
"""
import datetime
import json
import logging
import re
import uuid
from decimal import Decimal

from boto3.dynamodb.conditions import Key

from clients import KB_ID, S3_BUCKET, bedrock_agent, edges_table, items_table, s3

log = logging.getLogger(__name__)


def slugify(title: str) -> str:
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[\s_-]+', '-', slug)
    return slug.strip('-')[:60]

# Frontmatter link field each edge type is written into on the *source* note's
# own card (Luhmann-style — connections live on the card, not a separate index).
EDGE_TYPE_TO_FIELD = {
    "SUPPORTS": "supports",
    "CONTRADICTS": "contradicts",
    "EXTENDS": "extends",
    "RELATED_TO": "related_to",
    "GROUNDED_IN": "grounded_in",
}


def parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Parse the fixed frontmatter schema this project writes (flat scalars + simple
    list blocks). Not a general YAML parser — only handles the shapes write_note/
    write_summary/write_edge produce.
    """
    end = content.find("\n---\n", 4)
    fm_lines = content[4:end].split("\n") if content.startswith("---\n") and end != -1 else []
    body = content[end + 5:] if end != -1 else content

    fields: dict = {}
    i = 0
    while i < len(fm_lines):
        line = fm_lines[i]
        if not line.strip() or line.startswith(" "):
            i += 1
            continue
        key, _, val = line.partition(":")
        key, val = key.strip(), val.strip()
        if val:
            fields[key] = [] if val == "[]" else val
            i += 1
            continue
        # Scalar with empty value vs. start of a list block — peek ahead.
        nxt = fm_lines[i + 1].strip() if i + 1 < len(fm_lines) else ""
        if nxt == "[]":
            fields[key] = []
            i += 2
        elif nxt.startswith("-"):
            items = []
            i += 1
            while i < len(fm_lines) and fm_lines[i].strip().startswith("-"):
                items.append(fm_lines[i].strip()[1:].strip())
                i += 1
            fields[key] = items
        else:
            fields[key] = ""
            i += 1
    return fields, body


def render_frontmatter(fields: dict) -> str:
    lines = ["---"]
    for key, val in fields.items():
        if isinstance(val, list):
            if val:
                lines.append(f"{key}:")
                lines.extend(f"  - {v}" for v in val)
            else:
                lines.append(f"{key}: []")
        else:
            lines.append(f"{key}: {val}")
    lines.append("---\n")
    return "\n".join(lines)


def regenerate_note_links(note_id: str) -> None:
    """
    Rewrite a note's frontmatter link lists from its current outgoing edges in
    DynamoDB, as [[note_id|Title]] wikilinks so Obsidian's graph/backlinks pick
    them up. Preserves every other frontmatter field (title, tags, date, ...) and
    the body exactly as they currently are in S3 — S3 stays source of truth for
    note content, this only ever touches the generated link fields.
    """
    item = items_table.get_item(Key={"note_id": note_id}).get("Item")
    if not item:
        log.warning(f"Cannot regenerate links: note {note_id} not found in items table")
        return

    s3_key = item["s3_key"]
    existing = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)["Body"].read().decode()
    fields, body = parse_frontmatter(existing)

    edges = edges_table.query(KeyConditionExpression=Key("from_id").eq(note_id)).get("Items", [])
    by_type: dict[str, list[str]] = {}
    for edge in edges:
        by_type.setdefault(edge["type"], []).append(edge["to_id"])

    target_ids = {tid for ids in by_type.values() for tid in ids}
    titles = {}
    for tid in target_ids:
        target = items_table.get_item(Key={"note_id": tid}).get("Item")
        titles[tid] = target["title"] if target else tid

    for edge_type, field in EDGE_TYPE_TO_FIELD.items():
        fields[field] = [f"[[{tid}|{titles[tid]}]]" for tid in by_type.get(edge_type, [])]

    s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=(render_frontmatter(fields) + body).encode(), ContentType="text/markdown")
    log.info(f"Regenerated links for {note_id}: {sum(len(v) for v in by_type.values())} edges")


def write_edge_record(from_id: str, to_id: str, edge_type: str, confidence: float, reason: str = "", regenerate: bool = True) -> str:
    """
    Unconditional edge write — trimmed copy of _write_edge_record in
    app/MyAgent/tools/notes.py, for direct (non-agent) writes originating from
    a user action in the API rather than a model classification.
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    edge_id = uuid.uuid4().hex
    edges_table.put_item(Item={
        "from_id": from_id,
        "edge_id": edge_id,
        "to_id": to_id,
        "type": edge_type,
        "confidence": Decimal(str(confidence)),
        "authored_by": "user",
        "created_at": now,
        "history": [{"action": "created", "by": "user", "at": now, "confidence": Decimal(str(confidence)), "reason": reason}],
    })
    if regenerate:
        regenerate_note_links(from_id)
    log.info(f"Written edge: {from_id} -{edge_type}-> {to_id} ({confidence})")
    return edge_id


def write_permanent_note(title: str, body: str, tags: list[str], grounded_in: list[str]) -> dict:
    """
    Direct write path for a PermanentNote — no agent in the loop (CLAUDE.md:
    "Agent never creates a PermanentNote vertex or writes to its body. Write
    path is direct: frontend -> FastAPI -> S3 + DynamoDB + KB sync trigger").
    Deliberately omits authored_by (always user-authored, no draft state) and
    source_id (a PermanentNote has no source of its own — it cites literature
    notes via GROUNDED_IN edges instead, written below).
    """
    note_id = f"{slugify(title)}-{uuid.uuid4().hex[:8]}"
    s3_key = f"{note_id}.md"
    today = datetime.date.today().isoformat()

    tag_lines = "\n".join(f"  - {t}" for t in tags) if tags else "  []"
    md_content = f"""---
title: {title}
note_id: {note_id}
type: permanent-note
date: {today}
tags:
{tag_lines}
supports: []
contradicts: []
extends: []
related_to: []
grounded_in: []
---

{body}
"""

    metadata = {"note_id": note_id, "type": "permanent-note", "date": today, "tags": ", ".join(tags)}

    s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=md_content.encode(), ContentType="text/markdown")
    s3.put_object(Bucket=S3_BUCKET, Key=f"{s3_key}.metadata.json", Body=json.dumps(metadata).encode(), ContentType="application/json")

    items_table.put_item(Item={
        "note_id": note_id,
        "type": "permanent-note",
        "title": title,
        "s3_key": s3_key,
        "date": today,
        "tags": tags,
        "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "gsi_pk": "item",
    })

    # GROUNDED_IN edges are the user's own explicit citations, not a scored
    # classification — write them directly (confidence 1.0), same pattern
    # write_summary uses for its grounded_in list. Skip the per-call
    # frontmatter regen and do it once after the loop instead.
    for member_id in grounded_in:
        write_edge_record(note_id, member_id, "GROUNDED_IN", 1.0, reason="cited at note creation", regenerate=False)
    if grounded_in:
        regenerate_note_links(note_id)

    log.info(f"Written permanent note: {s3_key}")
    return {"note_id": note_id, "s3_key": s3_key, "title": title}


def trigger_kb_sync() -> str:
    """Direct port of the agent tool of the same name (app/MyAgent/tools/notes.py)."""
    sources = bedrock_agent.list_data_sources(knowledgeBaseId=KB_ID)
    data_source_id = sources["dataSourceSummaries"][0]["dataSourceId"]
    response = bedrock_agent.start_ingestion_job(knowledgeBaseId=KB_ID, dataSourceId=data_source_id)
    job_id = response["ingestionJob"]["ingestionJobId"]
    log.info(f"KB sync started: {job_id}")
    return job_id
