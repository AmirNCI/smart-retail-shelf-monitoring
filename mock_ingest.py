"""
Temporary local stand-in for the AWS backend (API Gateway -> SQS -> Lambda ->
DynamoDB), so the sensor + fog pipeline can be tested end-to-end today.

On Day 2, point fog/config.json's "dispatch_url" at the deployed API Gateway
endpoint instead, and this file is no longer needed.
"""

import json
from datetime import datetime

from flask import Flask, jsonify, request

app = Flask(__name__)


@app.route("/ingest", methods=["POST"])
def ingest():
    payload = request.get_json(force=True)
    kind = payload.get("kind", "unknown")
    ts = datetime.now().strftime("%H:%M:%S")

    if kind == "alert":
        for alert in payload.get("alerts", []):
            print(f"[{ts}] ALERT  shelf={alert.get('shelf')} type={alert['type']} "
                  f"detail={json.dumps({k: v for k, v in alert.items() if k not in ('type', 'shelf')})}")
    elif kind == "batch":
        shelves = payload.get("shelves", {})
        print(f"[{ts}] BATCH  {len(shelves)} shelf/shelves reporting: {list(shelves.keys())}")
    else:
        print(f"[{ts}] UNKNOWN payload kind: {kind}")

    return jsonify({"status": "received"}), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=9000)
