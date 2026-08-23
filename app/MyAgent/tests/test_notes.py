"""
Unit tests for the pure-ish helpers in tools/notes.py — no AWS dependency
except _resolve_source, which is moto-mocked. See CLAUDE.md's Testing
section for why these specific functions: real bugs building the
structured Source model lived exactly here (dedup normalization,
frontmatter scalar handling), and were expensive to catch via live
deploy-and-verify when a local test would catch them in milliseconds.
"""
import re

import httpx
import pytest
from moto import mock_aws

from tools.notes import (
    _fetch_youtube,
    _normalize_source_key,
    _parse_frontmatter,
    _render_frontmatter,
    _resolve_source,
    _slugify,
    _youtube_video_id,
    fetch_url,
    read_pdf,
)


class _FakeResponse:
    def __init__(self, status_code=200, text="", content=b"", headers=None, json_data=None):
        self.status_code = status_code
        self.text = text
        self.content = content or text.encode()
        self.headers = headers or {}
        self._json_data = json_data

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(f"status {self.status_code}", request=None, response=self)


class _FakeClient:
    """Stands in for httpx.Client — routes .get(url) to a response keyed by
    a substring match against the configured dict, so one fake can answer
    both the oEmbed call and the main fetch in a single test."""

    def __init__(self, responses):
        self._responses = responses

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def get(self, url, **kwargs):
        for key, response in self._responses.items():
            if key in url:
                return response
        raise AssertionError(f"no fake response configured for {url}")


@pytest.fixture
def fake_httpx(monkeypatch):
    def _install(responses):
        monkeypatch.setattr("tools.notes.httpx.Client", lambda *a, **kw: _FakeClient(responses))

    return _install


def _create_sources_table():
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


def _create_uploads_bucket():
    import boto3

    boto3.client("s3", region_name="ap-southeast-2").create_bucket(
        Bucket="test-uploads", CreateBucketConfiguration={"LocationConstraint": "ap-southeast-2"}
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
        _create_sources_table()

        first = _resolve_source(source_url="https://example.com/article", source_title="An Article")
        second = _resolve_source(source_url="https://example.com/article?utm_source=twitter", source_title="An Article")

        assert first == second

    @mock_aws
    def test_no_source_returns_none(self):
        assert _resolve_source() is None

    @mock_aws
    def test_same_pdf_content_dedupes_to_same_source_id(self):
        # Real bug caught in live verification: keying dedup off the S3 key
        # itself never dedupes, since every upload gets a fresh upload_id in
        # its key even for byte-identical content. Must key off the actual
        # content (via the single-PUT object's ETag, which is its MD5).
        import boto3

        _create_sources_table()
        _create_uploads_bucket()
        s3 = boto3.client("s3", region_name="ap-southeast-2")
        pdf_bytes = b"%PDF-1.4 identical content"
        s3.put_object(Bucket="test-uploads", Key="uploads/aaa111/paper.pdf", Body=pdf_bytes)
        s3.put_object(Bucket="test-uploads", Key="uploads/bbb222/paper-reupload.pdf", Body=pdf_bytes)

        first = _resolve_source(source_pdf_key="uploads/aaa111/paper.pdf")
        second = _resolve_source(source_pdf_key="uploads/bbb222/paper-reupload.pdf")

        assert first == second

    @mock_aws
    def test_different_pdf_content_doesnt_match(self):
        import boto3

        _create_sources_table()
        _create_uploads_bucket()
        s3 = boto3.client("s3", region_name="ap-southeast-2")
        s3.put_object(Bucket="test-uploads", Key="uploads/aaa111/paper-one.pdf", Body=b"content one")
        s3.put_object(Bucket="test-uploads", Key="uploads/bbb222/paper-two.pdf", Body=b"content two, different")

        first = _resolve_source(source_pdf_key="uploads/aaa111/paper-one.pdf")
        second = _resolve_source(source_pdf_key="uploads/bbb222/paper-two.pdf")

        assert first != second

    @mock_aws
    def test_pdf_source_defaults_title_to_filename(self):
        import boto3

        _create_sources_table()
        _create_uploads_bucket()
        s3 = boto3.client("s3", region_name="ap-southeast-2")
        s3.put_object(Bucket="test-uploads", Key="uploads/abc123/My Paper.pdf", Body=b"content")

        source_id = _resolve_source(source_pdf_key="uploads/abc123/My Paper.pdf")

        item = boto3.resource("dynamodb", region_name="ap-southeast-2").Table("test-sources").get_item(
            Key={"source_id": source_id}
        )["Item"]
        assert item["title"] == "My Paper.pdf"
        assert item["type"] == "pdf"

    @mock_aws
    def test_pdf_key_takes_priority_over_url(self):
        import boto3

        _create_sources_table()
        _create_uploads_bucket()
        s3 = boto3.client("s3", region_name="ap-southeast-2")
        s3.put_object(Bucket="test-uploads", Key="uploads/abc123/paper.pdf", Body=b"content")

        source_id = _resolve_source(source_url="https://example.com/article", source_pdf_key="uploads/abc123/paper.pdf")

        item = boto3.resource("dynamodb", region_name="ap-southeast-2").Table("test-sources").get_item(
            Key={"source_id": source_id}
        )["Item"]
        assert item["type"] == "pdf"


class TestReadPdf:
    @mock_aws
    def test_reads_pdf_bytes_into_a_document_content_block(self):
        import boto3

        s3 = boto3.client("s3", region_name="ap-southeast-2")
        s3.create_bucket(Bucket="test-uploads", CreateBucketConfiguration={"LocationConstraint": "ap-southeast-2"})
        pdf_bytes = b"%PDF-1.4 fake pdf content for testing"
        s3.put_object(Bucket="test-uploads", Key="uploads/abc123/paper.pdf", Body=pdf_bytes)

        result = read_pdf("uploads/abc123/paper.pdf")

        assert result["status"] == "success"
        assert len(result["content"]) == 1
        doc = result["content"][0]["document"]
        assert doc["format"] == "pdf"
        assert doc["source"]["bytes"] == pdf_bytes
        assert "paper" in doc["name"]

    @mock_aws
    def test_filename_with_periods_produces_a_valid_document_name(self):
        # Real bug caught live: os.path.splitext only strips the *last*
        # extension, so "notes.v2.pdf" -> "notes.v2" still has a period —
        # Bedrock's document name only allows alphanumeric, whitespace,
        # hyphens, parens, brackets, and this reached ConverseStream
        # unsanitized, crashing the whole turn with a ValidationException.
        import boto3

        s3 = boto3.client("s3", region_name="ap-southeast-2")
        s3.create_bucket(Bucket="test-uploads", CreateBucketConfiguration={"LocationConstraint": "ap-southeast-2"})
        s3.put_object(Bucket="test-uploads", Key="uploads/abc123/notes.v2.pdf", Body=b"%PDF-1.4 fake")

        result = read_pdf("uploads/abc123/notes.v2.pdf")

        doc_name = result["content"][0]["document"]["name"]
        assert re.fullmatch(r"[a-zA-Z0-9\s\-()\[\]]+", doc_name)

    @mock_aws
    def test_cleans_up_tmp_file_after_reading(self):
        import glob

        import boto3

        s3 = boto3.client("s3", region_name="ap-southeast-2")
        s3.create_bucket(Bucket="test-uploads", CreateBucketConfiguration={"LocationConstraint": "ap-southeast-2"})
        s3.put_object(Bucket="test-uploads", Key="uploads/abc123/paper.pdf", Body=b"%PDF-1.4 fake")

        before = set(glob.glob("/tmp/*.pdf"))
        read_pdf("uploads/abc123/paper.pdf")
        after = set(glob.glob("/tmp/*.pdf"))

        assert after == before


class TestFetchUrl:
    HTML_WITH_METADATA = """<html><head>
        <title>How Caching Actually Works</title>
        <meta name="author" content="Jane Doe">
        </head><body><p>Cache invalidation is famously hard.</p></body></html>"""

    HTML_NO_METADATA = "<html><body><p>Just some text, no title or author tags.</p></body></html>"

    def test_html_page_extracts_title_and_author(self, fake_httpx):
        fake_httpx({"example.com": _FakeResponse(text=self.HTML_WITH_METADATA, headers={"content-type": "text/html"})})
        result = fetch_url("https://example.com/article")
        assert result["title"] == "How Caching Actually Works"
        assert result["author"] == "Jane Doe"
        assert "Cache invalidation is famously hard" in result["text"]
        assert "<p>" not in result["text"]

    def test_html_page_with_no_metadata_returns_empty_strings_not_a_crash(self, fake_httpx):
        fake_httpx({"example.com": _FakeResponse(text=self.HTML_NO_METADATA, headers={"content-type": "text/html"})})
        result = fetch_url("https://example.com/no-metadata")
        assert result["title"] == ""
        assert result["author"] == ""
        assert "Just some text" in result["text"]

    def test_pdf_url_returns_document_content_block(self, fake_httpx):
        pdf_bytes = b"%PDF-1.4 fake pdf bytes"
        fake_httpx({"example.com": _FakeResponse(content=pdf_bytes, headers={"content-type": "application/pdf"})})
        result = fetch_url("https://example.com/paper.pdf")
        assert result["status"] == "success"
        doc = result["content"][0]["document"]
        assert doc["format"] == "pdf"
        assert doc["source"]["bytes"] == pdf_bytes

    def test_pdf_url_with_no_extension_and_dotted_id_produces_a_valid_document_name(self, fake_httpx):
        # Real bug caught live against https://arxiv.org/pdf/1706.03762 — no
        # .pdf suffix to strip at all, so the raw "1706.03762" (with periods)
        # reached ConverseStream unsanitized and crashed the whole turn.
        pdf_bytes = b"%PDF-1.4 fake pdf bytes"
        fake_httpx({"arxiv.org": _FakeResponse(content=pdf_bytes, headers={"content-type": "application/pdf"})})
        result = fetch_url("https://arxiv.org/pdf/1706.03762")
        doc_name = result["content"][0]["document"]["name"]
        assert re.fullmatch(r"[a-zA-Z0-9\s\-()\[\]]+", doc_name)

    def test_unreachable_url_raises(self, fake_httpx):
        fake_httpx({"example.com": _FakeResponse(status_code=404)})
        with pytest.raises(httpx.HTTPStatusError):
            fetch_url("https://example.com/missing")

    def test_youtube_url_routes_to_fetch_youtube(self, fake_httpx, monkeypatch):
        monkeypatch.setattr("tools.notes._fetch_youtube", lambda video_id, url: {"title": "t", "author": "a", "text": "x"})
        result = fetch_url("https://youtu.be/dQw4w9WgXcQ")
        assert result == {"title": "t", "author": "a", "text": "x"}


class TestFetchYoutube:
    def test_returns_structured_title_author_text(self, fake_httpx):
        fake_httpx({
            "oembed": _FakeResponse(json_data={"title": "A Video", "author_name": "A Channel"}),
        })

        class _FakeTranscript:
            def fetch(self, video_id):
                return [type("Snippet", (), {"text": "hello"})(), type("Snippet", (), {"text": "world"})()]

        import tools.notes as notes_module
        original = notes_module.YouTubeTranscriptApi
        notes_module.YouTubeTranscriptApi = lambda: _FakeTranscript()
        try:
            result = _fetch_youtube("dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ")
        finally:
            notes_module.YouTubeTranscriptApi = original

        assert result == {"title": "A Video", "author": "A Channel", "text": "hello world"}

    def test_no_transcript_falls_back_to_title_channel_only(self, fake_httpx):
        from tools.notes import CouldNotRetrieveTranscript

        fake_httpx({
            "oembed": _FakeResponse(json_data={"title": "A Video", "author_name": "A Channel"}),
        })

        class _FakeTranscript:
            def fetch(self, video_id):
                raise CouldNotRetrieveTranscript(video_id)

        import tools.notes as notes_module
        original = notes_module.YouTubeTranscriptApi
        notes_module.YouTubeTranscriptApi = lambda: _FakeTranscript()
        try:
            result = _fetch_youtube("dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ")
        finally:
            notes_module.YouTubeTranscriptApi = original

        assert result["title"] == "A Video"
        assert result["author"] == "A Channel"
        assert "No transcript is available" in result["text"]

    def test_no_transcript_and_no_title_reraises(self, fake_httpx):
        from tools.notes import CouldNotRetrieveTranscript

        fake_httpx({"oembed": _FakeResponse(status_code=404)})  # oEmbed fails too -> no title

        class _FakeTranscript:
            def fetch(self, video_id):
                raise CouldNotRetrieveTranscript(video_id)

        import tools.notes as notes_module
        original = notes_module.YouTubeTranscriptApi
        notes_module.YouTubeTranscriptApi = lambda: _FakeTranscript()
        try:
            with pytest.raises(CouldNotRetrieveTranscript):
                _fetch_youtube("dQw4w9WgXcQ", "https://youtu.be/dQw4w9WgXcQ")
        finally:
            notes_module.YouTubeTranscriptApi = original
