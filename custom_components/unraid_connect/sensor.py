"""Sensor platform for Unraid integration."""
# ruff: noqa: TRY300

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
from typing import Any

import dateutil.parser

from homeassistant.components.sensor import (
    EntityCategory,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import (
    ATTR_CPU_BRAND,
    ATTR_CPU_CORES,
    ATTR_CPU_THREADS,
    ATTR_DISK_NAME,
    ATTR_DISK_SIZE,
    ATTR_DISK_TYPE,
    DOMAIN as INTEGRATION_DOMAIN,
    ICON_ARRAY,
    ICON_CPU,
    ICON_DISK,
    ICON_MEMORY,
    ICON_NOTIFICATION,
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

PARALLEL_UPDATES = 1

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Unraid sensors."""
    coordinator = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["coordinator"]
    name = hass.data[INTEGRATION_DOMAIN][entry.entry_id]["name"]

    entities: list[SensorEntity] = []
    system_entities: list[UnraidSystemStateSensor] = []
    array_entities: list[UnraidArrayStateSensor] = []
    flash_entities: list[UnraidFlashUsageSensor] = []

    # Add system sensors
    system_entities.append(UnraidSystemStateSensor(coordinator, name))
    # CPU usage sensor disabled - Unraid GraphQL API doesn't provide real-time CPU usage data
    # entities.append(UnraidCpuUsageSensor(coordinator, name))

    # Add other system sensors to entities directly if data is available
    cpu_temp = (
        coordinator.data.get("system_info", {}).get("temperatures", {}).get("cpu")
    )
    if cpu_temp is not None or coordinator.data.get("system_info", {}).get(
        "hardware", {}
    ):
        entities.append(UnraidCpuTempSensor(coordinator, name))

    mb_temp = (
        coordinator.data.get("system_info", {})
        .get("temperatures", {})
        .get("motherboard")
    )
    if mb_temp is not None or coordinator.data.get("system_info", {}).get(
        "hardware", {}
    ):
        entities.append(UnraidMotherboardTempSensor(coordinator, name))
    # Memory usage sensor disabled - Unraid GraphQL API doesn't provide real-time memory usage data
    # entities.append(UnraidMemoryUsageSensor(coordinator, name))
    entities.append(UnraidUptimeSensor(coordinator, name))
    entities.append(UnraidNotificationSensor(coordinator, name))

    # Add flash drive usage sensor (always create, handles missing data gracefully)
    flash_entities.append(UnraidFlashUsageSensor(coordinator, name))

    # Add array sensors
    array_entities.append(UnraidArrayStateSensor(coordinator, name))
    # Add array space sensors directly to entities
    entities.append(UnraidArraySpaceUsedSensor(coordinator, name))
    entities.append(UnraidArraySpaceFreeSensor(coordinator, name))
    # Array Total Space is now an attribute of Array Free Space

    # Add all entities to the main list
    entities.extend(system_entities)
    entities.extend(flash_entities)
    entities.extend(array_entities)

    # Get array data for disks
    array_data = coordinator.data.get("array_status", {}).get("array", {})

    # Add data disks
    data_disks = array_data.get("disks", [])
    data_disk_entities: list[UnraidDiskSpaceUsedSensor] = []
    for disk in data_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            # Data disk type is implied by the collection it's in

            # Add space sensors for all disks
            data_disk_entities.append(
                UnraidDiskSpaceUsedSensor(coordinator, name, disk_id, disk_name)
            )
            # Free space is now included as an attribute in the usage sensor

            # Temperature sensors are now included as attributes in the disk health binary sensors
            # No need to create separate temperature sensors

    # Add data disk entities to the main list
    entities.extend(data_disk_entities)

    # Add parity disks
    parity_disks = array_data.get("parities", [])
    parity_disk_entities: list[UnraidDiskSpaceUsedSensor] = []
    for disk in parity_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            # Parity disk type is implied by the collection it's in

            # Parity disks don't have meaningful usage metrics, so we don't create sensors for them

            # Temperature sensors are now included as attributes in the disk health binary sensors
            # No need to create separate temperature sensors

    # Add parity disk entities to the main list
    entities.extend(parity_disk_entities)

    # Add cache disks
    cache_disks = array_data.get("caches", [])
    cache_disk_entities: list[UnraidDiskSpaceUsedSensor] = []
    for disk in cache_disks:
        if disk.get("id") and disk.get("name"):
            disk_id = disk.get("id")
            disk_name = disk.get("name")
            # Cache disk type is implied by the collection it's in

            # Add space sensors for cache drives
            cache_disk_entities.append(
                UnraidDiskSpaceUsedSensor(coordinator, name, disk_id, disk_name)
            )
            # Free space is now included as an attribute in the usage sensor

            # Temperature sensors are now included as attributes in the disk health binary sensors
            # No need to create separate temperature sensors

    # Add cache disk entities to the main list
    entities.extend(cache_disk_entities)

    # Add shares
    shares_data = coordinator.data.get("shares", [])
    share_entities: list[UnraidShareSpaceUsedSensor] = []
    for share in shares_data:
        if share.get("name"):
            share_name = share.get("name")
            share_entities.append(
                UnraidShareSpaceUsedSensor(coordinator, name, share_name)
            )
            # Add free space sensor directly to entities
            entities.append(UnraidShareSpaceFreeSensor(coordinator, name, share_name))

    # Add share entities to the main list
    entities.extend(share_entities)

    async_add_entities(entities)


class UnraidSystemStateSensor(UnraidSystemEntity, SensorEntity):
    """Sensor for Unraid system state."""

    _attr_name = "Server Status"
    _attr_icon = ICON_CPU
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "state")

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        online = self.coordinator.data.get("system_info", {}).get("online", False)
        return "Online" if online else "Offline"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            system_info = self.coordinator.data.get("system_info", {})
            info = system_info.get("info", {})

            attributes = {}

            # Add OS information
            os_info = info.get("os", {})
            if os_info:
                attributes.update(
                    {
                        "os_platform": os_info.get("platform"),
                        "os_distro": os_info.get("distro"),
                        "os_release": os_info.get("release"),
                    }
                )

            # Add version information
            versions = info.get("versions", {})
            if versions:
                attributes.update(
                    {
                        "unraid_version": versions.get("unraid"),
                        "kernel_version": versions.get("kernel"),
                        "docker_version": versions.get("docker"),
                    }
                )

            # Add CPU information
            cpu_info = info.get("cpu", {})
            if cpu_info:
                attributes.update(
                    {
                        "cpu_manufacturer": cpu_info.get("manufacturer"),
                        "cpu_brand": cpu_info.get("brand"),
                        "cpu_cores": cpu_info.get("cores"),
                        "cpu_threads": cpu_info.get("threads"),
                    }
                )

            return attributes
        except (KeyError, AttributeError, TypeError):
            return {}


class UnraidCpuUsageSensor(UnraidSystemEntity, SensorEntity):
    """Sensor for Unraid CPU usage."""

    _attr_name = "CPU Usage"
    _attr_icon = ICON_CPU
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "cpu_usage")

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        try:
            # Try to get CPU usage from different possible locations in the API response
            _LOGGER.debug(
                "CPU usage sensor data: %s",
                self.coordinator.data.get("system_info", {}),
            )

            # First try from system_info.info.cpu
            cpu_info = (
                self.coordinator.data.get("system_info", {})
                .get("info", {})
                .get("cpu", {})
            )

            # Check if we have usage data in cpu_info
            if cpu_info and "usage" in cpu_info:
                try:
                    return round(float(cpu_info["usage"]), 1)
                except (ValueError, TypeError):
                    pass

            # Try from system_info.cpu_usage
            cpu_usage = self.coordinator.data.get("system_info", {}).get("cpu_usage")
            if cpu_usage is not None:
                try:
                    return round(float(cpu_usage), 1)
                except (ValueError, TypeError):
                    pass

            # Try from system_info.info.load
            load_info = (
                self.coordinator.data.get("system_info", {})
                .get("info", {})
                .get("load", {})
            )

            if load_info:
                # If we have current load, use that
                if "current" in load_info:
                    try:
                        # Convert load to percentage based on number of cores
                        cpu_info = (
                            self.coordinator.data.get("system_info", {})
                            .get("info", {})
                            .get("cpu", {})
                        )
                        cores = max(cpu_info.get("cores", 1), 1)

                        current_load = float(load_info["current"])
                        # Calculate percentage (load / cores * 100)
                        return round(min(current_load / cores * 100, 100), 1)
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

                # If we have average load, use that
                if "average" in load_info:
                    try:
                        # Convert load to percentage based on number of cores
                        cpu_info = (
                            self.coordinator.data.get("system_info", {})
                            .get("info", {})
                            .get("cpu", {})
                        )
                        cores = max(cpu_info.get("cores", 1), 1)

                        avg_load = float(load_info["average"])
                        # Calculate percentage (load / cores * 100)
                        return round(min(avg_load / cores * 100, 100), 1)
                    except (ValueError, TypeError, ZeroDivisionError):
                        pass

            # If we get here, we couldn't find CPU usage data
            # This is a known limitation of the Unraid GraphQL API
            _LOGGER.debug("CPU usage data not available in Unraid GraphQL API - this is a known limitation")
            return 0
        except (KeyError, AttributeError, TypeError):
            _LOGGER.debug("Error getting CPU usage data - using default value of 0")
            return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            cpu_info = (
                self.coordinator.data.get("system_info", {})
                .get("info", {})
                .get("cpu", {})
            )

            attributes = {
                ATTR_CPU_BRAND: cpu_info.get("brand", "Unknown"),
                ATTR_CPU_CORES: cpu_info.get("cores", 0),
                ATTR_CPU_THREADS: cpu_info.get("threads", 0),
                "manufacturer": cpu_info.get("manufacturer", "Unknown"),
            }

            # Add load information if available
            load_info = (
                self.coordinator.data.get("system_info", {})
                .get("info", {})
                .get("load", {})
            )

            if load_info:
                if "current" in load_info:
                    attributes["load_current"] = load_info["current"]
                if "average" in load_info:
                    attributes["load_average"] = load_info["average"]

            # Add OS information if available
            info = self.coordinator.data.get("system_info", {}).get("info", {})
            os_info = info.get("os", {})
            if os_info:
                attributes.update(
                    {
                        "os_platform": os_info.get("platform", "Unknown"),
                        "os_distro": os_info.get("distro", "Unknown"),
                        "os_release": os_info.get("release", "Unknown"),
                    }
                )

            # Add version information if available
            versions = info.get("versions", {})
            if versions:
                attributes["unraid_version"] = versions.get("unraid", "Unknown")

            # Add API limitation note for CPU usage
            attributes["api_limitation"] = "Real-time CPU usage not available in Unraid GraphQL API"
            attributes["data_source"] = "Static hardware information only"

            return attributes
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
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "temperature")

    def _get_temperature_from_direct_source(self) -> float | None:
        """Get CPU temperature from direct temperature source."""
        temperatures = self.coordinator.data.get("system_info", {}).get(
            "temperatures", {}
        )
        if not temperatures:
            return None

        # First try to get the CPU temperature directly
        if "cpu" in temperatures and temperatures["cpu"] is not None:
            try:
                return round(float(temperatures["cpu"]), 1)
            except (ValueError, TypeError):
                pass

        # Next, try to get from sensors array if available
        temp = self._get_temp_from_sensors(temperatures.get("sensors", []))
        if temp is not None:
            return temp

        # Try to get from hardware sensors if available
        return self._get_temp_from_hardware()

    def _get_temp_from_sensors(self, sensors: list[dict[str, Any]]) -> float | None:
        """Get temperature from sensors array."""
        for sensor in sensors:
            name = sensor.get("name", "").lower()
            if "cpu" in name or "processor" in name:
                try:
                    return round(float(sensor.get("value", 0)), 1)
                except (ValueError, TypeError):
                    pass
        return None

    def _get_temp_from_hardware(self) -> float | None:
        """Get temperature from hardware sensors."""
        hardware = self.coordinator.data.get("system_info", {}).get("hardware", {})
        if not hardware:
            return None

        # Try to get CPU temperature from hardware sensors
        if "cpu" in hardware and hardware["cpu"] is not None:
            try:
                return round(float(hardware["cpu"]), 1)
            except (ValueError, TypeError):
                pass

        # Try to get from hardware sensors array if available
        return self._get_temp_from_sensors_array(hardware.get("sensors", []))

    def _get_temp_from_sensors_array(
        self, sensors: list[dict[str, Any]]
    ) -> float | None:
        """Get temperature from hardware sensors array."""
        for sensor in sensors:
            name = sensor.get("name", "").lower()
            if "cpu" in name or "processor" in name:
                try:
                    return round(float(sensor.get("temp", 0)), 1)
                except (ValueError, TypeError):
                    pass
        return None

    def _get_temperature_from_cpu_info(self) -> float | None:
        """Get CPU temperature from CPU info object."""
        cpu_info = (
            self.coordinator.data.get("system_info", {}).get("info", {}).get("cpu", {})
        )
        if "temperature" in cpu_info and cpu_info["temperature"] is not None:
            try:
                return round(float(cpu_info["temperature"]), 1)
            except (ValueError, TypeError):
                pass

        return None

    def _get_temperature_from_temps_structure(self) -> float | None:
        """Get CPU temperature from temps structure."""
        temps = (
            self.coordinator.data.get("system_info", {})
            .get("info", {})
            .get("temps", {})
        )
        if not temps:
            return None

        # Look for CPU temperature in temps
        for temp_item in temps:
            if "cpu" in temp_item.get("name", "").lower():
                try:
                    return round(float(temp_item.get("temp", 0)), 1)
                except (ValueError, TypeError):
                    pass

        return None

    def _get_temperature_from_system_data(self) -> float | None:
        """Get CPU temperature from system data."""
        system_data = self.coordinator.data.get("system_info", {})
        if "cpuTemperature" in system_data:
            try:
                return round(float(system_data["cpuTemperature"]), 1)
            except (ValueError, TypeError):
                pass

        return None

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        try:
            # Try all possible sources for CPU temperature
            temp = self._get_temperature_from_direct_source()
            if temp is not None:
                return temp

            temp = self._get_temperature_from_cpu_info()
            if temp is not None:
                return temp

            temp = self._get_temperature_from_temps_structure()
            if temp is not None:
                return temp

            temp = self._get_temperature_from_system_data()
            if temp is not None:
                return temp

            # No valid temperature found
            return None
        except (KeyError, AttributeError, TypeError, ValueError):
            return None

    def _get_cpu_sensors(self) -> list[dict[str, Any]]:
        """Get CPU sensors information."""
        temperatures = self.coordinator.data.get("system_info", {}).get(
            "temperatures", {}
        )
        if not temperatures or "sensors" not in temperatures:
            return []

        cpu_sensors = []
        for sensor in temperatures["sensors"]:
            name = sensor.get("name", "").lower()
            if "cpu" in name or "processor" in name:
                cpu_sensors.append(
                    {
                        "name": sensor.get("name", "Unknown"),
                        "adapter": sensor.get("adapter", "Unknown"),
                        "value": sensor.get("value"),
                    }
                )

        return cpu_sensors

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            cpu_info = (
                self.coordinator.data.get("system_info", {})
                .get("info", {})
                .get("cpu", {})
            )
            attributes = {
                ATTR_CPU_BRAND: cpu_info.get("brand", "Unknown"),
                ATTR_CPU_CORES: cpu_info.get("cores", 0),
                ATTR_CPU_THREADS: cpu_info.get("threads", 0),
                "manufacturer": cpu_info.get("manufacturer", "Unknown"),
            }

            # Add sensor information if available
            cpu_sensors = self._get_cpu_sensors()
            if cpu_sensors:
                attributes["sensors"] = cpu_sensors
                return attributes
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
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "mb_temperature")

    def _get_temp_from_temperatures(self) -> float | None:
        """Get motherboard temperature from temperatures object."""
        temperatures = self.coordinator.data.get("system_info", {}).get(
            "temperatures", {}
        )
        if not temperatures:
            return None

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
        return self._get_temp_from_sensors(temperatures.get("sensors", []))

    def _get_temp_from_sensors(self, sensors: list[dict[str, Any]]) -> float | None:
        """Get temperature from sensors array."""
        for sensor in sensors:
            name = sensor.get("name", "").lower()
            # Look for common motherboard temperature sensor names
            if (
                "motherboard" in name
                or "system" in name
                or "mb" in name
                or "board" in name
            ):
                try:
                    return round(float(sensor.get("value", 0)), 1)
                except (ValueError, TypeError):
                    pass
        return None

    def _get_temp_from_hardware(self) -> float | None:
        """Get temperature from hardware sensors."""
        hardware = self.coordinator.data.get("system_info", {}).get("hardware", {})
        if not hardware:
            return None

        # Try to get motherboard temperature from hardware sensors
        if "motherboard" in hardware and hardware["motherboard"] is not None:
            try:
                return round(float(hardware["motherboard"]), 1)
            except (ValueError, TypeError):
                pass

        # Try to get system temperature from hardware sensors
        if "system" in hardware and hardware["system"] is not None:
            try:
                return round(float(hardware["system"]), 1)
            except (ValueError, TypeError):
                pass

        # Try to get from hardware sensors array if available
        return self._get_temp_from_hardware_sensors(hardware.get("sensors", []))

    def _get_temp_from_hardware_sensors(
        self, sensors: list[dict[str, Any]]
    ) -> float | None:
        """Get temperature from hardware sensors array."""
        for sensor in sensors:
            name = sensor.get("name", "").lower()
            if (
                "motherboard" in name
                or "system" in name
                or "mb" in name
                or "board" in name
            ):
                try:
                    return round(float(sensor.get("temp", 0)), 1)
                except (ValueError, TypeError):
                    pass
        return None

    def _get_temp_from_system_data(self) -> float | None:
        """Get temperature from system data."""
        system_data = self.coordinator.data.get("system_info", {})
        if "systemTemperature" in system_data:
            try:
                return round(float(system_data["systemTemperature"]), 1)
            except (ValueError, TypeError):
                pass
        return None

    def _get_temp_from_info_data(self) -> float | None:
        """Get temperature from info data."""
        info_data = self.coordinator.data.get("system_info", {}).get("info", {})
        if not info_data:
            return None

        # Try motherboard info
        mb_data = info_data.get("motherboard", {})
        if mb_data and "temperature" in mb_data and mb_data["temperature"] is not None:
            try:
                return round(float(mb_data["temperature"]), 1)
            except (ValueError, TypeError):
                pass
        return None

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        try:
            # Try all possible sources for motherboard temperature
            temp = self._get_temp_from_temperatures()
            if temp is not None:
                return temp

            temp = self._get_temp_from_hardware()
            if temp is not None:
                return temp

            temp = self._get_temp_from_system_data()
            if temp is not None:
                return temp

            temp = self._get_temp_from_info_data()
            if temp is not None:
                return temp

            # No valid temperature found
            return None
        except (KeyError, AttributeError, TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            attributes = {}

            # Add sensor information if available
            temperatures = self.coordinator.data.get("system_info", {}).get(
                "temperatures", {}
            )
            if temperatures and "sensors" in temperatures:
                mb_sensors = []
                for sensor in temperatures["sensors"]:
                    name = sensor.get("name", "").lower()
                    if (
                        "motherboard" in name
                        or "system" in name
                        or "mb" in name
                        or "board" in name
                    ):
                        mb_sensors.append(
                            {
                                "name": sensor.get("name", "Unknown"),
                                "adapter": sensor.get("adapter", "Unknown"),
                                "value": sensor.get("value"),
                            }
                        )

                if mb_sensors:
                    attributes["sensors"] = mb_sensors
                    return attributes
                return attributes
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
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "memory_usage")

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor."""
        try:
            # First try to get memory from info structure
            _LOGGER.debug(
                "Memory usage sensor data: %s",
                self.coordinator.data.get("system_info", {}),
            )
            memory = (
                self.coordinator.data.get("system_info", {})
                .get("info", {})
                .get("memory", {})
            )

            # Check if we have valid memory data
            if memory and isinstance(memory, dict):
                # Check if we have a direct usage value
                if "usage" in memory:
                    try:
                        usage_value = float(memory["usage"])
                        _LOGGER.debug("Found memory usage: %s%%", usage_value)
                        return round(usage_value, 1)
                    except (ValueError, TypeError):
                        pass

                total = memory.get("total", 0)
                # Use available memory as free for more accurate usage calculation
                # (available accounts for buffer/cache that can be reclaimed)
                available = memory.get("available", memory.get("free", 0))

                if total > 0:
                    used_percent = 100 - (
                        available / total * 100
                    )  # Calculate based on available memory
                    _LOGGER.debug("Calculated memory usage: %s%% (total: %s, available: %s)",
                                round(used_percent, 1), total, available)
                    return round(used_percent, 1)

            # If we don't have valid memory data in the info structure,
            # try to get it directly from system_info
            direct_memory = self.coordinator.data.get("system_info", {}).get(
                "memory", {}
            )
            if direct_memory and isinstance(direct_memory, dict):
                total = direct_memory.get("total", 0)
                available = direct_memory.get("available", direct_memory.get("free", 0))

                if total > 0:
                    used_percent = 100 - (available / total * 100)
                    return round(used_percent, 1)
                return 0

            # Default to 0 if we can't calculate
            _LOGGER.debug("Memory usage data not available in Unraid GraphQL API - this is a known limitation")
            return 0
        except (KeyError, AttributeError, TypeError, ZeroDivisionError):
            _LOGGER.debug("Error getting memory usage data - using default value of 0")
            return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            memory = (
                self.coordinator.data.get("system_info", {})
                .get("info", {})
                .get("memory", {})
            )

            attributes = {
                "total": self._format_memory_size(memory.get("total", 0)),
                "used": self._format_memory_size(memory.get("used", 0)),
                "free": self._format_memory_size(memory.get("free", 0)),
                "available": self._format_memory_size(memory.get("available", 0)),
                "active": self._format_memory_size(memory.get("active", 0)),
            }

            # Add API limitation note for memory usage
            attributes["api_limitation"] = "Real-time memory usage not available in Unraid GraphQL API"
            attributes["data_source"] = "Placeholder values due to API limitations"

            return attributes
        except (KeyError, AttributeError, TypeError):
            return {}

    def _format_memory_size(self, size_bytes: int) -> str:
        """Format memory size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024**2:
            return f"{size_bytes / 1024:.2f} KB"
        if size_bytes < 1024**3:
            return f"{size_bytes / (1024**2):.2f} MB"
        if size_bytes < 1024**4:
            return f"{size_bytes / (1024**3):.2f} GB"
        return f"{size_bytes / (1024**4):.2f} TB"


class UnraidUptimeSensor(UnraidSystemEntity, SensorEntity):
    """Sensor for Unraid uptime."""

    _attr_name = "Server Uptime"
    _attr_icon = ICON_SERVER
    _attr_device_class = None  # Changed from TIMESTAMP to display a formatted string
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "uptime")

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor as a human-readable duration."""
        try:
            # First try to get uptime from the os.uptime field (ISO 8601 datetime string)
            uptime_str = (
                self.coordinator.data.get("system_info", {})
                .get("info", {})
                .get("os", {})
                .get("uptime")
            )

            if uptime_str:
                try:
                    # Parse the ISO 8601 datetime string to a datetime object with timezone
                    boot_time = dateutil.parser.parse(uptime_str)
                    # Calculate duration from boot time to now
                    now = datetime.now(boot_time.tzinfo or UTC)
                    uptime_duration = now - boot_time

                    # Format the duration in a human-readable way
                    return self._format_timedelta(uptime_duration)
                except (ValueError, TypeError):
                    pass

            # If that fails, try to get uptime as seconds
            uptime_seconds = (
                self.coordinator.data.get("system_info", {})
                .get("info", {})
                .get("uptime_seconds")
            )

            if uptime_seconds is not None:
                try:
                    # Convert seconds to timedelta
                    uptime_duration = timedelta(seconds=int(uptime_seconds))
                    return self._format_timedelta(uptime_duration)
                except (ValueError, TypeError):
                    pass

            # If that fails, try to get uptime directly
            uptime = self.coordinator.data.get("system_info", {}).get("uptime")
            if uptime is not None:
                if isinstance(uptime, str):
                    # If it's already a formatted string, return it
                    return uptime
                try:
                    # Try to convert to seconds and format
                    uptime_duration = timedelta(seconds=int(uptime))
                    return self._format_timedelta(uptime_duration)
                except (ValueError, TypeError):
                    pass

            # If we get here, we couldn't find a valid uptime
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
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            uptime_str = (
                self.coordinator.data.get("system_info", {})
                .get("info", {})
                .get("os", {})
                .get("uptime")
            )
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
                    "total_seconds": uptime_duration.total_seconds(),
                }
            return {}
        except (KeyError, AttributeError, TypeError, ValueError):
            return {}


class UnraidNotificationSensor(UnraidSystemEntity, SensorEntity):
    """Sensor for Unraid notifications."""

    _attr_name = "Active Notifications"
    _attr_icon = ICON_NOTIFICATION
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_native_unit_of_measurement = None
    _attr_state_class = None

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "notifications")

    @property
    def native_value(self) -> int | None:
        """Return the number of unread notifications."""
        try:
            return (
                self.coordinator.data.get("notifications", {})
                .get("overview", {})
                .get("unread", {})
                .get("total", 0)
            )
        except (KeyError, AttributeError, TypeError):
            return 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            notifications = self.coordinator.data.get("notifications", {})
            unread = notifications.get("overview", {}).get("unread", {})

            # Get notification counts by type
            info_count = unread.get("info", 0)
            warning_count = unread.get("warning", 0)
            alert_count = unread.get("alert", 0)

            # Get the most recent notifications (up to 5)
            notification_list = notifications.get("list", [])

            # Format recent notifications with user-friendly attributes
            recent_notifications = []
            for notification in notification_list[:5]:
                formatted_notification = {
                    "Title": notification.get("title", "Unknown"),
                    "Severity": self._format_importance(notification.get("importance", "INFO")),
                    "Date & Time": self._format_timestamp(notification.get("timestamp")),
                }
                recent_notifications.append(formatted_notification)

            # Return notification data with user-friendly attribute names
            return {
                "Info Notifications": info_count,
                "Warning Notifications": warning_count,
                "Alert Notifications": alert_count,
                "Recent Notifications": recent_notifications,
            }
        except (KeyError, AttributeError, TypeError):
            return {}

    def _format_importance(self, importance: str) -> str:
        """Format notification importance to user-friendly text."""
        importance_map = {
            "INFO": "Information",
            "WARNING": "Warning",
            "ALERT": "Alert",
            "ERROR": "Error",
            "CRITICAL": "Critical"
        }
        return importance_map.get(importance.upper(), importance.title())

    def _format_timestamp(self, timestamp: str | None) -> str:
        """Format ISO timestamp to user-friendly format."""
        if not timestamp:
            return "Unknown"

        try:
            # Parse the ISO 8601 timestamp
            dt = dateutil.parser.parse(timestamp)
            # Format as "May 20, 2025 6:40 PM"
            return dt.strftime("%B %d, %Y %I:%M %p")
        except (ValueError, TypeError):
            return timestamp or "Unknown"


class UnraidArrayStateSensor(UnraidArrayEntity, SensorEntity):
    """Sensor for Unraid array state."""

    _attr_name = "Array Status"
    _attr_icon = ICON_ARRAY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "state")

    @property
    def native_value(self) -> str:
        """Return the state of the sensor."""
        try:
            return (
                self.coordinator.data.get("array_status", {})
                .get("array", {})
                .get("state", "Unknown")
            )
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
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "space_used")

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor as a percentage."""
        try:
            capacity = (
                self.coordinator.data.get("array_status", {})
                .get("array", {})
                .get("capacity", {})
                .get("kilobytes", {})
            )
            free = int(capacity.get("free", "0")) if capacity.get("free") else 0
            total = int(capacity.get("total", "0")) if capacity.get("total") else 0

            if total > 0:
                used = total - free
                return round((used / total) * 100, 1)
            return 0
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            capacity = (
                self.coordinator.data.get("array_status", {})
                .get("array", {})
                .get("capacity", {})
                .get("kilobytes", {})
            )

            # Get capacity values in KiB
            used_kib = int(capacity.get("used", "0")) if capacity.get("used") else 0
            free_kib = int(capacity.get("free", "0")) if capacity.get("free") else 0
            total_kib = int(capacity.get("total", "0")) if capacity.get("total") else 0

            # Convert to bytes for formatting
            used_bytes = used_kib * 1024
            free_bytes = free_kib * 1024
            total_bytes = total_kib * 1024

            # Calculate percentage
            used_percent = round((used_kib / total_kib) * 100, 1) if total_kib > 0 else 0

            return {
                "Used Space": self._format_size(used_bytes),
                "Free Space": self._format_size(free_bytes),
                "Total Capacity": self._format_size(total_bytes),
                "Used Percentage": f"{used_percent}%",
            }
        except (KeyError, AttributeError, TypeError, ValueError):
            return {}

    def _format_size(self, size_bytes: int) -> str:
        """Format size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024**2:
            return f"{size_bytes / 1024:.2f} KiB"
        if size_bytes < 1024**3:
            return f"{size_bytes / (1024**2):.2f} MiB"
        if size_bytes < 1024**4:
            return f"{size_bytes / (1024**3):.2f} GiB"
        return f"{size_bytes / (1024**4):.2f} TiB"


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
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "space_free")

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor as a percentage."""
        try:
            # First try to get from capacity.kilobytes
            capacity_kb = (
                self.coordinator.data.get("array_status", {})
                .get("array", {})
                .get("capacity", {})
                .get("kilobytes", {})
            )

            if capacity_kb:
                free_kb = (
                    int(capacity_kb.get("free", "0")) if capacity_kb.get("free") else 0
                )
                total_kb = (
                    int(capacity_kb.get("total", "0"))
                    if capacity_kb.get("total")
                    else 0
                )

                if total_kb > 0:
                    # Return free space as percentage
                    return round((free_kb / total_kb) * 100, 1)
                return 0

            # If that fails, try to get from capacity directly
            capacity = (
                self.coordinator.data.get("array_status", {})
                .get("array", {})
                .get("capacity", {})
            )

            if capacity:
                free = int(capacity.get("free", "0")) if capacity.get("free") else 0
                total = int(capacity.get("total", "0")) if capacity.get("total") else 0

                if total > 0:
                    # Return free space as percentage
                    return round((free / total) * 100, 1)
                return 0

            # If we get here, we couldn't calculate the percentage
            return 0
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            # First try to get from capacity.kilobytes
            capacity_kb = (
                self.coordinator.data.get("array_status", {})
                .get("array", {})
                .get("capacity", {})
                .get("kilobytes", {})
            )

            if capacity_kb:
                free_kib = (
                    int(capacity_kb.get("free", "0")) if capacity_kb.get("free") else 0
                )
                total_kib = (
                    int(capacity_kb.get("total", "0"))
                    if capacity_kb.get("total")
                    else 0
                )
                used_kib = (
                    int(capacity_kb.get("used", "0")) if capacity_kb.get("used") else 0
                )

                # If used is not available, calculate it
                if used_kib == 0 and total_kib > 0 and free_kib > 0:
                    used_kib = total_kib - free_kib

                # Convert to bytes
                free_bytes = free_kib * 1024
                total_bytes = total_kib * 1024
                used_bytes = used_kib * 1024

                return {
                    "Free Space": self._format_size(free_bytes),
                    "Total Capacity": self._format_size(total_bytes),
                    "Used Space": self._format_size(used_bytes),
                    "Used Percentage": f"{round(100 - (free_kib / total_kib * 100), 1)}%" if total_kib > 0 else "0%",
                }

            # If that fails, try to get from capacity directly
            capacity = (
                self.coordinator.data.get("array_status", {})
                .get("array", {})
                .get("capacity", {})
            )

            if capacity:
                free_kib = int(capacity.get("free", "0")) if capacity.get("free") else 0
                total_kib = (
                    int(capacity.get("total", "0")) if capacity.get("total") else 0
                )
                used_kib = int(capacity.get("used", "0")) if capacity.get("used") else 0

                # If used is not available, calculate it
                if used_kib == 0 and total_kib > 0 and free_kib > 0:
                    used_kib = total_kib - free_kib

                # Convert to bytes
                free_bytes = free_kib * 1024
                total_bytes = total_kib * 1024
                used_bytes = used_kib * 1024

                return {
                    "Free Space": self._format_size(free_bytes),
                    "Total Capacity": self._format_size(total_bytes),
                    "Used Space": self._format_size(used_bytes),
                    "Used Percentage": f"{round(100 - (free_kib / total_kib * 100), 1)}%" if total_kib > 0 else "0%",
                }

            # Return empty attributes if we get here
            return {}
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return {}

    def _format_size(self, size_bytes: int) -> str:
        """Format size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024**2:
            return f"{size_bytes / 1024:.2f} KiB"
        if size_bytes < 1024**3:
            return f"{size_bytes / (1024**2):.2f} MiB"
        if size_bytes < 1024**4:
            return f"{size_bytes / (1024**3):.2f} GiB"
        return f"{size_bytes / (1024**4):.2f} TiB"


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
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "space_total")

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor as a formatted string."""
        try:
            total_kib = (
                self.coordinator.data.get("array_status", {})
                .get("array", {})
                .get("capacity", {})
                .get("kilobytes", {})
                .get("total", "0")
            )
            if total_kib:
                # Return formatted size string with auto-units
                total_bytes = int(total_kib) * 1024
                return self._format_size(total_bytes)
            return "0 B"
        except (KeyError, AttributeError, TypeError, ValueError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            capacity = (
                self.coordinator.data.get("array_status", {})
                .get("array", {})
                .get("capacity", {})
            )
            kilobytes = capacity.get("kilobytes", {})
            total_kib = kilobytes.get("total", "0")
            used_kib = kilobytes.get("used", "0")
            free_kib = kilobytes.get("free", "0")

            total_bytes = int(total_kib) * 1024 if total_kib else 0
            used_bytes = int(used_kib) * 1024 if used_kib else 0
            free_bytes = int(free_kib) * 1024 if free_kib else 0

            used_percent = (
                round((used_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0
            )
            free_percent = (
                round((free_bytes / total_bytes) * 100, 1) if total_bytes > 0 else 0
            )

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
        if size_bytes < 1024**2:
            return f"{size_bytes / 1024:.2f} KiB"
        if size_bytes < 1024**3:
            return f"{size_bytes / (1024**2):.2f} MiB"
        if size_bytes < 1024**4:
            return f"{size_bytes / (1024**3):.2f} GiB"
        return f"{size_bytes / (1024**4):.2f} TiB"


class UnraidFlashUsageSensor(UnraidSystemEntity, SensorEntity):
    """Sensor for Unraid flash drive space usage."""

    _attr_name = "Flash Drive Usage"
    _attr_icon = "mdi:usb-flash-drive"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_device_class = None
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(
        self,
        coordinator: UnraidDataUpdateCoordinator,
        server_name: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, server_name, "flash_usage")

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor as a percentage."""
        try:
            flash_info = self.coordinator.data.get("array_status", {}).get("flash", {})

            # If no flash data is available yet, return None (unavailable)
            if not flash_info:
                return None

            fs_size = int(flash_info.get("fsSize", 0))
            fs_used = int(flash_info.get("fsUsed", 0))

            if fs_size > 0:
                # Return usage as percentage
                return round((fs_used / fs_size) * 100, 1)
            return 0
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            flash_info = self.coordinator.data.get("array_status", {}).get("flash", {})

            # If no flash data is available yet, return basic attributes
            if not flash_info:
                return {
                    "Flash Drive Name": "Unknown",
                    "Device Path": "N/A",
                    "Total Capacity": "N/A",
                    "Free Space": "N/A",
                    "Used Space": "N/A",
                    "Used Percentage": "N/A",
                    "Free Percentage": "N/A",
                    "Status": "Waiting for data...",
                }

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
                "Flash Drive Name": flash_info.get("name", "flash"),
                "Device Path": flash_info.get("device", "N/A"),
                "Total Capacity": self._format_size(fs_size_bytes),
                "Free Space": self._format_size(fs_free_bytes),
                "Used Space": self._format_size(fs_used_bytes),
                "Used Percentage": f"{used_percent}%",
                "Free Percentage": f"{free_percent}%",
                "Status": "Active",
            }
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return {
                "Flash Drive Name": "Unknown",
                "Device Path": "N/A",
                "Total Capacity": "N/A",
                "Free Space": "N/A",
                "Used Space": "N/A",
                "Used Percentage": "N/A",
                "Free Percentage": "N/A",
                "Status": "Error retrieving data",
            }

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        # Always return True since the sensor should always be available
        # even when waiting for data. The native_value will return None
        # when data is not available, which is the correct behavior.
        return super().available

    @property
    def icon(self) -> str:
        """Return the icon for the sensor."""
        return "mdi:usb-flash-drive"

    def _format_size(self, size_bytes: int) -> str:
        """Format size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024**2:
            return f"{size_bytes / 1024:.2f} KiB"
        if size_bytes < 1024**3:
            return f"{size_bytes / (1024**2):.2f} MiB"
        if size_bytes < 1024**4:
            return f"{size_bytes / (1024**3):.2f} GiB"
        return f"{size_bytes / (1024**4):.2f} TiB"


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
    ) -> None:
        """Initialize the sensor."""
        # Clean disk name to handle any potential slashes
        disk_name = disk_name.replace("/", "_")
        super().__init__(coordinator, server_name, "temp", disk_id, disk_type)
        self._disk_name = disk_name
        self._attr_name = f"Disk {disk_name} Temperature"

        # Store the last known temperature to preserve it when disk is in standby
        self._last_known_temp = None
        self._last_known_attributes: dict[str, Any] = {}
        self._is_standby = False
        self._is_rotational = True  # Default to rotational for safety

    def _format_size(self, size_bytes: int) -> str:
        """Format size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024**2:
            return f"{size_bytes / 1024:.2f} KiB"
        if size_bytes < 1024**3:
            return f"{size_bytes / (1024**2):.2f} MiB"
        if size_bytes < 1024**4:
            return f"{size_bytes / (1024**3):.2f} GiB"
        return f"{size_bytes / (1024**4):.2f} TiB"

    @property
    def native_value(self) -> int | None:
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
                        _LOGGER.debug(
                            "Disk %s in standby, using last known temperature: %s°C",
                            self._disk_name,
                            self._last_known_temp,
                        )
                        return self._last_known_temp

                    # For cache disks, provide a default temperature if none is available
                    # This is a workaround for the API not returning temperature data for cache disks
                    if self._disk_type == "Cache" and not self._is_rotational:
                        _LOGGER.debug(
                            "No temperature data for cache disk %s, using default value",
                            self._disk_name,
                        )
                        return 35  # Default temperature for SSDs

                    # Otherwise, return None (unknown temperature)
                    return None

            # If disk not found but we have a last known temperature, use it
            if self._last_known_temp is not None:
                return self._last_known_temp

            # If we get here, no temperature data is available
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
                    # Active rotational drives are available
                    return super().available

            # If disk not found, not available
            return False
        except (KeyError, AttributeError, TypeError):
            return False

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
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
                        size_bytes = (
                            int(disk.get("size", 0)) * 1024 if disk.get("size") else 0
                        )
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
                            "used": size_formatted
                            if array_state == "STARTED"
                            else "0 B",
                            "free": "0 B"
                            if array_state == "STARTED"
                            else size_formatted,
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
                    size_bytes = (
                        int(disk.get("size", 0)) * 1024 if disk.get("size") else 0
                    )
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
                        fs_size = (
                            int(disk.get("fsSize", 0)) * 1024
                            if disk.get("fsSize")
                            else 0
                        )
                        fs_free = (
                            int(disk.get("fsFree", 0)) * 1024
                            if disk.get("fsFree")
                            else 0
                        )
                        fs_used = (
                            int(disk.get("fsUsed", 0)) * 1024
                            if disk.get("fsUsed")
                            else 0
                        )

                        attributes.update(
                            {
                                "fs_size": self._format_size(fs_size),
                                "fs_free": self._format_size(fs_free),
                                "fs_used": self._format_size(fs_used),
                                "fs_size_bytes": fs_size,
                                "fs_free_bytes": fs_free,
                                "fs_used_bytes": fs_used,
                            }
                        )

                        # Add usage percentage
                        if fs_size > 0:
                            attributes["usage_percent"] = round(
                                (fs_used / fs_size) * 100, 1
                            )

                    # Store the current attributes for future use
                    self._last_known_attributes = dict(attributes)

                    return attributes

            # If disk not found but we have last known attributes, use them
            if self._last_known_attributes:
                return self._last_known_attributes

            # If we get here, no attributes are available
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
    ) -> None:
        """Initialize the sensor."""
        # Clean disk name to handle any potential slashes
        disk_name = disk_name.replace("/", "_")
        self._disk_name = disk_name

        # Determine disk type based on where it's found in the array data
        disk_type = self._determine_disk_type(coordinator, disk_id)

        super().__init__(coordinator, server_name, "space_used", disk_id, disk_type)

        # Use consistent naming format with proper capitalization
        formatted_disk_name = self._format_disk_name_for_display(disk_name)
        self._attr_name = f"{formatted_disk_name} Usage"

        # Store the last known value to preserve it when disk is in standby
        self._last_known_value: float | None = None
        self._last_known_attributes: dict[str, Any] = {}

    def _format_disk_name_for_display(self, disk_name: str) -> str:
        """Format disk name for user-friendly display."""
        # Handle numbered disks (disk1, disk2, etc.)
        if disk_name.startswith("disk") and disk_name[4:].isdigit():
            disk_number = disk_name[4:]
            return f"Disk {disk_number}"

        # Handle special disk names with proper capitalization
        if disk_name.lower() == "cache":
            return "Cache"
        elif disk_name.lower() == "parity":
            return "Parity"
        elif disk_name.lower() == "garbage":
            return "Garbage"
        else:
            # For other names, capitalize first letter
            return disk_name.capitalize()

    def _translate_disk_status(self, status: str | None) -> str:
        """Translate technical disk status codes to user-friendly descriptions."""
        if not status:
            return "Unknown"

        status_translations = {
            "DISK_OK": "Healthy",
            "DISK_DSBL": "Disabled",
            "DISK_NP": "Not Present",
            "DISK_NP_DSBL": "Not Present (Disabled)",
            "DISK_INVALID": "Invalid",
            "DISK_WRONG": "Wrong Disk",
            "DISK_NEW": "New Disk",
            "DISK_EMULATED": "Emulated",
            "DISK_MISSING": "Missing",
            "DISK_ERROR": "Error",
            "DISK_UNKNOWN": "Unknown Status",
        }

        return status_translations.get(status, status)

    def _translate_disk_state(self, state: str | None) -> str:
        """Translate technical disk state codes to user-friendly descriptions."""
        if not state:
            return "Unknown"

        state_translations = {
            "ACTIVE": "Active",
            "STANDBY": "Standby (Power Saving)",
            "SPUN_DOWN": "Spun Down",
            "SPINNING_UP": "Spinning Up",
            "SPINNING_DOWN": "Spinning Down",
            "IDLE": "Idle",
            "OFFLINE": "Offline",
        }

        return state_translations.get(state.upper(), state)

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

    def _get_parity_disk_usage(self, array_state: str) -> float:
        """Get usage percentage for parity disks based on array state."""
        # Parity disks are 100% used when array is started, 0% otherwise
        value = 100.0 if array_state == "STARTED" else 0.0

        # Update last known value
        if self._last_known_value is None:
            self._last_known_value = 0.0
        self._last_known_value = value

        return value

    def _get_active_disk_usage(self, disk: dict[str, Any]) -> float:
        """Calculate usage percentage for an active disk."""
        # First try to get filesystem size and used values
        fs_size = int(disk.get("fsSize", 0)) if disk.get("fsSize") else 0
        fs_used = int(disk.get("fsUsed", 0)) if disk.get("fsUsed") else 0

        # If we have valid filesystem data, use it
        if fs_size > 0 and fs_used >= 0:
            # Calculate and store the current value
            current_value = round((fs_used / fs_size) * 100, 1)
            if self._last_known_value is None:
                self._last_known_value = 0.0
            self._last_known_value = current_value
            return current_value

        # For ZFS disks, try to get size and used from other fields
        # ZFS disks might have different field names or structure
        if disk.get("fsType", "").lower() == "zfs":
            # Try to get size and used from zfs_* fields if they exist
            zfs_size = int(disk.get("zfsSize", 0)) if disk.get("zfsSize") else 0
            zfs_used = int(disk.get("zfsUsed", 0)) if disk.get("zfsUsed") else 0

            if zfs_size > 0:
                # Calculate and store the current value
                current_value = round((zfs_used / zfs_size) * 100, 1)
                if self._last_known_value is None:
                    self._last_known_value = 0.0
                self._last_known_value = current_value
                return current_value

            # Try to get from size and free fields
            size = int(disk.get("size", 0)) if disk.get("size") else 0
            free = int(disk.get("free", 0)) if disk.get("free") else 0

            if size > 0 and free >= 0:
                used = size - free
                # Calculate and store the current value
                current_value = round((used / size) * 100, 1)
                if self._last_known_value is None:
                    self._last_known_value = 0.0
                self._last_known_value = current_value
                return current_value

        # If we can't calculate but have a previous value, use it
        if self._last_known_value is not None:
            return self._last_known_value

        # Default to 0 if we can't calculate
        return 0

    def _get_standby_disk_usage(self, disk_state: str) -> float:
        """Get usage percentage for a disk in standby mode."""
        if self._last_known_value is not None:
            _LOGGER.debug(
                "Disk %s in %s state, using last known value: %s%%",
                self._disk_name,
                disk_state,
                self._last_known_value,
            )
            return self._last_known_value

        # If no last known value, return 0 for standby disks
        return 0

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor as a percentage."""
        try:
            array_data = self.coordinator.data.get("array_status", {}).get("array", {})
            array_state = array_data.get("state", "").upper()

            # Handle parity disks differently
            if self._disk_type == "Parity":
                return self._get_parity_disk_usage(array_state)

            # Get the appropriate disk list based on type
            disks = (
                array_data.get("caches", [])
                if self._disk_type == "Cache"
                else array_data.get("disks", [])
            )

            # Find the specific disk
            for disk in disks:
                if disk.get("id") != self._disk_id:
                    continue

                # Check disk state
                disk_state = disk.get("state", "").upper()

                # For cache disks (SSDs) or active disks, calculate current value
                if self._disk_type == "Cache" or disk_state == "ACTIVE":
                    return self._get_active_disk_usage(disk)

                # For standby disks, return the last known value
                return self._get_standby_disk_usage(disk_state)

            # If disk not found but we have a last known value, use it
            if self._last_known_value is not None:
                return self._last_known_value

            # If we get here, no value is available
            return None
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            # On error, return last known value if available
            if self._last_known_value is not None:
                return self._last_known_value
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
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
                        size_bytes = (
                            int(disk.get("size", 0)) * 1024 if disk.get("size") else 0
                        )
                        size_formatted = self._format_size(size_bytes)

                        # Build attributes for parity disk
                        attributes = {
                            "Disk Name": disk.get("name"),
                            "Disk Type": self._disk_type,
                            "Capacity": size_formatted,
                            "Health Status": self._translate_disk_status(disk.get("status")),
                            "Power State": self._translate_disk_state(disk_state),
                            "Drive Type": "Hard Disk Drive (HDD)" if disk.get("rotational", True) else "Solid State Drive (SSD/NVMe)",
                            "Array Status": "Started" if array_state == "STARTED" else "Stopped",
                            "Usage": "100%" if array_state == "STARTED" else "0%",
                        }

                        # Add device path if available
                        if disk.get("device"):
                            attributes["Device Path"] = f"/dev/{disk.get('device')}"

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
                    size_bytes = (
                        int(disk.get("size", 0)) * 1024 if disk.get("size") else 0
                    )
                    size_formatted = self._format_size(size_bytes)

                    # Build base attributes
                    attributes = {
                        "Disk Name": disk.get("name"),
                        "Disk Type": self._disk_type,
                        "Capacity": size_formatted,
                        "Health Status": self._translate_disk_status(disk.get("status")),
                        "Power State": self._translate_disk_state(disk.get("state", "")),
                        "Drive Type": "Hard Disk Drive (HDD)" if disk.get("rotational", True) else "Solid State Drive (SSD/NVMe)",
                    }

                    # Add device path if available
                    if disk.get("device"):
                        attributes["Device Path"] = f"/dev/{disk.get('device')}"

                    # Add file system information if it exists
                    if "fsSize" in disk and "fsUsed" in disk and "fsFree" in disk:
                        fs_size = (
                            int(disk.get("fsSize", 0)) * 1024
                            if disk.get("fsSize")
                            else 0
                        )
                        fs_free = (
                            int(disk.get("fsFree", 0)) * 1024
                            if disk.get("fsFree")
                            else 0
                        )
                        fs_used = (
                            int(disk.get("fsUsed", 0)) * 1024
                            if disk.get("fsUsed")
                            else 0
                        )

                        attributes.update(
                            {
                                "File System Size": self._format_size(fs_size),
                                "Free Space": self._format_size(fs_free),
                                "Used Space": self._format_size(fs_used),
                                "Usage": f"{round((fs_used / fs_size) * 100, 1)}%" if fs_size > 0 else "0%",
                            }
                        )

                    # Store the current attributes for future use
                    self._last_known_attributes = dict(attributes)

                    return attributes

            # If disk not found but we have last known attributes, use them
            if self._last_known_attributes:
                return self._last_known_attributes

            # If we get here, no attributes are available
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
        if size_bytes < 1024**2:
            return f"{size_bytes / 1024:.2f} KiB"
        if size_bytes < 1024**3:
            return f"{size_bytes / (1024**2):.2f} MiB"
        if size_bytes < 1024**4:
            return f"{size_bytes / (1024**3):.2f} GiB"
        return f"{size_bytes / (1024**4):.2f} TiB"


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
    ) -> None:
        """Initialize the sensor."""
        # Clean disk name to handle any potential slashes
        disk_name = disk_name.replace("/", "_")
        self._disk_name = disk_name

        # Determine disk type based on where it's found in the array data
        disk_type = self._determine_disk_type(coordinator, disk_id)

        super().__init__(coordinator, server_name, "space_free", disk_id, disk_type)

        # Use consistent naming format: "{name} Free Space"
        self._attr_name = f"{disk_name} Free Space"

        # Store the last known value to preserve it when disk is in standby
        self._last_known_value: float | None = None
        self._last_known_attributes: dict[str, Any] = {}

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

    def _get_parity_disk_free_space(self, array_state: str) -> float:
        """Get free space percentage for parity disks based on array state."""
        # Parity disks have 0% free when array is started, 100% otherwise
        value = 0.0 if array_state == "STARTED" else 100.0

        # Update last known value
        if self._last_known_value is None:
            self._last_known_value = 0.0
        self._last_known_value = value

        return value

    def _get_active_disk_free_space(self, disk: dict[str, Any]) -> float:
        """Calculate free space percentage for an active disk."""
        fs_size = int(disk.get("fsSize", 0)) if disk.get("fsSize") else 0
        fs_free = int(disk.get("fsFree", 0)) if disk.get("fsFree") else 0

        if fs_size <= 0:
            # If we can't calculate but have a previous value, use it
            if self._last_known_value is not None:
                return self._last_known_value
            return 0

        # Calculate and store the current value
        current_value = round((fs_free / fs_size) * 100, 1)
        if self._last_known_value is None:
            self._last_known_value = 0.0
        self._last_known_value = current_value
        return current_value

    def _get_standby_disk_free_space(self, disk_state: str) -> float:
        """Get free space percentage for a disk in standby mode."""
        if self._last_known_value is not None:
            _LOGGER.debug(
                "Disk %s in %s state, using last known value: %s%%",
                self._disk_name,
                disk_state,
                self._last_known_value,
            )
            return self._last_known_value

        # If no last known value, return 0 for standby disks
        return 0

    @property
    def native_value(self) -> float | None:
        """Return the state of the sensor as a percentage."""
        try:
            array_data = self.coordinator.data.get("array_status", {}).get("array", {})
            array_state = array_data.get("state", "").upper()

            # Handle parity disks differently
            if self._disk_type == "Parity":
                return self._get_parity_disk_free_space(array_state)

            # Get the appropriate disk list based on type
            disks = (
                array_data.get("caches", [])
                if self._disk_type == "Cache"
                else array_data.get("disks", [])
            )

            # Find the specific disk
            for disk in disks:
                if disk.get("id") != self._disk_id:
                    continue

                # Check disk state
                disk_state = disk.get("state", "").upper()

                # For cache disks (SSDs) or active disks, calculate current value
                if self._disk_type == "Cache" or disk_state == "ACTIVE":
                    return self._get_active_disk_free_space(disk)

                # For standby disks, return the last known value
                return self._get_standby_disk_free_space(disk_state)

            # If disk not found but we have a last known value, use it
            if self._last_known_value is not None:
                return self._last_known_value

            # If we get here, no value is available
            return None
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            # On error, return last known value if available
            if self._last_known_value is not None:
                return self._last_known_value
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
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
                        size_bytes = (
                            int(disk.get("size", 0)) * 1024 if disk.get("size") else 0
                        )
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
                            "used": size_formatted
                            if array_state == "STARTED"
                            else "0 B",
                            "free": "0 B"
                            if array_state == "STARTED"
                            else size_formatted,
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
                    size_bytes = (
                        int(disk.get("size", 0)) * 1024 if disk.get("size") else 0
                    )
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
                        fs_size = (
                            int(disk.get("fsSize", 0)) * 1024
                            if disk.get("fsSize")
                            else 0
                        )
                        fs_free = (
                            int(disk.get("fsFree", 0)) * 1024
                            if disk.get("fsFree")
                            else 0
                        )
                        fs_used = (
                            int(disk.get("fsUsed", 0)) * 1024
                            if disk.get("fsUsed")
                            else 0
                        )

                        attributes.update(
                            {
                                "fs_size": self._format_size(fs_size),
                                "fs_free": self._format_size(fs_free),
                                "fs_used": self._format_size(fs_used),
                                "fs_size_bytes": fs_size,
                                "fs_free_bytes": fs_free,
                                "fs_used_bytes": fs_used,
                            }
                        )

                        # Add usage percentage
                        if fs_size > 0:
                            attributes["usage_percent"] = round(
                                (fs_used / fs_size) * 100, 1
                            )

                    # Store the current attributes for future use
                    self._last_known_attributes = dict(attributes)

                    return attributes

            # If disk not found but we have last known attributes, use them
            if self._last_known_attributes:
                return self._last_known_attributes

            # If we get here, no attributes are available
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
        if size_bytes < 1024**2:
            return f"{size_bytes / 1024:.2f} KiB"
        if size_bytes < 1024**3:
            return f"{size_bytes / (1024**2):.2f} MiB"
        if size_bytes < 1024**4:
            return f"{size_bytes / (1024**3):.2f} GiB"
        return f"{size_bytes / (1024**4):.2f} TiB"


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
    ) -> None:
        """Initialize the sensor."""
        # Clean share name to handle any potential slashes
        share_name_safe = share_name.replace("/", "_")
        super().__init__(coordinator, server_name, "space_used", share_name)
        self._attr_name = f"Share {share_name_safe} Usage"

    @property
    def native_value(self) -> float | None:
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

            # If we get here, the share wasn't found
            return None
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            shares = self.coordinator.data.get("shares", [])

            for share in shares:
                if share.get("name") == self._share_name:
                    # Convert KiB values to bytes for formatting
                    free_bytes = (
                        int(share.get("free", 0)) * 1024 if share.get("free") else 0
                    )
                    used_bytes = (
                        int(share.get("used", 0)) * 1024 if share.get("used") else 0
                    )
                    size_bytes = free_bytes + used_bytes

                    # Calculate percentage
                    used_percent = (
                        round((used_bytes / size_bytes) * 100, 1)
                        if size_bytes > 0
                        else 0
                    )

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
                        "free_percent": round(100 - used_percent, 1)
                        if size_bytes > 0
                        else 0,
                        "total_bytes": size_bytes,
                        "free_bytes": free_bytes,
                        "used_bytes": used_bytes,
                        "total_gib": total_gib,
                        "free_gib": free_gib,
                        "used_gib": used_gib,
                    }

            # If we get here, the share wasn't found
            return {}
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return {}

    def _format_size(self, size_bytes: int) -> str:
        """Format size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024**2:
            return f"{size_bytes / 1024:.2f} KiB"
        if size_bytes < 1024**3:
            return f"{size_bytes / (1024**2):.2f} MiB"
        if size_bytes < 1024**4:
            return f"{size_bytes / (1024**3):.2f} GiB"
        return f"{size_bytes / (1024**4):.2f} TiB"


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
    ) -> None:
        """Initialize the sensor."""
        # Clean share name to handle any potential slashes
        share_name_safe = share_name.replace("/", "_")
        super().__init__(coordinator, server_name, "space_free", share_name)
        self._attr_name = f"Share {share_name_safe} Free Space"

    @property
    def native_value(self) -> float | None:
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

            # If we get here, the share wasn't found
            return None
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        try:
            shares = self.coordinator.data.get("shares", [])

            for share in shares:
                if share.get("name") == self._share_name:
                    # Convert KiB values to bytes for formatting
                    free_bytes = (
                        int(share.get("free", 0)) * 1024 if share.get("free") else 0
                    )
                    used_bytes = (
                        int(share.get("used", 0)) * 1024 if share.get("used") else 0
                    )
                    size_bytes = free_bytes + used_bytes

                    # Calculate percentage
                    free_percent = (
                        round((free_bytes / size_bytes) * 100, 1)
                        if size_bytes > 0
                        else 0
                    )

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
                        "used_percent": round(100 - free_percent, 1)
                        if size_bytes > 0
                        else 0,
                        "total_bytes": size_bytes,
                        "free_bytes": free_bytes,
                        "used_bytes": used_bytes,
                        "total_gib": total_gib,
                        "free_gib": free_gib,
                        "used_gib": used_gib,
                    }

            # If we get here, the share wasn't found
            return {}
        except (KeyError, AttributeError, TypeError, ValueError, ZeroDivisionError):
            return {}

    def _format_size(self, size_bytes: int) -> str:
        """Format size to appropriate unit."""
        if size_bytes < 1024:
            return f"{size_bytes} B"
        if size_bytes < 1024**2:
            return f"{size_bytes / 1024:.2f} KiB"
        if size_bytes < 1024**3:
            return f"{size_bytes / (1024**2):.2f} MiB"
        if size_bytes < 1024**4:
            return f"{size_bytes / (1024**3):.2f} GiB"
        return f"{size_bytes / (1024**4):.2f} TiB"

