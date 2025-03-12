"""Binary sensor platform for Unraid integration."""
import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    EntityCategory,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ARRAY_STATE_STARTED,
    ATTR_CONTAINER_IMAGE,
    ATTR_CONTAINER_STATUS,
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

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Unraid binary sensors."""
    coordinator = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["coordinator"]
    name = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["name"]

    entities = []

    # Add system binary sensors
    entities.append(UnraidOnlineBinarySensor(coordinator, name))

    # Add array binary sensors
    entities.append(UnraidArrayRunningBinarySensor(coordinator, name))

    # Add disk binary sensors
    array_data = coordinator.data.get("array_status", {}).get("array", {})

    # Add data disks
    data_disks = array_data.get("disks", [])
    for disk in data_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            entities.append(
                UnraidDiskHealthBinarySensor(coordinator, name, disk_id, disk_name, "Data")
            )

    # Add parity disks
    parity_disks = array_data.get("parities", [])
    for disk in parity_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            entities.append(
                UnraidDiskHealthBinarySensor(coordinator, name, disk_id, disk_name, "Parity")
            )

    # Add cache disks
    cache_disks = array_data.get("caches", [])
    for disk in cache_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            entities.append(
                UnraidDiskHealthBinarySensor(coordinator, name, disk_id, disk_name, "Cache")
            )

    # Add docker container binary sensors
    docker_data = coordinator.data.get("docker_containers", {}).get("dockerContainers", [])
    for container in docker_data:
        if container.get("id") and container.get("names"):
            container_id = container.get("id")
            container_name = container.get("names", [])[0] if container.get("names") else container_id
            entities.append(
                UnraidDockerContainerRunningBinarySensor(coordinator, name, container_id, container_name)
            )

    # Add VM binary sensors
    vm_data = coordinator.data.get("vms", {}).get("domain", [])
    for vm in vm_data:
        if vm.get("uuid") and vm.get("name"):
            vm_id = vm.get("uuid")
            vm_name = vm.get("name")
            entities.append(
                UnraidVMRunningBinarySensor(coordinator, name, vm_id, vm_name)
            )

    async_add_entities(entities)


class UnraidOnlineBinarySensor(UnraidSystemEntity, BinarySensorEntity):
    """Binary sensor for Unraid online status."""

    _attr_name = "Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ):
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

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ):
        """Initialize the binary sensor."""
        super().__init__(coordinator, server_name, "running")

    @property
    def is_on(self) -> bool:
        """Return true if the array is running."""
        try:
            state = self.coordinator.data.get("array_status", {}).get("array", {}).get("state")
            return state == ARRAY_STATE_STARTED
        except (KeyError, AttributeError, TypeError):
            return False


class UnraidDiskHealthBinarySensor(UnraidDiskEntity, BinarySensorEntity):
    """Binary sensor for Unraid disk health."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = ICON_DISK

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        disk_id: str,
        disk_name: str,
        disk_type: str,
    ):
        """Initialize the binary sensor."""
        # Clean disk name to handle any potential slashes
        disk_name = disk_name.replace('/', '_')
        super().__init__(coordinator, server_name, "health", disk_id, disk_type)
        self._disk_name = disk_name
        self._attr_name = f"{disk_name} Health"

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
                    # Any disk, active or standby, should report a problem if status is not DISK_OK
                    # This doesn't wake the disk but reports problems based on the state Unraid already knows
                    return disk.get("status") != "DISK_OK"
            
            # Default to problem if disk not found
            return True
        except (KeyError, AttributeError, TypeError):
            return True
    
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
            
            return False
        except (KeyError, AttributeError, TypeError):
            return False

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
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
                    # Check disk state first
                    disk_state = disk.get("state", "").upper()
                    
                    # Get disk size in bytes and format it
                    size_bytes = int(disk.get("size", 0)) * 1024 if disk.get("size") else 0
                    size_formatted = self._format_size(size_bytes)
                    
                    # Build base attributes
                    attributes = {
                        ATTR_DISK_NAME: disk.get("name"),
                        ATTR_DISK_TYPE: self._disk_type,
                        ATTR_DISK_SIZE: size_formatted,
                        "size_bytes": size_bytes,
                        "status": disk.get("status"),
                        "rotational": disk.get("rotational", True),
                    }
                    
                    # For inactive/standby disks, report basic info but don't query data
                    # that would wake them up
                    if disk_state != "ACTIVE" and disk_state != "":
                        attributes["state"] = disk_state
                        return attributes
                    
                    # For active disks, add temp and other detailed data
                    if "temp" in disk:
                        attributes[ATTR_DISK_TEMP] = disk.get("temp")
                    
                    if "serial" in disk:
                        attributes[ATTR_DISK_SERIAL] = disk.get("serial")
                        
                    # Add file system information if it exists
                    if "fsSize" in disk and "fsUsed" in disk and "fsFree" in disk:
                        fs_size = int(disk.get("fsSize", 0)) * 1024 if disk.get("fsSize") else 0
                        fs_free = int(disk.get("fsFree", 0)) * 1024 if disk.get("fsFree") else 0
                        fs_used = int(disk.get("fsUsed", 0)) * 1024 if disk.get("fsUsed") else 0
                        
                        attributes.update({
                            "fs_size": self._format_size(fs_size),
                            "fs_free": self._format_size(fs_free),
                            "fs_used": self._format_size(fs_used),
                            "fs_size_bytes": fs_size,
                            "fs_free_bytes": fs_free,
                            "fs_used_bytes": fs_used,
                        })
                        
                        # Add usage percentage
                        if fs_size > 0:
                            attributes["usage_percent"] = round((fs_used / fs_size) * 100, 1)
                                
                    return attributes
            
            return {}
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return {}
            
    def _format_size(self, size_bytes: int) -> str:
        """Format size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.2f} KiB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024 ** 2):.2f} MiB"
        elif size_bytes < 1024 ** 4:
            return f"{size_bytes / (1024 ** 3):.2f} GiB"
        else:
            return f"{size_bytes / (1024 ** 4):.2f} TiB"