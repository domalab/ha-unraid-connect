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
                            
                            # For disks and parity, merge the new data with existing data to preserve values
                            if "disks" in array_status["array"]:
                                # If we don't have any disk info yet, use the new data
                                if not self.data["array_status"]["array"].get("disks"):
                                    self.data["array_status"]["array"]["disks"] = array_status["array"]["disks"]
                                else:
                                    # Otherwise, merge the data to preserve values for standby disks
                                    existing_disks = self.data["array_status"]["array"]["disks"]
                                    new_disks = array_status["array"]["disks"]
                                    
                                    # Create a map of existing disks by ID for quick lookup
                                    existing_disk_map = {disk.get("id"): disk for disk in existing_disks if disk.get("id")}
                                    
                                    # Create a new list to store the merged disks
                                    merged_disks = []
                                    
                                    # Process each new disk
                                    for new_disk in new_disks:
                                        disk_id = new_disk.get("id")
                                        if not disk_id:
                                            # If no ID, just use the new disk data
                                            merged_disks.append(new_disk)
                                            continue
                                            
                                        # Check if we have existing data for this disk
                                        if disk_id in existing_disk_map:
                                            existing_disk = existing_disk_map[disk_id]
                                            
                                            # Get the disk states
                                            new_state = new_disk.get("state", "").upper()
                                            existing_state = existing_disk.get("state", "").upper()
                                            
                                            # If the disk was active but is now in standby, preserve the filesystem data
                                            if existing_state == "ACTIVE" and new_state == "STANDBY":
                                                # Create a merged disk with preserved filesystem data
                                                merged_disk = dict(new_disk)  # Start with new disk data
                                                
                                                # Preserve filesystem data from the existing disk
                                                if "fsSize" in existing_disk and existing_disk["fsSize"] != "0":
                                                    merged_disk["fsSize"] = existing_disk["fsSize"]
                                                if "fsFree" in existing_disk and existing_disk["fsFree"] != "0":
                                                    merged_disk["fsFree"] = existing_disk["fsFree"]
                                                if "fsUsed" in existing_disk and existing_disk["fsUsed"] != "0":
                                                    merged_disk["fsUsed"] = existing_disk["fsUsed"]
                                                
                                                # Add the merged disk to the list
                                                merged_disks.append(merged_disk)
                                                _LOGGER.debug(f"Preserved filesystem data for disk {disk_id} in standby mode")
                                            else:
                                                # For other state transitions, use the new disk data
                                                merged_disks.append(new_disk)
                                        else:
                                            # If no existing data, use the new disk data
                                            merged_disks.append(new_disk)
                                    
                                    # Update the disks with the merged list
                                    self.data["array_status"]["array"]["disks"] = merged_disks
                            
                            # For parity disks, similar approach but simpler since they don't have filesystem data
                            if "parities" in array_status["array"]:
                                if not self.data["array_status"]["array"].get("parities"):
                                    self.data["array_status"]["array"]["parities"] = array_status["array"]["parities"]
                        
                        # Update spindown configuration
                        if "spindown_config" in array_status:
                            self.data["array_status"]["spindown_config"] = array_status["spindown_config"]
                            
                        # Update flash drive data
                        if "flash" in array_status:
                            self.data["array_status"]["flash"] = array_status["flash"]
                except Exception as err:
                    _LOGGER.error("Error fetching array status: %s", err)
                
                # For shares, only query if it's time for a detailed update and respect spindown settings
                if self._detail_update_counter >= self._detail_update_frequency:
                    _LOGGER.debug("Performing detailed update (cycle %s of %s)", 
                                 self._detail_update_counter, self._detail_update_frequency)
                    
                    # Shares information - but only once every N cycles based on spindown delay
                    try:
                        shares = await self.api.get_shares()
                        self.data["shares"] = shares
                    except Exception as err:
                        _LOGGER.error("Error fetching shares: %s", err)
                        
                    # Reset counter
                    self._detail_update_counter = 0

                # Return data even if some requests failed
                return self.data

        except UnraidApiError as err:
            if any(s in str(err) for s in ("401", "403", "Unauthorized", "Forbidden")):
                raise ConfigEntryAuthFailed from err
            raise UpdateFailed(f"Error communicating with Unraid API: {err}")
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}")