"""The REGAZ Energy integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import RegazApiClient
from .const import DEFAULT_BASE_URL, DOMAIN, PLATFORMS
from .coordinator import RegazDataUpdateCoordinator


@dataclass(slots=True)
class RegazRuntimeData:
    """Runtime objects for a config entry."""

    api: RegazApiClient
    coordinator: RegazDataUpdateCoordinator


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up integration from YAML (unused)."""
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up REGAZ Energy from a config entry."""
    session = async_get_clientsession(hass)
    api = RegazApiClient(
        session,
        username=entry.data[CONF_USERNAME],
        password=entry.data[CONF_PASSWORD],
        base_url=entry.data.get("base_url", DEFAULT_BASE_URL),
    )

    coordinator = RegazDataUpdateCoordinator(hass, entry, api)
    await coordinator.async_config_entry_first_refresh()

    runtime_data = RegazRuntimeData(api=api, coordinator=coordinator)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime_data
    entry.runtime_data = runtime_data

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
