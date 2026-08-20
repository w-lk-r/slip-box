import re
import uuid
import json
import datetime
import logging
import os

import boto3
import httpx
from dotenv import load_dotenv
from strands import tool

from config import FETCH_URL_MAX_CHARS, KB_RETRIEVE_TOP_K

load_dotenv()

log = logging.getLogger(__name__)

S3_BUCKET = os.environ["S3_BUCKET"]
KB_ID = os.environ["KB_ID"]
ITEMS_TABLE = os.environ["ITEMS_TABLE"]
REGION = os.environ.get("AWS_REGION", os.environ.get("REGION", "ap-southeast-2"))

s3 = boto3.client("s3", region_name=REGION)
ddb = boto3.resource("dynamodb", region_name=REGION)
bedrock_agent = boto3.client("bedrock-agent", region_name=REGION)
bedrock_runtime = boto3.client("bedrock-agent-runtime", region_name=REGION)


def _slugify(title: str) -> str:
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[\s_-]+', '-', slug)
    return slug.strip('-')[:60]


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

    # Regenerate S3 frontmatter, preserving the existing body
    s3_key = item["s3_key"]
    existing = s3.get_object(Bucket=S3_BUCKET, Key=s3_key)["Body"].read().decode()
    end_of_frontmatter = existing.find("\n---\n", 4)
    body = existing[end_of_frontmatter + 5:] if end_of_frontmatter != -1 else ""

    tag_lines = "\n".join(f"  - {t}" for t in item.get("tags", [])) or "  []"
    grounded_lines = "\n".join(f"  - {n}" for n in grounded_in) or "  []"
    md_content = f"""---
title: {item["title"]}
note_id: {summary_note_id}
type: summary-card
authored_by: {item.get("authored_by", "model")}
date: {item["date"]}
tags:
{tag_lines}
grounded_in:
{grounded_lines}
related_to: []
---
{body}"""

    s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=md_content.encode(), ContentType="text/markdown")
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
