"""
Data update coordinator for the Unraid integration.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any, Callable

import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from gql.transport.exceptions import TransportQueryError, TransportServerError

from .api import UnraidAPI
from .const import DOMAIN, LOGGER, DEFAULT_SCAN_INTERVAL

class UnraidDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the Unraid API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UnraidAPI,
        update_interval: timedelta | None = None,
    ) -> None:
        """Initialize coordinator."""
        self.api = api
        self.hass = hass
        
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            update_interval=update_interval or timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API."""
        LOGGER.debug("Starting data update from Unraid API")
        async with async_timeout.timeout(30):
            try:
                # Create task group for concurrent API calls
                system_info_task = asyncio.create_task(self.api.get_system_info())
                array_status_task = asyncio.create_task(self.api.get_array_status())
                docker_status_task = asyncio.create_task(self.api.get_docker_status())
                
                # Wait for all tasks to complete
                system_info, array_status, docker_status = await asyncio.gather(
                    system_info_task,
                    array_status_task,
                    docker_status_task,
                )
                
                LOGGER.debug("System info received with %d keys", 
                           len(system_info) if isinstance(system_info, dict) else 0)
                LOGGER.debug("Array status received with %d keys", 
                           len(array_status) if isinstance(array_status, dict) else 0)
                LOGGER.debug("Docker status received with %d containers", 
                           len(docker_status) if isinstance(docker_status, list) else 0)
                
                LOGGER.debug("Data update completed successfully")
                return {
                    "system": system_info,
                    "array": array_status,
                    "docker": docker_status,
                }
            except TransportQueryError as err:
                LOGGER.error("GraphQL query error: %s", err.errors, exc_info=True)
                raise UpdateFailed(f"GraphQL query error: {err}")
            except TransportServerError as err:
                LOGGER.error("GraphQL server error: %s", err, exc_info=True)
                raise UpdateFailed(f"GraphQL server error: {err}")
            except asyncio.TimeoutError:
                LOGGER.error("Timeout while fetching data from Unraid API")
                raise UpdateFailed("Timeout while fetching data")
            except Exception as err:
                LOGGER.error("Unexpected error communicating with API: %s", err, exc_info=True)
                raise UpdateFailed(f"Error communicating with API: {err}")

    async def async_service_array_operation(self, operation: str) -> None:
        """Execute array operation through API."""
        LOGGER.info("Executing array operation: %s", operation)
        try:
            await self.api.control_array(operation)
            await self.async_request_refresh()
        except Exception as err:
            LOGGER.error("Failed to execute array operation: %s", err)
            raise

    async def async_service_docker_container(self, container_id: str, action: str) -> None:
        """Execute Docker container action through API."""
        LOGGER.info("Executing Docker container action: %s on %s", action, container_id)
        try:
            await self.api.control_docker_container(container_id, action)
            # Allow time for the container to change state
            await asyncio.sleep(2)
            await self.async_request_refresh()
        except Exception as err:
            LOGGER.error("Failed to execute Docker container action: %s", err)
            raise