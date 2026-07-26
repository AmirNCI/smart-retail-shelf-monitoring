"""
This AWS Lambda function runs when someone opens the dashboard. It reads
the two DynamoDB tables and sends back the current shelf readings and any
alerts that are still active, as JSON.
"""

import json
import os
import time
from decimal import Decimal

import boto3

dynamodb = boto3.resource("dynamodb")
stock_table = dynamodb.Table(os.environ["STOCK_TABLE"])
alerts_table = dynamodb.Table(os.environ["ALERTS_TABLE"])


def number_from_decimal(value):
    """DynamoDB gives us Decimal numbers, but JSON does not know what a
    Decimal is, so turn it into a normal int or float first."""
    if value == int(value):
        return int(value)
    return float(value)


def clean_shelf_item(item):
    """Turn every Decimal value in a shelf item into a normal number."""
    clean_item = {}
    for key, value in item.items():
        if isinstance(value, Decimal):
            clean_item[key] = number_from_decimal(value)
        else:
            clean_item[key] = value
    return clean_item


def clean_alert_item(item):
    """Same idea as clean_shelf_item, but also cleans the nested 'detail'."""
    clean_item = clean_shelf_item(item)
    clean_item["detail"] = json.loads(clean_item.get("detail", "{}"))
    return clean_item


def lambda_handler(event, context):
    now = int(time.time())

    shelf_items = stock_table.scan().get("Items", [])
    clean_shelves = []
    for item in shelf_items:
        clean_shelves.append(clean_shelf_item(item))

    alert_items = alerts_table.scan().get("Items", [])
    active_alerts = []
    for item in alert_items:
        if int(item.get("ttl", 0)) > now:
            active_alerts.append(clean_alert_item(item))

    body = {"shelves": clean_shelves, "alerts": active_alerts}

    return {
        "statusCode": 200,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
        },
        "body": json.dumps(body),
    }
