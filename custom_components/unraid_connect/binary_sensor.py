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
                    # Return True (problem) if status is not "DISK_OK"
                    return disk.get("status") != "DISK_OK"
            
            # Default to problem if disk not found
            return True
        except (KeyError, AttributeError, TypeError):
            return True

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
                    # Get disk size in bytes and format it
                    size_bytes = int(disk.get("size", 0)) * 1024 if disk.get("size") else 0
                    size_formatted = self._format_size(size_bytes)
                    
                    # Build base attributes
                    attributes = {
                        "name": disk.get("name"),
                        "type": self._disk_type,
                        "status": disk.get("status"),
                        "device": disk.get("device"),
                        "size": size_formatted,
                        "size_bytes": size_bytes,
                        "numErrors": disk.get("numErrors"),
                        "rotational": disk.get("rotational", True),
                    }
                    
                    # Add temperature if available
                    temp = disk.get("temp")
                    if temp is not None:
                        attributes["temperature"] = temp
                        
                    # Add filesystem info if available for data/cache disks
                    if self._disk_type in ["Data", "Cache"]:
                        if "fsSize" in disk and "fsFree" in disk and "fsUsed" in disk:
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


class UnraidDockerContainerRunningBinarySensor(UnraidDockerEntity, BinarySensorEntity):
    """Binary sensor for Unraid Docker container running status."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = ICON_DOCKER

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        container_id: str,
        container_name: str,
    ):
        """Initialize the binary sensor."""
        # Clean container name - remove leading slash if present
        container_name = container_name.lstrip('/')
        self._container_name = container_name
        super().__init__(coordinator, server_name, "running", container_id)
        self._attr_name = f"Docker {container_name}"

    @property
    def is_on(self) -> bool:
        """Return true if the container is running."""
        try:
            containers = self.coordinator.data.get("docker_containers", {}).get("dockerContainers", [])
            
            for container in containers:
                if container.get("id") == self._container_id:
                    return container.get("state") == CONTAINER_STATE_RUNNING
            
            return False
        except (KeyError, AttributeError, TypeError):
            return False

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            containers = self.coordinator.data.get("docker_containers", {}).get("dockerContainers", [])
            
            for container in containers:
                if container.get("id") == self._container_id:
                    return {
                        "name": self._container_name,
                        ATTR_CONTAINER_IMAGE: container.get("image"),
                        ATTR_CONTAINER_STATUS: container.get("status"),
                        "created": container.get("created"),
                        "auto_start": container.get("autoStart"),
                    }
            
            return {}
        except (KeyError, AttributeError, TypeError):
            return {}


class UnraidVMRunningBinarySensor(UnraidVMEntity, BinarySensorEntity):
    """Binary sensor for Unraid VM running status."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC 
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = ICON_VM

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        vm_id: str,
        vm_name: str,
    ):
        """Initialize the binary sensor."""
        # Clean VM name
        vm_name = vm_name.replace('/', '')
        self._vm_name = vm_name
        super().__init__(coordinator, server_name, "running", vm_id)
        self._attr_name = f"VM {vm_name}"

    @property
    def is_on(self) -> bool:
        """Return true if the VM is running."""
        try:
            vms = self.coordinator.data.get("vms", {}).get("domain", [])
            
            for vm in vms:
                if vm.get("uuid") == self._vm_id:
                    return vm.get("state") == VM_STATE_RUNNING
            
            return False
        except (KeyError, AttributeError, TypeError):
            return False

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            vms = self.coordinator.data.get("vms", {}).get("domain", [])
            
            for vm in vms:
                if vm.get("uuid") == self._vm_id:
                    return {
                        "name": self._vm_name,
                        ATTR_VM_STATE: vm.get("state"),
                    }
            
            return {}
        except (KeyError, AttributeError, TypeError):
            return {}