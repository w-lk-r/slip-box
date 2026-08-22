import os

# tools/notes.py reads these at import time — must be set before any test
# module imports it. Values don't need to be real; nothing here touches
# actual AWS except the moto-mocked test, which creates its own table.
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("KB_ID", "test-kb")
os.environ.setdefault("ITEMS_TABLE", "test-items")
os.environ.setdefault("EDGES_TABLE", "test-edges")
os.environ.setdefault("SOURCES_TABLE", "test-sources")
os.environ.setdefault("INGEST_SESSIONS_TABLE", "test-ingest-sessions")
os.environ.setdefault("UPLOADS_BUCKET", "test-uploads")
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-southeast-2")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
