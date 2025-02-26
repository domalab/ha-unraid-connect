"""DataUpdateCoordinator for Unraid integration."""
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
                system_info_task = self.api.get_system_info()
                array_status_task = self.api.get_array_status()
                docker_containers_task = self.api.get_docker_containers()
                vms_task = self.api.get_vms()
                shares_task = self.api.get_shares()

                # Gather results
                results = await asyncio.gather(
                    system_info_task,
                    array_status_task,
                    docker_containers_task,
                    vms_task,
                    shares_task,
                    return_exceptions=True,
                )

                # Process results, handling any individual API errors
                if not isinstance(results[0], Exception):
                    self.data["system_info"] = results[0]
                else:
                    _LOGGER.error("Error fetching system info: %s", results[0])

                if not isinstance(results[1], Exception):
                    self.data["array_status"] = results[1]
                else:
                    _LOGGER.error("Error fetching array status: %s", results[1])

                if not isinstance(results[2], Exception):
                    self.data["docker_containers"] = results[2]
                else:
                    _LOGGER.error("Error fetching docker containers: %s", results[2])

                if not isinstance(results[3], Exception):
                    self.data["vms"] = results[3]
                else:
                    _LOGGER.error("Error fetching VMs: %s", results[3])

                if not isinstance(results[4], Exception):
                    self.data["shares"] = results[4]
                else:
                    _LOGGER.error("Error fetching shares: %s", results[4])

                return self.data

        except UnraidApiError as err:
            if err.status in ("401", "403"):
                raise ConfigEntryAuthFailed from err
            raise UpdateFailed(f"Error communicating with Unraid API: {err}")
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}")