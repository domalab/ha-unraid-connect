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
        # Default to a conservative value, will be updated from Unraid settings
        self._detail_update_frequency = 24  # Only query disk details once every 24 cycles
        self._spindown_delay = 0  # Will be updated from Unraid settings
        self._respect_spindown = True  # Always respect spindown settings
        
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
                
                # For array status and disks, always get a safe version that doesn't wake sleeping disks
                # Our modified API implementation ensures disks stay asleep
                try:
                    # Set a flag on the API client to control whether to query disk details
                    # Only query disk details if it's time for a detailed update
                    should_query_disk_details = self._detail_update_counter >= self._detail_update_frequency
                    self.api._skip_disk_details = not should_query_disk_details
                    
                    if should_query_disk_details:
                        _LOGGER.debug("Performing detailed disk query (cycle %s of %s)", 
                                     self._detail_update_counter, self._detail_update_frequency)
                        # Reset counter for next time
                        self._detail_update_counter = 0
                    else:
                        _LOGGER.debug("Skipping detailed disk query to avoid waking disks (cycle %s of %s)",
                                     self._detail_update_counter, self._detail_update_frequency)
                    
                    array_status = await self.api.get_array_status()
                    
                    # Update spindown configuration if available
                    if "spindown_config" in array_status:
                        spindown_config = array_status.get("spindown_config", {})
                        spindown_delay_str = spindown_config.get("delay", "0")
                        
                        try:
                            # Convert spindown delay to minutes based on Unraid's settings
                            # 0 = Never, 15/30/45 = minutes, 1-9 = hours
                            spindown_delay_value = int(spindown_delay_str)
                            
                            if spindown_delay_value == 0:
                                # Never spin down - set a very high value
                                spindown_delay = 24 * 60 * 7  # 1 week in minutes
                                _LOGGER.debug("Spindown set to NEVER")
                            elif spindown_delay_value <= 45:
                                # Values 15, 30, 45 are in minutes
                                spindown_delay = spindown_delay_value
                                _LOGGER.debug("Spindown set to %s minutes", spindown_delay)
                            else:
                                # Values 1-9 are in hours
                                spindown_delay = spindown_delay_value * 60
                                _LOGGER.debug("Spindown set to %s hours (%s minutes)", 
                                             spindown_delay_value, spindown_delay)
                                
                            self._spindown_delay = spindown_delay
                            
                            # Adjust detail update frequency based on spindown delay
                            # Make sure we query less frequently than the spindown delay
                            # Use the update interval to calculate how many cycles to wait
                            if spindown_delay > 0:
                                update_interval_minutes = self.update_interval.total_seconds() / 60
                                if update_interval_minutes > 0:
                                    # Add a buffer of 2x the spindown delay to be safe
                                    # But ensure we have at least 24 cycles (default)
                                    self._detail_update_frequency = max(
                                        24,  # Minimum of 24 cycles
                                        int((spindown_delay * 2) / update_interval_minutes)
                                    )
                                    _LOGGER.debug(
                                        "Adjusted detail update frequency to %s cycles based on spindown delay of %s minutes",
                                        self._detail_update_frequency,
                                        spindown_delay
                                    )
                        except (ValueError, TypeError):
                            _LOGGER.warning("Invalid spindown delay value: %s", spindown_delay_str)
                    
                    # Update array status data
                    self.data["array_status"] = array_status
                    
                    # Get shares data
                    try:
                        shares = await self.api.get_shares()
                        self.data["shares"] = shares
                    except Exception as err:
                        _LOGGER.error("Error fetching shares: %s", err)
                    
                    # Get detailed disk information if applicable
                    if should_query_disk_details:
                        try:
                            disks_info = await self.api.get_disks_info()
                            self.data["disks_info"] = disks_info
                        except Exception as err:
                            _LOGGER.error("Error fetching disk info: %s", err)
                    
                    # Get network information
                    try:
                        network_info = await self.api.get_network_info()
                        self.data["network_info"] = network_info
                    except Exception as err:
                        _LOGGER.error("Error fetching network info: %s", err)
                    
                    # Get parity history
                    try:
                        parity_history = await self.api.get_parity_history()
                        self.data["parity_history"] = parity_history
                    except Exception as err:
                        _LOGGER.error("Error fetching parity history: %s", err)
                    
                except Exception as err:
                    _LOGGER.error("Error fetching array status: %s", err)

                return self.data
                
        except asyncio.TimeoutError as err:
            _LOGGER.error("Timeout error updating from Unraid API: %s", err)
            raise UpdateFailed(f"Timeout error communicating with API: {err}")
        except UnraidApiError as err:
            _LOGGER.error("Error talking to Unraid API: %s", err)
            if "Auth" in str(err) or "401" in str(err) or "403" in str(err):
                raise ConfigEntryAuthFailed(f"Auth failed: {err}")
            raise UpdateFailed(f"Error communicating with API: {err}")
        except Exception as err:
            _LOGGER.exception("Unknown error occurred: %s", err)
            raise UpdateFailed(f"Unknown error occurred: {err}")