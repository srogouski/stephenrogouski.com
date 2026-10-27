"""Unit tests for the visitor counter Lambda.

Uses moto to mock DynamoDB so no real AWS resources are touched.
"""
import importlib
import json
import os

import boto3
import pytest
from moto import mock_aws

TABLE_NAME = "test-visitor-count"
ITEM_ID = "visits"


@pytest.fixture
def app_module():
    """Import the Lambda module with env vars and a mocked DynamoDB table."""
    os.environ["TABLE_NAME"] = TABLE_NAME
    os.environ["ITEM_ID"] = ITEM_ID
    os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

    with mock_aws():
        client = boto3.client("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=TABLE_NAME,
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Import (or reload) after the mock is active so the resource is mocked.
        import app  # noqa: WPS433 - local import is intentional

        importlib.reload(app)
        yield app


def test_increment_from_empty(app_module):
    assert app_module.increment_count() == 1


def test_increment_is_monotonic(app_module):
    assert app_module.increment_count() == 1
    assert app_module.increment_count() == 2
    assert app_module.increment_count() == 3


def test_handler_returns_200_and_count(app_module):
    result = app_module.lambda_handler({}, None)
    assert result["statusCode"] == 200
    assert result["headers"]["Content-Type"] == "application/json"
    assert result["headers"]["Access-Control-Allow-Origin"] == "*"

    body = json.loads(result["body"])
    assert body["count"] == 1


def test_handler_count_increases_across_calls(app_module):
    first = json.loads(app_module.lambda_handler({}, None)["body"])["count"]
    second = json.loads(app_module.lambda_handler({}, None)["body"])["count"]
    assert second == first + 1


def test_handler_returns_500_on_error(app_module, monkeypatch):
    def boom():
        raise RuntimeError("dynamo down")

    monkeypatch.setattr(app_module, "increment_count", boom)
    result = app_module.lambda_handler({}, None)
    assert result["statusCode"] == 500
    body = json.loads(result["body"])
    assert "error" in body
