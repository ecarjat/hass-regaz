"""Explicit, repeatable import of REGAZ's dated daily consumption."""

from __future__ import annotations

import asyncio
from datetime import date, timedelta
import math
from typing import Any

from homeassistant.components.recorder.statistics import async_add_external_statistics
from homeassistant.const import UnitOfEnergy, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import EnergyConverter, VolumeConverter

from .const import DOMAIN

try:
    from homeassistant.components.recorder.models import StatisticMeanType
except ImportError:  # Home Assistant 2025.1 compatibility
    StatisticMeanType = None


def _month_iter(start: date, end: date):
    year, month = start.year, start.month
    while (year, month) <= (end.year, end.month):
        yield year, month
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)


def _daily_rows(
    rows: list[dict[str, Any]], start: date, end: date
) -> list[tuple[date, float, float]]:
    """Validate a complete range before writing any statistics."""
    days: dict[date, tuple[float, float]] = {}
    for row in rows:
        try:
            day = date(int(row["year"]), int(row["month"]), int(row["day"]))
        except (KeyError, TypeError, ValueError, OverflowError) as err:
            raise HomeAssistantError("Invalid date in REGAZ daily history") from err
        if not start <= day <= end:
            continue
        try:
            energy, volume = float(row["value"]), float(row["volume"])
        except (KeyError, TypeError, ValueError, OverflowError) as err:
            raise HomeAssistantError(f"Incomplete REGAZ data for {day}") from err
        if day in days or not all(
            math.isfinite(x) and x >= 0 for x in (energy, volume)
        ):
            raise HomeAssistantError(f"Invalid or duplicate REGAZ data for {day}")
        days[day] = (energy, volume)
    expected = (end - start).days + 1
    if len(days) != expected:
        first_missing = next(
            start + timedelta(days=offset)
            for offset in range(expected)
            if start + timedelta(days=offset) not in days
        )
        latest = f" Latest available date in this range: {max(days)}." if days else ""
        raise HomeAssistantError(
            f"REGAZ has no daily reading for {first_missing}.{latest} "
            "No statistics were imported."
        )
    return [(day, *days[day]) for day in sorted(days)]


def _build_statistics(
    days: list[tuple[date, float, float]],
) -> tuple[list[dict], list[dict]]:
    """Create separate cumulative statistics with a zero baseline."""
    starts = [dt_util.as_utc(dt_util.start_of_local_day(day)) for day, _, _ in days]
    if any(start.minute or start.second for start in starts):
        raise HomeAssistantError(
            "Daily import requires a time zone aligned to whole UTC hours"
        )
    baseline = starts[0] - timedelta(hours=1)
    energy = [{"start": baseline, "state": 0.0, "sum": 0.0}]
    volume = [{"start": baseline, "state": 0.0, "sum": 0.0}]
    energy_sum = volume_sum = 0.0
    for start, (_, daily_energy, daily_volume) in zip(starts, days):
        energy_sum += daily_energy
        volume_sum += daily_volume
        energy.append({"start": start, "state": energy_sum, "sum": energy_sum})
        volume.append({"start": start, "state": volume_sum, "sum": volume_sum})
    return energy, volume


def _metadata(entry_id: str, kind: str) -> dict:
    gas = kind == "gas"
    metadata = {
        "has_sum": True,
        "name": f"REGAZ daily {'gas volume' if gas else 'energy'}",
        "source": DOMAIN,
        "statistic_id": f"{DOMAIN}:{entry_id.lower()}_daily_{kind}",
        "unit_of_measurement": UnitOfVolume.CUBIC_METERS
        if gas
        else UnitOfEnergy.KILO_WATT_HOUR,
    }
    if StatisticMeanType is None:
        metadata["has_mean"] = False
    else:
        metadata["mean_type"] = StatisticMeanType.NONE
        metadata["unit_class"] = (
            VolumeConverter.UNIT_CLASS if gas else EnergyConverter.UNIT_CLASS
        )
    return metadata


async def async_import_daily_history(
    hass: HomeAssistant, entry_id: str, api, home_uuid: str, start: date, end: date
) -> None:
    """Import a complete range; subsequent imports rebuild the entire same series."""
    if end < start or end >= dt_util.now().date() or (end - start).days > 3660:
        raise HomeAssistantError("Choose a range of completed days, at most ten years")
    store = Store(hass, 1, f"{DOMAIN}_daily_history_{entry_id}")
    previous = await store.async_load() or {}
    if previous and (
        previous.get("start_date") != start.isoformat()
        or end.isoformat() < previous.get("end_date", "")
    ):
        raise HomeAssistantError(
            "Repeat imports must keep the original start date and include the previously imported end date"
        )

    rows: list[dict[str, Any]] = []
    for index, (year, month) in enumerate(_month_iter(start, end)):
        if index:
            await asyncio.sleep(1)
        try:
            payload = await api.async_get_statistics(
                home_uuid, "day", params={"year": year, "month": month}
            )
        except Exception as err:
            raise HomeAssistantError(
                f"REGAZ daily history request failed for {year}-{month:02d}"
            ) from err
        data = payload.get("data")
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise HomeAssistantError(
                f"Invalid REGAZ daily history for {year}-{month:02d}"
            )
        rows.extend(data)
    days = _daily_rows(rows, start, end)
    energy, gas = _build_statistics(days)
    async_add_external_statistics(hass, _metadata(entry_id, "energy"), energy)
    async_add_external_statistics(hass, _metadata(entry_id, "gas"), gas)
    await store.async_save(
        {"start_date": start.isoformat(), "end_date": end.isoformat()}
    )
