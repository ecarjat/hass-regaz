# REGAZ Energy

Custom Home Assistant integration and reverse-engineering toolkit for `https://monespace.regaz.fr`.

Repository: `https://github.com/ecarjat/hass-regaz`

## Features

- Home Assistant custom integration domain: `regaz_energy`
- Config flow authentication with REGAZ username/password
- 24-hour polling by default (configurable in options)
- Current-home-only scope (first home returned by REGAZ API)
- Core sensors:
- Total energy (kWh)
- Total gas volume (m³)
- Current month/year energy and volume
- Meter index and last meter reading diagnostics
- A problem indicator when the last meter reading is older than three days or polling fails
- An optional action to import dated daily history into separate Home Assistant statistics
- Diagnostics endpoint with redaction of secrets/identifiers

## Installation

### HACS

1. Open HACS in Home Assistant.
2. Add `https://github.com/ecarjat/hass-regaz` as a custom repository (`Integration` category).
3. Install `REGAZ Energy`.
4. Restart Home Assistant.
5. Add the integration from `Settings -> Devices & Services`.

### Manual

1. Copy `/custom_components/regaz_energy` into your Home Assistant `custom_components` directory.
2. Restart Home Assistant.
3. Add the integration from `Settings -> Devices & Services`.

## Configuration

Use the UI config flow and provide:

- `username` (REGAZ portal login)
- `password`

Options:

- `update_interval_hours` (default: `24`)

After a temporary fetch failure, the integration keeps the last successful reading,
reports the problem, and retries within one hour. The reading date is supplied by
REGAZ and may lag behind the date of the successful fetch.

Use **Meter index** for the Energy dashboard's gas source. The total energy and
total gas volume entities sum the history currently returned by REGAZ. That
history can be revised or truncated, so these entities no longer advertise an
increasing state class and should not be used as cumulative Energy dashboard
sources. Existing long-term statistics for them are preserved by Home Assistant,
but new statistics are no longer generated for those two entities. Current
month/year entities report unavailable until the matching period is returned.

### Importing historical daily consumption

In **Developer Tools → Actions**, run **REGAZ Energy: Import daily consumption
history**, select the integration entry, and provide inclusive start and end dates
in `YYYY-MM-DD` format. Import only completed days for which REGAZ has a complete
daily record. For example:

```yaml
action: regaz_energy.import_daily_history
data:
  entry_id: YOUR_CONFIG_ENTRY_ID
  start_date: "2026-10-01"
  end_date: "2026-10-31"
```

The action creates separate daily gas and energy statistics; it does **not**
overwrite the existing meter index or its Energy dashboard history. To use the
imported data in the dashboard, select the corresponding REGAZ daily statistic
instead of the existing source; do not select both for the same consumption.
The daily amount is placed at the start of the local day; it does not imply
hourly readings. A zero baseline is recorded in the preceding hour.

Each repeat import must use the original start date and an end date at least as
late as the previous import. The entire range is checked and rebuilt, so revised
REGAZ estimates update later cumulative sums without duplicate entries. The
action fails without writing statistics when a day is missing or invalid. Imported
statistics do not update automatically: repeat the action to extend them or pick
up provider revisions. Data older than REGAZ's daily-history retention cannot
be reconstructed. REGAZ estimates remain estimates. Whole-hour UTC-offset time
zones are currently required.

## Python Requirements

For the standalone toolkit:

```bash
pip install -r requirements.txt
```

For tests:

```bash
pip install -r requirements-dev.txt
```

## Reverse-Engineering Toolkit

The toolkit is in `/tools`:

- `regaz_client.py`: async cookie-session API client
- `regaz_api_probe.py`: probing CLI

Example:

```bash
python3 tools/regaz_api_probe.py \
  --env-file .env \
  --output-dir artifacts/regaz_probe
```

Optional arguments:

- `--home-uuid`
- `--year` and `--month` for day-level statistics
- `--base-url`

## API Caveats

- Login endpoint returns `204` on success (`/api/authentication/login_check`) and sets auth cookies.
- Invalid credentials return `401`.
- Unauthenticated requests to protected endpoints return `403`.
- Day-level stats endpoint requires `year` and `month` query params:
- `/api/home/{home_uuid}/home-consumption-point/consumption/statistics/level/day?year=YYYY&month=M`

## Notes

- API behavior can change server-side.
- `value` is interpreted as energy (kWh), `volume` as gas volume (m³).
- Scope is intentionally limited to the current/first home for v1.
