"""Base auto-entity class."""

from functools import cached_property
from typing import Any, Collection, Generic, Mapping, TypeVar, cast

from homeassistant.core import (
    Event, EventStateChangedData, State, HomeAssistant, CALLBACK_TYPE,
    callback
)
from homeassistant.const import STATE_UNKNOWN, STATE_UNAVAILABLE
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers import start
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.helpers.event import async_track_state_change_event

from .calculations import get_calculation, get_calculation_key
from .auto_area import AutoArea
from .const import (CONFIG_EXCLUDED_HUMIDITY_ENTITIES, CONFIG_EXCLUDED_ILLUMINANCE_ENTITIES,
                    CONFIG_EXCLUDED_TEMPERATURE_ENTITIES, DOMAIN, LOGGER, NAME, VERSION)

_TDeviceClass = TypeVar(
    "_TDeviceClass", BinarySensorDeviceClass, SensorDeviceClass)
_TEntity = TypeVar("_TEntity", bound=Entity)
_TState = TypeVar("_TState")


class AutoEntity(Entity, Generic[_TEntity, _TDeviceClass, _TState]):
    """Set up an aggregated entity."""
    _attr_should_poll = False

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
        self._extra_attributes: dict[str, Any] = {}
        self._device_class = device_class
        self._name_prefix = name_prefix
        self._prefix = prefix
        self._check_entities: bool = False

        self.entity_ids: list[str] = []

        self._aggregated_state: _TState | str | None = None
        self._async_unsub_state_changed: CALLBACK_TYPE | None = None
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
            "entities": {state.entity_id: state.state for state in self.entity_states.values()},
            **self._extra_attributes
        }

    async def async_added_to_hass(self):
        """Start tracking sensors."""
        @callback
        def async_state_changed_listener(
            event: Event[EventStateChangedData],
        ) -> None:
            """Handle child updates."""
            self.async_set_context(event.context)
            self.async_defer_or_update_ha_state()

        self.entity_ids = self.get_sensor_entities()

        self.async_on_remove(
            async_track_state_change_event(
                self.hass, self.entity_ids, async_state_changed_listener
            )
        )
        self.async_on_remove(start.async_at_start(
            self.hass, self._update_at_start))

    async def _async_state_changed_listener(
        self, event: Event[EventStateChangedData]
    ) -> None:
        """Respond to a member state changing.

        This method must be run in the event loop.
        """
        # removed
        if self._async_unsub_state_changed is None:
            return

        self.async_set_context(event.context)

        if (new_state := event.data["new_state"]) is None:
            # The state was removed from the state machine
            self._reset_tracked_state()

        self._async_update_group_state(new_state)
        self.async_write_ha_state()

    def _reset_tracked_state(self) -> None:
        """Reset tracked state."""
        self.entity_ids = self.get_sensor_entities()
        self.entity_states = {}

        for entity_id in self.entity_ids:
            if (state := self.hass.states.get(entity_id)) is not None:
                self._see_state(state)

    @callback
    def _async_update_group_state(self, new_state: State | None = None) -> None:
        """Update group state."""
        if new_state:
            self._see_state(new_state)

        self._aggregated_state = self._get_state()

    @callback
    def _async_stop(self) -> None:
        """Unregister the group from Home Assistant.

        This method must be run in the event loop.
        """
        if self._async_unsub_state_changed:
            self._async_unsub_state_changed()
            self._async_unsub_state_changed = None

    @callback
    def _async_start_tracking(self) -> None:
        """Start tracking members.

        This method must be run in the event loop.
        """
        if self.entity_ids and self._async_unsub_state_changed is None:
            self._async_unsub_state_changed = async_track_state_change_event(
                self.hass, self.entity_ids, self._async_state_changed_listener
            )
        self._async_update_group_state()

    @callback
    def async_update_tracked_entity_ids(
        self
    ) -> None:
        """Update the member entity IDs.

        This method must be run in the event loop.
        """
        if sorted(self.entity_ids) == sorted(self.get_sensor_entities()):
            return

        self._async_stop()
        self._reset_tracked_state()
        self._async_start_tracking()
        self.async_write_ha_state()

    def _set_tracked(self, entity_ids: Collection[str] | None) -> None:
        """Tuple of entities to be tracked."""
        # tracking are the entities we want to track
        # trackable are the entities we actually watch

        if not entity_ids:
            self.tracking = ()
            self.trackable = ()
            self.single_state_type_key = None
            return

    @callback
    def async_update_group_state(self) -> None:
        """Method to update the entity."""
        self._async_update_group_state()

    @callback
    def _update_at_start(self, _: HomeAssistant) -> None:
        """Update the group state at start."""
        self._reset_tracked_state()
        self.async_update_group_state()
        self.async_write_ha_state()

    @callback
    def async_defer_or_update_ha_state(self) -> None:
        """Only update once at start."""
        if not self.hass.is_running:
            return
        self.async_update_group_state()
        self.async_write_ha_state()

    def _see_state(self, state: State | None) -> None:
        """Keep track of the state."""
        if state is None:
            return
        if state.state is not None and state.state in [
            STATE_UNKNOWN,
            STATE_UNAVAILABLE,
        ]:
            self.entity_states.pop(state.entity_id, None)
        else:
            try:
                self.entity_states[state.entity_id] = state
            except ValueError:
                self.entity_states.pop(state.entity_id, None)

    def _get_state(self) -> _TState | str | None:
        """Get the state of the sensor."""
        if len(self.entity_states.values()) == 0:
            return STATE_UNAVAILABLE

        calculate_state = get_calculation(
            self.auto_area.config_entry.options,
            self.device_class
        )
        if calculate_state is None:
            return None

        return cast(_TState | str | None, calculate_state(list(self.entity_states.values())))
