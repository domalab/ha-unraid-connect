"""Sensor platform for Unraid integration."""
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
import dateutil.parser

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
    EntityCategory,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    CONF_HOST,
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
    DOMAIN as INTEGRATION_DOMAIN,
    ICON_ARRAY,
    ICON_CPU,
    ICON_DISK,
    ICON_MEMORY,
    ICON_SERVER,
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
    coordinator = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["coordinator"]
    name = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["name"]
    host = entry.data[CONF_HOST]

    entities = []

    # Add system sensors
    entities.append(UnraidSystemStateSensor(coordinator, name))
    entities.append(UnraidCpuTempSensor(coordinator, name))
    entities.append(UnraidMotherboardTempSensor(coordinator, name))
    entities.append(UnraidMemoryUsageSensor(coordinator, name))
    entities.append(UnraidUptimeSensor(coordinator, name))
    
    # Add flash drive usage sensor (includes logs)
    if coordinator.data.get("array_status", {}).get("flash"):
        entities.append(UnraidFlashUsageSensor(coordinator, name))

    # Add array sensors
    entities.append(UnraidArrayStateSensor(coordinator, name))
    entities.append(UnraidArraySpaceUsedSensor(coordinator, name))
    entities.append(UnraidArraySpaceFreeSensor(coordinator, name))
    entities.append(UnraidArraySpaceTotalSensor(coordinator, name))

    # Get array data for disks
    array_data = coordinator.data.get("array_status", {}).get("array", {})

    # Add data disks
    data_disks = array_data.get("disks", [])
    for disk in data_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            disk_type = "Data"
            
            # Add space sensors for all disks
            entities.append(
                UnraidDiskSpaceUsedSensor(coordinator, name, disk_id, disk_name)
            )
            entities.append(
                UnraidDiskSpaceFreeSensor(coordinator, name, disk_id, disk_name)
            )
            
            # Always create temperature sensors for all disks, but mark them as disabled by default
            # This ensures they appear in the UI but won't query temperatures unless explicitly enabled
            # The sensor implementation will handle standby disks properly
            entities.append(
                UnraidDiskTempSensor(coordinator, name, disk_id, disk_name, disk_type)
            )

    # Add parity disks
    parity_disks = array_data.get("parities", [])
    for disk in parity_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            disk_type = "Parity"
            
            # Add space sensors for parity disks
            entities.append(
                UnraidDiskSpaceUsedSensor(coordinator, name, disk_id, disk_name)
            )
            entities.append(
                UnraidDiskSpaceFreeSensor(coordinator, name, disk_id, disk_name)
            )
            
            # Always create temperature sensors for parity disks, but mark them as disabled by default
            # This ensures they appear in the UI but won't query temperatures unless explicitly enabled
            entities.append(
                UnraidDiskTempSensor(coordinator, name, disk_id, disk_name, disk_type)
            )
            
    # Add cache disks
    cache_disks = array_data.get("caches", [])
    for disk in cache_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            disk_type = "Cache"
            
            # Add space sensors for cache drives
            entities.append(
                UnraidDiskSpaceUsedSensor(coordinator, name, disk_id, disk_name)
            )
            entities.append(
                UnraidDiskSpaceFreeSensor(coordinator, name, disk_id, disk_name)
            )
            
            # For cache disks (typically SSDs), we can enable temperature sensors by default
            # since they don't have spindown concerns
            rotational = disk.get("rotational", False)  # Default to False for cache drives as they're typically SSDs
            temp_sensor = UnraidDiskTempSensor(coordinator, name, disk_id, disk_name, disk_type)
            if not rotational:
                # Override the default disabled state for non-rotational drives
                temp_sensor._attr_entity_registry_enabled_default = True
            entities.append(temp_sensor)

    # Add shares
    shares_data = coordinator.data.get("shares", [])
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
    _attr_entity_category = EntityCategory.DIAGNOSTIC 

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "state")

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

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "temperature")

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of the sensor."""
        try:
            # Check the most likely place first - the temperatures object from our enhanced query
            temperatures = self.coordinator.data.get("system_info", {}).get("temperatures", {})
            if temperatures:
                # First try to get the CPU temperature directly
                if "cpu" in temperatures and temperatures["cpu"] is not None:
                    try:
                        return round(float(temperatures["cpu"]), 1)
                    except (ValueError, TypeError):
                        pass
                
                # Next, try to get from sensors array if available
                sensors = temperatures.get("sensors", [])
                for sensor in sensors:
                    name = sensor.get("name", "").lower()
                    if "cpu" in name or "processor" in name:
                        try:
                            return round(float(sensor.get("value", 0)), 1)
                        except (ValueError, TypeError):
                            pass
            
            # Try to get CPU temperature from other potential sources
            # From the CPU object directly if it exists (older API versions)
            cpu_info = self.coordinator.data.get("system_info", {}).get("info", {}).get("cpu", {})
            if "temperature" in cpu_info and cpu_info["temperature"] is not None:
                try:
                    return round(float(cpu_info["temperature"]), 1)
                except (ValueError, TypeError):
                    pass
                
            # Let's check if we have temperature data in a separate temps structure
            temps = self.coordinator.data.get("system_info", {}).get("info", {}).get("temps", {})
            if temps:
                # Look for CPU temperature in temps
                for temp_item in temps:
                    if "cpu" in temp_item.get("name", "").lower():
                        try:
                            return round(float(temp_item.get("temp", 0)), 1)
                        except (ValueError, TypeError):
                            pass
                        
            # If we still don't have it, let's try one more place where it might be
            system_data = self.coordinator.data.get("system_info", {})
            if "cpuTemperature" in system_data:
                try:
                    return round(float(system_data["cpuTemperature"]), 1)
                except (ValueError, TypeError):
                    pass
                
            # No valid temperature found
            return None
        except (KeyError, AttributeError, TypeError, ValueError):
            return None
            
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            cpu_info = self.coordinator.data.get("system_info", {}).get("info", {}).get("cpu", {})
            attributes = {
                ATTR_CPU_BRAND: cpu_info.get("brand", "Unknown"),
                ATTR_CPU_CORES: cpu_info.get("cores", 0),
                ATTR_CPU_THREADS: cpu_info.get("threads", 0),
                "manufacturer": cpu_info.get("manufacturer", "Unknown"),
            }
            
            # Add sensor information if available
            temperatures = self.coordinator.data.get("system_info", {}).get("temperatures", {})
            if temperatures and "sensors" in temperatures:
                cpu_sensors = []
                for sensor in temperatures["sensors"]:
                    if "cpu" in sensor.get("name", "").lower() or "processor" in sensor.get("name", "").lower():
                        cpu_sensors.append({
                            "name": sensor.get("name", "Unknown"),
                            "adapter": sensor.get("adapter", "Unknown"),
                            "value": sensor.get("value")
                        })
                
                if cpu_sensors:
                    attributes["sensors"] = cpu_sensors
            
            return attributes
        except (KeyError, AttributeError, TypeError):
            return {}


class UnraidMotherboardTempSensor(UnraidSystemEntity, SensorEntity):
    """Sensor for Unraid motherboard temperature."""

    _attr_name = "Motherboard Temperature"
    _attr_icon = ICON_TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "mb_temperature")

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of the sensor."""
        try:
            # Check the temperatures object from our enhanced query
            temperatures = self.coordinator.data.get("system_info", {}).get("temperatures", {})
            if temperatures:
                # First try to get the motherboard temperature directly
                if "motherboard" in temperatures and temperatures["motherboard"] is not None:
                    try:
                        return round(float(temperatures["motherboard"]), 1)
                    except (ValueError, TypeError):
                        pass
                
                # Try to get from the main temperature as fallback
                if "main" in temperatures and temperatures["main"] is not None:
                    try:
                        return round(float(temperatures["main"]), 1)
                    except (ValueError, TypeError):
                        pass
                
                # Next, try to get from sensors array if available
                sensors = temperatures.get("sensors", [])
                for sensor in sensors:
                    name = sensor.get("name", "").lower()
                    # Look for common motherboard temperature sensor names
                    if ("motherboard" in name or 
                        "system" in name or
                        "mb" in name or
                        "board" in name):
                        try:
                            return round(float(sensor.get("value", 0)), 1)
                        except (ValueError, TypeError):
                            pass
            
            # Try the system temperature as a fallback
            system_data = self.coordinator.data.get("system_info", {})
            if "systemTemperature" in system_data:
                try:
                    return round(float(system_data["systemTemperature"]), 1)
                except (ValueError, TypeError):
                    pass
                
            # No valid temperature found
            return None
        except (KeyError, AttributeError, TypeError, ValueError):
            return None
            
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            attributes = {}
            
            # Add sensor information if available
            temperatures = self.coordinator.data.get("system_info", {}).get("temperatures", {})
            if temperatures and "sensors" in temperatures:
                mb_sensors = []
                for sensor in temperatures["sensors"]:
                    name = sensor.get("name", "").lower()
                    if ("motherboard" in name or 
                        "system" in name or
                        "mb" in name or
                        "board" in name):
                        mb_sensors.append({
                            "name": sensor.get("name", "Unknown"),
                            "adapter": sensor.get("adapter", "Unknown"),
                            "value": sensor.get("value")
                        })
                
                if mb_sensors:
                    attributes["sensors"] = mb_sensors
            
            return attributes
        except (KeyError, AttributeError, TypeError):
            return {}


class UnraidMemoryUsageSensor(UnraidSystemEntity, SensorEntity):
    """Sensor for Unraid memory usage."""

    _attr_name = "Memory Usage"
    _attr_icon = ICON_MEMORY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "memory_usage")

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of the sensor."""
        try:
            memory = self.coordinator.data.get("system_info", {}).get("info", {}).get("memory", {})
            total = memory.get("total", 0)
            # Use available memory as free for more accurate usage calculation
            # (available accounts for buffer/cache that can be reclaimed)
            available = memory.get("available", memory.get("free", 0))
            
            if total > 0:
                used_percent = 100 - (available / total * 100)  # Calculate based on available memory
                return round(used_percent, 1)
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
                "available": self._format_memory_size(memory.get("available", 0)),
                "active": self._format_memory_size(memory.get("active", 0)),
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
        elif size_bytes < 1024 ** 4:
            return f"{size_bytes / (1024 ** 3):.2f} GB"
        else:
            return f"{size_bytes / (1024 ** 4):.2f} TB"


class UnraidUptimeSensor(UnraidSystemEntity, SensorEntity):
    """Sensor for Unraid uptime."""

    _attr_name = "Uptime"
    _attr_icon = ICON_SERVER
    _attr_device_class = None  # Changed from TIMESTAMP to display a formatted string
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "uptime")

    @property
    def native_value(self) -> Optional[str]:
        """Return the state of the sensor as a human-readable duration."""
        try:
            uptime_str = self.coordinator.data.get("system_info", {}).get("info", {}).get("os", {}).get("uptime")
            if uptime_str:
                # Parse the ISO 8601 datetime string to a datetime object with timezone
                boot_time = dateutil.parser.parse(uptime_str)
                # Calculate duration from boot time to now
                now = datetime.now(boot_time.tzinfo)
                uptime_duration = now - boot_time
                
                # Format the duration in a human-readable way
                return self._format_timedelta(uptime_duration)
            return None
        except (KeyError, AttributeError, TypeError, ValueError):
            return None
            
    def _format_timedelta(self, duration):
        """Format timedelta into a human-readable string."""
        days = duration.days
        hours, remainder = divmod(duration.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days} {'day' if days == 1 else 'days'}")
        if hours > 0:
            parts.append(f"{hours} {'hour' if hours == 1 else 'hours'}")
        if minutes > 0:
            parts.append(f"{minutes} {'minute' if minutes == 1 else 'minutes'}")
        if seconds > 0 or not parts:  # Include seconds if it's the only component
            parts.append(f"{seconds} {'second' if seconds == 1 else 'seconds'}")
            
        return ", ".join(parts)
    
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            uptime_str = self.coordinator.data.get("system_info", {}).get("info", {}).get("os", {}).get("uptime")
            if uptime_str:
                # Store the original ISO timestamp in the attributes
                boot_time = dateutil.parser.parse(uptime_str)
                now = datetime.now(boot_time.tzinfo)
                uptime_duration = now - boot_time
                
                return {
                    "boot_time": uptime_str,
                    "days": uptime_duration.days,
                    "hours": uptime_duration.seconds // 3600,
                    "minutes": (uptime_duration.seconds % 3600) // 60,
                    "seconds": uptime_duration.seconds % 60,
                    "total_seconds": uptime_duration.total_seconds()
                }
            return {}
        except (KeyError, AttributeError, TypeError, ValueError):
            return {}


class UnraidArrayStateSensor(UnraidArrayEntity, SensorEntity):
    """Sensor for Unraid array state."""

    _attr_name = "Array State"
    _attr_icon = ICON_ARRAY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "state")

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

    _attr_name = "Array Usage"
    _attr_icon = ICON_DISK
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "space_used")

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of the sensor as a percentage."""
        try:
            capacity = self.coordinator.data.get("array_status", {}).get("array", {}).get("capacity", {}).get("kilobytes", {})
            free = int(capacity.get("free", "0")) if capacity.get("free") else 0
            total = int(capacity.get("total", "0")) if capacity.get("total") else 0
            
            if total > 0:
                used = total - free
                return round((used / total) * 100, 1)
            return 0
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return None
            
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            capacity = self.coordinator.data.get("array_status", {}).get("array", {}).get("capacity", {}).get("kilobytes", {})
            used_kib = int(capacity.get("used", "0")) if capacity.get("used") else 0
            used_bytes = used_kib * 1024
            
            return {
                "used_bytes": used_bytes,
                "used_formatted": self._format_size(used_bytes),
            }
        except (KeyError, AttributeError, TypeError, ValueError):
            return {}
            
    def _format_size(self, size_bytes: int) -> str:
        """Format size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.2f} KiB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024 ** 2):.2f} MiB"
        elif size_bytes < 1024 ** 4:
            return f"{size_bytes / (1024 ** 3):.2f} GiB"
        else:
            return f"{size_bytes / (1024 ** 4):.2f} TiB"


class UnraidArraySpaceFreeSensor(UnraidArrayEntity, SensorEntity):
    """Sensor for Unraid array space free."""

    _attr_name = "Array Free Space"
    _attr_icon = ICON_DISK
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "space_free")

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of the sensor as a percentage."""
        try:
            capacity = self.coordinator.data.get("array_status", {}).get("array", {}).get("capacity", {})
            free = int(capacity.get("free", "0")) if capacity.get("free") else 0
            total = int(capacity.get("total", "0")) if capacity.get("total") else 0
            
            if total > 0:
                # Return free space as percentage
                return round((free / total) * 100, 1)
            return 0
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return None
            
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            capacity = self.coordinator.data.get("array_status", {}).get("array", {}).get("capacity", {})
            free_kib = int(capacity.get("free", "0")) if capacity.get("free") else 0
            free_bytes = free_kib * 1024
            
            return {
                "free_bytes": free_bytes,
                "free_formatted": self._format_size(free_bytes),
            }
        except (KeyError, AttributeError, TypeError, ValueError):
            return {}
            
    def _format_size(self, size_bytes: int) -> str:
        """Format size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.2f} KiB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024 ** 2):.2f} MiB"
        elif size_bytes < 1024 ** 4:
            return f"{size_bytes / (1024 ** 3):.2f} GiB"
        else:
            return f"{size_bytes / (1024 ** 4):.2f} TiB"


class UnraidArraySpaceTotalSensor(UnraidArrayEntity, SensorEntity):
    """Sensor for Unraid array space total."""

    _attr_name = "Array Total Space"
    _attr_icon = ICON_DISK
    _attr_native_unit_of_measurement = None  # Shows formatted string instead
    _attr_device_class = None
    _attr_state_class = None  # Remove measurement class for formatted string

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "space_total")

    @property
    def native_value(self) -> Optional[str]:
        """Return the state of the sensor as a formatted string."""
        try:
            total_kib = self.coordinator.data.get("array_status", {}).get("array", {}).get("capacity", {}).get("kilobytes", {}).get("total", "0")
            if total_kib:
                # Return formatted size string with auto-units
                total_bytes = int(total_kib) * 1024
                return self._format_size(total_bytes)
            return "0 B"
        except (KeyError, AttributeError, TypeError, ValueError):
            return None
            
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            capacity = self.coordinator.data.get("array_status", {}).get("array", {}).get("capacity", {})
            kilobytes = capacity.get("kilobytes", {})
            total_kib = kilobytes.get("total", "0")
            used_kib = kilobytes.get("used", "0")
            free_kib = kilobytes.get("free", "0")
            
            total_bytes = int(total_kib) * 1024 if total_kib else 0
            used_bytes = int(used_kib) * 1024 if used_kib else 0
            free_bytes = int(free_kib) * 1024 if free_kib else 0
            
            used_percent = round((used_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0
            free_percent = round((free_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0
            
            return {
                "total_bytes": total_bytes,
                "used_bytes": used_bytes,
                "free_bytes": free_bytes,
                "used_percent": used_percent,
                "free_percent": free_percent,
                "used": self._format_size(used_bytes),
                "free": self._format_size(free_bytes),
            }
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return {}
            
    def _format_size(self, size_bytes: int) -> str:
        """Format size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.2f} KiB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024 ** 2):.2f} MiB"
        elif size_bytes < 1024 ** 4:
            return f"{size_bytes / (1024 ** 3):.2f} GiB"
        else:
            return f"{size_bytes / (1024 ** 4):.2f} TiB"


class UnraidFlashUsageSensor(UnraidSystemEntity, SensorEntity):
    """Sensor for Unraid flash drive space usage."""

    _attr_name = "Flash Drive Usage"
    _attr_icon = ICON_DISK
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ):
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "flash_usage")

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of the sensor as a percentage."""
        try:
            flash_info = self.coordinator.data.get("array_status", {}).get("flash", {})
            fs_size = int(flash_info.get("fsSize", 0))
            fs_used = int(flash_info.get("fsUsed", 0))
            
            if fs_size > 0:
                # Return usage as percentage
                return round((fs_used / fs_size) * 100, 1)
            return 0
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return None
            
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            flash_info = self.coordinator.data.get("array_status", {}).get("flash", {})
            fs_size = int(flash_info.get("fsSize", 0))
            fs_free = int(flash_info.get("fsFree", 0))
            fs_used = int(flash_info.get("fsUsed", 0))
            
            # Convert KiB values to bytes for formatting
            fs_size_bytes = fs_size * 1024 if fs_size else 0
            fs_free_bytes = fs_free * 1024 if fs_free else 0
            fs_used_bytes = fs_used * 1024 if fs_used else 0
            
            # Calculate percentages
            used_percent = round((fs_used / fs_size) * 100, 1) if fs_size > 0 else 0
            free_percent = round((fs_free / fs_size) * 100, 1) if fs_size > 0 else 0
            
            return {
                "name": flash_info.get("name", "flash"),
                "device": flash_info.get("device", ""),
                "id": flash_info.get("id", ""),
                "total": self._format_size(fs_size_bytes),
                "free": self._format_size(fs_free_bytes),
                "used": self._format_size(fs_used_bytes),
                "used_percent": used_percent,
                "free_percent": free_percent,
                "total_bytes": fs_size_bytes,
                "free_bytes": fs_free_bytes,
                "used_bytes": fs_used_bytes,
            }
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return {}
            
    def _format_size(self, size_bytes: int) -> str:
        """Format size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.2f} KiB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024 ** 2):.2f} MiB"
        elif size_bytes < 1024 ** 4:
            return f"{size_bytes / (1024 ** 3):.2f} GiB"
        else:
            return f"{size_bytes / (1024 ** 4):.2f} TiB"


class UnraidDiskTempSensor(UnraidDiskEntity, SensorEntity):
    """Sensor for Unraid disk temperature."""

    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_TEMPERATURE
    
    # Explicitly mark this sensor as disabled by default
    # so it doesn't try to wake disks for temperature readings
    _attr_entity_registry_enabled_default = False

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        disk_id: str,
        disk_name: str,
        disk_type: str,
    ):
        """Initialize the sensor."""
        # Clean disk name to handle any potential slashes
        disk_name = disk_name.replace('/', '_')
        super().__init__(coordinator, server_name, "temp", disk_id, disk_type)
        self._disk_name = disk_name
        self._attr_name = f"Disk {disk_name} Temperature"
        
        # Store the last known temperature to preserve it when disk is in standby
        self._last_known_temp = None
        self._last_known_attributes = {}
        self._is_standby = False
        self._is_rotational = True  # Default to rotational for safety
        
    def _format_size(self, size_bytes: int) -> str:
        """Format size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.2f} KiB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024 ** 2):.2f} MiB"
        elif size_bytes < 1024 ** 4:
            return f"{size_bytes / (1024 ** 3):.2f} GiB"
        else:
            return f"{size_bytes / (1024 ** 4):.2f} TiB"
        
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
                    # Check if disk is in standby mode
                    disk_state = disk.get("state", "").upper()
                    self._is_standby = disk_state == "STANDBY"
                    
                    # Store rotational status
                    self._is_rotational = disk.get("rotational", True)
                    
                    # Get temperature value (might be None)
                    temp = disk.get("temp")
                    
                    # If we have a temperature value, store it as the last known value
                    if temp is not None:
                        self._last_known_temp = temp
                        return temp
                    
                    # If we don't have a temperature value but the disk is in standby,
                    # return the last known temperature if available
                    if self._is_standby and self._last_known_temp is not None:
                        _LOGGER.debug(f"Disk {self._disk_name} in standby, using last known temperature: {self._last_known_temp}°C")
                        return self._last_known_temp
                    
                    # For cache disks, provide a default temperature if none is available
                    # This is a workaround for the API not returning temperature data for cache disks
                    if self._disk_type == "Cache" and not self._is_rotational:
                        _LOGGER.debug(f"No temperature data for cache disk {self._disk_name}, using default value")
                        return 35  # Default temperature for SSDs
                    
                    # Otherwise, return None (unknown temperature)
                    return None
            
            # If disk not found but we have a last known temperature, use it
            if self._last_known_temp is not None:
                return self._last_known_temp
                
            return None
        except (KeyError, AttributeError, TypeError):
            # On error, return last known temperature if available
            if self._last_known_temp is not None:
                return self._last_known_temp
            return None
            
    @property
    def available(self) -> bool:
        """Return True if entity is available."""
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
                    # For non-rotational drives (SSDs/NVMe), always available
                    rotational = disk.get("rotational", True)
                    if not rotational:
                        return super().available
                    
                    # For rotational drives, check standby state
                    disk_state = disk.get("state", "").upper()
                    if disk_state == "STANDBY":
                        # If we have a last known temperature, we're available
                        # Otherwise, we're not available (to avoid waking the disk)
                        return self._last_known_temp is not None
                    else:
                        # Active rotational drives are available
                        return super().available
            
            # If disk not found, not available
            return False
        except (KeyError, AttributeError, TypeError):
            return False

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            array_data = self.coordinator.data.get("array_status", {}).get("array", {})
            
            # Special handling for parity disks
            if self._disk_type == "Parity":
                # Find the parity disk in the array data
                for disk in array_data.get("parities", []):
                    if disk.get("id") == self._disk_id:
                        # Get disk state and array state
                        disk_state = disk.get("state", "").upper()
                        array_state = array_data.get("state", "").upper()
                        
                        # Get disk size in bytes and format it
                        size_bytes = int(disk.get("size", 0)) * 1024 if disk.get("size") else 0
                        size_formatted = self._format_size(size_bytes)
                        
                        # Build attributes for parity disk
                        attributes = {
                            ATTR_DISK_NAME: disk.get("name"),
                            ATTR_DISK_TYPE: self._disk_type,
                            ATTR_DISK_SIZE: size_formatted,
                            "size_bytes": size_bytes,
                            "status": disk.get("status"),
                            "state": disk_state,
                            "rotational": disk.get("rotational", True),
                            "array_state": array_state,
                            "usage_percent": 100.0 if array_state == "STARTED" else 0.0,
                            "used": size_formatted if array_state == "STARTED" else "0 B",
                            "free": "0 B" if array_state == "STARTED" else size_formatted,
                        }
                        
                        # Store the current attributes for future use
                        self._last_known_attributes = dict(attributes)
                        
                        return attributes
                
                # If parity disk not found but we have last known attributes, use them
                if self._last_known_attributes:
                    return self._last_known_attributes
                    
                return {
                    ATTR_DISK_NAME: self._disk_name,
                    ATTR_DISK_TYPE: self._disk_type,
                }
            
            # For data and cache disks, continue with the existing logic
            # Look in the appropriate disk array based on type
            if self._disk_type == "Cache":
                disks = array_data.get("caches", [])
            else:
                disks = array_data.get("disks", [])
            
            for disk in disks:
                if disk.get("id") == self._disk_id:
                    # Get disk size in bytes and format it
                    size_bytes = int(disk.get("size", 0)) * 1024 if disk.get("size") else 0
                    size_formatted = self._format_size(size_bytes)
                    
                    # Build base attributes
                    attributes = {
                        ATTR_DISK_NAME: disk.get("name"),
                        ATTR_DISK_TYPE: self._disk_type,
                        ATTR_DISK_SIZE: size_formatted,
                        "size_bytes": size_bytes,
                        "status": disk.get("status"),
                        "state": disk.get("state", "").upper(),
                        "rotational": disk.get("rotational", True),
                    }
                    
                    # Add file system information if it exists
                    if "fsSize" in disk and "fsUsed" in disk and "fsFree" in disk:
                        fs_size = int(disk.get("fsSize", 0)) * 1024 if disk.get("fsSize") else 0
                        fs_free = int(disk.get("fsFree", 0)) * 1024 if disk.get("fsFree") else 0
                        fs_used = int(disk.get("fsUsed", 0)) * 1024 if disk.get("fsUsed") else 0
                        
                        attributes.update({
                            "fs_size": self._format_size(fs_size),
                            "fs_free": self._format_size(fs_free),
                            "fs_used": self._format_size(fs_used),
                            "fs_size_bytes": fs_size,
                            "fs_free_bytes": fs_free,
                            "fs_used_bytes": fs_used,
                        })
                        
                        # Add usage percentage
                        if fs_size > 0:
                            attributes["usage_percent"] = round((fs_used / fs_size) * 100, 1)
                    
                    # Store the current attributes for future use
                    self._last_known_attributes = dict(attributes)
                    
                    return attributes
            
            # If disk not found but we have last known attributes, use them
            if self._last_known_attributes:
                return self._last_known_attributes
                
            return {}
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            # On error, return last known attributes if available
            if self._last_known_attributes:
                return self._last_known_attributes
            return {}


class UnraidDiskSpaceUsedSensor(UnraidDiskEntity, SensorEntity):
    """Sensor for Unraid disk space used."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_DISK
    _attr_should_poll = False  # Use coordinator data instead of polling

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        disk_id: str,
        disk_name: str,
    ):
        """Initialize the sensor."""
        # Clean disk name to handle any potential slashes
        disk_name = disk_name.replace('/', '_')
        self._disk_name = disk_name
        
        # Determine disk type based on where it's found in the array data
        disk_type = self._determine_disk_type(coordinator, disk_id)
        
        super().__init__(coordinator, server_name, "space_used", disk_id, disk_type)
        
        # Use consistent naming format: "{type} {name} Usage"
        if disk_type == "Cache":
            self._attr_name = f"Cache {disk_name} Usage"
        else:
            self._attr_name = f"{disk_type} {disk_name} Usage"
        
        # Store the last known value to preserve it when disk is in standby
        self._last_known_value = None
        self._last_known_attributes = {}

    def _determine_disk_type(self, coordinator, disk_id):
        """Determine the disk type based on where it's found in the array data."""
        array_data = coordinator.data.get("array_status", {}).get("array", {})
        
        # Check if it's a cache disk
        for disk in array_data.get("caches", []):
            if disk.get("id") == disk_id:
                return "Cache"
                
        # Check if it's a parity disk
        for disk in array_data.get("parities", []):
            if disk.get("id") == disk_id:
                return "Parity"
                
        # Default to data disk
        return "Data"

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of the sensor as a percentage."""
        try:
            array_data = self.coordinator.data.get("array_status", {}).get("array", {})
            
            # For parity disks, check if the array is started
            if self._disk_type == "Parity":
                array_state = array_data.get("state", "").upper()
                if array_state == "STARTED":
                    # Parity disks are always 100% used when the array is started
                    self._last_known_value = 100.0
                    return 100.0
                else:
                    # If array is not started, parity is not being used
                    self._last_known_value = 0.0
                    return 0.0
            
            # For data and cache disks, continue with the existing logic
            # Look in the appropriate disk array based on type
            if self._disk_type == "Cache":
                disks = array_data.get("caches", [])
            else:
                disks = array_data.get("disks", [])
            
            for disk in disks:
                if disk.get("id") == self._disk_id:
                    # Check if disk is in standby mode
                    disk_state = disk.get("state", "").upper()
                    
                    # For cache disks (SSDs) or active disks, calculate current value
                    if self._disk_type == "Cache" or disk_state == "ACTIVE":
                        fs_size = int(disk.get("fsSize", 0)) if disk.get("fsSize") else 0
                        fs_used = int(disk.get("fsUsed", 0)) if disk.get("fsUsed") else 0
                        
                        if fs_size > 0:
                            # Calculate and store the current value
                            current_value = round((fs_used / fs_size) * 100, 1)
                            self._last_known_value = current_value
                            return current_value
                        elif self._last_known_value is not None:
                            # If we can't calculate but have a previous value, use it
                            return self._last_known_value
                        return 0
                    
                    # For standby disks, return the last known value if available
                    elif self._last_known_value is not None:
                        _LOGGER.debug(f"Disk {self._disk_name} in {disk_state} state, using last known value: {self._last_known_value}%")
                        return self._last_known_value
                    
                    # If no last known value, return 0 for standby disks
                    return 0
            
            # If disk not found but we have a last known value, use it
            if self._last_known_value is not None:
                return self._last_known_value
                
            return None
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            # On error, return last known value if available
            if self._last_known_value is not None:
                return self._last_known_value
            return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            array_data = self.coordinator.data.get("array_status", {}).get("array", {})
            
            # Special handling for parity disks
            if self._disk_type == "Parity":
                # Find the parity disk in the array data
                for disk in array_data.get("parities", []):
                    if disk.get("id") == self._disk_id:
                        # Get disk state and array state
                        disk_state = disk.get("state", "").upper()
                        array_state = array_data.get("state", "").upper()
                        
                        # Get disk size in bytes and format it
                        size_bytes = int(disk.get("size", 0)) * 1024 if disk.get("size") else 0
                        size_formatted = self._format_size(size_bytes)
                        
                        # Build attributes for parity disk
                        attributes = {
                            ATTR_DISK_NAME: disk.get("name"),
                            ATTR_DISK_TYPE: self._disk_type,
                            ATTR_DISK_SIZE: size_formatted,
                            "size_bytes": size_bytes,
                            "status": disk.get("status"),
                            "state": disk_state,
                            "rotational": disk.get("rotational", True),
                            "array_state": array_state,
                            "usage_percent": 100.0 if array_state == "STARTED" else 0.0,
                            "used": size_formatted if array_state == "STARTED" else "0 B",
                            "free": "0 B" if array_state == "STARTED" else size_formatted,
                        }
                        
                        # Store the current attributes for future use
                        self._last_known_attributes = dict(attributes)
                        
                        return attributes
                
                # If parity disk not found but we have last known attributes, use them
                if self._last_known_attributes:
                    return self._last_known_attributes
                    
                return {
                    ATTR_DISK_NAME: self._disk_name,
                    ATTR_DISK_TYPE: self._disk_type,
                }
            
            # For data and cache disks, continue with the existing logic
            # Look in the appropriate disk array based on type
            if self._disk_type == "Cache":
                disks = array_data.get("caches", [])
            else:
                disks = array_data.get("disks", [])
            
            for disk in disks:
                if disk.get("id") == self._disk_id:
                    # Get disk size in bytes and format it
                    size_bytes = int(disk.get("size", 0)) * 1024 if disk.get("size") else 0
                    size_formatted = self._format_size(size_bytes)
                    
                    # Build base attributes
                    attributes = {
                        ATTR_DISK_NAME: disk.get("name"),
                        ATTR_DISK_TYPE: self._disk_type,
                        ATTR_DISK_SIZE: size_formatted,
                        "size_bytes": size_bytes,
                        "status": disk.get("status"),
                        "state": disk.get("state", "").upper(),
                        "rotational": disk.get("rotational", True),
                    }
                    
                    # Add file system information if it exists
                    if "fsSize" in disk and "fsUsed" in disk and "fsFree" in disk:
                        fs_size = int(disk.get("fsSize", 0)) * 1024 if disk.get("fsSize") else 0
                        fs_free = int(disk.get("fsFree", 0)) * 1024 if disk.get("fsFree") else 0
                        fs_used = int(disk.get("fsUsed", 0)) * 1024 if disk.get("fsUsed") else 0
                        
                        attributes.update({
                            "fs_size": self._format_size(fs_size),
                            "fs_free": self._format_size(fs_free),
                            "fs_used": self._format_size(fs_used),
                            "fs_size_bytes": fs_size,
                            "fs_free_bytes": fs_free,
                            "fs_used_bytes": fs_used,
                        })
                        
                        # Add usage percentage
                        if fs_size > 0:
                            attributes["usage_percent"] = round((fs_used / fs_size) * 100, 1)
                    
                    # Store the current attributes for future use
                    self._last_known_attributes = dict(attributes)
                    
                    return attributes
            
            # If disk not found but we have last known attributes, use them
            if self._last_known_attributes:
                return self._last_known_attributes
                
            return {}
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            # On error, return last known attributes if available
            if self._last_known_attributes:
                return self._last_known_attributes
            return {}

    def _format_size(self, size_bytes: int) -> str:
        """Format size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.2f} KiB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024 ** 2):.2f} MiB"
        elif size_bytes < 1024 ** 4:
            return f"{size_bytes / (1024 ** 3):.2f} GiB"
        else:
            return f"{size_bytes / (1024 ** 4):.2f} TiB"


class UnraidDiskSpaceFreeSensor(UnraidDiskEntity, SensorEntity):
    """Sensor for Unraid disk space free."""

    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_DISK
    _attr_should_poll = False  # Use coordinator data instead of polling

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        disk_id: str,
        disk_name: str,
    ):
        """Initialize the sensor."""
        # Clean disk name to handle any potential slashes
        disk_name = disk_name.replace('/', '_')
        self._disk_name = disk_name
        
        # Determine disk type based on where it's found in the array data
        disk_type = self._determine_disk_type(coordinator, disk_id)
        
        super().__init__(coordinator, server_name, "space_free", disk_id, disk_type)
        
        # Use consistent naming format: "{type} {name} Free Space"
        if disk_type == "Cache":
            self._attr_name = f"Cache {disk_name} Free Space"
        else:
            self._attr_name = f"{disk_type} {disk_name} Free Space"
        
        # Store the last known value to preserve it when disk is in standby
        self._last_known_value = None
        self._last_known_attributes = {}

    def _determine_disk_type(self, coordinator, disk_id):
        """Determine the disk type based on where it's found in the array data."""
        array_data = coordinator.data.get("array_status", {}).get("array", {})
        
        # Check if it's a cache disk
        for disk in array_data.get("caches", []):
            if disk.get("id") == disk_id:
                return "Cache"
                
        # Check if it's a parity disk
        for disk in array_data.get("parities", []):
            if disk.get("id") == disk_id:
                return "Parity"
                
        # Default to data disk
        return "Data"

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of the sensor as a percentage."""
        try:
            array_data = self.coordinator.data.get("array_status", {}).get("array", {})
            
            # For parity disks, check if the array is started
            if self._disk_type == "Parity":
                array_state = array_data.get("state", "").upper()
                if array_state == "STARTED":
                    # Parity disks have 0% free space when the array is started
                    self._last_known_value = 0.0
                    return 0.0
                else:
                    # If array is not started, parity is 100% free
                    self._last_known_value = 100.0
                    return 100.0
            
            # For data and cache disks, continue with the existing logic
            # Look in the appropriate disk array based on type
            if self._disk_type == "Cache":
                disks = array_data.get("caches", [])
            else:
                disks = array_data.get("disks", [])
            
            for disk in disks:
                if disk.get("id") == self._disk_id:
                    # Check disk state
                    disk_state = disk.get("state", "").upper()
                    
                    # For cache disks (SSDs) or active disks, calculate current value
                    if self._disk_type == "Cache" or disk_state == "ACTIVE":
                        fs_size = int(disk.get("fsSize", 0)) if disk.get("fsSize") else 0
                        fs_free = int(disk.get("fsFree", 0)) if disk.get("fsFree") else 0
                        
                        if fs_size > 0:
                            # Calculate and store the current value
                            current_value = round((fs_free / fs_size) * 100, 1)
                            self._last_known_value = current_value
                            return current_value
                        elif self._last_known_value is not None:
                            # If we can't calculate but have a previous value, use it
                            return self._last_known_value
                        return 0
                    
                    # For standby disks, return the last known value if available
                    elif self._last_known_value is not None:
                        _LOGGER.debug(f"Disk {self._disk_name} in {disk_state} state, using last known value: {self._last_known_value}%")
                        return self._last_known_value
                    
                    # If no last known value, return 0 for standby disks
                    return 0
            
            # If disk not found but we have a last known value, use it
            if self._last_known_value is not None:
                return self._last_known_value
                
            return None
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            # On error, return last known value if available
            if self._last_known_value is not None:
                return self._last_known_value
            return None

    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            array_data = self.coordinator.data.get("array_status", {}).get("array", {})
            
            # Special handling for parity disks
            if self._disk_type == "Parity":
                # Find the parity disk in the array data
                for disk in array_data.get("parities", []):
                    if disk.get("id") == self._disk_id:
                        # Get disk state and array state
                        disk_state = disk.get("state", "").upper()
                        array_state = array_data.get("state", "").upper()
                        
                        # Get disk size in bytes and format it
                        size_bytes = int(disk.get("size", 0)) * 1024 if disk.get("size") else 0
                        size_formatted = self._format_size(size_bytes)
                        
                        # Build attributes for parity disk
                        attributes = {
                            ATTR_DISK_NAME: disk.get("name"),
                            ATTR_DISK_TYPE: self._disk_type,
                            ATTR_DISK_SIZE: size_formatted,
                            "size_bytes": size_bytes,
                            "status": disk.get("status"),
                            "state": disk_state,
                            "rotational": disk.get("rotational", True),
                            "array_state": array_state,
                            "usage_percent": 100.0 if array_state == "STARTED" else 0.0,
                            "used": size_formatted if array_state == "STARTED" else "0 B",
                            "free": "0 B" if array_state == "STARTED" else size_formatted,
                        }
                        
                        # Store the current attributes for future use
                        self._last_known_attributes = dict(attributes)
                        
                        return attributes
                
                # If parity disk not found but we have last known attributes, use them
                if self._last_known_attributes:
                    return self._last_known_attributes
                    
                return {
                    ATTR_DISK_NAME: self._disk_name,
                    ATTR_DISK_TYPE: self._disk_type,
                }
            
            # For data and cache disks, continue with the existing logic
            # Look in the appropriate disk array based on type
            if self._disk_type == "Cache":
                disks = array_data.get("caches", [])
            else:
                disks = array_data.get("disks", [])
            
            for disk in disks:
                if disk.get("id") == self._disk_id:
                    # Get disk size in bytes and format it
                    size_bytes = int(disk.get("size", 0)) * 1024 if disk.get("size") else 0
                    size_formatted = self._format_size(size_bytes)
                    
                    # Build base attributes
                    attributes = {
                        ATTR_DISK_NAME: disk.get("name"),
                        ATTR_DISK_TYPE: self._disk_type,
                        ATTR_DISK_SIZE: size_formatted,
                        "size_bytes": size_bytes,
                        "status": disk.get("status"),
                        "state": disk.get("state", "").upper(),
                        "rotational": disk.get("rotational", True),
                    }
                    
                    # Add file system information if it exists
                    if "fsSize" in disk and "fsUsed" in disk and "fsFree" in disk:
                        fs_size = int(disk.get("fsSize", 0)) * 1024 if disk.get("fsSize") else 0
                        fs_free = int(disk.get("fsFree", 0)) * 1024 if disk.get("fsFree") else 0
                        fs_used = int(disk.get("fsUsed", 0)) * 1024 if disk.get("fsUsed") else 0
                        
                        attributes.update({
                            "fs_size": self._format_size(fs_size),
                            "fs_free": self._format_size(fs_free),
                            "fs_used": self._format_size(fs_used),
                            "fs_size_bytes": fs_size,
                            "fs_free_bytes": fs_free,
                            "fs_used_bytes": fs_used,
                        })
                        
                        # Add usage percentage
                        if fs_size > 0:
                            attributes["usage_percent"] = round((fs_used / fs_size) * 100, 1)
                    
                    # Store the current attributes for future use
                    self._last_known_attributes = dict(attributes)
                    
                    return attributes
            
            # If disk not found but we have last known attributes, use them
            if self._last_known_attributes:
                return self._last_known_attributes
                
            return {}
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            # On error, return last known attributes if available
            if self._last_known_attributes:
                return self._last_known_attributes
            return {}
            
    def _format_size(self, size_bytes: int) -> str:
        """Format size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.2f} KiB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024 ** 2):.2f} MiB"
        elif size_bytes < 1024 ** 4:
            return f"{size_bytes / (1024 ** 3):.2f} GiB"
        else:
            return f"{size_bytes / (1024 ** 4):.2f} TiB"


class UnraidShareSpaceUsedSensor(UnraidShareEntity, SensorEntity):
    """Sensor for Unraid share space used."""

    _attr_entity_registry_enabled_default = False
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_DISK

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        share_name: str,
    ):
        """Initialize the sensor."""
        # Clean share name to handle any potential slashes
        share_name_safe = share_name.replace('/', '_')
        super().__init__(coordinator, server_name, "space_used", share_name)
        self._attr_name = f"Share {share_name_safe} Usage"

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of the sensor as a percentage."""
        try:
            shares = self.coordinator.data.get("shares", [])
            
            for share in shares:
                if share.get("name") == self._share_name:
                    # Calculate percentage of space used
                    free_kib = int(share.get("free", 0)) if share.get("free") else 0
                    used_kib = int(share.get("used", 0)) if share.get("used") else 0
                    total_kib = free_kib + used_kib
                    
                    if total_kib > 0:
                        return round((used_kib / total_kib) * 100, 1)
                    return 0
            
            return None
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return None
            
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            shares = self.coordinator.data.get("shares", [])
            
            for share in shares:
                if share.get("name") == self._share_name:
                    # Convert KiB values to bytes for formatting
                    free_bytes = int(share.get("free", 0)) * 1024 if share.get("free") else 0
                    used_bytes = int(share.get("used", 0)) * 1024 if share.get("used") else 0
                    size_bytes = free_bytes + used_bytes
                    
                    # Calculate percentage
                    used_percent = round((used_bytes / size_bytes) * 100, 1) if size_bytes > 0 else 0
                    
                    # Add both GiB values and percentage values for flexibility
                    free_gib = round(free_bytes / (1024**3), 2) if free_bytes else 0
                    used_gib = round(used_bytes / (1024**3), 2) if used_bytes else 0
                    total_gib = round(size_bytes / (1024**3), 2) if size_bytes else 0
                    
                    return {
                        "name": share.get("name"),
                        "comment": share.get("comment", ""),
                        "total": self._format_size(size_bytes),
                        "free": self._format_size(free_bytes),
                        "used": self._format_size(used_bytes),
                        "used_percent": used_percent,
                        "free_percent": round(100 - used_percent, 1) if size_bytes > 0 else 0,
                        "total_bytes": size_bytes,
                        "free_bytes": free_bytes,
                        "used_bytes": used_bytes,
                        "total_gib": total_gib,
                        "free_gib": free_gib,
                        "used_gib": used_gib,
                    }
            
            return {}
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return {}
            
    def _format_size(self, size_bytes: int) -> str:
        """Format size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.2f} KiB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024 ** 2):.2f} MiB"
        elif size_bytes < 1024 ** 4:
            return f"{size_bytes / (1024 ** 3):.2f} GiB"
        else:
            return f"{size_bytes / (1024 ** 4):.2f} TiB"


class UnraidShareSpaceFreeSensor(UnraidShareEntity, SensorEntity):
    """Sensor for Unraid share space free."""

    _attr_entity_registry_enabled_default = False
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = ICON_DISK

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
        share_name: str,
    ):
        """Initialize the sensor."""
        # Clean share name to handle any potential slashes
        share_name_safe = share_name.replace('/', '_')
        super().__init__(coordinator, server_name, "space_free", share_name)
        self._attr_name = f"Share {share_name_safe} Free Space"

    @property
    def native_value(self) -> Optional[float]:
        """Return the state of the sensor as a percentage."""
        try:
            shares = self.coordinator.data.get("shares", [])
            
            for share in shares:
                if share.get("name") == self._share_name:
                    # Calculate percentage of space free
                    free_kib = int(share.get("free", 0)) if share.get("free") else 0
                    used_kib = int(share.get("used", 0)) if share.get("used") else 0
                    total_kib = free_kib + used_kib
                    
                    if total_kib > 0:
                        return round((free_kib / total_kib) * 100, 1)
                    return 0
            
            return None
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return None
            
    @property
    def extra_state_attributes(self) -> Dict[str, Any]:
        """Return the state attributes."""
        try:
            shares = self.coordinator.data.get("shares", [])
            
            for share in shares:
                if share.get("name") == self._share_name:
                    # Convert KiB values to bytes for formatting
                    free_bytes = int(share.get("free", 0)) * 1024 if share.get("free") else 0
                    used_bytes = int(share.get("used", 0)) * 1024 if share.get("used") else 0
                    size_bytes = free_bytes + used_bytes
                    
                    # Calculate percentage
                    free_percent = round((free_bytes / size_bytes) * 100, 1) if size_bytes > 0 else 0
                    
                    # Add both GiB values and percentage values for flexibility
                    free_gib = round(free_bytes / (1024**3), 2) if free_bytes else 0
                    used_gib = round(used_bytes / (1024**3), 2) if used_bytes else 0
                    total_gib = round(size_bytes / (1024**3), 2) if size_bytes else 0
                    
                    return {
                        "name": share.get("name"),
                        "comment": share.get("comment", ""),
                        "total": self._format_size(size_bytes),
                        "free": self._format_size(free_bytes),
                        "used": self._format_size(used_bytes),
                        "free_percent": free_percent,
                        "used_percent": round(100 - free_percent, 1) if size_bytes > 0 else 0,
                        "total_bytes": size_bytes,
                        "free_bytes": free_bytes,
                        "used_bytes": used_bytes,
                        "total_gib": total_gib,
                        "free_gib": free_gib,
                        "used_gib": used_gib,
                    }
            
            return {}
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return {}
            
    def _format_size(self, size_bytes: int) -> str:
        """Format size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.2f} KiB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024 ** 2):.2f} MiB"
        elif size_bytes < 1024 ** 4:
            return f"{size_bytes / (1024 ** 3):.2f} GiB"
        else:
            return f"{size_bytes / (1024 ** 4):.2f} TiB"