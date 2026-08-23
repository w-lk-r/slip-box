"""
FastAPI TestClient test for POST /uploads/presign, per CLAUDE.md's guidance
for a request/response shape change. generate_presigned_url is a local SigV4
signing operation with no live AWS call, so this module needs no moto
mocking of its own — but `from main import app` still has to happen inside
a mock_aws() context (real bug caught live: pytest executes this module's
top-level code at collection time, before any test or fixture runs, so an
unmocked import here was the *first* import of the shared clients.py module
in the whole test session — and since Python caches modules, every later
test file's own `with mock_aws(): from main import app` pattern silently
got clients.py's boto3 objects already bound outside any mock, breaking
every test file that ran after this one alphabetically). Matches the same
"imported inside mock_aws so clients.py's ddb.Table() binds to the mock"
pattern test_ingest_status.py's fixture already uses.
"""
from fastapi.testclient import TestClient
from moto import mock_aws

with mock_aws():
    from main import app

client = TestClient(app)


def _file(filename: str, size: int = 1024) -> dict:
    return {"filename": filename, "size": size}


class TestPresignUploads:
    def test_returns_one_presigned_url_per_pdf(self):
        resp = client.post("/uploads/presign", json={"files": [_file("a.pdf"), _file("b.pdf")]})
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["files"]) == 2
        upload_id = body["upload_id"]
        assert body["files"][0]["key"] == f"uploads/{upload_id}/a.pdf"
        assert body["files"][0]["upload_url"].startswith("https://")
        assert body["files"][1]["key"] == f"uploads/{upload_id}/b.pdf"

    def test_rejects_non_pdf_filename(self):
        resp = client.post("/uploads/presign", json={"files": [_file("notes.txt")]})
        assert resp.status_code == 422

    def test_strips_path_components_from_filename(self):
        resp = client.post("/uploads/presign", json={"files": [_file("../../etc/passwd.pdf")]})
        assert resp.status_code == 200
        body = resp.json()
        assert body["files"][0]["key"] == f"uploads/{body['upload_id']}/passwd.pdf"

    def test_rejects_empty_file_list(self):
        resp = client.post("/uploads/presign", json={"files": []})
        assert resp.status_code == 422

    def test_rejects_file_over_size_cap(self):
        resp = client.post("/uploads/presign", json={"files": [_file("big.pdf", size=25 * 1024 * 1024)]})
        assert resp.status_code == 422

    def test_accepts_file_at_size_cap(self):
        resp = client.post("/uploads/presign", json={"files": [_file("exact.pdf", size=20 * 1024 * 1024)]})
        assert resp.status_code == 200

    def test_rejects_zero_or_negative_size(self):
        resp = client.post("/uploads/presign", json={"files": [_file("empty.pdf", size=0)]})
        assert resp.status_code == 422
