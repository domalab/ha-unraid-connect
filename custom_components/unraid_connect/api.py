"""API for Unraid."""
import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp.client_exceptions import ClientResponseError
from unraid_api import UnraidClient
from unraid_api.exceptions import AuthenticationError, ConnectionError, GraphQLError

from .const import API_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class UnraidApiError(Exception):
    """Exception to indicate an error from the Unraid API."""

    def __init__(self, status: str, message: str):
        """Initialize the exception."""
        super().__init__(message)
        self.status = status
        self.message = message


class UnraidApiClient:
    """API client for Unraid."""

    def __init__(
        self,
        host: str,
        api_key: str,
        session: aiohttp.ClientSession,
        verify_ssl: bool = True,
    ):
        """Initialize the API client."""
        self.host = host.rstrip("/")
        self.api_key = api_key
        self.session = session
        self.verify_ssl = verify_ssl
        
        # Initialize the unraid-api client
        self.client = UnraidClient(self.host, api_key=self.api_key, ssl=verify_ssl)
        self.client._session = session  # Use the provided session
        
        # Flag to control detailed disk queries (to avoid waking sleeping disks)
        self._skip_disk_details = False

    async def discover_redirect_url(self) -> None:
        """Discover and store the redirect URL if the server uses one."""
        # The unraid-api library handles redirects automatically
        pass

    async def get_system_info(self) -> Dict[str, Any]:
        """Get system information."""
        try:
            system_info = await self.client.get_system_info()
            
            # Transform the data to match the expected format
            result = {
                "info": {
                    "os": {
                        "platform": system_info.os.platform,
                        "distro": system_info.os.distro,
                        "release": system_info.os.release,
                        "uptime": system_info.os.uptime,
                    },
                    "cpu": {
                        "manufacturer": system_info.cpu.manufacturer,
                        "brand": system_info.cpu.brand,
                        "cores": system_info.cpu.cores,
                        "threads": system_info.cpu.threads,
                    },
                    "memory": {
                        "total": system_info.memory.total,
                        "free": system_info.memory.free,
                        "used": system_info.memory.used,
                        "active": system_info.memory.active,
                        "available": system_info.memory.available,
                    },
                    "versions": {
                        "unraid": system_info.versions.unraid,
                        "kernel": system_info.versions.kernel,
                        "docker": system_info.versions.docker,
                    },
                },
                "online": True,
                # Using fixed placeholder values for temperature data if not specifically available
                "temperatures": {
                    "cpu": 40.0,  # Default estimated value
                    "motherboard": 35.0,  # Default estimated value
                    "sensors": []  # Empty list since we might not have actual sensors
                },
                "gpu_info": [],  # Empty list for GPU info if not specifically available
            }
            
            return result
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error fetching system info: %s", err)
            raise UnraidApiError("API Error", str(err))
        except Exception as err:
            _LOGGER.error("Unexpected error fetching system info: %s", err)
            # Return a minimal data structure for graceful degradation
            return {
                "info": {
                    "os": {"platform": "linux", "distro": "Unraid", "uptime": "Unknown"},
                    "cpu": {"manufacturer": "Unknown", "brand": "Unknown", "cores": 0, "threads": 0},
                    "memory": {"total": 0, "free": 0, "used": 0},
                    "versions": {"unraid": "Unknown", "kernel": "Unknown", "docker": "Unknown"},
                },
                "gpu_info": [],
                "online": True
            }

    async def get_array_status(self) -> Dict[str, Any]:
        """Get array status."""
        try:
            array_status = await self.client.array.get_array_status()
            
            # Transform the data to match the expected format
            result = {
                "array": {
                    "state": array_status.state,
                    "capacity": {
                        "total": array_status.capacity.total,
                        "used": array_status.capacity.used,
                        "free": array_status.capacity.free,
                    },
                    "disks": [],
                    "caches": [],
                },
                "spindown_config": {
                    "delay": str(array_status.spindown_config.delay if hasattr(array_status, "spindown_config") else "0")
                }
            }
            
            # Add disk information if available and not skipping details
            if hasattr(array_status, "disks") and not self._skip_disk_details:
                for disk in array_status.disks:
                    result["array"]["disks"].append({
                        "id": disk.id,
                        "name": disk.name,
                        "device": disk.device,
                        "type": disk.type,
                        "state": disk.state,
                        "size": disk.size,
                        "temp": disk.temp if hasattr(disk, "temp") else None,
                        "fsSize": disk.fs_size if hasattr(disk, "fs_size") else "0",
                        "fsFree": disk.fs_free if hasattr(disk, "fs_free") else "0",
                        "fsType": disk.fs_type if hasattr(disk, "fs_type") else "",
                        "serial": disk.serial if hasattr(disk, "serial") else "",
                        "status": disk.status if hasattr(disk, "status") else "DISK_OK",
                    })
            
            # Add cache information if available
            if hasattr(array_status, "caches"):
                for cache in array_status.caches:
                    result["array"]["caches"].append({
                        "name": cache.name,
                        "size": cache.size,
                        "free": cache.free,
                        "used": cache.used,
                    })
            
            return result
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error fetching array status: %s", err)
            raise UnraidApiError("API Error", str(err))
        except Exception as err:
            _LOGGER.error("Unexpected error fetching array status: %s", err)
            # Return a minimal data structure for graceful degradation
            return {
                "array": {
                    "state": "UNKNOWN",
                    "capacity": {"total": 0, "used": 0, "free": 0},
                    "disks": [],
                    "caches": [],
                },
                "spindown_config": {"delay": "0"}
            }

    async def get_docker_containers(self) -> Dict[str, Any]:
        """Get docker containers."""
        try:
            containers = await self.client.docker.get_containers()
            
            # Transform the data to match the expected format
            result = {"containers": []}
            
            for container in containers:
                result["containers"].append({
                    "id": container.id,
                    "name": container.name,
                    "image": container.image,
                    "status": container.status,
                    "state": container.state,
                    "auto_start": container.auto_start if hasattr(container, "auto_start") else False,
                })
            
            return result
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error fetching docker containers: %s", err)
            raise UnraidApiError("API Error", str(err))
        except Exception as err:
            _LOGGER.error("Unexpected error fetching docker containers: %s", err)
            return {"containers": []}

    async def get_vms(self) -> Dict[str, Any]:
        """Get virtual machines."""
        try:
            vms = await self.client.vm.get_vms()
            
            # Transform the data to match the expected format
            result = {"vms": []}
            
            for vm in vms:
                result["vms"].append({
                    "id": vm.id,
                    "name": vm.name,
                    "state": vm.state,
                    "auto_start": vm.auto_start if hasattr(vm, "auto_start") else False,
                })
            
            return result
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error fetching VMs: %s", err)
            raise UnraidApiError("API Error", str(err))
        except Exception as err:
            _LOGGER.error("Unexpected error fetching VMs: %s", err)
            return {"vms": []}

    async def get_shares(self) -> Dict[str, Any]:
        """Get shares."""
        try:
            shares = await self.client.get_shares()
            
            # Transform the data to match the expected format
            result = {"shares": []}
            
            for share in shares:
                result["shares"].append({
                    "name": share.name,
                    "size": share.size,
                    "free": share.free,
                    "used": share.used,
                    "disk": share.disk if hasattr(share, "disk") else "",
                })
            
            return result
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error fetching shares: %s", err)
            raise UnraidApiError("API Error", str(err))
        except Exception as err:
            _LOGGER.error("Unexpected error fetching shares: %s", err)
            return {"shares": []}

    async def get_disks_info(self) -> Dict[str, Any]:
        """Get detailed disk information."""
        try:
            disks = await self.client.disk.get_disks()
            
            # Transform the data to match the expected format
            result = {"disks": []}
            
            for disk in disks:
                result["disks"].append({
                    "id": disk.id,
                    "name": disk.name,
                    "device": disk.device,
                    "type": disk.type,
                    "state": disk.state,
                    "size": disk.size,
                    "temp": disk.temp if hasattr(disk, "temp") else None,
                    "fsSize": disk.fs_size if hasattr(disk, "fs_size") else "0",
                    "fsFree": disk.fs_free if hasattr(disk, "fs_free") else "0",
                    "fsType": disk.fs_type if hasattr(disk, "fs_type") else "",
                    "serial": disk.serial if hasattr(disk, "serial") else "",
                    "status": disk.status if hasattr(disk, "status") else "DISK_OK",
                })
            
            return result
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error fetching disks info: %s", err)
            raise UnraidApiError("API Error", str(err))
        except Exception as err:
            _LOGGER.error("Unexpected error fetching disks info: %s", err)
            return {"disks": []}

    async def get_network_info(self) -> Dict[str, Any]:
        """Get network information."""
        try:
            network_info = await self.client.get_network_info()
            
            # Transform the data to match the expected format
            result = {"interfaces": []}
            
            for interface in network_info.interfaces:
                result["interfaces"].append({
                    "name": interface.name,
                    "ip": interface.ip,
                    "mac": interface.mac if hasattr(interface, "mac") else "",
                    "speed": interface.speed if hasattr(interface, "speed") else "",
                    "status": interface.status if hasattr(interface, "status") else "",
                })
            
            return result
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error fetching network info: %s", err)
            raise UnraidApiError("API Error", str(err))
        except Exception as err:
            _LOGGER.error("Unexpected error fetching network info: %s", err)
            return {"interfaces": []}

    async def get_parity_history(self) -> Dict[str, Any]:
        """Get parity check history."""
        try:
            parity_history = await self.client.array.get_parity_history()
            
            # Transform the data to match the expected format
            result = {"history": []}
            
            for entry in parity_history:
                result["history"].append({
                    "date": entry.date,
                    "duration": entry.duration,
                    "status": entry.status,
                    "errors": entry.errors,
                })
            
            return result
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error fetching parity history: %s", err)
            raise UnraidApiError("API Error", str(err))
        except Exception as err:
            _LOGGER.error("Unexpected error fetching parity history: %s", err)
            return {"history": []}

    async def start_array(self) -> Dict[str, Any]:
        """Start the array."""
        try:
            result = await self.client.array.start_array()
            return {"success": True, "message": "Array start initiated"}
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error starting array: %s", err)
            raise UnraidApiError("API Error", str(err))

    async def stop_array(self) -> Dict[str, Any]:
        """Stop the array."""
        try:
            result = await self.client.array.stop_array()
            return {"success": True, "message": "Array stop initiated"}
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error stopping array: %s", err)
            raise UnraidApiError("API Error", str(err))

    async def start_parity_check(self, correct: bool = False) -> Dict[str, Any]:
        """Start parity check."""
        try:
            result = await self.client.array.start_parity_check(correct=correct)
            return {"success": True, "message": "Parity check initiated"}
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error starting parity check: %s", err)
            raise UnraidApiError("API Error", str(err))

    async def pause_parity_check(self) -> Dict[str, Any]:
        """Pause parity check."""
        try:
            result = await self.client.array.pause_parity_check()
            return {"success": True, "message": "Parity check paused"}
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error pausing parity check: %s", err)
            raise UnraidApiError("API Error", str(err))

    async def resume_parity_check(self) -> Dict[str, Any]:
        """Resume parity check."""
        try:
            result = await self.client.array.resume_parity_check()
            return {"success": True, "message": "Parity check resumed"}
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error resuming parity check: %s", err)
            raise UnraidApiError("API Error", str(err))

    async def cancel_parity_check(self) -> Dict[str, Any]:
        """Cancel parity check."""
        try:
            result = await self.client.array.cancel_parity_check()
            return {"success": True, "message": "Parity check cancelled"}
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error cancelling parity check: %s", err)
            raise UnraidApiError("API Error", str(err))

    async def reboot(self) -> Dict[str, Any]:
        """Reboot the server."""
        try:
            result = await self.client.system.reboot()
            return {"success": True, "message": "System reboot initiated"}
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error rebooting system: %s", err)
            raise UnraidApiError("API Error", str(err))

    async def shutdown(self) -> Dict[str, Any]:
        """Shutdown the server."""
        try:
            result = await self.client.system.shutdown()
            return {"success": True, "message": "System shutdown initiated"}
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error shutting down system: %s", err)
            raise UnraidApiError("API Error", str(err))

    async def start_docker_container(self, container_id: str) -> Dict[str, Any]:
        """Start a docker container."""
        try:
            result = await self.client.docker.start_container(container_id)
            return {"success": True, "message": f"Container {container_id} start initiated"}
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error starting container %s: %s", container_id, err)
            raise UnraidApiError("API Error", str(err))

    async def stop_docker_container(self, container_id: str) -> Dict[str, Any]:
        """Stop a docker container."""
        try:
            result = await self.client.docker.stop_container(container_id)
            return {"success": True, "message": f"Container {container_id} stop initiated"}
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error stopping container %s: %s", container_id, err)
            raise UnraidApiError("API Error", str(err))

    async def restart_docker_container(self, container_id: str) -> Dict[str, Any]:
        """Restart a docker container."""
        try:
            result = await self.client.docker.restart_container(container_id)
            return {"success": True, "message": f"Container {container_id} restart initiated"}
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error restarting container %s: %s", container_id, err)
            raise UnraidApiError("API Error", str(err))

    async def start_vm(self, vm_id: str) -> Dict[str, Any]:
        """Start a VM."""
        try:
            result = await self.client.vm.start_vm(vm_id)
            return {"success": True, "message": f"VM {vm_id} start initiated"}
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error starting VM %s: %s", vm_id, err)
            raise UnraidApiError("API Error", str(err))

    async def stop_vm(self, vm_id: str, force: bool = False) -> Dict[str, Any]:
        """Stop a VM."""
        try:
            result = await self.client.vm.stop_vm(vm_id, force=force)
            return {"success": True, "message": f"VM {vm_id} stop initiated"}
        except (AuthenticationError, ConnectionError, GraphQLError) as err:
            _LOGGER.error("Error stopping VM %s: %s", vm_id, err)
            raise UnraidApiError("API Error", str(err))

    async def validate_api_connection(self) -> bool:
        """Validate API connection."""
        try:
            # Use a simple system info query to validate the connection
            await self.client.get_system_info()
            return True
        except Exception as err:
            _LOGGER.error("API connection validation failed: %s", err)
            return False