"""
Constants for the Unraid integration.
"""
from __future__ import annotations

import logging
import sys
from typing import Final

# Integration domain
DOMAIN: Final = "unraid_connect"

# Set up logging
LOGGER = logging.getLogger(__name__)

# Configuration constants
DEFAULT_SCAN_INTERVAL: Final = 30  # seconds
CONFIG_VERSION: Final = 1

# Error constants
ERROR_CANNOT_CONNECT: Final = "cannot_connect"
ERROR_INVALID_AUTH: Final = "invalid_auth"
ERROR_UNKNOWN: Final = "unknown"

# Array states
ARRAY_STATE_STARTED: Final = "started"
ARRAY_STATE_STOPPED: Final = "stopped"
ARRAY_STATE_MOUNTING: Final = "mounting"
ARRAY_STATE_UNMOUNTING: Final = "unmounting"

# Docker states
DOCKER_STATE_RUNNING: Final = "running"
DOCKER_STATE_EXITED: Final = "exited"
DOCKER_STATE_PAUSED: Final = "paused"
DOCKER_STATE_RESTARTING: Final = "restarting"

# Service constants
SERVICE_ARRAY_OPERATIONS: Final = "array_operation"
SERVICE_START_ARRAY: Final = "start_array"
SERVICE_STOP_ARRAY: Final = "stop_array"
SERVICE_DOCKER_CONTAINER: Final = "docker_container"
SERVICE_START_CONTAINER: Final = "start_container"
SERVICE_STOP_CONTAINER: Final = "stop_container"
SERVICE_RESTART_CONTAINER: Final = "restart_container"

# Array operations
ARRAY_OPERATIONS: Final[list[str]] = [
    "start",
    "stop",
    "pause",
    "resume",
    "check",
    "cancel_check",
]

# Icon mappings
ICONS: Final[dict[str, str]] = {
    "array": "mdi:harddisk",
    "docker": "mdi:docker",
    "system": "mdi:server",
    "network": "mdi:ethernet",
    "ups": "mdi:battery",
    "cpu": "mdi:cpu-64-bit",
    "memory": "mdi:memory",
    "disk": "mdi:disk",
    "parity": "mdi:harddisk-plus",
    "temperature": "mdi:thermometer",
}

# Create a custom formatter that includes more details
class DetailedFormatter(logging.Formatter):
    """Formatter that includes more details for debugging."""
    
    def format(self, record):
        """Format the specified record."""
        record.levelname = f"[{record.levelname}]"
        record.pathname = record.pathname.split("/")[-1]
        return super().format(record)

# Configure the logger
def setup_logger():
    """Set up detailed logging for the integration."""
    # Remove any existing handlers
    for handler in LOGGER.handlers[:]:
        LOGGER.removeHandler(handler)
    
    handler = logging.StreamHandler(stream=sys.stdout)
    fmt = DetailedFormatter(
        '%(asctime)s %(levelname)-10s %(name)s (%(pathname)s:%(lineno)d): %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    handler.setFormatter(fmt)
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    
    # Prevent log messages from being passed to the root logger
    LOGGER.propagate = False
    
    # Log once that logging is configured
    LOGGER.debug("Unraid integration logger configured")

# Initialize logging
setup_logger()

# Translation keys
ATTR_ACTION: Final = "action"
ATTR_CONTAINER_ID: Final = "container_id"
ATTR_OPERATION: Final = "operation"

# Attribute keys
ATTR_STATE: Final = "state"
ATTR_STATUS: Final = "status"
ATTR_IMAGE: Final = "image"
ATTR_AUTO_START: Final = "auto_start"
ATTR_CPU_USAGE: Final = "cpu_usage"
ATTR_MEMORY_USAGE: Final = "memory_usage"
ATTR_MEMORY_PERCENT: Final = "memory_percent"
ATTR_NETWORK_RX: Final = "network_rx"
ATTR_NETWORK_TX: Final = "network_tx"
ATTR_BLOCK_READ: Final = "block_read"
ATTR_BLOCK_WRITE: Final = "block_write"
ATTR_PORTS: Final = "ports"
ATTR_COMMAND: Final = "command"
ATTR_CREATED: Final = "created"
ATTR_TEMPERATURE: Final = "temperature"
ATTR_SIZE: Final = "size"
ATTR_INTERFACE: Final = "interface"
ATTR_ROTATIONAL: Final = "rotational"
ATTR_SERIAL: Final = "serial"
ATTR_MODEL: Final = "model"
ATTR_ERRORS: Final = "errors"
ATTR_PROGRESS: Final = "progress"
ATTR_SPEED: Final = "speed"
ATTR_ETA: Final = "eta"