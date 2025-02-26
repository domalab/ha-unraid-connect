"""Base entity classes for Unraid integration."""
from typing import Any, Dict, Optional

from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, ICON_SERVER
from .coordinator import UnraidDataUpdateCoordinator


class UnraidEntity(CoordinatorEntity, Entity):
    """Base entity for Unraid integration."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        entity_type: str,
        entity_key: str,
    ):
        """Initialize the entity."""
        super().__init__(coordinator)
        self._server_name = server_name
        self._entity_type = entity_type
        self._entity_key = entity_key
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{coordinator.api.host}_{entity_type}_{entity_key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for this entity."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.api.host)},
            name=self._server_name,
            manufacturer="Unraid",
            model=self._get_unraid_version(),
            configuration_url=self.coordinator.api.host,
        )

    def _get_unraid_version(self) -> str:
        """Get the Unraid version from the API data."""
        try:
            return self.coordinator.data.get("system_info", {}).get("info", {}).get("versions", {}).get("unraid", "Unknown")
        except (KeyError, AttributeError):
            return "Unknown"

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self.async_write_ha_state()


class UnraidSystemEntity(UnraidEntity):
    """Base entity for Unraid system entities."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        entity_key: str,
    ):
        """Initialize the entity."""
        super().__init__(coordinator, server_name, "system", entity_key)
        self._attr_icon = ICON_SERVER


class UnraidArrayEntity(UnraidEntity):
    """Base entity for Unraid array entities."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        entity_key: str,
    ):
        """Initialize the entity."""
        super().__init__(coordinator, server_name, "array", entity_key)


class UnraidDiskEntity(UnraidEntity):
    """Base entity for Unraid disk entities."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        entity_key: str,
        disk_id: str,
        disk_type: str,
    ):
        """Initialize the entity."""
        super().__init__(coordinator, server_name, "disk", entity_key)
        self._disk_id = disk_id
        self._disk_type = disk_type
        # Update unique ID to include disk ID
        self._attr_unique_id = f"{coordinator.api.host}_disk_{disk_id}_{entity_key}"


class UnraidDockerEntity(UnraidEntity):
    """Base entity for Unraid Docker entities."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        entity_key: str,
        container_id: str,
    ):
        """Initialize the entity."""
        super().__init__(coordinator, server_name, "docker", entity_key)
        self._container_id = container_id
        # Update unique ID to include container ID
        self._attr_unique_id = f"{coordinator.api.host}_docker_{container_id}_{entity_key}"


class UnraidVMEntity(UnraidEntity):
    """Base entity for Unraid VM entities."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        entity_key: str,
        vm_id: str,
    ):
        """Initialize the entity."""
        super().__init__(coordinator, server_name, "vm", entity_key)
        self._vm_id = vm_id
        # Update unique ID to include VM ID
        self._attr_unique_id = f"{coordinator.api.host}_vm_{vm_id}_{entity_key}"


class UnraidShareEntity(UnraidEntity):
    """Base entity for Unraid share entities."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        entity_key: str,
        share_name: str,
    ):
        """Initialize the entity."""
        super().__init__(coordinator, server_name, "share", entity_key)
        self._share_name = share_name
        # Update unique ID to include share name
        self._attr_unique_id = f"{coordinator.api.host}_share_{share_name}_{entity_key}"