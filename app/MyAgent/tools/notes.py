import re
import uuid
import json
import datetime
import logging
import os
from decimal import Decimal

import boto3
import httpx
from boto3.dynamodb.conditions import Key
from dotenv import load_dotenv
from strands import tool

from config import EDGE_CONFIDENCE_THRESHOLD, FETCH_URL_MAX_CHARS, KB_RETRIEVE_TOP_K

load_dotenv()

log = logging.getLogger(__name__)

S3_BUCKET = os.environ["S3_BUCKET"]
KB_ID = os.environ["KB_ID"]
ITEMS_TABLE = os.environ["ITEMS_TABLE"]
EDGES_TABLE = os.environ["EDGES_TABLE"]
REGION = os.environ.get("AWS_REGION", os.environ.get("REGION", "ap-southeast-2"))

s3 = boto3.client("s3", region_name=REGION)
ddb = boto3.resource("dynamodb", region_name=REGION)
bedrock_agent = boto3.client("bedrock-agent", region_name=REGION)
bedrock_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)

# Frontmatter link field each edge type is written into on the *source* note's
# own card (Luhmann-style — connections live on the card, not a separate index).
EDGE_TYPE_TO_FIELD = {
    "SUPPORTS": "supports",
    "CONTRADICTS": "contradicts",
    "EXTENDS": "extends",
    "RELATED_TO": "related_to",
    "GROUNDED_IN": "grounded_in",
}


def _slugify(title: str) -> str:
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[\s_-]+', '-', slug)
    return slug.strip('-')[:60]


def _parse_frontmatter(content: str) -> tuple[dict, str]:
    """
    Parse the fixed frontmatter schema this module writes (flat scalars + simple
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


def _render_frontmatter(fields: dict) -> str:
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


def _regenerate_note_links(note_id: str) -> None:
    """
    Rewrite a note's frontmatter link lists from its current outgoing edges in
    DynamoDB, as [[note_id|Title]] wikilinks so Obsidian's graph/backlinks pick
    them up. Preserves every other frontmatter field (title, tags, date, ...) and
    the body exactly as they currently are in S3 — S3 stays source of truth for
    note content, this only ever touches the generated link fields.
    """
    item = ddb.Table(ITEMS_TABLE).get_item(Key={"note_id": note_id}).get("Item")
    if not item:
        log.warning(f"Cannot regenerate links: note {note_id} not found in items table")
        return

    s3_key = item["s3_key"]
    existing = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)["Body"].read().decode()
    fields, body = _parse_frontmatter(existing)

    edges = ddb.Table(EDGES_TABLE).query(KeyConditionExpression=Key("from_id").eq(note_id)).get("Items", [])
    by_type: dict[str, list[str]] = {}
    for edge in edges:
        by_type.setdefault(edge["type"], []).append(edge["to_id"])

    target_ids = {tid for ids in by_type.values() for tid in ids}
    titles = {}
    for tid in target_ids:
        target = ddb.Table(ITEMS_TABLE).get_item(Key={"note_id": tid}).get("Item")
        titles[tid] = target["title"] if target else tid

    for edge_type, field in EDGE_TYPE_TO_FIELD.items():
        fields[field] = [f"[[{tid}|{titles[tid]}]]" for tid in by_type.get(edge_type, [])]

    s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=(_render_frontmatter(fields) + body).encode(), ContentType="text/markdown")
    log.info(f"Regenerated links for {note_id}: {sum(len(v) for v in by_type.values())} edges")


@tool
def write_note(title: str, body: str, source_url: str = "", tags: list[str] = []) -> dict:
    """
    Write an atomic literature note to the slip case knowledge base.

    Creates a .md file and .md.metadata.json sidecar in S3, and a record in
    DynamoDB items table. The sidecar keeps frontmatter out of KB embeddings.
    Call trigger_kb_sync after writing all notes for this ingestion.

    Args:
        title: Precise, descriptive title for the note — becomes the filename
        body: Note body in clear prose, capturing the idea in relation to its source
        source_url: URL or citation for the source material
        tags: Concept tags for the note

    Returns:
        dict with note_id, s3_key, and title
    """
    note_id = f"{_slugify(title)}-{uuid.uuid4().hex[:8]}"
    s3_key = f"{note_id}.md"
    today = datetime.date.today().isoformat()

    tag_lines = "\n".join(f"  - {t}" for t in tags) if tags else "  []"
    md_content = f"""---
title: {title}
note_id: {note_id}
type: literature-note
authored_by: model
source: {source_url}
date: {today}
tags:
{tag_lines}
supports: []
contradicts: []
extends: []
related_to: []
---

{body}
"""

    # Sidecar keeps frontmatter out of KB embeddings — only body gets indexed
    metadata = {
        "note_id": note_id,
        "type": "literature-note",
        "authored_by": "model",
        "source": source_url,
        "date": today,
        "tags": ", ".join(tags),
    }

    s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=md_content.encode(), ContentType="text/markdown")
    s3.put_object(Bucket=S3_BUCKET, Key=f"{s3_key}.metadata.json", Body=json.dumps(metadata).encode(), ContentType="application/json")

    ddb.Table(ITEMS_TABLE).put_item(Item={
        "note_id": note_id,
        "type": "literature-note",
        "authored_by": "model",
        "title": title,
        "s3_key": s3_key,
        "source_url": source_url,
        "date": today,
        "tags": tags,
        "created_at": datetime.datetime.utcnow().isoformat(),
    })

    log.info(f"Written note: {s3_key}")
    return {"note_id": note_id, "s3_key": s3_key, "title": title}


@tool
def write_edge(from_id: str, to_id: str, edge_type: str, confidence: float, reason: str = "") -> dict:
    """
    Propose a typed connection from one note to another. Writes it to the edges
    table only if confidence meets EDGE_CONFIDENCE_THRESHOLD — below-threshold
    edges are dropped entirely, no queue. On write, regenerates the source note's
    frontmatter link list so the connection shows up on its card as a [[wikilink]].

    Args:
        from_id: note_id of the note this connection originates from
        to_id: note_id of the note being connected to
        edge_type: SUPPORTS, CONTRADICTS, EXTENDS, or RELATED_TO for connections between
            literature notes. GROUNDED_IN is reserved for a permanent-note or summary-card
            citing the literature note it's grounded in — do not use it between two
            literature notes.
        confidence: how confident you are in this classification, 0-1
        reason: one-sentence justification, kept in the edge's history for provenance

    Returns:
        dict with written: bool, and edge_id if written
    """
    edge_type = edge_type.strip().upper()
    if edge_type not in EDGE_TYPE_TO_FIELD:
        return {"written": False, "error": f"edge_type must be one of {sorted(EDGE_TYPE_TO_FIELD)}"}
    if not 0 <= confidence <= 1:
        return {"written": False, "error": "confidence must be between 0 and 1"}
    if edge_type == "GROUNDED_IN":
        source = ddb.Table(ITEMS_TABLE).get_item(Key={"note_id": from_id}).get("Item")
        if not source or source.get("type") not in ("permanent-note", "summary-card"):
            return {
                "written": False,
                "error": "GROUNDED_IN must originate from a permanent-note or summary-card, not a literature-note. "
                         "Use SUPPORTS, CONTRADICTS, EXTENDS, or RELATED_TO between literature notes instead.",
            }
    if confidence < EDGE_CONFIDENCE_THRESHOLD:
        log.info(f"Edge dropped below threshold: {from_id} -{edge_type}-> {to_id} ({confidence})")
        return {"written": False, "reason": "below confidence threshold"}

    now = datetime.datetime.utcnow().isoformat()
    edge_id = uuid.uuid4().hex
    confidence_dec = Decimal(str(confidence))
    ddb.Table(EDGES_TABLE).put_item(Item={
        "from_id": from_id,
        "edge_id": edge_id,
        "to_id": to_id,
        "type": edge_type,
        "confidence": confidence_dec,
        "authored_by": "model",
        "created_at": now,
        "history": [{"action": "created", "by": "model", "at": now, "confidence": confidence_dec, "reason": reason}],
    })

    _regenerate_note_links(from_id)
    log.info(f"Written edge: {from_id} -{edge_type}-> {to_id} ({confidence})")
    return {"written": True, "edge_id": edge_id}


@tool
def search_notes(query: str) -> list[dict]:
    """
    Search existing notes in the knowledge base for content related to the query.
    Use this after writing notes to find existing slip case entries that may connect.

    Args:
        query: Natural language search query

    Returns:
        List of matching notes with content and relevance score
    """
    response = bedrock_runtime.retrieve(
        knowledgeBaseId=KB_ID,
        retrievalQuery={"text": query},
        retrievalConfiguration={"managedSearchConfiguration": {"numberOfResults": KB_RETRIEVE_TOP_K}},
    )
    return [
        {
            "score": r.get("score"),
            "content": r.get("content", {}).get("text", ""),
            "location": r.get("location", {}).get("s3Location", {}).get("uri", ""),
        }
        for r in response.get("retrievalResults", [])
    ]


@tool
def write_summary(title: str, body: str, grounded_in: list[str] = [], tags: list[str] = []) -> dict:
    """
    Write a summary card — a synthesis note spanning multiple literature notes.
    Use this when you identify a conceptual centre, a recurring theme, or a
    cluster of notes that form a coherent argument. Written immediately, no draft.

    Args:
        title: Descriptive title capturing the synthesis
        body: The synthesis in clear prose — the argument, pattern, or insight
              that emerges from the grounded notes taken together
        grounded_in: List of note_ids this summary draws from
        tags: Concept tags

    Returns:
        dict with note_id, s3_key, and title
    """
    note_id = f"{_slugify(title)}-{uuid.uuid4().hex[:8]}"
    s3_key = f"{note_id}.md"
    today = datetime.date.today().isoformat()

    tag_lines = "\n".join(f"  - {t}" for t in tags) if tags else "  []"
    grounded_lines = "\n".join(f"  - {n}" for n in grounded_in) if grounded_in else "  []"
    md_content = f"""---
title: {title}
note_id: {note_id}
type: summary-card
authored_by: model
date: {today}
tags:
{tag_lines}
grounded_in:
{grounded_lines}
related_to: []
---

{body}
"""

    metadata = {
        "note_id": note_id,
        "type": "summary-card",
        "authored_by": "model",
        "date": today,
        "tags": ", ".join(tags),
    }

    s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=md_content.encode(), ContentType="text/markdown")
    s3.put_object(Bucket=S3_BUCKET, Key=f"{s3_key}.metadata.json", Body=json.dumps(metadata).encode(), ContentType="application/json")

    ddb.Table(ITEMS_TABLE).put_item(Item={
        "note_id": note_id,
        "type": "summary-card",
        "authored_by": "model",
        "title": title,
        "s3_key": s3_key,
        "grounded_in": grounded_in,
        "date": today,
        "tags": tags,
        "created_at": datetime.datetime.utcnow().isoformat(),
    })

    log.info(f"Written summary card: {s3_key}")
    return {"note_id": note_id, "s3_key": s3_key, "title": title}


@tool
def update_summary(summary_note_id: str, add_note_ids: list[str] = [], remove_note_ids: list[str] = []) -> dict:
    """
    Add or remove notes from an existing summary card's cluster.
    Use this when a new note clearly belongs to an existing cluster rather than
    warranting a new summary card. A note can belong to multiple clusters — call
    this for each relevant summary card.

    Args:
        summary_note_id: note_id of the summary card to update
        add_note_ids: note_ids to add to this cluster
        remove_note_ids: note_ids to remove from this cluster

    Returns:
        dict with note_id and updated grounded_in list
    """
    table = ddb.Table(ITEMS_TABLE)
    result = table.get_item(Key={"note_id": summary_note_id})
    item = result.get("Item")
    if not item:
        return {"error": f"Summary card {summary_note_id} not found"}

    current = set(item.get("grounded_in", []))
    current.update(add_note_ids)
    current.difference_update(remove_note_ids)
    grounded_in = list(current)

    table.update_item(
        Key={"note_id": summary_note_id},
        UpdateExpression="SET grounded_in = :g, updated_at = :u",
        ExpressionAttributeValues={
            ":g": grounded_in,
            ":u": datetime.datetime.utcnow().isoformat(),
        },
    )

    # Regenerate frontmatter from the current S3 copy, not DynamoDB — preserves
    # any hand-edited title/tags/date instead of silently reverting them the
    # next time an unrelated update_summary call touches this note.
    s3_key = item["s3_key"]
    existing = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)["Body"].read().decode()
    fields, body = _parse_frontmatter(existing)
    fields["grounded_in"] = grounded_in

    s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=(_render_frontmatter(fields) + body).encode(), ContentType="text/markdown")
    log.info(f"Updated summary card cluster: {s3_key}")
    return {"note_id": summary_note_id, "grounded_in": grounded_in}


@tool
def trigger_kb_sync() -> str:
    """
    Trigger a sync of the knowledge base to index newly written notes.
    Always call this after writing one or more notes.

    Returns:
        Ingestion job ID
    """
    sources = bedrock_agent.list_data_sources(knowledgeBaseId=KB_ID)
    data_source_id = sources["dataSourceSummaries"][0]["dataSourceId"]
    response = bedrock_agent.start_ingestion_job(knowledgeBaseId=KB_ID, dataSourceId=data_source_id)
    job_id = response["ingestionJob"]["ingestionJobId"]
    log.info(f"KB sync started: {job_id}")
    return job_id


@tool
def fetch_url(url: str) -> str:
    """
    Fetch the text content of a URL for ingestion.
    Use this when the user provides a URL rather than pasting content directly.

    Args:
        url: The URL to fetch

    Returns:
        Page text content (HTML tags stripped, capped at 50k characters)
    """
    with httpx.Client(follow_redirects=True, timeout=30) as client:
        response = client.get(url, headers={"User-Agent": "SlipBox/1.0"})
        response.raise_for_status()
        text = re.sub(r'<[^>]+>', ' ', response.text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:FETCH_URL_MAX_CHARS]
