"""Coordinator tests for REGAZ integration."""

from __future__ import annotations

import pytest
from datetime import timedelta

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.regaz_energy.api import RegazAuthError
from custom_components.regaz_energy.const import DOMAIN
from custom_components.regaz_energy.coordinator import RegazDataUpdateCoordinator


class SuccessApi:
    async def async_get_home_snapshot(self, *, home_uuid=None):
        return {
            "home_uuid": "home-1",
            "statistics_all": {"data": {"month": [], "year": []}},
        }


class AuthFailApi:
    async def async_get_home_snapshot(self, *, home_uuid=None):
        raise RegazAuthError("auth failed")


@pytest.mark.asyncio
async def test_coordinator_refresh_success(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    coordinator = RegazDataUpdateCoordinator(hass, entry, SuccessApi())

    await coordinator.async_refresh()

    assert coordinator.data["home_uuid"] == "home-1"
    assert coordinator.home_uuid == "home-1"


@pytest.mark.asyncio
async def test_coordinator_auth_error_triggers_reauth_exception(hass) -> None:
    entry = MockConfigEntry(domain=DOMAIN)
    coordinator = RegazDataUpdateCoordinator(hass, entry, AuthFailApi())

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


@pytest.mark.asyncio
async def test_temporary_failures_keep_last_reading_and_retry_early(hass) -> None:
    class Api:
        result = {
            "home_uuid": "home-1",
            "meter_info": {"valeurPrecise": 100},
            "statistics_all": {"data": {}},
        }

        async def async_get_home_snapshot(self, *, home_uuid=None):
            if isinstance(self.result, Exception):
                raise self.result
            return self.result

    api = Api()
    coordinator = RegazDataUpdateCoordinator(hass, MockConfigEntry(domain=DOMAIN), api)
    await coordinator.async_refresh()
    api.result = TimeoutError()
    await coordinator.async_refresh()
    assert coordinator.last_update_success
    assert coordinator.data["meter_info"]["valeurPrecise"] == 100
    assert "meter_info" in coordinator.data["failed_sections"]
    assert coordinator.update_interval == timedelta(hours=1)

    api.result = {
        "home_uuid": "home-1",
        "meter_info": {"valeurPrecise": 101},
        "statistics_all": {"data": {}},
    }
    await coordinator.async_refresh()
    assert coordinator.data["meter_info"]["valeurPrecise"] == 101
    assert coordinator.update_interval == timedelta(hours=24)


@pytest.mark.asyncio
async def test_partial_failure_keeps_only_previous_failed_section(hass) -> None:
    class Api:
        result = {
            "home_uuid": "home-1",
            "meter_info": {"valeurPrecise": 100},
            "statistics_all": {"data": {"year": []}},
        }

        async def async_get_home_snapshot(self, *, home_uuid=None):
            return self.result

    api = Api()
    coordinator = RegazDataUpdateCoordinator(hass, MockConfigEntry(domain=DOMAIN), api)
    await coordinator.async_refresh()
    api.result = {
        "home_uuid": "home-1",
        "meter_info": None,
        "statistics_all": {"data": {"year": [2026]}},
        "failed_sections": ["meter_info"],
    }
    await coordinator.async_refresh()
    assert coordinator.data["meter_info"]["valeurPrecise"] == 100
    assert coordinator.data["statistics_all"]["data"]["year"] == [2026]
    assert coordinator.update_interval == timedelta(hours=1)
