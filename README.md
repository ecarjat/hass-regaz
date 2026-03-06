# REGAZ Energy

Custom Home Assistant integration and reverse-engineering toolkit for `https://monespace.regaz.fr`.

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
- Diagnostics endpoint with redaction of secrets/identifiers

## Installation

### HACS

1. Open HACS in Home Assistant.
2. Add this repository as a custom repository (`Integration` category).
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
