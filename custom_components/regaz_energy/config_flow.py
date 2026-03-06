"""Config flow for the REGAZ Energy integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .api import RegazApiClient, RegazApiError, RegazAuthError
from .const import (
    CONF_UPDATE_INTERVAL_HOURS,
    DEFAULT_BASE_URL,
    DEFAULT_UPDATE_INTERVAL_HOURS,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""


class InvalidAuth(Exception):
    """Error to indicate there is invalid auth."""


async def _async_validate_user_input(user_input: Mapping[str, str]) -> dict[str, str]:
    """Validate user input against REGAZ endpoints."""
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar()) as session:
        api = RegazApiClient(
            session,
            username=user_input[CONF_USERNAME],
            password=user_input[CONF_PASSWORD],
            base_url=DEFAULT_BASE_URL,
        )

        try:
            await api.async_authenticate(force=True)
            me = await api.async_get_me(extra=True)
        except RegazAuthError as err:
            raise InvalidAuth from err
        except RegazApiError as err:
            raise CannotConnect from err
        except aiohttp.ClientError as err:
            raise CannotConnect from err

    account_uuid = str(me.get("uuid") or user_input[CONF_USERNAME])
    title = str(me.get("email") or user_input[CONF_USERNAME])
    return {"account_uuid": account_uuid, "title": title}


class RegazEnergyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for REGAZ Energy."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Handle user initiated flow."""
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await _async_validate_user_input(user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pragma: no cover - defensive fallback
                _LOGGER.exception("Unexpected exception in async_step_user")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["account_uuid"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=info["title"],
                    data={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Handle reauth flow start."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self,
        user_input: dict[str, Any] | None = None,
    ) -> FlowResult:
        """Confirm reauth flow."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            try:
                info = await _async_validate_user_input(user_input)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:  # pragma: no cover - defensive fallback
                _LOGGER.exception("Unexpected exception in async_step_reauth_confirm")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(info["account_uuid"])
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        schema = vol.Schema(
            {
                vol.Required(CONF_USERNAME): str,
                vol.Required(CONF_PASSWORD): str,
            }
        )

        if reauth_entry:
            schema = self.add_suggested_values_to_schema(
                schema,
                {CONF_USERNAME: reauth_entry.data.get(CONF_USERNAME, "")},
            )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> config_entries.OptionsFlow:
        """Create options flow."""
        return RegazEnergyOptionsFlow(config_entry)


class RegazEnergyOptionsFlow(OptionsFlow):
    """Options flow for REGAZ settings."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Manage options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL_HOURS,
                    default=DEFAULT_UPDATE_INTERVAL_HOURS,
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=168)),
            }
        )
        schema = self.add_suggested_values_to_schema(schema, self.config_entry.options)

        return self.async_show_form(step_id="init", data_schema=schema)
