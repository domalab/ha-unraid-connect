"""
Binary sensor platform for the Unraid integration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Final

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, LOGGER
from .coordinator import UnraidDataUpdateCoordinator
from .entity import UnraidEntity, UnraidDockerEntity

@dataclass
class UnraidBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Class describing Unraid binary sensor entities."""
    is_on_fn: Callable[[dict[str, Any]], bool] = lambda _: False
    available_fn: Callable[[dict[str, Any]], bool] = lambda _: True
    entity_category: EntityCategory | None = None
    entity_registry_enabled_default: bool = True

# Define all binary sensors with appropriate categories and default states
ARRAY_BINARY_SENSORS: Final[tuple[UnraidBinarySensorEntityDescription, ...]] = (
    UnraidBinarySensorEntityDescription(
        key="array_protection",
        translation_key="array_protection",
        name="Array Protection",
        device_class=BinarySensorDeviceClass.SAFETY,
        is_on_fn=lambda data: data["array"].get("protected", False),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    UnraidBinarySensorEntityDescription(
        key="array_started",
        translation_key="array_started",
        name="Array Started",
        device_class=BinarySensorDeviceClass.RUNNING,
        is_on_fn=lambda data: data["array"].get("started", False) or 
                              data["array"].get("state", "") == "started",
    ),
    UnraidBinarySensorEntityDescription(
        key="parity_check_running",
        translation_key="parity_check_running",
        name="Parity Check Running",
        device_class=BinarySensorDeviceClass.RUNNING,
        icon="mdi:harddisk-plus",
        is_on_fn=lambda data: data["array"].get("parityCheckActive", False),
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid binary sensor based on a config entry."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    LOGGER.debug("Setting up Unraid binary sensors")
    entities = []
    
    # Add array-related binary sensors
    for description in ARRAY_BINARY_SENSORS:
        LOGGER.debug("Adding array binary sensor: %s", description.key)
        entities.append(
            UnraidBinarySensor(
                coordinator=coordinator,
                config_entry=entry,
                description=description,
            )
        )
    
    # Add dynamic binary sensors for each Docker container
    if coordinator.data and "docker" in coordinator.data:
        for container in coordinator.data["docker"]:
            if "names" in container and container["names"] and "id" in container:
                container_name = container["names"][0] if isinstance(container["names"], list) else container["names"]
                LOGGER.debug("Adding Docker container binary sensor: %s", container_name)
                
                entities.append(
                    UnraidDockerContainerSensor(
                        coordinator=coordinator,
                        config_entry=entry,
                        container_id=container["id"],
                        container_name=container_name,
                    )
                )
    
    async_add_entities(entities)
    LOGGER.info("Added %d Unraid binary sensors", len(entities))

class UnraidBinarySensor(UnraidEntity, BinarySensorEntity):
    """Binary sensor for Unraid integration."""

    entity_description: UnraidBinarySensorEntityDescription

    def __init__(
        self,
        coordinator,
        config_entry,
        description: UnraidBinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, config_entry, description)
        
    @property
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
        try:
            return self.entity_description.is_on_fn(self.coordinator.data)
        except (KeyError, TypeError) as err:
            LOGGER.warning("Error getting state for %s: %s", 
                          self.entity_id, err)
            return None
            
    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not super().available:
            return False
            
        try:
            return self.entity_description.available_fn(self.coordinator.data)
        except (KeyError, TypeError):
            return False


class UnraidDockerContainerSensor(UnraidDockerEntity, BinarySensorEntity):
    """Binary sensor for an Unraid Docker container."""

    def __init__(
        self,
        coordinator,
        config_entry,
        container_id,
        container_name,
    ) -> None:
        """Initialize the Docker container binary sensor."""
        super().__init__(coordinator, config_entry, container_id, container_name)
        self._attr_device_class = BinarySensorDeviceClass.RUNNING
        self._attr_entity_registry_enabled_default = True
        LOGGER.debug("Initialized Docker container sensor: %s", self._attr_unique_id)
        
    @property
    def is_on(self) -> bool | None:
        """Return true if the container is running."""
        container = self._get_container_data()
        if container is None:
            return None
            
        return container.get("state") == "running"
            
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs = {}
        
        container = self._get_container_data()
        if container is None:
            return attrs
            
        attrs["image"] = container.get("image")
        attrs["status"] = container.get("status")
        attrs["auto_start"] = container.get("autoStart", False)
        
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
        
        # Add ports if available
        if "ports" in container and container["ports"]:
            attrs["ports"] = container["ports"]
            
        return attrs