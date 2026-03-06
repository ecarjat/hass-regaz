"""Diagnostics tests for REGAZ integration."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.regaz_energy.diagnostics import async_get_config_entry_diagnostics
from custom_components.regaz_energy.const import DOMAIN


@pytest.mark.asyncio
async def test_diagnostics_redacts_sensitive_values(hass) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "super_secret",
        },
    )
    entry.add_to_hass(hass)

    runtime_data = SimpleNamespace(
        coordinator=SimpleNamespace(
            data={
                "jwt_s": "token",
                "account": {"email": "user@example.com"},
                "meter_info": {"cptNoSerie": "4625B111986231"},
            }
        )
    )

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime_data

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    assert diagnostics["entry_data"][CONF_PASSWORD] == "**REDACTED**"
    assert diagnostics["coordinator_data"]["jwt_s"] == "**REDACTED**"
    assert diagnostics["coordinator_data"]["account"]["email"] == "**REDACTED**"
