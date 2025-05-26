"""Diagnostics support for Unraid Connect."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from .const import DOMAIN

REDACT_FIELDS = {CONF_API_KEY, "token", "credentials", "uuid", "id"}
REDACT_CONFIG = {"entry_id", CONF_API_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    # Get the coordinator for this entry
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]

    # Get the raw API data
    data = coordinator.data

    # Redact sensitive information
    redacted_data = async_redact_data(data, REDACT_FIELDS)

    # Add configuration information
    redacted_config = async_redact_data(entry.as_dict(), REDACT_CONFIG)

    # Return both configuration and data
    return {
        "config": redacted_config,
        "data": redacted_data,
        "last_update_success": coordinator.last_update_success,
        "last_update_time": coordinator.last_update_time.isoformat()
        if coordinator.last_update_time
        else None,
        "update_interval": str(coordinator.update_interval)
        if coordinator.update_interval
        else None,
    }
