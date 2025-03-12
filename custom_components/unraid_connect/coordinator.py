"""DataUpdateCoordinator for Unraid integration."""
import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict

import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed

from .api import UnraidApiClient, UnraidApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class UnraidDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Unraid data."""

    def __init__(
        self, hass: HomeAssistant, api: UnraidApiClient, update_interval: int, name: str
    ):
        """Initialize the coordinator."""
        self.api = api
        self.name = name
        self._detail_update_counter = 0  # Counter to track update cycles for full detail updates
        # Use much less frequent detailed queries to allow disks to enter standby
        self._detail_update_frequency = 24  # Only query disk details once every 24 cycles (every 24 minutes with default 60s interval)
        
        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from Unraid API."""
        try:
            async with async_timeout.timeout(60):
                # Initialize data structure if it doesn't exist
                if not self.data:
                    self.data = {
                        "system_info": {},
                        "array_status": {},
                        "docker_containers": {},
                        "vms": {},
                        "shares": {},
                    }

                # Increment the detail update counter
                self._detail_update_counter += 1
                
                # Always fetch critical data on every update (non-disk data)
                # Basic system info without disk temperatures
                try:
                    system_info = await self.api.get_system_info()
                    self.data["system_info"] = system_info
                except Exception as err:
                    _LOGGER.error("Error fetching system info: %s", err)
                
                # Docker containers
                try:
                    docker_containers = await self.api.get_docker_containers()
                    self.data["docker_containers"] = docker_containers
                except Exception as err:
                    _LOGGER.error("Error fetching docker containers: %s", err)
                
                # VMs
                try:
                    vms = await self.api.get_vms()
                    self.data["vms"] = vms
                except Exception as err:
                    _LOGGER.error("Error fetching VMs: %s", err)
                
                # For shares, very rarely query them due to potential disk wakeup
                if self._detail_update_counter >= self._detail_update_frequency:
                    # Shares information - but only once every 24 cycles (4 hours at 10min intervals)
                    try:
                        shares = await self.api.get_shares()
                        self.data["shares"] = shares
                    except Exception as err:
                        _LOGGER.error("Error fetching shares: %s", err)
                        
                    # Reset counter
                    self._detail_update_counter = 0

                # For array status and disks, always get a safe version that doesn't wake sleeping disks
                # Our modified API implementation ensures disks stay asleep
                try:
                    array_status = await self.api.get_array_status()
                    
                    # If this is the first time, store the complete result
                    if not self.data.get("array_status"):
                        self.data["array_status"] = array_status
                    else:
                        # Update only the non-disk parts of the array status
                        if "array" in array_status:
                            # Update array state and capacity info
                            if "state" in array_status["array"]:
                                self.data["array_status"]["array"]["state"] = array_status["array"]["state"]
                            
                            if "capacity" in array_status["array"]:
                                self.data["array_status"]["array"]["capacity"] = array_status["array"]["capacity"]
                            
                            # For cache drives (SSDs), we can safely update them without wakeup concerns
                            if "caches" in array_status["array"]:
                                self.data["array_status"]["array"]["caches"] = array_status["array"]["caches"]
                            
                            # For disks and parity, only update them if they weren't there before
                            # or if we don't have any disk info yet
                            if not self.data["array_status"]["array"].get("disks"):
                                self.data["array_status"]["array"]["disks"] = array_status["array"]["disks"]
                            
                            if not self.data["array_status"]["array"].get("parities"):
                                self.data["array_status"]["array"]["parities"] = array_status["array"]["parities"]
                        
                        # Update spindown configuration
                        if "spindown_config" in array_status:
                            self.data["array_status"]["spindown_config"] = array_status["spindown_config"]
                except Exception as err:
                    _LOGGER.error("Error fetching array status: %s", err)

                # Return data even if some requests failed
                return self.data

        except UnraidApiError as err:
            if any(s in str(err) for s in ("401", "403", "Unauthorized", "Forbidden")):
                raise ConfigEntryAuthFailed from err
            raise UpdateFailed(f"Error communicating with Unraid API: {err}")
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}")