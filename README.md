# Smart Retail Shelf Monitoring
A fog-computing based smart retail system: mock sensors publish shelf data over MQTT to a coded fog node, which processes it locally (threshold alerts + batching) and forwards it to a serverless AWS backend, feeding a live dashboard. Built for NCI module H9FECC (Fog and Edge Computing).

---

## Live Application
http://smart-retail-dashboard-611292914398.s3-website-us-east-1.amazonaws.com

---

## Tech Stack
- **Sensors & Fog Node:** Python 3, paho-mqtt, requests
- **Message Broker:** Mosquitto (MQTT)
- **Cloud Backend:** AWS API Gateway, SQS, Lambda (Python 3.12), DynamoDB
- **Dashboard Hosting:** AWS S3 (static website hosting)
- **Infrastructure as Code:** AWS CloudFormation
- **Dashboard:** HTML, CSS, JavaScript (no framework, no build step)
- **Version Control:** GitHub (public repository: https://github.com/AmirNCI/smart-retail-shelf-monitoring)

---

## Features
- 5 sensor types per shelf: weight, foot traffic, temperature, humidity, fridge door
- 10 products across 5 categories (dairy, frozen, bakery, produce, beverages)
- Configurable sensor frequency and fog dispatch rate, all driven from `config.json`
- Fog node does real local processing — immediate alerts + 15-second batching, not a pass-through relay
- Per-shelf alert thresholds (frozen and dairy have genuinely different normal ranges)
- Fully serverless AWS backend — no EC2, scales automatically (verified with an 80-request concurrent burst test)
- Live dashboard: stock levels, sensor readings, and active alerts, grouped by category
- Dashboard is genuinely cloud-hosted on S3, not just a local file

---

## Project Structure
```
Smart_Retail_Project/
├── config.json              # all sensor, MQTT, and fog threshold configuration
├── generators.py             # one function per sensor type, generates a reading
├── sensor_base.py             # runs a single sensor forever (connect, loop, publish)
├── run_sensors.py             # entry point — starts one thread per configured sensor
├── fog_node.py                 # fog node: subscribe, threshold-check, batch, dispatch
├── mock_ingest.py              # optional local Flask backend, for testing without AWS
├── backend/
│   ├── template.yaml           # CloudFormation: API Gateway, SQS, Lambda, DynamoDB, S3
│   ├── lambda_ingest.py        # SQS -> DynamoDB (writes stock + alerts)
│   └── lambda_query.py         # DynamoDB -> dashboard (reads stock + active alerts)
└── dashboard/
    └── index.html              # self-contained live dashboard (HTML/CSS/JS)
```

---

## Running Locally (Sensors + Fog Node)
**Prerequisites:** Python 3, mosquitto

```bash
# Install dependencies
pip install paho-mqtt requests

# Install and start the MQTT broker (macOS)
brew install mosquitto
mosquitto -p 1883 -v
```

In a second terminal, start the fog node (dispatches to whatever URL is set in `config.json`):
```bash
python3 fog_node.py config.json
```

In a third terminal, start the sensors:
```bash
python3 run_sensors.py config.json
```

You should see sensor readings flow into the fog node, batched dispatches every 15 seconds, and immediate alert dispatches whenever a threshold is breached. Stop everything with Ctrl+C in each terminal.

Open the dashboard locally to watch it update live:
```bash
open dashboard/index.html
```

---

## Deploying the AWS Backend
The whole backend — API Gateway, SQS, 2 Lambda functions, 2 DynamoDB tables, and an S3 bucket for the dashboard — deploys as a single CloudFormation stack.

```bash
cd backend
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name smart-retail-backend \
  --region us-east-1 \
  --capabilities CAPABILITY_IAM
```

Get the endpoint URLs after deploying:
```bash
aws cloudformation describe-stacks --stack-name smart-retail-backend \
  --region us-east-1 --query "Stacks[0].Outputs"
```

Put the `IngestUrl` value into `config.json`'s `fog.dispatch_url`. Upload the dashboard to its S3 bucket (`DashboardUrl` output) whenever `dashboard/index.html` changes — S3 doesn't auto-sync with the local file:
```bash
aws s3 cp dashboard/index.html \
  s3://smart-retail-dashboard-<your-account-id>/index.html \
  --content-type "text/html" --region us-east-1
```

### Important Note
This project was built and tested on an **AWS Academy Learner Lab** account. Credentials expire every few hours (`ExpiredToken` error) and need refreshing from the Lab's "AWS Details" panel. IAM is locked down on this account type — `iam:CreateRole` is denied, so every Lambda reuses the pre-provisioned `LabRole` rather than a custom one. AWS Budgets and CloudWatch billing alarms don't work either (spend is tracked by the Lab itself, not the AWS bill) — which is the main reason this project has no EC2 instance anywhere: nothing here accrues cost just for sitting idle.

---

## Configuration

| Setting | Where | Description |
|---|---|---|
| `frequency_sec` | per sensor, `config.json` | how often that sensor publishes a reading |
| `batch_interval_sec` | `config.json` → `fog` | how often the fog node sends routine readings to the backend |
| `restock_threshold_kg` | per `shelf_weight` sensor | stock level (kg) that triggers a restock alert for that shelf |
| `normal_range_c` / `normal_range_pct` | per `temperature` / `humidity` sensor | that shelf's own normal operating range |
| `max_open_sec` | per `fridge_door` sensor | how long the door can stay open before an alert fires |
| `dispatch_url` | `config.json` → `fog` | where the fog node sends data (the AWS `IngestUrl`) |

Every threshold above is read per-shelf by the fog node, not applied globally — this matters because dairy (2-6°C) and frozen (-20 to -15°C) genuinely need different rules.

---

## Code Style
The sensor, fog node, and Lambda code is deliberately written in a simple, beginner-friendly style — plain functions and dictionaries, no classes, no comprehensions, no recursion — so it's easy to read and explain line by line. The CloudFormation template and dashboard's JavaScript are normal infrastructure/frontend code, not simplified.
