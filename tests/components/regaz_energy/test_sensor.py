"""Sensor mapping tests for REGAZ integration."""

from __future__ import annotations

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
                        {"year": 2026, "month": "02", "value": 2190.94073, "volume": 194.1},
                    ],
                    "year": [
                        {"year": 2026, "value": 7544.83749, "volume": 660.85, "monthCount": 2}
                    ],
                }
            },
        }


@pytest.mark.asyncio
async def test_total_energy_sensor_metadata_and_value(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    coordinator = RegazDataUpdateCoordinator(hass, entry, ApiStub())
    await coordinator.async_refresh()

    description = next(item for item in SENSOR_DESCRIPTIONS if item.key == "total_energy_kwh")
    entity = RegazEnergySensor(coordinator, entry, description)

    assert entity.native_value == pytest.approx(7543.941, abs=0.001)
    assert entity.entity_description.device_class == SensorDeviceClass.ENERGY
    assert entity.entity_description.state_class == SensorStateClass.TOTAL_INCREASING
    assert entity.entity_description.native_unit_of_measurement == UnitOfEnergy.KILO_WATT_HOUR


@pytest.mark.asyncio
async def test_meter_sensor_is_diagnostic_and_has_value(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    coordinator = RegazDataUpdateCoordinator(hass, entry, ApiStub())
    await coordinator.async_refresh()

    description = next(item for item in SENSOR_DESCRIPTIONS if item.key == "meter_last_reading")
    entity = RegazEnergySensor(coordinator, entry, description)

    assert entity.native_value == pytest.approx(1295.0)
    assert entity.entity_description.entity_category is not None
