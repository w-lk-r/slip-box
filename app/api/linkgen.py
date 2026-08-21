"""
Frontmatter link regeneration — trimmed copy of the same-named functions in
app/MyAgent/tools/notes.py. Duplicated rather than shared because this package
and MyAgent are two separate deployable units (Lambda zip vs. AgentCore Runtime
CodeZip) with no shared-library convention in this repo. Keep in sync manually;
if a third consumer of this logic shows up (e.g. review-todo #9's S3
reconciliation Lambda), that's the point to extract a real shared package.
"""
import logging

from boto3.dynamodb.conditions import Key

from clients import S3_BUCKET, edges_table, items_table, s3

log = logging.getLogger(__name__)

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
