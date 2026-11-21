"""Tests for safe daily statistics imports."""

from datetime import date
from unittest.mock import patch

import pytest

pytest.importorskip("homeassistant")
pytest.importorskip("pytest_homeassistant_custom_component")

from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.recorder.statistics import get_last_statistics

from custom_components.regaz_energy.statistics import async_import_daily_history


class MemoryStore:
    data = None

    def __init__(self, *args):
        pass

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        type(self).data = data


class Api:
    rows = [
        {"year": 2025, "month": "10", "day": "28", "value": 20.0, "volume": 2.0},
        {"year": 2025, "month": "10", "day": "29", "value": 30.0, "volume": 3.0},
    ]

    async def async_get_statistics(self, home_uuid, level, *, params):
        return {"data": self.rows}


@pytest.mark.asyncio
async def test_import_is_repeatable_and_revises_following_totals(hass):
    MemoryStore.data = None
    api = Api()
    recorded = []
    with patch("custom_components.regaz_energy.statistics.Store", MemoryStore), patch(
        "custom_components.regaz_energy.statistics.async_add_external_statistics",
        side_effect=lambda hass, metadata, data: recorded.append((metadata, data)),
    ):
        await async_import_daily_history(
            hass, "entry123", api, "home", date(2025, 10, 28), date(2025, 10, 29)
        )
        assert [row["sum"] for row in recorded[1][1]] == [0.0, 2.0, 5.0]
        assert recorded[1][0]["statistic_id"] == "regaz_energy:entry123_daily_gas"
        assert all(row["start"].tzinfo is not None for row in recorded[1][1])
        api.rows = [dict(api.rows[0], volume=1.5), api.rows[1]]
        await async_import_daily_history(
            hass, "entry123", api, "home", date(2025, 10, 28), date(2025, 10, 29)
        )
        assert [row["sum"] for row in recorded[3][1]] == [0.0, 1.5, 4.5]
        assert [row["start"] for row in recorded[1][1]] == [
            row["start"] for row in recorded[3][1]
        ]
        with pytest.raises(HomeAssistantError, match="original start date"):
            await async_import_daily_history(
                hass, "entry123", api, "home", date(2025, 10, 29), date(2025, 10, 29)
            )
    assert len(recorded) == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "bad_rows",
    [[], [{"year": 2025, "month": "10", "day": "28", "value": 2, "volume": -1}]],
)
async def test_import_rejects_missing_or_invalid_days_before_writing(hass, bad_rows):
    MemoryStore.data = None
    api = Api()
    api.rows = bad_rows
    with patch("custom_components.regaz_energy.statistics.Store", MemoryStore), patch(
        "custom_components.regaz_energy.statistics.async_add_external_statistics"
    ) as add:
        with pytest.raises(HomeAssistantError):
            await async_import_daily_history(
                hass, "entry123", api, "home", date(2025, 10, 28), date(2025, 10, 29)
            )
        add.assert_not_called()


@pytest.mark.asyncio
async def test_missing_last_day_reports_available_date(hass):
    MemoryStore.data = None
    api = Api()
    with patch("custom_components.regaz_energy.statistics.Store", MemoryStore), patch(
        "custom_components.regaz_energy.statistics.async_add_external_statistics"
    ) as add:
        with pytest.raises(HomeAssistantError) as error:
            await async_import_daily_history(
                hass, "entry123", api, "home", date(2025, 10, 28), date(2025, 10, 30)
            )
        assert "2025-10-30" in str(error.value)
        assert "2025-10-29" in str(error.value)
        assert "No statistics were imported" in str(error.value)
        add.assert_not_called()


@pytest.mark.asyncio
async def test_import_writes_real_recorder_and_updates_revisions(recorder_mock, hass):
    api = Api()
    await async_import_daily_history(
        hass, "entry123", api, "home", date(2025, 10, 28), date(2025, 10, 29)
    )
    await recorder_mock.async_block_till_done()
    statistic_id = "regaz_energy:entry123_daily_gas"
    results = await hass.async_add_executor_job(
        get_last_statistics, hass, 3, statistic_id, False, {"sum"}
    )
    assert results[statistic_id][0]["sum"] == pytest.approx(5.0)

    api.rows = [dict(api.rows[0], volume=1.5), api.rows[1]]
    await async_import_daily_history(
        hass, "entry123", api, "home", date(2025, 10, 28), date(2025, 10, 29)
    )
    await recorder_mock.async_block_till_done()
    results = await hass.async_add_executor_job(
        get_last_statistics, hass, 3, statistic_id, False, {"sum"}
    )
    assert len(results[statistic_id]) == 3
    assert results[statistic_id][0]["sum"] == pytest.approx(4.5)
