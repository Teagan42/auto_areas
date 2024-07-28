"""🤖 Auto Areas. A custom component for Home Assistant which automates your areas."""
from __future__ import annotations
import asyncio

from homeassistant.helpers import issue_registry
from homeassistant.helpers.typing import ConfigType
from homeassistant.helpers.entity_registry import EVENT_ENTITY_REGISTRY_UPDATED, EventEntityRegistryUpdatedData
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED


from .auto_area import (
    AutoArea,
)

from .const import DOMAIN, LOGGER, ISSUE_TYPE_YAML_DETECTED

PLATFORMS: list[Platform] = [Platform.SWITCH,
                             Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialize AutoArea for this config entry."""
    hass.data.setdefault(DOMAIN, {})

    auto_area = AutoArea(hass=hass, entry=entry)
    hass.data[DOMAIN][entry.entry_id] = auto_area

    if hass.is_running:
        # Initialize immediately
        await async_init(hass, entry, auto_area)
    else:
        # Schedule initialization when HA is started and initialized
        # https://developers.home-assistant.io/docs/asyncio_working_with_async/#calling-async-functions-from-threads

        @callback
        def init(hass: HomeAssistant, entry: ConfigEntry, auto_area: AutoArea):
            asyncio.run_coroutine_threadsafe(
                async_init(hass, entry, auto_area), hass.loop
            ).result()

        hass.bus.async_listen_once(
            EVENT_HOMEASSISTANT_STARTED,
            lambda params: init(hass, entry, auto_area)
        )

    return True


async def async_init(hass: HomeAssistant, entry: ConfigEntry, auto_area: AutoArea):
    """Initialize component."""
    async def async_entity_registry_updated(event: Event[EventEntityRegistryUpdatedData]) -> None:
        """Handle entity registry updated event."""
        if event.data["action"] == "update":
            if event.data["changes"].get("area_id", None) != auto_area.area_id:
                # Event is update but no change in area, ignore event
                return
        # Create and Remove events do not attach entity data, have to check if there's any chage to entities manually
        for auto_entity in auto_area.auto_entities.values():
            current_ids = auto_entity.entity_ids
            new_ids = auto_entity.get_sensor_entities()
            if sorted(current_ids) == sorted(new_ids):
                # No change in entity ids, check next auto entity
                continue
            auto_entity.track_state_changes(new_ids)
        return

    await asyncio.sleep(5)  # wait for all area devices to be initialized
    await auto_area.async_initialize()
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    hass.bus.async_listen(EVENT_ENTITY_REGISTRY_UPDATED,
                          async_entity_registry_updated)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    LOGGER.info("🔄 Reloading entry %s", entry)

    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    # unsubscribe from changes:
    hass.data[DOMAIN][entry.entry_id].cleanup()

    # unload platforms:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)
        LOGGER.warning("Unloaded successfully %s", entry.entry_id)
    else:
        LOGGER.error("Couldn't unload config entry %s", entry.entry_id)

    return unloaded


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Check for YAML-config."""

    if config.get("auto_areas") is not None:
        LOGGER.warning(
            "Detected an existing YAML configuration. "
            + "This is not supported anymore, please remove it."
        )
        issue_registry.async_create_issue(
            hass,
            DOMAIN,
            ISSUE_TYPE_YAML_DETECTED,
            is_fixable=False,
            is_persistent=False,
            severity=issue_registry.IssueSeverity.WARNING,
            translation_key=ISSUE_TYPE_YAML_DETECTED,
        )

    return True
