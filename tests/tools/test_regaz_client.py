"""Tests for standalone REGAZ toolkit API client."""

from __future__ import annotations

import pytest

from tools.regaz_client import (
    RegazApiClient,
    RegazAuthError,
    RegazDayLevelValidationError,
    RegazForbiddenError,
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
    def __init__(self, responses: list[FakeResponse]):
        self.responses = responses
        self.calls: list[tuple[str, str, dict]] = []

    def _next(self) -> FakeContextManager:
        assert self.responses, "No fake responses left"
        return FakeContextManager(self.responses.pop(0))

    def post(self, url: str, **kwargs):
        self.calls.append(("POST", url, kwargs))
        return self._next()

    def request(self, method: str, url: str, **kwargs):
        self.calls.append((method, url, kwargs))
        return self._next()


@pytest.mark.asyncio
async def test_login_success_sets_session_authenticated() -> None:
    session = FakeSession([FakeResponse(204)])
    client = RegazApiClient(session, "user@example.com", "secret")

    await client.login()

    assert session.calls[0][0] == "POST"
    assert session.calls[0][1].endswith("/api/authentication/login_check")


@pytest.mark.asyncio
async def test_login_invalid_credentials_raises_auth_error() -> None:
    session = FakeSession([FakeResponse(401, {"message": "Identifiants invalides."})])
    client = RegazApiClient(session, "user@example.com", "wrong")

    with pytest.raises(RegazAuthError):
        await client.login()


@pytest.mark.asyncio
async def test_get_me_reauths_after_forbidden() -> None:
    session = FakeSession(
        [
            FakeResponse(204),
            FakeResponse(403, {"message": "Forbidden"}),
            FakeResponse(204),
            FakeResponse(200, {"uuid": "acc-1", "homes": [{"uuid": "home-1"}]}),
        ]
    )
    client = RegazApiClient(session, "user@example.com", "secret")

    payload = await client.get_me(extra=True)

    assert payload["uuid"] == "acc-1"
    assert len(session.calls) == 4
    assert session.calls[1][0] == "GET"
    assert session.calls[3][0] == "GET"


@pytest.mark.asyncio
async def test_get_me_raises_on_server_error() -> None:
    session = FakeSession(
        [
            FakeResponse(204),
            FakeResponse(500, {"message": "Internal Server Error"}),
        ]
    )
    client = RegazApiClient(session, "user@example.com", "secret")

    with pytest.raises(RegazRequestError) as err:
        await client.get_me()

    assert err.value.status == 500


@pytest.mark.asyncio
async def test_day_level_requires_year_and_month() -> None:
    session = FakeSession([])
    client = RegazApiClient(session, "user@example.com", "secret")

    with pytest.raises(RegazDayLevelValidationError):
        await client.get_statistics("home-1", "day", params={"year": 2026})


@pytest.mark.asyncio
async def test_forbidden_after_retry_raises_forbidden_error() -> None:
    session = FakeSession(
        [
            FakeResponse(204),
            FakeResponse(403, {"message": "Forbidden"}),
            FakeResponse(204),
            FakeResponse(403, {"message": "Forbidden"}),
        ]
    )
    client = RegazApiClient(session, "user@example.com", "secret")

    with pytest.raises(RegazForbiddenError):
        await client.get_me()
