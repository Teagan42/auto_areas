"""Perform calculations based on entity states."""
from __future__ import annotations
from statistics import mean, median
from collections.abc import Callable
from typing import Any
from collections.abc import Mapping
from homeassistant.core import State
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.helpers.typing import StateType
from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE

from .const import (
    CONFIG_HUMIDITY_CALCULATION,
    CONFIG_ILLUMINANCE_CALCULATION,
    CONFIG_PRESENCE_CALCULATION,
    CONFIG_TEMPERATURE_CALCULATION
)

CALCULATE_MAX = "max"
CALCULATE_MIN = "min"
CALCULATE_MEAN = "mean"
CALCULATE_MEDIAN = "median"
CALCULATE_LAST = "last"
CALCULATE_ALL = "all"
CALCULATE_ONE = "one"
CALCULATE_NONE = "none"


def is_float(state: State) -> bool:
    """Check if state is a float."""
    try:
        return float(state.state) is not None
    except Exception:
        return False


def is_bool(state: State) -> bool:
    """Check if state is a boolean."""
    try:
        return isinstance(state.state, bool) or state.state in [
            "on", "off", "yes", "no", "true", "false", "1", "0", True, False, 1, 0]
    except Exception:
        return False


def as_bool(state: State) -> bool:
    """Convert state to a boolean."""
    if isinstance(state.state, bool):
        return bool(state.state)
    return state.state in [
        "on", "yes", "true", "1", True, 1]


def float_states(states: list[State]) -> list[float]:
    """Filter and retrieve floats from list of states."""
    return [float(s.state) for s in states if is_float(s)]


def bool_states(states: list[State]) -> list[bool]:
    """Filter and retrieve bools from list of states."""
    return [as_bool(s) for s in states if is_bool(s)]


def calculate_max(states: list[State]) -> StateType:
    """Calculate the maximum of the list of values."""
    calc_values = float_states(states)
    if len(calc_values) == 0:
        return STATE_UNKNOWN
    return max(calc_values)


def calculate_min(states: list[State]) -> StateType:
    """Calculate the min of the list of values."""
    calc_values = float_states(states)
    if len(calc_values) == 0:
        return STATE_UNKNOWN
    return min(calc_values)


def calculate_mean(states: list[State]) -> StateType:
    """Calculate the mean of the list of values."""
    calc_values = float_states(states)
    if len(calc_values) == 0:
        return STATE_UNKNOWN
    return mean(calc_values)


def calculate_median(states: list[State]) -> StateType:
    """Calculate the median of the list of values."""
    calc_values = float_states(states)
    if len(calc_values) == 0:
        return STATE_UNKNOWN
    return median(calc_values)


def calculate_all(states: list[State]) -> StateType:
    """Calculate whether all of the list of values are true."""
    calc_values = bool_states(states)
    if len(calc_values) == 0:
        return STATE_UNKNOWN
    return len([v for v in calc_values if not v]) == 0


def calculate_one(states: list[State]) -> StateType:
    """Calculate whether one of the list of values is true."""
    calc_values = bool_states(states)
    if len(calc_values) == 0:
        return STATE_UNKNOWN
    return len([v for v in calc_values if v]) > 0


def calculate_none(states: list[State]) -> StateType:
    """Calculate whether none of the list of values is true."""
    calc_values = bool_states(states)
    if len(calc_values) == 0:
        return STATE_UNKNOWN
    return len([v for v in calc_values if v]) == 0


def calculate_last(states: list[State]) -> StateType:
    """Calculate the last update of the list of values."""
    calc_values = [s for s in states if s.state is not None and s.state not in [
        STATE_UNKNOWN, STATE_UNAVAILABLE]]
    if len(calc_values) == 0:
        return STATE_UNKNOWN
    return sorted(calc_values, key=lambda v: v.last_updated, reverse=True)[0].state


CALCULATE = {
    CALCULATE_MAX: calculate_max,
    CALCULATE_MEAN: calculate_mean,
    CALCULATE_MIN: calculate_min,
    CALCULATE_MEDIAN: calculate_median,
    CALCULATE_ALL: calculate_all,
    CALCULATE_ONE: calculate_one,
    CALCULATE_NONE: calculate_none,
    CALCULATE_LAST: calculate_last,
}

# Default calculation methods
DEFAULT_CALCULATION_ILLUMINANCE = CALCULATE_LAST
DEFAULT_CALCULATION_TEMPERATURE = CALCULATE_MEAN
DEFAULT_CALCULATION_HUMIDITY = CALCULATE_MAX
DEFAULT_CALCULATION_PRESENCE = CALCULATE_ALL


def get_calculation_key(
    config_options: Mapping[str, Any],
    sensor_type: SensorDeviceClass | BinarySensorDeviceClass
) -> str | None:
    """Get the configured calculation key for the sensor provided."""
    if sensor_type == SensorDeviceClass.ILLUMINANCE:
        return config_options.get(
            CONFIG_ILLUMINANCE_CALCULATION,
            DEFAULT_CALCULATION_ILLUMINANCE)

    if sensor_type == SensorDeviceClass.TEMPERATURE:
        return config_options.get(
            CONFIG_TEMPERATURE_CALCULATION,
            DEFAULT_CALCULATION_TEMPERATURE)

    if sensor_type == SensorDeviceClass.HUMIDITY:
        return config_options.get(
            CONFIG_HUMIDITY_CALCULATION,
            DEFAULT_CALCULATION_HUMIDITY)
    if sensor_type in [BinarySensorDeviceClass.MOTION, BinarySensorDeviceClass.PRESENCE, BinarySensorDeviceClass.OCCUPANCY]:
        return config_options.get(
            CONFIG_PRESENCE_CALCULATION,
            DEFAULT_CALCULATION_PRESENCE
        )
    return None


def get_calculation(
    config_options: Mapping[str, Any],
    sensor_type: SensorDeviceClass | BinarySensorDeviceClass
) -> Callable[[list[State]], StateType] | None:
    """Get the configured calculation for the sensor provided."""
    key = get_calculation_key(config_options, sensor_type)
    if key is None:
        return None
    return CALCULATE.get(key, None)
