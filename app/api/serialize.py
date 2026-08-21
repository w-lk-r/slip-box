from decimal import Decimal


def clean(obj):
    """Recursively convert DynamoDB's Decimal (and nested dict/list) into plain
    JSON-serializable types. DynamoDB returns confidence scores etc. as Decimal,
    which the standard JSON encoder can't handle directly."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [clean(v) for v in obj]
    return obj
