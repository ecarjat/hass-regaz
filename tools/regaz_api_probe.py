#!/usr/bin/env python3
"""Probe monespace.regaz.fr endpoints and save normalized snapshots."""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiohttp

from regaz_client import DEFAULT_BASE_URL, RegazApiClient, RegazError


def _load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _normalize(data: Any) -> Any:
    """Normalize data into JSON-compatible primitives."""
    return json.loads(json.dumps(data, ensure_ascii=False, default=str))


def _save_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(_normalize(payload), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _safe_len(item: Any) -> int:
    return len(item) if isinstance(item, list) else 0


def _build_summary(snapshot: dict[str, Any]) -> dict[str, Any]:
    month_rows = (
        (snapshot.get("statistics_all") or {}).get("data", {}).get("month", [])
        if isinstance(snapshot.get("statistics_all"), dict)
        else []
    )
    year_rows = (
        (snapshot.get("statistics_all") or {}).get("data", {}).get("year", [])
        if isinstance(snapshot.get("statistics_all"), dict)
        else []
    )
    day_rows = (
        (snapshot.get("statistics_day") or {}).get("data", [])
        if isinstance(snapshot.get("statistics_day"), dict)
        else []
    )

    account = snapshot.get("account") or {}
    pce = snapshot.get("pce") or {}
    meter = snapshot.get("meter_info") or {}

    return {
        "fetched_at": snapshot.get("fetched_at"),
        "home_uuid": snapshot.get("home_uuid"),
        "account_uuid": account.get("uuid"),
        "account_email": account.get("email"),
        "homes_count": _safe_len(account.get("homes")),
        "pce": pce.get("pce"),
        "pce_state": pce.get("state"),
        "month_rows": _safe_len(month_rows),
        "year_rows": _safe_len(year_rows),
        "day_rows": _safe_len(day_rows),
        "meter_index": meter.get("valeurPrecise"),
        "meter_reading_date": meter.get("date"),
        "day_query": snapshot.get("day_query"),
    }


async def _run_probe(args: argparse.Namespace) -> int:
    env_values = _load_env_file(Path(args.env_file)) if args.env_file else {}

    username = args.username or env_values.get("USER")
    password = args.password or env_values.get("PASS")

    if not username or not password:
        raise SystemExit(
            "Missing credentials. Provide --username/--password or set USER and PASS in --env-file"
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar()) as session:
        client = RegazApiClient(
            session,
            username=username,
            password=password,
            base_url=args.base_url,
        )

        snapshot = await client.fetch_home_snapshot(
            home_uuid=args.home_uuid,
            day_year=args.year,
            day_month=args.month,
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / timestamp
    run_dir.mkdir(parents=True, exist_ok=True)

    summary = _build_summary(snapshot)

    _save_json(run_dir / "summary.json", summary)
    _save_json(run_dir / "snapshot.json", snapshot)

    for key in (
        "account",
        "home",
        "pce",
        "meter_info",
        "indicators",
        "statistics_all",
        "statistics_history",
        "statistics_day",
    ):
        _save_json(run_dir / f"{key}.json", snapshot.get(key))

    print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))
    print(f"Saved probe output to {run_dir}")
    return 0


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="REGAZ base URL")
    parser.add_argument("--env-file", default=".env", help="Env file with USER and PASS")
    parser.add_argument("--username", help="Override USER from env file")
    parser.add_argument("--password", help="Override PASS from env file")
    parser.add_argument("--home-uuid", help="Specific home UUID; defaults to account current/first")
    parser.add_argument("--year", type=int, help="Day-level query year")
    parser.add_argument("--month", type=int, help="Day-level query month")
    parser.add_argument(
        "--output-dir",
        default="artifacts/regaz_probe",
        help="Output directory for normalized snapshots",
    )
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    try:
        return asyncio.run(_run_probe(args))
    except RegazError as err:
        print(f"Probe failed: {err}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
