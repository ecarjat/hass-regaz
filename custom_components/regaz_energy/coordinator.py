"""Coordinator for REGAZ energy data."""

from __future__ import annotations

from datetime import timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import RegazApiClient, RegazApiError, RegazAuthError, RegazForbiddenError
from .const import CONF_UPDATE_INTERVAL_HOURS, DEFAULT_UPDATE_INTERVAL_HOURS, DOMAIN

_LOGGER = logging.getLogger(__name__)


class RegazDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Fetch and coordinate REGAZ payload updates."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        api: RegazApiClient,
    ) -> None:
        self.api = api
        self.config_entry = config_entry
        self.home_uuid: str | None = None

        update_hours = config_entry.options.get(
            CONF_UPDATE_INTERVAL_HOURS,
            DEFAULT_UPDATE_INTERVAL_HOURS,
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=timedelta(hours=int(update_hours)),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            payload = await self.api.async_get_home_snapshot(home_uuid=self.home_uuid)
            if payload.get("home_uuid"):
                self.home_uuid = str(payload["home_uuid"])
            return payload
        except (RegazAuthError, RegazForbiddenError) as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except RegazApiError as err:
            raise UpdateFailed(str(err)) from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected coordinator error: {err}") from err
