"""DataUpdateCoordinator for Unraid integration."""
# ruff: noqa: SLF001, BLE001, B904, G004

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any
import weakref

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import UnraidApiClient, UnraidApiError
from .const import SPINDOWN_DEFAULT_MINUTES

_LOGGER = logging.getLogger(__name__)


class UnraidDataUpdateCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Enhanced class to manage fetching Unraid data with memory optimization."""

    api: UnraidApiClient
    config_entry: ConfigEntry

    def __init__(
        self, hass: HomeAssistant, api: UnraidApiClient, update_interval: int, name: str
    ) -> None:
        """Initialize the coordinator with enhanced memory management."""
        self.api = api
        self.name = name
        self._detail_update_counter = 0
        self._detail_update_frequency = 24  # Conservative default
        self._spindown_delay = 0
        self._respect_spindown = True

        # Memory optimization: Data caching with TTL
        self._data_cache: dict[str, dict[str, Any]] = {}
        self._cache_timestamps: dict[str, datetime] = {}
        self._cache_ttl: dict[str, int] = {
            "system_info": 300,      # 5 minutes - rarely changes
            "docker_containers": 60,  # 1 minute - can change frequently
            "vms": 60,               # 1 minute - can change frequently
            "notifications": 120,     # 2 minutes - moderate frequency
            "shares": 1800,          # 30 minutes - rarely changes
            "array_status": 30,      # 30 seconds - most dynamic
        }

        # Network efficiency: Batch API calls
        self._pending_api_calls: dict[str, asyncio.Task] = {}
        self._api_call_lock = asyncio.Lock()

        # Query preference caching (from enhanced API)
        self._successful_queries: dict[str, str] = {}

        # Add a flag to control disk details querying
        self.api._skip_disk_details = False

        super().__init__(
            hass,
            _LOGGER,
            name=name,
            update_interval=timedelta(seconds=update_interval),
        )

    def _is_cache_valid(self, data_type: str) -> bool:
        """Check if cached data is still valid."""
        if data_type not in self._cache_timestamps:
            return False

        cache_age = (datetime.now() - self._cache_timestamps[data_type]).total_seconds()
        return cache_age < self._cache_ttl.get(data_type, 60)

    def _get_cached_data(self, data_type: str) -> dict[str, Any] | None:
        """Get cached data if valid."""
        if self._is_cache_valid(data_type):
            return self._data_cache.get(data_type)
        return None

    def _cache_data(self, data_type: str, data: dict[str, Any]) -> None:
        """Cache data with timestamp."""
        self._data_cache[data_type] = data
        self._cache_timestamps[data_type] = datetime.now()

    async def _batch_api_call(self, call_name: str, api_func, *args, **kwargs) -> dict[str, Any]:
        """Execute API calls with batching to prevent duplicate requests."""
        async with self._api_call_lock:
            # Check if this call is already pending
            if call_name in self._pending_api_calls:
                try:
                    return await self._pending_api_calls[call_name]
                except Exception:
                    # If the pending call failed, remove it and try again
                    self._pending_api_calls.pop(call_name, None)

            # Create new API call task
            task = asyncio.create_task(api_func(*args, **kwargs))
            self._pending_api_calls[call_name] = task

            try:
                result = await task
                return result
            finally:
                # Clean up completed task
                self._pending_api_calls.pop(call_name, None)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from Unraid API with enhanced caching and batching."""
        try:
            async with asyncio.timeout(60):
                # Initialize data structure if it doesn't exist
                if not self.data:
                    self.data = {
                        "system_info": {},
                        "array_status": {},
                        "docker_containers": {},
                        "vms": {},
                        "shares": {},
                        "notifications": {},
                    }

                # Increment the detail update counter
                self._detail_update_counter += 1

                # Use concurrent fetching for independent data sources
                fetch_tasks = []

                # Always fetch array status (most critical and dynamic)
                fetch_tasks.append(self._fetch_array_status_cached())

                # Fetch other data based on cache validity
                if not self._is_cache_valid("system_info"):
                    fetch_tasks.append(self._fetch_system_info_cached())

                if not self._is_cache_valid("docker_containers"):
                    fetch_tasks.append(self._fetch_docker_containers_cached())

                if not self._is_cache_valid("vms"):
                    fetch_tasks.append(self._fetch_vms_cached())

                if not self._is_cache_valid("notifications"):
                    fetch_tasks.append(self._fetch_notifications_cached())

                # For shares, only query if it's time for a detailed update or cache is invalid
                if (self._detail_update_counter >= self._detail_update_frequency or
                    not self._is_cache_valid("shares")):
                    fetch_tasks.append(self._fetch_shares_cached())
                    # Reset counter if we did a detailed update
                    if self._detail_update_counter >= self._detail_update_frequency:
                        self._detail_update_counter = 0

                # Execute all fetch tasks concurrently
                if fetch_tasks:
                    await asyncio.gather(*fetch_tasks, return_exceptions=True)

                # Update data from cache
                for data_type in ["system_info", "array_status", "docker_containers",
                                "vms", "shares", "notifications"]:
                    cached_data = self._get_cached_data(data_type)
                    if cached_data is not None:
                        self.data[data_type] = cached_data

                # Clean up old cache entries to prevent memory leaks
                self._cleanup_cache()

                return self.data

        except UnraidApiError as err:
            if any(s in str(err) for s in ("401", "403", "Unauthorized", "Forbidden")):
                raise ConfigEntryAuthFailed from err
            raise UpdateFailed(f"Error communicating with Unraid API: {err}")
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}")

    def _cleanup_cache(self) -> None:
        """Clean up old cache entries to prevent memory leaks."""
        current_time = datetime.now()
        expired_keys = []

        for data_type, timestamp in self._cache_timestamps.items():
            cache_age = (current_time - timestamp).total_seconds()
            max_age = self._cache_ttl.get(data_type, 60) * 2  # Keep for 2x TTL

            if cache_age > max_age:
                expired_keys.append(data_type)

        for key in expired_keys:
            self._data_cache.pop(key, None)
            self._cache_timestamps.pop(key, None)
            _LOGGER.debug("Cleaned up expired cache entry: %s", key)

    # Enhanced cached fetch methods
    async def _fetch_system_info_cached(self) -> None:
        """Fetch system info with caching."""
        try:
            system_info = await self._batch_api_call("system_info", self.api.get_system_info)
            self._cache_data("system_info", system_info)
            _LOGGER.debug("Fetched and cached system info")
        except Exception as err:
            _LOGGER.error("Error fetching system info: %s", err)

    async def _fetch_docker_containers_cached(self) -> None:
        """Fetch docker containers with caching."""
        try:
            containers = await self._batch_api_call("docker_containers", self.api.get_docker_containers)
            self._cache_data("docker_containers", containers)
            _LOGGER.debug("Fetched and cached docker containers")
        except Exception as err:
            _LOGGER.error("Error fetching docker containers: %s", err)

    async def _fetch_vms_cached(self) -> None:
        """Fetch VMs with caching."""
        try:
            vms = await self._batch_api_call("vms", self.api.get_vms)
            self._cache_data("vms", vms)

            # Log VM count for debugging
            vm_domains = vms.get("vms", {}).get("domain", [])
            if not vm_domains:
                vm_domains = vms.get("vms", {}).get("domains", [])

            _LOGGER.debug("Fetched and cached %d VMs", len(vm_domains) if vm_domains else 0)
        except Exception as err:
            _LOGGER.error("Error fetching VMs: %s", err)

    async def _fetch_notifications_cached(self) -> None:
        """Fetch notifications with caching."""
        try:
            notifications = await self._batch_api_call("notifications", self.api.get_notifications, limit=10)
            self._cache_data("notifications", notifications)

            unread_count = notifications.get("overview", {}).get("unread", {}).get("total", 0)
            _LOGGER.debug("Fetched and cached %d unread notifications", unread_count)
        except Exception as err:
            _LOGGER.error("Error fetching notifications: %s", err)

    async def _fetch_shares_cached(self) -> None:
        """Fetch shares with caching."""
        try:
            shares = await self._batch_api_call("shares", self.api.get_shares)
            self._cache_data("shares", shares)
            _LOGGER.debug("Fetched and cached shares data")
        except Exception as err:
            _LOGGER.error("Error fetching shares: %s", err)

    async def _fetch_array_status_cached(self) -> None:
        """Fetch array status with caching and special disk handling."""
        try:
            # Set disk detail querying flag
            should_query_disk_details = (
                self._detail_update_counter >= self._detail_update_frequency
            )
            self.api._skip_disk_details = not should_query_disk_details

            if should_query_disk_details:
                _LOGGER.debug("Performing detailed disk query (cycle %s of %s)",
                            self._detail_update_counter, self._detail_update_frequency)
            else:
                _LOGGER.debug("Skipping detailed disk query to avoid waking disks (cycle %s of %s)",
                            self._detail_update_counter, self._detail_update_frequency)

            array_status = await self._batch_api_call("array_status", self.api.get_array_status)

            # Process spindown configuration
            self._process_spindown_config(array_status)

            # Process and cache array status data
            self._process_array_status_data(array_status)
            self._cache_data("array_status", self.data.get("array_status", {}))

        except Exception as err:
            _LOGGER.error("Error fetching array status: %s", err)

    async def _fetch_basic_system_data(self) -> None:
        """Fetch basic system data that doesn't risk waking disks."""
        # Basic system info without disk temperatures
        try:
            system_info = await self.api.get_system_info()
            _LOGGER.debug("System info data: %s", system_info)
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

            # Log VM count for debugging
            vm_domains = vms.get("vms", {}).get("domain", [])
            if not vm_domains:
                # Try alternative field name
                vm_domains = vms.get("vms", {}).get("domains", [])

            if vm_domains:
                _LOGGER.debug("Found %d VMs", len(vm_domains))
            else:
                _LOGGER.debug("No VMs found or VM service not available")
        except Exception as err:
            _LOGGER.error("Error fetching VMs: %s", err)

        # Notifications
        try:
            notifications = await self.api.get_notifications(limit=10)
            self.data["notifications"] = notifications

            # Log notification count for debugging
            unread_count = (
                notifications.get("overview", {}).get("unread", {}).get("total", 0)
            )
            _LOGGER.debug("Found %d unread notifications", unread_count)
        except Exception as err:
            _LOGGER.error("Error fetching notifications: %s", err)

    async def _fetch_array_status(self) -> None:
        """Fetch array status with special handling for disk data."""
        try:
            # Set a flag on the API client to control whether to query disk details
            should_query_disk_details = (
                self._detail_update_counter >= self._detail_update_frequency
            )
            self.api._skip_disk_details = not should_query_disk_details

            if should_query_disk_details:
                _LOGGER.debug(
                    "Performing detailed disk query (cycle %s of %s)",
                    self._detail_update_counter,
                    self._detail_update_frequency,
                )
            else:
                _LOGGER.debug(
                    "Skipping detailed disk query to avoid waking disks (cycle %s of %s)",
                    self._detail_update_counter,
                    self._detail_update_frequency,
                )

            array_status = await self.api.get_array_status()

            # Process spindown configuration
            self._process_spindown_config(array_status)

            # Process array status data
            self._process_array_status_data(array_status)

        except Exception as err:
            _LOGGER.error("Error fetching array status: %s", err)

    def _process_spindown_config(self, array_status: dict[str, Any]) -> None:
        """Process spindown configuration from array status."""
        if "spindown_config" not in array_status:
            return

        spindown_config = array_status.get("spindown_config", {})
        spindown_delay_str = spindown_config.get("delay", "0")

        try:
            # Convert spindown delay to minutes based on Unraid's ACTUAL settings
            # According to Unraid documentation and web interface:
            # "0" = 30 minutes (default)
            # "15" = 15 minutes
            # "30" = 30 minutes
            # "45" = 45 minutes
            # "1" through "9" = hours
            # "-1" or "never" = Never spin down

            spindown_delay_value = int(spindown_delay_str)

            if spindown_delay_value == 0:
                # Default/unconfigured Unraid setting
                # In Unraid, delay=0 means "use default" which is typically 30 minutes
                # but could vary based on Unraid version or user's previous configuration
                spindown_delay = SPINDOWN_DEFAULT_MINUTES
                _LOGGER.debug("Spindown set to default/unconfigured (using %d minutes)", spindown_delay)
            elif spindown_delay_value == -1:
                # Never spin down - set a very high value
                spindown_delay = 24 * 60 * 7  # 1 week in minutes
                _LOGGER.debug("Spindown set to NEVER")
            elif 1 <= spindown_delay_value <= 45:
                # Values 1-45: check if it's minutes or hours
                if spindown_delay_value in [15, 30, 45]:
                    # These are minute values
                    spindown_delay = spindown_delay_value
                    _LOGGER.debug("Spindown set to %s minutes", spindown_delay)
                else:
                    # Values 1-9 (excluding 15,30,45) are hours
                    spindown_delay = spindown_delay_value * 60
                    _LOGGER.debug(
                        "Spindown set to %s hours (%s minutes)",
                        spindown_delay_value,
                        spindown_delay,
                    )
            else:
                # Fallback for unexpected values
                spindown_delay = 30  # Default to 30 minutes
                _LOGGER.warning("Unexpected spindown delay value %s, defaulting to 30 minutes", spindown_delay_value)

            self._spindown_delay = spindown_delay
            self._adjust_detail_update_frequency(spindown_delay)

        except (ValueError, TypeError):
            _LOGGER.warning("Invalid spindown delay value: %s, defaulting to 30 minutes", spindown_delay_str)
            self._spindown_delay = 30
            self._adjust_detail_update_frequency(30)

    def _adjust_detail_update_frequency(self, spindown_delay: int) -> None:
        """Adjust detail update frequency based on spindown delay."""
        if spindown_delay <= 0 or self.update_interval is None:
            return

        update_interval_minutes = self.update_interval.total_seconds() / 60
        if update_interval_minutes <= 0:
            return

        # Add a buffer of 2x the spindown delay to be safe
        # But ensure we have at least 24 cycles (default)
        self._detail_update_frequency = max(
            24,  # Minimum of 24 cycles
            int((spindown_delay * 2) / update_interval_minutes),
        )
        _LOGGER.debug(
            "Adjusted detail update frequency to %s cycles based on spindown delay of %s minutes",
            self._detail_update_frequency,
            spindown_delay,
        )

    def _process_array_status_data(self, array_status: dict[str, Any]) -> None:
        """Process array status data with special handling for disk data."""
        # If this is the first time, store the complete result
        if not self.data.get("array_status"):
            self.data["array_status"] = array_status
            return

        # Update only the non-disk parts of the array status
        if "array" in array_status:
            self._update_array_data(array_status)

        # Update spindown configuration
        if "spindown_config" in array_status:
            self.data["array_status"]["spindown_config"] = array_status[
                "spindown_config"
            ]

        # Update flash drive data
        if "flash" in array_status:
            self.data["array_status"]["flash"] = array_status["flash"]

    def _update_array_data(self, array_status: dict[str, Any]) -> None:
        """Update array data with special handling for disks."""
        array_data = array_status.get("array", {})

        # Update array state and capacity info
        if "state" in array_data:
            self.data["array_status"]["array"]["state"] = array_data["state"]

        if "capacity" in array_data:
            self.data["array_status"]["array"]["capacity"] = array_data["capacity"]

        # For cache drives (SSDs), we can safely update them without wakeup concerns
        if "caches" in array_data:
            self.data["array_status"]["array"]["caches"] = array_data["caches"]

        # For disks and parity, merge the new data with existing data to preserve values
        if "disks" in array_data:
            self._update_disk_data(array_data["disks"])

        # For parity disks, similar approach but simpler since they don't have filesystem data
        if "parities" in array_data:
            if not self.data["array_status"]["array"].get("parities"):
                self.data["array_status"]["array"]["parities"] = array_data["parities"]

    def _update_disk_data(self, new_disks: list[dict[str, Any]]) -> None:
        """Update disk data with special handling for standby disks."""
        # If we don't have any disk info yet, use the new data
        if not self.data["array_status"]["array"].get("disks"):
            self.data["array_status"]["array"]["disks"] = new_disks
            return

        # Otherwise, merge the data to preserve values for standby disks
        existing_disks = self.data["array_status"]["array"]["disks"]

        # Create a map of existing disks by ID for quick lookup
        existing_disk_map = {
            disk.get("id"): disk for disk in existing_disks if disk.get("id")
        }

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
                self._merge_disk_data(
                    merged_disks, new_disk, existing_disk_map[disk_id], disk_id
                )
            else:
                # If no existing data, use the new disk data
                merged_disks.append(new_disk)

        # Update the disks with the merged list
        self.data["array_status"]["array"]["disks"] = merged_disks

    def _merge_disk_data(
        self,
        merged_disks: list[dict[str, Any]],
        new_disk: dict[str, Any],
        existing_disk: dict[str, Any],
        disk_id: str,
    ) -> None:
        """Merge disk data preserving filesystem info for standby disks."""
        # Get the disk states
        new_state = new_disk.get("state", "").upper()
        existing_state = existing_disk.get("state", "").upper()

        # If the disk was active but is now in standby, preserve the filesystem data
        if existing_state == "ACTIVE" and new_state == "STANDBY":
            # Create a merged disk with preserved filesystem data
            merged_disk = dict(new_disk)  # Start with new disk data

            # Preserve filesystem data from the existing disk
            for fs_field in ("fsSize", "fsFree", "fsUsed"):
                if fs_field in existing_disk and existing_disk[fs_field] != "0":
                    merged_disk[fs_field] = existing_disk[fs_field]

            # Add the merged disk to the list
            merged_disks.append(merged_disk)
            _LOGGER.debug(
                f"Preserved filesystem data for disk {disk_id} in standby mode"
            )
        else:
            # For other state transitions, use the new disk data
            merged_disks.append(new_disk)

    async def _fetch_detailed_data(self) -> None:
        """Fetch detailed data that should only be queried occasionally."""
        _LOGGER.debug(
            "Performing detailed update (cycle %s of %s)",
            self._detail_update_counter,
            self._detail_update_frequency,
        )

        # Shares information - but only once every N cycles based on spindown delay
        try:
            shares = await self.api.get_shares()
            self.data["shares"] = shares
        except Exception as err:
            _LOGGER.error("Error fetching shares: %s", err)
