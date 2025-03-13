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
    _LOGGER.debug("Setting up disk binary sensors with array data: %s", array_data)

    # Add data disks
    data_disks = array_data.get("disks", [])
    _LOGGER.debug("Found %s data disks", len(data_disks))
    for disk in data_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            _LOGGER.debug("Creating health sensor for data disk %s (%s)", disk_name, disk_id)
            entities.append(
                UnraidDiskHealthBinarySensor(coordinator, name, disk_id, disk_name, "Data")
            )

    # Add parity disks
    parity_disks = array_data.get("parities", [])
    _LOGGER.debug("Found %s parity disks", len(parity_disks))
    for disk in parity_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            _LOGGER.debug("Creating health sensor for parity disk %s (%s)", disk_name, disk_id)
            entities.append(
                UnraidDiskHealthBinarySensor(coordinator, name, disk_id, disk_name, "Parity")
            )

    # Add cache disks
    cache_disks = array_data.get("caches", [])
    _LOGGER.debug("Found %s cache disks", len(cache_disks))
    for disk in cache_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            _LOGGER.debug("Creating health sensor for cache disk %s (%s)", disk_name, disk_id)
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

    _LOGGER.debug("Adding %s binary sensor entities to Home Assistant", len(entities))
    async_add_entities(entities)


class UnraidOnlineBinarySensor(UnraidSystemEntity, BinarySensorEntity):
    """Binary sensor for Unraid online status."""

    _attr_name = "Online"
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

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

    _attr_name = "Array"
    _attr_icon = ICON_ARRAY
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ):
        """Initialize the binary sensor."""
        super().__init__(coordinator, server_name, "array")

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
        
        # Use "health" as entity_key to make the entity ID follow the pattern binary_sensor.servername_disk_health
        super().__init__(coordinator, server_name, "health", disk_id, disk_type)
        
        self._disk_name = disk_name
        # Set the display name to just the disk name and Health
        self._attr_name = f"{disk_name} Health"
        
        # Override the unique_id to ensure it follows the desired pattern
        self._attr_unique_id = f"{coordinator.api.host}_disk_{disk_id}_health"
        
        # Track if the disk is in standby mode
        self._is_standby = False
        self._last_known_problem = None
        
        _LOGGER.debug(
            "Created disk health binary sensor: entity_id=%s, unique_id=%s, name=%s",
            f"binary_sensor.{server_name.lower()}_{disk_name.lower()}_health",
            self._attr_unique_id,
            self._attr_name
        )

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
                    return self._last_known_problem if self._is_standby else has_problem
            
            # Default to problem if disk not found
            return True if self._last_known_problem is None else self._last_known_problem
        except (KeyError, AttributeError, TypeError):
            return True if self._last_known_problem is None else self._last_known_problem
    
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
                    # Include standby state in attributes
                    disk_state = disk.get("state", "").upper()
                    
                    attributes = {
                        ATTR_DISK_NAME: disk.get("name"),
                        ATTR_DISK_TYPE: self._disk_type,
                        "status": disk.get("status"),
                        "state": disk_state,
                    }
                    
                    # Add serial number if available
                    if disk.get("serial"):
                        attributes[ATTR_DISK_SERIAL] = disk.get("serial")
                    
                    # Add size if available and not in standby
                    if disk.get("size") and disk_state != "STANDBY":
                        attributes[ATTR_DISK_SIZE] = disk.get("size")
                    
                    # Add temperature if available and not in standby
                    if disk.get("temp") is not None and disk_state != "STANDBY":
                        attributes[ATTR_DISK_TEMP] = disk.get("temp")
                    
                    return attributes
            
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
    ):
        """Initialize the binary sensor."""
        # Clean container name to handle any potential slashes
        container_name = container_name.replace('/', '')
        # Use "docker" as entity key instead of "running" to avoid "running" in the entity ID
        super().__init__(coordinator, server_name, "docker", container_id)
        self._container_name = container_name
        # Remove "Running" from the display name
        self._attr_name = f"{container_name}"

    @property
    def is_on(self) -> bool:
        """Return true if the container is running."""
        try:
            docker_data = self.coordinator.data.get("docker_containers", {}).get("dockerContainers", [])
            for container in docker_data:
                if container.get("id") == self._container_id:
                    return container.get("state") == CONTAINER_STATE_RUNNING
            return False
        except (KeyError, AttributeError, TypeError):
            return False

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            docker_data = self.coordinator.data.get("docker_containers", {}).get("dockerContainers", [])
            for container in docker_data:
                if container.get("id") == self._container_id:
                    return {
                        ATTR_CONTAINER_IMAGE: container.get("image"),
                        ATTR_CONTAINER_STATUS: container.get("status"),
                    }
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
    ):
        """Initialize the binary sensor."""
        # Use "vm" as entity key instead of "running" to avoid "running" in the entity ID
        super().__init__(coordinator, server_name, "vm", vm_id)
        self._vm_name = vm_name
        # Remove "Running" from the display name
        self._attr_name = f"{vm_name}"

    @property
    def is_on(self) -> bool:
        """Return true if the VM is running."""
        try:
            vm_data = self.coordinator.data.get("vms", {}).get("domain", [])
            for vm in vm_data:
                if vm.get("uuid") == self._vm_id:
                    return vm.get("state") == VM_STATE_RUNNING
            return False
        except (KeyError, AttributeError, TypeError):
            return False

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            vm_data = self.coordinator.data.get("vms", {}).get("domain", [])
            for vm in vm_data:
                if vm.get("uuid") == self._vm_id:
                    return {
                        ATTR_VM_STATE: vm.get("state"),
                    }
            return {}
        except (KeyError, AttributeError, TypeError):
            return {}