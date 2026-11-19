"""REGAZ API client for Home Assistant integration runtime."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
import logging
import math
from typing import Any

import aiohttp
from homeassistant.util import dt as dt_util

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
        self._auth_generation = 0
        self._login_lock = asyncio.Lock()

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    async def _decode_payload(self, response: aiohttp.ClientResponse) -> Any:
        try:
            return await response.json(content_type=None)
        except Exception:
            return await response.text()

    async def async_authenticate(
        self, *, force: bool = False, unless_generation_changed: int | None = None
    ) -> None:
        """Authenticate and establish session cookies."""
        if self._authenticated and not force:
            return

        async with self._login_lock:
            if (
                unless_generation_changed is not None
                and self._auth_generation != unless_generation_changed
            ):
                return
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
                    self._auth_generation += 1
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
        auth_generation = self._auth_generation

        url = self._url(path)
        async with self._session.request(
            method,
            url,
            params=params,
            timeout=self._timeout,
        ) as response:
            if response.status in (401, 403):
                if retry_auth:
                    await self.async_authenticate(
                        force=True, unless_generation_changed=auth_generation
                    )
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
            raise RegazRequestError(
                404, "No homes found on account", self._url("api/authentication/me")
            )

        home_uuid = homes[0].get("uuid")
        if not home_uuid:
            raise RegazRequestError(
                500,
                "Missing home uuid in /api/authentication/me response",
                self._url("api/authentication/me"),
            )
        return str(home_uuid)

    async def async_get_home_snapshot(
        self, *, home_uuid: str | None = None
    ) -> dict[str, Any]:
        """Fetch consolidated payload used by Home Assistant coordinator."""
        me = await self.async_get_me(extra=True)
        homes = me.get("homes") or []

        if home_uuid is None:
            if not homes:
                raise RegazRequestError(
                    404, "No homes found on account", self._url("api/authentication/me")
                )
            if not homes[0].get("uuid"):
                raise RegazRequestError(
                    500, "Missing home UUID", self._url("api/authentication/me")
                )
            home_uuid = str(homes[0]["uuid"])

        home = next(
            (item for item in homes if str(item.get("uuid")) == home_uuid), None
        )

        now = dt_util.now()
        results = await asyncio.gather(
            self.async_get_pce(home_uuid),
            self.async_get_meter_info(home_uuid),
            self.async_get_indicators(home_uuid),
            self.async_get_statistics(home_uuid, "all"),
            self.async_get_statistics(
                home_uuid, "day", params={"year": now.year, "month": now.month}
            ),
            return_exceptions=True,
        )
        sections = dict(
            zip(
                ("pce", "meter_info", "indicators", "statistics_all", "statistics_day"),
                results,
            )
        )
        meter = sections["meter_info"]
        if not isinstance(meter, BaseException):
            try:
                value = float(meter["valeurPrecise"])
                if not math.isfinite(value) or value < 0:
                    raise ValueError
            except (KeyError, TypeError, ValueError, OverflowError):
                sections["meter_info"] = RegazApiError(
                    "Meter data is missing or invalid"
                )
        stats = sections["statistics_all"]
        if not isinstance(stats, BaseException) and (
            not isinstance(stats, dict)
            or not isinstance(stats.get("data"), dict)
            or not all(
                isinstance(stats["data"].get(key), list) for key in ("month", "year")
            )
        ):
            sections["statistics_all"] = RegazApiError(
                "Consumption statistics are missing"
            )
        daily = sections["statistics_day"]
        if not isinstance(daily, BaseException) and (
            not isinstance(daily, dict) or not isinstance(daily.get("data"), list)
        ):
            sections["statistics_day"] = RegazApiError("Daily statistics are missing")
        failures = [
            key for key, value in sections.items() if isinstance(value, BaseException)
        ]
        if all(key in failures for key in ("meter_info", "statistics_all")):
            # Preserve auth errors when neither useful data source is accessible.
            for value in sections.values():
                if isinstance(value, RegazAuthError):
                    raise value
            failure = sections["meter_info"]
            assert isinstance(failure, BaseException)
            raise failure
        for key in failures:
            _LOGGER.debug(
                "REGAZ %s endpoint failed (%s)", key, type(sections[key]).__name__
            )
            sections[key] = None

        return {
            "account": me,
            "home": home,
            "home_uuid": home_uuid,
            **sections,
            "failed_sections": failures,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }
