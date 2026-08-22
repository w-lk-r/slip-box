import os

import boto3
from dotenv import load_dotenv

load_dotenv()

S3_BUCKET = os.environ["S3_BUCKET"]
ITEMS_TABLE = os.environ["ITEMS_TABLE"]
EDGES_TABLE = os.environ["EDGES_TABLE"]
SOURCES_TABLE = os.environ["SOURCES_TABLE"]
AGENT_RUNTIME_ARN = os.environ["AGENT_RUNTIME_ARN"]
WORKER_FUNCTION_NAME = os.environ.get("WORKER_FUNCTION_NAME", "")
REGION = os.environ.get("AWS_REGION", os.environ.get("REGION", "ap-southeast-2"))

s3 = boto3.client("s3", region_name=REGION)
ddb = boto3.resource("dynamodb", region_name=REGION)
lambda_client = boto3.client("lambda", region_name=REGION)
agentcore = boto3.client("bedrock-agentcore", region_name=REGION)

items_table = ddb.Table(ITEMS_TABLE)
edges_table = ddb.Table(EDGES_TABLE)
sources_table = ddb.Table(SOURCES_TABLE)
