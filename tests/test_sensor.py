"""Tests for the Unraid Connect sensor platform."""
import asyncio
from unittest.mock import MagicMock, patch

import pytest
from homeassistant.components.sensor import SensorStateClass
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
)
from homeassistant.setup import async_setup_component

from custom_components.unraid_connect.api import UnraidApiClient
from custom_components.unraid_connect.const import DOMAIN
from custom_components.unraid_connect.coordinator import UnraidDataUpdateCoordinator
from custom_components.unraid_connect.sensor import (
    UnraidCpuTempSensor,
    UnraidMemoryUsageSensor,
    UnraidUptimeSensor,
    UnraidArraySpaceUsedSensor,
)


@pytest.fixture
def mock_coordinator():
    """Mock a data coordinator with test data."""
    coordinator = MagicMock(spec=UnraidDataUpdateCoordinator)
    
    # Create fake data matching the API response structure
    coordinator.data = {
        "system_info": {
            "info": {
                "os": {
                    "platform": "linux",
                    "distro": "Unraid",
                    "uptime": "2023-03-06T12:00:00Z",
                },
                "cpu": {
                    "manufacturer": "Intel",
                    "brand": "Core i7",
                    "cores": 8,
                    "threads": 16,
                },
                "memory": {
                    "total": 32000000000,
                    "free": 16000000000,
                    "used": 16000000000,
                    "available": 16000000000,
                    "active": 8000000000,
                },
                "versions": {
                    "unraid": "6.10.3",
                    "kernel": "5.15",
                    "docker": "20.10.12",
                },
            },
            "online": True,
            "temperatures": {
                "cpu": 45.5,
                "motherboard": 38.2,
            },
        },
        "array_status": {
            "array": {
                "state": "STARTED",
                "capacity": {
                    "kilobytes": {
                        "free": "10000000",
                        "used": "5000000",
                        "total": "15000000",
                    },
                },
            },
        },
    }
    
    return coordinator


def test_cpu_temp_sensor(mock_coordinator):
    """Test the CPU temperature sensor."""
    # Create the sensor
    sensor = UnraidCpuTempSensor(mock_coordinator, "Unraid Server")
    
    # Test properties
    assert sensor.name == "CPU Temperature"
    assert sensor.native_unit_of_measurement == UnitOfTemperature.CELSIUS
    assert sensor.device_class == "temperature"
    assert sensor.state_class == SensorStateClass.MEASUREMENT
    
    # Test value
    assert sensor.native_value == 45.5
    
    # Test attributes
    attrs = sensor.extra_state_attributes
    assert attrs["cpu_brand"] == "Core i7"
    assert attrs["cpu_cores"] == 8
    assert attrs["cpu_threads"] == 16
    assert attrs["manufacturer"] == "Intel"


def test_memory_usage_sensor(mock_coordinator):
    """Test the memory usage sensor."""
    # Create the sensor
    sensor = UnraidMemoryUsageSensor(mock_coordinator, "Unraid Server")
    
    # Test properties
    assert sensor.name == "Memory Usage"
    assert sensor.native_unit_of_measurement == PERCENTAGE
    assert sensor.state_class == SensorStateClass.MEASUREMENT
    
    # Test value - should be 50% since available/total = 50%
    assert sensor.native_value == 50.0
    
    # Test attributes
    attrs = sensor.extra_state_attributes
    assert "total" in attrs
    assert "used" in attrs
    assert "free" in attrs
    assert "available" in attrs
    assert "active" in attrs


def test_array_space_used_sensor(mock_coordinator):
    """Test the array space used sensor."""
    # Create the sensor
    sensor = UnraidArraySpaceUsedSensor(mock_coordinator, "Unraid Server")
    
    # Test properties
    assert sensor.name == "Array Usage"
    assert sensor.native_unit_of_measurement == PERCENTAGE
    assert sensor.state_class == SensorStateClass.MEASUREMENT
    
    # Test value - should be 33.3% since used/total = 0.33
    # The function rounds to 1 decimal place
    assert sensor.native_value == 33.3
    
    # Test attributes
    attrs = sensor.extra_state_attributes
    assert "used_formatted" in attrs
    assert "used_bytes" in attrs


def test_uptime_sensor(mock_coordinator):
    """Test the uptime sensor."""
    # Create the sensor
    sensor = UnraidUptimeSensor(mock_coordinator, "Unraid Server")
    
    # Test properties
    assert sensor.name == "Uptime"
    assert sensor.device_class is None  # No device class for human-readable uptime
    
    # Test attributes
    attrs = sensor.extra_state_attributes
    assert "boot_time" in attrs