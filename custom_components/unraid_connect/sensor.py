"""Sensor platform for Unraid integration."""
import logging
from typing import Any, Dict, List, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    TEMP_CELSIUS,
    CONF_HOST,
    UnitOfDataSize,
    UnitOfInformation,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ARRAY_STATE_STARTED,
    ATTR_CPU_BRAND,
    ATTR_CPU_CORES,
    ATTR_CPU_THREADS,
    ATTR_DISK_FREE,
    ATTR_DISK_FS_TYPE,
    ATTR_DISK_NAME,
    ATTR_DISK_SERIAL,
    ATTR_DISK_SIZE,
    ATTR_DISK_TEMP,
    ATTR_DISK_TYPE,
    ATTR_DISK_USED,
    ATTR_CONTAINER_IMAGE,
    ATTR_CONTAINER_STATUS,
    ATTR_UPTIME,
    DOMAIN,
    ICON_ARRAY,
    ICON_CPU,
    ICON_DISK,
    ICON_MEMORY,
    ICON_TEMPERATURE,
)
from .coordinator import UnraidDataUpdateCoordinator
from .entity import (
    UnraidArrayEntity,
    UnraidDiskEntity,
    UnraidShareEntity,
    UnraidSystemEntity,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Unraid sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    name = hass.data[DOMAIN][entry.entry_id]["name"]
    host = entry.data[CONF_HOST]

    entities = []

    # Add system sensors
    entities.append(UnraidSystemStateSensor(coordinator, name))
    entities.append(UnraidCpuTempSensor(coordinator, name))
    entities.append(UnraidMemoryUsageSensor(coordinator, name))
    entities.append(UnraidUptimeSensor(coordinator, name))

    # Add array sensors
    entities.append(UnraidArrayStateSensor(coordinator, name))
    entities.append(UnraidArraySpaceUsedSensor(coordinator, name))
    entities.append(UnraidArraySpaceFreeSensor(coordinator, name))
    entities.append(UnraidArraySpaceTotalSensor(coordinator, name))

    # Get array data for disks
    array_data = coordinator.data.get("array_status", {}).get("array", {})

    # Add parity disks
    parity_disks = array_data.get("parities", [])
    for disk in parity_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            entities.append(
                UnraidDiskTempSensor(coordinator, name, disk_id, disk_name, "Parity")
            )

    # Add data disks
    data_disks = array_data.get("disks", [])
    for disk in data_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            entities.append(
                UnraidDiskTempSensor(coordinator, name, disk_id, disk_name, "Data")
            )
            entities.append(
                UnraidDiskSpaceUsedSensor(coordinator, name, disk_id, disk_name)
            )
            entities.append(
                UnraidDiskSpaceFreeSensor(coordinator, name, disk_id, disk_name)
            )

    # Add cache disks
    cache_disks = array_data.get("caches", [])
    for disk in cache_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            entities.append(
                UnraidDiskTempSensor(coordinator, name, disk_id, disk_name, "Cache")
            )

    # Add shares
    shares_data = coordinator.data.get("shares", {}).get("shares", [])
    for share in shares_data:
        if share.get("name"):
            share_name = share.get("name")
            entities.append(UnraidShareSpaceUsedSensor(coordinator, name, share_name))
            entities.append(UnraidShareSpaceFreeSensor(coordinator, name, share_name))

    async_add_entities(entities)


class UnraidSystemStateSensor(UnraidSystemEntity, SensorEntity):
    """Sensor for Unraid system state."""

    _attr_name = "System State"
    _attr_icon = ICON_CPU

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        online = self.coordinator.data.get("system_info", {}).get("online", False)
        return "Online" if online else "Offline"

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            info = self.coordinator.data.get("system_info", {}).get("info", {})
            cpu_info = info.get("cpu", {})
            os_info = info.get("os", {})
            
            return {
                ATTR_CPU_BRAND: cpu_info.get("brand", "Unknown"),
                ATTR_CPU_CORES: cpu_info.get("cores", 0),
                ATTR_CPU_THREADS: cpu_info.get("threads", 0),
                "os_platform": os_info.get("platform", "Unknown"),
                "os_distro": os_info.get("distro", "Unknown"),
                "os_release": os_info.get("release", "Unknown"),
                "unraid_version": info.get("versions", {}).get("unraid", "Unknown"),
            }
        except (KeyError, AttributeError, TypeError):
            return {}


class UnraidCpuTempSensor(UnraidSystemEntity, SensorEntity):
    """Sensor for Unraid CPU temperature."""

    _attr_name = "CPU Temperature"
    _attr_icon = ICON_TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of the sensor."""
        try:
            cpu_info = self.coordinator.data.get("system_info", {}).get("info", {}).get("cpu", {})
            # Temperature might be in different formats depending on the system
            # This is just a placeholder - you would need to adjust based on actual data structure
            return cpu_info.get("temperature")
        except (KeyError, AttributeError, TypeError):
            return None


class UnraidMemoryUsageSensor(UnraidSystemEntity, SensorEntity):
    """Sensor for Unraid memory usage."""

    _attr_name = "Memory Usage"
    _attr_icon = ICON_MEMORY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of the sensor."""
        try:
            memory = self.coordinator.data.get("system_info", {}).get("info", {}).get("memory", {})
            total = memory.get("total", 0)
            used = memory.get("used", 0)
            
            if total > 0:
                return round((used / total) * 100, 2)
            return 0
        except (KeyError, AttributeError, TypeError, ZeroDivisionError):
            return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            memory = self.coordinator.data.get("system_info", {}).get("info", {}).get("memory", {})
            
            return {
                "total": self._format_memory_size(memory.get("total", 0)),
                "used": self._format_memory_size(memory.get("used", 0)),
                "free": self._format_memory_size(memory.get("free", 0)),
            }
        except (KeyError, AttributeError, TypeError):
            return {}
            
    def _format_memory_size(self, size_bytes: int) -> str:
        """Format memory size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.2f} KB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024 ** 2):.2f} MB"
        else:
            return f"{size_bytes / (1024 ** 3):.2f} GB"


class UnraidUptimeSensor(UnraidSystemEntity, SensorEntity):
    """Sensor for Unraid uptime."""

    _attr_name = "Uptime"
    _attr_icon = ICON_SERVER
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    @property
    def native_value(self) -> Optional[str]:
        """Return the state of the sensor."""
        try:
            uptime = self.coordinator.data.get("system_info", {}).get("info", {}).get("os", {}).get("uptime")
            return uptime
        except (KeyError, AttributeError, TypeError):
            return None


class UnraidArrayStateSensor(UnraidArrayEntity, SensorEntity):
    """Sensor for Unraid array state."""

    _attr_name = "Array State"
    _attr_icon = ICON_ARRAY

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        try:
            array_state = self.coordinator.data.get("array_status", {}).get("array", {}).get("state", "Unknown")
            return array_state
        except (KeyError, AttributeError, TypeError):
            return "Unknown"


class UnraidArraySpaceUsedSensor(UnraidArrayEntity, SensorEntity):
    """Sensor for Unraid array space used."""

    _attr_name = "Array Space Used"
    _attr_icon = ICON_DISK
    _attr_native_unit_of_measurement = UnitOfInformation.KIBIBYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Optional[int]:
        """Return the state of the sensor."""
        try:
            used = self.coordinator.data.get("array_status", {}).get("array", {}).get("capacity", {}).get("disks", {}).get("used", "0")
            return int(used) if used else 0
        except (KeyError, AttributeError, TypeError, ValueError):
            return None


class UnraidArraySpaceFreeSensor(UnraidArrayEntity, SensorEntity):
    """Sensor for Unraid array space free."""

    _attr_name = "Array Space Free"
    _attr_icon = ICON_DISK
    _attr_native_unit_of_measurement = UnitOfInformation.KIBIBYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Optional[int]:
        """Return the state of the sensor."""
        try:
            free = self.coordinator.data.get("array_status", {}).get("array", {}).get("capacity", {}).get("disks", {}).get("free", "0")
            return int(free) if free else 0
        except (KeyError, AttributeError, TypeError, ValueError):
            return None


class UnraidArraySpaceTotalSensor(UnraidArrayEntity, SensorEntity):
    """Sensor for Unraid array space total."""

    _attr_name = "Array Space Total"
    _attr_icon = ICON_DISK
    _attr_native_unit_of_measurement = UnitOfInformation.KIBIBYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_value(self) -> Optional[int]:
        """Return the state of the sensor."""
        try:
            total = self.coordinator.data.get("array_status", {}).get("array", {}).get("capacity", {}).get("disks", {}).get("total", "0")
            return int(total) if total else 0
        except (KeyError, AttributeError, TypeError, ValueError):
            return None


class UnraidDiskTempSensor(UnraidDiskEntity, SensorEntity):
    """Sensor for Unraid disk temperature."""

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_TEMPERATURE

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        disk_id: str,
        disk_name: str,
        disk_type: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "temperature", disk_id, disk_type)
        self._disk_name = disk_name
        self._attr_name = f"{disk_name} Temperature"

    @property
    def native_value(self) -> Optional[int]:
        """Return the state of the sensor."""
        try:
            array_data = self.coordinator.data.get("array_status", {}).get("array", {})
            
            # Look in different disk arrays based on type
            if self._disk_type == "Parity":
                disks = array_data.get("parities", [])
            elif self._disk_type == "Cache":
                disks = array_data.get("caches", [])
            else:
                disks = array_data.get("disks", [])
                
            for disk in disks:
                if disk.get("id") == self._disk_id:
                    return disk.get("temp")
            
            return None
        except (KeyError, AttributeError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            array_data = self.coordinator.data.get("array_status", {}).get("array", {})
            
            # Look in different disk arrays based on type
            if self._disk_type == "Parity":
                disks = array_data.get("parities", [])
            elif self._disk_type == "Cache":
                disks = array_data.get("caches", [])
            else:
                disks = array_data.get("disks", [])
                
            for disk in disks:
                if disk.get("id") == self._disk_id:
                    return {
                        ATTR_DISK_NAME: disk.get("name"),
                        ATTR_DISK_TYPE: self._disk_type,
                        ATTR_DISK_SIZE: disk.get("size"),
                        "status": disk.get("status"),
                    }
            
            return {}
        except (KeyError, AttributeError, TypeError):
            return {}


class UnraidDiskSpaceUsedSensor(UnraidDiskEntity, SensorEntity):
    """Sensor for Unraid disk space used."""

    _attr_native_unit_of_measurement = UnitOfInformation.KIBIBYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_DISK

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        disk_id: str,
        disk_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "space_used", disk_id, "Data")
        self._disk_name = disk_name
        self._attr_name = f"{disk_name} Space Used"

    @property
    def native_value(self) -> Optional[int]:
        """Return the state of the sensor."""
        try:
            disks = self.coordinator.data.get("array_status", {}).get("array", {}).get("disks", [])
            
            for disk in disks:
                if disk.get("id") == self._disk_id:
                    return disk.get("fsUsed", 0)
            
            return None
        except (KeyError, AttributeError, TypeError):
            return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            disks = self.coordinator.data.get("array_status", {}).get("array", {}).get("disks", [])
            
            for disk in disks:
                if disk.get("id") == self._disk_id:
                    return {
                        ATTR_DISK_NAME: disk.get("name"),
                        ATTR_DISK_TYPE: "Data",
                        ATTR_DISK_SIZE: disk.get("size"),
                        ATTR_DISK_FREE: disk.get("fsFree"),
                        ATTR_DISK_FS_TYPE: disk.get("fsType"),
                    }
            
            return {}
        except (KeyError, AttributeError, TypeError):
            return {}


class UnraidDiskSpaceFreeSensor(UnraidDiskEntity, SensorEntity):
    """Sensor for Unraid disk space free."""

    _attr_native_unit_of_measurement = UnitOfInformation.KIBIBYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_DISK

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        disk_id: str,
        disk_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "space_free", disk_id, "Data")
        self._disk_name = disk_name
        self._attr_name = f"{disk_name} Space Free"

    @property
    def native_value(self) -> Optional[int]:
        """Return the state of the sensor."""
        try:
            disks = self.coordinator.data.get("array_status", {}).get("array", {}).get("disks", [])
            
            for disk in disks:
                if disk.get("id") == self._disk_id:
                    return disk.get("fsFree", 0)
            
            return None
        except (KeyError, AttributeError, TypeError):
            return None


class UnraidShareSpaceUsedSensor(UnraidShareEntity, SensorEntity):
    """Sensor for Unraid share space used."""

    _attr_native_unit_of_measurement = UnitOfInformation.KIBIBYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_DISK

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        share_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "space_used", share_name)
        self._attr_name = f"Share {share_name} Space Used"

    @property
    def native_value(self) -> Optional[int]:
        """Return the state of the sensor."""
        try:
            shares = self.coordinator.data.get("shares", {}).get("shares", [])
            
            for share in shares:
                if share.get("name") == self._share_name:
                    return share.get("used", 0)
            
            return None
        except (KeyError, AttributeError, TypeError):
            return None


class UnraidShareSpaceFreeSensor(UnraidShareEntity, SensorEntity):
    """Sensor for Unraid share space free."""

    _attr_native_unit_of_measurement = UnitOfInformation.KIBIBYTES
    _attr_device_class = SensorDeviceClass.DATA_SIZE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_DISK

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        share_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "space_free", share_name)
        self._attr_name = f"Share {share_name} Space Free"

    @property
    def native_value(self) -> Optional[int]:
        """Return the state of the sensor."""
        try:
            shares = self.coordinator.data.get("shares", {}).get("shares", [])
            
            for share in shares:
                if share.get("name") == self._share_name:
                    return share.get("free", 0)
            
            return None
        except (KeyError, AttributeError, TypeError):
            return None