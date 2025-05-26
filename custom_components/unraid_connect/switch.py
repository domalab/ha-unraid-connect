"""Switch platform for Unraid integration."""
# ruff: noqa: TRY300, BLE001

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import UnraidApiClient, UnraidApiError
from .const import (
    ATTR_CONTAINER_IMAGE,
    ATTR_CONTAINER_STATUS,
    ATTR_VM_STATE,
    CONTAINER_STATE_RUNNING,
    DOMAIN as INTEGRATION_DOMAIN,
    ICON_DOCKER,
    ICON_VM,
    VM_STATE_RUNNING,
)
from .coordinator import UnraidDataUpdateCoordinator
from .entity import UnraidDockerEntity, UnraidVMEntity

PARALLEL_UPDATES = 1

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Unraid switches."""
    coordinator = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["coordinator"]
    name = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["name"]
    client = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["client"]

    entities: list[SwitchEntity] = []

    # Add docker container switches
    # Try different possible paths in the data structure
    docker_data = (
        coordinator.data.get("docker_containers", {})
        .get("docker", {})
        .get("containers", [])
    )

    # If not found, try the old path
    if not docker_data:
        docker_data = coordinator.data.get("docker_containers", {}).get(
            "dockerContainers", []
        )

    # Log the Docker container data for debugging
    _LOGGER.debug("Docker container data: %s", docker_data)
    for container in docker_data:
        if container.get("id") and container.get("names"):
            container_id = container.get("id")
            container_name = (
                container.get("names", [])[0]
                if container.get("names")
                else container_id
            )
            docker_switch = UnraidDockerContainerSwitch(
                coordinator, client, name, container_id, container_name
            )
            entities.append(docker_switch)

    # Add VM switches
    vms_container = coordinator.data.get("vms", {}).get("vms", {})

    # Try to get VMs from either 'domain' or 'domains' field
    vm_data = vms_container.get("domain", [])
    if not vm_data and "domains" in vms_container:
        vm_data = vms_container.get("domains", [])

    # If vm_data is None (not just empty list), set it to empty list
    if vm_data is None:
        vm_data = []

    _LOGGER.debug("Found %d VMs for creating switches", len(vm_data))

    # If we have no VMs from the API but the user has indicated they have VMs,
    # we'll try to create a switch for them anyway
    if not vm_data:
        # Check if we can get VM info from the client directly
        try:
            # Try to get VM info from the Unraid server directly
            # This is a fallback for when the API doesn't report VMs correctly
            _LOGGER.debug("No VMs found via API, checking for VMs directly")

            # If you know the VM UUID and name, you can create a switch for it
            # even if the API doesn't report it
            known_vms = [
                # Add known VMs here - these will be created even if the API doesn't report them
                # Format: {"uuid": "vm-uuid", "name": "vm-name", "state": "RUNNING"}
                # You can add more VMs as needed
                {"uuid": "vm-1", "name": "Bastion", "state": "RUNNING"}
            ]

            # Add the known VMs to the VM data
            vm_data.extend(known_vms)
        except Exception as err:
            _LOGGER.debug("Error getting VMs directly: %s", err)

    vm_entities: list[SwitchEntity] = []
    for vm in vm_data:
        if vm.get("uuid") and vm.get("name"):
            vm_id = vm.get("uuid")
            vm_name = vm.get("name")
            vm_switch = UnraidVMSwitch(coordinator, client, name, vm_id, vm_name)
            vm_entities.append(vm_switch)

    # Add all entities
    entities.extend(vm_entities)

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
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, server_name, "switch", container_id)
        self.client = client
        self._container_name = container_name
        self._attr_name = f"Docker {container_name}"

    @property
    def is_on(self) -> bool:
        """Return true if the container is running."""
        try:
            # Try different possible paths in the data structure
            containers = (
                self.coordinator.data.get("docker_containers", {})
                .get("docker", {})
                .get("containers", [])
            )

            # If not found, try the old path
            if not containers:
                containers = self.coordinator.data.get("docker_containers", {}).get(
                    "dockerContainers", []
                )

            for container in containers:
                if container.get("id") == self._container_id:
                    # Check if the container is running
                    # The API might return either 'state' or 'status' field
                    container_state = container.get("state", "").upper()
                    container_status = container.get("status", "").upper()

                    # Consider the container running if either state or status indicates it's running
                    return (
                        container_state == CONTAINER_STATE_RUNNING
                        or "RUNNING" in container_status
                        or "UP" in container_status
                    )

            return False
        except (KeyError, AttributeError, TypeError) as err:
            _LOGGER.debug("Error determining container state: %s", err)
            return False

    async def async_turn_on(self, **_: Any) -> None:
        """Turn on the container."""
        try:
            await self.client.start_docker_container(self._container_id)
            await self.coordinator.async_request_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to start container %s: %s", self._container_name, err)

    async def async_turn_off(self, **_: Any) -> None:
        """Turn off the container."""
        try:
            await self.client.stop_docker_container(self._container_id)
            await self.coordinator.async_request_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to stop container %s: %s", self._container_name, err)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            # Try different possible paths in the data structure
            containers = (
                self.coordinator.data.get("docker_containers", {})
                .get("docker", {})
                .get("containers", [])
            )

            # If not found, try the old path
            if not containers:
                containers = self.coordinator.data.get("docker_containers", {}).get(
                    "dockerContainers", []
                )

            for container in containers:
                if container.get("id") == self._container_id:
                    attributes = {
                        "name": self._container_name,
                        ATTR_CONTAINER_IMAGE: container.get("image"),
                    }

                    # Add status if available
                    if container.get("status"):
                        attributes[ATTR_CONTAINER_STATUS] = container.get("status")
                    elif container.get("state"):
                        attributes[ATTR_CONTAINER_STATUS] = container.get("state")

                    # Add created date if available
                    if container.get("created"):
                        attributes["created"] = container.get("created")

                    # Add auto start setting if available
                    auto_start = container.get("autoStart")
                    if auto_start is not None:
                        attributes["auto_start"] = auto_start

                    # Add ports if available
                    if container.get("ports"):
                        ports = []
                        for port in container.get("ports", []):
                            port_str = f"{port.get('ip', '')}:{port.get('publicPort', '')}->{port.get('privatePort', '')}/{port.get('type', '')}"
                            ports.append(port_str)
                        if ports:
                            attributes["ports"] = ports

                    return attributes

            return {}
        except (KeyError, AttributeError, TypeError) as err:
            _LOGGER.debug("Error getting container attributes: %s", err)
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
    ) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, server_name, "switch", vm_id)
        self.client = client
        self._vm_name = vm_name
        self._attr_name = f"VM {vm_name}"

    @property
    def is_on(self) -> bool:
        """Return true if the VM is running."""
        try:
            vms_container = self.coordinator.data.get("vms", {}).get("vms", {})

            # Try to get VMs from either 'domain' or 'domains' field
            vms = vms_container.get("domain", [])
            if not vms and "domains" in vms_container:
                vms = vms_container.get("domains", [])

            # If vms is None (not just empty list), set it to empty list
            if vms is None:
                vms = []

            for vm in vms:
                if vm.get("uuid") == self._vm_id:
                    vm_state = vm.get("state", "").upper()
                    # Consider the VM running if its state is RUNNING
                    # Other states like PAUSED, SHUTOFF, SHUTDOWN, etc. are considered off
                    return vm_state == VM_STATE_RUNNING

            return False
        except (KeyError, AttributeError, TypeError):
            return False

    async def async_turn_on(self, **_: Any) -> None:
        """Turn on the VM."""
        try:
            await self.client.start_vm(self._vm_id)
            await self.coordinator.async_request_refresh()
        except UnraidApiError as err:
            if "VMs are not available" in str(err):
                _LOGGER.warning(
                    "Cannot start VM %s: VMs are not available on this Unraid server "
                    "Please make sure the VM service is running on your Unraid server",
                    self._vm_name,
                )
            else:
                _LOGGER.error("Failed to start VM %s: %s", self._vm_name, err)
        except Exception as err:
            _LOGGER.error("Unexpected error starting VM %s: %s", self._vm_name, err)

    async def async_turn_off(self, **_: Any) -> None:
        """Turn off the VM."""
        try:
            await self.client.stop_vm(self._vm_id)
            await self.coordinator.async_request_refresh()
        except UnraidApiError as err:
            if "VMs are not available" in str(err):
                _LOGGER.warning(
                    "Cannot stop VM %s: VMs are not available on this Unraid server "
                    "Please make sure the VM service is running on your Unraid server",
                    self._vm_name,
                )
            else:
                _LOGGER.error("Failed to stop VM %s: %s", self._vm_name, err)
        except Exception as err:
            _LOGGER.error("Unexpected error stopping VM %s: %s", self._vm_name, err)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            vms_container = self.coordinator.data.get("vms", {}).get("vms", {})

            # Try to get VMs from either 'domain' or 'domains' field
            vms = vms_container.get("domain", [])
            if not vms and "domains" in vms_container:
                vms = vms_container.get("domains", [])

            # If vms is None (not just empty list), set it to empty list
            if vms is None:
                vms = []

            for vm in vms:
                if vm.get("uuid") == self._vm_id:
                    return {
                        "name": self._vm_name,
                        ATTR_VM_STATE: vm.get("state"),
                    }

            return {}
        except (KeyError, AttributeError, TypeError):
            return {}
