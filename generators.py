"""
This file has one function for each type of sensor.

Every function takes two dictionaries:
  - "state"    -> the sensor's memory from the last reading (e.g. current weight)
  - "settings" -> the sensor's settings from config.json (e.g. its normal range)

Each function updates "state" and returns a new "reading" dictionary.
"""

import random
import time


def generate_shelf_weight_reading(state, settings):
    # A customer "buys" a random amount, so the weight goes down a little.
    amount_bought = random.uniform(0.2, 1.2)
    state["weight_kg"] = state["weight_kg"] - amount_bought
    if state["weight_kg"] < 0:
        state["weight_kg"] = 0.0

    # If the shelf is low enough, staff sometimes restock it back to full.
    restock_threshold = settings["restock_threshold_kg"]
    if state["weight_kg"] <= restock_threshold and random.random() < 0.15:
        state["weight_kg"] = settings["initial_weight_kg"]

    return {"weight_kg": round(state["weight_kg"], 2)}


def generate_foot_traffic_reading(state, settings):
    # Most of the time it is quiet, but sometimes there is a busy moment.
    quiet_count = random.randint(0, 3)
    busy_count = random.randint(4, 15)

    if random.random() < 0.3:
        people_count = busy_count
    else:
        people_count = quiet_count

    return {"people_count": people_count}


def generate_temperature_reading(state, settings):
    low, high = settings["normal_range_c"]

    # Small random change each time, like a real temperature slowly drifting.
    state["temperature_c"] = state["temperature_c"] + random.uniform(-0.3, 0.3)
    if state["temperature_c"] < low - 1:
        state["temperature_c"] = low - 1
    if state["temperature_c"] > high + 1:
        state["temperature_c"] = high + 1

    # Once in a while, simulate a fault that pushes the temperature too high.
    anomaly_chance = settings.get("anomaly_probability", 0.05)
    if random.random() < anomaly_chance:
        state["temperature_c"] = high + random.uniform(2, 5)

    return {"temperature_c": round(state["temperature_c"], 2)}


def generate_humidity_reading(state, settings):
    low, high = settings["normal_range_pct"]

    state["humidity_pct"] = state["humidity_pct"] + random.uniform(-1.5, 1.5)
    if state["humidity_pct"] < low - 5:
        state["humidity_pct"] = low - 5
    if state["humidity_pct"] > high + 5:
        state["humidity_pct"] = high + 5

    anomaly_chance = settings.get("anomaly_probability", 0.05)
    if random.random() < anomaly_chance:
        state["humidity_pct"] = high + random.uniform(5, 10)

    return {"humidity_pct": round(state["humidity_pct"], 2)}


def generate_fridge_door_reading(state, settings):
    now = time.time()
    open_chance = settings.get("open_probability", 0.15)

    if state["is_open"] == False and random.random() < open_chance:
        state["is_open"] = True
        state["opened_at"] = now
    elif state["is_open"] == True and random.random() < 0.4:
        state["is_open"] = False
        state["opened_at"] = None

    if state["is_open"] == True:
        open_duration_sec = round(now - state["opened_at"], 1)
    else:
        open_duration_sec = 0.0

    return {"door_open": state["is_open"], "open_duration_sec": open_duration_sec}


# This dictionary connects each sensor "type" name (from config.json) to the
# function that knows how to generate that kind of reading.
SENSOR_READING_FUNCTIONS = {
    "shelf_weight": generate_shelf_weight_reading,
    "foot_traffic": generate_foot_traffic_reading,
    "temperature": generate_temperature_reading,
    "humidity": generate_humidity_reading,
    "fridge_door": generate_fridge_door_reading,
}


def make_starting_state(sensor_settings):
    """Build the starting 'memory' for one sensor, based on its type."""
    sensor_type = sensor_settings["type"]

    if sensor_type == "shelf_weight":
        return {"weight_kg": sensor_settings["initial_weight_kg"]}

    if sensor_type == "temperature":
        low, high = sensor_settings["normal_range_c"]
        return {"temperature_c": (low + high) / 2}

    if sensor_type == "humidity":
        low, high = sensor_settings["normal_range_pct"]
        return {"humidity_pct": (low + high) / 2}

    if sensor_type == "fridge_door":
        return {"is_open": False, "opened_at": None}

    # foot_traffic sensors don't need to remember anything between readings.
    return {}
