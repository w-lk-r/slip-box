import os

from strands.models.bedrock import BedrockModel


def load_model() -> BedrockModel:
    """Get Bedrock model client using IAM credentials.

    Guardrail catches injected-instruction/harmful-content attempts riding
    in through fetch_url/read_pdf's untrusted third-party content — see
    docs/review-todo.md #11 and the CDK-managed CfnGuardrail in app-stack.ts.
    """
    return BedrockModel(
        model_id="global.anthropic.claude-sonnet-4-5-20250929-v1:0",
        guardrail_id=os.environ["GUARDRAIL_ID"],
        guardrail_version=os.environ["GUARDRAIL_VERSION"],
        guardrail_trace="enabled",
    )
