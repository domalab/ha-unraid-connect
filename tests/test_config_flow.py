"""Tests for the Unraid Connect config flow."""
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_NAME, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant

from custom_components.unraid_connect.config_flow import CannotConnect, InvalidAuth
from custom_components.unraid_connect.const import DOMAIN, DEFAULT_NAME, DEFAULT_SCAN_INTERVAL


@pytest.fixture(autouse=True)
def mock_api_client():
    """Mock the API client."""
    with patch("custom_components.unraid_connect.config_flow.UnraidApiClient") as mock_client:
        client = mock_client.return_value
        client.validate_api_connection = AsyncMock()
        yield client


async def test_form_user(hass: HomeAssistant, mock_api_client):
    """Test we get the form."""
    # Set up the user step form
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == "form"
    assert result["errors"] == {}

    # Set successful validation
    mock_api_client.validate_api_connection.return_value = True
    
    # Test form submission
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "http://192.168.1.100",
            CONF_API_KEY: "test_api_key",
            CONF_NAME: "Test Server",
        },
    )

    assert result["type"] == "create_entry"
    assert result["title"] == "Test Server"
    assert result["data"] == {
        CONF_HOST: "http://192.168.1.100",
        CONF_API_KEY: "test_api_key",
        CONF_NAME: "Test Server",
        CONF_SCAN_INTERVAL: DEFAULT_SCAN_INTERVAL,
    }


async def test_form_invalid_auth(hass: HomeAssistant, mock_api_client):
    """Test we handle invalid auth."""
    # Set authentication failure
    mock_api_client.validate_api_connection.side_effect = InvalidAuth
    
    # Start config flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Test form submission with invalid auth
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "http://192.168.1.100",
            CONF_API_KEY: "wrong_api_key",
            CONF_NAME: "Test Server",
        },
    )

    # Verify error is shown
    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_form_connection_error(hass: HomeAssistant, mock_api_client):
    """Test we handle connection error."""
    # Set connection failure
    mock_api_client.validate_api_connection.side_effect = CannotConnect
    
    # Start config flow
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    # Test form submission with connection error
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_HOST: "http://192.168.1.100",
            CONF_API_KEY: "test_api_key",
            CONF_NAME: "Test Server",
        },
    )

    # Verify error is shown
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}