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
    "splines": "polyline",
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
        ui = React("Next.js\nIngest · Review · Graph")
        api = Python("FastAPI")

    with Cluster("AgentCore Runtime  —  ap-southeast-2"):
        bedrock = Bedrock("Amazon Bedrock\nClaude")
        ingestion = Python(
            "Ingestion Agent\n"
            "write_note · write_edge\n"
            "write_summary · update_summary\n"
            "search_notes · fetch_url"
        )

        with Cluster("Planned — split into separate agents"):
            classifier = Python("Classification Agent")
            researcher = Python("Research Agent")
            swot = Python("SWOT / Analysis Agent")

    with Cluster("Knowledge Store"):
        kb = Bedrock("Bedrock\nKnowledge Base")
        s3 = S3("S3\nslip-box-notes\n.md + sidecars")
        neptune = Neptune("Neptune\n(production target,\nnot used in MVP)")
        ddb = Dynamodb("DynamoDB\nitems · edges")

    # User flow — none of this is wired yet, no FastAPI built
    user >> Edge(style="dashed") >> ui >> Edge(style="dashed") >> api >> Edge(style="dashed") >> ingestion

    # Live agent → Bedrock
    ingestion >> Edge(color="grey") >> bedrock

    # Ingestion agent → storage (live today)
    ingestion >> Edge(label="write .md")     >> s3
    ingestion >> Edge(label="retrieve")      >> kb
    ingestion >> Edge(label="items + edges") >> ddb

    # S3 → KB sync
    s3 >> Edge(label="sync", style="dashed") >> kb

    # Planned agents — grouped visually, not wired to storage yet
    classifier >> Edge(color="grey", style="dashed") >> bedrock
    researcher >> Edge(color="grey", style="dashed") >> bedrock
    swot       >> Edge(color="grey", style="dashed") >> bedrock

    # DynamoDB → Neptune is a future migration, not a live path
    ddb >> Edge(label="future migration", style="dotted") >> neptune
