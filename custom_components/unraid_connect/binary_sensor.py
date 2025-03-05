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
    vm_data = coordinator.data.get("vms", {}).get("vms", {}).get("domain", [])
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
                    return {
                        "name": disk.get("name"),
                        "type": self._disk_type,
                        "status": disk.get("status"),
                        "device": disk.get("device"),
                        "size": disk.get("size"),
                        "numErrors": disk.get("numErrors"),
                    }
            
            return {}
        except (KeyError, AttributeError, TypeError):
            return {}


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
        super().__init__(coordinator, server_name, "running", container_id)
        self._container_name = container_name
        self._attr_name = f"Docker {container_name} Running"

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
        super().__init__(coordinator, server_name, "running", vm_id)
        self._vm_name = vm_name
        self._attr_name = f"VM {vm_name} Running"

    @property
    def is_on(self) -> bool:
        """Return true if the VM is running."""
        try:
            vms = self.coordinator.data.get("vms", {}).get("vms", {}).get("domain", [])
            
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
            vms = self.coordinator.data.get("vms", {}).get("vms", {}).get("domain", [])
            
            for vm in vms:
                if vm.get("uuid") == self._vm_id:
                    return {
                        "name": self._vm_name,
                        ATTR_VM_STATE: vm.get("state"),
                    }
            
            return {}
        except (KeyError, AttributeError, TypeError):
            return {}