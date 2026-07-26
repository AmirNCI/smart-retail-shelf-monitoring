"""
This is the program you run to start all the sensors.
It reads config.json, then starts one background thread per sensor.

Usage: python run_sensors.py [path/to/config.json]
"""

import json
import sys
import threading
import time

from sensor_base import run_sensor_forever


def main():
    # Get the config file path from the command line, or use a default.
    if len(sys.argv) > 1:
        config_path = sys.argv[1]
    else:
        config_path = "config.json"

    with open(config_path) as f:
        config = json.load(f)

    mqtt_host = config["mqtt"]["host"]
    mqtt_port = config["mqtt"]["port"]
    topic_prefix = config["mqtt"]["topic_prefix"]

    # Start one thread for every sensor listed in config.json.
    # Using threads lets all the sensors run at the same time, each on its
    # own schedule, instead of waiting for one another.
    for sensor_settings in config["sensors"]:
        thread = threading.Thread(
            target=run_sensor_forever,
            args=(sensor_settings, mqtt_host, mqtt_port, topic_prefix),
            daemon=True,
        )
        thread.start()

        topic = topic_prefix + "/" + sensor_settings["shelf"] + "/" + sensor_settings["type"]
        print("started " + sensor_settings["sensor_id"] + " -> topic " + topic)

    print("all sensors running, press Ctrl+C to stop")

    # Keep the main program alive so the background threads keep running.
    # (They are "daemon" threads, so they will all stop automatically
    # when this main program stops.)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nstopping...")


if __name__ == "__main__":
    main()
