"""
Backfill DynamoDB items table from existing S3 notes.
Idempotent — skips notes that already have a record.

Usage (from repo root):
    cd app/MyAgent && uv run python ../../scripts/backfill_items.py
"""

import os
import datetime
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "../app/MyAgent/.env"))

REGION = os.environ.get("AWS_REGION", os.environ.get("REGION", "ap-southeast-2"))
S3_BUCKET = os.environ["S3_BUCKET"]
ITEMS_TABLE = os.environ["ITEMS_TABLE"]

s3 = boto3.client("s3", region_name=REGION)
ddb = boto3.resource("dynamodb", region_name=REGION)
table = ddb.Table(ITEMS_TABLE)


def parse_frontmatter(content: str) -> dict:
    """Extract YAML frontmatter fields as a flat dict of strings/lists."""
    if not content.startswith("---"):
        return {}
    end = content.find("\n---\n", 4)
    if end == -1:
        return {}
    fm_text = content[4:end]
    result = {}
    for line in fm_text.splitlines():
        if ":" not in line or line.startswith(" "):
            continue
        key, _, val = line.partition(":")
        result[key.strip()] = val.strip()
    return result


def parse_tags(content: str, fm: dict) -> list[str]:
    """Parse tags whether inline list or multiline block."""
    raw = fm.get("tags", "")
    # Inline: [a, b, c]
    if raw.startswith("[") and raw.endswith("]"):
        return [t.strip() for t in raw[1:-1].split(",") if t.strip()]
    # Multiline block — scan lines after frontmatter open
    tags = []
    in_tags = False
    for line in content.splitlines():
        if line.strip() == "tags:":
            in_tags = True
            continue
        if in_tags:
            if line.startswith("  - "):
                tags.append(line.strip()[2:])
            elif line and not line.startswith(" "):
                break
    return tags


def already_exists(note_id: str) -> bool:
    try:
        result = table.get_item(Key={"note_id": note_id})
        return "Item" in result
    except ClientError:
        return False


def backfill():
    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=S3_BUCKET)

    written = 0
    skipped = 0

    for page in pages:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if not key.endswith(".md") or key.endswith(".metadata.json"):
                continue

            content = s3.get_object(Bucket=S3_BUCKET, Key=key)["Body"].read().decode()
            fm = parse_frontmatter(content)

            # Derive note_id from S3 key if not in frontmatter
            note_id = fm.get("note_id") or key.removesuffix(".md")

            if already_exists(note_id):
                print(f"  skip (exists): {key}")
                skipped += 1
                continue

            tags = parse_tags(content, fm)
            table.put_item(Item={
                "note_id": note_id,
                "type": fm.get("type", "literature-note"),
                "authored_by": fm.get("authored_by", "model"),
                "title": fm.get("title", note_id),
                "s3_key": key,
                "source_url": fm.get("source", ""),
                "date": fm.get("date", datetime.date.today().isoformat()),
                "tags": tags,
                "created_at": fm.get("date", datetime.date.today().isoformat()),
            })
            print(f"  written: {key}")
            written += 1

    print(f"\nDone — {written} written, {skipped} skipped.")


if __name__ == "__main__":
    print(f"Backfilling {ITEMS_TABLE} from s3://{S3_BUCKET}...\n")
    backfill()
