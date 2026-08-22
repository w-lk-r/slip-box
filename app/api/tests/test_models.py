"""
Pydantic-only tests for IngestRequest's exactly-one-of validator, extended to
a third mutually-exclusive source (pdf_key) alongside text/url. No AWS
involved — pure request-shape validation, per CLAUDE.md's guidance for a
FastAPI request/response shape change.
"""
import pytest
from pydantic import ValidationError

from models import IngestRequest


class TestIngestRequestSourceValidation:
    def test_text_only_is_valid(self):
        IngestRequest(text="hello")

    def test_url_only_is_valid(self):
        IngestRequest(url="https://example.com")

    def test_pdf_key_only_is_valid(self):
        IngestRequest(pdf_key="uploads/abc123/paper.pdf")

    def test_none_provided_is_invalid(self):
        with pytest.raises(ValidationError):
            IngestRequest()

    def test_text_and_url_together_is_invalid(self):
        with pytest.raises(ValidationError):
            IngestRequest(text="hello", url="https://example.com")

    def test_text_and_pdf_key_together_is_invalid(self):
        with pytest.raises(ValidationError):
            IngestRequest(text="hello", pdf_key="uploads/abc123/paper.pdf")

    def test_url_and_pdf_key_together_is_invalid(self):
        with pytest.raises(ValidationError):
            IngestRequest(url="https://example.com", pdf_key="uploads/abc123/paper.pdf")

    def test_source_url_requires_text(self):
        with pytest.raises(ValidationError):
            IngestRequest(url="https://example.com", source_url="https://example.com/original")

    def test_source_url_valid_alongside_text(self):
        IngestRequest(text="hello", source_url="https://example.com/original")
