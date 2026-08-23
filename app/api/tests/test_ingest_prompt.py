"""
Pure-function tests for ingest.py's prompt-building helpers, per CLAUDE.md's
guidance for pure-ish helpers with no AWS dependency.

Regression coverage for a real Bedrock Guardrails PROMPT_ATTACK false
positive: the original single-mode wording ("Create exactly ONE atomic
note... do not create multiple notes even if...") combined with a URL
source reads as an imperative instruction-override immediately followed by
"fetch this URL" — structurally close to an indirect prompt-injection
pattern, and Bedrock's guardrail flagged it at MEDIUM confidence against a
MEDIUM-strength filter. Confirmed live via bedrock-runtime apply-guardrail
that the rewording below clears the same filter (action: NONE) without
loosening the guardrail's strength. These tests just pin the wording so it
doesn't drift back toward the flagged pattern; they can't exercise the
guardrail itself.

_build_prompt/_mode_instruction are pure functions, but importing
routers.ingest at all transitively imports clients.py, which constructs real
boto3 objects at module level — real bug caught live: doing that unmocked
at collection time (before any fixture runs) made this the first, unmocked
import of the shared clients.py module in the whole test session, breaking
every other test file's own mock_aws()-wrapped import later. Matches the
same pattern test_ingest_status.py's fixture and test_uploads.py already use.
"""
from moto import mock_aws

with mock_aws():
    from models import IngestRequest
    from routers.ingest import _build_prompt, _mode_instruction


def _req(**kwargs):
    return IngestRequest(url="https://example.com/article", **kwargs)


class TestModeInstruction:
    def test_auto_mode_has_no_instruction(self):
        assert _mode_instruction(_req(mode="auto")) == ""

    def test_single_mode_no_topic_avoids_imperative_override_phrasing(self):
        instruction = _mode_instruction(_req(mode="single"))
        assert "one atomic note" in instruction
        assert "create exactly" not in instruction.lower()
        assert "do not create multiple" not in instruction.lower()

    def test_single_mode_with_topic_avoids_imperative_override_phrasing(self):
        instruction = _mode_instruction(_req(mode="single", topic="caching"))
        assert "caching" in instruction
        assert "create exactly" not in instruction.lower()

    def test_all_mode_unchanged(self):
        assert _mode_instruction(_req(mode="all")) == (
            "Extract ALL the distinct key ideas from this source and create one atomic note per idea."
        )


class TestBuildPrompt:
    def test_single_mode_url_prompt_has_no_blank_instruction_prefix_issue(self):
        prompt = _build_prompt(_req(mode="single"))
        assert prompt.startswith("The user selected single-note mode")
        assert "Ingest this URL:" in prompt

    def test_auto_mode_url_prompt_is_just_the_source(self):
        prompt = _build_prompt(_req(mode="auto"))
        assert prompt == "Ingest this URL: https://example.com/article"
