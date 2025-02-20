"""
Sensor platform for the Unraid integration.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Final

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfTemperature,
    UnitOfInformation,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import DOMAIN, LOGGER
from .coordinator import UnraidDataUpdateCoordinator
from .entity import UnraidEntity, UnraidDockerEntity

@dataclass
class UnraidSensorEntityDescription(SensorEntityDescription):
    """Class describing Unraid sensor entities."""
    value_fn: Callable[[dict[str, Any]], StateType] = lambda _: None
    available_fn: Callable[[dict[str, Any]], bool] = lambda _: True
    entity_category: EntityCategory | None = None
    entity_registry_enabled_default: bool = True


SYSTEM_SENSORS: Final[tuple[UnraidSensorEntityDescription, ...]] = (
    UnraidSensorEntityDescription(
        key="cpu_cores",
        translation_key="cpu_cores",
        name="CPU Cores",
        icon="mdi:cpu-64-bit",
        value_fn=lambda data: data["system"]["cpu"]["cores"],
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    UnraidSensorEntityDescription(
        key="cpu_threads",
        translation_key="cpu_threads",
        name="CPU Threads",
        icon="mdi:cpu-64-bit",
        value_fn=lambda data: data["system"]["cpu"]["threads"],
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    UnraidSensorEntityDescription(
        key="cpu_temperature",
        translation_key="cpu_temperature",
        name="CPU Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data["system"]["cpu"].get("temperature"),
    ),
    UnraidSensorEntityDescription(
        key="cpu_load",
        translation_key="cpu_load",
        name="CPU Load",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cpu-64-bit",
        value_fn=lambda data: (
            round(data["system"]["cpu"]["load"]["currentLoad"], 1)
            if "load" in data["system"]["cpu"] and "currentLoad" in data["system"]["cpu"]["load"]
            else None
        ),
    ),
    UnraidSensorEntityDescription(
        key="memory_used_percent",
        translation_key="memory_used_percent",
        name="Memory Usage",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
        value_fn=lambda data: (
            round(data["system"]["memory"]["used"] / data["system"]["memory"]["total"] * 100, 1)
            if "memory" in data["system"] 
            and "used" in data["system"]["memory"] 
            and "total" in data["system"]["memory"]
            and data["system"]["memory"]["total"] > 0
            else None
        ),
    ),
    UnraidSensorEntityDescription(
        key="memory_available",
        translation_key="memory_available",
        name="Memory Available",
        native_unit_of_measurement=UnitOfInformation.GIGABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
        value_fn=lambda data: (
            round(data["system"]["memory"]["available"] / 1024 / 1024 / 1024, 2)
            if "memory" in data["system"] and "available" in data["system"]["memory"]
            else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    UnraidSensorEntityDescription(
        key="uptime",
        translation_key="uptime",
        name="Uptime",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        value_fn=lambda data: data["system"]["os"]["uptime"],
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

ARRAY_SENSORS: Final[tuple[UnraidSensorEntityDescription, ...]] = (
    UnraidSensorEntityDescription(
        key="array_state",
        translation_key="array_state",
        name="Array State",
        icon="mdi:harddisk",
        value_fn=lambda data: data["array"]["state"],
    ),
    UnraidSensorEntityDescription(
        key="array_capacity",
        translation_key="array_capacity",
        name="Array Capacity",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: (
            round(
                (data["array"]["capacity"]["disks"]["used"] /
                 data["array"]["capacity"]["disks"]["total"]) * 100,
                1
            )
            if "capacity" in data["array"] 
            and "disks" in data["array"]["capacity"]
            and "used" in data["array"]["capacity"]["disks"]
            and "total" in data["array"]["capacity"]["disks"]
            and data["array"]["capacity"]["disks"]["total"] > 0
            else None
        ),
    ),
    UnraidSensorEntityDescription(
        key="array_size",
        translation_key="array_size",
        name="Array Size",
        native_unit_of_measurement=UnitOfInformation.TERABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:harddisk",
        value_fn=lambda data: (
            round(data["array"]["capacity"]["disks"]["total"] / 1024 / 1024 / 1024 / 1024, 2)
            if "capacity" in data["array"] 
            and "disks" in data["array"]["capacity"]
            and "total" in data["array"]["capacity"]["disks"]
            else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    UnraidSensorEntityDescription(
        key="array_used",
        translation_key="array_used",
        name="Array Used",
        native_unit_of_measurement=UnitOfInformation.TERABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:harddisk",
        value_fn=lambda data: (
            round(data["array"]["capacity"]["disks"]["used"] / 1024 / 1024 / 1024 / 1024, 2)
            if "capacity" in data["array"] 
            and "disks" in data["array"]["capacity"]
            and "used" in data["array"]["capacity"]["disks"]
            else None
        ),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    UnraidSensorEntityDescription(
        key="array_free",
        translation_key="array_free",
        name="Array Free",
        native_unit_of_measurement=UnitOfInformation.TERABYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:harddisk",
        value_fn=lambda data: (
            round(data["array"]["capacity"]["disks"]["free"] / 1024 / 1024 / 1024 / 1024, 2)
            if "capacity" in data["array"] 
            and "disks" in data["array"]["capacity"]
            and "free" in data["array"]["capacity"]["disks"]
            else None
        ),
    ),
    UnraidSensorEntityDescription(
        key="parity_check_progress",
        translation_key="parity_check_progress",
        name="Parity Check Progress",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:harddisk-plus",
        value_fn=lambda data: (
            data["array"]["parityCheckProgress"]
            if data["array"].get("parityCheckActive") and "parityCheckProgress" in data["array"]
            else None
        ),
        available_fn=lambda data: data["array"].get("parityCheckActive", False),
    ),
    UnraidSensorEntityDescription(
        key="parity_check_speed",
        translation_key="parity_check_speed",
        name="Parity Check Speed",
        native_unit_of_measurement=UnitOfInformation.MEGABYTES_PER_SECOND,
        device_class=SensorDeviceClass.DATA_RATE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:harddisk-plus",
        value_fn=lambda data: (
            data["array"]["parityCheckSpeed"]
            if data["array"].get("parityCheckActive") and "parityCheckSpeed" in data["array"]
            else None
        ),
        available_fn=lambda data: data["array"].get("parityCheckActive", False),
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    UnraidSensorEntityDescription(
        key="parity_check_eta",
        translation_key="parity_check_eta",
        name="Parity Check ETA",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        icon="mdi:timer-outline",
        value_fn=lambda data: (
            data["array"]["parityCheckTotalSec"] - data["array"]["parityCheckElapsedSec"]
            if (data["array"].get("parityCheckActive") and 
                "parityCheckTotalSec" in data["array"] and
                "parityCheckElapsedSec" in data["array"] and
                data["array"]["parityCheckTotalSec"] > data["array"]["parityCheckElapsedSec"])
            else None
        ),
        available_fn=lambda data: data["array"].get("parityCheckActive", False),
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Unraid sensor based on a config entry."""
    coordinator: UnraidDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    
    LOGGER.debug("Setting up Unraid sensors")
    entities = []
    
    # Add system sensors
    for description in SYSTEM_SENSORS:
        LOGGER.debug("Adding system sensor: %s", description.key)
        entities.append(
            UnraidSensor(
                coordinator=coordinator,
                config_entry=entry,
                description=description,
            )
        )

    # Add array sensors
    for description in ARRAY_SENSORS:
        LOGGER.debug("Adding array sensor: %s", description.key)
        entities.append(
            UnraidSensor(
                coordinator=coordinator,
                config_entry=entry,
                description=description,
            )
        )
        
    # Add disk temperature sensors
    if coordinator.data and "array" in coordinator.data and "disks" in coordinator.data["array"]:
        for disk in coordinator.data["array"]["disks"]:
            if "name" in disk and "temp" in disk and disk.get("name"):
                disk_name = disk["name"]
                LOGGER.debug("Adding disk temperature sensor for %s", disk_name)
                
                entities.append(
                    UnraidDiskTempSensor(
                        coordinator=coordinator,
                        config_entry=entry,
                        disk_id=disk.get("id", disk_name),
                        disk_name=disk_name,
                    )
                )
    
    # Add Docker container usage sensors
    if coordinator.data and "docker" in coordinator.data:
        for container in coordinator.data["docker"]:
            if "names" in container and container["names"] and "id" in container:
                container_name = container["names"][0] if isinstance(container["names"], list) else container["names"]
                
                # Only add detailed sensors for containers that report usage metrics
                if "cpuUsage" in container or "memUsage" in container:
                    LOGGER.debug("Adding Docker container usage sensors for %s", container_name)
                    
                    if "cpuUsage" in container:
                        entities.append(
                            UnraidDockerCpuSensor(
                                coordinator=coordinator,
                                config_entry=entry,
                                container_id=container["id"],
                                container_name=container_name,
                            )
                        )
                        
                    if "memUsage" in container:
                        entities.append(
                            UnraidDockerMemorySensor(
                                coordinator=coordinator,
                                config_entry=entry,
                                container_id=container["id"],
                                container_name=container_name,
                            )
                        )
                        
                    if "memPercent" in container:
                        entities.append(
                            UnraidDockerMemoryPercentSensor(
                                coordinator=coordinator,
                                config_entry=entry,
                                container_id=container["id"],
                                container_name=container_name,
                            )
                        )
    
    async_add_entities(entities)
    LOGGER.info("Added %d Unraid sensors", len(entities))

class UnraidSensor(UnraidEntity, SensorEntity):
    """Sensor for Unraid integration."""

    entity_description: UnraidSensorEntityDescription

    def __init__(
        self,
        coordinator,
        config_entry,
        description: UnraidSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, config_entry, description)
        
    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        try:
            return self.entity_description.value_fn(self.coordinator.data)
        except (KeyError, TypeError) as err:
            LOGGER.warning("Error getting state for %s: %s", 
                          self.entity_id, err)
            return None
            
    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        if not super().available:
            return False
            
        try:
            return self.entity_description.available_fn(self.coordinator.data)
        except (KeyError, TypeError):
            return False


class UnraidDiskTempSensor(UnraidEntity, SensorEntity):
    """Temperature sensor for an Unraid disk."""

    def __init__(
        self,
        coordinator,
        config_entry,
        disk_id,
        disk_name,
    ) -> None:
        """Initialize the disk temperature sensor."""
        super().__init__(coordinator, config_entry)
        self._disk_id = disk_id
        self._disk_name = disk_name
        self._attr_unique_id = f"{config_entry.entry_id}_disk_{disk_id}_temp"
        self._attr_name = f"Disk {disk_name} Temperature"
        self._attr_device_class = SensorDeviceClass.TEMPERATURE
        self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_has_entity_name = True
        LOGGER.debug("Initialized disk temperature sensor: %s", self._attr_unique_id)
        
    @property
    def native_value(self) -> StateType:
        """Return the temperature of the disk."""
        try:
            if not self.coordinator.data or "array" not in self.coordinator.data or "disks" not in self.coordinator.data["array"]:
                return None
                
            for disk in self.coordinator.data["array"]["disks"]:
                if ((disk.get("id") == self._disk_id or disk.get("name") == self._disk_name) and 
                    "temp" in disk):
                    return disk["temp"]
                    
            return None
                
        except Exception as err:
            LOGGER.warning("Error getting disk temperature: %s", err)
            return None
            
    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        attrs = {}
        
        try:
            if not self.coordinator.data or "array" not in self.coordinator.data or "disks" not in self.coordinator.data["array"]:
                return attrs
                
            for disk in self.coordinator.data["array"]["disks"]:
                if disk.get("id") == self._disk_id or disk.get("name") == self._disk_name:
                    attrs["status"] = disk.get("status")
                    attrs["size"] = disk.get("size")
                    attrs["interface"] = disk.get("interface")
                    attrs["rotational"] = disk.get("rotational", True)
                    attrs["serial"] = disk.get("serial")
                    attrs["model"] = disk.get("model")
                    
                    if "numErrors" in disk:
                        attrs["errors"] = disk["numErrors"]
                    
                    break
                    
        except Exception as err:
            LOGGER.warning("Error getting disk attributes: %s", err)
            
        return attrs


class UnraidDockerCpuSensor(UnraidDockerEntity, SensorEntity):
    """CPU usage sensor for an Unraid Docker container."""

    def __init__(
        self,
        coordinator,
        config_entry,
        container_id,
        container_name,
    ) -> None:
        """Initialize the Docker CPU usage sensor."""
        super().__init__(coordinator, config_entry, container_id, container_name)
        self._attr_unique_id = f"{config_entry.entry_id}_docker_{container_id}_cpu"
        self._attr_name = f"{container_name} CPU Usage"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:cpu-64-bit"
        LOGGER.debug("Initialized Docker CPU usage sensor: %s", self._attr_unique_id)
        
    @property
    def native_value(self) -> StateType:
        """Return the CPU usage of the container."""
        container = self._get_container_data()
        if container is None or "cpuUsage" not in container:
            return None
            
        # Some implementations return this as a string percentage
        if isinstance(container["cpuUsage"], str) and container["cpuUsage"].endswith('%'):
            try:
                return float(container["cpuUsage"].rstrip('%'))
            except (ValueError, TypeError):
                return None
                
        return container["cpuUsage"]


class UnraidDockerMemorySensor(UnraidDockerEntity, SensorEntity):
    """Memory usage sensor for an Unraid Docker container."""

    def __init__(
        self,
        coordinator,
        config_entry,
        container_id,
        container_name,
    ) -> None:
        """Initialize the Docker memory usage sensor."""
        super().__init__(coordinator, config_entry, container_id, container_name)
        self._attr_unique_id = f"{config_entry.entry_id}_docker_{container_id}_memory"
        self._attr_name = f"{container_name} Memory Usage"
        self._attr_device_class = SensorDeviceClass.DATA_SIZE
        self._attr_native_unit_of_measurement = UnitOfInformation.MEGABYTES
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:memory"
        LOGGER.debug("Initialized Docker memory usage sensor: %s", self._attr_unique_id)
        
    @property
    def native_value(self) -> StateType:
        """Return the memory usage of the container."""
        container = self._get_container_data()
        if container is None or "memUsage" not in container:
            return None
            
        # Handle different units that might be returned
        if isinstance(container["memUsage"], str):
            mem_usage = container["memUsage"].lower()
            
            # Convert to MB if in different units
            if mem_usage.endswith('kb'):
                try:
                    return round(float(mem_usage.rstrip('kb')) / 1024, 2)
                except (ValueError, TypeError):
                    return None
            elif mem_usage.endswith('mb'):
                try:
                    return float(mem_usage.rstrip('mb'))
                except (ValueError, TypeError):
                    return None
            elif mem_usage.endswith('gb'):
                try:
                    return float(mem_usage.rstrip('gb')) * 1024
                except (ValueError, TypeError):
                    return None
                    
        return container["memUsage"]


class UnraidDockerMemoryPercentSensor(UnraidDockerEntity, SensorEntity):
    """Memory percent sensor for an Unraid Docker container."""

    def __init__(
        self,
        coordinator,
        config_entry,
        container_id,
        container_name,
    ) -> None:
        """Initialize the Docker memory percent sensor."""
        super().__init__(coordinator, config_entry, container_id, container_name)
        self._attr_unique_id = f"{config_entry.entry_id}_docker_{container_id}_memory_percent"
        self._attr_name = f"{container_name} Memory Percent"
        self._attr_device_class = SensorDeviceClass.BATTERY
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_icon = "mdi:memory"
        LOGGER.debug("Initialized Docker memory percent sensor: %s", self._attr_unique_id)
        
    @property
    def native_value(self) -> StateType:
        """Return the memory percent of the container."""
        container = self._get_container_data()
        if container is None or "memPercent" not in container:
            return None
            
        # Some implementations return this as a string percentage
        if isinstance(container["memPercent"], str) and container["memPercent"].endswith('%'):
            try:
                return float(container["memPercent"].rstrip('%'))
            except (ValueError, TypeError):
                return None
                
        return container["memPercent"]