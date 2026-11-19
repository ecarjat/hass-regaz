"""Test setup and entity registration together."""

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.regaz_energy.const import DOMAIN


@pytest.mark.asyncio
async def test_setup_registers_meter_health_and_import_action(
    recorder_mock, hass, enable_custom_integrations
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "test@example.com", CONF_PASSWORD: "secret"},
    )
    entry.add_to_hass(hass)
    snapshot = {
        "home_uuid": "home-1",
        "pce": {"pce": "123"},
        "meter_info": {"valeurPrecise": 1815, "date": "2026-11-12T00:00:00+01:00"},
        "statistics_all": {"data": {"month": [], "year": []}},
        "failed_sections": [],
    }
    with patch(
        "custom_components.regaz_energy.async_create_clientsession",
        return_value=object(),
    ), patch(
        "custom_components.regaz_energy.api.RegazApiClient.async_get_home_snapshot",
        AsyncMock(return_value=snapshot),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        states = hass.states.async_all()
        meter = next(
            state
            for state in states
            if state.attributes.get("device_class") == "gas" and state.state == "1815.0"
        )
        assert meter.attributes["state_class"] == "total_increasing"
        assert any(
            state.domain == "binary_sensor"
            and state.attributes.get("device_class") == "problem"
            for state in states
        )
        assert hass.services.has_service(DOMAIN, "import_daily_history")
        with patch(
            "custom_components.regaz_energy.async_import_daily_history",
            new_callable=AsyncMock,
        ) as importer:
            await hass.services.async_call(
                DOMAIN,
                "import_daily_history",
                {
                    "entry_id": entry.entry_id,
                    "start_date": "2025-10-01",
                    "end_date": "2025-10-31",
                },
                blocking=True,
            )
            importer.assert_awaited_once()
        assert await hass.config_entries.async_unload(entry.entry_id)
