"""Constants for the Unraid integration."""

DOMAIN = "unraid_connect"
DEFAULT_NAME = "Unraid Connect"
DEFAULT_SCAN_INTERVAL = 30

# Config flow
CONF_URL = "url"
CONF_VERIFY_SSL = "verify_ssl"

# API
API_TIMEOUT = 10
BASE_GRAPHQL_URL = "/graphql"

# Array state values
ARRAY_STATE_STARTED = "STARTED"
ARRAY_STATE_STOPPED = "STOPPED"
ARRAY_STATE_NEW_ARRAY = "NEW_ARRAY"
ARRAY_STATE_RECON_DISK = "RECON_DISK"
ARRAY_STATE_DISABLE_DISK = "DISABLE_DISK"
ARRAY_STATE_SWAP_DSBL = "SWAP_DSBL"
ARRAY_STATE_INVALID_EXPANSION = "INVALID_EXPANSION"
ARRAY_STATE_PARITY_NOT_BIGGEST = "PARITY_NOT_BIGGEST"
ARRAY_STATE_TOO_MANY_MISSING_DISKS = "TOO_MANY_MISSING_DISKS"
ARRAY_STATE_NEW_DISK_TOO_SMALL = "NEW_DISK_TOO_SMALL"
ARRAY_STATE_NO_DATA_DISKS = "NO_DATA_DISKS"

# Docker container state values
CONTAINER_STATE_RUNNING = "RUNNING"
CONTAINER_STATE_EXITED = "EXITED"

# Array disk types
DISK_TYPE_DATA = "Data"
DISK_TYPE_PARITY = "Parity"
DISK_TYPE_CACHE = "Cache"
DISK_TYPE_FLASH = "Flash"

# Array disk statuses
DISK_STATUS_OK = "DISK_OK"
DISK_STATUS_NP = "DISK_NP"
DISK_STATUS_MISSING = "DISK_NP_MISSING"
DISK_STATUS_INVALID = "DISK_INVALID"
DISK_STATUS_WRONG = "DISK_WRONG"
DISK_STATUS_DSBL = "DISK_DSBL"
DISK_STATUS_NP_DSBL = "DISK_NP_DSBL"
DISK_STATUS_DSBL_NEW = "DISK_DSBL_NEW"
DISK_STATUS_NEW = "DISK_NEW"

# Note: Disk spindown state detection has been removed as the Unraid Connect GraphQL API
# does not provide reliable disk power state information (ACTIVE/STANDBY/SPUN_DOWN).
# The integration now queries all disk health data every cycle for consistent monitoring.

# VM States
VM_STATE_RUNNING = "RUNNING"
VM_STATE_SHUTOFF = "SHUTOFF"
VM_STATE_SHUTDOWN = "SHUTDOWN"  # Alternative to SHUTOFF in some API versions
VM_STATE_PAUSED = "PAUSED"
VM_STATE_CRASHED = "CRASHED"
VM_STATE_PMSUSPENDED = "PMSUSPENDED"  # Power management suspended
VM_STATE_BLOCKED = "BLOCKED"  # Blocked on resource
VM_STATE_NOSTATE = "NOSTATE"  # No state reported

# Attributes
ATTR_DISK_NAME = "disk_name"
ATTR_DISK_TYPE = "disk_type"
ATTR_DISK_SIZE = "disk_size"
ATTR_DISK_FREE = "disk_free"
ATTR_DISK_USED = "disk_used"
ATTR_DISK_TEMP = "disk_temperature"
ATTR_DISK_FS_TYPE = "disk_fs_type"
ATTR_DISK_SERIAL = "disk_serial"
ATTR_CONTAINER_IMAGE = "image"
ATTR_CONTAINER_STATUS = "status"
ATTR_VM_STATE = "state"
ATTR_CPU_BRAND = "cpu_brand"
ATTR_CPU_CORES = "cpu_cores"
ATTR_CPU_THREADS = "cpu_threads"
ATTR_UPTIME = "uptime"
ATTR_ARRAY_STATUS = "array_status"

# Service names
SERVICE_START_ARRAY = "start_array"
SERVICE_STOP_ARRAY = "stop_array"
SERVICE_START_PARITY_CHECK = "start_parity_check"
SERVICE_PAUSE_PARITY_CHECK = "pause_parity_check"
SERVICE_RESUME_PARITY_CHECK = "resume_parity_check"
SERVICE_CANCEL_PARITY_CHECK = "cancel_parity_check"
SERVICE_REBOOT = "reboot"
SERVICE_SHUTDOWN = "shutdown"

# VM service names
SERVICE_VM_PAUSE = "vm_pause"
SERVICE_VM_RESUME = "vm_resume"
SERVICE_VM_FORCE_SHUTDOWN = "vm_force_shutdown"
SERVICE_VM_REBOOT = "vm_reboot"
SERVICE_VM_RESET = "vm_reset"
SERVICE_VM_FORCE_STOP = "vm_force_stop"

# Docker service names
SERVICE_DOCKER_RESTART = "docker_restart"
SERVICE_DOCKER_LOGS = "docker_logs"

# Categories
CATEGORY_ARRAY = "array"
CATEGORY_SYSTEM = "system"
CATEGORY_VM = "vm"
CATEGORY_DOCKER = "docker"

# Icons
ICON_SERVER = "mdi:server"
ICON_DISK = "mdi:harddisk"
ICON_ARRAY = "mdi:circle-slice-8"
ICON_PARITY = "mdi:shield-check"
ICON_CACHE = "mdi:flash"
ICON_MEMORY = "mdi:memory"
ICON_CPU = "mdi:cpu-64-bit"
ICON_DOCKER = "mdi:docker"
ICON_TEMPERATURE = "mdi:temperature-celsius"
ICON_VM = "mdi:application"
ICON_NOTIFICATION = "mdi:bell"
