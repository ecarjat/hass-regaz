"""REGAZ API client for Home Assistant integration runtime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
import logging
from typing import Any

import aiohttp

from .const import DEFAULT_BASE_URL

_LOGGER = logging.getLogger(__name__)


class RegazApiError(Exception):
    """Base REGAZ API error."""


class RegazAuthError(RegazApiError):
    """Authentication failed or session expired."""


class RegazForbiddenError(RegazApiError):
    """Request forbidden."""


class RegazDayValidationError(RegazApiError):
    """Day-level endpoint contract validation failed."""


@dataclass(slots=True)
class RegazRequestError(RegazApiError):
    """HTTP request failed."""

    status: int
    message: str
    url: str

    def __str__(self) -> str:
        return f"Regaz API error {self.status} for {self.url}: {self.message}"


class RegazApiClient:
    """Cookie-session client for monespace.regaz.fr."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        username: str,
        password: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: int = 20,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._authenticated = False
        self._login_lock = asyncio.Lock()

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    async def _decode_payload(self, response: aiohttp.ClientResponse) -> Any:
        try:
            return await response.json(content_type=None)
        except Exception:
            return await response.text()

    async def async_authenticate(self, *, force: bool = False) -> None:
        """Authenticate and establish session cookies."""
        if self._authenticated and not force:
            return

        async with self._login_lock:
            if self._authenticated and not force:
                return

            url = self._url("api/authentication/login_check")
            async with self._session.post(
                url,
                json={"username": self._username, "password": self._password},
                timeout=self._timeout,
            ) as response:
                if response.status == 204:
                    self._authenticated = True
                    return

                payload = await self._decode_payload(response)
                message = (
                    payload.get("message", "Authentication failed")
                    if isinstance(payload, dict)
                    else str(payload)
                )

                if response.status == 401:
                    raise RegazAuthError(message)
                if response.status == 403:
                    raise RegazForbiddenError(message)
                raise RegazRequestError(response.status, message, url)

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        retry_auth: bool = True,
    ) -> Any:
        await self.async_authenticate()

        url = self._url(path)
        async with self._session.request(
            method,
            url,
            params=params,
            timeout=self._timeout,
        ) as response:
            if response.status in (401, 403):
                if retry_auth:
                    await self.async_authenticate(force=True)
                    return await self._request_json(
                        method,
                        path,
                        params=params,
                        retry_auth=False,
                    )

                payload = await self._decode_payload(response)
                message = (
                    payload.get("message", "Unauthorized")
                    if isinstance(payload, dict)
                    else str(payload)
                )
                if response.status == 401:
                    raise RegazAuthError(message)
                raise RegazForbiddenError(message)

            if response.status >= 400:
                payload = await self._decode_payload(response)
                message = (
                    payload.get("message", "Request failed")
                    if isinstance(payload, dict)
                    else str(payload)
                )
                raise RegazRequestError(response.status, message, url)

            if response.status == 204:
                return None
            return await self._decode_payload(response)

    async def async_get_me(self, *, extra: bool = True) -> dict[str, Any]:
        payload = await self._request_json(
            "GET",
            "api/authentication/me",
            params={"extra": str(extra).lower()},
        )
        return payload if isinstance(payload, dict) else {}

    async def async_get_pce(self, home_uuid: str) -> dict[str, Any]:
        payload = await self._request_json(
            "GET",
            f"api/home/{home_uuid}/home-consumption-point/pce",
        )
        return payload if isinstance(payload, dict) else {}

    async def async_get_meter_info(self, home_uuid: str) -> dict[str, Any]:
        payload = await self._request_json(
            "GET",
            f"api/home/{home_uuid}/home-consumption-point/meter/info",
        )
        return payload if isinstance(payload, dict) else {}

    async def async_get_indicators(self, home_uuid: str) -> dict[str, Any]:
        payload = await self._request_json(
            "GET",
            f"api/home/{home_uuid}/home-consumption-point/consumption/indicators",
        )
        return payload if isinstance(payload, dict) else {}

    async def async_get_statistics(
        self,
        home_uuid: str,
        level: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if level == "day":
            year = (params or {}).get("year")
            month = (params or {}).get("month")
            if year is None or month is None:
                raise RegazDayValidationError(
                    "The day statistics endpoint requires both 'year' and 'month' query params"
                )

        payload = await self._request_json(
            "GET",
            f"api/home/{home_uuid}/home-consumption-point/consumption/statistics/level/{level}",
            params=params,
        )
        return payload if isinstance(payload, dict) else {}

    async def async_resolve_current_home_uuid(self) -> str:
        me = await self.async_get_me(extra=True)
        homes = me.get("homes") or []
        if not homes:
            raise RegazRequestError(404, "No homes found on account", self._url("api/authentication/me"))

        home_uuid = homes[0].get("uuid")
        if not home_uuid:
            raise RegazRequestError(
                500,
                "Missing home uuid in /api/authentication/me response",
                self._url("api/authentication/me"),
            )
        return str(home_uuid)

    async def async_get_home_snapshot(self, *, home_uuid: str | None = None) -> dict[str, Any]:
        """Fetch consolidated payload used by Home Assistant coordinator."""
        me = await self.async_get_me(extra=True)
        homes = me.get("homes") or []

        if home_uuid is None:
            if not homes:
                raise RegazRequestError(404, "No homes found on account", self._url("api/authentication/me"))
            home_uuid = str(homes[0].get("uuid"))

        home = next((item for item in homes if str(item.get("uuid")) == home_uuid), None)

        now = datetime.now()
        day_params = {"year": now.year, "month": now.month}

        pce, meter_info, indicators, statistics_all = await asyncio.gather(
            self.async_get_pce(home_uuid),
            self.async_get_meter_info(home_uuid),
            self.async_get_indicators(home_uuid),
            self.async_get_statistics(home_uuid, "all"),
        )

        statistics_history: dict[str, Any] = {}
        statistics_day: dict[str, Any] = {}

        try:
            statistics_history = await self.async_get_statistics(home_uuid, "history")
        except RegazApiError as err:
            _LOGGER.debug("Optional history endpoint failed: %s", err)

        try:
            statistics_day = await self.async_get_statistics(
                home_uuid,
                "day",
                params=day_params,
            )
        except RegazApiError as err:
            _LOGGER.debug("Optional day endpoint failed: %s", err)

        return {
            "account": me,
            "home": home,
            "home_uuid": home_uuid,
            "pce": pce,
            "meter_info": meter_info,
            "indicators": indicators,
            "statistics_all": statistics_all,
            "statistics_history": statistics_history,
            "statistics_day": statistics_day,
            "day_query": day_params,
            "fetched_at": datetime.now().isoformat(),
        }
