"""Core area functionality."""
from __future__ import annotations
from ast import TypeVar
from typing import Any, Sequence, Union
from homeassistant.core import HomeAssistant
from homeassistant.helpers.area_registry import async_get as async_get_area_registry
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry
from homeassistant.helpers.issue_registry import async_create_issue, IssueSeverity
from homeassistant.config_entries import ConfigEntry

from homeassistant.helpers.area_registry import AreaEntry
from homeassistant.helpers.entity_registry import RegistryEntry

from .auto_lights import AutoLights
from .ha_helpers import get_all_entities, is_valid_entity
from .const import (
    CONFIG_LIGHT_CONTROL,
    CONFIG_AREA,
    DOMAIN,
    LOGGER,
    RELEVANT_DOMAINS,
)


class AutoAreasError(Exception):
    """Exception to indicate a general API error."""


def flatten_ids(entity_ids: Sequence[Union[str, list[str]]]) -> list[str]:
    """Flatten a list of lists."""
    return [item for sublist in entity_ids for item in (flatten_ids(sublist) if isinstance(sublist, list) else [sublist])]


class AutoArea:
    """Class to manage fetching data from the API."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        LOGGER.info('🤖 Auto Area "%s" (%s)', entry.title, entry.options)
        self.hass = hass
        self.config_entry = entry

        self.area_registry = async_get_area_registry(self.hass)
        self.device_registry = async_get_device_registry(self.hass)
        self.entity_registry = async_get_entity_registry(self.hass)

        self.area_id: str | None = entry.data.get(CONFIG_AREA, None)
        self.area: AreaEntry | None = self.area_registry.async_get_area(
            self.area_id or "")
        self.auto_lights = None
        self.auto_entities: dict[str, Any] = {}
        if self.area_id is None or self.area is None:
            async_create_issue(
                hass,
                DOMAIN,
                f"invalid_area_config_{entry.entry_id}",
                is_fixable=True,
                severity=IssueSeverity.ERROR,
                translation_key="invalid_area_config",
                data={
                    "entry_id": entry.entry_id
                }
            )

    async def async_initialize(self):
        """Subscribe to area changes and reload if necessary."""
        LOGGER.info(
            "%s: Initializing after HA start",
            self.area_name
        )

        if not self.config_entry.options.get(CONFIG_LIGHT_CONTROL, True):
            return
        self.auto_lights = AutoLights(self)
        await self.auto_lights.initialize()

    @property
    def tracked_entity_ids(self) -> list[str]:
        """Tracked entity ids."""
        return flatten_ids([auto_entity.entity_ids for auto_entity in self.auto_entities.values()])

    def cleanup(self):
        """Deinitialize this area."""
        LOGGER.debug(
            "%s: Disabling area control",
            self.area_name
        )
        if self.auto_lights:
            self.auto_lights.cleanup()

    def get_valid_entities(self) -> list[RegistryEntry]:
        """Return all valid and relevant entities for this area."""
        entities = [
            entity
            for entity in get_all_entities(
                self.entity_registry,
                self.device_registry,
                self.area_id or "",
                RELEVANT_DOMAINS,
            )
            if is_valid_entity(self.hass, entity)
        ]
        return entities

    @property
    def area_name(self) -> str:
        """Return area name or fallback."""
        return self.area.name if self.area is not None else "unknown"
