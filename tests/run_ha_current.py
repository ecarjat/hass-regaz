"""Run the HA 2026.11 suite with the latest available custom-component harness."""

# The current harness imports httpx before HA 2026.11 installs its httpx2 alias,
# and references one removed logger cleanup helper. Preload HA and bridge only
# that test cleanup hook until the upstream harness supports 2026.11.
import homeassistant  # noqa: F401
import homeassistant.components.logger as logger
import pytest

if not hasattr(logger, "_clear_logger_overwrites"):
    logger._clear_logger_overwrites = lambda *args: None

raise SystemExit(pytest.main(["-q"]))
