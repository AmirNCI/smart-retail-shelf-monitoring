# Smart Retail Shelf Monitoring

A fog/edge computing system for a retail store: mock sensors publish readings
over MQTT to a fog node, which processes them locally and forwards the result
to a real AWS cloud backend, feeding a live dashboard.

Built for NCI module H9FECC (Fog and Edge Computing).

## Architecture

```
Sensors (MQTT publish)
   -> Fog node (threshold checks + 15s batching, MQTT subscribe / HTTP dispatch)
      -> AWS API Gateway
         -> SQS queue
            -> Lambda (writes DynamoDB)
               -> Lambda (reads DynamoDB)
                  -> Dashboard (polls every 5s)
```

**Sensor & fog layer** (all plain Python, no AWS SDK needed): 5 sensor types
(shelf weight, foot traffic, temperature, humidity, fridge door) publish JSON
readings over MQTT. The fog node subscribes to all of them, applies threshold
logic locally (restock alerts, door-open-too-long, temperature/humidity
anomalies), dispatches alerts immediately, and batches routine readings every
`batch_interval_sec` (15s) instead of forwarding every reading one by one —
this local processing is the actual point of a fog layer: cut bandwidth and
latency to the cloud.

**Backend**: fully serverless on AWS — API Gateway receives the fog node's
HTTP POSTs and writes straight into an SQS queue (no Lambda needed just to
relay messages), which decouples ingestion from processing. A Lambda function
drains the queue and writes to two DynamoDB tables (current stock per shelf,
and active alerts). A second Lambda reads both tables and serves the
dashboard's polling requests. Everything here (SQS, Lambda, DynamoDB
on-demand billing) auto-scales with no manual capacity planning — verified
with a burst of 80 concurrent requests, which CloudWatch showed Lambda
handling with up to 5 concurrent executions automatically.

**Dashboard**: a single self-contained HTML/JS/CSS file (no build step, no
framework) that polls the backend every 5 seconds and shows live stock levels,
sensor readings, and active alerts, grouped by product category. Hosted on
S3 static website hosting (its own public AWS URL, part of the same
CloudFormation stack) so it's a genuine cloud-hosted dashboard, not just a
local file that happens to call a cloud API — see "AWS backend" below for the
link and how to re-upload it after edits.

## Product catalog

`config.json` currently simulates **10 products across 5 categories** (shelf
name encodes category as `<category>-<product>`):

| Category | Products | Sensors |
|---|---|---|
| Dairy | milk, yogurt, cheese, butter | weight, foot traffic, temp, humidity, fridge door |
| Frozen | icecream, vegetables | weight, foot traffic, temp, humidity, fridge door |
| Bakery | bread | weight, foot traffic |
| Produce | apples, bananas | weight, foot traffic |
| Beverages | soda | weight, foot traffic |

Dairy and frozen get the full sensor set since they're refrigerated; the rest
are ambient shelves with no door/temperature/humidity to monitor. Frozen's
temperature/humidity thresholds are deliberately different from dairy's (e.g.
-20 to -15°C vs 2-6°C) — the fog node reads each shelf's own thresholds from
its sensor config rather than using one global rule for every shelf.

## Requirements

- Python 3, `pip install paho-mqtt requests` (`flask` too, only if you want
  to run the old local mock backend instead of the real AWS one)
- An MQTT broker (mosquitto): on macOS, `brew install mosquitto`, then run
  it with `mosquitto -p 1883 -v` (no config file needed for local-only use)
- An AWS account with the backend already deployed (see below) — this
  project was built against an AWS Academy Learner Lab account

## Running locally

Start each component in its own terminal, from this `files/` directory:

```bash
# 1. Start the MQTT broker
mosquitto -p 1883 -v

# 2. Start the fog node (dispatches to whatever URL is in config.json)
python3 fog_node.py config.json

# 3. Start the sensors
python3 run_sensors.py config.json
```

You should see sensor readings flow into the fog node, batched dispatches
every 15 seconds, and immediate alert dispatches whenever a threshold is
breached (restock needed, door left open too long, temperature/humidity out
of range). Stop everything with Ctrl+C in each terminal (or `pkill -f
run_sensors.py`, `pkill -f fog_node.py`, `pkill -f mosquitto` if backgrounded).

Open `dashboard/index.html` directly in a browser (`open dashboard/index.html`
on macOS) to watch stock levels and alerts update live.

## AWS backend

The backend is one CloudFormation stack (`backend/template.yaml`) — API
Gateway, SQS, 2 Lambda functions (source also kept as standalone files in
`backend/` for readability), and 2 DynamoDB tables. No S3 bucket is needed:
the Lambda code is small enough to embed directly in the template.

```bash
cd backend
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name smart-retail-backend \
  --region us-east-1 \
  --capabilities CAPABILITY_IAM
```

After deploying, grab the endpoint URLs and put the ingest one into
`config.json`'s `fog.dispatch_url`:

```bash
aws cloudformation describe-stacks --stack-name smart-retail-backend \
  --region us-east-1 --query "Stacks[0].Outputs"
```

This also creates a public S3 bucket for the dashboard (`DashboardUrl` in the
outputs above). Upload the dashboard to it whenever `dashboard/index.html`
changes:

```bash
aws s3 cp dashboard/index.html \
  s3://smart-retail-dashboard-<your-account-id>/index.html \
  --content-type "text/html" --region us-east-1
```

**If you're on an AWS Academy Learner Lab account** (as this project was
built on): credentials expire every few hours (`ExpiredToken` error), and IAM
is locked down — you can't create new IAM roles (`iam:CreateRole` is denied),
so every Lambda reuses the pre-provisioned `LabRole`. AWS Budgets and
CloudWatch billing alarms don't work on this account type either (spend is
tracked by the Learner Lab itself, shown in the Vocareum UI, not your AWS
bill) — that's why this project is built entirely serverless with no idle
compute (no EC2, no Elastic Beanstalk), so there's nothing racking up cost
between sessions regardless.

## Configuration

All sensor frequencies, dispatch rates, and fog thresholds live in
`config.json` — nothing is hardcoded in the sensor/fog code itself. Each
sensor entry carries its own settings (e.g. a `shelf_weight` sensor has its
own `restock_threshold_kg`; a `temperature` sensor has its own
`normal_range_c`), and the fog node reads these per-shelf rather than
applying one global setting to every shelf.

## Code style

The sensor, fog node, and Lambda code is deliberately written in a simple,
beginner-friendly style (plain functions and dictionaries, no classes, no
comprehensions, no recursion) so it's easy to read and explain line by line.
The CloudFormation template and dashboard's JavaScript are not — those stay
as normal infrastructure/frontend code.

## Files

```
config.json              all sensor, MQTT, and fog threshold configuration
generators.py            one function per sensor type, generates a reading
sensor_base.py           runs a single sensor forever (connect, loop, publish)
run_sensors.py           entry point — starts one thread per configured sensor
fog_node.py              fog node: subscribe, threshold-check, batch, dispatch
mock_ingest.py           optional local Flask backend, for testing without AWS
backend/template.yaml    CloudFormation: API Gateway, SQS, Lambda, DynamoDB
backend/lambda_ingest.py SQS -> DynamoDB (writes stock + alerts)
backend/lambda_query.py  DynamoDB -> dashboard (reads stock + active alerts)
dashboard/index.html     self-contained live dashboard (HTML/CSS/JS)
```
