"""DataUpdateCoordinator for Unraid integration."""
import asyncio
import logging
from datetime import timedelta
from typing import Any, Dict

import async_timeout
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.exceptions import ConfigEntryAuthFailed

from .api import UnraidApiClient, UnraidApiError
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class UnraidDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Unraid data."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: UnraidApiClient,
        update_interval: int,
        name: str,
    ):
        """Initialize the coordinator."""
        self.api = api
        self.name = name
        self.data = {}

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=update_interval),
        )

    async def _async_update_data(self) -> Dict[str, Any]:
        """Fetch data from Unraid API."""
        try:
            async with async_timeout.timeout(60):
                # Initialize data structure if it doesn't exist
                if not self.data:
                    self.data = {
                        "system_info": {},
                        "array_status": {},
                        "docker_containers": {},
                        "vms": {},
                        "shares": {},
                    }

                # Fetch all data in parallel
                tasks = [
                    self.api.get_system_info(),
                    self.api.get_array_status(),
                    self.api.get_docker_containers(),
                    self.api.get_vms(),
                    self.api.get_shares()
                ]
                
                # Try to get as much data as possible
                try:
                    system_info = await tasks[0]
                    self.data["system_info"] = system_info
                except Exception as err:
                    _LOGGER.error("Error fetching system info: %s", err)

                try:
                    array_status = await tasks[1]
                    self.data["array_status"] = array_status
                except Exception as err:
                    _LOGGER.error("Error fetching array status: %s", err)

                try:
                    docker_containers = await tasks[2]
                    self.data["docker_containers"] = docker_containers
                except Exception as err:
                    _LOGGER.error("Error fetching docker containers: %s", err)

                try:
                    vms = await tasks[3]
                    self.data["vms"] = vms
                except Exception as err:
                    _LOGGER.error("Error fetching VMs: %s", err)

                try:
                    shares = await tasks[4]
                    self.data["shares"] = shares
                except Exception as err:
                    _LOGGER.error("Error fetching shares: %s", err)

                # Return data even if some requests failed
                return self.data

        except UnraidApiError as err:
            if any(s in str(err) for s in ("401", "403", "Unauthorized", "Forbidden")):
                raise ConfigEntryAuthFailed from err
            raise UpdateFailed(f"Error communicating with Unraid API: {err}")
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}")