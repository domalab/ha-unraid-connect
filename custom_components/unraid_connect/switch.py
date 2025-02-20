"""
Switch platform for controlling Unraid Docker containers.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, Callable, Final

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LOGGER
from .coordinator import UnraidDataUpdateCoordinator
from .entity import UnraidDockerEntity

@dataclass
class UnraidSwitchEntityDescription(SwitchEntityDescription):
    """Class describing Unraid switch entities."""
    is_on_fn: Callable[[dict[str, Any]], bool] = lambda _: False
    available_fn: Callable[[dict[str, Any]], bool] = lambda _: True
    entity_category: EntityCategory | None = None
    entity_registry_enabled_default: bool = True

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid switch based on a config entry."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    LOGGER.debug("Setting up Unraid Docker container switches")
    entities = []
    
    # Add switch for each Docker container
    if coordinator.data and "docker" in coordinator.data:
        for container in coordinator.data["docker"]:
            if "names" in container and container["names"] and "id" in container:
                container_name = container["names"][0] if isinstance(container["names"], list) else container["names"]
                LOGGER.debug("Adding Docker container switch: %s", container_name)
                
                entities.append(
                    UnraidDockerContainerSwitch(
                        coordinator=coordinator,
                        config_entry=entry,
                        container_id=container["id"],
                        container_name=container_name,
                    )
                )
    
    async_add_entities(entities)
    LOGGER.info("Added %d Unraid Docker container switches", len(entities))

class UnraidDockerContainerSwitch(UnraidDockerEntity, SwitchEntity):
    """Switch for controlling an Unraid Docker container."""

    def __init__(
        self,
        coordinator,
        config_entry,
        container_id,
        container_name,
    ) -> None:
        """Initialize the Docker container switch."""
        super().__init__(coordinator, config_entry, container_id, container_name)
        self._attr_entity_registry_enabled_default = True
        self._attr_icon = "mdi:docker"
        LOGGER.debug("Initialized Docker container switch: %s", self._attr_unique_id)
        
    @property
    def is_on(self) -> bool:
        """Return true if the container is running."""
        container = self._get_container_data()
        if container is None:
            return False
            
        return container.get("state") == "running"
            
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start the Docker container."""
        LOGGER.info("Starting Docker container: %s", self._container_name)
        try:
            await self._control_container("start")
            self._attr_is_on = True
            self.async_write_ha_state()
        except Exception as err:
            LOGGER.error("Failed to start Docker container %s: %s", 
                       self._container_name, err, exc_info=True)
            
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop the Docker container."""
        LOGGER.info("Stopping Docker container: %s", self._container_name)
        try:
            await self._control_container("stop")
            self._attr_is_on = False
            self.async_write_ha_state()
        except Exception as err:
            LOGGER.error("Failed to stop Docker container %s: %s", 
                       self._container_name, err, exc_info=True)
    
    async def _control_container(self, action: str) -> None:
        """Control the Docker container using the coordinator's service method."""
        try:
            # Use the coordinator's service method
            await self.coordinator.async_service_docker_container(self._container_id, action)
            
        except Exception as err:
            LOGGER.error("Error controlling container: %s", err, exc_info=True)
            raise
            
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs = {}
        
        container = self._get_container_data()
        if container is None:
            return attrs
            
        # Basic container info
        attrs["image"] = container.get("image")
        attrs["status"] = container.get("status")
        attrs["auto_start"] = container.get("autoStart", False)
        attrs["created"] = container.get("created")
        
        # Add command if available
        if "command" in container:
            command = container["command"]
            if isinstance(command, str) and len(command) < 255:
                # Truncate extremely long commands
                attrs["command"] = command
                
        # Add performance metrics if available
        if "cpuUsage" in container:
            attrs["cpu_usage"] = container["cpuUsage"]
        if "memUsage" in container:
            attrs["memory_usage"] = container["memUsage"]
        if "memPercent" in container:
            attrs["memory_percent"] = container["memPercent"]
        
        # Add network IO if available
        if "netIO" in container and container["netIO"]:
            if "rx" in container["netIO"]:
                attrs["network_rx"] = container["netIO"]["rx"]
            if "tx" in container["netIO"]:
                attrs["network_tx"] = container["netIO"]["tx"]
        
        # Add block IO if available
        if "blockIO" in container and container["blockIO"]:
            if "read" in container["blockIO"]:
                attrs["block_read"] = container["blockIO"]["read"]
            if "write" in container["blockIO"]:
                attrs["block_write"] = container["blockIO"]["write"]
        
        # Add ports if available (limit to reasonable size)
        if "ports" in container and container["ports"]:
            if isinstance(container["ports"], list) and len(container["ports"]) < 20:
                attrs["ports"] = container["ports"]
            elif isinstance(container["ports"], str) and len(container["ports"]) < 255:
                attrs["ports"] = container["ports"]
            
        return attrs