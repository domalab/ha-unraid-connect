"""Button platform for Unraid integration."""

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import UnraidApiClient, UnraidApiError
from .const import DOMAIN as INTEGRATION_DOMAIN, ICON_ARRAY
from .entity import UnraidArrayEntity, UnraidSystemEntity

PARALLEL_UPDATES = 1

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Unraid buttons."""
    coordinator = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["coordinator"]
    name = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["name"]
    client = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["client"]

    entities = [
        # System buttons
        UnraidRebootButton(coordinator, client, name),
        UnraidShutdownButton(coordinator, client, name),
        # Array buttons
        UnraidStartArrayButton(coordinator, client, name),
        UnraidStopArrayButton(coordinator, client, name),
        # Parity check buttons
        UnraidStartParityCheckButton(coordinator, client, name),
        UnraidPauseParityCheckButton(coordinator, client, name),
        UnraidResumeParityCheckButton(coordinator, client, name),
        UnraidCancelParityCheckButton(coordinator, client, name),
    ]

    async_add_entities(entities)


class UnraidRebootButton(UnraidSystemEntity, ButtonEntity):
    """Button for rebooting Unraid server."""

    _attr_name = "Reboot"
    _attr_icon = "mdi:restart"
    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator,
        client: UnraidApiClient,
        server_name: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, server_name, "reboot")
        self.client = client

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.client.reboot()
        except UnraidApiError as err:
            _LOGGER.error("Failed to reboot server: %s", err)


class UnraidShutdownButton(UnraidSystemEntity, ButtonEntity):
    """Button for shutting down Unraid server."""

    _attr_name = "Shutdown"
    _attr_icon = "mdi:power"
    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator,
        client: UnraidApiClient,
        server_name: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, server_name, "shutdown")
        self.client = client

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.client.shutdown()
        except UnraidApiError as err:
            _LOGGER.error("Failed to shutdown server: %s", err)


class UnraidStartArrayButton(UnraidArrayEntity, ButtonEntity):
    """Button for starting Unraid array."""

    _attr_name = "Start Array"
    _attr_icon = ICON_ARRAY
    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator,
        client: UnraidApiClient,
        server_name: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, server_name, "start")
        self.client = client

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.client.start_array()
            await self.coordinator.async_request_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to start array: %s", err)


class UnraidStopArrayButton(UnraidArrayEntity, ButtonEntity):
    """Button for stopping Unraid array."""

    _attr_name = "Stop Array"
    _attr_icon = ICON_ARRAY
    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator,
        client: UnraidApiClient,
        server_name: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, server_name, "stop")
        self.client = client

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.client.stop_array()
            await self.coordinator.async_request_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to stop array: %s", err)


class UnraidStartParityCheckButton(UnraidArrayEntity, ButtonEntity):
    """Button for starting parity check."""

    _attr_name = "Start Parity Check"
    _attr_icon = "mdi:check-circle"
    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator,
        client: UnraidApiClient,
        server_name: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, server_name, "start_parity_check")
        self.client = client

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.client.start_parity_check(correct=False)
            await self.coordinator.async_request_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to start parity check: %s", err)


class UnraidPauseParityCheckButton(UnraidArrayEntity, ButtonEntity):
    """Button for pausing parity check."""

    _attr_name = "Pause Parity Check"
    _attr_icon = "mdi:pause-circle"
    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator,
        client: UnraidApiClient,
        server_name: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, server_name, "pause_parity_check")
        self.client = client

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.client.pause_parity_check()
            await self.coordinator.async_request_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to pause parity check: %s", err)


class UnraidResumeParityCheckButton(UnraidArrayEntity, ButtonEntity):
    """Button for resuming parity check."""

    _attr_name = "Resume Parity Check"
    _attr_icon = "mdi:play-circle"
    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator,
        client: UnraidApiClient,
        server_name: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, server_name, "resume_parity_check")
        self.client = client

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.client.resume_parity_check()
            await self.coordinator.async_request_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to resume parity check: %s", err)


class UnraidCancelParityCheckButton(UnraidArrayEntity, ButtonEntity):
    """Button for canceling parity check."""

    _attr_name = "Cancel Parity Check"
    _attr_icon = "mdi:close-circle"
    _attr_entity_registry_enabled_default = False
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(
        self,
        coordinator,
        client: UnraidApiClient,
        server_name: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, server_name, "cancel_parity_check")
        self.client = client

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.client.cancel_parity_check()
            await self.coordinator.async_request_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to cancel parity check: %s", err)
