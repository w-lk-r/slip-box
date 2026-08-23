"""
Unit tests for worker.py's ingest-session status writes. moto-mocked per
CLAUDE.md's guidance for a new DynamoDB read/write shape — no real AWS call,
no deploy needed. worker.py's call to bedrock-agentcore's
invoke_agent_runtime isn't moto-supported, so handler()'s success/error paths
are exercised with that one call monkeypatched; the DynamoDB writes around it
are real (against a moto-mocked table).
"""
import json

import boto3
import pytest
from moto import mock_aws

import worker


@pytest.fixture
def sessions_table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="ap-southeast-2")
        ddb.create_table(
            TableName=worker.INGEST_SESSIONS_TABLE,
            KeySchema=[{"AttributeName": "session_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "session_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield ddb.Table(worker.INGEST_SESSIONS_TABLE)


class TestSeedProcessing:
    def test_writes_processing_status_with_ttl(self, sessions_table):
        worker._seed_processing("session-1")
        item = sessions_table.get_item(Key={"session_id": "session-1"})["Item"]
        assert item["status"] == "processing"
        assert "started_at" in item
        assert item["ttl"] > 0


class TestMarkError:
    def test_updates_existing_record_to_error(self, sessions_table):
        worker._seed_processing("session-2")
        worker._mark_error("session-2", "boom")
        item = sessions_table.get_item(Key={"session_id": "session-2"})["Item"]
        assert item["status"] == "error"
        assert item["error"] == "boom"


class TestHandler:
    def test_success_path_seeds_processing_and_returns_complete(self, sessions_table, monkeypatch):
        class FakeStream:
            def read(self):
                return b'{"ok": true}'

        monkeypatch.setattr(
            worker.agentcore, "invoke_agent_runtime",
            lambda **kwargs: {"response": FakeStream(), "contentType": "application/json"},
        )

        result = worker.handler({"prompt": "hi", "session_id": "session-3"}, None)

        assert result == {"session_id": "session-3", "status": "complete"}
        item = sessions_table.get_item(Key={"session_id": "session-3"})["Item"]
        assert item["status"] == "processing"  # handler itself never writes "complete" — the agent's hook does

    def test_mode_is_forwarded_to_agent_payload_when_present(self, sessions_table, monkeypatch):
        # review-todo #8: reconciler.py's Stage 2 trigger sets mode:
        # "reclassify" so main.py routes to the standalone classification
        # agent instead of the ingestion agent — worker.py must pass it
        # through untouched.
        class FakeStream:
            def read(self):
                return b'{"ok": true}'

        calls = []

        def fake_invoke(**kwargs):
            calls.append(kwargs)
            return {"response": FakeStream(), "contentType": "application/json"}

        monkeypatch.setattr(worker.agentcore, "invoke_agent_runtime", fake_invoke)

        worker.handler({"prompt": "reclassify this", "session_id": "session-5", "mode": "reclassify"}, None)

        payload = json.loads(calls[0]["payload"])
        assert payload == {"prompt": "reclassify this", "mode": "reclassify"}

    def test_mode_omitted_when_not_present_on_event(self, sessions_table, monkeypatch):
        class FakeStream:
            def read(self):
                return b'{"ok": true}'

        calls = []

        def fake_invoke(**kwargs):
            calls.append(kwargs)
            return {"response": FakeStream(), "contentType": "application/json"}

        monkeypatch.setattr(worker.agentcore, "invoke_agent_runtime", fake_invoke)

        worker.handler({"prompt": "hi", "session_id": "session-6"}, None)

        payload = json.loads(calls[0]["payload"])
        assert payload == {"prompt": "hi"}

    def test_invoke_failure_marks_error_and_reraises(self, sessions_table, monkeypatch):
        def _raise(**kwargs):
            raise RuntimeError("runtime unavailable")

        monkeypatch.setattr(worker.agentcore, "invoke_agent_runtime", _raise)

        with pytest.raises(RuntimeError):
            worker.handler({"prompt": "hi", "session_id": "session-4"}, None)

        item = sessions_table.get_item(Key={"session_id": "session-4"})["Item"]
        assert item["status"] == "error"
        assert "runtime unavailable" in item["error"]
