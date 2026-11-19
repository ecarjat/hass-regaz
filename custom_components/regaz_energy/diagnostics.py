"""Diagnostics support for REGAZ Energy."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant

from .const import CONF_UPDATE_INTERVAL_HOURS, DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    coordinator_data = runtime_data.coordinator.data if runtime_data.coordinator else {}

    data = coordinator_data or {}
    meter = data.get("meter_info") or {}
    stats = (data.get("statistics_all") or {}).get("data") or {}
    return {
        "entry_data": {
            key: "**REDACTED**"
            for key in (CONF_USERNAME, CONF_PASSWORD)
            if key in entry.data
        },
        "entry_options": {
            key: entry.options[key]
            for key in (CONF_UPDATE_INTERVAL_HOURS,)
            if key in entry.options
        },
        "coordinator_data": {
            "fetched_at": data.get("fetched_at"),
            "failed_sections": data.get("failed_sections", []),
            "meter_reading_date": meter.get("date"),
            "month_count": len(stats.get("month") or []),
            "year_count": len(stats.get("year") or []),
        },
    }
