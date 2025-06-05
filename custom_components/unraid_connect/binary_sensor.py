"""Binary sensor platform for Unraid integration."""
# ruff: noqa: TRY300

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    EntityCategory,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ARRAY_STATE_STARTED,
    ATTR_CONTAINER_IMAGE,
    ATTR_CONTAINER_STATUS,
    ATTR_DISK_NAME,
    ATTR_DISK_SERIAL,
    ATTR_DISK_SIZE,
    ATTR_DISK_TEMP,
    ATTR_DISK_TYPE,
    ATTR_VM_STATE,
    CONTAINER_STATE_RUNNING,
    DOMAIN as INTEGRATION_DOMAIN,
    ICON_ARRAY,
    ICON_DISK,
    ICON_DOCKER,
    ICON_VM,
    VM_STATE_RUNNING,
)
from .coordinator import UnraidDataUpdateCoordinator
from .entity import (
    UnraidArrayEntity,
    UnraidDiskEntity,
    UnraidDockerEntity,
    UnraidSystemEntity,
    UnraidVMEntity,
)

PARALLEL_UPDATES = 1

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Unraid binary sensors."""
    coordinator = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["coordinator"]
    name = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["name"]

    entities: list[BinarySensorEntity] = []

    # Add system binary sensors
    entities.append(UnraidOnlineBinarySensor(coordinator, name))

    # Add array binary sensors
    array_sensor = UnraidArrayRunningBinarySensor(coordinator, name)
    entities.append(array_sensor)

    # Add disk binary sensors
    array_data = coordinator.data.get("array_status", {}).get("array", {})
    _LOGGER.debug("Setting up disk binary sensors with array data: %s", array_data)

    # Add data disks
    data_disks = array_data.get("disks", [])
    _LOGGER.debug("Found %s data disks", len(data_disks))
    for disk in data_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            _LOGGER.debug(
                "Creating health sensor for data disk %s (%s)", disk_name, disk_id
            )
            disk_health_sensor = UnraidDiskHealthBinarySensor(
                coordinator, name, disk_id, disk_name, "Data"
            )
            entities.append(disk_health_sensor)

    # Add parity disks
    parity_disks = array_data.get("parities", [])
    _LOGGER.debug("Found %s parity disks", len(parity_disks))
    for disk in parity_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            _LOGGER.debug(
                "Creating health sensor for parity disk %s (%s)", disk_name, disk_id
            )
            parity_health_sensor = UnraidDiskHealthBinarySensor(
                coordinator, name, disk_id, disk_name, "Parity"
            )
            entities.append(parity_health_sensor)

    # Add cache disks
    cache_disks = array_data.get("caches", [])
    _LOGGER.debug("Found %s cache disks", len(cache_disks))
    for disk in cache_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            _LOGGER.debug(
                "Creating health sensor for cache disk %s (%s)", disk_name, disk_id
            )
            cache_health_sensor = UnraidDiskHealthBinarySensor(
                coordinator, name, disk_id, disk_name, "Cache"
            )
            entities.append(cache_health_sensor)

    # Add docker container binary sensors
    docker_data = coordinator.data.get("docker_containers", {}).get(
        "dockerContainers", []
    )
    for container in docker_data:
        if container.get("id") and container.get("names"):
            container_id = container.get("id")
            container_name = (
                container.get("names", [])[0]
                if container.get("names")
                else container_id
            )
            docker_sensor = UnraidDockerContainerRunningBinarySensor(
                coordinator, name, container_id, container_name
            )
            entities.append(docker_sensor)

    # Add VM binary sensors
    vm_data = coordinator.data.get("vms", {}).get("domain", [])
    for vm in vm_data:
        if vm.get("uuid") and vm.get("name"):
            vm_id = vm.get("uuid")
            vm_name = vm.get("name")
            vm_sensor = UnraidVMRunningBinarySensor(coordinator, name, vm_id, vm_name)
            entities.append(vm_sensor)

    _LOGGER.debug("Adding %s binary sensor entities to Home Assistant", len(entities))
    async_add_entities(entities)


class UnraidOnlineBinarySensor(UnraidSystemEntity, BinarySensorEntity):
    """Binary sensor for Unraid online status."""

    _attr_name = "Server Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, server_name, "online")  # Add the entity_key

    @property
    def is_on(self) -> bool:
        """Return true if the server is online."""
        try:
            return self.coordinator.data.get("system_info", {}).get("online", False)
        except (KeyError, AttributeError, TypeError):
            return False


class UnraidArrayRunningBinarySensor(UnraidArrayEntity, BinarySensorEntity):
    """Binary sensor for Unraid array running status."""

    _attr_name = "Array Running"
    _attr_icon = ICON_ARRAY
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, server_name, "array")

    @property
    def is_on(self) -> bool:
        """Return true if the array is running."""
        try:
            state = (
                self.coordinator.data.get("array_status", {})
                .get("array", {})
                .get("state")
            )
            if state is not None:
                return state == ARRAY_STATE_STARTED
            # If state is None
            return False
        except (KeyError, AttributeError, TypeError):
            return False


class UnraidDiskHealthBinarySensor(UnraidDiskEntity, BinarySensorEntity):
    """Binary sensor for Unraid disk health."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = ICON_DISK

    def _format_size(self, size_bytes: float) -> str:
        """Format bytes into a human-readable string."""
        if size_bytes < 1024:
            return f"{size_bytes:.2f} B"
        if size_bytes < 1024**2:
            return f"{size_bytes / 1024:.2f} KB"
        if size_bytes < 1024**3:
            return f"{size_bytes / (1024**2):.2f} MB"
        if size_bytes < 1024**4:
            return f"{size_bytes / (1024**3):.2f} GB"
        return f"{size_bytes / (1024**4):.2f} TB"

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        disk_id: str,
        disk_name: str,
        disk_type: str,
    ) -> None:
        """Initialize the binary sensor."""
        # Clean disk name to handle any potential slashes
        disk_name = disk_name.replace("/", "_")

        # Use "health" as entity_key to make the entity ID follow the pattern binary_sensor.servername_disk_health
        super().__init__(coordinator, server_name, "health", disk_id, disk_type)

        self._disk_name = disk_name
        # Set the display name with proper formatting
        formatted_disk_name = self._format_disk_name_for_display(disk_name)
        self._attr_name = f"{formatted_disk_name} Health"

        # Override the unique_id to ensure it follows the desired pattern
        self._attr_unique_id = f"{coordinator.api.host}_disk_{disk_id}_health"

        # Track if the disk is in standby mode
        self._is_standby = False
        self._last_known_problem = None

        # Store the last known temperature to preserve it when disk is in standby
        self._last_known_temp: float | None = None

        _LOGGER.debug(
            "Created disk health binary sensor: entity_id=%s, unique_id=%s, name=%s",
            f"binary_sensor.{server_name.lower()}_{disk_name.lower()}_health",
            self._attr_unique_id,
            self._attr_name,
        )

    def _format_disk_name_for_display(self, disk_name: str) -> str:
        """Format disk name for user-friendly display."""
        # Handle numbered disks (disk1, disk2, etc.)
        if disk_name.startswith("disk") and disk_name[4:].isdigit():
            disk_number = disk_name[4:]
            return f"Disk {disk_number}"

        # Handle special disk names with proper capitalization
        if disk_name.lower() == "cache":
            return "Cache"
        elif disk_name.lower() == "parity":
            return "Parity"
        elif disk_name.lower() == "garbage":
            return "Garbage"
        else:
            # For other names, capitalize first letter
            return disk_name.capitalize()

    def _format_size(self, size_bytes: float) -> str:
        """Format size in bytes to human readable format."""
        if size_bytes == 0:
            return "0 B"

        units = ["B", "KB", "MB", "GB", "TB", "PB"]
        unit_index = 0
        size = float(size_bytes)

        while size >= 1024 and unit_index < len(units) - 1:
            size /= 1024
            unit_index += 1

        if unit_index == 0:
            return f"{int(size)} {units[unit_index]}"
        else:
            return f"{size:.2f} {units[unit_index]}"

    def _translate_disk_status(self, status: str | None) -> str:
        """Translate technical disk status codes to user-friendly descriptions."""
        if not status:
            return "Unknown"

        status_translations = {
            "DISK_OK": "Healthy",
            "DISK_DSBL": "Disabled",
            "DISK_NP": "Not Present",
            "DISK_NP_DSBL": "Not Present (Disabled)",
            "DISK_INVALID": "Invalid",
            "DISK_WRONG": "Wrong Disk",
            "DISK_NEW": "New Disk",
            "DISK_EMULATED": "Emulated",
            "DISK_MISSING": "Missing",
            "DISK_ERROR": "Error",
            "DISK_UNKNOWN": "Unknown Status",
        }

        return status_translations.get(status, status)

    def _translate_disk_state(self, state: str | None) -> str:
        """Translate technical disk state codes to user-friendly descriptions."""
        if not state:
            return "Unknown"

        state_translations = {
            "ACTIVE": "Active",
            "STANDBY": "Standby (Power Saving)",
            "SPUN_DOWN": "Spun Down",
            "SPINNING_UP": "Spinning Up",
            "SPINNING_DOWN": "Spinning Down",
            "IDLE": "Idle",
            "OFFLINE": "Offline",
        }

        return state_translations.get(state.upper(), state)

    @property
    def is_on(self) -> bool:
        """Return true if the disk has a problem."""
        try:
            array_data = self.coordinator.data.get("array_status", {}).get("array", {})

            # Look in different disk arrays based on type
            if self._disk_type == "Parity":
                disks = array_data.get("parities", [])
            elif self._disk_type == "Cache":
                disks = array_data.get("caches", [])
            else:
                disks = array_data.get("disks", [])

            for disk in disks:
                if disk.get("id") == self._disk_id:
                    # Check if disk is in standby mode
                    disk_state = disk.get("state", "").upper()
                    self._is_standby = disk_state == "STANDBY"

                    # Any disk, active or standby, should report a problem if status is not DISK_OK
                    # This doesn't wake the disk but reports problems based on the state Unraid already knows
                    has_problem = disk.get("status") != "DISK_OK"

                    # Store the last known problem state
                    if not self._is_standby or self._last_known_problem is None:
                        self._last_known_problem = has_problem

                    # If the disk is in standby, use the last known problem state
                    # This prevents unnecessary disk wakeups just to check health
                    if self._is_standby:
                        return bool(self._last_known_problem)
                    return has_problem

            # Default to problem if disk not found
            if self._last_known_problem is None:
                return True
            return bool(self._last_known_problem)
        except (KeyError, AttributeError, TypeError):
            if self._last_known_problem is None:
                return True
            return bool(self._last_known_problem)

    @property
    def state(self) -> str:
        """Return a user-friendly state instead of on/off."""
        if not self.available:
            return "unavailable"

        # For PROBLEM device class: off = healthy, on = problem
        if self.is_on:
            return "Problem"
        else:
            return "OK"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        try:
            array_data = self.coordinator.data.get("array_status", {}).get("array", {})

            # Look in different disk arrays based on type
            if self._disk_type == "Parity":
                disks = array_data.get("parities", [])
            elif self._disk_type == "Cache":
                disks = array_data.get("caches", [])
            else:
                disks = array_data.get("disks", [])

            for disk in disks:
                if disk.get("id") == self._disk_id:
                    return super().available

            # If we get here, the disk doesn't exist
            # No disk found in the loop
            return False
        except (KeyError, AttributeError, TypeError):
            return False

    def _get_disk_attributes(
        self, disk: dict[str, Any], disk_state: str
    ) -> dict[str, Any]:
        """Get disk attributes with user-friendly formatting."""
        attributes = {
            "Disk Name": disk.get("name"),
            "Disk Type": self._disk_type,
            "Health Status": self._translate_disk_status(disk.get("status")),
            "Power State": self._translate_disk_state(disk_state),
        }

        # Add device path if available
        if disk.get("device"):
            attributes["Device Path"] = f"/dev/{disk.get('device')}"

        # Add serial number if available
        if disk.get("serial"):
            attributes["Serial Number"] = disk.get("serial")

        # Add size if available and not in standby
        if disk.get("size") and disk_state != "STANDBY":
            try:
                size_value = disk.get("size")
                if size_value is not None:
                    size_bytes = float(size_value)
                    attributes["Disk Capacity"] = self._format_size(size_bytes)
            except (ValueError, TypeError):
                attributes["Disk Capacity"] = str(disk.get("size"))

        # Add rotational status if available
        if "rotational" in disk:
            is_rotational = disk.get("rotational", True)
            attributes["Drive Type"] = "Hard Disk Drive (HDD)" if is_rotational else "Solid State Drive (SSD/NVMe)"

        # Add temperature if available and not in standby
        self._add_temperature_attributes(attributes, disk, disk_state)

        # Add disk usage information if available
        self._add_disk_usage_attributes(attributes, disk, disk_state)

        # Add SMART health information
        self._add_smart_health_attributes(attributes, disk)

        return attributes

    def _add_smart_health_attributes(
        self, attributes: dict[str, Any], disk: dict[str, Any]
    ) -> None:
        """Add SMART health attributes to provide user information."""
        # Add SMART status only
        smart_status = disk.get("smartStatus")
        if smart_status:
            attributes["SMART Health"] = "Passed" if smart_status == "OK" else "Failed"

    def _add_temperature_attributes(
        self, attributes: dict[str, Any], disk: dict[str, Any], disk_state: str
    ) -> None:
        """Add temperature attributes to the disk."""
        # Skip temperature for bootdisk (sda) as it can't provide SMART reports
        if disk.get("device") == "sda" and disk.get("name", "").lower() == "bootdisk":
            attributes["Temperature"] = "Not Available (Boot Disk)"
            return

        # Check if we have health data source information
        health_data_source = disk.get("health_data_source", "unknown")

        # For disks with cached data (likely in standby), use cached values
        if health_data_source == "cached":
            temp = disk.get("temp") or disk.get("temperature")
            if temp is not None:
                try:
                    temp_value = float(temp)
                    attributes["Temperature"] = f"{temp_value}°C"
                    self._last_known_temp = temp_value
                except (ValueError, TypeError):
                    attributes["Temperature"] = "Not Available"
            else:
                attributes["Temperature"] = "Not Available (Disk in Standby)"
            return

        # For disks in standby (legacy detection), we don't want to wake them just to get temperature
        if disk_state == "STANDBY":
            # If we have a last known temperature, use it
            if hasattr(self, "_last_known_temp") and self._last_known_temp is not None:
                attributes["Temperature"] = f"{self._last_known_temp}°C"
            else:
                attributes["Temperature"] = "Not Available (Disk in Standby)"
            return

        # For active disks, try to get the temperature
        temp = None
        temp_source = None

        # First try the temp field
        if disk.get("temp") is not None:
            temp = disk.get("temp")
            temp_source = "temp field"

        # Then try the temperature field
        elif disk.get("temperature") is not None:
            temp = disk.get("temperature")
            temp_source = "temperature field"

        # Then try the smart data if available
        elif disk.get("smart") and isinstance(disk.get("smart"), dict):
            smart_data = disk.get("smart", {})
            if smart_data.get("temperature") is not None:
                temp = smart_data.get("temperature")
                temp_source = "SMART data"

        # If we found a temperature, add it to the attributes
        if temp is not None:
            try:
                temp_value = float(temp)
                attributes["Temperature"] = f"{temp_value}°C"
                # Store the temperature for future use
                self._last_known_temp = temp_value
            except (ValueError, TypeError):
                attributes["Temperature"] = "Not Available"
        # For SSDs/NVMe with no temperature, provide a default
        elif not disk.get("rotational", True):
            temp_value = 35.0  # Default temperature for SSDs
            attributes["Temperature"] = f"{temp_value}°C"
            self._last_known_temp = temp_value
        else:
            attributes["Temperature"] = "Not Available"

    def _add_disk_usage_attributes(
        self, attributes: dict[str, Any], disk: dict[str, Any], disk_state: str
    ) -> None:
        """Add disk usage attributes if available."""
        # Skip usage attributes for disks in standby
        if disk_state == "STANDBY":
            return

        # Add filesystem type if available
        if disk.get("fsType"):
            attributes["File System Type"] = disk.get("fsType")

        # Special handling for ZFS disks
        if disk.get("fsType", "").lower() == "zfs":
            self._add_zfs_disk_usage_attributes(attributes, disk)
            return

        # Standard handling for non-ZFS disks
        self._add_standard_disk_usage_attributes(attributes, disk)

    def _add_standard_disk_usage_attributes(
        self, attributes: dict[str, Any], disk: dict[str, Any]
    ) -> None:
        """Add usage attributes for standard (non-ZFS) disks."""
        # Add filesystem size and used if available
        if disk.get("fsSize") and disk.get("fsUsed"):
            try:
                fs_size = float(disk.get("fsSize", 0))
                fs_used = float(disk.get("fsUsed", 0))
                fs_free = fs_size - fs_used

                if fs_size > 0:
                    # Add usage percentage
                    usage_percent = round((fs_used / fs_size) * 100, 1)
                    attributes["Usage"] = f"{usage_percent}%"

                    # Add formatted values only
                    attributes["Capacity"] = self._format_size(fs_size)
                    attributes["Used Space"] = self._format_size(fs_used)
                    attributes["Free Space"] = self._format_size(fs_free)
            except (ValueError, TypeError):
                pass
        else:
            # If fsSize/fsUsed are not available, try size/free
            size = disk.get("size")
            free = disk.get("free")
            if size and free:
                try:
                    size_float = float(size)
                    free_float = float(free)
                    used_float = size_float - free_float

                    if size_float > 0:
                        # Add usage percentage
                        usage_percent = round((used_float / size_float) * 100, 1)
                        attributes["usage_percent"] = usage_percent

                        # Add formatted values
                        attributes["fs_size"] = self._format_size(size_float)
                        attributes["fs_used"] = self._format_size(used_float)
                        attributes["fs_free"] = self._format_size(free_float)

                        # Add raw values in KB
                        attributes["fs_size_kb"] = int(size_float)
                        attributes["fs_used_kb"] = int(used_float)
                        attributes["fs_free_kb"] = int(free_float)
                except (ValueError, TypeError):
                    pass

    def _add_zfs_disk_usage_attributes(
        self, attributes: dict[str, Any], disk: dict[str, Any]
    ) -> None:
        """Add usage attributes for ZFS disks."""
        # First try zfs specific fields
        zfs_size = disk.get("zfsSize")
        zfs_used = disk.get("zfsUsed")

        if zfs_size and zfs_used:
            try:
                zfs_size_float = float(zfs_size)
                zfs_used_float = float(zfs_used)
                zfs_free_float = zfs_size_float - zfs_used_float

                if zfs_size_float > 0:
                    # Add usage percentage
                    usage_percent = round((zfs_used_float / zfs_size_float) * 100, 1)
                    attributes["usage_percent"] = usage_percent

                    # Add formatted values
                    attributes["fs_size"] = self._format_size(zfs_size_float)
                    attributes["fs_used"] = self._format_size(zfs_used_float)
                    attributes["fs_free"] = self._format_size(zfs_free_float)

                    # Add raw values in KB
                    attributes["fs_size_kb"] = int(zfs_size_float)
                    attributes["fs_used_kb"] = int(zfs_used_float)
                    attributes["fs_free_kb"] = int(zfs_free_float)
                    return
                # If we can't parse the values
                return
            except (ValueError, TypeError):
                pass

        # If ZFS specific fields aren't available, try standard fields
        if disk.get("fsSize") and disk.get("fsUsed"):
            try:
                fs_size = float(disk.get("fsSize", 0))
                fs_used = float(disk.get("fsUsed", 0))
                fs_free = fs_size - fs_used

                if fs_size > 0:
                    # Add usage percentage
                    usage_percent = round((fs_used / fs_size) * 100, 1)
                    attributes["usage_percent"] = usage_percent

                    # Add formatted values
                    attributes["fs_size"] = self._format_size(fs_size)
                    attributes["fs_used"] = self._format_size(fs_used)
                    attributes["fs_free"] = self._format_size(fs_free)

                    # Add raw values in KB
                    attributes["fs_size_kb"] = int(fs_size)
                    attributes["fs_used_kb"] = int(fs_used)
                    attributes["fs_free_kb"] = int(fs_free)
                    return
                # If we can't parse the values
                return
            except (ValueError, TypeError):
                pass

        # If standard fields aren't available, try size/free
        size = disk.get("size")
        free = disk.get("free")

        if size and free:
            try:
                size_float = float(size)
                free_float = float(free)
                used_float = size_float - free_float

                if size_float > 0:
                    # Add usage percentage
                    usage_percent = round((used_float / size_float) * 100, 1)
                    attributes["usage_percent"] = usage_percent

                    # Add formatted values
                    attributes["fs_size"] = self._format_size(size_float)
                    attributes["fs_used"] = self._format_size(used_float)
                    attributes["fs_free"] = self._format_size(free_float)

                    # Add raw values in KB
                    attributes["fs_size_kb"] = int(size_float)
                    attributes["fs_used_kb"] = int(used_float)
                    attributes["fs_free_kb"] = int(free_float)
                    return
                # If we can't parse the values
                return
            except (ValueError, TypeError):
                pass

        # If we get here, we couldn't find any usage data
        attributes["fs_usage_available"] = False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            array_data = self.coordinator.data.get("array_status", {}).get("array", {})

            # Look in different disk arrays based on type
            if self._disk_type == "Parity":
                disks = array_data.get("parities", [])
            elif self._disk_type == "Cache":
                disks = array_data.get("caches", [])
            else:
                disks = array_data.get("disks", [])

            for disk in disks:
                if disk.get("id") == self._disk_id:
                    # Include standby state in attributes
                    disk_state = disk.get("state", "").upper()
                    return self._get_disk_attributes(disk, disk_state)

            # If we get here, the disk wasn't found
            # No disk found in the loop
            return {
                ATTR_DISK_NAME: self._disk_name,
                ATTR_DISK_TYPE: self._disk_type,
            }
        except (KeyError, AttributeError, TypeError):
            return {
                ATTR_DISK_NAME: self._disk_name,
                ATTR_DISK_TYPE: self._disk_type,
            }


class UnraidDockerContainerRunningBinarySensor(UnraidDockerEntity, BinarySensorEntity):
    """Binary sensor for Unraid Docker container running status."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = ICON_DOCKER
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        container_id: str,
        container_name: str,
    ) -> None:
        """Initialize the binary sensor."""
        # Clean container name to handle any potential slashes
        container_name = container_name.replace("/", "")
        # Use "docker" as entity key instead of "running" to avoid "running" in the entity ID
        super().__init__(coordinator, server_name, "docker", container_id)
        self._container_name = container_name
        # Use container name without redundant "Running"
        self._attr_name = f"Container {container_name}"

    @property
    def is_on(self) -> bool:
        """Return true if the container is running."""
        try:
            docker_data = self.coordinator.data.get("docker_containers", {}).get(
                "dockerContainers", []
            )
            for container in docker_data:
                if container.get("id") == self._container_id:
                    return container.get("state") == CONTAINER_STATE_RUNNING

            # If we get here, the container wasn't found
            # No container found in the loop
            return False
        except (KeyError, AttributeError, TypeError):
            return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            docker_data = self.coordinator.data.get("docker_containers", {}).get(
                "dockerContainers", []
            )
            for container in docker_data:
                if container.get("id") == self._container_id:
                    return {
                        ATTR_CONTAINER_IMAGE: container.get("image"),
                        ATTR_CONTAINER_STATUS: container.get("status"),
                    }

            # If we get here, the container wasn't found
            # No container found in the loop
            return {}
        except (KeyError, AttributeError, TypeError):
            return {}


class UnraidVMRunningBinarySensor(UnraidVMEntity, BinarySensorEntity):
    """Binary sensor for Unraid VM running status."""

    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = ICON_VM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        vm_id: str,
        vm_name: str,
    ) -> None:
        """Initialize the binary sensor."""
        # Use "vm" as entity key instead of "running" to avoid "running" in the entity ID
        super().__init__(coordinator, server_name, "vm", vm_id)
        self._vm_name = vm_name
        # Use VM name without redundant "Running"
        self._attr_name = f"VM {vm_name}"

    @property
    def is_on(self) -> bool:
        """Return true if the VM is running."""
        try:
            vm_data = self.coordinator.data.get("vms", {}).get("domain", [])
            for vm in vm_data:
                if vm.get("uuid") == self._vm_id:
                    return vm.get("state") == VM_STATE_RUNNING

            # If we get here, the VM wasn't found
            # No VM found in the loop
            return False
        except (KeyError, AttributeError, TypeError):
            return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            vm_data = self.coordinator.data.get("vms", {}).get("domain", [])
            for vm in vm_data:
                if vm.get("uuid") == self._vm_id:
                    return {
                        ATTR_VM_STATE: vm.get("state"),
                    }

            # If we get here, the VM wasn't found
            # No VM found in the loop
            return {}
        except (KeyError, AttributeError, TypeError):
            return {}
