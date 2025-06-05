"""Repair flows for Unraid Connect integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant import data_entry_flow
from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN


class ApiConnectionRepairFlow(RepairsFlow):
    """Handler for API connection issues."""

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the first step of API connection repair."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the confirm step of API connection repair."""
        if user_input is not None:
            # Test the API connection
            try:
                coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]["coordinator"]
                api_client = self.hass.data[DOMAIN][self.config_entry.entry_id]["api"]
                
                # Attempt to validate connection
                connection_valid = await api_client.validate_connection()
                
                if connection_valid:
                    # Connection is working, remove the issue
                    ir.async_delete_issue(self.hass, DOMAIN, "api_connection_failed")
                    return self.async_create_entry(
                        title="API Connection Restored",
                        data={"status": "resolved"}
                    )
                else:
                    # Connection still failing
                    return self.async_abort(reason="connection_still_failing")
                    
            except Exception:
                return self.async_abort(reason="connection_test_failed")

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
            description_placeholders={
                "host": self.config_entry.data.get("host", "Unknown"),
            },
        )


class SensorUnavailableRepairFlow(RepairsFlow):
    """Handler for sensor unavailability issues."""

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the first step of sensor repair."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the confirm step of sensor repair."""
        if user_input is not None:
            try:
                # Force a coordinator refresh
                coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]["coordinator"]
                await coordinator.async_refresh()
                
                # Check if sensors are now available
                # This is a simplified check - in practice, you'd check specific sensors
                if coordinator.last_update_success:
                    ir.async_delete_issue(self.hass, DOMAIN, "sensors_unavailable")
                    return self.async_create_entry(
                        title="Sensors Restored",
                        data={"status": "resolved"}
                    )
                else:
                    return self.async_abort(reason="sensors_still_unavailable")
                    
            except Exception:
                return self.async_abort(reason="refresh_failed")

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
        )


class CacheCorruptionRepairFlow(RepairsFlow):
    """Handler for cache corruption issues."""

    async def async_step_init(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the first step of cache repair."""
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, str] | None = None
    ) -> data_entry_flow.FlowResult:
        """Handle the confirm step of cache repair."""
        if user_input is not None:
            try:
                coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id]["coordinator"]
                
                # Clear all cache data
                if hasattr(coordinator, "_data_cache"):
                    coordinator._data_cache.clear()
                if hasattr(coordinator, "_cache_timestamps"):
                    coordinator._cache_timestamps.clear()
                
                # Force a fresh data fetch
                await coordinator.async_refresh()
                
                if coordinator.last_update_success:
                    ir.async_delete_issue(self.hass, DOMAIN, "cache_corruption")
                    return self.async_create_entry(
                        title="Cache Cleared",
                        data={"status": "resolved"}
                    )
                else:
                    return self.async_abort(reason="cache_clear_failed")
                    
            except Exception:
                return self.async_abort(reason="cache_repair_failed")

        return self.async_show_form(
            step_id="confirm",
            data_schema=vol.Schema({}),
        )


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Create a repair flow for the given issue."""
    if issue_id == "api_connection_failed":
        return ApiConnectionRepairFlow()
    elif issue_id == "sensors_unavailable":
        return SensorUnavailableRepairFlow()
    elif issue_id == "cache_corruption":
        return CacheCorruptionRepairFlow()
    
    # Default to a simple confirmation flow for unknown issues
    return ConfirmRepairFlow()


# Helper functions to create repair issues
async def create_api_connection_issue(hass: HomeAssistant, error_details: str) -> None:
    """Create an API connection repair issue."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        "api_connection_failed",
        breaks_in_ha_version=None,
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.ERROR,
        translation_key="api_connection_failed",
        translation_placeholders={"error": error_details},
    )


async def create_sensor_unavailable_issue(hass: HomeAssistant, sensor_count: int) -> None:
    """Create a sensor unavailability repair issue."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        "sensors_unavailable",
        breaks_in_ha_version=None,
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="sensors_unavailable",
        translation_placeholders={"count": str(sensor_count)},
    )


async def create_cache_corruption_issue(hass: HomeAssistant) -> None:
    """Create a cache corruption repair issue."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        "cache_corruption",
        breaks_in_ha_version=None,
        is_fixable=True,
        is_persistent=False,
        severity=ir.IssueSeverity.WARNING,
        translation_key="cache_corruption",
    )
