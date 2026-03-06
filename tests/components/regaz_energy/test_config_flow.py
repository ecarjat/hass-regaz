"""Config flow tests for REGAZ integration."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.regaz_energy.const import DOMAIN


@pytest.mark.asyncio
async def test_user_flow_success(hass, enable_custom_integrations, monkeypatch) -> None:
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
