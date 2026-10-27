"""Visitor counter Lambda.

Atomically increments a single DynamoDB item and returns the new count.
Invoked via API Gateway HTTP API (GET /count).
"""
import json
import os

import boto3

TABLE_NAME = os.environ.get("TABLE_NAME")
ITEM_ID = os.environ.get("ITEM_ID", "visits")

_dynamodb = boto3.resource("dynamodb")


def _table():
    """Return the DynamoDB table resource.

    Looked up lazily so tests can set TABLE_NAME / patch boto3 first.
    """
    return _dynamodb.Table(TABLE_NAME)


def increment_count():
    """Atomically add 1 to the counter and return the new value as an int."""
    response = _table().update_item(
        Key={"id": ITEM_ID},
        UpdateExpression="ADD visits :inc",
        ExpressionAttributeValues={":inc": 1},
        ReturnValues="UPDATED_NEW",
    )
    return int(response["Attributes"]["visits"])


def _response(status, body):
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }


def lambda_handler(event, context):
    """API Gateway entry point."""
    try:
        count = increment_count()
        return _response(200, {"count": count})
    except Exception as exc:  # noqa: BLE001 - surface a clean 500 to the client
        print(f"Error incrementing visitor count: {exc}")
        return _response(500, {"error": "Could not update visitor count."})
