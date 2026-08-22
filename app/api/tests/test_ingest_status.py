"""
FastAPI TestClient test for GET /ingest/{session_id}, per CLAUDE.md's
guidance for a request/response shape change — catches serialization bugs
with no real Lambda or API Gateway involved. Backed by a moto-mocked
ingest-sessions table.
"""
import boto3
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws


@pytest.fixture
def client():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="ap-southeast-2")
        ddb.create_table(
            TableName="test-ingest-sessions",
            KeySchema=[{"AttributeName": "session_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "session_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        from main import app  # imported inside mock_aws so clients.py's ddb.Table() binds to the mock
        yield TestClient(app), ddb.Table("test-ingest-sessions")


class TestGetIngestStatus:
    def test_processing_status_when_no_record_exists_yet(self, client):
        test_client, _table = client
        # No PutItem has landed yet — the real race between POST /ingest
        # returning 202 and the Worker's own seed write. Must read as
        # "processing", not 404 — nothing has failed.
        resp = test_client.get("/ingest/unknown-session")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "processing"
        assert body["notes_created"] == []

    def test_complete_status_with_notes(self, client):
        test_client, table = client
        table.put_item(Item={
            "session_id": "session-1",
            "status": "complete",
            "notes_created": [{"note_id": "n1", "title": "A Note"}],
            "started_at": "2026-08-22T00:00:00+00:00",
            "completed_at": "2026-08-22T00:00:05+00:00",
        })
        resp = test_client.get("/ingest/session-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "complete"
        assert body["notes_created"] == [{"note_id": "n1", "title": "A Note"}]
        assert body["skipped_reason"] is None

    def test_complete_status_with_skipped_reason(self, client):
        test_client, table = client
        table.put_item(Item={
            "session_id": "session-2",
            "status": "complete",
            "notes_created": [],
            "skipped_reason": "Source didn't cover the requested topic.",
        })
        resp = test_client.get("/ingest/session-2")
        body = resp.json()
        assert body["notes_created"] == []
        assert body["skipped_reason"] == "Source didn't cover the requested topic."

    def test_error_status(self, client):
        test_client, table = client
        table.put_item(Item={"session_id": "session-3", "status": "error", "error": "runtime unavailable"})
        resp = test_client.get("/ingest/session-3")
        body = resp.json()
        assert body["status"] == "error"
        assert body["error"] == "runtime unavailable"
