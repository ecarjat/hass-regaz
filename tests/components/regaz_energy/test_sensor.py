"""Sensor mapping tests for REGAZ integration."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import UnitOfEnergy
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.regaz_energy.const import DOMAIN
from custom_components.regaz_energy.coordinator import RegazDataUpdateCoordinator
from custom_components.regaz_energy.sensor import (
    SENSOR_DESCRIPTIONS,
    RegazEnergySensor,
    _current_month_row,
    _current_year_row,
)


class ApiStub:
    async def async_get_home_snapshot(self, *, home_uuid=None):
        return {
            "home_uuid": "home-1",
            "pce": {"pce": 83513},
            "meter_info": {
                "valeurPrecise": 1295,
                "dindValeur": 1295,
                "date": "2026-03-04T00:00:00+01:00",
                "cptNoSerie": "4625B111986231",
            },
            "statistics_all": {
                "data": {
                    "month": [
                        {"year": 2026, "month": "01", "value": 5353, "volume": 474.1},
                        {
                            "year": 2026,
                            "month": "02",
                            "value": 2190.94073,
                            "volume": 194.1,
                        },
                    ],
                    "year": [
                        {
                            "year": 2026,
                            "value": 7544.83749,
                            "volume": 660.85,
                            "monthCount": 2,
                        }
                    ],
                }
            },
        }


@pytest.mark.asyncio
async def test_total_energy_sensor_metadata_and_value(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    coordinator = RegazDataUpdateCoordinator(hass, entry, ApiStub())
    await coordinator.async_refresh()

    description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "total_energy_kwh"
    )
    entity = RegazEnergySensor(coordinator, entry, description)

    assert entity.native_value == pytest.approx(7543.941, abs=0.001)
    assert entity.entity_description.device_class == SensorDeviceClass.ENERGY
    assert entity.entity_description.state_class is None
    assert (
        entity.entity_description.native_unit_of_measurement
        == UnitOfEnergy.KILO_WATT_HOUR
    )


@pytest.mark.asyncio
async def test_meter_sensor_is_diagnostic_and_has_value(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    coordinator = RegazDataUpdateCoordinator(hass, entry, ApiStub())
    await coordinator.async_refresh()

    description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "meter_last_reading"
    )
    entity = RegazEnergySensor(coordinator, entry, description)

    assert entity.native_value == pytest.approx(1295.0)
    assert entity.entity_description.entity_category is not None


def test_current_period_energy_and_gas_use_total_state_class() -> None:
    current_month_energy = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "current_month_energy_kwh"
    )
    current_month_volume = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "current_month_volume_m3"
    )
    current_year_energy = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "current_year_energy_kwh"
    )
    current_year_volume = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "current_year_volume_m3"
    )

    assert current_month_energy.state_class == SensorStateClass.TOTAL
    assert current_month_volume.state_class == SensorStateClass.TOTAL
    assert current_year_energy.state_class == SensorStateClass.TOTAL
    assert current_year_volume.state_class == SensorStateClass.TOTAL


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("key", "expected_month"),
    [
        ("current_month_energy_kwh", 10),
        ("current_month_volume_m3", 10),
        ("current_year_energy_kwh", 1),
        ("current_year_volume_m3", 1),
    ],
)
async def test_period_reset_tracks_data_period(hass, key, expected_month) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    coordinator = RegazDataUpdateCoordinator(hass, entry, ApiStub())
    await coordinator.async_refresh()
    description = next(item for item in SENSOR_DESCRIPTIONS if item.key == key)
    entity = RegazEnergySensor(coordinator, entry, description)

    coordinator.data["statistics_all"]["data"] = {
        "month": [{"year": 2026, "month": "10", "value": 773, "volume": 69}],
        "year": [{"year": 2026, "value": 1000, "volume": 90}],
    }
    with patch(
        "custom_components.regaz_energy.sensor.dt_util.now",
        return_value=datetime(2026, 10, 15),
    ):
        reset = entity.last_reset
    assert reset is not None
    assert (reset.year, reset.month, reset.day) == (2026, expected_month, 1)
    assert reset.tzinfo is not None

    coordinator.data["statistics_all"]["data"]["month"].append(
        {"year": 2026, "month": "11", "value": 20, "volume": 2}
    )
    coordinator.data["statistics_all"]["data"]["year"].append(
        {"year": 2027, "value": 20, "volume": 2}
    )
    next_time = (
        datetime(2026, 11, 15) if expected_month == 10 else datetime(2027, 1, 15)
    )
    with patch(
        "custom_components.regaz_energy.sensor.dt_util.now", return_value=next_time
    ):
        next_reset = entity.last_reset
    assert next_reset is not None
    assert next_reset > reset
    if expected_month == 10:
        assert (next_reset.year, next_reset.month) == (2026, 11)
    else:
        assert (next_reset.year, next_reset.month) == (2027, 1)


@pytest.mark.asyncio
async def test_current_month_does_not_show_previous_month(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    coordinator = RegazDataUpdateCoordinator(hass, entry, ApiStub())
    await coordinator.async_refresh()
    description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "current_month_volume_m3"
    )
    entity = RegazEnergySensor(coordinator, entry, description)
    with patch(
        "custom_components.regaz_energy.sensor.dt_util.now",
        return_value=datetime(2026, 3, 1),
    ):
        assert entity.native_value is None
        assert entity.last_reset is None


@pytest.mark.asyncio
async def test_incomplete_history_is_not_reported_as_a_total(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    coordinator = RegazDataUpdateCoordinator(hass, entry, ApiStub())
    await coordinator.async_refresh()
    description = next(
        item for item in SENSOR_DESCRIPTIONS if item.key == "total_energy_kwh"
    )
    entity = RegazEnergySensor(coordinator, entry, description)
    coordinator.data["statistics_all"]["data"]["month"][0]["value"] = "NaN"
    assert entity.native_value is None


def test_current_periods_use_daily_and_monthly_data_when_provider_totals_lag() -> None:
    monthly = [
        {"year": 2026, "month": str(month), "value": 100, "volume": 10}
        for month in range(1, 11)
    ]
    daily = [
        {"year": 2026, "month": "11", "day": str(day), "value": 5, "volume": 0.5}
        for day in range(1, 4)
    ]
    payload = {
        "statistics_all": {"data": {"month": monthly, "year": [{"year": 2025}]}},
        "statistics_day": {"data": daily},
    }
    with patch(
        "custom_components.regaz_energy.sensor.dt_util.now",
        return_value=datetime(2026, 11, 19),
    ):
        month, year = _current_month_row(payload), _current_year_row(payload)
        assert month["value"] == 15
        assert month["volume"] == 1.5
        assert month["through_date"] == "2026-11-03"
        assert year["value"] == 1015
        assert year["volume"] == 101.5
        assert year["through_date"] == "2026-11-03"

        # Once REGAZ supplies the monthly total, it replaces the daily fallback.
        monthly.append({"year": 2026, "month": "11", "value": 55, "volume": 5.5})
        assert _current_month_row(payload)["value"] == 55
        assert _current_year_row(payload)["value"] == 1055


def test_missing_daily_or_monthly_periods_are_not_invented() -> None:
    payload = {
        "statistics_all": {
            "data": {
                "month": [{"year": 2026, "month": "2", "value": 10, "volume": 1}],
                "year": [],
            }
        },
        "statistics_day": {
            "data": [
                {"year": 2026, "month": "11", "day": "2", "value": 10, "volume": 1}
            ]
        },
    }
    with patch(
        "custom_components.regaz_energy.sensor.dt_util.now",
        return_value=datetime(2026, 11, 19),
    ):
        assert _current_month_row(payload) is None
        assert _current_year_row(payload) is None
