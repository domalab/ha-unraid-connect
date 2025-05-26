"""GraphQL client for Unraid API."""

from __future__ import annotations

import json
import logging
from typing import Any

import aiohttp
from aiohttp import ClientSession

from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

_LOGGER = logging.getLogger(__name__)


class UnraidGraphQLClient:
    """GraphQL client for Unraid API."""

    def __init__(
        self,
        hass: HomeAssistant,
        server_url: str,
        api_key: str,
    ) -> None:
        """Initialize the client."""
        self.hass = hass
        self.server_url = server_url
        self.api_key = api_key
        self.graphql_url = f"{server_url}/graphql"
        self.session: ClientSession | None = None

    async def _get_session(self) -> ClientSession:
        """Get the aiohttp session."""
        if self.session is None:
            self.session = async_get_clientsession(self.hass)
        return self.session

    async def execute(
        self, query: str, variables: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Execute a GraphQL query."""
        session = await self._get_session()

        # Prepare the request payload
        payload = {
            "query": query,
            "variables": variables or {},
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }

        try:
            async with session.post(
                self.graphql_url, json=payload, headers=headers
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    _LOGGER.error(
                        "GraphQL request failed with status %s: %s",
                        response.status,
                        error_text,
                    )
                    return {
                        "errors": [
                            {"message": f"HTTP error {response.status}: {error_text}"}
                        ]
                    }

                # Parse the response as text first to handle large integers
                response_text = await response.text()

                # Custom JSON parsing to handle large integers
                try:
                    # Replace large integers with strings to avoid precision loss
                    # This is a workaround for the 32-bit integer limitation in JavaScript
                    return json.loads(
                        response_text,
                        parse_int=lambda x: str(x) if int(x) > 2**31 - 1 else int(x),
                    )
                except json.JSONDecodeError as err:
                    _LOGGER.error("Failed to parse GraphQL response: %s", err)
                    return {"errors": [{"message": f"JSON parse error: {err}"}]}

        except aiohttp.ClientError as err:
            _LOGGER.error("GraphQL request failed: %s", err)
            return {"errors": [{"message": f"Request error: {err}"}]}
        except TimeoutError:
            _LOGGER.error("GraphQL request timed out")
            return {"errors": [{"message": "Request timed out"}]}
