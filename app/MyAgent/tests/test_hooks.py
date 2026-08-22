"""
Unit tests for hooks.py's IngestOutcomeTracker — the structured replacement
for grepping a 2000-char-truncated Worker log line to find out whether a turn
created a note (see docs/future-scope.md's "Real ingest-completion tracking").

Uses the real strands.hooks event dataclasses (not hand-rolled stand-ins) so
these tests break if the installed SDK's event shape ever changes underneath
this code — see CLAUDE.md's Testing section on trusting installed source over
assumptions. The DynamoDB write is moto-mocked, per the same section's
guidance for a new read/write shape.
"""
import json

import boto3
import pytest
from moto import mock_aws
from strands.agent.agent_result import AgentResult
from strands.hooks.events import AfterInvocationEvent, AfterToolCallEvent
from strands.telemetry.metrics import EventLoopMetrics

from hooks import INGEST_SESSIONS_TABLE, IngestOutcomeTracker


def _tool_call_event(name: str, result: dict, exception: Exception | None = None) -> AfterToolCallEvent:
    return AfterToolCallEvent(
        agent=None,
        selected_tool=None,
        tool_use={"toolUseId": "t1", "name": name, "input": {}},
        invocation_state={},
        result=result,
        exception=exception,
    )


def _success_result(payload: dict) -> dict:
    return {"toolUseId": "t1", "status": "success", "content": [{"text": json.dumps(payload)}]}


def _invocation_event(final_text: str | None) -> AfterInvocationEvent:
    message = {"role": "assistant", "content": [{"text": final_text}]} if final_text is not None else {"role": "assistant", "content": []}
    result = AgentResult(stop_reason="end_turn", message=message, metrics=EventLoopMetrics(), state={})
    return AfterInvocationEvent(agent=None, result=result)


@pytest.fixture
def sessions_table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="ap-southeast-2")
        ddb.create_table(
            TableName=INGEST_SESSIONS_TABLE,
            KeySchema=[{"AttributeName": "session_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "session_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield ddb.Table(INGEST_SESSIONS_TABLE)


class TestNoteAccumulation:
    def test_tracks_write_note_success(self):
        tracker = IngestOutcomeTracker("session-1")
        tracker._on_tool_call(_tool_call_event(
            "write_note", _success_result({"note_id": "n1", "s3_key": "n1.md", "title": "A Note"})
        ))
        assert tracker.notes_created == [{"note_id": "n1", "title": "A Note"}]

    def test_tracks_write_summary_success(self):
        tracker = IngestOutcomeTracker("session-1")
        tracker._on_tool_call(_tool_call_event(
            "write_summary", _success_result({"note_id": "s1", "s3_key": "s1.md", "title": "A Summary"})
        ))
        assert tracker.notes_created == [{"note_id": "s1", "title": "A Summary"}]

    def test_ignores_untracked_tools(self):
        tracker = IngestOutcomeTracker("session-1")
        tracker._on_tool_call(_tool_call_event("search_notes", _success_result({"results": []})))
        assert tracker.notes_created == []

    def test_ignores_failed_tool_calls(self):
        tracker = IngestOutcomeTracker("session-1")
        tracker._on_tool_call(_tool_call_event(
            "write_note", {"toolUseId": "t1", "status": "error", "content": [{"text": "boom"}]},
            exception=RuntimeError("boom"),
        ))
        assert tracker.notes_created == []

    def test_ignores_error_status_even_without_exception(self):
        tracker = IngestOutcomeTracker("session-1")
        tracker._on_tool_call(_tool_call_event(
            "write_note", {"toolUseId": "t1", "status": "error", "content": [{"text": "Error: bad input"}]},
        ))
        assert tracker.notes_created == []

    def test_accumulates_multiple_notes(self):
        tracker = IngestOutcomeTracker("session-1")
        tracker._on_tool_call(_tool_call_event("write_note", _success_result({"note_id": "n1", "title": "One"})))
        tracker._on_tool_call(_tool_call_event("write_note", _success_result({"note_id": "n2", "title": "Two"})))
        assert len(tracker.notes_created) == 2


class TestSessionWrite:
    def test_turn_with_notes_writes_complete_status(self, sessions_table):
        tracker = IngestOutcomeTracker("session-1")
        tracker.notes_created = [{"note_id": "n1", "title": "A Note"}]
        tracker._on_turn_end(_invocation_event("Done."))

        item = sessions_table.get_item(Key={"session_id": "session-1"})["Item"]
        assert item["status"] == "complete"
        assert item["notes_created"] == [{"note_id": "n1", "title": "A Note"}]
        assert "skipped_reason" not in item

    def test_turn_with_no_notes_writes_skipped_reason(self, sessions_table):
        tracker = IngestOutcomeTracker("session-2")
        tracker._on_turn_end(_invocation_event("This source doesn't cover the requested topic."))

        item = sessions_table.get_item(Key={"session_id": "session-2"})["Item"]
        assert item["status"] == "complete"
        assert item["notes_created"] == []
        assert item["skipped_reason"] == "This source doesn't cover the requested topic."

    def test_write_failure_does_not_raise(self, monkeypatch):
        # No table created — the update_item call will fail with a real
        # ClientError. The hook must swallow it, not blow up the agent's
        # response over a tracking-side failure.
        with mock_aws():
            tracker = IngestOutcomeTracker("session-3")
            tracker._on_turn_end(_invocation_event("Done."))  # should not raise
