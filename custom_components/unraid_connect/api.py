"""
API client for the Unraid integration.
"""

from __future__ import annotations

from typing import Any, Final

from gql import Client, gql
from gql.transport.aiohttp import AIOHTTPTransport
from gql.transport.exceptions import TransportQueryError, TransportServerError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import LOGGER

# GraphQL Queries
QUERY_SYSTEM_INFO: Final[
    str
] = """
    query {
        info {
            os {
                platform
                distro
                release
                uptime
                hostname
            }
            cpu {
                manufacturer
                brand
                cores
                threads
                speed
                temperature
                load {
                    currentLoad
                    avgLoad
                }
            }
            memory {
                total
                free
                used
                active
                available
                swapTotal
                swapUsed
                swapFree
            }
            filesystem {
                type
                used
                use
                size
                mount
            }
            baseboard {
                manufacturer
                model
            }
        }
    }
"""

QUERY_ARRAY_STATUS: Final[
    str
] = """
    query {
        array {
            state
            started
            fsSize
            protected
            capacity {
                disks {
                    free
                    used
                    total
                }
                cache {
                    free
                    used
                    total
                }
            }
            disks {
                name
                id
                device
                size
                status
                temp
                numErrors
                interface
                rotational
                serial
                model
            }
            parityCheckActive
            parityCheckProgress
            parityCheckElapsedSec
            parityCheckTotalSec
            parityCheckSpeed
        }
    }
"""

QUERY_DOCKER_STATUS: Final[
    str
] = """
    query {
        dockerContainers {
            id
            names
            state
            status
            image
            autoStart
            created
            ports
            command
            cpuUsage
            memUsage
            memPercent
            netIO {
                rx
                tx
            }
            blockIO {
                read
                write
            }
        }
    }
"""

MUTATION_CONTROL_DOCKER: Final[
    str
] = """
    mutation ControlContainer($id: String!, $action: String!) {
        dockerContainer(id: $id, action: $action) {
            id
            state
        }
    }
"""

MUTATION_CONTROL_ARRAY: Final[
    str
] = """
    mutation ControlArray($operation: String!) {
        array(operation: $operation) {
            state
        }
    }
"""


class UnraidAPIError(Exception):
    """Exception raised for Unraid API errors."""


class UnraidConnectionError(UnraidAPIError):
    """Exception raised when connection to the Unraid API fails."""


class UnraidAuthError(UnraidAPIError):
    """Exception raised when authentication to the Unraid API fails."""


class UnraidAPI:
    """Wrapper class for Unraid GraphQL API."""

    def __init__(self, client: Client):
        """Initialize the API wrapper."""
        self.client = client
        LOGGER.debug("UnraidAPI initialized with GraphQL client")

    @classmethod
    async def create(
        cls, hass, host: str, api_key: str, timeout: int = 10
    ) -> UnraidAPI:
        """Create and initialize an API client."""
        LOGGER.debug("Creating new Unraid API client for %s", host)

        try:
            # Get Home Assistant URL to use as origin
            ha_url = hass.config.api.base_url
            LOGGER.debug("Using Home Assistant URL as origin: %s", ha_url)

            # Create session first
            session = async_get_clientsession(hass, verify_ssl=False)

            # Check if the host looks like a myunraid.net URL
            if "myunraid.net" in host:
                # Use the full URL with https
                if not host.startswith(("http://", "https://")):
                    url = f"https://{host}"
                else:
                    url = host
            else:
                # For local IPs, start with simple format and let redirects handle it
                if not host.startswith(("http://", "https://")):
                    url = f"http://{host}"
                else:
                    url = host

            # Ensure URL ends with /graphql
            if not url.endswith("/graphql"):
                url = f"{url}/graphql" if url.endswith("/") else f"{url}/graphql"

            LOGGER.debug("Attempting to connect to GraphQL endpoint at: %s", url)

            # Configure transport with Home Assistant URL as origin
            transport = AIOHTTPTransport(
                url=url,
                headers={
                    "x-api-key": api_key,
                    "Origin": ha_url,
                    "Referer": ha_url + "/",
                    "User-Agent": "HomeAssistant/UnraidConnect",
                },
            )

            # Explicitly assign session to transport
            transport.session = session

            client = Client(
                transport=transport,
                fetch_schema_from_transport=True,
                execute_timeout=timeout,
            )

            # Test connection
            LOGGER.debug("Testing API connection")
            test_query = gql(
                """
                query {
                    info {
                        os {
                            platform
                        }
                    }
                }
                """
            )
            result = await client.execute_async(test_query)
            LOGGER.debug("GraphQL client initialized successfully: %s", result)

            return cls(client)

        except TransportServerError as err:
            LOGGER.error("Connection error to Unraid API: %s", err)
            # Check if it's a redirect error (302)
            if "302" in str(err):
                LOGGER.warning(
                    "Got a redirect (302). Your server may require using the myunraid.net URL"
                )
            raise UnraidConnectionError(f"Failed to connect to server: {err}") from err
        except TransportQueryError as err:
            if "Unauthorized" in str(err) or "Invalid API key" in str(err):
                LOGGER.error("Authentication error with Unraid API: %s", err)
                raise UnraidAuthError(f"Invalid API key: {err}") from err
            LOGGER.error("Query error with Unraid API: %s", err)
            raise UnraidConnectionError(f"Failed to query API: {err}") from err
        except Exception as err:
            LOGGER.error("Failed to initialize GraphQL client: %s", err, exc_info=True)
            raise UnraidAPIError(f"Unexpected error: {err}") from err

    async def close(self) -> None:
        """Close the API client connection."""
        if hasattr(self.client.transport, "close"):
            LOGGER.debug("Closing GraphQL transport session")
            await self.client.transport.close()

    async def get_system_info(self) -> dict[str, Any]:
        """Get system information."""
        LOGGER.debug("Executing system info query")
        query = gql(QUERY_SYSTEM_INFO)
        try:
            result = await self.client.execute_async(query)
            LOGGER.debug("System info query executed successfully")
            return result["info"]
        except Exception as err:
            LOGGER.error("Error executing system info query: %s", err, exc_info=True)
            raise

    async def get_array_status(self) -> dict[str, Any]:
        """Get array status information."""
        LOGGER.debug("Executing array status query")
        query = gql(QUERY_ARRAY_STATUS)
        try:
            result = await self.client.execute_async(query)
            LOGGER.debug("Array status query executed successfully")
            return result["array"]
        except Exception as err:
            LOGGER.error("Error executing array status query: %s", err, exc_info=True)
            raise

    async def get_docker_status(self) -> list[dict[str, Any]]:
        """Get Docker container status."""
        LOGGER.debug("Executing docker containers query")
        query = gql(QUERY_DOCKER_STATUS)
        try:
            result = await self.client.execute_async(query)
            LOGGER.debug("Docker containers query executed successfully")
            return result["dockerContainers"]
        except Exception as err:
            LOGGER.error(
                "Error executing docker containers query: %s", err, exc_info=True
            )
            raise

    async def control_docker_container(
        self, container_id: str, action: str
    ) -> dict[str, Any]:
        """Control a Docker container."""
        LOGGER.debug(
            "Executing docker container control mutation: %s on %s",
            action,
            container_id,
        )
        mutation = gql(MUTATION_CONTROL_DOCKER)

        variables = {
            "id": container_id,
            "action": action,
        }

        try:
            result = await self.client.execute_async(
                mutation, variable_values=variables
            )
            LOGGER.debug("Docker container control mutation executed successfully")
            return result["dockerContainer"]
        except Exception as err:
            LOGGER.error(
                "Error executing docker container control mutation: %s",
                err,
                exc_info=True,
            )
            raise

    async def control_array(self, operation: str) -> dict[str, Any]:
        """Control the Unraid array."""
        LOGGER.debug("Executing array control mutation: %s", operation)
        mutation = gql(MUTATION_CONTROL_ARRAY)

        variables = {
            "operation": operation,
        }

        try:
            result = await self.client.execute_async(
                mutation, variable_values=variables
            )
            LOGGER.debug("Array control mutation executed successfully")
            return result["array"]
        except Exception as err:
            LOGGER.error(
                "Error executing array control mutation: %s", err, exc_info=True
            )
            raise
