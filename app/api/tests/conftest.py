import os

# clients.py reads these at import time — must be set before any test module
# imports it (directly or via a router). Values don't need to be real; nothing
# here touches actual AWS except the moto-mocked tests, which create their own
# tables.
os.environ.setdefault("S3_BUCKET", "test-bucket")
os.environ.setdefault("ITEMS_TABLE", "test-items")
os.environ.setdefault("EDGES_TABLE", "test-edges")
os.environ.setdefault("SOURCES_TABLE", "test-sources")
os.environ.setdefault("INGEST_SESSIONS_TABLE", "test-ingest-sessions")
os.environ.setdefault("UPLOADS_BUCKET", "test-uploads")
os.environ.setdefault("AGENT_RUNTIME_ARN", "arn:aws:bedrock-agentcore:ap-southeast-2:000000000000:runtime/test")
os.environ.setdefault("WORKER_FUNCTION_NAME", "test-worker")
os.environ.setdefault("KB_ID", "test-kb")
os.environ.setdefault("AWS_DEFAULT_REGION", "ap-southeast-2")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
