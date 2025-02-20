"""
Base entity for Unraid integration.
"""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, LOGGER


class UnraidEntity(CoordinatorEntity, Entity):
    """Base entity for Unraid integration."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, config_entry, description=None):
        """Initialize the entity."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._attr_device_info = self._get_device_info()
        
        if description is not None:
            self.entity_description = description
            self._attr_unique_id = f"{config_entry.entry_id}_{description.key}"
            
        LOGGER.debug("Initialized %s entity: %s", self.__class__.__name__, 
                    getattr(self, "unique_id", "unknown"))

    def _get_device_info(self) -> DeviceInfo:
        """Return device information for this entity."""
        try:
            system_info = self.coordinator.data.get("system", {})
            
            # Get OS information
            os_info = system_info.get("os", {})
            platform = os_info.get("platform", "unknown")
            distro = os_info.get("distro", "Unraid")
            release = os_info.get("release", "unknown")
            
            # Get hardware information if available
            hw_info = ""
            if "cpu" in system_info:
                cpu = system_info["cpu"]
                if "manufacturer" in cpu and "brand" in cpu:
                    hw_info = f"{cpu.get('manufacturer')} {cpu.get('brand')}"
                    
            model = f"{distro} {release}"
            if hw_info:
                model = f"{model} on {hw_info}"
                
            return DeviceInfo(
                identifiers={(DOMAIN, self._config_entry.entry_id)},
                name=f"Unraid Server ({self._config_entry.data.get('host')})",
                manufacturer="Lime Technology, Inc.",
                model=model,
                sw_version=release,
                entry_type=DeviceEntryType.SERVICE,
                configuration_url=f"http://{self._config_entry.data.get('host')}/Dashboard",
            )
        except Exception as err:
            LOGGER.warning("Error generating device info: %s", err)
            return DeviceInfo(
                identifiers={(DOMAIN, self._config_entry.entry_id)},
                name=f"Unraid Server ({self._config_entry.data.get('host')})",
                manufacturer="Lime Technology, Inc.",
                model="Unraid Server",
                entry_type=DeviceEntryType.SERVICE,
            )
            
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.last_update_success


class UnraidDockerEntity(UnraidEntity):
    """Base entity for Unraid Docker container entities."""

    def __init__(self, coordinator, config_entry, container_id, container_name):
        """Initialize the Docker container entity."""
        super().__init__(coordinator, config_entry)
        self._container_id = container_id
        self._container_name = container_name
        self._attr_unique_id = f"{config_entry.entry_id}_docker_{container_id}"
        self._attr_name = container_name
        self._attr_device_info = self._get_docker_device_info()
        
    def _get_docker_device_info(self) -> DeviceInfo:
        """Return device information for this Docker container."""
        try:
            # Get container details
            container = self._get_container_data()
            
            if not container:
                # Fall back to basic info if container not found
                return DeviceInfo(
                    identifiers={(DOMAIN, f"docker_{self._container_id}")},
                    name=f"Docker: {self._container_name}",
                    manufacturer="Docker",
                    model="Container",
                    via_device=(DOMAIN, self._config_entry.entry_id),
                )
                
            # If we have container info, create more detailed device info
            image = container.get("image", "unknown")
            image_parts = image.split(":")
            sw_version = "latest"
            if len(image_parts) > 1:
                sw_version = image_parts[1]
                
            return DeviceInfo(
                identifiers={(DOMAIN, f"docker_{self._container_id}")},
                name=f"Docker: {self._container_name}",
                manufacturer="Docker",
                model=image_parts[0] if len(image_parts) > 0 else image,
                sw_version=sw_version,
                via_device=(DOMAIN, self._config_entry.entry_id),
                configuration_url=f"http://{self._config_entry.data.get('host')}/Docker",
            )
        except Exception as err:
            LOGGER.warning("Error generating Docker device info: %s", err)
            return DeviceInfo(
                identifiers={(DOMAIN, f"docker_{self._container_id}")},
                name=f"Docker: {self._container_name}",
                manufacturer="Docker",
                via_device=(DOMAIN, self._config_entry.entry_id),
            )
            
    def _get_container_data(self) -> dict[str, Any] | None:
        """Get the container data from coordinator data."""
        try:
            if not self.coordinator.data or "docker" not in self.coordinator.data:
                return None
                
            for container in self.coordinator.data["docker"]:
                if container.get("id") == self._container_id:
                    return container
                    
            return None
        except Exception as err:
            LOGGER.warning("Error fetching container data: %s", err)
            return None
            
    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not super().available:
            return False
            
        # Entity is only available if the container still exists
        return self._get_container_data() is not None