"""Comprehensive diagnostics support for Unraid Connect integration."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import DOMAIN

# Sensitive data to redact for privacy
REDACT_FIELDS = {
    CONF_API_KEY,
    "token",
    "credentials",
    "uuid",
    "id",
    "serialNum",           # Disk serial numbers
    "serial_number",       # Alternative serial field
    "mac",                 # MAC addresses
    "macAddress",          # Alternative MAC field
    "ip",                  # IP addresses
    "ipAddress",           # Alternative IP field
    CONF_HOST,             # Host/server address
    "hostname",            # Hostname
    "device_id",           # Device identifiers
    "unique_id",           # Unique identifiers
}

REDACT_CONFIG = {"entry_id", CONF_API_KEY, CONF_HOST}

# Cache performance tracking
_cache_stats = {
    "hits": 0,
    "misses": 0,
    "errors": 0,
    "total_calls": 0,
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return comprehensive diagnostics for the Unraid Connect integration."""
    try:
        # Get the coordinator and API client for this entry
        coordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
        api_client = hass.data[DOMAIN][entry.entry_id]["api"]

        # Start timing the diagnostics collection
        start_time = datetime.now()

        # Collect all diagnostic data
        diagnostics_data = {
            "integration_info": await _get_integration_info(coordinator, entry),
            "api_connection_status": await _get_api_connection_status(api_client),
            "cache_performance": _get_cache_performance_metrics(coordinator),
            "sensor_health": await _get_sensor_health_data(hass, entry),
            "integration_performance": _get_integration_performance(coordinator),
            "system_information": _get_system_information(coordinator),
            "configuration_data": _get_configuration_data(entry),
            "entity_registry_info": await _get_entity_registry_info(hass, entry),
            "diagnostics_collection_time": (datetime.now() - start_time).total_seconds(),
        }

        # Redact sensitive information from the entire diagnostics data
        return async_redact_data(diagnostics_data, REDACT_FIELDS)

    except Exception as err:
        # Return basic diagnostics if comprehensive collection fails
        return {
            "error": f"Failed to collect comprehensive diagnostics: {err}",
            "basic_info": {
                "entry_id": "REDACTED",
                "domain": DOMAIN,
                "last_update_success": getattr(coordinator, "last_update_success", None),
                "last_update_time": coordinator.last_update_time.isoformat()
                if hasattr(coordinator, "last_update_time") and coordinator.last_update_time
                else None,
            }
        }


async def _get_integration_info(coordinator, entry: ConfigEntry) -> dict[str, Any]:
    """Get basic integration information."""
    return {
        "domain": DOMAIN,
        "version": entry.version,
        "title": entry.title,
        "state": entry.state.name if entry.state else "unknown",
        "source": entry.source,
        "last_update_success": coordinator.last_update_success,
        "last_update_time": coordinator.last_update_time.isoformat()
        if coordinator.last_update_time else None,
        "update_interval_seconds": coordinator.update_interval.total_seconds()
        if coordinator.update_interval else None,
        "startup_time": coordinator._startup_time.isoformat()
        if hasattr(coordinator, "_startup_time") else None,
        "uptime_seconds": (datetime.now() - coordinator._startup_time).total_seconds()
        if hasattr(coordinator, "_startup_time") else None,
    }


async def _get_api_connection_status(api_client) -> dict[str, Any]:
    """Get API connection status and health information."""
    connection_status = {
        "endpoint_configured": bool(getattr(api_client, "base_url", None)),
        "api_key_configured": bool(getattr(api_client, "api_key", None)),
        "last_successful_call": None,
        "connection_test_result": None,
        "response_time_ms": None,
    }

    # Test API connection with timing
    try:
        start_time = datetime.now()
        test_result = await api_client.validate_connection()
        response_time = (datetime.now() - start_time).total_seconds() * 1000

        connection_status.update({
            "connection_test_result": "success" if test_result else "failed",
            "response_time_ms": round(response_time, 2),
            "last_successful_call": datetime.now().isoformat(),
        })
    except Exception as err:
        connection_status.update({
            "connection_test_result": "error",
            "connection_error": str(err),
        })

    return connection_status


def _get_cache_performance_metrics(coordinator) -> dict[str, Any]:
    """Get comprehensive cache performance metrics."""
    cache_metrics = {
        "cache_categories": {},
        "memory_usage": {},
        "performance_stats": {},
    }

    # Cache TTL configuration
    if hasattr(coordinator, "_cache_ttl"):
        cache_metrics["cache_categories"] = {
            category: {
                "ttl_seconds": ttl,
                "ttl_minutes": round(ttl / 60, 2),
                "frequency_tier": _get_frequency_tier(ttl),
            }
            for category, ttl in coordinator._cache_ttl.items()
        }

    # Cache timestamps and validity
    if hasattr(coordinator, "_cache_timestamps"):
        current_time = datetime.now()
        cache_metrics["cache_status"] = {}

        for category, timestamp in coordinator._cache_timestamps.items():
            age_seconds = (current_time - timestamp).total_seconds()
            ttl = coordinator._cache_ttl.get(category, 60)

            cache_metrics["cache_status"][category] = {
                "last_updated": timestamp.isoformat(),
                "age_seconds": round(age_seconds, 2),
                "age_minutes": round(age_seconds / 60, 2),
                "is_valid": age_seconds < ttl,
                "expires_in_seconds": max(0, ttl - age_seconds),
            }

    # Memory usage estimation
    if hasattr(coordinator, "_data_cache"):
        total_entries = len(coordinator._data_cache)
        cache_metrics["memory_usage"] = {
            "total_cache_entries": total_entries,
            "cache_categories_count": len(coordinator._cache_ttl) if hasattr(coordinator, "_cache_ttl") else 0,
            "estimated_memory_kb": total_entries * 10,  # Rough estimate
        }

    # Performance statistics
    cache_metrics["performance_stats"] = {
        "cache_hits": _cache_stats.get("hits", 0),
        "cache_misses": _cache_stats.get("misses", 0),
        "cache_errors": _cache_stats.get("errors", 0),
        "total_calls": _cache_stats.get("total_calls", 0),
        "hit_ratio": (_cache_stats.get("hits", 0) / max(_cache_stats.get("total_calls", 1), 1)) * 100,
    }

    return cache_metrics


def _get_frequency_tier(ttl_seconds: int) -> str:
    """Determine the frequency tier based on TTL value."""
    if ttl_seconds <= 120:  # 2 minutes or less
        return "real-time"
    elif ttl_seconds <= 900:  # 15 minutes or less
        return "medium-frequency"
    else:
        return "static/semi-static"


async def _get_sensor_health_data(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Get comprehensive sensor health and status information."""
    entity_registry = er.async_get(hass)

    # Get all entities for this integration
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)

    sensor_health = {
        "total_entities": len(entities),
        "entities_by_platform": {},
        "entities_by_status": {"available": 0, "unavailable": 0, "unknown": 0},
        "disk_health_sensors": {},
        "temperature_sensors": {},
        "usage_sensors": {},
        "binary_sensors": {},
        "switches": {},
        "buttons": {},
        "problematic_entities": [],
    }

    # Categorize entities by platform
    for entity in entities:
        platform = entity.platform
        if platform not in sensor_health["entities_by_platform"]:
            sensor_health["entities_by_platform"][platform] = 0
        sensor_health["entities_by_platform"][platform] += 1

        # Get current state
        state = hass.states.get(entity.entity_id)
        if state:
            if state.state == "unavailable":
                sensor_health["entities_by_status"]["unavailable"] += 1
                sensor_health["problematic_entities"].append({
                    "entity_id": entity.entity_id,
                    "platform": platform,
                    "issue": "unavailable",
                    "last_updated": state.last_updated.isoformat() if state.last_updated else None,
                })
            elif state.state == "unknown":
                sensor_health["entities_by_status"]["unknown"] += 1
            else:
                sensor_health["entities_by_status"]["available"] += 1

            # Categorize specific sensor types
            if "health" in entity.entity_id and platform == "binary_sensor":
                sensor_health["disk_health_sensors"][entity.entity_id] = {
                    "state": state.state,
                    "last_updated": state.last_updated.isoformat() if state.last_updated else None,
                    "attributes": dict(state.attributes) if state.attributes else {},
                }
            elif "temperature" in entity.entity_id and platform == "sensor":
                sensor_health["temperature_sensors"][entity.entity_id] = {
                    "state": state.state,
                    "unit": state.attributes.get("unit_of_measurement"),
                    "last_updated": state.last_updated.isoformat() if state.last_updated else None,
                }
            elif "usage" in entity.entity_id and platform == "sensor":
                sensor_health["usage_sensors"][entity.entity_id] = {
                    "state": state.state,
                    "unit": state.attributes.get("unit_of_measurement"),
                    "last_updated": state.last_updated.isoformat() if state.last_updated else None,
                }
            elif platform == "binary_sensor":
                sensor_health["binary_sensors"][entity.entity_id] = {
                    "state": state.state,
                    "last_updated": state.last_updated.isoformat() if state.last_updated else None,
                }
            elif platform == "switch":
                sensor_health["switches"][entity.entity_id] = {
                    "state": state.state,
                    "last_updated": state.last_updated.isoformat() if state.last_updated else None,
                }
            elif platform == "button":
                sensor_health["buttons"][entity.entity_id] = {
                    "last_updated": state.last_updated.isoformat() if state.last_updated else None,
                }

    return sensor_health


def _get_integration_performance(coordinator) -> dict[str, Any]:
    """Get integration performance metrics."""
    performance_data = {
        "coordinator_stats": {
            "last_update_success": coordinator.last_update_success,
            "last_update_time": coordinator.last_update_time.isoformat()
            if coordinator.last_update_time else None,
            "update_interval_seconds": coordinator.update_interval.total_seconds()
            if coordinator.update_interval else None,
        },
        "api_call_frequency": {},
        "error_tracking": {},
        "optimization_metrics": {},
    }

    # Calculate API call frequency based on cache TTL values
    if hasattr(coordinator, "_cache_ttl"):
        total_calls_per_hour = 0
        for category, ttl in coordinator._cache_ttl.items():
            calls_per_hour = 3600 / ttl  # 3600 seconds in an hour
            performance_data["api_call_frequency"][category] = {
                "ttl_seconds": ttl,
                "calls_per_hour": round(calls_per_hour, 2),
                "calls_per_day": round(calls_per_hour * 24, 2),
            }
            total_calls_per_hour += calls_per_hour

        performance_data["api_call_frequency"]["total_calls_per_hour"] = round(total_calls_per_hour, 2)
        performance_data["api_call_frequency"]["total_calls_per_day"] = round(total_calls_per_hour * 24, 2)

        # Calculate optimization impact (compared to 30-second intervals for all)
        baseline_calls_per_hour = len(coordinator._cache_ttl) * (3600 / 30)  # All at 30 seconds
        optimization_percentage = ((baseline_calls_per_hour - total_calls_per_hour) / baseline_calls_per_hour) * 100

        performance_data["optimization_metrics"] = {
            "baseline_calls_per_hour": round(baseline_calls_per_hour, 2),
            "optimized_calls_per_hour": round(total_calls_per_hour, 2),
            "reduction_percentage": round(optimization_percentage, 2),
            "calls_saved_per_day": round((baseline_calls_per_hour - total_calls_per_hour) * 24, 2),
        }

    return performance_data


def _get_system_information(coordinator) -> dict[str, Any]:
    """Get Unraid system information from coordinator data."""
    system_info = {
        "server_details": {},
        "disk_configuration": {},
        "array_status": {},
        "container_summary": {},
        "vm_summary": {},
    }

    # Extract system information
    if coordinator.data and "system_info" in coordinator.data:
        sys_data = coordinator.data["system_info"]
        if "info" in sys_data:
            info = sys_data["info"]

            # Server details (redacted sensitive info)
            if "os" in info:
                system_info["server_details"]["os"] = {
                    "platform": info["os"].get("platform"),
                    "distro": info["os"].get("distro"),
                    "release": info["os"].get("release"),
                    "kernel": info["os"].get("kernel"),
                }

            if "cpu" in info:
                system_info["server_details"]["cpu"] = {
                    "manufacturer": info["cpu"].get("manufacturer"),
                    "brand": info["cpu"].get("brand"),
                    "cores": info["cpu"].get("cores"),
                    "threads": info["cpu"].get("threads"),
                }

    # Extract array status
    if coordinator.data and "array_status" in coordinator.data:
        array_data = coordinator.data["array_status"]
        if "array" in array_data:
            array_info = array_data["array"]

            system_info["array_status"] = {
                "state": array_info.get("state"),
                "disk_count": len(array_info.get("disks", [])),
                "parity_count": len(array_info.get("parities", [])),
                "cache_count": len(array_info.get("caches", [])),
            }

            # Disk configuration summary
            disks = array_info.get("disks", [])
            if disks:
                disk_types = {}
                disk_sizes = []
                for disk in disks:
                    disk_type = disk.get("type", "unknown")
                    disk_types[disk_type] = disk_types.get(disk_type, 0) + 1

                    # Extract size information if available
                    if "fsSize" in disk:
                        disk_sizes.append(disk["fsSize"])

                system_info["disk_configuration"] = {
                    "total_disks": len(disks),
                    "disk_types": disk_types,
                    "total_capacity_mb": sum(disk_sizes) if disk_sizes else None,
                }

    # Container summary
    if coordinator.data and "docker_containers" in coordinator.data:
        containers = coordinator.data["docker_containers"].get("docker", {}).get("containers", [])
        running_containers = [c for c in containers if c.get("state") == "RUNNING"]

        system_info["container_summary"] = {
            "total_containers": len(containers),
            "running_containers": len(running_containers),
            "stopped_containers": len(containers) - len(running_containers),
        }

    # VM summary
    if coordinator.data and "vms" in coordinator.data:
        vm_data = coordinator.data["vms"]
        system_info["vm_summary"] = {
            "vms_available": bool(vm_data and vm_data != {}),
            "vm_count": len(vm_data.get("domains", [])) if isinstance(vm_data.get("domains"), list) else 0,
        }

    return system_info


def _get_configuration_data(entry: ConfigEntry) -> dict[str, Any]:
    """Get sanitized configuration data."""
    config_data = {
        "entry_info": {
            "title": entry.title,
            "version": entry.version,
            "source": entry.source,
            "state": entry.state.name if entry.state else "unknown",
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
            "modified_at": entry.modified_at.isoformat() if entry.modified_at else None,
        },
        "options": dict(entry.options) if entry.options else {},
        "data_keys": list(entry.data.keys()) if entry.data else [],
        "has_api_key": CONF_API_KEY in entry.data if entry.data else False,
        "has_host": CONF_HOST in entry.data if entry.data else False,
    }

    return config_data


async def _get_entity_registry_info(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Get entity registry information for troubleshooting."""
    entity_registry = er.async_get(hass)
    entities = er.async_entries_for_config_entry(entity_registry, entry.entry_id)

    registry_info = {
        "total_entities": len(entities),
        "entities_by_platform": {},
        "disabled_entities": [],
        "entities_with_issues": [],
    }

    for entity in entities:
        # Count by platform
        platform = entity.platform
        if platform not in registry_info["entities_by_platform"]:
            registry_info["entities_by_platform"][platform] = 0
        registry_info["entities_by_platform"][platform] += 1

        # Track disabled entities
        if entity.disabled:
            registry_info["disabled_entities"].append({
                "entity_id": entity.entity_id,
                "platform": platform,
                "disabled_by": entity.disabled_by.name if entity.disabled_by else "unknown",
            })

        # Check for potential issues
        state = hass.states.get(entity.entity_id)
        if state and state.state in ["unavailable", "unknown"]:
            registry_info["entities_with_issues"].append({
                "entity_id": entity.entity_id,
                "platform": platform,
                "state": state.state,
                "last_updated": state.last_updated.isoformat() if state.last_updated else None,
            })

    return registry_info
