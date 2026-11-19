"""Tests for the REGAZ reading problem indicator."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.regaz_energy.binary_sensor import RegazReadingProblem
from custom_components.regaz_energy.const import DOMAIN
from custom_components.regaz_energy.coordinator import RegazDataUpdateCoordinator


@pytest.mark.asyncio
async def test_problem_indicator_reports_stale_and_failed_readings(hass):
    entry = MockConfigEntry(domain=DOMAIN)
    coordinator = RegazDataUpdateCoordinator(hass, entry, object())
    entity = RegazReadingProblem(coordinator, entry)
    coordinator.data = {
        "meter_info": {"date": "2026-11-18T00:00:00+00:00"},
        "failed_sections": [],
    }
    with patch(
        "custom_components.regaz_energy.binary_sensor.dt_util.utcnow",
        return_value=datetime(2026, 11, 19, tzinfo=timezone.utc),
    ):
        assert entity.is_on is False
        coordinator.data["failed_sections"] = ["meter_info"]
        assert entity.is_on is True
        coordinator.data["failed_sections"] = []
        coordinator.data["meter_info"]["date"] = "2026-11-12T00:00:00+00:00"
        assert entity.is_on is True
        coordinator.data["meter_info"]["date"] = None
        assert entity.is_on is True
