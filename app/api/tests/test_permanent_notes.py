"""
Tests for the PermanentNote direct write path — linkgen.py's
write_permanent_note/write_edge_record/trigger_kb_sync, and items.py's
POST /items/permanent and POST /items/{note_id}/find-connections. moto-mocked
(S3 + DynamoDB items/edges tables), per CLAUDE.md's guidance for a new
DynamoDB/S3 read-write shape. `from main import app` happens inside
mock_aws() per test_items.py's own docstring (an unmocked module-level import
of clients.py breaks every other test file in the same pytest session).

lambda_client.invoke and linkgen.trigger_kb_sync are monkeypatched rather than
moto-mocked, same technique test_summarize.py uses for the Lambda invoke:
moto's Lambda mock can't execute real handler code, and moto has no
bedrock-agent mock at all.
"""
import json
from unittest.mock import MagicMock

import boto3
import pytest
from boto3.dynamodb.conditions import Key
from moto import mock_aws

REGION = "ap-southeast-2"


def _create_tables():
    ddb = boto3.resource("dynamodb", region_name=REGION)
    ddb.create_table(
        TableName="test-items",
        KeySchema=[{"AttributeName": "note_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "note_id", "AttributeType": "S"}],
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
    boto3.client("s3", region_name=REGION).create_bucket(
        Bucket="test-bucket", CreateBucketConfiguration={"LocationConstraint": REGION}
    )
    return ddb


def _lit_note_md(note_id: str, title: str = "A Literature Note") -> str:
    return f"""---
title: {title}
note_id: {note_id}
type: literature-note
authored_by: model
date: 2026-08-26
tags: []
supports: []
contradicts: []
extends: []
related_to: []
---

Body text for {title}.
"""


def _put_lit_note(items_table, s3, note_id: str, title: str = "A Literature Note"):
    items_table.put_item(Item={
        "note_id": note_id, "type": "literature-note", "title": title,
        "s3_key": f"{note_id}.md", "created_at": "2026-08-26T00:00:00", "gsi_pk": "item",
    })
    s3.put_object(Bucket="test-bucket", Key=f"{note_id}.md", Body=_lit_note_md(note_id, title).encode())


@pytest.fixture
def client():
    with mock_aws():
        ddb = _create_tables()
        from clients import s3
        import routers.items as items_module
        from main import app
        from fastapi.testclient import TestClient

        items_module.lambda_client.invoke = MagicMock()
        items_module.trigger_kb_sync = MagicMock()
        yield (
            TestClient(app),
            ddb.Table("test-items"),
            ddb.Table("test-edges"),
            s3,
            items_module,
        )


class TestWritePermanentNote:
    def test_writes_s3_and_item_row_with_no_authored_by_or_source_id(self, client):
        from linkgen import write_permanent_note
        _test_client, items_table, _edges, s3, _items_module = client

        result = write_permanent_note("My Idea", "The body of my idea.", ["tag1"], [])

        note_id = result["note_id"]
        raw = s3.get_object(Bucket="test-bucket", Key=f"{note_id}.md")["Body"].read().decode()
        assert "type: permanent-note" in raw
        assert "authored_by" not in raw
        assert "The body of my idea." in raw

        row = items_table.get_item(Key={"note_id": note_id})["Item"]
        assert row["type"] == "permanent-note"
        assert "authored_by" not in row
        assert "source_id" not in row

    def test_grounded_in_writes_edges_and_wikilinks(self, client):
        from linkgen import write_permanent_note
        _test_client, items_table, edges_table, s3, _items_module = client

        _put_lit_note(items_table, s3, "lit-a", "Cited Note")

        result = write_permanent_note("My Idea", "Body.", [], ["lit-a"])
        note_id = result["note_id"]

        edges = edges_table.query(KeyConditionExpression=Key("from_id").eq(note_id)).get("Items", [])
        assert len(edges) == 1
        assert edges[0]["type"] == "GROUNDED_IN"
        assert edges[0]["to_id"] == "lit-a"

        raw = s3.get_object(Bucket="test-bucket", Key=f"{note_id}.md")["Body"].read().decode()
        assert "[[lit-a|Cited Note]]" in raw


class TestCreatePermanentNoteEndpoint:
    def test_201_on_success(self, client):
        test_client, items_table, _edges, _s3, items_module = client

        resp = test_client.post("/items/permanent", json={"title": "New Idea", "body": "The idea.", "tags": []})

        assert resp.status_code == 201
        note_id = resp.json()["note_id"]
        assert items_table.get_item(Key={"note_id": note_id})["Item"]["type"] == "permanent-note"
        items_module.trigger_kb_sync.assert_called_once()

    def test_404_when_grounded_in_note_missing(self, client):
        test_client, items_table, _edges, _s3, _items_module = client

        resp = test_client.post(
            "/items/permanent",
            json={"title": "New Idea", "body": "The idea.", "grounded_in": ["does-not-exist"]},
        )

        assert resp.status_code == 404
        assert "does-not-exist" in resp.json()["detail"]
        # Nothing written on the missing-note failure path.
        assert "Items" not in items_table.scan() or items_table.scan()["Items"] == []


class TestFindConnectionsEndpoint:
    def test_404_for_missing_note(self, client):
        test_client, _items, _edges, _s3, _items_module = client
        resp = test_client.post("/items/does-not-exist/find-connections")
        assert resp.status_code == 404

    def test_400_for_literature_note(self, client):
        test_client, items_table, _edges, s3, _items_module = client
        _put_lit_note(items_table, s3, "lit-a")

        resp = test_client.post("/items/lit-a/find-connections")

        assert resp.status_code == 400

    def test_202_invokes_worker_with_reclassify_mode(self, client):
        from linkgen import write_permanent_note
        test_client, items_table, _edges, s3, items_module = client
        _put_lit_note(items_table, s3, "lit-a")
        note_id = write_permanent_note("My Idea", "The body of my idea.", [], [])["note_id"]

        resp = test_client.post(f"/items/{note_id}/find-connections")

        assert resp.status_code == 202
        assert resp.json()["session_id"]

        items_module.lambda_client.invoke.assert_called_once()
        call_kwargs = items_module.lambda_client.invoke.call_args.kwargs
        sent_payload = json.loads(call_kwargs["Payload"])
        assert sent_payload["mode"] == "reclassify"
        assert sent_payload["session_id"] == resp.json()["session_id"]
        assert call_kwargs["InvocationType"] == "Event"
        assert note_id in sent_payload["prompt"]
        assert "The body of my idea." in sent_payload["prompt"]
