"""Switch platform for Unraid integration."""
import logging
from typing import Any, Dict, List, Optional, Callable

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import UnraidApiClient, UnraidApiError
from .const import (
    ARRAY_STATE_STARTED,
    ATTR_CONTAINER_IMAGE,
    ATTR_CONTAINER_STATUS,
    ATTR_VM_STATE,
    CONTAINER_STATE_RUNNING,
    DOMAIN as INTEGRATION_DOMAIN,
    ICON_ARRAY,
    ICON_DOCKER,
    ICON_VM,
    VM_STATE_RUNNING,
)
from .coordinator import UnraidDataUpdateCoordinator
from .entity import (
    UnraidArrayEntity,
    UnraidDockerEntity,
    UnraidVMEntity,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Unraid switches."""
    coordinator = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["coordinator"]
    name = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["name"]
    client = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["client"]

    entities = []

    # Add docker container switches
    docker_data = coordinator.data.get("docker_containers", {}).get("dockerContainers", [])
    for container in docker_data:
        if container.get("id") and container.get("names"):
            container_id = container.get("id")
            container_name = container.get("names", [])[0] if container.get("names") else container_id
            entities.append(
                UnraidDockerContainerSwitch(coordinator, client, name, container_id, container_name)
            )

    # Add VM switches
    vm_data = coordinator.data.get("vms", {}).get("vms", {}).get("domain", [])
    for vm in vm_data:
        if vm.get("uuid") and vm.get("name"):
            vm_id = vm.get("uuid")
            vm_name = vm.get("name")
            entities.append(
                UnraidVMSwitch(coordinator, client, name, vm_id, vm_name)
            )

    async_add_entities(entities)

class UnraidDockerContainerSwitch(UnraidDockerEntity, SwitchEntity):
    """Switch for controlling Unraid Docker container."""

    _attr_icon = ICON_DOCKER

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        client: UnraidApiClient,
        server_name: str,
        container_id: str,
        container_name: str,
    ):
        """Initialize the switch."""
        super().__init__(coordinator, server_name, "switch", container_id)
        self.client = client
        self._container_name = container_name
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

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the container."""
        try:
            await self.client.start_docker_container(self._container_id)
            await self.coordinator.async_request_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to start container %s: %s", self._container_name, err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the container."""
        try:
            await self.client.stop_docker_container(self._container_id)
            await self.coordinator.async_request_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to stop container %s: %s", self._container_name, err)

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


class UnraidVMSwitch(UnraidVMEntity, SwitchEntity):
    """Switch for controlling Unraid VM."""

    _attr_icon = ICON_VM

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        client: UnraidApiClient,
        server_name: str,
        vm_id: str,
        vm_name: str,
    ):
        """Initialize the switch."""
        super().__init__(coordinator, server_name, "switch", vm_id)
        self.client = client
        self._vm_name = vm_name
        self._attr_name = f"VM {vm_name}"

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

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the VM."""
        try:
            await self.client.start_vm(self._vm_id)
            await self.coordinator.async_request_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to start VM %s: %s", self._vm_name, err)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the VM."""
        try:
            await self.client.stop_vm(self._vm_id)
            await self.coordinator.async_request_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to stop VM %s: %s", self._vm_name, err)

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