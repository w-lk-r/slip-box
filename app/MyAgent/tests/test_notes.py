"""
Unit tests for the pure-ish helpers in tools/notes.py — no AWS dependency
except _resolve_source, which is moto-mocked. See CLAUDE.md's Testing
section for why these specific functions: real bugs building the
structured Source model lived exactly here (dedup normalization,
frontmatter scalar handling), and were expensive to catch via live
deploy-and-verify when a local test would catch them in milliseconds.
"""
from moto import mock_aws

from tools.notes import (
    _normalize_source_key,
    _parse_frontmatter,
    _render_frontmatter,
    _resolve_source,
    _slugify,
    _youtube_video_id,
)


class TestSlugify:
    def test_basic(self):
        assert _slugify("Hello World") == "hello-world"

    def test_strips_punctuation(self):
        assert _slugify("What's the Zettelkasten Method?") == "whats-the-zettelkasten-method"

    def test_collapses_whitespace_and_dashes(self):
        assert _slugify("a   b---c") == "a-b-c"

    def test_truncates_to_60_chars(self):
        long_title = "a" * 100
        assert len(_slugify(long_title)) == 60


class TestYoutubeVideoId:
    VIDEO_ID = "dQw4w9WgXcQ"

    def test_watch_url(self):
        assert _youtube_video_id(f"https://www.youtube.com/watch?v={self.VIDEO_ID}") == self.VIDEO_ID

    def test_watch_url_no_www(self):
        assert _youtube_video_id(f"https://youtube.com/watch?v={self.VIDEO_ID}") == self.VIDEO_ID

    def test_watch_url_with_extra_params(self):
        assert _youtube_video_id(f"https://www.youtube.com/watch?v={self.VIDEO_ID}&t=30s") == self.VIDEO_ID

    def test_short_url(self):
        assert _youtube_video_id(f"https://youtu.be/{self.VIDEO_ID}") == self.VIDEO_ID

    def test_short_url_with_tracking_param(self):
        assert _youtube_video_id(f"https://youtu.be/{self.VIDEO_ID}?si=abc123") == self.VIDEO_ID

    def test_mobile_url(self):
        assert _youtube_video_id(f"https://m.youtube.com/watch?v={self.VIDEO_ID}") == self.VIDEO_ID

    def test_shorts_url(self):
        assert _youtube_video_id(f"https://www.youtube.com/shorts/{self.VIDEO_ID}") == self.VIDEO_ID

    def test_embed_url(self):
        assert _youtube_video_id(f"https://www.youtube.com/embed/{self.VIDEO_ID}") == self.VIDEO_ID

    def test_non_youtube_url_returns_none(self):
        assert _youtube_video_id("https://example.com/article") is None


class TestNormalizeSourceKey:
    def test_youtube_urls_with_different_tracking_params_match(self):
        # The exact real bug this session: the same video shared multiple
        # times with a different ?si= each time must dedupe to one Source.
        a = _normalize_source_key("https://youtube.com/watch?v=CkoGWHyLTsk&si=oYcJzNrcqUcX4bPk")
        b = _normalize_source_key("https://youtu.be/CkoGWHyLTsk?si=SR-aV1TVFhXXze7R")
        assert a == b

    def test_different_youtube_videos_dont_match(self):
        a = _normalize_source_key("https://youtube.com/watch?v=CkoGWHyLTsk")
        b = _normalize_source_key("https://youtube.com/watch?v=Dk5nn24OSMA")
        assert a != b

    def test_web_url_strips_tracking_params(self):
        a = _normalize_source_key("https://example.com/article?utm_source=twitter")
        b = _normalize_source_key("https://example.com/article")
        assert a == b

    def test_web_url_case_insensitive_host(self):
        a = _normalize_source_key("https://Example.com/article")
        b = _normalize_source_key("https://example.com/article")
        assert a == b

    def test_web_url_trailing_slash_ignored(self):
        a = _normalize_source_key("https://example.com/article/")
        b = _normalize_source_key("https://example.com/article")
        assert a == b

    def test_web_url_keeps_non_tracking_params(self):
        a = _normalize_source_key("https://example.com/article?id=5")
        b = _normalize_source_key("https://example.com/article?id=6")
        assert a != b


class TestFrontmatterRoundTrip:
    def test_scalar_wikilink_source_field_round_trips(self):
        fields = {
            "title": "Test note",
            "note_id": "test-note-abc123",
            "source": "[[some-source-id|Some Source Title]]",
            "tags": ["a", "b"],
            "supports": [],
        }
        rendered = _render_frontmatter(fields)
        content = rendered + "\nBody text.\n"
        parsed, body = _parse_frontmatter(content)

        assert parsed["source"] == "[[some-source-id|Some Source Title]]"
        assert parsed["tags"] == ["a", "b"]
        assert parsed["supports"] == []
        assert body.strip() == "Body text."

    def test_empty_source_field_round_trips(self):
        fields = {"title": "Test note", "source": ""}
        parsed, _ = _parse_frontmatter(_render_frontmatter(fields) + "\nBody.\n")
        assert parsed["source"] == ""


class TestResolveSource:
    @mock_aws
    def test_same_url_dedupes_to_same_source_id(self):
        import boto3

        ddb = boto3.resource("dynamodb", region_name="ap-southeast-2")
        ddb.create_table(
            TableName="test-sources",
            KeySchema=[{"AttributeName": "source_id", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "source_id", "AttributeType": "S"},
                {"AttributeName": "source_key", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "source-key-index",
                    "KeySchema": [{"AttributeName": "source_key", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        first = _resolve_source("https://example.com/article", source_title="An Article")
        second = _resolve_source("https://example.com/article?utm_source=twitter", source_title="An Article")

        assert first == second

    @mock_aws
    def test_no_source_url_returns_none(self):
        assert _resolve_source("") is None
