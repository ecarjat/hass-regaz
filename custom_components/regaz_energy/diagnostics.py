"""Diagnostics support for REGAZ Energy."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, REDACT_KEYS


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    coordinator_data = runtime_data.coordinator.data if runtime_data.coordinator else {}

    return {
        "entry_data": async_redact_data(dict(entry.data), REDACT_KEYS),
        "entry_options": async_redact_data(dict(entry.options), REDACT_KEYS),
        "coordinator_data": async_redact_data(coordinator_data or {}, REDACT_KEYS),
    }
