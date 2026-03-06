"""Async API client for monespace.regaz.fr."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiohttp

DEFAULT_BASE_URL = "https://monespace.regaz.fr"


class RegazError(Exception):
    """Base REGAZ error."""


class RegazAuthError(RegazError):
    """Authentication failed."""


class RegazForbiddenError(RegazError):
    """Authenticated session is missing or forbidden."""


class RegazDayLevelValidationError(RegazError):
    """Day-level endpoint requires year/month."""


@dataclass(slots=True)
class RegazRequestError(RegazError):
    """API request failed."""

    status: int
    message: str
    url: str

    def __str__(self) -> str:
        return f"Regaz API error {self.status} for {self.url}: {self.message}"


class RegazApiClient:
    """Cookie-session API client for REGAZ."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: int = 20,
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._base_url = base_url.rstrip("/")
        self._timeout = aiohttp.ClientTimeout(total=timeout_seconds)
        self._login_lock = asyncio.Lock()
        self._authenticated = False

    @property
    def username(self) -> str:
        return self._username

    def _url(self, path: str) -> str:
        return f"{self._base_url}/{path.lstrip('/')}"

    async def _decode_payload(self, response: aiohttp.ClientResponse) -> Any:
        try:
            return await response.json(content_type=None)
        except Exception:
            return await response.text()

    async def login(self, *, force: bool = False) -> None:
        """Authenticate and establish cookie-based session."""
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
        retry_on_auth: bool = True,
    ) -> Any:
        await self.login()

        url = self._url(path)
        async with self._session.request(
            method,
            url,
            params=params,
            timeout=self._timeout,
        ) as response:
            if response.status in (401, 403):
                if retry_on_auth:
                    await self.login(force=True)
                    return await self._request_json(
                        method,
                        path,
                        params=params,
                        retry_on_auth=False,
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

    async def get_me(self, *, extra: bool = True) -> dict[str, Any]:
        params = {"extra": str(extra).lower()}
        payload = await self._request_json("GET", "api/authentication/me", params=params)
        if not isinstance(payload, dict):
            raise RegazRequestError(500, "Invalid /me payload", self._url("api/authentication/me"))
        return payload

    async def get_pce(self, home_uuid: str) -> dict[str, Any]:
        payload = await self._request_json(
            "GET",
            f"api/home/{home_uuid}/home-consumption-point/pce",
        )
        return payload if isinstance(payload, dict) else {}

    async def get_meter_info(self, home_uuid: str) -> dict[str, Any]:
        payload = await self._request_json(
            "GET",
            f"api/home/{home_uuid}/home-consumption-point/meter/info",
        )
        return payload if isinstance(payload, dict) else {}

    async def get_indicators(self, home_uuid: str) -> dict[str, Any]:
        payload = await self._request_json(
            "GET",
            f"api/home/{home_uuid}/home-consumption-point/consumption/indicators",
        )
        return payload if isinstance(payload, dict) else {}

    async def get_statistics(
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
                raise RegazDayLevelValidationError(
                    "Day-level statistics require both 'year' and 'month' query parameters"
                )

        payload = await self._request_json(
            "GET",
            f"api/home/{home_uuid}/home-consumption-point/consumption/statistics/level/{level}",
            params=params,
        )
        return payload if isinstance(payload, dict) else {}

    async def get_statistics_all(self, home_uuid: str) -> dict[str, Any]:
        return await self.get_statistics(home_uuid, "all")

    async def get_statistics_history(self, home_uuid: str) -> dict[str, Any]:
        return await self.get_statistics(home_uuid, "history")

    async def get_statistics_day(self, home_uuid: str, *, year: int, month: int) -> dict[str, Any]:
        return await self.get_statistics(
            home_uuid,
            "day",
            params={"year": year, "month": month},
        )

    async def resolve_home_uuid(self) -> str:
        me = await self.get_me(extra=True)
        homes = me.get("homes") or []
        if not homes:
            raise RegazRequestError(404, "No homes found on account", self._url("api/authentication/me"))
        first_home = homes[0]
        home_uuid = first_home.get("uuid")
        if not home_uuid:
            raise RegazRequestError(500, "Missing home uuid in /me payload", self._url("api/authentication/me"))
        return str(home_uuid)

    async def fetch_home_snapshot(
        self,
        *,
        home_uuid: str | None = None,
        day_year: int | None = None,
        day_month: int | None = None,
    ) -> dict[str, Any]:
        me = await self.get_me(extra=True)
        homes = me.get("homes") or []

        if home_uuid is None:
            if not homes:
                raise RegazRequestError(404, "No homes found on account", self._url("api/authentication/me"))
            home_uuid = str(homes[0].get("uuid"))

        selected_home = next((home for home in homes if str(home.get("uuid")) == home_uuid), None)

        now = datetime.now()
        year = day_year or now.year
        month = day_month or now.month

        pce, meter_info, indicators, stats_all, stats_history, stats_day = await asyncio.gather(
            self.get_pce(home_uuid),
            self.get_meter_info(home_uuid),
            self.get_indicators(home_uuid),
            self.get_statistics_all(home_uuid),
            self.get_statistics_history(home_uuid),
            self.get_statistics_day(home_uuid, year=year, month=month),
        )

        return {
            "account": me,
            "home": selected_home,
            "home_uuid": home_uuid,
            "pce": pce,
            "meter_info": meter_info,
            "indicators": indicators,
            "statistics_all": stats_all,
            "statistics_history": stats_history,
            "statistics_day": stats_day,
            "day_query": {"year": year, "month": month},
            "fetched_at": datetime.now().isoformat(),
        }
