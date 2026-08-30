"""
The 8 custom @tool functions both agents use (see app/MyAgent/agents/ for
which agent owns which — app/MyAgent/CLAUDE.md has the full table), grouped
under a TOOLS section below. Everything under INTERNAL HELPERS is a private
(_-prefixed) implementation detail no agent calls directly.
"""
import re
import uuid
import json
import datetime
import logging
import os
import urllib.parse
from decimal import Decimal


import boto3
import httpx
from boto3.dynamodb.conditions import Attr, Key
from dotenv import load_dotenv
from strands import tool
from youtube_transcript_api import CouldNotRetrieveTranscript, YouTubeTranscriptApi


from config import EDGE_CONFIDENCE_THRESHOLD, FETCH_URL_MAX_CHARS, KB_RETRIEVE_TOP_K


load_dotenv()


log = logging.getLogger(__name__)


S3_BUCKET = os.environ["S3_BUCKET"]
KB_ID = os.environ["KB_ID"]
ITEMS_TABLE = os.environ["ITEMS_TABLE"]
EDGES_TABLE = os.environ["EDGES_TABLE"]
SOURCES_TABLE = os.environ["SOURCES_TABLE"]
UPLOADS_BUCKET = os.environ["UPLOADS_BUCKET"]
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


# ============================================================================
# TOOLS
# ============================================================================


@tool
def write_note(title: str, body: str, source_url: str = "", source_pdf_key: str = "", source_title: str = "", source_author: str = "", tags: list[str] = []) -> dict:
    """
    Write an atomic literature note to the slip case knowledge base.

    Creates a .md file and .md.metadata.json sidecar in S3, and a record in
    DynamoDB items table. The sidecar keeps frontmatter out of KB embeddings.
    Call trigger_kb_sync after writing all notes for this ingestion.

    Args:
        title: Precise, descriptive title for the note — becomes the filename
        body: Note body in clear prose, capturing the idea in relation to its source
        source_url: URL of the source material, if any. The same URL always
            resolves to the same Source record (deduped), so re-ingesting the
            same source doesn't create a duplicate citation.
        source_pdf_key: S3 key of an uploaded PDF source, if any (the same
            pdf_key passed to read_pdf) — mutually exclusive with source_url.
            The same PDF always resolves to the same Source record.
        source_title: Title of the source itself (article headline, video title —
            distinct from this note's own title), if known
        source_author: Author, channel, or publisher of the source, if known
        tags: Concept tags for the note

    Returns:
        dict with note_id, s3_key, and title
    """
    note_id = f"{_slugify(title)}-{uuid.uuid4().hex[:8]}"
    s3_key = f"{note_id}.md"
    today = datetime.date.today().isoformat()

    source_id = _resolve_source(source_url, source_pdf_key, source_title, source_author)
    source_display = source_title or source_url or (source_pdf_key.rsplit("/", 1)[-1] if source_pdf_key else "")
    source_field = f"[[{source_id}|{source_display}]]" if source_id else ""

    tag_lines = "\n".join(f"  - {t}" for t in tags) if tags else "  []"
    md_content = f"""---
title: {title}
note_id: {note_id}
type: literature-note
authored_by: model
source: {source_field}
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

    # Sidecar keeps frontmatter out of KB embeddings — only body gets indexed.
    # Clean scalar values here, not the [[wikilink]] above — Bedrock KB
    # metadata filtering wants a real filterable value, not wikilink syntax.
    metadata = {
        "note_id": note_id,
        "type": "literature-note",
        "authored_by": "model",
        "source_url": source_url,
        "source_title": source_title,
        "date": today,
        "tags": ", ".join(tags),
    }

    s3.put_object(Bucket=S3_BUCKET, Key=s3_key, Body=md_content.encode(), ContentType="text/markdown")
    s3.put_object(Bucket=S3_BUCKET, Key=f"{s3_key}.metadata.json", Body=json.dumps(metadata).encode(), ContentType="application/json")

    item = {
        "note_id": note_id,
        "type": "literature-note",
        "authored_by": "model",
        "title": title,
        "s3_key": s3_key,
        "date": today,
        "tags": tags,
        "created_at": datetime.datetime.utcnow().isoformat(),
        "gsi_pk": "item",  # constant partition key for recent-index — see app-stack.ts
    }
    # Omitted (not empty-string) when there's no source, so sourceless notes
    # simply don't appear in source-index — a sparse GSI, not a meaningless bucket.
    if source_id:
        item["source_id"] = source_id
    ddb.Table(ITEMS_TABLE).put_item(Item=item)

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

    # Real duplicate caught live: independent classification passes (a fresh
    # ingest's own call, a later Stage 2 reclassification) can rediscover the
    # same genuine connection and each write it as a brand-new edge, since
    # nothing checked whether one already existed. Skip rather than update on
    # a match — an update would silently clobber a confidence the user may
    # have already corrected by hand, undermining the whole point of edges
    # being user-editable.
    existing = ddb.Table(EDGES_TABLE).query(
        KeyConditionExpression=Key("from_id").eq(from_id),
        FilterExpression=Attr("to_id").eq(to_id) & Attr("type").eq(edge_type),
    ).get("Items", [])
    if existing:
        log.info(f"Edge already exists, skipping duplicate: {from_id} -{edge_type}-> {to_id}")
        return {"written": False, "reason": "duplicate edge already exists", "edge_id": existing[0]["edge_id"]}

    edge_id = _write_edge_record(from_id, to_id, edge_type, confidence, reason)
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
        "gsi_pk": "item",  # constant partition key for recent-index — see app-stack.ts
    })

    # GROUNDED_IN edges are deterministic cluster membership, not a scored
    # classification — write them directly (confidence 1.0) rather than through
    # the write_edge tool's threshold gate, which doesn't apply here. Skip the
    # per-call frontmatter regen and do it once after the loop instead.
    for member_id in grounded_in:
        _write_edge_record(note_id, member_id, "GROUNDED_IN", 1.0, reason="summary card grounding", regenerate=False)
    if grounded_in:
        _regenerate_note_links(note_id)

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
    new_members = set(add_note_ids) - current
    removed_members = set(remove_note_ids) & current
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

    for member_id in new_members:
        _write_edge_record(summary_note_id, member_id, "GROUNDED_IN", 1.0, reason="summary card grounding", regenerate=False)
    for member_id in removed_members:
        _delete_edges_to(summary_note_id, member_id, "GROUNDED_IN")

    # Regenerates frontmatter (title/tags/date preserved) from the edges just
    # written/deleted above, reading the current S3 copy rather than DynamoDB —
    # preserves any hand-edited title/tags/date instead of silently reverting
    # them the next time an unrelated update_summary call touches this note.
    _regenerate_note_links(summary_note_id)
    log.info(f"Updated summary card cluster: {item['s3_key']}")
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
def read_pdf(pdf_key: str) -> dict:
    """
    Read an uploaded PDF and return it as a document for you to read natively
    (text, tables, layout) — no separate text-extraction step. Call this
    first when ingesting an uploaded PDF, before write_note; pass the same
    pdf_key to write_note's source_pdf_key param afterward so the citation
    resolves correctly.

    Args:
        pdf_key: S3 key of the uploaded PDF within the uploads bucket, e.g.
            "uploads/{upload_id}/{filename}.pdf"

    Returns:
        The PDF as a document content block for you to read directly.
    """
    filename = pdf_key.rsplit("/", 1)[-1]
    tmp_path = f"/tmp/{uuid.uuid4().hex}.pdf"
    try:
        s3.download_file(UPLOADS_BUCKET, pdf_key, tmp_path)
        with open(tmp_path, "rb") as f:
            content = f.read()
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    base_name = _sanitize_document_name(os.path.splitext(filename)[0])
    neutral_name = f"{base_name}-{uuid.uuid4().hex[:8]}"
    return {
        "status": "success",
        "content": [{"document": {"name": neutral_name, "format": "pdf", "source": {"bytes": content}}}],
    }


@tool
def fetch_url(url: str) -> dict:
    """
    Fetch a URL for ingestion. Branches by content type: a direct PDF link is
    handed to you natively to read (like read_pdf, no separate extraction);
    YouTube URLs (youtube.com/watch, youtu.be, /shorts/, /embed/, /live/)
    return the video's transcript plus title/channel; anything else returns
    extracted readable text plus title/author where the page provides them.

    Pass title/author straight to write_note's source_title/source_author —
    don't parse them back out of the text yourself.

    Args:
        url: The URL to fetch

    Returns:
        For a PDF, a document content block for you to read directly. For
        everything else, a dict with title, author (both "" if unknown), and
        text (page content or YouTube transcript, capped at 50k characters).
    """
    video_id = _youtube_video_id(url)
    if video_id:
        return _fetch_youtube(video_id, url)

    with httpx.Client(follow_redirects=True, timeout=30) as client:
        response = client.get(url, headers={"User-Agent": "SlipBox/1.0"})
        response.raise_for_status()

        content_type = response.headers.get("content-type", "")
        if "application/pdf" in content_type or url.lower().split("?")[0].endswith(".pdf"):
            name = _sanitize_document_name(url.rsplit("/", 1)[-1].removesuffix(".pdf"))
            neutral_name = f"{name}-{uuid.uuid4().hex[:8]}"
            return {
                "status": "success",
                "content": [{"document": {"name": neutral_name, "format": "pdf", "source": {"bytes": response.content}}}],
            }

        title, author = _extract_html_metadata(response.text)
        text = re.sub(r'<[^>]+>', ' ', response.text)
        text = re.sub(r'\s+', ' ', text).strip()
        return {"title": title, "author": author, "text": text[:FETCH_URL_MAX_CHARS]}


# ============================================================================
# INTERNAL HELPERS
# ============================================================================


def _slugify(title: str) -> str:
    slug = re.sub(r'[^\w\s-]', '', title.lower())
    slug = re.sub(r'[\s_-]+', '-', slug)
    return slug.strip('-')[:60]


# Query-string params that vary per share/click but don't change what's being
# cited — stripped so the same source shared twice (e.g. a YouTube link with
# a different ?si= tracking value each time, a real case hit this session)
# dedupes to one Source record instead of a fresh one per share.
_TRACKING_PARAMS = {"si", "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content", "feature", "fbclid", "gclid", "t"}


def _normalize_source_key(url: str, title: str = "") -> str:
    """
    Canonical dedup key for a source URL. YouTube collapses to just the video
    ID — any two shares of "the same video" only ever differ in tracking or
    timestamp query params, never in a way that changes identity. Everything
    else gets a general normalization: lowercase host, drop tracking params,
    sort what's left, strip trailing slash and fragment.

    Amazon/Kindle is a real, separate case: Kindle's own share action mints a
    fresh a.co short link (and read.amazon.com deep link) per *highlight*,
    even for the same book — there's no stable per-book URL to normalize
    against the way YouTube has a video ID. Dedupes by title instead,
    whenever a real one was given (not the URL-fallback case) — two
    citations sharing the exact book title are treated as the same source.
    A real, if rare, false-merge risk (two different books sharing a title)
    accepted as a personal-scale tradeoff, rather than one book fragmenting
    into a fresh Source record per quote shared — a real case hit live.
    """
    video_id = _youtube_video_id(url)
    if video_id:
        return f"youtube:{video_id}"

    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    if title and (host == "a.co" or host.endswith(".amazon.com")):
        return f"amazon-title:{title.strip().lower()}"

    kept = sorted((k, v) for k, v in urllib.parse.parse_qsl(parsed.query) if k.lower() not in _TRACKING_PARAMS)
    path = parsed.path.rstrip("/") or "/"
    return urllib.parse.urlunparse((parsed.scheme.lower(), parsed.netloc.lower(), path, "", urllib.parse.urlencode(kept), ""))


def _resolve_source(source_url: str = "", source_pdf_key: str = "", source_title: str = "", source_author: str = "") -> str | None:
    """
    Look up or create the Source record a note cites, deduped by
    _normalize_source_key for URL sources or a content hash for PDF sources.
    PDF dedup can't key off the S3 key itself — every upload gets a fresh
    upload_id/key, so two uploads of the byte-identical file would never
    match. Instead it uses the object's ETag, which for a single (non-
    multipart) PUT upload — the only kind this project's presigned-upload
    flow does — IS the MD5 of the content, so this is a real content hash
    without a full re-download just to compute one. Returns None if no
    source was given at all (matches write_note's existing optional-source
    behavior). source_pdf_key takes priority if both are somehow given.
    """
    if source_pdf_key:
        etag = s3.head_object(Bucket=UPLOADS_BUCKET, Key=source_pdf_key)["ETag"].strip('"')
        source_key = f"pdf:{etag}"
        title = source_title or source_pdf_key.rsplit("/", 1)[-1]
        source_type = "pdf"
        url = ""
    elif source_url:
        source_key = _normalize_source_key(source_url, source_title)
        title = source_title or source_url
        source_type = "youtube" if _youtube_video_id(source_url) else "web"
        url = source_url
    else:
        return None

    existing = ddb.Table(SOURCES_TABLE).query(
        IndexName="source-key-index",
        KeyConditionExpression=Key("source_key").eq(source_key),
        Limit=1,
    ).get("Items", [])
    if existing:
        return existing[0]["source_id"]

    source_id = f"{_slugify(title)}-{uuid.uuid4().hex[:8]}"
    now = datetime.datetime.utcnow().isoformat()
    ddb.Table(SOURCES_TABLE).put_item(Item={
        "source_id": source_id,
        "source_key": source_key,
        "type": source_type,
        "title": title,
        "author": source_author,
        "url": url,
        "retrieved_at": now,
        "created_at": now,
    })
    return source_id


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


def _write_edge_record(from_id: str, to_id: str, edge_type: str, confidence: float, reason: str = "", regenerate: bool = True) -> str:
    """
    Unconditional edge write — no threshold/validation, used by write_edge (after
    it validates) and by write_summary/update_summary for deterministic GROUNDED_IN
    membership edges, which aren't a confidence-scored classification.
    """
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
    if regenerate:
        _regenerate_note_links(from_id)
    log.info(f"Written edge: {from_id} -{edge_type}-> {to_id} ({confidence})")
    return edge_id


def _delete_edges_to(from_id: str, to_id: str, edge_type: str) -> None:
    """Delete every edge from_id -edge_type-> to_id (normally just one)."""
    edges = ddb.Table(EDGES_TABLE).query(KeyConditionExpression=Key("from_id").eq(from_id)).get("Items", [])
    for edge in edges:
        if edge["to_id"] == to_id and edge["type"] == edge_type:
            ddb.Table(EDGES_TABLE).delete_item(Key={"from_id": from_id, "edge_id": edge["edge_id"]})


def _youtube_video_id(url: str) -> str | None:
    """Extract the video ID from watch/shorts/embed/live/youtu.be URL shapes."""
    parsed = urllib.parse.urlparse(url)
    host = parsed.netloc.lower()
    for prefix in ("www.", "m.", "music."):
        host = host.removeprefix(prefix)
    if host == "youtu.be":
        return parsed.path.lstrip("/").split("/")[0] or None
    if host == "youtube.com":
        if parsed.path == "/watch":
            return urllib.parse.parse_qs(parsed.query).get("v", [None])[0]
        for prefix in ("/shorts/", "/embed/", "/live/"):
            if parsed.path.startswith(prefix):
                return parsed.path[len(prefix):].split("/")[0] or None
    return None


def _fetch_youtube(video_id: str, original_url: str) -> dict:
    """
    Transcript (via youtube-transcript-api's timedtext endpoint, no API key
    needed) plus title/channel (via YouTube's oEmbed endpoint) — replaces
    fetch_url's default HTML-strip, which returns nothing usable against a
    JS-rendered watch page. Returns the same {title, author, text} shape
    fetch_url does for every other content type — no more prepending a
    "Title: X\\nChannel: Y" header into the text and hoping the caller
    notices it.
    """
    title, channel = "", ""
    try:
        with httpx.Client(timeout=10) as client:
            resp = client.get(
                "https://www.youtube.com/oembed",
                params={"url": original_url, "format": "json"},
            )
            if resp.status_code == 200:
                data = resp.json()
                title, channel = data.get("title") or "", data.get("author_name") or ""
    except httpx.HTTPError:
        pass

    try:
        transcript = YouTubeTranscriptApi().fetch(video_id)
        text = " ".join(snippet.text for snippet in transcript)
    except CouldNotRetrieveTranscript as e:
        if not title:
            raise
        log.info(f"No YouTube transcript available for {video_id} ({type(e).__name__}: {e}), falling back to title/channel only")
        text = ("No transcript is available for this video — write the note from "
                "the title/channel alone if that's enough, or tell the user none was found.")
        return {"title": title, "author": channel, "text": text[:FETCH_URL_MAX_CHARS]}

    return {"title": title, "author": channel, "text": text[:FETCH_URL_MAX_CHARS]}


_DISALLOWED_DOCUMENT_NAME_CHARS = re.compile(r'[^a-zA-Z0-9\s\-()\[\]]')


def _sanitize_document_name(name: str) -> str:
    """Bedrock's document content block only allows alphanumeric, whitespace,
    hyphens, parentheses, and square brackets in a document name, with no
    consecutive whitespace — real bug caught live: os.path.splitext only
    strips the *last* extension, so periods/underscores from a filename or
    URL slug (e.g. arXiv's "1706.03762", which has no .pdf suffix to strip
    at all) reached ConverseStream unsanitized and crashed the whole turn
    with a ValidationException, not just a tool-level error."""
    cleaned = _DISALLOWED_DOCUMENT_NAME_CHARS.sub(" ", name)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned or "document"


_TITLE_RE = re.compile(r'<title[^>]*>(.*?)</title>', re.IGNORECASE | re.DOTALL)


_AUTHOR_META_PATTERNS = (
    re.compile(r'<meta[^>]+name=["\']author["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE),
    re.compile(r'<meta[^>]+property=["\']article:author["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE),
)


def _extract_html_metadata(html: str) -> tuple[str, str]:
    """Best-effort <title> and author extraction from an HTML page — not a
    real HTML parser, just enough to stop citations being just a bare URL."""
    title_match = _TITLE_RE.search(html)
    title = re.sub(r'\s+', ' ', title_match.group(1)).strip() if title_match else ""

    author = ""
    for pattern in _AUTHOR_META_PATTERNS:
        match = pattern.search(html)
        if match:
            author = match.group(1).strip()
            break
    return title, author
