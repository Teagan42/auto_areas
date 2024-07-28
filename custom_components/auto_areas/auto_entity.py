"""Base auto-entity class."""

from functools import cached_property
from typing import Any, Generic, Mapping, TypeVar, cast

from homeassistant.core import Event, EventStateChangedData, State, HomeAssistant, CALLBACK_TYPE
from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import StateType
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.helpers.event import async_track_state_change_event

from .calculations import get_calculation, get_calculation_key
from .auto_area import AutoArea
from .const import (CONFIG_EXCLUDED_HUMIDITY_ENTITIES, CONFIG_EXCLUDED_ILLUMINANCE_ENTITIES,
                    CONFIG_EXCLUDED_TEMPERATURE_ENTITIES, DOMAIN, LOGGER, NAME, VERSION)

_TDeviceClass = TypeVar(
    "_TDeviceClass", BinarySensorDeviceClass, SensorDeviceClass)
_TEntity = TypeVar("_TEntity", bound=Entity)


class AutoEntity(Entity, Generic[_TEntity, _TDeviceClass]):
    """Set up an aggregated entity."""

    def __init__(self,
                 hass: HomeAssistant,
                 auto_area: AutoArea,
                 device_class: _TDeviceClass,
                 name_prefix: str,
                 prefix: str
                 ) -> None:
        """Initialize sensor."""
        super().__init__()
        self.hass = hass
        self.auto_area = auto_area
        auto_area.auto_entities[device_class] = self
        self.entity_states: dict[str, State] = {}
        self._device_class = device_class
        self._name_prefix = name_prefix
        self._prefix = prefix

        self.entity_ids: list[str] = self.get_sensor_entities()

        self._aggregated_state: StateType = None
        self.unsubscribe: CALLBACK_TYPE | None = None
        LOGGER.info(
            "%s: Initialized %s sensor",
            self.auto_area.area_name,
            self.device_class
        )

    @property
    def _excluded_entities(self) -> list[str]:
        """Retrieve excluded entities."""
        if self._device_class == SensorDeviceClass.TEMPERATURE:
            return self.auto_area.config_entry.options.get(CONFIG_EXCLUDED_TEMPERATURE_ENTITIES, [])
        if self._device_class == SensorDeviceClass.HUMIDITY:
            return self.auto_area.config_entry.options.get(CONFIG_EXCLUDED_HUMIDITY_ENTITIES, [])
        if self._device_class == SensorDeviceClass.ILLUMINANCE:
            return self.auto_area.config_entry.options.get(CONFIG_EXCLUDED_ILLUMINANCE_ENTITIES, [])
        return []

    def get_sensor_entities(self) -> list[str]:
        """Retrieve all relevant entity ids for this sensor."""
        return [
            entity.entity_id
            for entity in self.auto_area.get_valid_entities()
            if (entity.device_class == self.device_class
                or entity.original_device_class == self.device_class) and entity.entity_id not in self._excluded_entities
        ]

    @cached_property
    def name(self):
        """Name of this entity."""
        return f"{self._name_prefix}{self.auto_area.area_name}"

    @cached_property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return f"{self.auto_area.config_entry.entry_id}_aggregated_{self.device_class}"

    @cached_property
    def device_class(self) -> _TDeviceClass:
        """Return device class."""
        return cast(_TDeviceClass, self._device_class)

    @cached_property
    def device_info(self) -> DeviceInfo:
        """Information about this device."""
        return {
            "identifiers": {(DOMAIN, self.auto_area.config_entry.entry_id)},
            "name": NAME,
            "model": VERSION,
            "manufacturer": NAME,
            "suggested_area": self.auto_area.area_name,
        }

    @cached_property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return entity specific state attributes.

        Implemented by platform classes. Convention for attribute names
        is lowercase snake_case.
        """
        return {
            "calculation": get_calculation_key(
                self.auto_area.config_entry.options,
                self.device_class
            ),
            "entities": {k: v.state for k, v in self.entity_states.items()}
        }

    async def async_added_to_hass(self):
        """Start tracking sensors."""
        LOGGER.debug(
            "%s: %s sensor entities: %s",
            self.auto_area.area_name,
            self.device_class,
            self.entity_ids,
        )

        # Get all current states
        for entity_id in self.entity_ids:
            state = self.hass.states.get(entity_id)
            if state is not None:
                try:
                    self.entity_states[entity_id] = state
                except ValueError:
                    LOGGER.warning(
                        "No initial state available for %s", entity_id
                    )

        self._aggregated_state = self._get_state()
        self.schedule_update_ha_state()

        # Subscribe to state changes
        self.track_state_changes()

    def track_state_changes(self, entity_ids: list[str] | None = None) -> None:
        """Track entity state changes."""
        if self.unsubscribe:
            try:
                self.unsubscribe()
            except ValueError:
                pass
        self.unsubscribe = None

        self.entity_ids = entity_ids or self.entity_ids
        self.unsubscribe = async_track_state_change_event(
            self.hass,
            self.entity_ids,
            self._handle_state_change,
        )
        entity_state_keys = self.entity_states.keys()
        for entity_id in entity_state_keys:
            # Remove any states no longer tracked
            if entity_id in self.entity_ids:
                continue
            self.entity_states.pop(entity_id, None)

    async def _handle_state_change(self, event: Event[EventStateChangedData]):
        """Handle state change of any tracked illuminance sensors."""
        to_state = event.data.get("new_state")
        if to_state is None:
            return

        if to_state.state in [
            STATE_UNKNOWN,
            STATE_UNAVAILABLE,
        ]:
            self.entity_states.pop(to_state.entity_id, None)
        else:
            try:
                to_state.state = float(to_state.state)  # type: ignore
                self.entity_states[to_state.entity_id] = to_state
            except ValueError:
                self.entity_states.pop(to_state.entity_id, None)

        self._aggregated_state = self._get_state()

        LOGGER.debug(
            "%s: got state %s, %d entities",
            self.device_class,
            str(self.state),
            len(self.entity_states.values())
        )

        self.async_schedule_update_ha_state()

    async def async_will_remove_from_hass(self) -> None:
        """Clean up event listeners."""
        if self.unsubscribe:
            try:
                self.unsubscribe()
            except ValueError:
                pass
        self.unsubscribe = None

    def _get_state(self) -> StateType | None:
        """Get the state of the sensor."""
        if len(self.entity_ids) == 0:
            return STATE_UNAVAILABLE

        calculate_state = get_calculation(
            self.auto_area.config_entry.options,
            self.device_class
        )
        if calculate_state is None:
            LOGGER.error(
                "%s: %s unable to get state calculation method",
                self.auto_area.area_name,
                self.device_class
            )
            return None

        return calculate_state(list(self.entity_states.values()))
