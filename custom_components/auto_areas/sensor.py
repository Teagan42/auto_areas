"""Sensor platform for auto_areas."""

from functools import cached_property
from typing import Any, override

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.components.sensor import SensorEntity
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import LIGHT_LUX, PERCENTAGE

from .auto_entity import AutoEntity

from .auto_area import AutoArea
from .const import DOMAIN, HUMIDITY_SENSOR_ENTITY_PREFIX, HUMIDITY_SENSOR_PREFIX, ILLUMINANCE_SENSOR_ENTITY_PREFIX, ILLUMINANCE_SENSOR_PREFIX, TEMPERATURE_SENSOR_ENTITY_PREFIX, TEMPERATURE_SENSOR_PREFIX


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback):
    """Set up the sensor platform."""
    auto_area: AutoArea = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([
        IlluminanceSensor(hass, auto_area),
        TemperatureSensor(hass, auto_area),
        HumiditySensor(hass, auto_area)
    ])


class AutoSensorEntity(AutoEntity[SensorEntity, SensorDeviceClass, float], SensorEntity):
    """Set up aggregated sensor."""

    @override
    def _get_state(self) -> float | str | None:
        self._attr_native_value = super()._get_state()
        return self._attr_native_value


class IlluminanceSensor(
    AutoSensorEntity
):
    """Set up aggregated illuminance sensor."""

    def __init__(self, hass, auto_area: AutoArea) -> None:
        """Initialize sensor."""
        super().__init__(
            hass,
            auto_area,
            SensorDeviceClass.ILLUMINANCE,
            ILLUMINANCE_SENSOR_PREFIX,
            ILLUMINANCE_SENSOR_ENTITY_PREFIX
        )

    @cached_property
    @override
    def native_unit_of_measurement(self) -> str | None:
        """Return unit of measurement."""
        return LIGHT_LUX


class TemperatureSensor(AutoSensorEntity):
    """Set up aggregated temperature sensor."""

    def __init__(self, hass, auto_area: AutoArea) -> None:
        """Initialize sensor."""
        super().__init__(
            hass,
            auto_area,
            SensorDeviceClass.TEMPERATURE,
            TEMPERATURE_SENSOR_PREFIX,
            TEMPERATURE_SENSOR_ENTITY_PREFIX
        )

    @cached_property
    @override
    def native_unit_of_measurement(self) -> str | None:
        """Return unit of measurement."""
        return self.hass.config.units.temperature_unit


class HumiditySensor(AutoSensorEntity):
    """Set up aggregated humidity sensor."""

    def __init__(self, hass, auto_area: AutoArea) -> None:
        """Initialize sensor."""
        super().__init__(
            hass,
            auto_area,
            SensorDeviceClass.HUMIDITY,
            HUMIDITY_SENSOR_PREFIX,
            HUMIDITY_SENSOR_ENTITY_PREFIX
        )

    @cached_property
    @override
    def native_unit_of_measurement(self) -> str | None:
        """Return unit of measurement."""
        return PERCENTAGE
