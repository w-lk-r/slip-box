"""
FastAPI TestClient tests for items.py's GET /items, GET /sources,
GET /items/review-queue, and POST/DELETE /items/{note_id}/review — per
CLAUDE.md's guidance for a new DynamoDB read/write shape and a FastAPI
request/response shape change. moto-mocked; `from main import app` happens
inside mock_aws() per the pattern test_uploads.py/test_ingest_status.py use
(see test_ingest_prompt.py's docstring for why an unmocked module-level
import of the shared clients.py module breaks every other test file in the
same pytest session).
"""
from decimal import Decimal

import boto3
import pytest
from moto import mock_aws

REGION = "ap-southeast-2"


def _create_tables():
    ddb = boto3.resource("dynamodb", region_name=REGION)
    ddb.create_table(
        TableName="test-items",
        KeySchema=[{"AttributeName": "note_id", "KeyType": "HASH"}],
        AttributeDefinitions=[
            {"AttributeName": "note_id", "AttributeType": "S"},
            {"AttributeName": "gsi_pk", "AttributeType": "S"},
            {"AttributeName": "created_at", "AttributeType": "S"},
            {"AttributeName": "source_id", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "recent-index",
                "KeySchema": [
                    {"AttributeName": "gsi_pk", "KeyType": "HASH"},
                    {"AttributeName": "created_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            },
            {
                "IndexName": "source-index",
                "KeySchema": [{"AttributeName": "source_id", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            },
        ],
        BillingMode="PAY_PER_REQUEST",
    )
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
    ddb.create_table(
        TableName="test-sources",
        KeySchema=[{"AttributeName": "source_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "source_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    boto3.client("s3", region_name=REGION).create_bucket(
        Bucket="test-bucket", CreateBucketConfiguration={"LocationConstraint": REGION}
    )
    return ddb


def _note_md(note_id: str, title: str = "A Note") -> str:
    return f"""---
title: {title}
note_id: {note_id}
type: literature-note
authored_by: model
date: 2026-08-23
tags: []
supports: []
contradicts: []
extends: []
related_to: []
---

Body text for {title}.
"""


def _item(note_id, title="A Note", created_at="2026-08-23T00:00:00", extra=None):
    row = {
        "note_id": note_id, "type": "literature-note", "title": title,
        "s3_key": f"{note_id}.md", "authored_by": "model", "date": "2026-08-23",
        "tags": [], "created_at": created_at, "gsi_pk": "item",
    }
    row.update(extra or {})
    return row


@pytest.fixture
def client():
    with mock_aws():
        ddb = _create_tables()
        from main import app
        from fastapi.testclient import TestClient
        yield (
            TestClient(app),
            ddb.Table("test-items"),
            ddb.Table("test-edges"),
            ddb.Table("test-sources"),
        )


class TestListItems:
    def test_filters_by_source_id_via_source_index(self, client):
        test_client, items_table, _edges, _sources = client
        items_table.put_item(Item=_item("note-a", extra={"source_id": "src-1"}))
        items_table.put_item(Item=_item("note-b", extra={"source_id": "src-2"}))

        resp = test_client.get("/items", params={"source_id": "src-1"})

        assert resp.status_code == 200
        note_ids = [i["note_id"] for i in resp.json()["items"]]
        assert note_ids == ["note-a"]

    def test_no_source_id_uses_recent_index(self, client):
        test_client, items_table, _edges, _sources = client
        items_table.put_item(Item=_item("note-a", created_at="2026-08-22T00:00:00"))
        items_table.put_item(Item=_item("note-b", created_at="2026-08-23T00:00:00"))

        resp = test_client.get("/items")

        note_ids = [i["note_id"] for i in resp.json()["items"]]
        assert note_ids == ["note-b", "note-a"]  # newest first


class TestListSources:
    def test_returns_all_sources(self, client):
        test_client, _items, _edges, sources_table = client
        sources_table.put_item(Item={"source_id": "src-1", "title": "A Source", "type": "web"})

        resp = test_client.get("/sources")

        assert resp.status_code == 200
        assert resp.json()["sources"] == [{"source_id": "src-1", "title": "A Source", "type": "web"}]


class TestReviewQueue:
    def test_unreviewed_items_appear_reviewed_items_dont(self, client):
        test_client, items_table, _edges, _sources = client
        items_table.put_item(Item=_item("unreviewed"))
        items_table.put_item(Item=_item("reviewed", extra={"reviewed_at": "2026-08-22T00:00:00"}))

        resp = test_client.get("/items/review-queue")

        note_ids = [i["note_id"] for i in resp.json()["items"]]
        assert note_ids == ["unreviewed"]

    def test_attaches_outgoing_and_incoming_edges_with_titles(self, client):
        test_client, items_table, edges_table, _sources = client
        items_table.put_item(Item=_item("note-a", title="Note A"))
        items_table.put_item(Item=_item("note-b", title="Note B"))
        items_table.put_item(Item=_item("note-c", title="Note C"))
        edges_table.put_item(Item={"from_id": "note-a", "edge_id": "e1", "to_id": "note-b", "type": "RELATED_TO", "confidence": Decimal("0.8")})
        edges_table.put_item(Item={"from_id": "note-c", "edge_id": "e2", "to_id": "note-a", "type": "EXTENDS", "confidence": Decimal("0.9")})

        resp = test_client.get("/items/review-queue")

        by_id = {i["note_id"]: i for i in resp.json()["items"]}
        assert by_id["note-a"]["outgoing_edges"] == [
            {"edge_id": "e1", "to_id": "note-b", "to_title": "Note B", "to_index_keywords": [], "type": "RELATED_TO", "confidence": 0.8}
        ]
        assert by_id["note-a"]["incoming_edges"] == [
            {"edge_id": "e2", "from_id": "note-c", "from_title": "Note C", "from_index_keywords": [], "type": "EXTENDS", "confidence": 0.9}
        ]


class TestMarkReviewed:
    def test_sets_reviewed_at(self, client):
        test_client, items_table, _edges, _sources = client
        items_table.put_item(Item=_item("note-a"))

        resp = test_client.post("/items/note-a/review")

        assert resp.status_code == 200
        assert resp.json()["reviewed_at"]
        assert items_table.get_item(Key={"note_id": "note-a"})["Item"]["reviewed_at"]

    def test_404_for_missing_note(self, client):
        test_client, _items, _edges, _sources = client
        resp = test_client.post("/items/does-not-exist/review")
        assert resp.status_code == 404


class TestUnmarkReviewed:
    def test_removes_reviewed_at(self, client):
        test_client, items_table, _edges, _sources = client
        items_table.put_item(Item=_item("note-a", extra={"reviewed_at": "2026-08-22T00:00:00"}))

        resp = test_client.delete("/items/note-a/review")

        assert resp.status_code == 200
        assert "reviewed_at" not in items_table.get_item(Key={"note_id": "note-a"})["Item"]

    def test_404_for_missing_note(self, client):
        test_client, _items, _edges, _sources = client
        resp = test_client.delete("/items/does-not-exist/review")
        assert resp.status_code == 404


class TestGetItem:
    """outgoing_edges/incoming_edges — added for the Expo flip-through view
    (docs/frontend-ux-spec.md's Flipping section), reusing the same
    _edges_for_note helper get_review_queue already uses."""

    def test_includes_structured_outgoing_and_incoming_edges(self, client):
        test_client, items_table, edges_table, _sources = client
        from clients import s3

        items_table.put_item(Item=_item("note-a", title="Note A"))
        items_table.put_item(Item=_item("note-b", title="Note B"))
        items_table.put_item(Item=_item("note-c", title="Note C"))
        s3.put_object(Bucket="test-bucket", Key="note-a.md", Body=_note_md("note-a", "Note A").encode())
        edges_table.put_item(Item={"from_id": "note-a", "edge_id": "e1", "to_id": "note-b", "type": "RELATED_TO", "confidence": Decimal("0.8")})
        edges_table.put_item(Item={"from_id": "note-c", "edge_id": "e2", "to_id": "note-a", "type": "EXTENDS", "confidence": Decimal("0.9")})

        resp = test_client.get("/items/note-a")

        assert resp.status_code == 200
        body = resp.json()
        assert body["outgoing_edges"] == [
            {"edge_id": "e1", "to_id": "note-b", "to_title": "Note B", "to_index_keywords": [], "type": "RELATED_TO", "confidence": 0.8}
        ]
        assert body["incoming_edges"] == [
            {"edge_id": "e2", "from_id": "note-c", "from_title": "Note C", "from_index_keywords": [], "type": "EXTENDS", "confidence": 0.9}
        ]

    def test_empty_lists_when_no_edges(self, client):
        test_client, items_table, _edges, _sources = client
        from clients import s3

        items_table.put_item(Item=_item("lonely-note"))
        s3.put_object(Bucket="test-bucket", Key="lonely-note.md", Body=_note_md("lonely-note").encode())

        resp = test_client.get("/items/lonely-note")

        assert resp.json()["outgoing_edges"] == []
        assert resp.json()["incoming_edges"] == []

    def test_neighbor_index_keywords_surfaced_on_edges(self, client):
        """A neighbor that's itself a curated index entry gets flagged on the
        edge — this is the whole "sub index cards" feature (see
        docs/frontend-ux-spec.md's Index Cards section): discovered by
        walking edges from an entry note, not a separate lookup."""
        test_client, items_table, edges_table, _sources = client
        from clients import s3

        items_table.put_item(Item=_item("note-a", title="Note A"))
        items_table.put_item(Item=_item("note-b", title="Note B", extra={"index_keywords": ["sleep"]}))
        s3.put_object(Bucket="test-bucket", Key="note-a.md", Body=_note_md("note-a", "Note A").encode())
        edges_table.put_item(Item={"from_id": "note-a", "edge_id": "e1", "to_id": "note-b", "type": "RELATED_TO", "confidence": Decimal("0.8")})

        resp = test_client.get("/items/note-a")

        assert resp.json()["outgoing_edges"][0]["to_index_keywords"] == ["sleep"]


class TestDeleteItem:
    """DELETE /items/{note_id} deliberately only removes the S3 object(s) —
    reconciler.py's own _handle_delete (S3-event-triggered) does the actual
    DynamoDB cascade. This class's job is to lock that design decision in:
    a future change that adds a premature items_table.delete_item call here
    should fail test_row_is_not_deleted_here, not silently reintroduce the
    dangling-reference bug docs/schema-change-checklist.md warns about."""

    def test_404_for_missing_note(self, client):
        test_client, _items, _edges, _sources = client
        resp = test_client.delete("/items/does-not-exist")
        assert resp.status_code == 404

    def test_deletes_md_and_sidecar_from_s3(self, client):
        test_client, items_table, _edges, _sources = client
        from clients import s3

        items_table.put_item(Item=_item("note-a"))
        s3.put_object(Bucket="test-bucket", Key="note-a.md", Body=_note_md("note-a").encode())
        s3.put_object(Bucket="test-bucket", Key="note-a.md.metadata.json", Body=b"{}")

        resp = test_client.delete("/items/note-a")

        assert resp.status_code == 202
        assert resp.json() == {"note_id": "note-a", "status": "deleting"}
        existing_keys = {o["Key"] for o in s3.list_objects_v2(Bucket="test-bucket").get("Contents", [])}
        assert "note-a.md" not in existing_keys
        assert "note-a.md.metadata.json" not in existing_keys

    def test_row_is_not_deleted_here(self, client):
        test_client, items_table, _edges, _sources = client
        from clients import s3

        items_table.put_item(Item=_item("note-a"))
        s3.put_object(Bucket="test-bucket", Key="note-a.md", Body=_note_md("note-a").encode())

        test_client.delete("/items/note-a")

        assert items_table.get_item(Key={"note_id": "note-a"}).get("Item") is not None


class TestListIndex:
    def test_groups_by_keyword_sorted_alphabetically(self, client):
        test_client, items_table, _edges, _sources = client
        items_table.put_item(Item=_item("note-a", title="Note A", extra={"index_keywords": ["sleep", "health"]}))
        items_table.put_item(Item=_item("note-b", title="Note B", extra={"index_keywords": ["health"]}))
        items_table.put_item(Item=_item("note-c", title="Note C"))  # no index_keywords — sparse, excluded

        resp = test_client.get("/index")

        assert resp.status_code == 200
        entries = resp.json()["entries"]
        assert [e["keyword"] for e in entries] == ["health", "sleep"]
        health_note_ids = {n["note_id"] for n in next(e for e in entries if e["keyword"] == "health")["notes"]}
        assert health_note_ids == {"note-a", "note-b"}

    def test_empty_when_nothing_indexed(self, client):
        test_client, items_table, _edges, _sources = client
        items_table.put_item(Item=_item("note-a"))

        resp = test_client.get("/index")

        assert resp.json()["entries"] == []


class TestAddIndexKeyword:
    def test_adds_keyword_to_note(self, client):
        test_client, items_table, _edges, _sources = client
        items_table.put_item(Item=_item("note-a"))

        resp = test_client.post("/items/note-a/index-keywords", json={"keyword": "sleep"})

        assert resp.status_code == 200
        assert resp.json()["index_keywords"] == ["sleep"]

    def test_dedupes_existing_keyword(self, client):
        test_client, items_table, _edges, _sources = client
        items_table.put_item(Item=_item("note-a", extra={"index_keywords": ["sleep"]}))

        resp = test_client.post("/items/note-a/index-keywords", json={"keyword": "sleep"})

        assert resp.json()["index_keywords"] == ["sleep"]

    def test_404_for_missing_note(self, client):
        test_client, _items, _edges, _sources = client
        resp = test_client.post("/items/does-not-exist/index-keywords", json={"keyword": "sleep"})
        assert resp.status_code == 404


class TestRemoveIndexKeyword:
    def test_removes_one_of_several(self, client):
        test_client, items_table, _edges, _sources = client
        items_table.put_item(Item=_item("note-a", extra={"index_keywords": ["sleep", "health"]}))

        resp = test_client.delete("/items/note-a/index-keywords/sleep")

        assert resp.status_code == 200
        assert resp.json()["index_keywords"] == ["health"]

    def test_removing_last_keyword_clears_attribute_entirely(self, client):
        test_client, items_table, _edges, _sources = client
        items_table.put_item(Item=_item("note-a", extra={"index_keywords": ["sleep"]}))

        resp = test_client.delete("/items/note-a/index-keywords/sleep")

        assert resp.status_code == 200
        assert "index_keywords" not in items_table.get_item(Key={"note_id": "note-a"})["Item"]

    def test_404_for_missing_note(self, client):
        test_client, _items, _edges, _sources = client
        resp = test_client.delete("/items/does-not-exist/index-keywords/sleep")
        assert resp.status_code == 404
