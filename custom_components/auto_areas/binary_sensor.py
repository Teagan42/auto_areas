"""Binary sensor platform for auto_areas."""

from __future__ import annotations

from functools import cached_property
from typing import Literal, override
from homeassistant.core import Event, EventStateChangedData
from homeassistant.const import STATE_ON, STATE_OFF
from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event

from .ha_helpers import all_states_are_off
from .auto_entity import AutoEntity
from .auto_area import AutoArea
from .calculations import bool_states
from .const import (
    DOMAIN,
    LOGGER,
    PRESENCE_BINARY_SENSOR_DEVICE_CLASSES,
    PRESENCE_BINARY_SENSOR_ENTITY_PREFIX,
    PRESENCE_BINARY_SENSOR_PREFIX,
    PRESENCE_ON_STATES,
)


async def async_setup_entry(hass, entry, async_add_entities: AddEntitiesCallback):
    """Set up the binary_sensor platform."""
    auto_area: AutoArea = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PresenceBinarySensor(hass, auto_area)])


class PresenceBinarySensor(
    AutoEntity[BinarySensorEntity,
               BinarySensorDeviceClass, bool], BinarySensorEntity
):
    """Set up aggregated presence binary sensor."""

    def __init__(self, hass, auto_area: AutoArea) -> None:
        """Initialize presence binary sensor."""
        super().__init__(
            hass,
            auto_area,
            BinarySensorDeviceClass.OCCUPANCY,
            PRESENCE_BINARY_SENSOR_PREFIX,
            PRESENCE_BINARY_SENSOR_ENTITY_PREFIX
        )
        LOGGER.debug("Presence entities %s", self.entity_ids)

    @cached_property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        if not isinstance(self._aggregated_state, bool):
            return None

        return self._aggregated_state

    @cached_property
    def state(self) -> Literal["on", "off"] | None:  # type: ignore
        """Return the state of the binary sensor."""
        if (is_on := self.is_on) is None:
            return None
        return STATE_ON if is_on else STATE_OFF

    @override
    def get_sensor_entities(self) -> list[str]:
        """Retrieve all relevant presence entities."""
        return [
            entity.entity_id
            for entity in self.auto_area.get_valid_entities()
            if entity.device_class in PRESENCE_BINARY_SENSOR_DEVICE_CLASSES
            or entity.original_device_class in PRESENCE_BINARY_SENSOR_DEVICE_CLASSES
        ]

    @override
    def _get_state(self) -> bool | str | None:
        self._attr_native_value = super()._get_state()
        bools = bool_states(list(self.entity_states.values()))
        self._extra_attributes = {
            "num_false": len([b for b in bools if not b]),
            "num_true": len([b for b in bools if b])
        }
        return self._attr_native_value
