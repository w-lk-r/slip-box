import os

import boto3
from dotenv import load_dotenv

load_dotenv()

S3_BUCKET = os.environ["S3_BUCKET"]
ITEMS_TABLE = os.environ["ITEMS_TABLE"]
EDGES_TABLE = os.environ["EDGES_TABLE"]
SOURCES_TABLE = os.environ["SOURCES_TABLE"]
INGEST_SESSIONS_TABLE = os.environ["INGEST_SESSIONS_TABLE"]
UPLOADS_BUCKET = os.environ["UPLOADS_BUCKET"]
AGENT_RUNTIME_ARN = os.environ["AGENT_RUNTIME_ARN"]
WORKER_FUNCTION_NAME = os.environ.get("WORKER_FUNCTION_NAME", "")
REGION = os.environ.get("AWS_REGION", os.environ.get("REGION", "ap-southeast-2"))

# Explicit regional endpoint — boto3's default S3 endpoint resolution can
# still hand back the legacy global s3.amazonaws.com host for a bucket
# outside us-east-1, which 307-redirects to the real regional endpoint. Fine
# for normal SDK calls (transparently followed), but a presigned PUT URL
# handed to a browser shouldn't need a redirect hop at all.
s3 = boto3.client("s3", region_name=REGION, endpoint_url=f"https://s3.{REGION}.amazonaws.com")
ddb = boto3.resource("dynamodb", region_name=REGION)
lambda_client = boto3.client("lambda", region_name=REGION)
agentcore = boto3.client("bedrock-agentcore", region_name=REGION)

items_table = ddb.Table(ITEMS_TABLE)
edges_table = ddb.Table(EDGES_TABLE)
sources_table = ddb.Table(SOURCES_TABLE)
ingest_sessions_table = ddb.Table(INGEST_SESSIONS_TABLE)
