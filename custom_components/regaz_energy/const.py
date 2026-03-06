"""Constants for the REGAZ Energy integration."""

from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "regaz_energy"
PLATFORMS = [Platform.SENSOR]

DEFAULT_BASE_URL = "https://monespace.regaz.fr"
DEFAULT_UPDATE_INTERVAL_HOURS = 24
CONF_UPDATE_INTERVAL_HOURS = "update_interval_hours"

REDACT_KEYS = {
    "password",
    "jwt_hp",
    "jwt_s",
    "authorization",
    "cookie",
    "set-cookie",
    "email",
    "telephone",
    "address",
    "clientId",
    "pce",
    "cptNoSerie",
    "chronoExt",
    "uuid",
}
