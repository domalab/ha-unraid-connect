"""The Unraid integration."""
import asyncio
import logging
from typing import Any, Dict

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_HOST,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_VERIFY_SSL,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession
import homeassistant.helpers.config_validation as cv

from .api import UnraidApiClient, UnraidApiError
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    SERVICE_CANCEL_PARITY_CHECK,
    SERVICE_PAUSE_PARITY_CHECK,
    SERVICE_RESUME_PARITY_CHECK,
    SERVICE_REBOOT,
    SERVICE_SHUTDOWN,
    SERVICE_START_ARRAY,
    SERVICE_START_PARITY_CHECK,
    SERVICE_STOP_ARRAY,
)
from .coordinator import UnraidDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
]

# Service schema for parity check with correction option
START_PARITY_SCHEMA = vol.Schema(
    {
        vol.Optional("correct", default=False): cv.boolean,
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Unraid from a config entry."""
    # Get config entry data
    host = entry.data[CONF_HOST]
    api_key = entry.data[CONF_API_KEY]
    name = entry.data.get(CONF_NAME, host)
    verify_ssl = entry.options.get(CONF_VERIFY_SSL, entry.data.get(CONF_VERIFY_SSL, True))
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )

    # Create API client
    session = async_get_clientsession(hass)
    client = UnraidApiClient(
        host=host,
        api_key=api_key,
        session=session,
        verify_ssl=verify_ssl,
    )

    # Create coordinator
    coordinator = UnraidDataUpdateCoordinator(
        hass=hass,
        api=client,
        update_interval=scan_interval,
        name=name,
    )

    # Fetch initial data
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady as err:
        raise ConfigEntryNotReady(f"Failed to get initial data: {err}") from err

    # Store coordinator and API client
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "name": name,
    }

    # Register services
    async def start_array(call: ServiceCall) -> None:
        """Start the array."""
        try:
            await client.start_array()
            await coordinator.async_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to start array: %s", err)

    async def stop_array(call: ServiceCall) -> None:
        """Stop the array."""
        try:
            await client.stop_array()
            await coordinator.async_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to stop array: %s", err)

    async def start_parity_check(call: ServiceCall) -> None:
        """Start parity check."""
        correct = call.data.get("correct", False)
        try:
            await client.start_parity_check(correct=correct)
            await coordinator.async_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to start parity check: %s", err)

    async def pause_parity_check(call: ServiceCall) -> None:
        """Pause parity check."""
        try:
            await client.pause_parity_check()
            await coordinator.async_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to pause parity check: %s", err)

    async def resume_parity_check(call: ServiceCall) -> None:
        """Resume parity check."""
        try:
            await client.resume_parity_check()
            await coordinator.async_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to resume parity check: %s", err)

    async def cancel_parity_check(call: ServiceCall) -> None:
        """Cancel parity check."""
        try:
            await client.cancel_parity_check()
            await coordinator.async_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to cancel parity check: %s", err)

    async def reboot(call: ServiceCall) -> None:
        """Reboot server."""
        try:
            await client.reboot()
        except UnraidApiError as err:
            _LOGGER.error("Failed to reboot server: %s", err)

    async def shutdown(call: ServiceCall) -> None:
        """Shutdown server."""
        try:
            await client.shutdown()
        except UnraidApiError as err:
            _LOGGER.error("Failed to shutdown server: %s", err)

    # Register services
    hass.services.async_register(DOMAIN, SERVICE_START_ARRAY, start_array)
    hass.services.async_register(DOMAIN, SERVICE_STOP_ARRAY, stop_array)
    hass.services.async_register(
        DOMAIN, SERVICE_START_PARITY_CHECK, start_parity_check, schema=START_PARITY_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_PAUSE_PARITY_CHECK, pause_parity_check)
    hass.services.async_register(DOMAIN, SERVICE_RESUME_PARITY_CHECK, resume_parity_check)
    hass.services.async_register(DOMAIN, SERVICE_CANCEL_PARITY_CHECK, cancel_parity_check)
    hass.services.async_register(DOMAIN, SERVICE_REBOOT, reboot)
    hass.services.async_register(DOMAIN, SERVICE_SHUTDOWN, shutdown)

    # Set up all platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload entry when options change
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove entry from data
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry."""
    await hass.config_entries.async_reload(entry.entry_id)