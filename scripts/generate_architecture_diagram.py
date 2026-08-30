"""
Generate the Slip Box architecture diagram.
Run from repo root: cd app/MyAgent && uv run python ../../scripts/generate_architecture_diagram.py
Output: docs/diagrams/architecture.png
"""

import os
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent.parent / "docs" / "diagrams"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
os.chdir(OUTPUT_DIR)

from diagrams import Diagram, Cluster, Edge
from diagrams.aws.compute import Lambda
from diagrams.aws.ml import Bedrock
from diagrams.aws.network import APIGateway
from diagrams.aws.storage import S3
from diagrams.aws.database import Dynamodb, Neptune
from diagrams.onprem.client import Client, User
from diagrams.programming.framework import React
from diagrams.programming.language import Python

graph_attr = {
    "fontsize": "12",
    "bgcolor": "white",
    "pad": "0.6",
    "splines": "polyline",
    "nodesep": "0.5",
    "ranksep": "0.8",
}

with Diagram(
    "Slip Box — Architecture",
    filename="architecture",
    outformat="png",
    show=False,
    graph_attr=graph_attr,
    direction="TB",
):
    user = User("User")

    with Cluster("Clients (live)"):
        web = React("Next.js\nGraph · Review · Sources\nUpload · Write")
        mobile = Client("Expo Mobile\nprimary daily-use app")

    with Cluster("FastAPI backend  —  API Gateway + Lambda"):
        gw = APIGateway("API Gateway")
        api_fn = Python("ApiFunction\ndirect S3/DynamoDB\nreads + writes")
        worker_fn = Lambda("WorkerFunction\nasync agent invoke")

    reconciler_fn = Lambda("ReconcilerFunction\nS3 → DynamoDB sync\n(fired by S3 events)")

    with Cluster("AgentCore Runtime  —  ap-southeast-2"):
        bedrock = Bedrock("Amazon Bedrock\nClaude")
        ingestion = Python(
            "Ingestion Agent\n"
            "write_note · write_summary\n"
            "update_summary · search_notes\n"
            "fetch_url · read_pdf"
        )
        classifier = Python(
            "Classification Agent\n"
            "search_notes · write_edge\n"
            "(Agent-as-tool + standalone\nreclassify pass)"
        )

        with Cluster("Deferred — future scope"):
            researcher = Python("Research Agent\n(--research fan-out)")
            swot = Python("SWOT / Analysis Agent")

    with Cluster("Knowledge Store"):
        kb = Bedrock("Bedrock\nKnowledge Base")
        s3 = S3("S3\nslip-box-notes\n.md + sidecars")
        uploads = S3("S3\nslip-box-uploads\nraw PDF staging")
        neptune = Neptune("Neptune\n(production target,\nnot used in MVP)")
        ddb = Dynamodb("DynamoDB\nitems · edges · sources")

    # Client -> backend (live)
    user >> web
    user >> mobile
    web >> Edge() >> gw
    mobile >> Edge() >> gw
    gw >> api_fn
    gw >> Edge(label="/ingest, /summarize") >> worker_fn

    # ApiFunction: direct writes, no agent (PermanentNote, edge edits, review/index actions)
    api_fn >> Edge(label="direct write\n(PermanentNote, edges)") >> s3
    api_fn >> Edge(label="direct read/write") >> ddb
    api_fn >> Edge(label="uploads presign") >> uploads
    api_fn >> Edge(label="trigger sync", style="dashed") >> kb

    # WorkerFunction -> AgentCore (async invoke, live)
    worker_fn >> Edge(label="invoke_agent_runtime") >> ingestion
    worker_fn >> Edge(label="mode: reclassify") >> classifier

    # Ingestion agent -> classification agent (Agent-as-tool, live)
    ingestion >> Edge(label="classify_relationships\n(as-tool)") >> classifier

    # Agents -> Bedrock model
    ingestion >> Edge(color="grey") >> bedrock
    classifier >> Edge(color="grey") >> bedrock

    # Agents -> storage (live)
    ingestion >> Edge(label="write .md")     >> s3
    ingestion >> Edge(label="retrieve")      >> kb
    ingestion >> Edge(label="items + edges") >> ddb
    classifier >> Edge(label="write_edge")   >> ddb

    # S3 -> reconciler -> DynamoDB (Stage 1, live) and -> KB sync
    s3 >> Edge(label="ObjectCreated/Removed") >> reconciler_fn
    reconciler_fn >> Edge(label="upsert/delete") >> ddb
    reconciler_fn >> Edge(label="mode: reclassify\n(Stage 2)", style="dashed") >> worker_fn
    s3 >> Edge(label="sync", style="dashed") >> kb

    # Deferred agents — not wired to storage, kept for context only
    researcher >> Edge(color="grey", style="dashed") >> bedrock
    swot       >> Edge(color="grey", style="dashed") >> bedrock

    # DynamoDB -> Neptune is a future migration, not a live path
    ddb >> Edge(label="future migration", style="dotted") >> neptune
