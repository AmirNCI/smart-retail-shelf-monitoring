"""
This AWS Lambda function runs automatically whenever a new message arrives
in the SQS queue. It reads the message (which came from the fog node) and
saves the important parts into two DynamoDB tables:
  - one table for the latest stock/sensor readings per shelf
  - one table for alerts that are currently active
"""

import json
import os
import time
from decimal import Decimal

import boto3

dynamodb = boto3.resource("dynamodb")
stock_table = dynamodb.Table(os.environ["STOCK_TABLE"])
alerts_table = dynamodb.Table(os.environ["ALERTS_TABLE"])

# An alert only counts as "active" for this many seconds after it arrives.
# If a new one does not arrive to refresh it, it quietly expires.
ALERT_ACTIVE_SECONDS = 120


def lambda_handler(event, context):
    for record in event["Records"]:
        # DynamoDB does not understand normal Python floats, so we tell
        # json.loads to turn every number into a Decimal instead.
        try:
            payload = json.loads(record["body"], parse_float=Decimal)
        except (json.JSONDecodeError, KeyError):
            continue

        if payload.get("kind") == "alert":
            save_alerts(payload)
        elif payload.get("kind") == "batch":
            save_batch(payload)

    return {"batchItemFailures": []}


def save_alerts(payload):
    now = int(time.time())

    for alert in payload.get("alerts", []):
        shelf = alert.get("shelf", payload.get("shelf", "unknown"))

        # Keep every field from the alert except "type" and "shelf" as extra detail.
        detail = {}
        for key in alert:
            if key != "type" and key != "shelf":
                detail[key] = alert[key]

        alerts_table.put_item(Item={
            "shelf": shelf,
            "alert_type": alert.get("type", "unknown"),
            "detail": json.dumps(detail, default=decimal_to_number),
            "detected_at": alert.get("detected_at", ""),
            "ttl": now + ALERT_ACTIVE_SECONDS,
        })


def save_batch(payload):
    last_updated = payload.get("dispatched_at", "")

    for shelf, readings in payload.get("shelves", {}).items():
        item = {"shelf": shelf, "last_updated": last_updated}

        for sensor_type, reading in readings.items():
            if sensor_type == "shelf_weight":
                item["weight_kg"] = reading.get("weight_kg")
            elif sensor_type == "foot_traffic":
                item["people_count"] = reading.get("people_count")
            elif sensor_type == "temperature":
                item["temperature_c"] = reading.get("temperature_c")
            elif sensor_type == "humidity":
                item["humidity_pct"] = reading.get("humidity_pct")
            elif sensor_type == "fridge_door":
                item["door_open"] = reading.get("door_open")
                item["door_open_sec"] = reading.get("open_duration_sec")

        stock_table.put_item(Item=item)


def decimal_to_number(value):
    """Used by json.dumps to turn a Decimal into a normal number."""
    if isinstance(value, Decimal):
        if value == int(value):
            return int(value)
        return float(value)
    return str(value)
