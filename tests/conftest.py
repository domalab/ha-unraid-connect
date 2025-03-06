"""Fixtures for Unraid Connect integration tests."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.const import CONF_API_KEY, CONF_HOST, CONF_NAME
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from custom_components.unraid_connect.const import DOMAIN

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def mock_config_entry():
    """Mock a config entry for Unraid Connect."""
    return {
        CONF_HOST: "http://192.168.1.100",
        CONF_API_KEY: "test_api_key",
        CONF_NAME: "Unraid Server",
    }


@pytest.fixture
def mock_setup_entry():
    """Mock setting up a config entry."""
    with patch(
        "custom_components.unraid_connect.async_setup_entry", return_value=True
    ) as mock_setup:
        yield mock_setup


@pytest.fixture
def mock_api_client():
    """Mock the Unraid API client."""
    with patch("custom_components.unraid_connect.api.UnraidApiClient") as mock_client:
        client = mock_client.return_value
        
        # Mock API responses
        client.validate_api_connection.return_value = asyncio.Future()
        client.validate_api_connection.return_value.set_result(True)
        
        client.get_system_info.return_value = asyncio.Future()
        client.get_system_info.return_value.set_result({
            "info": {
                "os": {"platform": "linux", "distro": "Unraid", "uptime": "2023-03-01T12:00:00Z"},
                "cpu": {"manufacturer": "Intel", "brand": "Core i7", "cores": 8, "threads": 16},
                "memory": {"total": 32000000000, "free": 16000000000, "used": 16000000000},
                "versions": {"unraid": "6.10.2", "kernel": "5.15", "docker": "20.10.0"}
            },
            "online": True
        })
        
        client.get_array_status.return_value = asyncio.Future()
        client.get_array_status.return_value.set_result({
            "array": {
                "state": "STARTED",
                "capacity": {
                    "kilobytes": {
                        "free": "10000000",
                        "used": "5000000",
                        "total": "15000000"
                    },
                    "disks": {
                        "free": "2", 
                        "used": "3",
                        "total": "5"
                    }
                },
                "disks": [
                    {
                        "id": "disk1",
                        "name": "disk1",
                        "device": "sda",
                        "size": 1000000,
                        "status": "DISK_OK",
                        "type": "Data",
                        "temp": 35,
                        "rotational": True,
                        "fsSize": 1000000,
                        "fsFree": 500000,
                        "fsUsed": 500000
                    }
                ],
                "parities": [],
                "caches": []
            }
        })
        
        client.get_docker_containers.return_value = asyncio.Future()
        client.get_docker_containers.return_value.set_result({
            "dockerContainers": [
                {
                    "id": "container1",
                    "names": ["container1"],
                    "image": "image1",
                    "state": "RUNNING",
                    "status": "Up 1 day",
                    "autoStart": True
                }
            ]
        })
        
        client.get_vms.return_value = asyncio.Future()
        client.get_vms.return_value.set_result({
            "vms": {
                "domain": [
                    {
                        "uuid": "vm1",
                        "name": "vm1",
                        "state": "RUNNING"
                    }
                ]
            }
        })
        
        client.get_shares.return_value = asyncio.Future()
        client.get_shares.return_value.set_result([
            {
                "name": "share1",
                "comment": "test share",
                "free": 5000000,
                "size": 0,
                "used": 5000000
            }
        ])
        
        yield client


@pytest.fixture
async def mock_unraid_integration(hass: HomeAssistant, mock_api_client):
    """Set up the Unraid integration in Home Assistant."""
    await async_setup_component(hass, DOMAIN, {
        DOMAIN: {
            CONF_HOST: "http://192.168.1.100",
            CONF_API_KEY: "test_api_key",
            CONF_NAME: "Unraid Server",
        }
    })
    await hass.async_block_till_done()
    return DOMAIN