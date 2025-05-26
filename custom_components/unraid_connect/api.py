"""API for Unraid."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from typing import Any

import aiohttp
from aiohttp.client_exceptions import ClientResponseError

from .const import (
    API_TIMEOUT,
    BASE_GRAPHQL_URL,
    DISK_STATE_ACTIVE,
    DISK_STATE_STANDBY,
    DISK_STATE_SPUN_DOWN,
    DISK_STATE_UNKNOWN,
    NON_ROTATIONAL_DISK_TYPES,
    SPINDOWN_DEFAULT,
    SPINDOWN_NEVER,
    SPINDOWN_DEFAULT_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


def extract_id(prefixed_id: str) -> str:
    """Extract the actual ID from a prefixed ID.

    The Unraid API uses a special PrefixedID scalar type for entity IDs.
    This type prefixes the underlying ID with the server identifier on output.

    Args:
        prefixed_id: The prefixed ID in the format "serverId:actualId"

    Returns:
        The actual ID without the server prefix

    """
    if ":" in prefixed_id:
        return prefixed_id.split(":", 1)[1]
    return prefixed_id


class UnraidApiError(Exception):
    """Exception to indicate an error from the Unraid API."""

    def __init__(self, status: str, message: str) -> None:
        """Initialize the exception."""
        super().__init__(message)
        self.status = status
        self.message = message


class UnraidApiClient:
    """API client for Unraid."""

    # ruff: noqa: TRY300, TRY301, BLE001

    def __init__(
        self,
        host: str,
        api_key: str,
        session: aiohttp.ClientSession,
        verify_ssl: bool = True,
    ) -> None:
        """Initialize the API client."""
        self.host = host.rstrip("/")
        self.api_key = api_key
        self.session = session
        self.verify_ssl = verify_ssl
        self.redirect_url: str | None = None
        self._skip_disk_details: bool = False
        self.version: str = "Unknown"

        # Disk state management for intelligent spindown awareness
        self._disk_states: dict[str, dict[str, Any]] = {}
        self._spindown_config: dict[str, Any] = {}
        self._last_disk_state_check: float = 0
        self._disk_state_cache_duration = 30  # Cache disk states for 30 seconds

        # Standard API key header
        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "Accept": "application/json",
            # Add Origin header to help with CORS - use the target host as origin
            # This helps bypass CORS restrictions when the server doesn't have extraOrigins configured
            "Origin": self.host,
            "Referer": f"{self.host}/dashboard",
        }

        self.api_url = f"{self.host}{BASE_GRAPHQL_URL}"

    async def discover_redirect_url(self) -> None:
        """Discover and store the redirect URL if the server uses one."""
        try:
            async with self.session.get(
                self.api_url, allow_redirects=False, ssl=self.verify_ssl
            ) as resp:
                if resp.status == 302 and "Location" in resp.headers:
                    location = resp.headers["Location"]
                    if isinstance(location, str):
                        self.redirect_url = location
                        _LOGGER.debug("Discovered redirect URL: %s", self.redirect_url)

                    # Update our endpoint to use the redirect URL
                    if self.redirect_url is not None:
                        self.api_url = self.redirect_url

                    # If the redirect is to a domain name, extract it for the Origin header
                    if self.redirect_url is not None:
                        domain_match = re.search(r"https?://([^/]+)", self.redirect_url)
                        if domain_match:
                            domain = domain_match.group(1)
                            # Set the Origin and Referer to match the redirect URL's domain
                            # This is crucial for CORS to work properly
                            protocol = (
                                "https"
                                if self.redirect_url.startswith("https")
                                else "http"
                            )
                            self.headers["Host"] = domain
                            self.headers["Origin"] = f"{protocol}://{domain}"
                            self.headers["Referer"] = f"{protocol}://{domain}/dashboard"
                            _LOGGER.debug("Updated headers to use domain: %s", domain)

        except (TimeoutError, aiohttp.ClientError) as err:
            _LOGGER.warning("Could not discover redirect URL: %s", err)

    async def _send_graphql_request(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send a GraphQL request to the Unraid API."""
        # Clean up the query by removing comments and extra whitespace
        # This is important for GraphQL syntax
        cleaned_lines = []
        for line in query.split("\n"):
            # Remove comments (lines starting with #)
            if "#" in line:
                line = line.split("#")[0]

            stripped = line.strip()
            if stripped:
                cleaned_lines.append(stripped)

        # Join with a single space
        query = " ".join(cleaned_lines)

        # Extract operation name if present
        operation_name: str | None = None
        if "query " in query and "{" in query:
            # Extract the operation name from queries like "query OperationName { ... }"
            match = re.search(r"query\s+([A-Za-z0-9_]+)\s*{", query)
            if match:
                operation_name = match.group(1)
        elif "mutation " in query and "{" in query:
            # Extract the operation name from mutations
            match = re.search(r"mutation\s+([A-Za-z0-9_]+)\s*[({]", query)
            if match:
                operation_name = match.group(1)

        # Prepare the request payload
        json_data: dict[str, Any] = {"query": query}
        if operation_name:
            json_data["operationName"] = operation_name
        if variables:
            json_data["variables"] = variables

        try:
            async with asyncio.timeout(API_TIMEOUT):
                _LOGGER.debug(
                    "Sending GraphQL request to %s with headers %s",
                    self.api_url,
                    self.headers,
                )
                _LOGGER.debug("Request data: %s", json_data)

                async with self.session.post(
                    self.api_url,
                    json=json_data,
                    headers=self.headers,
                    ssl=self.verify_ssl,
                ) as resp:
                    response_text = await resp.text()
                    _LOGGER.debug(
                        "Response status: %s, body: %s", resp.status, response_text
                    )

                    def _raise_api_error(status, text):
                        raise UnraidApiError(
                            str(status), f"Error from Unraid API: {text}"
                        )

                    if resp.status != 200:
                        _raise_api_error(resp.status, response_text)

                    try:
                        response_json = await resp.json()
                    except ValueError as err:
                        raise UnraidApiError(
                            "Parse Error",
                            f"Failed to parse JSON response: {response_text}",
                        ) from err

                    # Check for GraphQL errors
                    if "errors" in response_json:
                        errors = response_json["errors"]

                        def _raise_graphql_error(message):
                            raise UnraidApiError("GraphQL Error", message)

                        error_message = (
                            errors[0]["message"] if errors else "Unknown GraphQL error"
                        )
                        _raise_graphql_error(error_message)

                    return response_json

        except TimeoutError as err:
            raise UnraidApiError(
                "Timeout", f"Timeout when connecting to Unraid API: {err}"
            ) from err
        except ClientResponseError as err:
            raise UnraidApiError(
                str(err.status), f"Error connecting to Unraid API: {err}"
            ) from err
        except Exception as err:
            raise UnraidApiError("Unknown", f"Unknown error: {err}") from err

    async def _get_disk_states(self, force_refresh: bool = False) -> dict[str, dict[str, Any]]:
        """Get current disk states with caching to avoid frequent API calls."""
        import time

        current_time = time.time()

        # Use cached data if it's still fresh and not forcing refresh
        if (
            not force_refresh
            and self._disk_states
            and (current_time - self._last_disk_state_check) < self._disk_state_cache_duration
        ):
            _LOGGER.debug("Using cached disk states")
            return self._disk_states

        try:
            # Query basic disk information that doesn't wake sleeping disks
            # According to the official Unraid API schema, this query is safe
            disk_state_query = """
            query GetDiskStates {
                disks {
                    id
                    name
                    device
                    type
                    vendor
                    size
                }
            }
            """

            _LOGGER.debug("Fetching current disk states")
            response = await self._send_graphql_request(disk_state_query)

            if "data" in response and "disks" in response["data"]:
                disks = response["data"]["disks"]

                # Update our disk states cache
                self._disk_states = {}
                for disk in disks:
                    disk_id = disk.get("id")
                    if disk_id:
                        # Determine if this is a non-rotational disk (SSD/NVMe)
                        disk_type = disk.get("type", "").upper()
                        is_non_rotational = disk_type in NON_ROTATIONAL_DISK_TYPES

                        self._disk_states[disk_id] = {
                            "id": disk_id,
                            "name": disk.get("name"),
                            "device": disk.get("device"),
                            "type": disk_type,
                            "vendor": disk.get("vendor"),
                            "size": disk.get("size"),
                            "is_non_rotational": is_non_rotational,
                            "state": DISK_STATE_UNKNOWN,  # Will be determined by detailed queries
                            "last_known_temp": None,
                            "last_known_smart_status": None,
                        }

                self._last_disk_state_check = current_time
                _LOGGER.debug("Updated disk states cache with %d disks", len(self._disk_states))

        except Exception as err:
            _LOGGER.debug("Error getting disk states: %s", err)
            # Return cached data if available, otherwise empty dict
            if not self._disk_states:
                self._disk_states = {}

        return self._disk_states

    def _is_spindown_enabled(self) -> bool:
        """Check if spindown is enabled based on configuration.

        Returns True if spindown is enabled (any value except -1 'never').
        Returns False only if spindown is explicitly set to 'never' (-1).
        """
        spindown_delay = self._spindown_config.get("delay", SPINDOWN_DEFAULT)

        # Convert string to int if needed
        if isinstance(spindown_delay, str):
            try:
                spindown_delay = int(spindown_delay)
            except (ValueError, TypeError):
                spindown_delay = SPINDOWN_DEFAULT

        # Spindown is enabled unless explicitly set to "never" (-1)
        # 0 = default (30 minutes), 15/30/45 = minutes, 1-9 = hours
        # Only -1 means "never spin down"
        return spindown_delay != SPINDOWN_NEVER

    def _should_query_disk_details(self, disk_id: str) -> bool:
        """Determine if we should query detailed information for a specific disk."""
        # If spindown is set to "never" (-1), we can query all disks safely
        if not self._is_spindown_enabled():
            _LOGGER.debug("Spindown set to NEVER, querying all disk details")
            return True

        # Get disk state information
        disk_state = self._disk_states.get(disk_id, {})

        # Always query non-rotational disks (SSDs, NVMe) as they don't spin down
        if disk_state.get("is_non_rotational", False):
            _LOGGER.debug("Disk %s is non-rotational, safe to query", disk_state.get("name"))
            return True

        # Check the actual spindown delay value
        spindown_delay = self._spindown_config.get("delay", SPINDOWN_DEFAULT)
        try:
            delay_value = int(spindown_delay)
        except (ValueError, TypeError):
            delay_value = SPINDOWN_DEFAULT

        # For default spindown (delay=0), query disks normally
        # This is the factory default and most common setting
        if delay_value == SPINDOWN_DEFAULT:
            _LOGGER.debug("Disk %s: using default spindown, safe to query", disk_state.get("name"))
            return True

        # For rotational disks with explicit spindown times (15, 30, 45 minutes or 1-9 hours):
        # Be more conservative to avoid waking sleeping disks
        _LOGGER.debug(
            "Disk %s is rotational with explicit spindown delay %s, being conservative",
            disk_state.get("name"), spindown_delay
        )
        return False

    async def _get_safe_disk_health_info(self, disk_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Get disk health information only for disks that are safe to query."""
        safe_disk_health = {}

        if not disk_ids:
            return safe_disk_health

        # Get current disk states
        disk_states = await self._get_disk_states()

        # Debug: Log the disk IDs we're trying to match
        _LOGGER.debug("Requested disk IDs: %s", disk_ids)
        _LOGGER.debug("Available disk states: %s", list(disk_states.keys()))

        # Determine which disks are safe to query
        safe_disk_ids = []
        for disk_id in disk_ids:
            if self._should_query_disk_details(disk_id):
                safe_disk_ids.append(disk_id)

        # If no disk IDs match our states, we need to query all disks and match by device/name
        if not safe_disk_ids:
            _LOGGER.debug("No disk IDs matched states, will query all disks and match by device/name")

            # Check the actual spindown configuration
            spindown_delay = self._spindown_config.get("delay", SPINDOWN_DEFAULT)
            try:
                delay_value = int(spindown_delay)
            except (ValueError, TypeError):
                delay_value = SPINDOWN_DEFAULT

            # Query all disks when:
            # 1. Spindown is set to "never" (-1), OR
            # 2. Using default spindown (delay=0) - this is the common case
            if not self._is_spindown_enabled():
                _LOGGER.debug("Spindown set to NEVER, querying all disks for health info")
            elif delay_value == SPINDOWN_DEFAULT:
                _LOGGER.debug("Using default spindown (delay=0), querying all disks for health info")
            else:
                _LOGGER.debug("Explicit spindown delay %s configured, being conservative with disk queries", spindown_delay)
                return safe_disk_health

        try:
            # Query detailed health information only for safe disks
            # We'll use a comprehensive query but only process results for safe disks
            health_query = """
            query GetDiskHealthInfo {
                disks {
                    id
                    device
                    type
                    name
                    vendor
                    size
                    temperature
                    smartStatus
                    serialNum
                    firmwareRevision
                    interfaceType
                    partitions {
                        name
                        fsType
                        size
                    }
                }
            }
            """

            _LOGGER.debug("Querying health info for %d safe disks", len(safe_disk_ids))
            response = await self._send_graphql_request(health_query)

            if "data" in response and "disks" in response["data"]:
                all_disks = response["data"]["disks"]

                # Check spindown configuration to determine processing strategy
                spindown_delay = self._spindown_config.get("delay", SPINDOWN_DEFAULT)
                try:
                    delay_value = int(spindown_delay)
                except (ValueError, TypeError):
                    delay_value = SPINDOWN_DEFAULT

                # Process all disks when:
                # 1. Spindown is set to "never" (-1), OR
                # 2. Using default spindown (delay=0) - this is the common case
                if not self._is_spindown_enabled() or delay_value == SPINDOWN_DEFAULT:
                    if not self._is_spindown_enabled():
                        _LOGGER.debug("Spindown set to NEVER, processing all %d disks", len(all_disks))
                    else:
                        _LOGGER.debug("Using default spindown (delay=0), processing all %d disks", len(all_disks))
                    for disk in all_disks:
                        disk_id = disk.get("id")
                        if disk_id:
                            safe_disk_health[disk_id] = disk

                            # Update our disk states cache with the health information
                            if disk_id in self._disk_states:
                                self._disk_states[disk_id]["last_known_temp"] = disk.get("temperature")
                                self._disk_states[disk_id]["last_known_smart_status"] = disk.get("smartStatus")
                                self._disk_states[disk_id]["state"] = DISK_STATE_ACTIVE  # If we got data, it's active
                else:
                    # Process only the safe disks when spindown is enabled
                    for disk in all_disks:
                        disk_id = disk.get("id")
                        if disk_id in safe_disk_ids:
                            safe_disk_health[disk_id] = disk

                            # Update our disk states cache with the health information
                            if disk_id in self._disk_states:
                                self._disk_states[disk_id]["last_known_temp"] = disk.get("temperature")
                                self._disk_states[disk_id]["last_known_smart_status"] = disk.get("smartStatus")
                                self._disk_states[disk_id]["state"] = DISK_STATE_ACTIVE  # If we got data, it's active

                _LOGGER.debug("Retrieved health info for %d disks", len(safe_disk_health))

        except Exception as err:
            _LOGGER.debug("Error getting safe disk health info: %s", err)

        return safe_disk_health

    def _find_matching_health_data(self, disk: dict[str, Any], safe_disk_health: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
        """Find matching health data for a disk by ID, device, or name."""
        disk_id = disk.get("id")

        # First try to match by disk ID
        if disk_id in safe_disk_health:
            return safe_disk_health[disk_id]

        # Extract serial number from array disk ID for matching
        # Array IDs format: prefix:DEVICE_NAME_SERIAL
        # Health IDs format: prefix:SERIAL
        disk_serial = None
        if disk_id and ":" in disk_id:
            id_parts = disk_id.split(":")
            if len(id_parts) >= 2:
                # Extract serial from the end of the ID
                full_suffix = id_parts[1]
                if "_" in full_suffix:
                    # Format: DEVICE_NAME_SERIAL -> extract SERIAL
                    disk_serial = full_suffix.split("_")[-1]
                else:
                    # Format: SERIAL -> use as is
                    disk_serial = full_suffix

        # Try to match by serial number in health data IDs
        if disk_serial:
            for health_disk_id, health_disk_data in safe_disk_health.items():
                if health_disk_id.endswith(":" + disk_serial):
                    _LOGGER.debug("Matched disk %s by serial number %s", disk.get("name"), disk_serial)
                    return health_disk_data

        # Try to match by device name or other identifiers
        disk_device = disk.get("device")
        disk_name = disk.get("name")

        for health_disk_id, health_disk_data in safe_disk_health.items():
            health_device = health_disk_data.get("device")
            health_name = health_disk_data.get("name")

            # Match by device path
            if disk_device and health_device and disk_device == health_device:
                _LOGGER.debug("Matched disk %s by device path %s", disk_name, disk_device)
                return health_disk_data

            # Match by name
            if disk_name and health_name and disk_name == health_name:
                _LOGGER.debug("Matched disk %s by name", disk_name)
                return health_disk_data

        return None

    def _create_default_system_data(self) -> dict[str, Any]:
        """Create default system data structure."""
        return {
            "info": {
                "os": {
                    "platform": "linux",
                    "distro": "Unraid",
                    "uptime": "Unknown",
                },
                "cpu": {
                    "manufacturer": "Unknown",
                    "brand": "Unknown",
                    "cores": 0,
                    "threads": 0,
                },
                "memory": {"total": 0, "free": 0, "used": 0},
                "versions": {
                    "unraid": "Unknown",
                    "kernel": "Unknown",
                    "docker": "Unknown",
                },
                "devices": {"gpu": []},
            },
            "gpu_info": [],
            "online": True,
            "temperatures": {
                "cpu": 40.0,  # Default estimated value
                "motherboard": 35.0,  # Default estimated value
                "sensors": [],  # Empty list as fallback
            },
            "fans": [],
        }

    def _process_memory_values(self, memory: dict[str, Any]) -> None:
        """Process memory values from string to integers."""
        string_to_standard = {
            "totalString": "total",
            "freeString": "free",
            "usedString": "used",
            "activeString": "active",
            "availableString": "available",
        }

        for string_key, standard_key in string_to_standard.items():
            if string_key in memory and memory[string_key] is not None:
                try:
                    # Convert string to integer
                    memory[standard_key] = int(memory[string_key])
                    # Keep the string value for reference
                    memory[f"{standard_key}_str"] = memory[string_key]
                    _LOGGER.debug(
                        "Memory %s: %s (%s bytes)",
                        standard_key,
                        memory[standard_key],
                        memory[string_key],
                    )
                except (ValueError, TypeError):
                    _LOGGER.warning(
                        "Failed to convert memory %s value '%s' to integer",
                        string_key,
                        memory[string_key],
                    )
                    # Use a default value
                    memory[standard_key] = 0

    def _calculate_memory_usage(self, memory: dict[str, Any]) -> None:
        """Calculate memory usage percentage."""
        if "total" in memory and "available" in memory:
            try:
                total = int(memory.get("total", 0))
                available = int(memory.get("available", 0))
                if total > 0:
                    memory_usage_percent = 100 - (available / total * 100)
                    # Add calculated memory usage percentage
                    memory["usage"] = round(memory_usage_percent, 1)
                    _LOGGER.debug("Calculated memory usage: %s%%", memory["usage"])
            except (ValueError, TypeError, ZeroDivisionError) as err:
                _LOGGER.debug("Error calculating memory usage: %s", err)
                # Set a default value
                memory["usage"] = 0

    def _create_default_system_info(self) -> dict[str, Any]:
        """Create default system info structure."""
        return {
            "info": {
                "cpu": {
                    "manufacturer": "Unknown",
                    "brand": "Unknown",
                    "cores": 0,
                    "threads": 0,
                    "speed": 0,
                    "speedmax": 0,
                    "usage": 0,  # Default CPU usage
                    "load": {"current": 0, "average": 0},
                },
                "memory": {
                    "total": 0,
                    "free": 0,
                    "used": 0,
                    "active": 0,
                    "available": 0,
                    "usage": 0,  # Default memory usage
                },
                "os": {
                    "platform": "linux",
                    "distro": "Unraid",
                    "uptime": "Unknown",
                },
                "versions": {
                    "unraid": "Unknown",
                    "kernel": "Unknown",
                    "docker": "Unknown",
                },
            },
            "online": True,
            "temperatures": {},
            "fans": [],
        }

    def _calculate_memory_usage_from_array(self, array_data: dict[str, Any]) -> float:
        """Calculate memory usage percentage from array data."""
        try:
            if (
                not array_data
                or "data" not in array_data
                or "array" not in array_data["data"]
            ):
                return 0

            array_info = array_data["data"]["array"]
            if (
                "capacity" not in array_info
                or "kilobytes" not in array_info["capacity"]
            ):
                return 0

            capacity = array_info["capacity"]["kilobytes"]

            # Convert string values to integers
            total = int(capacity.get("total", "0"))
            used = int(capacity.get("used", "0"))

            # Calculate memory usage percentage
            if total > 0:
                memory_usage = round((used / total) * 100, 1)
                _LOGGER.debug(
                    "Calculated memory usage from array data: %s%%", memory_usage
                )
                return memory_usage
        except (KeyError, ValueError, TypeError, ZeroDivisionError) as err:
            _LOGGER.debug("Error calculating memory usage from array data: %s", err)

        return 0

    async def get_system_info(self) -> dict[str, Any]:
        """Get system information."""
        # Initialize with default data
        system_data = self._create_default_system_data()

        # Try to get comprehensive system info from the info endpoint
        try:
            # Use a simplified system info query that avoids the large integer issue
            # We'll query CPU and OS info separately from memory to avoid the GraphQL Int overflow
            system_info_query = """
            query GetSystemInfo {
                info {
                    cpu {
                        manufacturer
                        brand
                        cores
                        threads
                        speed
                        speedmax
                    }
                    os {
                        platform
                        distro
                        release
                        uptime
                        hostname
                        kernel
                    }
                    versions {
                        unraid
                        kernel
                        docker
                    }
                }
            }
            """

            _LOGGER.debug("Fetching comprehensive system info")
            response = await self._send_graphql_request(system_info_query)

            if (
                response
                and "data" in response
                and "info" in response["data"]
            ):
                info_data = response["data"]["info"]

                # Create proper system data structure
                system_data = {
                    "info": info_data,
                    "online": True,
                    "temperatures": {},
                    "fans": [],
                }

                # Memory data will be processed separately to avoid GraphQL Int overflow

                # Process CPU data and try to get load information
                if "cpu" in info_data:
                    await self._enhance_cpu_data(info_data["cpu"])
                    _LOGGER.debug("CPU data processed: %s", info_data["cpu"])

                # Try to get memory information separately to avoid the large integer issue
                await self._get_memory_info(system_data)

                _LOGGER.debug("Successfully fetched system info from info endpoint")
            else:
                _LOGGER.warning("No system info data in response, using defaults")

        except Exception as err:
            _LOGGER.error("Error getting system info: %s", err)
            # Fall back to default data structure
            system_data = self._create_default_system_info()

        # Add sensor data if possible
        try:
            sensors_data = await self.get_system_sensors()
            if sensors_data:
                if "temperatures" in sensors_data:
                    system_data["temperatures"] = sensors_data["temperatures"]
                if "fans" in sensors_data:
                    system_data["fans"] = sensors_data["fans"]
                    _LOGGER.debug("Found %d system fans", len(sensors_data["fans"]))
        except Exception as err:
            _LOGGER.debug("Error getting system sensors: %s", err)

        return system_data

    def _process_system_memory(self, system_data: dict[str, Any]) -> None:
        """Process memory values and calculate usage."""
        if "info" in system_data and "memory" in system_data["info"]:
            memory_data = system_data["info"]["memory"]

            # Calculate memory usage percentage
            if "total" in memory_data and "available" in memory_data:
                try:
                    total = int(memory_data.get("total", 0))
                    available = int(memory_data.get("available", 0))

                    if total > 0:
                        memory_usage = 100 - (available / total * 100)
                        memory_data["usage"] = round(memory_usage, 1)
                        _LOGGER.debug(
                            "Calculated memory usage: %s%%", memory_data["usage"]
                        )
                    else:
                        memory_data["usage"] = 0
                except (ValueError, TypeError, ZeroDivisionError) as err:
                    _LOGGER.debug("Error calculating memory usage: %s", err)
                    memory_data["usage"] = 0
            else:
                memory_data["usage"] = 0

    def _set_default_cpu_usage(self, system_data: dict[str, Any]) -> None:
        """Set default CPU usage value."""
        if "info" in system_data and "cpu" in system_data["info"]:
            cpu_info = system_data["info"]["cpu"]
            # Add a default CPU usage value of 0
            # This ensures the sensor always has a value
            cpu_info["usage"] = 0
            _LOGGER.debug("CPU info: %s", cpu_info)

    async def _enhance_cpu_data(self, cpu_data: dict[str, Any]) -> None:
        """Enhance CPU data with load information."""
        try:
            # According to the official Unraid GraphQL API schema, there are no fields for:
            # - CPU usage percentage
            # - CPU load averages
            # - Real-time CPU performance metrics
            #
            # The InfoCpu type only includes static hardware information:
            # - manufacturer, brand, vendor, family, model
            # - speed, speedmin, speedmax, threads, cores, processors
            # - socket, cache, flags
            #
            # This is a limitation of the current Unraid API, not our integration

            _LOGGER.debug("CPU usage/load data not available in Unraid GraphQL API")

            # Set default values since the API doesn't provide real-time CPU metrics
            cpu_data["usage"] = 0
            cpu_data["load"] = {"current": 0, "average": 0}

        except Exception as err:
            _LOGGER.debug("Error enhancing CPU data: %s", err)
            # Set default values
            cpu_data["usage"] = 0
            cpu_data["load"] = {"current": 0, "average": 0}

    async def _get_memory_info(self, system_data: dict[str, Any]) -> None:
        """Get memory information using alternative approaches to avoid GraphQL Int overflow."""
        try:
            # The official Unraid API has a bug where memory values exceed Int32 limits
            # According to the official schema, memory fields are Int! types, not Long scalars
            # This is a known limitation in the Unraid GraphQL API for systems with >2GB RAM

            # Try to get memory info from the array capacity as a workaround
            # Array capacity might provide some memory-related information
            array_query = """
            query GetArrayCapacity {
                array {
                    capacity {
                        kilobytes {
                            free
                            used
                            total
                        }
                    }
                }
            }
            """

            array_response = await self._send_graphql_request(array_query)

            if (
                array_response
                and "data" in array_response
                and "array" in array_response["data"]
                and "capacity" in array_response["data"]["array"]
                and "kilobytes" in array_response["data"]["array"]["capacity"]
            ):
                capacity_data = array_response["data"]["array"]["capacity"]["kilobytes"]

                # Convert kilobytes to bytes and estimate system memory
                # This is not actual RAM but gives us some system capacity info
                if "info" in system_data and "memory" in system_data["info"]:
                    # Use array capacity as a rough indicator of system scale
                    total_kb = int(capacity_data.get("total", "0"))
                    used_kb = int(capacity_data.get("used", "0"))

                    # Estimate memory usage based on array usage (very rough approximation)
                    if total_kb > 0:
                        usage_percent = (used_kb / total_kb) * 100
                        # Cap at reasonable values for memory usage
                        estimated_usage = min(max(usage_percent * 0.1, 5), 95)  # Scale down and bound

                        system_data["info"]["memory"].update({
                            "total": 1,  # Placeholder to avoid division by zero
                            "free": 0,
                            "used": 1,
                            "active": 0,
                            "available": 0,
                            "usage": round(estimated_usage, 1),
                        })
                        _LOGGER.debug("Estimated memory usage from array capacity: %s%%", estimated_usage)
                        return

            # If array capacity approach fails, set safe defaults
            if "info" not in system_data:
                system_data["info"] = {}
            if "memory" not in system_data["info"]:
                system_data["info"]["memory"] = {
                    "total": 1,  # Placeholder to avoid division by zero
                    "free": 0,
                    "used": 1,
                    "active": 0,
                    "available": 0,
                    "usage": 0,
                }
                _LOGGER.debug("Set default memory values due to GraphQL API limitations")

        except Exception as err:
            _LOGGER.debug("Error getting memory info: %s", err)
            # Use default memory values
            if "info" not in system_data:
                system_data["info"] = {}
            if "memory" not in system_data["info"]:
                system_data["info"]["memory"] = {
                    "total": 1,
                    "free": 0,
                    "used": 1,
                    "active": 0,
                    "available": 0,
                    "usage": 0,
                }

    async def _try_system_stats_memory(self, system_data: dict[str, Any]) -> None:
        """Try to get memory info from system stats or other endpoints."""
        try:
            # Try a different approach - maybe there's a system stats endpoint
            stats_query = """
            query GetSystemStats {
                system {
                    stats {
                        memory {
                            total
                            free
                            used
                            available
                        }
                    }
                }
            }
            """

            stats_response = await self._send_graphql_request(stats_query)

            if (
                stats_response
                and "data" in stats_response
                and "system" in stats_response["data"]
                and "stats" in stats_response["data"]["system"]
                and "memory" in stats_response["data"]["system"]["stats"]
            ):
                memory_stats = stats_response["data"]["system"]["stats"]["memory"]

                # Update system data with stats memory info
                if "info" in system_data and "memory" in system_data["info"]:
                    system_data["info"]["memory"].update(memory_stats)
                    self._calculate_memory_usage(system_data["info"]["memory"])
                    _LOGGER.debug("Updated memory info from system stats: %s", memory_stats)

        except Exception as err:
            _LOGGER.debug("System stats memory query failed: %s", err)
            # Try to estimate memory from other sources or use defaults
            await self._estimate_memory_from_other_sources(system_data)

    async def _estimate_memory_from_other_sources(self, system_data: dict[str, Any]) -> None:
        """Try to estimate memory usage from other available data sources."""
        try:
            # For now, we'll set some reasonable default values
            # In a real implementation, you might try to parse /proc/meminfo or similar

            # Set default memory values that indicate the system has memory but we can't measure it
            if "info" in system_data and "memory" in system_data["info"]:
                memory_info = system_data["info"]["memory"]

                # If we don't have any memory data, set some defaults
                if memory_info.get("total", 0) == 0:
                    # Set a placeholder that indicates we have a system but can't measure memory
                    memory_info.update({
                        "total": 1,  # Placeholder to avoid division by zero
                        "free": 0,
                        "used": 1,
                        "active": 0,
                        "available": 0,
                        "usage": 0,  # Will be calculated as 0% since we can't get real data
                    })
                    _LOGGER.debug("Set placeholder memory values due to GraphQL limitations")

        except Exception as err:
            _LOGGER.debug("Error estimating memory from other sources: %s", err)

    def _process_memory_values(self, memory_data: dict[str, Any]) -> None:
        """Process memory values to ensure they are in the correct format."""
        try:
            # Convert string values to integers if needed
            for key in ["total", "free", "used", "active", "available", "buffcache", "swaptotal", "swapused", "swapfree"]:
                if key in memory_data and isinstance(memory_data[key], str):
                    try:
                        memory_data[key] = int(memory_data[key])
                    except (ValueError, TypeError):
                        memory_data[key] = 0
                elif key not in memory_data:
                    memory_data[key] = 0
        except Exception as err:
            _LOGGER.debug("Error processing memory values: %s", err)

    def _calculate_memory_usage(self, memory_data: dict[str, Any]) -> None:
        """Calculate memory usage percentage."""
        try:
            total = memory_data.get("total", 0)
            available = memory_data.get("available", memory_data.get("free", 0))

            if total > 0:
                used_percent = 100 - (available / total * 100)
                memory_data["usage"] = round(used_percent, 1)
                _LOGGER.debug("Calculated memory usage: %s%% (total: %s, available: %s)",
                            memory_data["usage"], total, available)
            else:
                memory_data["usage"] = 0
                _LOGGER.debug("Cannot calculate memory usage: total memory is 0")
        except Exception as err:
            _LOGGER.debug("Error calculating memory usage: %s", err)
            memory_data["usage"] = 0

    async def _get_basic_array_info(self) -> dict[str, Any]:
        """Get basic array information."""
        # Initialize array data structure
        array_data: dict[str, Any] = {
            "array": {
                "state": "",
                "capacity": {},
                "disks": [],
                "parities": [],
                "caches": [],
            },
            "flash": {},
            "spindown_config": {},
        }

        # First, get basic array info (state, capacity, spindown config)
        # This is safe to use and doesn't wake sleeping disks
        # The Unraid API uses a custom Long scalar type for large integers
        basic_array_query = """
        query GetBasicArrayInfo {
            array {
                state
                capacity {
                    kilobytes {
                        # These will be returned as Long scalar type values
                        free
                        used
                        total
                    }
                    disks {
                        # These will be returned as Long scalar type values
                        free
                        used
                        total
                    }
                }
            }
            vars {
                spindownDelay
                spinupGroups
            }
        }
        """

        try:
            response = await self._send_graphql_request(basic_array_query)
            if "data" not in response or "array" not in response["data"]:
                return array_data

            # Update array info
            array_info = response["data"]["array"]
            array_data["array"].update(array_info)

            # Get spindown configuration if available
            if "vars" in response["data"]:
                self._process_spindown_config(array_data, response["data"]["vars"])

        except Exception as err:
            _LOGGER.warning("Error getting basic array info: %s", err)

        return array_data

    def _process_spindown_config(
        self, array_data: dict[str, Any], vars_info: dict[str, Any]
    ) -> None:
        """Process spindown configuration from vars info."""
        spindown_delay = vars_info.get("spindownDelay", "0")
        spinup_groups = vars_info.get("spinupGroups", False)

        array_data["spindown_config"] = {
            "delay": spindown_delay,
            "groups_enabled": spinup_groups,
        }

        _LOGGER.debug(
            "Spindown config: delay=%s, groups=%s",
            spindown_delay,
            spinup_groups,
        )

    def _create_safe_parity_disk(
        self, parity: dict[str, Any], array_state: str
    ) -> dict[str, Any]:
        """Create a safe parity disk object."""
        # Default to STANDBY for safety
        disk_state = "STANDBY"

        # If the disk status is OK, we'll check if it's likely active
        disk_status = parity.get("status", "").upper()
        if disk_status == "DISK_OK" and array_state == "STARTED":
            disk_state = "ACTIVE"

        return {
            "id": parity.get("id"),
            "name": parity.get("name"),
            "device": parity.get("device", ""),
            "size": parity.get("size", "0"),
            "status": parity.get("status", "DISK_OK"),
            "type": "Parity",
            "temp": None,  # No temperature to avoid waking disk
            "rotational": True,
            "state": disk_state,  # Use our determined state
        }

    def _create_safe_data_disk(self, disk: dict[str, Any]) -> dict[str, Any]:
        """Create a safe data disk object."""
        # Default to STANDBY for safety
        disk_state = "STANDBY"

        # If the disk has filesystem info, it's likely active
        fs_size = disk.get("fsSize", "0")
        if fs_size and fs_size != "0":
            disk_state = "ACTIVE"

        return {
            "id": disk.get("id"),
            "name": disk.get("name"),
            "device": disk.get("device", ""),
            "status": disk.get("status", "DISK_OK"),
            "type": disk.get("type", "Data"),
            "fsSize": disk.get("fsSize", "0"),
            "fsFree": disk.get("fsFree", "0"),
            "fsUsed": disk.get("fsUsed", "0"),
            "temp": None,  # No temperature to avoid waking disk
            "rotational": True,  # Assume rotational for safety
            "state": disk_state,  # Use our determined state
        }

    def _create_safe_cache_disk(self, cache: dict[str, Any]) -> dict[str, Any]:
        """Create a safe cache disk object."""
        return {
            "id": cache.get("id"),
            "name": cache.get("name"),
            "device": cache.get("device", ""),
            "status": cache.get("status", "DISK_OK"),
            "type": cache.get("type", "Cache"),
            "fsSize": cache.get("fsSize", "0"),
            "fsFree": cache.get("fsFree", "0"),
            "fsUsed": cache.get("fsUsed", "0"),
            "temp": None,  # Will be populated by the temperature query for cache disks
            "rotational": False,  # Assume SSD for cache
            "state": "ACTIVE",  # Default to ACTIVE for cache disks (typically SSDs)
        }

    async def _get_complete_array_info(
        self, array_data: dict[str, Any]
    ) -> dict[str, Any]:
        """Get complete array information."""
        complete_array_query = """
        query GetCompleteArrayInfo {
            array {
                parities {
                    id
                    name
                    device
                    size
                    status
                    type
                }
                disks {
                    id
                    name
                    device
                    status
                    type
                    fsSize
                    fsFree
                    fsUsed
                }
                caches {
                    id
                    name
                    device
                    status
                    type
                    fsSize
                    fsFree
                    fsUsed
                }
            }
        }
        """

        try:
            response = await self._send_graphql_request(complete_array_query)
            if "data" not in response or "array" not in response["data"]:
                return array_data

            array_info = response["data"]["array"]
            array_state = array_data.get("array", {}).get("state", "")

            # Process parity disks
            if "parities" in array_info:
                for parity in array_info["parities"]:
                    safe_parity = self._create_safe_parity_disk(parity, array_state)
                    array_data["array"]["parities"].append(safe_parity)

            # Process data disks
            if "disks" in array_info:
                for disk in array_info["disks"]:
                    safe_disk = self._create_safe_data_disk(disk)
                    array_data["array"]["disks"].append(safe_disk)

            # Process cache disks
            if "caches" in array_info:
                for cache in array_info["caches"]:
                    safe_cache = self._create_safe_cache_disk(cache)
                    array_data["array"]["caches"].append(safe_cache)

        except Exception as err:
            _LOGGER.warning("Error getting complete array info: %s", err)

        return array_data

    async def _update_cache_disk_temperatures(self, array_data: dict[str, Any]) -> None:
        """Update cache disk temperatures and health information with spindown awareness."""
        try:
            # Get cache disk IDs for intelligent querying
            cache_disk_ids = []
            for cache_disk in array_data["array"]["caches"]:
                disk_id = cache_disk.get("id")
                if disk_id:
                    cache_disk_ids.append(disk_id)

            if not cache_disk_ids:
                _LOGGER.debug("No cache disks found to update")
                return

            # Update spindown configuration from array data
            self._update_spindown_config(array_data)

            # Get safe disk health information using intelligent spindown awareness
            safe_disk_health = await self._get_safe_disk_health_info(cache_disk_ids)

            # Update cache disks with available health data
            for cache_disk in array_data["array"]["caches"]:
                disk_id = cache_disk.get("id")
                health_data = self._find_matching_health_data(cache_disk, safe_disk_health)

                if health_data:
                    # We have fresh health data for this disk
                    self._update_disk_with_health_data(cache_disk, health_data)
                else:
                    # Use cached/last known data for this disk
                    self._update_disk_with_cached_data(cache_disk, disk_id)

        except UnraidApiError as err:
            _LOGGER.debug("API error getting cache disk temperatures: %s", err)
        except TimeoutError:
            _LOGGER.debug(
                "Timeout when getting cache disk temperatures - this is normal if disks are in standby"
            )
        except Exception as err:
            _LOGGER.debug("Error getting cache disk temperatures: %s", err)

    def _update_spindown_config(self, array_data: dict[str, Any]) -> None:
        """Update spindown configuration from array data."""
        try:
            if "spindown_config" in array_data:
                self._spindown_config = array_data["spindown_config"]
                _LOGGER.debug("Updated spindown config from array data: %s", self._spindown_config)

                # If we see delay=0, try to get the actual configured value
                delay = self._spindown_config.get("delay", "0")
                if delay == "0" or delay == 0:
                    _LOGGER.debug("Detected delay=0 (default/unconfigured), this may not reflect actual Unraid spindown setting")
                    _LOGGER.debug("Your Unraid server may be configured for a specific spindown time that's not reflected in the GraphQL API")
        except Exception as err:
            _LOGGER.debug("Error updating spindown config: %s", err)

    def _update_disk_with_health_data(self, disk: dict[str, Any], health_data: dict[str, Any]) -> None:
        """Update disk with fresh health data."""
        disk_name = disk.get("name", "unknown")

        # Update temperature
        temp = health_data.get("temperature")
        if temp is not None:
            disk["temp"] = temp
            disk["temperature"] = temp
            _LOGGER.debug("Updated disk %s temperature: %s°C", disk_name, temp)

        # Update SMART status and health information
        smart_status = health_data.get("smartStatus")
        if smart_status is not None:
            disk["smartStatus"] = smart_status
            disk["health"] = "OK" if smart_status == "OK" else "WARNING"
            _LOGGER.debug("Updated disk %s SMART status: %s", disk_name, smart_status)

        # Update additional disk information
        for field in ["vendor", "size", "serialNum", "firmwareRevision", "interfaceType", "id"]:
            if field in health_data and health_data[field] is not None:
                disk[field] = health_data[field]

        # Update partition information if available
        if "partitions" in health_data and health_data["partitions"]:
            disk["partitions"] = health_data["partitions"]

        # Mark as having fresh data
        import time
        disk["health_data_source"] = "live"
        disk["health_data_timestamp"] = time.time()

    def _update_disk_with_cached_data(self, disk: dict[str, Any], disk_id: str) -> None:
        """Update disk with cached/last known data for sleeping disks."""
        disk_name = disk.get("name", "unknown")

        # Get cached disk state
        disk_state = self._disk_states.get(disk_id, {})

        # Use last known temperature if available
        last_temp = disk_state.get("last_known_temp")
        if last_temp is not None:
            disk["temp"] = last_temp
            disk["temperature"] = last_temp
            _LOGGER.debug("Using cached temperature for disk %s: %s°C", disk_name, last_temp)

        # Use last known SMART status if available
        last_smart = disk_state.get("last_known_smart_status")
        if last_smart is not None:
            disk["smartStatus"] = last_smart
            disk["health"] = "OK" if last_smart == "OK" else "WARNING"
            _LOGGER.debug("Using cached SMART status for disk %s: %s", disk_name, last_smart)

        # Mark as using cached data
        disk["health_data_source"] = "cached"
        disk["health_note"] = "Disk may be in standby - using last known values"

        # Determine disk state for user information
        if disk_state.get("is_non_rotational", False):
            disk["disk_state_note"] = "SSD/NVMe - always available"
        else:
            disk["disk_state_note"] = "Rotational disk - may be in standby to save power"

    def _match_and_update_disk_health(
        self, cache_disk: dict[str, Any], all_disks: list[dict[str, Any]]
    ) -> None:
        """Match and update disk health information including temperature and SMART status."""
        cache_name = cache_disk.get("name")
        cache_device = cache_disk.get("device")

        for disk in all_disks:
            disk_name = disk.get("name")
            disk_device = disk.get("device")
            disk_type = disk.get("type", "").lower()

            # Check if this disk matches our cache disk
            is_match = (
                (cache_name and disk_name and cache_name == disk_name)
                or (cache_device and disk_device and cache_device == disk_device)
                or ("cache" in disk_type)
            )

            if not is_match:
                continue

            # Update temperature
            temp = disk.get("temperature")
            if temp is not None:
                cache_disk["temp"] = temp
                cache_disk["temperature"] = temp  # Also set the standard field name
                _LOGGER.debug(
                    "Updated cache disk %s temperature to %s°C",
                    cache_name,
                    temp,
                )

            # Update SMART status and health information
            smart_status = disk.get("smartStatus")
            if smart_status is not None:
                cache_disk["smartStatus"] = smart_status
                cache_disk["health"] = "OK" if smart_status == "OK" else "WARNING"
                _LOGGER.debug(
                    "Updated cache disk %s SMART status: %s",
                    cache_name,
                    smart_status,
                )

            # Update additional disk information from the official schema
            for field in ["vendor", "size", "serialNum", "firmwareRevision", "interfaceType", "id"]:
                if field in disk and disk[field] is not None:
                    cache_disk[field] = disk[field]

            # Update partition information if available
            if "partitions" in disk and disk["partitions"]:
                cache_disk["partitions"] = disk["partitions"]
                _LOGGER.debug(
                    "Updated cache disk %s partition info: %s partitions",
                    cache_name,
                    len(disk["partitions"]),
                )

            _LOGGER.debug("Updated cache disk %s health information", cache_name)
            break  # Found a match, no need to continue

    async def _update_all_disk_health(self, array_data: dict[str, Any]) -> None:
        """Update health information for all disks (data, parity, and cache) with spindown awareness."""
        try:
            # Collect all disk IDs from data and parity disks
            all_disk_ids = []

            # Get data disk IDs
            for data_disk in array_data["array"]["disks"]:
                disk_id = data_disk.get("id")
                if disk_id:
                    all_disk_ids.append(disk_id)

            # Get parity disk IDs
            for parity_disk in array_data["array"]["parities"]:
                disk_id = parity_disk.get("id")
                if disk_id:
                    all_disk_ids.append(disk_id)

            if not all_disk_ids:
                _LOGGER.debug("No data or parity disks found to update")
                return

            # Update spindown configuration
            self._update_spindown_config(array_data)

            # Get safe disk health information using intelligent spindown awareness
            safe_disk_health = await self._get_safe_disk_health_info(all_disk_ids)

            # Update data disks with available health data
            for data_disk in array_data["array"]["disks"]:
                disk_id = data_disk.get("id")
                health_data = self._find_matching_health_data(data_disk, safe_disk_health)

                if health_data:
                    self._update_disk_with_health_data(data_disk, health_data)
                else:
                    self._update_disk_with_cached_data(data_disk, disk_id)

            # Update parity disks with available health data
            for parity_disk in array_data["array"]["parities"]:
                disk_id = parity_disk.get("id")
                health_data = self._find_matching_health_data(parity_disk, safe_disk_health)

                if health_data:
                    self._update_disk_with_health_data(parity_disk, health_data)
                else:
                    self._update_disk_with_cached_data(parity_disk, disk_id)

            _LOGGER.debug("Updated health information for all disk types with spindown awareness")

        except UnraidApiError as err:
            _LOGGER.debug("API error getting all disk health: %s", err)
        except TimeoutError:
            _LOGGER.debug("Timeout getting all disk health - this is normal if disks are in standby")
        except Exception as err:
            _LOGGER.debug("Error getting all disk health: %s", err)

    def _match_and_update_disk_health_generic(
        self, disk: dict[str, Any], all_disks: list[dict[str, Any]], disk_category: str
    ) -> None:
        """Match and update disk health information for any disk type."""
        disk_name = disk.get("name")
        disk_device = disk.get("device")
        disk_id = disk.get("id")

        for api_disk in all_disks:
            api_disk_name = api_disk.get("name")
            api_disk_device = api_disk.get("device")
            api_disk_id = api_disk.get("id")

            # Check if this API disk matches our array disk
            is_match = (
                (disk_name and api_disk_name and disk_name == api_disk_name)
                or (disk_device and api_disk_device and disk_device == api_disk_device)
                or (disk_id and api_disk_id and disk_id == api_disk_id)
            )

            if not is_match:
                continue

            # Update SMART status and health information
            smart_status = api_disk.get("smartStatus")
            if smart_status is not None:
                disk["smartStatus"] = smart_status
                disk["health"] = "OK" if smart_status == "OK" else "WARNING"
                _LOGGER.debug(
                    "Updated %s disk %s SMART status: %s",
                    disk_category,
                    disk_name,
                    smart_status,
                )

            # Update additional disk information from the official schema
            for field in ["vendor", "size", "serialNum", "firmwareRevision", "interfaceType", "state"]:
                if field in api_disk and api_disk[field] is not None:
                    disk[field] = api_disk[field]

            # Update temperature (only for active disks to avoid waking sleeping ones)
            disk_state = api_disk.get("state", "").upper()
            if disk_state == "ACTIVE":
                temp = api_disk.get("temperature")
                if temp is not None:
                    disk["temperature"] = temp
                    _LOGGER.debug(
                        "Updated %s disk %s temperature: %s°C",
                        disk_category,
                        disk_name,
                        temp,
                    )

            # Update partition information if available
            if "partitions" in api_disk and api_disk["partitions"]:
                disk["partitions"] = api_disk["partitions"]
                _LOGGER.debug(
                    "Updated %s disk %s partition info: %s partitions",
                    disk_category,
                    disk_name,
                    len(api_disk["partitions"]),
                )

            _LOGGER.debug("Updated %s disk %s health information", disk_category, disk_name)
            break  # Found a match, no need to continue

    async def get_array_status(self) -> dict[str, Any]:
        """Get array status."""
        # Get basic array info
        array_data = await self._get_basic_array_info()

        # Get complete array info
        array_data = await self._get_complete_array_info(array_data)

        # Only get detailed disk information if we're doing a detailed update
        if not hasattr(self, "_skip_disk_details") or not self._skip_disk_details:
            # Get detailed disk information (temperatures, etc.)
            # This might wake sleeping disks, so we only do it when requested
            _LOGGER.debug("Getting detailed disk information")
            # Add detailed queries here if needed
        else:
            # Skip detailed queries to avoid waking disks
            _LOGGER.debug("Skipping disk details query to avoid waking disks")

            # Even when skipping detailed queries, we can safely get health data for cache disks
            # since they're typically SSDs/NVMe and don't have spindown concerns
            await self._update_cache_disk_temperatures(array_data)

            # Also update health information for all disks (data and parity)
            await self._update_all_disk_health(array_data)

        return array_data

    async def get_docker_containers(self) -> dict[str, Any]:
        """Get docker containers."""
        try:
            # Use the exact query format from the documentation
            query = """
            query GetDockerContainers {
                docker {
                    containers {
                        id
                        names
                        image
                        state
                        status
                        autoStart
                        ports {
                            ip
                            privatePort
                            publicPort
                            type
                        }
                    }
                }
            }
            """

            try:
                response = await self._send_graphql_request(query)

                # Return the data directly without restructuring
                return response.get("data", {"docker": {"containers": []}})
            except UnraidApiError as err:
                _LOGGER.warning("GraphQL docker containers failed: %s", err)
                # Return empty data structure
                return {"docker": {"containers": []}}
        except Exception as err:
            _LOGGER.error("Error getting docker containers: %s", err)
            return {"docker": {"containers": []}}

    async def get_vms(self) -> dict[str, Any]:
        """Get virtual machines with intelligent query selection.

        Uses cached query preference to minimize API calls and fallback complexity.
        Returns a dictionary with a 'vms' key containing both 'domain' and 'domains' keys.
        """
        # Use cached successful query pattern if available
        if hasattr(self, '_vm_query_preference') and self._vm_query_preference:
            try:
                response = await self._send_graphql_request(self._vm_query_preference)
                if self._process_vm_response(response):
                    return self._process_vm_response(response)
            except Exception as err:
                _LOGGER.debug("Cached VM query failed, falling back: %s", err)
                # Clear the cached preference if it fails
                self._vm_query_preference = None

        # Smart query selection with preference caching
        vm_queries = [
            {
                "name": "primary_domain",
                "query": """
                query GetVirtualMachines {
                    vms {
                        domain {
                            uuid
                            name
                            state
                        }
                    }
                }
                """,
                "path": ["vms", "domain"]
            },
            {
                "name": "alternative_domains",
                "query": """
                query GetVirtualMachinesAlt {
                    vms {
                        domains {
                            uuid
                            name
                            state
                        }
                    }
                }
                """,
                "path": ["vms", "domains"]
            },
            {
                "name": "system_fallback",
                "query": """
                query GetSystemVMs {
                    info {
                        system {
                            vms {
                                uuid
                                name
                                state
                            }
                        }
                    }
                }
                """,
                "path": ["info", "system", "vms"]
            }
        ]

        for query_config in vm_queries:
            try:
                response = await self._send_graphql_request(query_config["query"])
                processed_response = self._process_vm_response(response, query_config["path"])

                if processed_response:
                    # Cache successful query for future use
                    self._vm_query_preference = query_config["query"]
                    _LOGGER.debug("VM query '%s' successful, caching for future use", query_config["name"])
                    return processed_response

            except Exception as err:
                _LOGGER.debug("VM query '%s' failed: %s", query_config["name"], err)
                continue

        # If all queries fail, return empty structure
        _LOGGER.warning("All VM queries failed, returning empty VM data")
        return {"vms": {"domain": [], "domains": []}}

    def _process_vm_response(self, response: dict[str, Any], path: list[str] = None) -> dict[str, Any] | None:
        """Process VM response and normalize to consistent format."""
        try:
            if not response or "data" not in response:
                return None

            # Navigate to the VM data using the provided path
            data = response["data"]
            if path:
                for key in path:
                    if key not in data:
                        return None
                    data = data[key]

                # If we got VM data directly (from system fallback)
                if isinstance(data, list):
                    return {"vms": {"domain": data, "domains": data}}

            # Handle standard vms structure
            if "vms" in response["data"]:
                vms_data = response["data"]["vms"]
                domain_vms = vms_data.get("domain", [])
                domains_vms = vms_data.get("domains", [])

                # Use whichever field has data, prefer domain
                vm_list = domain_vms if domain_vms else domains_vms

                if vm_list:
                    return {"vms": {"domain": vm_list, "domains": vm_list}}

            return None

        except Exception as err:
            _LOGGER.debug("Error processing VM response: %s", err)
            return None

    async def get_shares(self) -> list[dict[str, Any]]:
        """Get network shares."""
        # The Unraid API uses a custom Long scalar type for large integers
        query = """
        query {
            shares {
                name
                comment
                # These will be returned as Long scalar type values
                free
                size
                used
            }
        }
        """

        try:
            response = await self._send_graphql_request(query)

            # Process the response to handle Long scalar type values
            if "data" in response and "shares" in response.get("data", {}):
                shares = response.get("data", {}).get("shares", [])

                # Process each share to handle Long scalar type values
                for share in shares:
                    # Convert size values to strings to preserve precision
                    for key in ("free", "size", "used"):
                        if key in share and share[key] is not None:
                            # Store the original value as a string to preserve precision
                            share[f"{key}_str"] = str(share[key])

                            # Keep the original value as is - it will be handled correctly
                            # by the GraphQL client as a number

                            _LOGGER.debug(
                                "Share %s %s: %s (%s bytes)",
                                share.get("name", "Unknown"),
                                key,
                                share[key],
                                share[f"{key}_str"],
                            )

                # Return data in the structure expected by the integration
                return shares
            # Check for errors
            if "errors" in response:
                errors = response.get("errors", [])
                error_messages = [error.get("message", "") for error in errors]
                _LOGGER.warning(
                    "GraphQL shares query returned errors: %s", error_messages
                )

            return []
        except UnraidApiError as err:
            _LOGGER.warning("GraphQL shares query failed: %s", err)
            return []
        except Exception as err:
            _LOGGER.error("Error getting shares: %s", err)
            return []

    def _create_basic_disk_info(self, disk: dict[str, Any]) -> dict[str, Any]:
        """Create a basic disk info structure with default values."""
        disk_name = disk.get("name", "")
        disk_state = disk.get("state", "").upper()

        return {
            "device": disk.get("device"),
            "name": disk_name,
            "type": "unknown",
            "size": 0,
            "vendor": "",
            "temperature": None,  # No temperature to avoid waking disk
            "smartStatus": "UNKNOWN",
            "state": disk_state,
            "fsSize": 0,
            "fsFree": 0,
            "fsUsed": 0,
            "numReads": 0,
            "numWrites": 0,
            "numErrors": 0,
        }

    async def _get_detailed_disk_info(self, disk_name: str) -> list[dict[str, Any]]:
        """Get detailed information for a specific disk."""
        detailed_query = """
        query {
            disks {
                device
                name
                type
                size
                vendor
                temperature
                smartStatus
                state
                fsSize
                fsFree
                fsUsed
                numReads
                numWrites
                numErrors
            }
        }
        """

        try:
            detailed_response = await self._send_graphql_request(detailed_query)
            all_disks = detailed_response.get("data", {}).get("disks", [])
            # Find the specific disk by name
            return [d for d in all_disks if d.get("name") == disk_name]
        except Exception as err:
            _LOGGER.debug("Error getting detailed info for disk %s: %s", disk_name, err)
            return []

    async def get_disks_info(self) -> dict[str, Any]:
        """Get detailed information about all disks without waking sleeping disks."""
        # First get basic disk states without detailed queries
        basic_query = """
        query {
            disks {
                name
                state
                device
            }
        }
        """

        detailed_disks = []

        try:
            response = await self._send_graphql_request(basic_query)
            if "data" not in response or "disks" not in response["data"]:
                return {"disks": []}

            disks = response["data"]["disks"]

            for disk in disks:
                disk_state = disk.get("state", "").upper()
                disk_name = disk.get("name")

                if not disk_name:
                    continue

                # Only query detailed information for active disks
                if disk_state == "ACTIVE":
                    # Get detailed info for this specific disk
                    disk_details = await self._get_detailed_disk_info(disk_name)

                    if disk_details:
                        detailed_disks.extend(disk_details)
                        _LOGGER.debug(
                            "Got detailed info for active disk: %s", disk_name
                        )
                    else:
                        # Add basic info if detailed query failed
                        detailed_disks.append(self._create_basic_disk_info(disk))
                else:
                    # For inactive/sleeping disks, just add basic info
                    _LOGGER.debug(
                        "Skipping detailed queries for non-active disk: %s (state: %s)",
                        disk_name,
                        disk_state,
                    )
                    detailed_disks.append(self._create_basic_disk_info(disk))

            return {"disks": detailed_disks}

        except UnraidApiError as err:
            _LOGGER.warning("GraphQL disks query failed: %s", err)
            return {"disks": []}
        except Exception as err:
            _LOGGER.error("Error getting disks info: %s", err)
            return {"disks": []}

    async def _get_cpu_mb_temperatures(self) -> dict[str, Any]:
        """Get CPU and motherboard temperatures."""
        temperatures: dict[str, Any] = {"cpu": None, "motherboard": None}

        info_query = """
        query {
            info {
                cpu {
                    temperature
                }
                motherboard {
                    temperature
                }
            }
        }
        """

        try:
            response = await self._send_graphql_request(info_query)
            if "data" not in response or "info" not in response["data"]:
                return temperatures

            info_data = response["data"]["info"]

            # Get CPU temperature
            if "cpu" in info_data and info_data["cpu"] is not None:
                cpu_data = info_data["cpu"]
                if "temperature" in cpu_data and cpu_data["temperature"] is not None:
                    cpu_temp = float(cpu_data["temperature"])
                    temperatures["cpu"] = cpu_temp
                    _LOGGER.debug("CPU temperature: %s°C", temperatures["cpu"])

            # Get motherboard temperature
            if "motherboard" in info_data and info_data["motherboard"] is not None:
                mb_data = info_data["motherboard"]
                if "temperature" in mb_data and mb_data["temperature"] is not None:
                    mb_temp = float(mb_data["temperature"])
                    temperatures["motherboard"] = mb_temp
                    _LOGGER.debug(
                        "Motherboard temperature: %s°C", temperatures["motherboard"]
                    )

        except UnraidApiError as err:
            _LOGGER.debug("GraphQL info temperature query failed: %s", err)

        return temperatures

    async def _get_disk_temperatures(self) -> list[dict[str, Any]]:
        """Get disk temperatures as sensors with spindown awareness."""
        sensors: list[dict[str, Any]] = []

        try:
            # Get current disk states to determine which disks are safe to query
            disk_states = await self._get_disk_states()

            # Get all disk IDs
            all_disk_ids = list(disk_states.keys())

            if not all_disk_ids:
                _LOGGER.debug("No disks found for temperature monitoring")
                return sensors

            # Get safe disk health information (includes temperature)
            safe_disk_health = await self._get_safe_disk_health_info(all_disk_ids)

            # Process temperature data from safe disks
            for disk_id, health_data in safe_disk_health.items():
                temp = health_data.get("temperature")
                if temp is not None:
                    disk_name = health_data.get("name", "unknown")
                    disk_type = health_data.get("type", "unknown").lower()
                    sensor_name = f"{disk_type}_{disk_name}"

                    sensors.append({
                        "name": sensor_name,
                        "value": float(temp),
                        "source": "live"
                    })

                    _LOGGER.debug("Disk temperature sensor: %s = %s°C", sensor_name, temp)

            # Add cached temperature data for disks that are not safe to query
            for disk_id, disk_state in disk_states.items():
                if disk_id not in safe_disk_health:
                    last_temp = disk_state.get("last_known_temp")
                    if last_temp is not None:
                        disk_name = disk_state.get("name", "unknown")
                        disk_type = disk_state.get("type", "unknown").lower()
                        sensor_name = f"{disk_type}_{disk_name}"

                        sensors.append({
                            "name": sensor_name,
                            "value": float(last_temp),
                            "source": "cached",
                            "note": "Disk may be in standby"
                        })

                        _LOGGER.debug(
                            "Disk temperature sensor (cached): %s = %s°C",
                            sensor_name,
                            last_temp
                        )

        except UnraidApiError as err:
            _LOGGER.debug("GraphQL disk temperature query failed: %s", err)
        except Exception as err:
            _LOGGER.debug("Error getting disk temperatures: %s", err)

        return sensors

    async def _get_hardware_sensors(self) -> dict[str, Any]:
        """Get hardware sensors information including fans and temperatures."""
        result: dict[str, Any] = {
            "fans": [],
            "cpu": None,
            "motherboard": None,
            "temperatures": [],
        }

        # The hardware field is not available in the API
        # Let's use the system info endpoint directly
        hw_sensors_query = """
        query {
            info {
                system {
                    sensors {
                        fans {
                            name
                            rpm
                            status
                        }
                        temperatures {
                            name
                            temp
                            status
                        }
                    }
                }
            }
        }
        """

        try:
            response = await self._send_graphql_request(hw_sensors_query)
            if not self._is_valid_response(response):
                return result

            sensors_data = self._extract_sensors_data(response)
            if not sensors_data:
                return result

            # Process fan data
            self._process_fan_data(sensors_data, result)

            # Process temperature sensors
            self._process_temperature_data(sensors_data, result)

        except UnraidApiError as err:
            # This is expected to fail on many systems as the endpoint might not exist
            _LOGGER.debug("GraphQL hardware sensors query failed: %s", err)

        return result

    def _is_valid_response(self, response: dict[str, Any]) -> bool:
        """Check if the response is valid."""
        return "data" in response and "info" in response["data"]

    def _extract_sensors_data(self, response: dict[str, Any]) -> dict[str, Any] | None:
        """Extract sensors data from response."""
        info_data = response["data"]["info"]
        if "system" not in info_data or info_data["system"] is None:
            return None

        system_data = info_data["system"]
        if "sensors" not in system_data or system_data["sensors"] is None:
            return None

        return system_data["sensors"]

    def _process_fan_data(
        self, sensors_data: dict[str, Any], result: dict[str, Any]
    ) -> None:
        """Process fan data from sensors."""
        if not sensors_data.get("fans"):
            return

        for fan in sensors_data["fans"]:
            if "name" in fan and "rpm" in fan:
                rpm_value = None
                if fan["rpm"] is not None:
                    with contextlib.suppress(ValueError, TypeError):
                        rpm_value = int(fan["rpm"])

                result["fans"].append(
                    {
                        "name": fan["name"],
                        "rpm": rpm_value,
                        "status": fan.get("status", "unknown"),
                    }
                )

                _LOGGER.debug("Fan: %s, RPM: %s", fan["name"], fan["rpm"])

    def _process_temperature_data(
        self, sensors_data: dict[str, Any], result: dict[str, Any]
    ) -> None:
        """Process temperature data from sensors."""
        if not sensors_data.get("temperatures"):
            return

        for temp in sensors_data["temperatures"]:
            if "name" in temp and "temp" in temp and temp["temp"] is not None:
                try:
                    temp_value = float(temp["temp"])
                    result["temperatures"].append(
                        {
                            "name": temp["name"],
                            "value": temp_value,
                            "status": temp.get("status", "unknown"),
                        }
                    )
                    _LOGGER.debug(
                        "Temperature sensor: %s = %s°C",
                        temp["name"],
                        temp["temp"],
                    )
                except (ValueError, TypeError):
                    pass

    async def get_system_sensors(self) -> dict[str, Any]:
        """Get system sensors information including temperatures and fan speeds."""
        # Default return values
        result: dict[str, Any] = {
            "temperatures": {"cpu": None, "motherboard": None, "sensors": []},
            "fans": [],
            "hardware": {},
        }

        try:
            # Get CPU and motherboard temperatures from the info endpoint
            temp_data = await self._get_cpu_mb_temperatures()
            result["temperatures"]["cpu"] = temp_data["cpu"]
            result["temperatures"]["motherboard"] = temp_data["motherboard"]

            # Get disk temperatures
            result["temperatures"]["sensors"] = await self._get_disk_temperatures()

            # Get hardware sensors information
            hardware_data = await self._get_hardware_sensors()
            result["fans"] = hardware_data["fans"]
            result["hardware"] = hardware_data

            # If we have hardware CPU temperature but not from the info endpoint, use it
            if (
                result["temperatures"]["cpu"] is None
                and hardware_data["cpu"] is not None
            ):
                result["temperatures"]["cpu"] = hardware_data["cpu"]

            # If we have hardware motherboard temperature but not from the info endpoint, use it
            if (
                result["temperatures"]["motherboard"] is None
                and hardware_data["motherboard"] is not None
            ):
                result["temperatures"]["motherboard"] = hardware_data["motherboard"]

            # Add any additional temperature sensors from hardware
            for temp_sensor in hardware_data["temperatures"]:
                result["temperatures"]["sensors"].append(temp_sensor)

            return result

        except Exception as err:
            _LOGGER.error("Error getting system sensors: %s", err)
            return result

    async def get_network_info(self) -> dict[str, Any]:
        """Get network interface information."""
        query = """
        query {
            network {
                iface
                ifaceName
                ipv4
                ipv6
                mac
                operstate
                type
                duplex
                speed
                accessUrls {
                    type
                    name
                    ipv4
                    ipv6
                }
            }
        }
        """
        try:
            response = await self._send_graphql_request(query)
            return response.get("data", {})
        except UnraidApiError as err:
            _LOGGER.warning("GraphQL network query failed: %s", err)
            return {"network": []}
        except Exception as err:
            _LOGGER.error("Error getting network info: %s", err)
            return {"network": []}

    async def get_parity_history(self) -> dict[str, Any]:
        """Get parity check history."""
        query = """
        query {
            parityHistory {
                date
                duration
                speed
                status
                errors
            }
        }
        """
        try:
            response = await self._send_graphql_request(query)
            return response.get("data", {})
        except UnraidApiError as err:
            _LOGGER.warning("GraphQL parity history query failed: %s", err)
            return {"parityHistory": []}
        except Exception as err:
            _LOGGER.error("Error getting parity history: %s", err)
            return {"parityHistory": []}

    async def start_array(self) -> dict[str, Any]:
        """Start array."""
        query = """
        mutation StartArray {
            array {
                setState(input: {desiredState: START}) {
                    state
                }
            }
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {}).get("array", {})

    async def stop_array(self) -> dict[str, Any]:
        """Stop array."""
        query = """
        mutation StopArray {
            array {
                setState(input: {desiredState: STOP}) {
                    state
                }
            }
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {}).get("array", {})

    async def start_parity_check(self, correct: bool = False) -> dict[str, Any]:
        """Start parity check."""
        query = """
        mutation StartParityCheck($correct: Boolean!) {
            parityCheck {
                start(correct: $correct)
            }
        }
        """
        variables = {"correct": correct}
        response = await self._send_graphql_request(query, variables)
        return response.get("data", {}).get("parityCheck", {})

    async def pause_parity_check(self) -> dict[str, Any]:
        """Pause parity check."""
        query = """
        mutation {
            parityCheck {
                pause
            }
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {}).get("parityCheck", {})

    async def resume_parity_check(self) -> dict[str, Any]:
        """Resume parity check."""
        query = """
        mutation {
            parityCheck {
                resume
            }
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {}).get("parityCheck", {})

    async def cancel_parity_check(self) -> dict[str, Any]:
        """Cancel parity check."""
        query = """
        mutation {
            parityCheck {
                cancel
            }
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {}).get("parityCheck", {})

    async def reboot(self) -> dict[str, Any]:
        """Reboot server."""
        query = """
        mutation {
            reboot
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def shutdown(self) -> dict[str, Any]:
        """Shutdown server."""
        query = """
        mutation {
            shutdown
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def start_docker_container(self, container_id: str) -> dict[str, Any]:
        """Start a Docker container.

        Args:
            container_id: The ID of the container to start. Can be a prefixed ID or actual ID.

        Returns:
            Dictionary containing the response data or error information

        """
        # Extract the actual ID if it's a prefixed ID
        actual_id = extract_id(container_id)

        # First try with String! as used in the mobile app
        query = """
        mutation StartContainer($id: String!) {
            docker {
                start(id: $id) {
                    id
                    names
                    image
                    state
                    status
                    autoStart
                }
            }
        }
        """
        variables = {"id": actual_id}

        try:
            response = await self._send_graphql_request(query, variables)
            return response.get("data", {}).get("docker", {})
        except UnraidApiError as err:
            _LOGGER.warning("Failed with String! type, trying PrefixedID: %s", err)

            # Fallback to PrefixedID if String! doesn't work
            fallback_query = """
            mutation StartContainer($id: PrefixedID!) {
                docker {
                    start(id: $id) {
                        id
                        state
                    }
                }
            }
            """

            try:
                response = await self._send_graphql_request(fallback_query, variables)
                return response.get("data", {}).get("docker", {})
            except UnraidApiError as fallback_err:
                if "ArrayRunningError" in str(fallback_err):
                    _LOGGER.error(
                        "Cannot start container while array is running: %s",
                        fallback_err,
                    )
                elif "Authentication" in str(fallback_err) or "Forbidden" in str(
                    fallback_err
                ):
                    _LOGGER.error(
                        "Authentication failed or insufficient permissions: %s",
                        fallback_err,
                    )
                else:
                    _LOGGER.error("Failed to start Docker container: %s", fallback_err)
                return {"error": str(fallback_err)}

    async def stop_docker_container(self, container_id: str) -> dict[str, Any]:
        """Stop a Docker container.

        Args:
            container_id: The ID of the container to stop. Can be a prefixed ID or actual ID.

        Returns:
            Dictionary containing the response data or error information

        """
        # Extract the actual ID if it's a prefixed ID
        actual_id = extract_id(container_id)

        # First try with String! as used in the mobile app
        query = """
        mutation StopContainer($id: String!) {
            docker {
                stop(id: $id) {
                    id
                    names
                    image
                    state
                    status
                    autoStart
                }
            }
        }
        """
        variables = {"id": actual_id}

        try:
            response = await self._send_graphql_request(query, variables)
            return response.get("data", {}).get("docker", {})
        except UnraidApiError as err:
            _LOGGER.warning("Failed with String! type, trying PrefixedID: %s", err)

            # Fallback to PrefixedID if String! doesn't work
            fallback_query = """
            mutation StopContainer($id: PrefixedID!) {
                docker {
                    stop(id: $id) {
                        id
                        state
                    }
                }
            }
            """

            try:
                response = await self._send_graphql_request(fallback_query, variables)
                return response.get("data", {}).get("docker", {})
            except UnraidApiError as fallback_err:
                if "ArrayRunningError" in str(fallback_err):
                    _LOGGER.error(
                        "Cannot stop container while array is running: %s", fallback_err
                    )
                elif "Authentication" in str(fallback_err) or "Forbidden" in str(
                    fallback_err
                ):
                    _LOGGER.error(
                        "Authentication failed or insufficient permissions: %s",
                        fallback_err,
                    )
                else:
                    _LOGGER.error("Failed to stop Docker container: %s", fallback_err)
                return {"error": str(fallback_err)}

    async def restart_docker_container(self, container_id: str) -> dict[str, Any]:
        """Restart a Docker container."""
        # First stop the container
        stop_result = await self.stop_docker_container(container_id)
        if "error" in stop_result:
            return stop_result

        # Then start it again
        return await self.start_docker_container(container_id)

    async def get_docker_logs(
        self, container_id: str, lines: int = 100
    ) -> dict[str, Any]:
        """Get logs from a Docker container.

        Args:
            container_id: The ID of the container to get logs from
            lines: Number of log lines to retrieve (default: 100)

        Returns:
            Dictionary containing the logs or error information

        """
        # Extract the actual ID if it's a prefixed ID
        actual_id = extract_id(container_id)

        # Use the logs query from the GraphQL API
        query = """
        query GetContainerLogs($id: PrefixedID!, $lines: Int) {
            docker {
                container(id: $id) {
                    logs(lines: $lines)
                }
            }
        }
        """
        variables = {"id": actual_id, "lines": lines}

        try:
            response = await self._send_graphql_request(query, variables)
            container_data = (
                response.get("data", {}).get("docker", {}).get("container", {})
            )

            if not container_data:
                return {"error": "Container not found or no logs available"}

            logs = container_data.get("logs", "")
            return {"logs": logs}
        except UnraidApiError as err:
            _LOGGER.error("Failed to get Docker container logs: %s", err)
            return {"error": str(err)}

    async def manage_vm(self, vm_id: str, action: str, **kwargs) -> dict[str, Any]:
        """Unified VM management with comprehensive error handling.

        Combines the efficiency of single-function design with robust error handling.

        Args:
            vm_id: The ID of the VM to manage. Can be a prefixed ID or actual ID.
            action: The action to perform (start, stop, pause, resume, reboot, force_stop)
            **kwargs: Additional parameters (e.g., force=True for stop)

        Returns:
            Dictionary containing the response data or error information
        """
        # Validate action
        valid_actions = ["start", "stop", "pause", "resume", "reboot", "force_stop"]
        if action not in valid_actions:
            return {
                "error": f"Invalid action '{action}'. Must be one of: {', '.join(valid_actions)}",
                "code": "INVALID_ACTION"
            }

        # Extract the actual ID if it's a prefixed ID
        actual_id = extract_id(vm_id)

        # Map actions to their GraphQL mutations and parameter types
        action_config = {
            "start": {
                "mutation": "start",
                "id_type": "PrefixedID!",
                "params": {}
            },
            "stop": {
                "mutation": "stop",
                "id_type": "PrefixedID!",
                "params": {"force": kwargs.get("force", False)}
            },
            "pause": {
                "mutation": "pause",
                "id_type": "String!",
                "params": {}
            },
            "resume": {
                "mutation": "resume",
                "id_type": "String!",
                "params": {}
            },
            "reboot": {
                "mutation": "reboot",
                "id_type": "PrefixedID!",
                "params": {}
            },
            "force_stop": {
                "mutation": "forceStop",
                "id_type": "PrefixedID!",
                "params": {}
            }
        }

        config = action_config[action]
        mutation_name = config["mutation"]
        id_type = config["id_type"]
        params = config["params"]

        # Build the GraphQL mutation dynamically
        param_definitions = [f"$id: {id_type}"]
        param_calls = ["id: $id"]
        variables = {"id": actual_id}

        # Add additional parameters if needed
        for param_name, param_value in params.items():
            if param_value is not None:
                param_type = "Boolean" if isinstance(param_value, bool) else "String"
                param_definitions.append(f"${param_name}: {param_type}")
                param_calls.append(f"{param_name}: ${param_name}")
                variables[param_name] = param_value

        query = f"""
        mutation {mutation_name.title()}Vm({', '.join(param_definitions)}) {{
            vm {{
                {mutation_name}({', '.join(param_calls)})
            }}
        }}
        """

        try:
            response = await self._send_graphql_request(query, variables)
            result = response.get("data", {}).get("vm", {})

            if result and mutation_name in result:
                success = result[mutation_name]
                return {
                    "success": success,
                    "action": action,
                    "vm_id": vm_id,
                    "mutation": mutation_name
                }
            elif result:
                return result
            else:
                return {
                    "error": f"Failed to {action} VM or unexpected response structure",
                    "code": "UNEXPECTED_RESPONSE"
                }

        except UnraidApiError as err:
            return self._handle_vm_error(err, action, vm_id)
        except Exception as err:
            _LOGGER.error("Unexpected error during VM %s: %s", action, err)
            return {
                "error": f"Unexpected error during VM {action}: {err}",
                "code": "UNEXPECTED_ERROR"
            }

    def _handle_vm_error(self, err: UnraidApiError, action: str, vm_id: str) -> dict[str, Any]:
        """Handle VM operation errors with specific error codes."""
        error_str = str(err)

        if "ArrayRunningError" in error_str:
            return {
                "error": f"Cannot {action} VM while array is running",
                "code": "ARRAY_RUNNING",
                "vm_id": vm_id
            }
        elif "Authentication" in error_str or "Forbidden" in error_str:
            return {
                "error": f"Authentication failed or insufficient permissions for VM {action}",
                "code": "AUTH_FAILED",
                "vm_id": vm_id
            }
        elif "VMs are not available" in error_str:
            return {
                "error": "VM service is not available on this Unraid server",
                "code": "VM_SERVICE_UNAVAILABLE",
                "vm_id": vm_id
            }
        elif "not found" in error_str.lower():
            return {
                "error": f"VM with ID '{vm_id}' not found",
                "code": "VM_NOT_FOUND",
                "vm_id": vm_id
            }
        else:
            return {
                "error": f"Failed to {action} VM: {err}",
                "code": "API_ERROR",
                "vm_id": vm_id
            }

    async def start_vm(self, vm_id: str) -> dict[str, Any]:
        """Start a virtual machine.

        Wrapper for manage_vm for backward compatibility.
        """
        return await self.manage_vm(vm_id, "start")

    async def stop_vm(self, vm_id: str, force: bool = False) -> dict[str, Any]:
        """Stop a virtual machine.

        Wrapper for manage_vm for backward compatibility.
        """
        return await self.manage_vm(vm_id, "stop", force=force)

    async def pause_vm(self, vm_id: str) -> dict[str, Any]:
        """Pause a virtual machine.

        Wrapper for manage_vm for backward compatibility.
        """
        return await self.manage_vm(vm_id, "pause")

    async def resume_vm(self, vm_id: str) -> dict[str, Any]:
        """Resume a paused virtual machine.

        Wrapper for manage_vm for backward compatibility.
        """
        return await self.manage_vm(vm_id, "resume")

    async def reboot_vm(self, vm_id: str) -> dict[str, Any]:
        """Reboot a virtual machine.

        Wrapper for manage_vm for backward compatibility.
        """
        return await self.manage_vm(vm_id, "reboot")

    async def reset_vm(self, vm_id: str) -> dict[str, Any]:
        """Reset a virtual machine (hard reboot).

        Attempts to reset a VM using the VM mutation API.
        Falls back to alternative methods if the primary method fails.

        Args:
            vm_id: The UUID of the VM to reset

        Returns:
            Dictionary containing the response data or error information

        """
        # Extract the actual ID if it's a prefixed ID
        actual_id = extract_id(vm_id)

        # First try with String! as used in the mobile app
        query = """
        mutation ResetVm($id: String!) {
            vm {
                reset(id: $id)
            }
        }
        """
        variables = {"id": actual_id}
        try:
            response = await self._send_graphql_request(query, variables)
            result = response.get("data", {}).get("vm", {})
            if result:
                # After successful reset, fetch the updated VM data
                vm_data = await self._get_vm_data(actual_id)
                if vm_data:
                    return vm_data
                return result
        except UnraidApiError as err:
            _LOGGER.warning("Failed to reset VM with standard mutation: %s", err)

            # Try alternative mutation format
            try:
                alt_query = """
                mutation ResetVm($uuid: String!) {
                    vms {
                        reset(uuid: $uuid)
                    }
                }
                """
                alt_variables = {"uuid": actual_id}
                alt_response = await self._send_graphql_request(
                    alt_query, alt_variables
                )
                alt_result = alt_response.get("data", {}).get("vms", {})
                if alt_result:
                    return alt_result
            except UnraidApiError as alt_err:
                _LOGGER.warning(
                    "Failed to reset VM with alternative mutation: %s", alt_err
                )

                # Try a third mutation format
                try:
                    third_query = f"""
                    mutation {{
                        vm {{
                            domain(id: "{actual_id}") {{
                                reset
                            }}
                        }}
                    }}
                    """
                    third_response = await self._send_graphql_request(third_query)
                    third_result = third_response.get("data", {}).get("vm", {})
                    if third_result:
                        return third_result
                except UnraidApiError as third_err:
                    _LOGGER.error("All VM reset mutations failed: %s", third_err)
                    return {"error": str(third_err)}

            return {"error": str(err)}

        # This line should never be reached, but is needed to satisfy mypy
        return {"error": "Unknown error resetting VM"}

    async def force_stop_vm(self, vm_id: str) -> dict[str, Any]:
        """Force stop a virtual machine.

        Wrapper for manage_vm for backward compatibility.
        """
        return await self.manage_vm(vm_id, "force_stop")

    async def _get_vm_data(self, vm_id: str) -> dict[str, Any] | None:
        """Get detailed data for a specific VM.

        Args:
            vm_id: The ID of the VM to get data for

        Returns:
            Dictionary containing VM data or None if not found

        """
        try:
            query = """
            query GetVmData($id: String!) {
                vms {
                    domains(id: $id) {
                        uuid
                        name
                        state
                    }
                }
            }
            """
            variables = {"id": vm_id}
            response = await self._send_graphql_request(query, variables)
            domains = response.get("data", {}).get("vms", {}).get("domains", [])
            if domains and len(domains) > 0:
                return domains[0]
            return None
        except UnraidApiError as err:
            _LOGGER.warning("Failed to get VM data: %s", err)
            return None

    async def get_notifications(self, limit: int = 10) -> dict[str, Any]:
        """Get notifications from the Unraid server.

        Args:
            limit: Maximum number of notifications to retrieve

        Returns:
            Dictionary containing notification overview and list of notifications

        """
        query = """
        query GetNotifications($limit: Int!) {
            notifications {
                overview {
                    unread {
                        info
                        warning
                        alert
                        total
                    }
                }
                list(filter: {type: UNREAD, offset: 0, limit: $limit}) {
                    id
                    title
                    description
                    importance
                    timestamp
                }
            }
        }
        """
        variables = {"limit": limit}

        try:
            response = await self._send_graphql_request(query, variables)
            if "data" in response and "notifications" in response.get("data", {}):
                return response.get("data", {}).get("notifications", {})
            return {"overview": {"unread": {"total": 0}}, "list": []}
        except UnraidApiError as err:
            _LOGGER.warning("Failed to get notifications: %s", err)
            return {"overview": {"unread": {"total": 0}}, "list": []}
        except Exception as err:
            _LOGGER.error("Error getting notifications: %s", err)
            return {"overview": {"unread": {"total": 0}}, "list": []}

    async def validate_api_connection(self) -> bool:
        """Test if we can authenticate with the API."""
        try:
            # Try to discover redirect URL first
            await self.discover_redirect_url()

            # Use a very simple query that's likely to succeed even with limited permissions
            query = """
            query {
                online
            }
            """

            # Try direct API access
            try:
                response = await self._send_graphql_request(query)
                if "data" in response and response.get("data") is not None:
                    _LOGGER.debug("Authentication successful with default headers")
                    return True
            except UnraidApiError as err:
                _LOGGER.debug("Authentication failed with default headers: %s", err)

                # If that fails, try with a few different API key formats
                api_key_formats = [
                    # Standard key
                    self.api_key,
                    # With unraid_ prefix
                    f"unraid_{self.api_key}"
                    if not self.api_key.startswith("unraid_")
                    else self.api_key,
                ]

                for key_format in api_key_formats:
                    try:
                        self.headers["x-api-key"] = key_format
                        response = await self._send_graphql_request(query)
                        if "data" in response and response.get("data") is not None:
                            _LOGGER.debug(
                                "Authentication successful with API key format: %s",
                                key_format,
                            )
                            # Keep using this successful format
                            self.api_key = key_format
                            return True
                    except UnraidApiError as key_err:
                        _LOGGER.debug(
                            "API key format %s failed: %s", key_format, key_err
                        )

            # Try a different URL pattern as a fallback
            try:
                _LOGGER.debug("Trying direct HTTP request to check status")
                # Let's try to query a simple endpoint directly
                api_url = f"{self.host}/plugins/connect/api.php?action=status"
                headers = {
                    "x-api-key": self.api_key,
                    "Origin": self.host,
                    "Referer": self.host,
                }

                async with self.session.get(
                    api_url, headers=headers, ssl=self.verify_ssl
                ) as resp:
                    if resp.status == 200:
                        _LOGGER.debug("Direct HTTP request successful")
                        return True
            except Exception as err:
                _LOGGER.debug("Direct HTTP request failed: %s", err)

            _LOGGER.error("All authentication attempts failed")
            _LOGGER.error("Please make sure:")
            _LOGGER.error("1. Your API key is correct")
            _LOGGER.error(
                "2. Try using the HTTPS URL directly: %s",
                self.redirect_url or self.host,
            )
            _LOGGER.error(
                "3. If using a redirected URL, make sure SSL verification is enabled"
            )
            _LOGGER.error(
                "4. You might need to restart the Unraid Connect services from the Plugins tab"
            )

            return False

        except Exception as err:
            _LOGGER.error("Error validating API connection: %s", err)
            return False
