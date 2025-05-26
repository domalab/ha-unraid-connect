"""The Unraid integration."""
# ruff: noqa: C901

import logging

import aiohttp
import voluptuous as vol

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    CONF_API_KEY,
    CONF_HOST,
    CONF_NAME,
    CONF_SCAN_INTERVAL,
    CONF_VERIFY_SSL,
    Platform,
)
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import config_validation as cv, entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import UnraidApiClient, UnraidApiError
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DOMAIN as INTEGRATION_DOMAIN,
    SERVICE_CANCEL_PARITY_CHECK,
    SERVICE_DOCKER_LOGS,
    SERVICE_DOCKER_RESTART,
    SERVICE_PAUSE_PARITY_CHECK,
    SERVICE_REBOOT,
    SERVICE_RESUME_PARITY_CHECK,
    SERVICE_SHUTDOWN,
    SERVICE_START_ARRAY,
    SERVICE_START_PARITY_CHECK,
    SERVICE_STOP_ARRAY,
    SERVICE_VM_FORCE_SHUTDOWN,
    SERVICE_VM_FORCE_STOP,
    SERVICE_VM_PAUSE,
    SERVICE_VM_REBOOT,
    SERVICE_VM_RESET,
    SERVICE_VM_RESUME,
)
from .coordinator import UnraidDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
]

# Service schemas
START_PARITY_SCHEMA = vol.Schema(
    {
        vol.Optional("correct", default=False): cv.boolean,
    }
)

# VM service schemas
VM_ID_SCHEMA = vol.Schema(
    {
        vol.Optional("vm_id"): cv.string,
    }
)

VM_FORCE_SCHEMA = vol.Schema(
    {
        vol.Optional("vm_id"): cv.string,
        vol.Optional("force", default=True): cv.boolean,
    }
)

# Docker service schemas
DOCKER_ID_SCHEMA = vol.Schema(
    {
        vol.Optional("container_id"): cv.string,
    }
)

DOCKER_LOGS_SCHEMA = vol.Schema(
    {
        vol.Optional("container_id"): cv.string,
        vol.Optional("lines", default=100): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=1000)
        ),
    }
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Unraid from a config entry."""
    # Get config entry data
    host = entry.data[CONF_HOST]
    api_key = entry.data[CONF_API_KEY]
    name = entry.data.get(CONF_NAME, host)
    verify_ssl = entry.options.get(
        CONF_VERIFY_SSL, entry.data.get(CONF_VERIFY_SSL, True)
    )
    scan_interval = entry.options.get(
        CONF_SCAN_INTERVAL, entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )

    # Create API client
    session = async_get_clientsession(hass)
    client = UnraidApiClient(
        host=host,
        api_key=api_key,
        session=session,
        verify_ssl=verify_ssl,
    )

    # Try to discover redirect URL
    try:
        await client.discover_redirect_url()
    except (TimeoutError, aiohttp.ClientError) as err:
        _LOGGER.warning("Failed to discover redirect URL: %s", err)

    # Create coordinator
    coordinator = UnraidDataUpdateCoordinator(
        hass=hass,
        api=client,
        update_interval=scan_interval,
        name=name,
    )
    coordinator.config_entry = entry

    # Fetch initial data
    try:
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryNotReady as err:
        _LOGGER.error("Failed to get initial data - please ensure:")
        _LOGGER.error("1. Your API key is correct")
        _LOGGER.error(
            "2. You've added http://YOUR_HA_IP:8123 to Unraid Connect's extra origins"
        )
        _LOGGER.error("3. You've clicked APPLY after adding the origin")
        raise ConfigEntryNotReady(f"Failed to get initial data: {err}") from err

    # Store coordinator and API client
    hass.data.setdefault(INTEGRATION_DOMAIN, {})
    hass.data[INTEGRATION_DOMAIN][entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "name": name,
    }

    # Set runtime data
    entry.runtime_data = {"version": client.version}

    # Register services
    async def start_array(_: ServiceCall) -> None:
        """Start the array."""
        try:
            await client.start_array()
            await coordinator.async_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to start array: %s", err)

    async def stop_array(_: ServiceCall) -> None:
        """Stop the array."""
        try:
            await client.stop_array()
            await coordinator.async_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to stop array: %s", err)

    async def start_parity_check(call: ServiceCall) -> None:
        """Start parity check."""
        correct = call.data.get("correct", False)
        try:
            await client.start_parity_check(correct=correct)
            await coordinator.async_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to start parity check: %s", err)

    async def pause_parity_check(_: ServiceCall) -> None:
        """Pause parity check."""
        try:
            await client.pause_parity_check()
            await coordinator.async_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to pause parity check: %s", err)

    async def resume_parity_check(_: ServiceCall) -> None:
        """Resume parity check."""
        try:
            await client.resume_parity_check()
            await coordinator.async_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to resume parity check: %s", err)

    async def cancel_parity_check(_: ServiceCall) -> None:
        """Cancel parity check."""
        try:
            await client.cancel_parity_check()
            await coordinator.async_refresh()
        except UnraidApiError as err:
            _LOGGER.error("Failed to cancel parity check: %s", err)

    async def reboot(_: ServiceCall) -> None:
        """Reboot server."""
        try:
            await client.reboot()
        except UnraidApiError as err:
            _LOGGER.error("Failed to reboot server: %s", err)

    async def shutdown(_: ServiceCall) -> None:
        """Shutdown server."""
        try:
            await client.shutdown()
        except UnraidApiError as err:
            _LOGGER.error("Failed to shutdown server: %s", err)

    # VM service handlers
    async def vm_pause(call: ServiceCall) -> None:
        """Pause a VM."""
        vm_id = call.data.get("vm_id")
        entity_id = None

        # Get the entity_id from the target entities if available
        if (
            hasattr(call, "target")
            and call.target
            and hasattr(call.target, "entity_id")
        ):
            entity_id = call.target.entity_id

        # If no VM ID provided, try to get it from the entity
        if not vm_id and entity_id:
            entity_registry = er.async_get(hass)
            if entity_entry := entity_registry.async_get(entity_id):
                # Extract VM ID from the unique ID
                # Format is typically: {server_name}_{type}_{vm_id}
                unique_id_parts = entity_entry.unique_id.split("_")
                if len(unique_id_parts) >= 3:
                    vm_id = unique_id_parts[-1]

        if not vm_id:
            _LOGGER.error("No VM ID provided and couldn't extract it from entity")
            return

        try:
            await client.pause_vm(vm_id)
            await coordinator.async_refresh()
            _LOGGER.info("Successfully paused VM %s", vm_id)
        except UnraidApiError as err:
            _LOGGER.error("Failed to pause VM %s: %s", vm_id, err)

    async def vm_resume(call: ServiceCall) -> None:
        """Resume a VM."""
        vm_id = call.data.get("vm_id")
        entity_id = None

        # Get the entity_id from the target entities if available
        if (
            hasattr(call, "target")
            and call.target
            and hasattr(call.target, "entity_id")
        ):
            entity_id = call.target.entity_id

        # If no VM ID provided, try to get it from the entity
        if not vm_id and entity_id:
            entity_registry = er.async_get(hass)
            if entity_entry := entity_registry.async_get(entity_id):
                # Extract VM ID from the unique ID
                unique_id_parts = entity_entry.unique_id.split("_")
                if len(unique_id_parts) >= 3:
                    vm_id = unique_id_parts[-1]

        if not vm_id:
            _LOGGER.error("No VM ID provided and couldn't extract it from entity")
            return

        try:
            await client.resume_vm(vm_id)
            await coordinator.async_refresh()
            _LOGGER.info("Successfully resumed VM %s", vm_id)
        except UnraidApiError as err:
            _LOGGER.error("Failed to resume VM %s: %s", vm_id, err)

    async def vm_force_shutdown(call: ServiceCall) -> None:
        """Force shutdown a VM."""
        vm_id = call.data.get("vm_id")
        entity_id = None
        force = call.data.get("force", True)

        # Get the entity_id from the target entities if available
        if (
            hasattr(call, "target")
            and call.target
            and hasattr(call.target, "entity_id")
        ):
            entity_id = call.target.entity_id

        # If no VM ID provided, try to get it from the entity
        if not vm_id and entity_id:
            entity_registry = er.async_get(hass)
            if entity_entry := entity_registry.async_get(entity_id):
                # Extract VM ID from the unique ID
                unique_id_parts = entity_entry.unique_id.split("_")
                if len(unique_id_parts) >= 3:
                    vm_id = unique_id_parts[-1]

        if not vm_id:
            _LOGGER.error("No VM ID provided and couldn't extract it from entity")
            return

        try:
            await client.stop_vm(vm_id, force=force)
            await coordinator.async_refresh()
            _LOGGER.info("Successfully force shutdown VM %s", vm_id)
        except UnraidApiError as err:
            _LOGGER.error("Failed to force shutdown VM %s: %s", vm_id, err)

    async def vm_reboot(call: ServiceCall) -> None:
        """Reboot a VM."""
        vm_id = call.data.get("vm_id")
        entity_id = None

        # Get the entity_id from the target entities if available
        if (
            hasattr(call, "target")
            and call.target
            and hasattr(call.target, "entity_id")
        ):
            entity_id = call.target.entity_id

        # If no VM ID provided, try to get it from the entity
        if not vm_id and entity_id:
            entity_registry = er.async_get(hass)
            if entity_entry := entity_registry.async_get(entity_id):
                # Extract VM ID from the unique ID
                unique_id_parts = entity_entry.unique_id.split("_")
                if len(unique_id_parts) >= 3:
                    vm_id = unique_id_parts[-1]

        if not vm_id:
            _LOGGER.error("No VM ID provided and couldn't extract it from entity")
            return

        try:
            await client.reboot_vm(vm_id)
            await coordinator.async_refresh()
            _LOGGER.info("Successfully rebooted VM %s", vm_id)
        except UnraidApiError as err:
            _LOGGER.error("Failed to reboot VM %s: %s", vm_id, err)

    async def vm_reset(call: ServiceCall) -> None:
        """Reset a VM (hard reboot)."""
        vm_id = call.data.get("vm_id")
        entity_id = None

        # Get the entity_id from the target entities if available
        if (
            hasattr(call, "target")
            and call.target
            and hasattr(call.target, "entity_id")
        ):
            entity_id = call.target.entity_id

        # If no VM ID provided, try to get it from the entity
        if not vm_id and entity_id:
            entity_registry = er.async_get(hass)
            if entity_entry := entity_registry.async_get(entity_id):
                # Extract VM ID from the unique ID
                unique_id_parts = entity_entry.unique_id.split("_")
                if len(unique_id_parts) >= 3:
                    vm_id = unique_id_parts[-1]

        if not vm_id:
            _LOGGER.error("No VM ID provided and couldn't extract it from entity")
            return

        try:
            await client.reset_vm(vm_id)
            await coordinator.async_refresh()
            _LOGGER.info("Successfully reset VM %s", vm_id)
        except UnraidApiError as err:
            _LOGGER.error("Failed to reset VM %s: %s", vm_id, err)

    async def vm_force_stop(call: ServiceCall) -> None:
        """Force stop a VM."""
        vm_id = call.data.get("vm_id")
        entity_id = None

        # Get the entity_id from the target entities if available
        if (
            hasattr(call, "target")
            and call.target
            and hasattr(call.target, "entity_id")
        ):
            entity_id = call.target.entity_id

        # If no VM ID provided, try to get it from the entity
        if not vm_id and entity_id:
            entity_registry = er.async_get(hass)
            if entity_entry := entity_registry.async_get(entity_id):
                # Extract VM ID from the unique ID
                unique_id_parts = entity_entry.unique_id.split("_")
                if len(unique_id_parts) >= 3:
                    vm_id = unique_id_parts[-1]

        if not vm_id:
            _LOGGER.error("No VM ID provided and couldn't extract it from entity")
            return

        try:
            await client.force_stop_vm(vm_id)
            await coordinator.async_refresh()
            _LOGGER.info("Successfully force stopped VM %s", vm_id)
        except UnraidApiError as err:
            _LOGGER.error("Failed to force stop VM %s: %s", vm_id, err)

    # Docker service handlers
    async def docker_restart(call: ServiceCall) -> None:
        """Restart a Docker container."""
        container_id = call.data.get("container_id")
        entity_id = None

        # Get the entity_id from the target entities if available
        if (
            hasattr(call, "target")
            and call.target
            and hasattr(call.target, "entity_id")
        ):
            entity_id = call.target.entity_id

        # If no container ID provided, try to get it from the entity
        if not container_id and entity_id:
            entity_registry = er.async_get(hass)
            if entity_entry := entity_registry.async_get(entity_id):
                # Extract container ID from the unique ID
                unique_id_parts = entity_entry.unique_id.split("_")
                if len(unique_id_parts) >= 3:
                    container_id = unique_id_parts[-1]

        if not container_id:
            _LOGGER.error(
                "No container ID provided and couldn't extract it from entity"
            )
            return

        try:
            await client.restart_docker_container(container_id)
            await coordinator.async_refresh()
            _LOGGER.info("Successfully restarted Docker container %s", container_id)
        except UnraidApiError as err:
            _LOGGER.error(
                "Failed to restart Docker container %s: %s", container_id, err
            )

    async def docker_logs(call: ServiceCall) -> None:
        """Get logs from a Docker container."""
        container_id = call.data.get("container_id")
        entity_id = None
        lines = call.data.get("lines", 100)

        # Get the entity_id from the target entities if available
        if (
            hasattr(call, "target")
            and call.target
            and hasattr(call.target, "entity_id")
        ):
            entity_id = call.target.entity_id

        # If no container ID provided, try to get it from the entity
        if not container_id and entity_id:
            entity_registry = er.async_get(hass)
            if entity_entry := entity_registry.async_get(entity_id):
                # Extract container ID from the unique ID
                unique_id_parts = entity_entry.unique_id.split("_")
                if len(unique_id_parts) >= 3:
                    container_id = unique_id_parts[-1]

        if not container_id:
            _LOGGER.error(
                "No container ID provided and couldn't extract it from entity"
            )
            return

        try:
            logs_result = await client.get_docker_logs(container_id, lines=lines)

            if "error" in logs_result:
                _LOGGER.error("Failed to get logs: %s", logs_result["error"])
                return

            logs = logs_result.get("logs", "")

            # Create a persistent notification with the logs
            notification_id = f"unraid_docker_logs_{container_id[:8]}"
            notification_title = f"Docker Logs: {container_id[:8]}"

            persistent_notification.async_create(
                hass,
                message=logs,
                title=notification_title,
                notification_id=notification_id,
            )

            _LOGGER.info("Docker logs retrieved and notification created")
        except UnraidApiError as err:
            _LOGGER.error(
                "Failed to get Docker container logs %s: %s", container_id, err
            )

    # Register array services
    hass.services.async_register(INTEGRATION_DOMAIN, SERVICE_START_ARRAY, start_array)
    hass.services.async_register(INTEGRATION_DOMAIN, SERVICE_STOP_ARRAY, stop_array)
    hass.services.async_register(
        INTEGRATION_DOMAIN,
        SERVICE_START_PARITY_CHECK,
        start_parity_check,
        schema=START_PARITY_SCHEMA,
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN, SERVICE_PAUSE_PARITY_CHECK, pause_parity_check
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN, SERVICE_RESUME_PARITY_CHECK, resume_parity_check
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN, SERVICE_CANCEL_PARITY_CHECK, cancel_parity_check
    )
    hass.services.async_register(INTEGRATION_DOMAIN, SERVICE_REBOOT, reboot)
    hass.services.async_register(INTEGRATION_DOMAIN, SERVICE_SHUTDOWN, shutdown)

    # Register VM services
    hass.services.async_register(
        INTEGRATION_DOMAIN, SERVICE_VM_PAUSE, vm_pause, schema=VM_ID_SCHEMA
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN, SERVICE_VM_RESUME, vm_resume, schema=VM_ID_SCHEMA
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN,
        SERVICE_VM_FORCE_SHUTDOWN,
        vm_force_shutdown,
        schema=VM_FORCE_SCHEMA,
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN, SERVICE_VM_REBOOT, vm_reboot, schema=VM_ID_SCHEMA
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN, SERVICE_VM_RESET, vm_reset, schema=VM_ID_SCHEMA
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN, SERVICE_VM_FORCE_STOP, vm_force_stop, schema=VM_ID_SCHEMA
    )

    # Register Docker services
    hass.services.async_register(
        INTEGRATION_DOMAIN,
        SERVICE_DOCKER_RESTART,
        docker_restart,
        schema=DOCKER_ID_SCHEMA,
    )
    hass.services.async_register(
        INTEGRATION_DOMAIN, SERVICE_DOCKER_LOGS, docker_logs, schema=DOCKER_LOGS_SCHEMA
    )

    # Set up all platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Reload entry when options change
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    # Remove entry from data
    if unload_ok and INTEGRATION_DOMAIN in hass.data:
        if entry.entry_id in hass.data[INTEGRATION_DOMAIN]:
            hass.data[INTEGRATION_DOMAIN].pop(entry.entry_id)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry."""
    await hass.config_entries.async_reload(entry.entry_id)
