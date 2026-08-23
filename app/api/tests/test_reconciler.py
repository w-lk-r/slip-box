"""
Tests for reconciler.py — review-todo.md #9's Stage 1: a deterministic S3 ->
DynamoDB sync with no agent/model involvement. moto-mocked (S3 + DynamoDB),
per CLAUDE.md's guidance for a new DynamoDB/S3 read-write shape.
"""
import datetime
import json

import boto3
import pytest
from boto3.dynamodb.conditions import Key
from moto import mock_aws

import reconciler
from clients import S3_BUCKET, edges_table, items_table

REGION = "ap-southeast-2"


def _create_bucket():
    boto3.client("s3", region_name=REGION).create_bucket(
        Bucket=S3_BUCKET, CreateBucketConfiguration={"LocationConstraint": REGION}
    )


def _create_items_table():
    ddb = boto3.resource("dynamodb", region_name=REGION)
    ddb.create_table(
        TableName="test-items",
        KeySchema=[{"AttributeName": "note_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "note_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


def _create_edges_table():
    ddb = boto3.resource("dynamodb", region_name=REGION)
    ddb.create_table(
        TableName="test-edges",
        KeySchema=[
            {"AttributeName": "from_id", "KeyType": "HASH"},
            {"AttributeName": "edge_id", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "from_id", "AttributeType": "S"},
            {"AttributeName": "edge_id", "AttributeType": "S"},
            {"AttributeName": "to_id", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "to_id-index",
                "KeySchema": [{"AttributeName": "to_id", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )


def _note_md(note_id: str = "", title: str = "A Note", tags=None) -> str:
    tag_lines = "\n".join(f"  - {t}" for t in (tags or [])) if tags else "  []"
    note_id_line = f"note_id: {note_id}\n" if note_id else ""
    return f"""---
title: {title}
{note_id_line}type: literature-note
authored_by: model
date: 2026-08-22
tags:
{tag_lines}
supports: []
contradicts: []
extends: []
related_to: []
---

Body text for {title}.
"""


@pytest.fixture
def env():
    with mock_aws():
        _create_bucket()
        _create_items_table()
        _create_edges_table()
        yield


class TestHandleUpsert:
    def test_new_note_with_existing_note_id_is_written(self, env):
        reconciler.s3.put_object(Bucket=S3_BUCKET, Key="my-note-abc123.md", Body=_note_md("my-note-abc123").encode())
        reconciler._handle_upsert(S3_BUCKET, "my-note-abc123.md")

        item = items_table.get_item(Key={"note_id": "my-note-abc123"})["Item"]
        assert item["title"] == "A Note"
        assert item["s3_key"] == "my-note-abc123.md"
        assert item["gsi_pk"] == "item"

    def test_reupsert_preserves_attributes_it_doesnt_manage(self, env):
        # Real bug caught live: regenerate_note_links (called from
        # _handle_delete and from the agent's own write_edge/update_summary)
        # rewrites the note's own file to S3, which re-triggers this same
        # handler on the same key. A full put_item there silently wiped
        # grounded_in (a summary card's cluster membership) on that
        # redundant re-trigger, since it's a field Stage 1 never sets itself.
        reconciler.s3.put_object(Bucket=S3_BUCKET, Key="card-abc123.md", Body=_note_md("card-abc123").encode())
        reconciler._handle_upsert(S3_BUCKET, "card-abc123.md")
        items_table.update_item(
            Key={"note_id": "card-abc123"},
            UpdateExpression="SET grounded_in = :g",
            ExpressionAttributeValues={":g": ["some-member-note"]},
        )

        reconciler._handle_upsert(S3_BUCKET, "card-abc123.md")  # simulates the re-trigger

        item = items_table.get_item(Key={"note_id": "card-abc123"})["Item"]
        assert item.get("grounded_in") == ["some-member-note"]

    def test_reupsert_preserves_created_at(self, env, monkeypatch):
        # Changing the title changes the body text too (_note_md embeds it),
        # which now triggers a Stage 2 call — mock it out, not the focus here.
        monkeypatch.setattr(reconciler, "lambda_client", type("_", (), {"invoke": lambda self, **kw: None})())
        reconciler.s3.put_object(Bucket=S3_BUCKET, Key="my-note-abc123.md", Body=_note_md("my-note-abc123").encode())
        reconciler._handle_upsert(S3_BUCKET, "my-note-abc123.md")
        first_created_at = items_table.get_item(Key={"note_id": "my-note-abc123"})["Item"]["created_at"]

        reconciler.s3.put_object(
            Bucket=S3_BUCKET, Key="my-note-abc123.md", Body=_note_md("my-note-abc123", title="Edited Title").encode()
        )
        reconciler._handle_upsert(S3_BUCKET, "my-note-abc123.md")

        item = items_table.get_item(Key={"note_id": "my-note-abc123"})["Item"]
        assert item["title"] == "Edited Title"
        assert item["created_at"] == first_created_at

    def test_rename_updates_same_row_not_a_duplicate(self, env):
        reconciler.s3.put_object(Bucket=S3_BUCKET, Key="old-name.md", Body=_note_md("my-note-abc123").encode())
        reconciler._handle_upsert(S3_BUCKET, "old-name.md")

        reconciler.s3.put_object(Bucket=S3_BUCKET, Key="new-name.md", Body=_note_md("my-note-abc123").encode())
        reconciler._handle_upsert(S3_BUCKET, "new-name.md")

        item = items_table.get_item(Key={"note_id": "my-note-abc123"})["Item"]
        assert item["s3_key"] == "new-name.md"
        resp = items_table.scan()
        assert len(resp["Items"]) == 1

    def test_missing_note_id_backfills_and_rewrites_s3(self, env):
        raw = "---\ntitle: Untitled Hand Note\n---\n\nSome body text.\n"
        reconciler.s3.put_object(Bucket=S3_BUCKET, Key="untitled-hand-note.md", Body=raw.encode())

        reconciler._handle_upsert(S3_BUCKET, "untitled-hand-note.md")

        resp = items_table.scan()["Items"]
        assert len(resp) == 1
        item = resp[0]
        assert item["note_id"]
        assert item["type"] == "literature-note"
        assert item["authored_by"] == "user"

        rewritten = reconciler.s3.get_object(Bucket=S3_BUCKET, Key="untitled-hand-note.md")["Body"].read().decode()
        assert item["note_id"] in rewritten
        sidecar = reconciler.s3.get_object(Bucket=S3_BUCKET, Key="untitled-hand-note.md.metadata.json")
        assert sidecar["Body"].read()

    def test_unparseable_content_skips_without_raising(self, env):
        reconciler.s3.put_object(Bucket=S3_BUCKET, Key="broken.md", Body=b"\xff\xfe not valid text at all")
        reconciler._handle_upsert(S3_BUCKET, "broken.md")  # must not raise
        assert items_table.scan()["Items"] == []


class TestHandleDelete:
    def _seed_note(self, note_id: str, key: str, extra: dict | None = None):
        item = {"note_id": note_id, "type": "literature-note", "title": note_id, "s3_key": key,
                "authored_by": "model", "date": "2026-08-22", "tags": [], "created_at": "2026-08-22T00:00:00",
                "gsi_pk": "item"}
        item.update(extra or {})
        items_table.put_item(Item=item)
        reconciler.s3.put_object(Bucket=S3_BUCKET, Key=key, Body=_note_md(note_id).encode())

    def test_full_three_direction_cleanup(self, env):
        self._seed_note("note-a", "note-a.md")
        self._seed_note("note-b", "note-b.md")
        edges_table.put_item(Item={"from_id": "note-a", "edge_id": "e1", "to_id": "note-b", "type": "RELATED_TO", "confidence": 1})
        edges_table.put_item(Item={"from_id": "note-b", "edge_id": "e2", "to_id": "note-a", "type": "RELATED_TO", "confidence": 1})

        reconciler._handle_delete(S3_BUCKET, "note-a.md")

        assert items_table.get_item(Key={"note_id": "note-a"}).get("Item") is None
        assert edges_table.query(KeyConditionExpression=Key("from_id").eq("note-a"))["Items"] == []
        # note-b's outgoing edge to note-a (e2) must be gone (it was incoming to note-a)
        assert edges_table.query(KeyConditionExpression=Key("from_id").eq("note-b"))["Items"] == []
        # note-b's frontmatter must no longer reference note-a
        body = reconciler.s3.get_object(Bucket=S3_BUCKET, Key="note-b.md")["Body"].read().decode()
        assert "note-a" not in body

    def test_removes_from_summary_card_grounded_in(self, env):
        self._seed_note("member-note", "member-note.md")
        self._seed_note("card-1", "card-1.md", extra={"type": "summary-card", "grounded_in": ["member-note"]})
        edges_table.put_item(Item={"from_id": "card-1", "edge_id": "g1", "to_id": "member-note", "type": "GROUNDED_IN", "confidence": 1})

        reconciler._handle_delete(S3_BUCKET, "member-note.md")

        card = items_table.get_item(Key={"note_id": "card-1"})["Item"]
        assert card["grounded_in"] == []

    def test_no_matching_item_is_a_noop(self, env):
        reconciler._handle_delete(S3_BUCKET, "never-existed.md")  # must not raise

    def test_neighbor_regeneration_failure_does_not_block_own_deletion(self, env):
        # Real bug caught live: bulk-deleting several connected notes at once
        # (e.g. aws s3 sync --delete) can hit a neighbor whose own S3 file is
        # *also* already gone by the time regenerate_note_links fetches it.
        # That used to raise unhandled and abort this whole handler before it
        # reached items_table.delete_item — leaving note-a's row orphaned in
        # DynamoDB even though its S3 file was gone. The neighbor's row still
        # exists in items_table (so it's a genuine "affected_from_id"), but
        # its S3 object does not.
        self._seed_note("note-a", "note-a.md")
        self._seed_note("note-b", "note-b.md")
        edges_table.put_item(Item={"from_id": "note-b", "edge_id": "e1", "to_id": "note-a", "type": "RELATED_TO", "confidence": 1})
        reconciler.s3.delete_object(Bucket=S3_BUCKET, Key="note-b.md")  # note-b's file already gone

        reconciler._handle_delete(S3_BUCKET, "note-a.md")  # must not raise

        assert items_table.get_item(Key={"note_id": "note-a"}).get("Item") is None
        assert edges_table.query(KeyConditionExpression=Key("from_id").eq("note-b"))["Items"] == []


class TestStage2Trigger:
    """
    Stage 2 (review-todo.md #9) — an optional agent-triggered reclassification
    pass, layered on top of Stage 1's own unconditional guarantee. These tests
    cover the *decision* logic only (should reconciler.py fire a trigger, with
    what prompt) — the agent's own response to that prompt is a live-
    verification-only thing, per CLAUDE.md's carve-out for LLM judgment.
    reconciler.lambda_client.invoke is monkeypatched directly, matching
    test_worker.py's existing pattern for worker.agentcore.invoke_agent_runtime.
    """

    def test_body_change_on_existing_note_triggers(self, env, monkeypatch):
        calls = []
        monkeypatch.setattr(reconciler, "lambda_client", type("_", (), {"invoke": lambda self, **kw: calls.append(kw)})())

        reconciler.s3.put_object(Bucket=S3_BUCKET, Key="edit-note.md", Body=_note_md("edit-note", title="Edit Note").encode())
        reconciler._handle_upsert(S3_BUCKET, "edit-note.md")
        assert calls == []  # brand-new note — must not fire

        reconciler.s3.put_object(Bucket=S3_BUCKET, Key="edit-note.md", Body=_note_md("edit-note", title="Edit Note").encode().replace(b"Body text", b"Changed body text"))
        reconciler._handle_upsert(S3_BUCKET, "edit-note.md")

        assert len(calls) == 1
        payload = json.loads(calls[0]["Payload"])
        assert "do NOT call write_note" in payload["prompt"]
        assert "Edit Note" in payload["prompt"]
        assert calls[0]["FunctionName"] == "test-worker"
        assert calls[0]["InvocationType"] == "Event"

    def test_frontmatter_only_change_does_not_trigger(self, env, monkeypatch):
        calls = []
        monkeypatch.setattr(reconciler, "lambda_client", type("_", (), {"invoke": lambda self, **kw: calls.append(kw)})())

        reconciler.s3.put_object(Bucket=S3_BUCKET, Key="tags-only.md", Body=_note_md("tags-only").encode())
        reconciler._handle_upsert(S3_BUCKET, "tags-only.md")

        reconciler.s3.put_object(Bucket=S3_BUCKET, Key="tags-only.md", Body=_note_md("tags-only", tags=["new-tag"]).encode())
        reconciler._handle_upsert(S3_BUCKET, "tags-only.md")

        assert calls == []

    def test_delete_with_two_neighbors_triggers(self, env, monkeypatch):
        calls = []
        monkeypatch.setattr(reconciler, "lambda_client", type("_", (), {"invoke": lambda self, **kw: calls.append(kw)})())

        for nid, title in [("bridge", "Bridge Note"), ("left", "Left Note"), ("right", "Right Note")]:
            reconciler.s3.put_object(Bucket=S3_BUCKET, Key=f"{nid}.md", Body=_note_md(nid, title=title).encode())
            reconciler._handle_upsert(S3_BUCKET, f"{nid}.md")
        edges_table.put_item(Item={"from_id": "left", "edge_id": "e1", "to_id": "bridge", "type": "RELATED_TO", "confidence": 1})
        edges_table.put_item(Item={"from_id": "bridge", "edge_id": "e2", "to_id": "right", "type": "RELATED_TO", "confidence": 1})

        reconciler._handle_delete(S3_BUCKET, "bridge.md")

        assert len(calls) == 1
        payload = json.loads(calls[0]["Payload"])
        assert "Left Note" in payload["prompt"]
        assert "Right Note" in payload["prompt"]

    def test_delete_with_one_neighbor_does_not_trigger(self, env, monkeypatch):
        calls = []
        monkeypatch.setattr(reconciler, "lambda_client", type("_", (), {"invoke": lambda self, **kw: calls.append(kw)})())

        for nid in ("solo-a", "solo-b"):
            reconciler.s3.put_object(Bucket=S3_BUCKET, Key=f"{nid}.md", Body=_note_md(nid).encode())
            reconciler._handle_upsert(S3_BUCKET, f"{nid}.md")
        edges_table.put_item(Item={"from_id": "solo-b", "edge_id": "e1", "to_id": "solo-a", "type": "RELATED_TO", "confidence": 1})

        reconciler._handle_delete(S3_BUCKET, "solo-a.md")

        assert calls == []

    def test_missing_worker_function_name_skips_without_raising(self, env, monkeypatch):
        monkeypatch.setattr(reconciler, "WORKER_FUNCTION_NAME", "")
        calls = []
        monkeypatch.setattr(reconciler, "lambda_client", type("_", (), {"invoke": lambda self, **kw: calls.append(kw)})())

        reconciler.s3.put_object(Bucket=S3_BUCKET, Key="no-worker.md", Body=_note_md("no-worker").encode())
        reconciler._handle_upsert(S3_BUCKET, "no-worker.md")
        reconciler.s3.put_object(Bucket=S3_BUCKET, Key="no-worker.md", Body=_note_md("no-worker").encode().replace(b"Body text", b"Changed"))
        reconciler._handle_upsert(S3_BUCKET, "no-worker.md")  # must not raise

        assert calls == []


class TestHandler:
    def _event(self, event_name: str, key: str):
        return {"Records": [{"eventName": event_name, "s3": {"bucket": {"name": S3_BUCKET}, "object": {"key": key}}}]}

    def test_dispatches_object_created_to_upsert(self, env):
        reconciler.s3.put_object(Bucket=S3_BUCKET, Key="dispatch-test.md", Body=_note_md("dispatch-test").encode())
        reconciler.handler(self._event("ObjectCreated:Put", "dispatch-test.md"), None)
        assert items_table.get_item(Key={"note_id": "dispatch-test"}).get("Item") is not None

    def test_dispatches_object_removed_to_delete(self, env):
        self._seed = None
        items_table.put_item(Item={"note_id": "to-remove", "type": "literature-note", "title": "x", "s3_key": "to-remove.md",
                                    "authored_by": "model", "date": "2026-08-22", "tags": [], "created_at": "now", "gsi_pk": "item"})
        reconciler.handler(self._event("ObjectRemoved:Delete", "to-remove.md"), None)
        assert items_table.get_item(Key={"note_id": "to-remove"}).get("Item") is None

    def test_url_decodes_spaces_in_key(self, env):
        reconciler.s3.put_object(Bucket=S3_BUCKET, Key="a note with spaces.md", Body=_note_md("spaced-note").encode())
        reconciler.handler(self._event("ObjectCreated:Put", "a+note+with+spaces.md"), None)
        assert items_table.get_item(Key={"note_id": "spaced-note"}).get("Item") is not None
