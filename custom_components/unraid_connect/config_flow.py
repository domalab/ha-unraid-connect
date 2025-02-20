"""
Configuration flow for the Unraid integration.
"""

from __future__ import annotations

import re
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_HOST, CONF_API_KEY, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .api import UnraidAPI, UnraidConnectionError, UnraidAuthError
from .const import (
    DOMAIN,
    LOGGER,
    DEFAULT_SCAN_INTERVAL,
    ERROR_CANNOT_CONNECT,
    ERROR_INVALID_AUTH,
    ERROR_UNKNOWN,
)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.TEXT,
            )
        ),
        vol.Required(CONF_API_KEY): selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.PASSWORD,
            )
        ),
        vol.Optional(CONF_NAME): selector.TextSelector(
            selector.TextSelectorConfig(
                type=selector.TextSelectorType.TEXT,
            )
        ),
    }
)

OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(
            CONF_SCAN_INTERVAL,
            default=DEFAULT_SCAN_INTERVAL,
        ): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=10,
                max=300,
                unit_of_measurement="seconds",
                mode=selector.NumberSelectorMode.SLIDER,
                step=5,
            )
        ),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_USER_DATA_SCHEMA with values provided by the user.
    """
    host = data[CONF_HOST]
    api_key = data[CONF_API_KEY]

    # Clean up the host input
    host = host.strip()

    # If it's a myunraid.net address, preserve the full URL
    if "myunraid.net" in host:
        # Just ensure it has the protocol
        if not host.startswith(("http://", "https://")):
            host = f"https://{host}"
    else:
        # For local addresses, simplify
        # Remove http:// or https:// if present
        host = re.sub(r"^https?://", "", host)
        # Remove trailing slash if present
        host = host.rstrip("/")

    try:
        # Initialize API client to validate connection
        api = await UnraidAPI.create(hass, host, api_key)

        # Get system info for the title
        system_info = await api.get_system_info()

        # Extract the system information
        hostname = system_info["os"].get("hostname", host)
        distro = system_info["os"].get("distro", "Unraid")
        release = system_info["os"].get("release", "")

        # Determine a good title for the integration
        if CONF_NAME in data and data[CONF_NAME]:
            title = data[CONF_NAME]
        else:
            title = hostname if hostname else f"Unraid ({host})"

        LOGGER.debug("Successfully connected to Unraid server: %s %s", distro, release)

        # Close the client session
        await api.close()

        # Return info that you want to store in the config entry.
        return {
            "title": title,
            "hostname": hostname,
            "distro": distro,
            "release": release,
            "host": host,  # Store the cleaned host
        }

    except UnraidConnectionError as err:
        LOGGER.warning("Connection error to Unraid API: %s", err)
        raise UnraidConnectError(str(err)) from err
    except UnraidAuthError as err:
        LOGGER.warning("Authentication error with Unraid API: %s", err)
        raise UnraidAuthenticationError(str(err)) from err
    except Exception as err:
        LOGGER.exception("Unexpected exception during Unraid API connection")
        raise err


class UnraidConnectError(Exception):
    """Error to indicate we cannot connect."""


class UnraidAuthenticationError(Exception):
    """Error to indicate authentication failure."""


class UnraidConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Unraid."""

    VERSION = 1

    def __init__(self):
        """Initialize the config flow."""
        self._entry_data = None

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Create the options flow."""
        return UnraidOptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        description_placeholders = {
            "redirect_help": "",
        }

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except UnraidConnectError as err:
                errors["base"] = ERROR_CANNOT_CONNECT
                # If it looks like a redirect issue, give specific advice
                if "302" in str(err) or "redirect" in str(err).lower():
                    description_placeholders["redirect_help"] = (
                        "It appears your server uses Unraid Connect. "
                        "Try using the full myunraid.net URL instead of the local IP address."
                    )
                LOGGER.exception("Connection error: %s", err)
            except UnraidAuthenticationError:
                errors["base"] = ERROR_INVALID_AUTH
            except Exception:  # pylint: disable=broad-except
                LOGGER.exception("Unexpected exception")
                errors["base"] = ERROR_UNKNOWN
            else:
                # Check if this server is already configured
                await self.async_set_unique_id(f"unraid_{info['host']}")
                self._abort_if_unique_id_configured()

                # Create entry with cleaned host value
                user_input[CONF_HOST] = info["host"]

                return self.async_create_entry(
                    title=info["title"],
                    data=user_input,
                    description=f"Unraid {info.get('distro', 'Server')} {info.get('release', '')}".strip(),
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle reauth if API key becomes invalid."""
        self._entry_data = entry_data
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Dialog that informs the user that reauth is required."""
        errors: dict[str, str] = {}
        description_placeholders = {
            "redirect_help": "",
        }

        if user_input is not None:
            try:
                # Validate the new API key
                old_host = self._entry_data[CONF_HOST]
                new_data = {CONF_HOST: old_host, CONF_API_KEY: user_input[CONF_API_KEY]}
                await validate_input(
                    self.hass, new_data
                )  # We don't need the return value

                # Find the existing config entry
                existing_entry = await self.async_set_unique_id(f"unraid_{old_host}")
                if existing_entry:
                    # Update the API key and reload the entry
                    new_data = dict(self._entry_data)
                    new_data[CONF_API_KEY] = user_input[CONF_API_KEY]
                    self.hass.config_entries.async_update_entry(
                        existing_entry,
                        data=new_data,
                    )
                    await self.hass.config_entries.async_reload(existing_entry.entry_id)
                    return self.async_abort(reason="reauth_successful")

                errors["base"] = "entry_not_found"

            except UnraidConnectError as err:
                errors["base"] = ERROR_CANNOT_CONNECT
                # If it looks like a redirect issue, give specific advice
                if "302" in str(err) or "redirect" in str(err).lower():
                    description_placeholders["redirect_help"] = (
                        "It appears your server uses Unraid Connect. "
                        "Try using the full myunraid.net URL."
                    )
            except UnraidAuthenticationError:
                errors["base"] = ERROR_INVALID_AUTH
            except Exception:  # pylint: disable=broad-except
                LOGGER.exception("Unexpected exception")
                errors["base"] = ERROR_UNKNOWN

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_API_KEY): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders=description_placeholders,
        )


class UnraidOptionsFlow(config_entries.OptionsFlow):
    """Handle options for the Unraid integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle options flow."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        scan_interval = self.config_entry.options.get(
            CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
        )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=scan_interval,
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=10,
                            max=300,
                            unit_of_measurement="seconds",
                            mode=selector.NumberSelectorMode.SLIDER,
                            step=5,
                        )
                    ),
                }
            ),
        )