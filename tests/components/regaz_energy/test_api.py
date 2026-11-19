"""Tests for integration-level REGAZ API client behavior."""

from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock

pytest.importorskip("homeassistant")

from custom_components.regaz_energy.api import (
    RegazApiClient,
    RegazAuthError,
    RegazRequestError,
)


class FakeResponse:
    def __init__(self, status: int, payload=None):
        self.status = status
        self._payload = payload

    async def json(self, content_type=None):
        if isinstance(self._payload, dict):
            return self._payload
        raise ValueError("Not JSON")

    async def text(self):
        return "" if self._payload is None else str(self._payload)


class FakeContextManager:
    def __init__(self, response: FakeResponse):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeSession:
    def __init__(self, responses):
        self.responses = responses

    def _next(self):
        assert self.responses
        return FakeContextManager(self.responses.pop(0))

    def post(self, url, **kwargs):
        return self._next()

    def request(self, method, url, **kwargs):
        return self._next()


@pytest.mark.asyncio
async def test_authentication_success_then_get_me() -> None:
    session = FakeSession(
        [FakeResponse(204), FakeResponse(200, {"uuid": "acc", "homes": []})]
    )
    client = RegazApiClient(
        session,
        username="user@example.com",
        password="secret",
    )

    payload = await client.async_get_me(extra=True)

    assert payload["uuid"] == "acc"


@pytest.mark.asyncio
async def test_authentication_failure_raises_auth_error() -> None:
    session = FakeSession([FakeResponse(401, {"message": "Identifiants invalides."})])
    client = RegazApiClient(
        session,
        username="user@example.com",
        password="bad",
    )

    with pytest.raises(RegazAuthError):
        await client.async_authenticate(force=True)


@pytest.mark.asyncio
async def test_get_me_server_error_maps_request_error() -> None:
    session = FakeSession(
        [FakeResponse(204), FakeResponse(500, {"message": "Internal Server Error"})]
    )
    client = RegazApiClient(
        session,
        username="user@example.com",
        password="secret",
    )

    with pytest.raises(RegazRequestError):
        await client.async_get_me(extra=True)


@pytest.mark.asyncio
async def test_snapshot_preserves_meter_when_statistics_endpoint_fails() -> None:
    client = RegazApiClient(FakeSession([]), username="user", password="secret")
    client.async_get_me = AsyncMock(return_value={"homes": [{"uuid": "home"}]})
    client.async_get_pce = AsyncMock(return_value={})
    client.async_get_meter_info = AsyncMock(return_value={"valeurPrecise": 123})
    client.async_get_indicators = AsyncMock(side_effect=TimeoutError())
    client.async_get_statistics = AsyncMock(side_effect=TimeoutError())
    snapshot = await client.async_get_home_snapshot()
    assert snapshot["meter_info"]["valeurPrecise"] == 123
    assert snapshot["statistics_all"] is None
    assert set(snapshot["failed_sections"]) == {"indicators", "statistics_all"}


@pytest.mark.asyncio
async def test_snapshot_rejects_absent_home_uuid() -> None:
    client = RegazApiClient(FakeSession([]), username="user", password="secret")
    client.async_get_me = AsyncMock(return_value={"homes": [{}]})
    with pytest.raises(RegazRequestError):
        await client.async_get_home_snapshot()


@pytest.mark.asyncio
async def test_concurrent_expired_requests_only_reauthenticate_once() -> None:
    session = FakeSession([FakeResponse(204)])
    client = RegazApiClient(session, username="user", password="secret")
    client._authenticated = True
    client._auth_generation = 1
    await asyncio.gather(
        *(
            client.async_authenticate(force=True, unless_generation_changed=1)
            for _ in range(3)
        )
    )
    assert client._auth_generation == 2
    assert not session.responses
