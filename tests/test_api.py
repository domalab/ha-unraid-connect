"""Tests for the Unraid Connect API client."""
import asyncio
from unittest.mock import MagicMock, patch

import aiohttp
import pytest

from custom_components.unraid_connect.api import UnraidApiClient, UnraidApiError


@pytest.fixture
def mock_session():
    """Mock aiohttp ClientSession."""
    session = MagicMock(spec=aiohttp.ClientSession)
    
    # Create mock for post method responses
    mock_post_response = MagicMock()
    mock_post_response.__aenter__.return_value.status = 200
    mock_post_response.__aenter__.return_value.json.return_value = asyncio.Future()
    mock_post_response.__aenter__.return_value.json.return_value.set_result({"data": {"info": {"test": "data"}}})
    mock_post_response.__aenter__.return_value.text.return_value = asyncio.Future()
    mock_post_response.__aenter__.return_value.text.return_value.set_result('{"data": {"info": {"test": "data"}}}')
    
    # Setup 'post' method with the response
    session.post.return_value = mock_post_response
    
    return session


@pytest.mark.asyncio
async def test_api_client_constructor():
    """Test API client constructor initializes correctly."""
    mock_session = MagicMock()
    client = UnraidApiClient(
        host="http://192.168.1.100",
        api_key="test_api_key",
        session=mock_session
    )
    
    assert client.host == "http://192.168.1.100"
    assert client.api_key == "test_api_key"
    assert client.session == mock_session
    assert client.verify_ssl is True
    assert client.redirect_url is None
    assert client.api_url == "http://192.168.1.100/graphql"


@pytest.mark.asyncio
async def test_validate_api_connection_success(mock_session):
    """Test API connection validation success."""
    client = UnraidApiClient(
        host="http://192.168.1.100",
        api_key="test_api_key",
        session=mock_session
    )
    
    # Mock successful response
    mock_response = MagicMock()
    mock_response.__aenter__.return_value.status = 200
    mock_response.__aenter__.return_value.json.return_value = asyncio.Future()
    mock_response.__aenter__.return_value.json.return_value.set_result({"data": {"online": True}})
    mock_response.__aenter__.return_value.text.return_value = asyncio.Future()
    mock_response.__aenter__.return_value.text.return_value.set_result('{"data": {"online": true}}')
    
    mock_session.post.return_value = mock_response
    
    # Test connection validation
    result = await client.validate_api_connection()
    assert result is True
    assert mock_session.post.called


@pytest.mark.asyncio
async def test_validate_api_connection_failure(mock_session):
    """Test API connection validation failure."""
    client = UnraidApiClient(
        host="http://192.168.1.100",
        api_key="invalid_api_key",
        session=mock_session
    )
    
    # Mock error response
    mock_response = MagicMock()
    mock_response.__aenter__.return_value.status = 401
    mock_response.__aenter__.return_value.text.return_value = asyncio.Future()
    mock_response.__aenter__.return_value.text.return_value.set_result('{"error": "Unauthorized"}')
    
    mock_session.post.return_value = mock_response
    
    # Test connection validation
    result = await client.validate_api_connection()
    assert result is False


@pytest.mark.asyncio
async def test_get_system_info(mock_session):
    """Test getting system info."""
    client = UnraidApiClient(
        host="http://192.168.1.100",
        api_key="test_api_key",
        session=mock_session
    )
    
    # Mock successful response
    mock_system_info = {
        "info": {
            "os": {
                "platform": "linux",
                "distro": "Unraid",
                "uptime": "2023-03-06T12:00:00Z"
            },
            "cpu": {
                "manufacturer": "Intel",
                "brand": "Core i7",
                "cores": 8,
                "threads": 16
            },
            "memory": {
                "total": 32000000000,
                "free": 16000000000,
                "used": 16000000000
            },
            "versions": {
                "unraid": "6.10.3",
                "kernel": "5.15",
                "docker": "20.10.12"
            }
        },
        "online": True
    }
    
    mock_response = MagicMock()
    mock_response.__aenter__.return_value.status = 200
    mock_response.__aenter__.return_value.json.return_value = asyncio.Future()
    mock_response.__aenter__.return_value.json.return_value.set_result({"data": mock_system_info})
    mock_response.__aenter__.return_value.text.return_value = asyncio.Future()
    mock_response.__aenter__.return_value.text.return_value.set_result('{"data": ' + str(mock_system_info).replace("'", '"') + '}')
    
    mock_session.post.return_value = mock_response
    
    # Test getting system info
    result = await client.get_system_info()
    
    # Check that the query was sent
    assert mock_session.post.called
    
    # Check that the result is correctly returned
    assert "info" in result
    assert result["info"]["os"]["platform"] == "linux"
    assert result["info"]["cpu"]["manufacturer"] == "Intel"
    assert result["online"] is True