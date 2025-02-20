"""
Core initialization file for the Unraid integration.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_HOST,
    CONF_API_KEY,
    CONF_SCAN_INTERVAL,
    Platform,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import UnraidAPI, UnraidAPIError, UnraidConnectionError, UnraidAuthError
from .coordinator import UnraidDataUpdateCoordinator
from .const import (
    DOMAIN,
    LOGGER,
    DEFAULT_SCAN_INTERVAL,
)

PLATFORMS: Final[list[Platform]] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Unraid from a config entry."""
    LOGGER.info("Setting up Unraid integration for %s", entry.data[CONF_HOST])
    
    host = entry.data[CONF_HOST]
    api_key = entry.data[CONF_API_KEY]
    
    # Initialize the API client
    LOGGER.debug("Initializing GraphQL transport for %s", host)
    session = async_get_clientsession(hass)
    
    try:
        # Create API wrapper instance
        api = await UnraidAPI.create(hass, host, api_key)
        LOGGER.debug("Unraid API wrapper created successfully")
    except UnraidConnectionError as err:
        LOGGER.error("Failed to connect to Unraid server: %s", err)
        raise ConfigEntryNotReady(f"Failed to connect to Unraid server: {err}") from err
    except UnraidAuthError as err:
        LOGGER.error("Authentication failed with Unraid API: %s", err)
        raise ConfigEntryNotReady(f"Authentication failed: {err}") from err
    except UnraidAPIError as err:
        LOGGER.error("Error initializing Unraid API: %s", err)
        raise ConfigEntryNotReady(f"API initialization error: {err}") from err
    except Exception as err:
        LOGGER.error("Failed to initialize GraphQL client: %s", err, exc_info=True)
        raise ConfigEntryNotReady(f"Failed to connect to Unraid server: {err}") from err

    # Get scan interval from options or use default
    scan_interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    update_interval = timedelta(seconds=scan_interval)

    # Set up the DataUpdateCoordinator
    LOGGER.info("Creating data update coordinator with %s second interval", scan_interval)
    coordinator = UnraidDataUpdateCoordinator(
        hass,
        api,
        update_interval=update_interval,
    )

    # Fetch initial data
    LOGGER.info("Performing initial data refresh")
    try:
        await coordinator.async_config_entry_first_refresh()
        LOGGER.info("Initial data refresh successful")
    except ConfigEntryNotReady:
        LOGGER.error("Initial data refresh failed - retrying later")
        await api.close()
        raise
    except Exception as err:
        LOGGER.error("Initial data refresh failed: %s", err, exc_info=True)
        await api.close()
        raise ConfigEntryNotReady(f"Failed to fetch initial data: {err}") from err

    # Store the setup objects in hass.data for access by the platforms
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "api": api,
    }
    LOGGER.debug("Integration data stored in hass.data")

    # Set up all the platforms
    LOGGER.info("Setting up platforms: %s", PLATFORMS)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    # Register services
    # await register_services(hass)
    
    LOGGER.info("Unraid integration setup completed successfully")
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    LOGGER.info("Unloading Unraid integration for %s", entry.data[CONF_HOST])
    
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        LOGGER.debug("Platforms unloaded successfully")
        
        # Close the API client session gracefully
        if DOMAIN in hass.data and entry.entry_id in hass.data[DOMAIN]:
            if "api" in hass.data[DOMAIN][entry.entry_id]:
                api = hass.data[DOMAIN][entry.entry_id]["api"]
                await api.close()
                LOGGER.debug("Closed API session")
        
        # Clean up hass.data
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
        LOGGER.debug("Removed entry data from hass.data")
        LOGGER.info("Unraid integration unloaded successfully")
    else:
        LOGGER.warning("Failed to unload one or more platforms")
    
    return unload_ok

# Future services registration function
# async def register_services(hass: HomeAssistant) -> None:
#     """Register integration services."""
#     ...
