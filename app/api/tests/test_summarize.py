"""
Tests for ingest.py's POST /summarize — the on-demand summarize trigger, per
CLAUDE.md's guidance for a new DynamoDB read/write shape. moto-mocked;
`from main import app` happens inside mock_aws() per test_items.py's own
docstring (an unmocked module-level import of clients.py breaks every other
test file in the same pytest session — see test_ingest_prompt.py).

lambda_client.invoke is monkeypatched rather than moto-mocked: moto's Lambda
mock can't execute real handler code, so asserting on the call args of a
patched invoke is the only way to check the payload shape without actually
deploying anything.
"""
import json
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

REGION = "ap-southeast-2"


def _create_items_table():
    ddb = boto3.resource("dynamodb", region_name=REGION)
    table = ddb.create_table(
        TableName="test-items",
        KeySchema=[{"AttributeName": "note_id", "KeyType": "HASH"}],
        AttributeDefinitions=[{"AttributeName": "note_id", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )
    boto3.client("s3", region_name=REGION).create_bucket(
        Bucket="test-bucket", CreateBucketConfiguration={"LocationConstraint": REGION}
    )
    return table


def _note_md(title: str, body: str) -> str:
    return f"""---
title: {title}
type: literature-note
authored_by: model
date: 2026-08-23
tags: []
---

{body}
"""


def _put_note(items_table, s3, note_id: str, title: str, body: str):
    items_table.put_item(Item={"note_id": note_id, "type": "literature-note", "title": title, "s3_key": f"{note_id}.md"})
    s3.put_object(Bucket="test-bucket", Key=f"{note_id}.md", Body=_note_md(title, body).encode())


@pytest.fixture
def client():
    with mock_aws():
        items_table = _create_items_table()
        from clients import s3
        import routers.ingest as ingest_module
        from main import app
        from fastapi.testclient import TestClient

        ingest_module.lambda_client.invoke = MagicMock()
        yield TestClient(app), items_table, s3, ingest_module.lambda_client


class TestBuildSummarizePrompt:
    def test_includes_each_notes_title_and_body(self, client):
        _test_client, items_table, s3, _lambda = client
        from routers.ingest import _build_summarize_prompt

        _put_note(items_table, s3, "note-a", "Note A Title", "Body of note A.")
        _put_note(items_table, s3, "note-b", "Note B Title", "Body of note B.")

        prompt = _build_summarize_prompt(["note-a", "note-b"])

        assert "note-a" in prompt and "Note A Title" in prompt and "Body of note A." in prompt
        assert "note-b" in prompt and "Note B Title" in prompt and "Body of note B." in prompt

    def test_includes_threshold_override_language(self, client):
        _test_client, items_table, s3, _lambda = client
        from routers.ingest import _build_summarize_prompt

        _put_note(items_table, s3, "note-a", "A", "Body A.")
        _put_note(items_table, s3, "note-b", "B", "Body B.")

        prompt = _build_summarize_prompt(["note-a", "note-b"])

        assert "four-or-more-notes threshold" in prompt
        assert "direct request from the user" in prompt

    def test_404s_listing_missing_note_ids(self, client):
        _test_client, items_table, s3, _lambda = client
        from fastapi import HTTPException
        from routers.ingest import _build_summarize_prompt

        _put_note(items_table, s3, "note-a", "A", "Body A.")

        with pytest.raises(HTTPException) as exc_info:
            _build_summarize_prompt(["note-a", "does-not-exist"])

        assert exc_info.value.status_code == 404
        assert "does-not-exist" in exc_info.value.detail


class TestSummarizeEndpoint:
    def test_422_below_minimum_note_ids(self, client):
        test_client, _items, _s3, _lambda = client
        resp = test_client.post("/summarize", json={"note_ids": ["note-a"]})
        assert resp.status_code == 422

    def test_404_for_missing_note(self, client):
        test_client, items_table, s3, _lambda = client
        _put_note(items_table, s3, "note-a", "A", "Body A.")

        resp = test_client.post("/summarize", json={"note_ids": ["note-a", "does-not-exist"]})

        assert resp.status_code == 404

    def test_202_invokes_worker_with_summarize_mode(self, client):
        test_client, items_table, s3, lambda_client = client
        _put_note(items_table, s3, "note-a", "A", "Body A.")
        _put_note(items_table, s3, "note-b", "B", "Body B.")

        resp = test_client.post("/summarize", json={"note_ids": ["note-a", "note-b"]})

        assert resp.status_code == 202
        assert resp.json()["session_id"]
        assert resp.json()["status"] == "processing"

        lambda_client.invoke.assert_called_once()
        call_kwargs = lambda_client.invoke.call_args.kwargs
        sent_payload = json.loads(call_kwargs["Payload"])
        assert sent_payload["mode"] == "summarize"
        assert sent_payload["session_id"] == resp.json()["session_id"]
        assert call_kwargs["InvocationType"] == "Event"
