"""Sensor platform for REGAZ Energy."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
import math
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DOMAIN


@dataclass(frozen=True, kw_only=True)
class RegazSensorDescription(SensorEntityDescription):
    """Description for a REGAZ sensor."""

    value_fn: Callable[[dict[str, Any]], StateType]
    exists_fn: Callable[[dict[str, Any]], bool] = lambda _: True
    attrs_fn: Callable[[dict[str, Any]], dict[str, Any]] = lambda _: {}
    reset_fn: Callable[[dict[str, Any]], datetime | None] = lambda _: None


def _statistics_all(payload: dict[str, Any]) -> dict[str, Any]:
    return (
        payload.get("statistics_all")
        if isinstance(payload.get("statistics_all"), dict)
        else {}
    )


def _month_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = _statistics_all(payload).get("data")
    rows = data.get("month") if isinstance(data, dict) else []
    return (
        [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    )


def _year_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = _statistics_all(payload).get("data")
    rows = data.get("year") if isinstance(data, dict) else []
    return (
        [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    )


def _to_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError, OverflowError):
        return None


def _sum_field(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [_to_float(row.get(field)) for row in rows]
    if not values or any(value is None for value in values):
        return None
    return round(sum(value for value in values if value is not None), 3)


def _current_month_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    rows = _month_rows(payload)
    now = dt_util.now()
    for row in rows:
        try:
            if (
                int(row.get("year", 0)) == now.year
                and int(row.get("month", 0)) == now.month
            ):
                return row
        except (TypeError, ValueError):
            continue

    return _month_from_daily(payload, now.date())


def _month_from_daily(payload: dict[str, Any], today: date) -> dict[str, Any] | None:
    """Build a month-to-date row only from contiguous, valid daily readings."""
    daily = payload.get("statistics_day")
    rows = daily.get("data") if isinstance(daily, dict) else None
    if not isinstance(rows, list):
        return None
    days: dict[int, tuple[float, float]] = {}
    for row in rows:
        if not isinstance(row, dict):
            return None
        try:
            day = date(int(row["year"]), int(row["month"]), int(row["day"]))
        except (KeyError, TypeError, ValueError, OverflowError):
            return None
        if day.year != today.year or day.month != today.month or day > today:
            continue
        energy, volume = _to_float(row.get("value")), _to_float(row.get("volume"))
        if (
            day.day in days
            or energy is None
            or volume is None
            or energy < 0
            or volume < 0
        ):
            return None
        days[day.day] = (energy, volume)
    if not days or set(days) != set(range(1, max(days) + 1)):
        return None
    last_day = max(days)
    return {
        "year": today.year,
        "month": today.month,
        "value": sum(value[0] for value in days.values()),
        "volume": sum(value[1] for value in days.values()),
        "data_source": "daily_readings",
        "through_date": date(today.year, today.month, last_day).isoformat(),
    }


def _current_year_row(payload: dict[str, Any]) -> dict[str, Any] | None:
    rows = _year_rows(payload)
    now = dt_util.now()
    official = None
    for row in rows:
        try:
            if int(row.get("year", 0)) == now.year:
                official = row
                break
        except (TypeError, ValueError):
            continue

    months: dict[int, dict[str, Any]] = {}
    for row in _month_rows(payload):
        try:
            year, month = int(row.get("year", 0)), int(row.get("month", 0))
        except (TypeError, ValueError):
            return official
        if year != now.year or not 1 <= month <= now.month:
            continue
        if month in months:
            return official
        months[month] = row

    if now.month not in months and (current := _month_from_daily(payload, now.date())):
        months[now.month] = current
    if not months or set(months) != set(range(1, max(months) + 1)):
        return official
    if official:
        try:
            if int(official.get("monthCount", 0)) > len(months):
                return official
        except (TypeError, ValueError):
            pass
    energy = _sum_field(list(months.values()), "value")
    volume = _sum_field(list(months.values()), "volume")
    if energy is None or volume is None:
        return official
    latest = max(months)
    return {
        "year": now.year,
        "value": energy,
        "volume": volume,
        "monthCount": len(months),
        "complete": False,
        "data_source": "monthly_and_daily_readings",
        "through_month": latest,
        "through_date": months[latest].get("through_date"),
    }


def _meter(payload: dict[str, Any]) -> dict[str, Any]:
    meter = payload.get("meter_info")
    return meter if isinstance(meter, dict) else {}


def _month_attrs(payload: dict[str, Any]) -> dict[str, Any]:
    row = _current_month_row(payload)
    if not row:
        return {}
    return {
        "year": row.get("year"),
        "month": row.get("month"),
        "month_year": row.get("monthYear"),
        "value_type": row.get("valueType"),
        "data_source": row.get("data_source", "monthly_statistics"),
        "through_date": row.get("through_date"),
    }


def _year_attrs(payload: dict[str, Any]) -> dict[str, Any]:
    row = _current_year_row(payload)
    if not row:
        return {}
    return {
        "year": row.get("year"),
        "month_count": row.get("monthCount"),
        "complete": row.get("complete"),
        "data_source": row.get("data_source", "yearly_statistics"),
        "through_month": row.get("through_month"),
        "through_date": row.get("through_date"),
    }


def _period_reset(row: dict[str, Any] | None, *, monthly: bool) -> datetime | None:
    """Return the start of the period represented by a consumption row."""
    if not row:
        return None
    try:
        year = int(row["year"])
        month = int(row["month"]) if monthly else 1
        return dt_util.start_of_local_day(datetime(year, month, 1))
    except (KeyError, TypeError, ValueError):
        return None


def _meter_timestamp(payload: dict[str, Any]) -> datetime | None:
    meter_date = _meter(payload).get("date")
    if not meter_date:
        return None
    return dt_util.parse_datetime(str(meter_date))


SENSOR_DESCRIPTIONS: tuple[RegazSensorDescription, ...] = (
    RegazSensorDescription(
        key="total_energy_kwh",
        translation_key="total_energy_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        value_fn=lambda payload: _sum_field(_month_rows(payload), "value"),
    ),
    RegazSensorDescription(
        key="total_gas_volume_m3",
        translation_key="total_gas_volume_m3",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.GAS,
        value_fn=lambda payload: _sum_field(_month_rows(payload), "volume"),
    ),
    RegazSensorDescription(
        key="current_month_energy_kwh",
        translation_key="current_month_energy_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda payload: _to_float(
            (_current_month_row(payload) or {}).get("value")
        ),
        attrs_fn=_month_attrs,
        reset_fn=lambda payload: _period_reset(
            _current_month_row(payload), monthly=True
        ),
    ),
    RegazSensorDescription(
        key="current_month_volume_m3",
        translation_key="current_month_volume_m3",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda payload: _to_float(
            (_current_month_row(payload) or {}).get("volume")
        ),
        attrs_fn=_month_attrs,
        reset_fn=lambda payload: _period_reset(
            _current_month_row(payload), monthly=True
        ),
    ),
    RegazSensorDescription(
        key="current_year_energy_kwh",
        translation_key="current_year_energy_kwh",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda payload: _to_float(
            (_current_year_row(payload) or {}).get("value")
        ),
        attrs_fn=_year_attrs,
        reset_fn=lambda payload: _period_reset(
            _current_year_row(payload), monthly=False
        ),
    ),
    RegazSensorDescription(
        key="current_year_volume_m3",
        translation_key="current_year_volume_m3",
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda payload: _to_float(
            (_current_year_row(payload) or {}).get("volume")
        ),
        attrs_fn=_year_attrs,
        reset_fn=lambda payload: _period_reset(
            _current_year_row(payload), monthly=False
        ),
    ),
    RegazSensorDescription(
        key="meter_index",
        translation_key="meter_index",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda payload: _to_float(_meter(payload).get("valeurPrecise")),
        attrs_fn=lambda payload: {"reading_date": _meter(payload).get("date")},
    ),
    RegazSensorDescription(
        key="meter_last_reading",
        translation_key="meter_last_reading",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda payload: _to_float(_meter(payload).get("dindValeur")),
        attrs_fn=lambda payload: {
            "reading_date": _meter(payload).get("date"),
            "meter_serial": _meter(payload).get("cptNoSerie"),
        },
    ),
    RegazSensorDescription(
        key="meter_last_reading_at",
        translation_key="meter_last_reading_at",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_meter_timestamp,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up REGAZ sensors from config entry."""
    runtime_data = hass.data[DOMAIN][entry.entry_id]
    coordinator = runtime_data.coordinator

    async_add_entities(
        RegazEnergySensor(coordinator, entry, description)
        for description in SENSOR_DESCRIPTIONS
    )


class RegazEnergySensor(CoordinatorEntity, SensorEntity):
    """REGAZ sensor bound to coordinator payload."""

    entity_description: RegazSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator,
        entry: ConfigEntry,
        description: RegazSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"

    @property
    def available(self) -> bool:
        """Return sensor availability."""
        return bool(
            super().available
            and self.entity_description.exists_fn(self.coordinator.data or {})
            and self.native_value is not None
        )

    @property
    def native_value(self) -> StateType:
        """Return sensor value."""
        payload = self.coordinator.data or {}
        return self.entity_description.value_fn(payload)

    @property
    def last_reset(self) -> datetime | None:
        """Tell Home Assistant when a period total starts a new cycle."""
        return self.entity_description.reset_fn(self.coordinator.data or {})

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return optional attributes."""
        payload = self.coordinator.data or {}
        attrs = self.entity_description.attrs_fn(payload)
        attrs["home_uuid"] = payload.get("home_uuid")
        return attrs

    @property
    def device_info(self) -> DeviceInfo:
        """Return parent device info."""
        payload = self.coordinator.data or {}
        home_uuid = str(
            payload.get("home_uuid") or self.coordinator.home_uuid or "current"
        )
        pce = _meter(payload).get("pce") or (payload.get("pce") or {}).get("pce")
        name = f"REGAZ Home {pce}" if pce else "REGAZ Home"

        return DeviceInfo(
            identifiers={(DOMAIN, home_uuid)},
            name=name,
            manufacturer="REGAZ",
            model="Gas Consumption Point",
        )
