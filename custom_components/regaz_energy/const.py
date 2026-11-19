"""Constants for the REGAZ Energy integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "regaz_energy"
PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]

DEFAULT_BASE_URL = "https://monespace.regaz.fr"
DEFAULT_UPDATE_INTERVAL_HOURS = 24
CONF_UPDATE_INTERVAL_HOURS = "update_interval_hours"
