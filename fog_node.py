"""
This is the "fog node". It sits between the sensors and the cloud backend.

What it does, step by step:
1. Listens for sensor readings arriving over MQTT.
2. Remembers the newest reading from every sensor, in a dictionary.
3. Checks each reading against simple rules ("thresholds"). If something is
   wrong (e.g. stock too low, fridge door open too long), it sends an
   "alert" message to the backend immediately.
4. Every "batch_interval_sec" seconds (15 by default), it sends everything
   it currently knows in one "batch" message, instead of sending every
   single reading one by one. This saves bandwidth, which is the whole
   point of doing some processing at the fog layer instead of the cloud.
"""

import json
import sys
import threading
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt
import requests

# This dictionary remembers the newest reading for every shelf and sensor
# type, e.g. latest_readings["dairy-milk"]["temperature"] = {...}
latest_readings = {}

# Sensor messages arrive on a background MQTT thread, while the batch loop
# below runs on the main thread. This lock stops them from both changing
# latest_readings at the exact same moment and mixing things up.
readings_lock = threading.Lock()

# Alert rules for each shelf, built from config.json (see build_shelf_rules).
# Different product categories can have different rules -- for example a
# freezer needs a much colder normal temperature range than a fridge does.
shelf_rules = {}

# Used for any shelf that does not have its own rule in shelf_rules.
default_rules = {}

topic_prefix = ""
dispatch_url = ""


def build_shelf_rules(sensor_list):
    """Look through config.json's sensor list and collect each shelf's own
    alert thresholds (its own restock level, temperature range, etc.)."""
    rules = {}

    for sensor_settings in sensor_list:
        shelf = sensor_settings.get("shelf")
        sensor_type = sensor_settings.get("type")
        if shelf is None:
            continue

        if shelf not in rules:
            rules[shelf] = {}

        if sensor_type == "shelf_weight" and "restock_threshold_kg" in sensor_settings:
            rules[shelf]["restock_threshold_kg"] = sensor_settings["restock_threshold_kg"]

        if sensor_type == "fridge_door" and "max_open_sec" in sensor_settings:
            rules[shelf]["door_max_open_sec"] = sensor_settings["max_open_sec"]

        if sensor_type == "temperature" and "normal_range_c" in sensor_settings:
            rules[shelf]["temp_range_c"] = sensor_settings["normal_range_c"]

        if sensor_type == "humidity" and "normal_range_pct" in sensor_settings:
            rules[shelf]["humidity_range_pct"] = sensor_settings["normal_range_pct"]

    return rules


def get_rule(shelf, rule_name, fallback_value):
    """Get a shelf's own rule if it has one, otherwise use the fallback."""
    if shelf in shelf_rules and rule_name in shelf_rules[shelf]:
        return shelf_rules[shelf][rule_name]
    return fallback_value


def check_for_alert(shelf, sensor_type, reading):
    """Look at one reading and decide if it breaks a rule.
    Returns an alert dictionary, or None if everything is fine."""
    now = datetime.now(timezone.utc).isoformat()

    if sensor_type == "shelf_weight":
        threshold = get_rule(shelf, "restock_threshold_kg", default_rules["restock_threshold_kg"])
        if reading["weight_kg"] <= threshold:
            return {
                "type": "restock_needed",
                "shelf": shelf,
                "weight_kg": reading["weight_kg"],
                "detected_at": now,
            }

    if sensor_type == "fridge_door" and reading.get("door_open"):
        max_open_sec = get_rule(shelf, "door_max_open_sec", default_rules["door_max_open_sec"])
        if reading.get("open_duration_sec", 0) >= max_open_sec:
            return {
                "type": "door_open_too_long",
                "shelf": shelf,
                "open_duration_sec": reading["open_duration_sec"],
                "detected_at": now,
            }

    if sensor_type == "temperature":
        low, high = get_rule(shelf, "temp_range_c", default_rules["temp_range_c"])
        temperature = reading["temperature_c"]
        if temperature < low or temperature > high:
            return {
                "type": "temperature_out_of_range",
                "shelf": shelf,
                "temperature_c": temperature,
                "normal_range_c": [low, high],
                "detected_at": now,
            }

    if sensor_type == "humidity":
        low, high = get_rule(shelf, "humidity_range_pct", default_rules["humidity_range_pct"])
        humidity = reading["humidity_pct"]
        if humidity < low or humidity > high:
            return {
                "type": "humidity_out_of_range",
                "shelf": shelf,
                "humidity_pct": humidity,
                "normal_range_pct": [low, high],
                "detected_at": now,
            }

    return None


def send_to_backend(payload):
    """Send a JSON payload to the cloud backend over HTTP."""
    payload["dispatched_at"] = datetime.now(timezone.utc).isoformat()
    try:
        response = requests.post(dispatch_url, json=payload, timeout=3)
        print("dispatched " + payload["kind"] + " -> " + str(response.status_code))
    except requests.exceptions.RequestException as error:
        print("dispatch FAILED (" + payload["kind"] + "): " + str(error))


def on_connect(client, userdata, flags, reason_code, properties=None):
    topic = topic_prefix + "/#"
    client.subscribe(topic, qos=1)
    print("connected, subscribed to " + topic)


def on_message(client, userdata, msg):
    try:
        reading = json.loads(msg.payload.decode())
    except json.JSONDecodeError:
        print("dropped a message that was not valid JSON")
        return

    shelf = reading.get("shelf")
    sensor_type = reading.get("type")
    if shelf is None or sensor_type is None:
        return

    with readings_lock:
        if shelf not in latest_readings:
            latest_readings[shelf] = {}
        latest_readings[shelf][sensor_type] = reading

    alert = check_for_alert(shelf, sensor_type, reading)
    if alert is not None:
        send_to_backend({"kind": "alert", "shelf": shelf, "alerts": [alert]})


def batch_sending_loop(batch_interval_sec):
    """Every few seconds, send everything we currently know about every shelf."""
    while True:
        time.sleep(batch_interval_sec)

        with readings_lock:
            if len(latest_readings) == 0:
                continue
            # Make a copy so we are not still holding the lock while sending.
            snapshot = {}
            for shelf in latest_readings:
                snapshot[shelf] = dict(latest_readings[shelf])

        send_to_backend({"kind": "batch", "shelves": snapshot})


def main():
    global topic_prefix, dispatch_url, shelf_rules, default_rules

    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = "config.json"

    with open(config_path) as f:
        config = json.load(f)

    mqtt_host = config["mqtt"]["host"]
    mqtt_port = config["mqtt"]["port"]
    topic_prefix = config["mqtt"]["topic_prefix"]

    fog_settings = config["fog"]
    default_rules = {
        "restock_threshold_kg": fog_settings["restock_threshold_kg"],
        "door_max_open_sec": fog_settings["door_max_open_sec"],
        "temp_range_c": fog_settings["temp_range_c"],
        "humidity_range_pct": fog_settings["humidity_range_pct"],
    }
    dispatch_url = fog_settings["dispatch_url"]
    shelf_rules = build_shelf_rules(config["sensors"])

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="fog-node-01")
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(mqtt_host, mqtt_port, keepalive=30)
    client.loop_start()

    print("fog node running, waiting for sensor data...")
    batch_sending_loop(fog_settings["batch_interval_sec"])  # blocks forever


if __name__ == "__main__":
    main()
