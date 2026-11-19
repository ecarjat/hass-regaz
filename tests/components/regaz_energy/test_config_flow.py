"""Config flow tests for REGAZ integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.regaz_energy.const import CONF_UPDATE_INTERVAL_HOURS, DOMAIN
from custom_components.regaz_energy.config_flow import (
    CannotConnect,
    _async_validate_user_input,
)


@pytest.mark.asyncio
async def test_user_flow_success(
    recorder_mock, hass, enable_custom_integrations, monkeypatch
) -> None:
    async def mock_validate(user_input):
        return {"account_uuid": "acc-123", "title": "user@example.com"}

    monkeypatch.setattr(
        "custom_components.regaz_energy.config_flow._async_validate_user_input",
        mock_validate,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_USER},
    )
    assert result["type"] == FlowResultType.FORM

    with patch(
        "custom_components.regaz_energy.async_setup_entry",
        AsyncMock(return_value=True),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "user@example.com",
                CONF_PASSWORD: "secret",
            },
        )

    assert result2["type"] == FlowResultType.CREATE_ENTRY
    assert result2["title"] == "user@example.com"


@pytest.mark.asyncio
async def test_reauth_flow_updates_credentials(
    recorder_mock,
    hass,
    enable_custom_integrations,
    monkeypatch,
) -> None:
    async def mock_validate(user_input):
        return {"account_uuid": "acc-123", "title": "user@example.com"}

    monkeypatch.setattr(
        "custom_components.regaz_energy.config_flow._async_validate_user_input",
        mock_validate,
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="acc-123",
        data={
            CONF_USERNAME: "user@example.com",
            CONF_PASSWORD: "old_secret",
        },
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] == FlowResultType.FORM

    with patch.object(
        hass.config_entries,
        "async_reload",
        AsyncMock(return_value=True),
    ):
        result2 = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {
                CONF_USERNAME: "user@example.com",
                CONF_PASSWORD: "new_secret",
            },
        )

    assert result2["type"] == FlowResultType.ABORT
    assert result2["reason"] == "reauth_successful"


@pytest.mark.asyncio
async def test_options_flow_updates_interval(
    recorder_mock, hass, enable_custom_integrations
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_USERNAME: "user@example.com", CONF_PASSWORD: "secret"},
        options={CONF_UPDATE_INTERVAL_HOURS: 12},
    )
    entry.add_to_hass(hass)

    # Newer Home Assistant versions expose config_entry as a read-only property.
    with patch.object(
        OptionsFlow, "config_entry", property(OptionsFlow.config_entry.fget)
    ):
        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] == FlowResultType.FORM
        marker = next(iter(result["data_schema"].schema))
        assert marker.description["suggested_value"] == 12

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_UPDATE_INTERVAL_HOURS: 6}
        )
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_UPDATE_INTERVAL_HOURS] == 6


@pytest.mark.asyncio
async def test_login_timeout_is_a_connection_error() -> None:
    with patch(
        "custom_components.regaz_energy.config_flow.aiohttp.ClientSession"
    ), patch(
        "custom_components.regaz_energy.config_flow.RegazApiClient.async_authenticate",
        AsyncMock(side_effect=TimeoutError()),
    ):
        with pytest.raises(CannotConnect):
            await _async_validate_user_input(
                {CONF_USERNAME: "user", CONF_PASSWORD: "secret"}
            )
