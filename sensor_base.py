"""
This file has one function that knows how to run a single sensor.

It keeps generating readings forever and sending ("publishing") them over
MQTT, with a short pause between each reading, until the program is stopped.
"""

import json
import time
from datetime import datetime, timezone

import paho.mqtt.client as mqtt

from generators import SENSOR_READING_FUNCTIONS, make_starting_state


def run_sensor_forever(sensor_settings, mqtt_host, mqtt_port, topic_prefix):
    sensor_id = sensor_settings["sensor_id"]
    shelf = sensor_settings["shelf"]
    sensor_type = sensor_settings["type"]
    frequency_sec = sensor_settings["frequency_sec"]
    topic = topic_prefix + "/" + shelf + "/" + sensor_type

    # Connect to the MQTT broker (think of it as a message post office).
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="sensor-" + sensor_id)
    client.connect(mqtt_host, mqtt_port, keepalive=30)
    client.loop_start()

    # Look up which function generates readings for this sensor's type.
    generate_reading = SENSOR_READING_FUNCTIONS[sensor_type]

    # "state" is where a sensor remembers things between readings,
    # like its current weight, or whether the fridge door is open.
    state = make_starting_state(sensor_settings)

    while True:
        reading = generate_reading(state, sensor_settings)

        # Add the standard fields every sensor message needs.
        message = {
            "sensor_id": sensor_id,
            "shelf": shelf,
            "type": sensor_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        message.update(reading)

        client.publish(topic, json.dumps(message), qos=1)
        time.sleep(frequency_sec)
