"""The REGAZ Energy integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.service import async_register_admin_service

from .api import RegazApiClient
from .const import DEFAULT_BASE_URL, DOMAIN, PLATFORMS
from .coordinator import RegazDataUpdateCoordinator
from .statistics import async_import_daily_history


@dataclass(slots=True)
class RegazRuntimeData:
    """Runtime objects for a config entry."""

    api: RegazApiClient
    coordinator: RegazDataUpdateCoordinator
    history_lock: asyncio.Lock = field(default_factory=asyncio.Lock)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Register the explicit historical import action."""

    async def import_history(call: ServiceCall) -> None:
        entry_id = call.data["entry_id"]
        runtime = hass.data.get(DOMAIN, {}).get(entry_id)
        if runtime is None or not runtime.coordinator.home_uuid:
            raise HomeAssistantError("REGAZ entry is not loaded")
        try:
            start = date.fromisoformat(call.data["start_date"])
            end = date.fromisoformat(call.data["end_date"])
        except ValueError as err:
            raise HomeAssistantError("Dates must use YYYY-MM-DD") from err
        async with runtime.history_lock:
            await async_import_daily_history(
                hass, entry_id, runtime.api, runtime.coordinator.home_uuid, start, end
            )

    async_register_admin_service(
        hass,
        DOMAIN,
        "import_daily_history",
        import_history,
        schema=vol.Schema(
            {
                vol.Required("entry_id"): str,
                vol.Required("start_date"): str,
                vol.Required("end_date"): str,
            }
        ),
    )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up REGAZ Energy from a config entry."""
    # Authentication is cookie-based; isolate each account from the shared jar.
    session = async_create_clientsession(hass)
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
