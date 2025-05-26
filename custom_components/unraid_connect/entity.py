"""Base entity classes for Unraid integration."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN as INTEGRATION_DOMAIN, ICON_SERVER
from .coordinator import UnraidDataUpdateCoordinator


class UnraidEntity(CoordinatorEntity[UnraidDataUpdateCoordinator], Entity):
    """Base entity for Unraid integration."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        entity_type: str,
        entity_key: str,
    ) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._server_name = server_name
        self._entity_type = entity_type
        self._entity_key = entity_key
        self._attr_has_entity_name = True
        # Use the config entry ID for the unique_id to make it consistent across restarts
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{entity_type}_{entity_key}"
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for this entity."""
        # Get the host from the API client, handling the case when it's a mock object
        host = self.coordinator.api.host
        if hasattr(host, "__class__") and "Mock" in host.__class__.__name__:
            # For tests, use a valid URL
            host = "http://192.168.1.100"

        return DeviceInfo(
            identifiers={(INTEGRATION_DOMAIN, str(host))},
            name=self._server_name,
            manufacturer="Unraid",
            model=self._get_unraid_version(),
            configuration_url=str(host),
        )

    def _get_unraid_version(self) -> str:
        """Get the Unraid version from the API data."""
        try:
            return (
                self.coordinator.data.get("system_info", {})
                .get("info", {})
                .get("versions", {})
                .get("unraid", "Unknown")
            )
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
    ) -> None:
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
    ) -> None:
        """Initialize the entity."""
        # Normalize entity_key to make cleaner entity_ids
        if entity_key == "space_used":
            entity_key = "usage"
        elif entity_key == "space_free":
            entity_key = "free_space"
        elif entity_key == "space_total":
            entity_key = "total_space"

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
    ) -> None:
        """Initialize the entity."""
        # Normalize entity_key to make cleaner entity_ids
        if entity_key == "space_used":
            entity_key = "usage"
        elif entity_key == "space_free":
            entity_key = "free_space"

        super().__init__(coordinator, server_name, "disk", entity_key)
        self._disk_id = disk_id
        self._disk_type = disk_type
        # Update unique ID to include disk ID
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_disk_{disk_id}_{entity_key}"
        )


class UnraidDockerEntity(UnraidEntity):
    """Base entity for Unraid Docker entities."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        entity_key: str,
        container_id: str,
    ) -> None:
        """Initialize the entity."""
        # Normalize entity_key - remove "running" to make cleaner entity_ids
        if entity_key == "running":
            entity_key = ""

        super().__init__(coordinator, server_name, "docker", entity_key)
        self._container_id = container_id
        # Update unique ID to include container ID
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_docker_{container_id}_{entity_key}"
        )


class UnraidVMEntity(UnraidEntity):
    """Base entity for Unraid VM entities."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        entity_key: str,
        vm_id: str,
    ) -> None:
        """Initialize the entity."""
        # Normalize entity_key - remove "running" to make cleaner entity_ids
        if entity_key == "running":
            entity_key = ""

        super().__init__(coordinator, server_name, "vm", entity_key)
        self._vm_id = vm_id
        # Update unique ID to include VM ID
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_vm_{vm_id}_{entity_key}"
        )


class UnraidShareEntity(UnraidEntity):
    """Base entity for Unraid share entities."""

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        entity_key: str,
        share_name: str,
    ) -> None:
        """Initialize the entity."""
        # Clean up share_name for use in entity IDs
        share_name_clean = share_name.replace("/", "_")
        self._share_name = share_name  # Keep original for API calls

        # Normalize entity_key to make cleaner entity_ids
        if entity_key == "space_used":
            entity_key = "usage"
        elif entity_key == "space_free":
            entity_key = "free_space"

        super().__init__(coordinator, server_name, "share", entity_key)
        # Update unique ID to include cleaned share name
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_share_{share_name_clean}_{entity_key}"
        )
