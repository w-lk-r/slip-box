"""
Generate the Slip Box architecture diagram.
Run from repo root: cd app/MyAgent && uv run python ../../docs/diagram.py
Output: docs/architecture.png
"""

import os
from pathlib import Path

os.chdir(Path(__file__).parent)

from diagrams import Diagram, Cluster, Edge
from diagrams.aws.ml import Bedrock
from diagrams.aws.storage import S3
from diagrams.aws.database import Dynamodb, Neptune
from diagrams.onprem.client import User
from diagrams.programming.framework import React
from diagrams.programming.language import Python

graph_attr = {
    "fontsize": "12",
    "bgcolor": "white",
    "pad": "0.6",
    "splines": "curved",
    "nodesep": "0.6",
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

    with Cluster("Frontend (not yet built)"):
        ui  = React("Next.js\nIngest · Review · Graph")
        api = Python("FastAPI")

    with Cluster("AgentCore Runtime  —  ap-southeast-2"):
        bedrock = Bedrock("Amazon Bedrock\nClaude Sonnet")

        with Cluster("Strands Agents"):
            ingestion  = Python("Ingestion Agent")
            classifier = Python("Classification Agent")
            researcher = Python("Research Agent")
            swot       = Python("SWOT / Analysis Agent")

    with Cluster("Knowledge Store"):
        s3      = S3("S3\nslip-box-notes\n.md + sidecars")
        kb      = Bedrock("Bedrock\nKnowledge Base")
        ddb     = Dynamodb("DynamoDB\nitems · pending_edges")
        neptune = Neptune("Neptune\ngraph · typed edges")

    # User flow
    user >> ui >> api

    # API → agents
    api >> ingestion
    api >> classifier

    # Agents → Bedrock
    ingestion  >> Edge(color="grey") >> bedrock
    classifier >> Edge(color="grey") >> bedrock
    researcher >> Edge(color="grey") >> bedrock
    swot       >> Edge(color="grey") >> bedrock

    # Ingestion agent → storage
    ingestion >> Edge(label="write .md") >> s3
    ingestion >> Edge(label="retrieve")  >> kb
    ingestion >> Edge(label="metadata")  >> ddb

    # S3 → KB sync
    s3 >> Edge(label="sync", style="dashed") >> kb

    # Classification agent → graph
    classifier >> Edge(label="edges")   >> neptune
    classifier >> Edge(label="pending") >> ddb

    # Research agent → KB
    researcher >> Edge(label="retrieve") >> kb
