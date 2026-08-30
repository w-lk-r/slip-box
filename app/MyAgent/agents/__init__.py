"""
The two Strands agents Slip Box runs — not one mega-prompt:

- ingestion.py: extracts atomic notes from an incoming source and writes them
- classification.py: proposes and scores typed connections between notes

main.py (the AgentCore entrypoint) constructs and dispatches between them; it
holds no agent-definition logic of its own.
"""
