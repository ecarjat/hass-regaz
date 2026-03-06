### Build `regaz_energy` Integration + Reverse-Engineering Toolkit

**Summary**
- Create `plan.md` at repo root with this exact plan.
- Implement both deliverables:
1. A reusable REGAZ API reverse-engineering/probing toolkit.
2. A HACS-ready Home Assistant custom integration (`regaz_energy`) using config flow credentials.
- Use current-home-only scope and 24h polling by default.

**Key Changes**
1. **Repository bootstrap and plan artifact**
- Create project structure and commit-safe defaults (`.gitignore`, no secrets in code).
- Add `plan.md` with this plan as the canonical execution spec.

2. **Reverse-engineering toolkit (`tools/`)**
- Implement async API client with cookie-session auth and typed errors.
- Implement probe CLI that reads `.env` and can:
- login (`POST /api/authentication/login_check`),
- resolve home (`GET /api/authentication/me?extra=true`),
- fetch verified endpoints (`pce`, `meter/info`, `indicators`, `statistics level all/history/day`),
- output normalized JSON snapshots and field summaries.
- Hardcode/validate day-level contract: `level/day` requires `year` + `month` query args.

3. **Home Assistant custom integration (`custom_components/regaz_energy`)**
- `manifest.json`: `config_flow: true`, diagnostics enabled, HACS-compatible metadata.
- `config_flow.py`:
- user step with `username/password` validation using live API login + `/me`,
- reauth flow with `async_update_reload_and_abort`.
- `api.py`: `aiohttp` cookie-jar client for all REGAZ calls.
- `coordinator.py`: `DataUpdateCoordinator` (default 24h), auth failures raise `ConfigEntryAuthFailed`.
- `__init__.py`: config entry setup/unload/reload wiring.
- `sensor.py`: core v1 entities for current home only:
- total energy (kWh), total gas volume (m³),
- current month energy/volume,
- current year energy/volume,
- meter index + meter last reading (diagnostic).
- `diagnostics.py`: redact credentials, tokens/cookies, account identifiers.
- `const.py`, `strings.json`, `translations/en.json`, `translations/fr.json`.

4. **Packaging and docs**
- Add `hacs.json` for direct HACS installation.
- Add README with install steps (HACS/manual), config flow usage, entities, troubleshooting, API caveats.
- Document operational constraints (session cookies, day endpoint parameters, current-home scope).

**Test Plan**
- Add integration tests for:
- API client success/failure mapping (`204`, `401`, `403`, `500`),
- config flow user + reauth paths,
- coordinator refresh and auth-failure reauth trigger,
- sensor value mapping and metadata (`device_class`, `state_class`, units, unique IDs),
- diagnostics redaction coverage.
- Run HA test subset and static checks before finalizing.

**Assumptions / Defaults**
- API contract is based on live verification done on 2026-03-06 and may drift.
- `value` is treated as energy (kWh), `volume` as gas volume (m³).
- Scope is current home only (not all homes) for v1.
- Polling interval default is 24 hours; adjustable via options flow.
