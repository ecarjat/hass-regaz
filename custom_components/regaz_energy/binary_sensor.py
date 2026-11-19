"""Data-quality indicator for REGAZ meter readings."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the reading freshness indicator."""
    coordinator = hass.data[DOMAIN][entry.entry_id].coordinator
    async_add_entities([RegazReadingProblem(coordinator, entry)])


class RegazReadingProblem(CoordinatorEntity, BinarySensorEntity):
    """Report failed polls or meter readings more than three days old."""

    _attr_has_entity_name = True
    _attr_translation_key = "reading_problem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_reading_problem"

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data or {}
        if data.get("failed_sections"):
            return True
        meter = data.get("meter_info") or {}
        value = meter.get("date")
        reading = dt_util.parse_datetime(str(value)) if value else None
        if reading is None:
            return True
        if reading.tzinfo is None:
            reading = dt_util.as_local(reading)
        return dt_util.utcnow() - reading > timedelta(days=3)

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data or {}
        return {
            "reading_date": (data.get("meter_info") or {}).get("date"),
            "last_successful_fetch": data.get("fetched_at"),
            "failed_sections": data.get("failed_sections", []),
        }

    @property
    def device_info(self):
        data = self.coordinator.data or {}
        home_uuid = str(
            data.get("home_uuid") or self.coordinator.home_uuid or "current"
        )
        return {"identifiers": {(DOMAIN, home_uuid)}}
