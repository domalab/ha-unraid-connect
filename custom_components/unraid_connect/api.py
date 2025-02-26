"""API for Unraid."""
import asyncio
import logging
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp.client_exceptions import ClientResponseError

from .const import API_TIMEOUT, BASE_GRAPHQL_URL

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
        self.headers = {"x-api-key": api_key}
        self.api_url = f"{self.host}{BASE_GRAPHQL_URL}"

    async def _send_graphql_request(
        self, query: str, variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send a GraphQL request to the Unraid API."""
        json_data = {"query": query}
        if variables:
            json_data["variables"] = variables

        try:
            async with asyncio.timeout(API_TIMEOUT):
                async with self.session.post(
                    self.api_url,
                    json=json_data,
                    headers=self.headers,
                    ssl=self.verify_ssl,
                ) as resp:
                    if resp.status != 200:
                        raise UnraidApiError(
                            str(resp.status), f"Error from Unraid API: {await resp.text()}"
                        )
                    
                    response_json = await resp.json()
                    
                    # Check for GraphQL errors
                    if "errors" in response_json:
                        errors = response_json["errors"]
                        error_message = errors[0]["message"] if errors else "Unknown GraphQL error"
                        raise UnraidApiError("GraphQL Error", error_message)
                    
                    return response_json

        except asyncio.TimeoutError as err:
            raise UnraidApiError("Timeout", f"Timeout when connecting to Unraid API: {err}")
        except ClientResponseError as err:
            raise UnraidApiError(str(err.status), f"Error connecting to Unraid API: {err}")
        except Exception as err:
            raise UnraidApiError("Unknown", f"Unknown error: {err}")

    async def get_system_info(self) -> Dict[str, Any]:
        """Get system information."""
        query = """
        query {
            info {
                os {
                    platform
                    distro
                    release
                    uptime
                }
                cpu {
                    manufacturer
                    brand
                    cores
                    threads
                }
                memory {
                    total
                    free
                    used
                }
                versions {
                    unraid
                }
            }
            online
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def get_array_status(self) -> Dict[str, Any]:
        """Get array status."""
        query = """
        query {
            array {
                state
                capacity {
                    disks {
                        free
                        used
                        total
                    }
                }
                parities {
                    id
                    name
                    device
                    size
                    temp
                    status
                    type
                }
                disks {
                    id
                    name
                    device
                    size
                    fsSize
                    fsFree
                    fsUsed
                    fsType
                    temp
                    status
                    type
                    numReads
                    numWrites
                    numErrors
                }
                caches {
                    id
                    name
                    device
                    size
                    temp
                    status
                    type
                }
            }
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def get_docker_containers(self) -> Dict[str, Any]:
        """Get docker containers."""
        query = """
        query {
            dockerContainers {
                id
                names
                image
                state
                status
                autoStart
                created
            }
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def get_vms(self) -> Dict[str, Any]:
        """Get virtual machines."""
        query = """
        query {
            vms {
                domain {
                    uuid
                    name
                    state
                }
            }
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def get_shares(self) -> Dict[str, Any]:
        """Get network shares."""
        query = """
        query {
            shares {
                name
                free
                used
                size
                comment
            }
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def start_array(self) -> Dict[str, Any]:
        """Start array."""
        query = """
        mutation {
            startArray {
                state
            }
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def stop_array(self) -> Dict[str, Any]:
        """Stop array."""
        query = """
        mutation {
            stopArray {
                state
            }
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def start_parity_check(self, correct: bool = False) -> Dict[str, Any]:
        """Start parity check."""
        query = """
        mutation StartParityCheck($correct: Boolean) {
            startParityCheck(correct: $correct)
        }
        """
        variables = {"correct": correct}
        response = await self._send_graphql_request(query, variables)
        return response.get("data", {})

    async def pause_parity_check(self) -> Dict[str, Any]:
        """Pause parity check."""
        query = """
        mutation {
            pauseParityCheck
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def resume_parity_check(self) -> Dict[str, Any]:
        """Resume parity check."""
        query = """
        mutation {
            resumeParityCheck
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def cancel_parity_check(self) -> Dict[str, Any]:
        """Cancel parity check."""
        query = """
        mutation {
            cancelParityCheck
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def reboot(self) -> Dict[str, Any]:
        """Reboot server."""
        query = """
        mutation {
            reboot
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def shutdown(self) -> Dict[str, Any]:
        """Shutdown server."""
        query = """
        mutation {
            shutdown
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def validate_api_connection(self) -> bool:
        """Test if we can authenticate with the API."""
        try:
            await self.get_system_info()
            return True
        except UnraidApiError:
            return False