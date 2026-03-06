"""Coordinator tests for REGAZ integration."""

from __future__ import annotations

import pytest

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
