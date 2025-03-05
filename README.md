# Unraid Integration for Home Assistant

⚠️ **EXPERIMENTAL**: This integration is currently in experimental status and under active development. Use with caution in production environments.

This custom integration allows you to monitor and control your Unraid server through Home Assistant, providing detailed system information, array status, and Docker container management capabilities.

## Features

- **System Monitoring**
  - CPU usage, temperature, and thread count
  - Memory usage and availability
  - System uptime
  - Hardware information

- **Array Management**
  - Array status and protection state
  - Array capacity and usage metrics
  - Parity check progress and status
  - Individual disk temperatures and health

- **Docker Container Control**
  - Container status monitoring
  - Start/stop/restart capabilities
  - Resource usage tracking (CPU, memory)
  - Container health checks

## Requirements

- Home Assistant 2025.2.0 or newer
- Unraid server with Unraid Connect plugin installed
- Valid API key from Unraid Connect

## Installation

### Option 1: HACS (Recommended)

1. Ensure [HACS](https://hacs.xyz/) is installed
2. Add this repository as a custom repository in HACS:
   - Repository: `your-github-username/ha-unraid-connect`
   - Category: `Integration`
3. Search for "Unraid Connect" in HACS and install
4. Restart Home Assistant

### Option 2: Manual Installation

1. Download the latest release from GitHub
2. Copy the `custom_components/unraid_connect` directory to your `config/custom_components` directory
3. Restart Home Assistant

## Configuration

1. Install and configure the Unraid Connect plugin on your Unraid server
2. Generate an API key using the command:

   ```bash
   unraid-api apikey --create
   ```

3. In Home Assistant, go to **Settings** → **Devices & Services**
4. Click **+ ADD INTEGRATION** and search for "Unraid Connect"
5. Enter your:
   - Unraid server address (e.g., `192.168.1.100` or your myunraid.net address)
   - API key
   - Optional: Custom name for the integration

## Available Entities

### Binary Sensors

- Array Protection Status
- Array Started Status
- Parity Check Running Status
- Docker Container Running Status (per container)

### Sensors

- CPU Statistics (cores, threads, temperature, load)
- Memory Usage and Availability
- Array Metrics (capacity, size, used space, free space)
- Parity Check Progress and Speed
- Docker Container Resource Usage (per container)

### Switches

- Docker Container Control (start/stop functionality)

## API Authentication

The integration supports two authentication methods:

1. Direct API key (recommended)
2. MyUnraid.net URL with API key

For MyUnraid.net users, use your full myunraid.net URL instead of the local IP address.

## Known Issues

1. Initial connection may fail if using local IP with redirects - use myunraid.net URL instead
2. Some Docker container metrics may not be available depending on your Unraid version
3. API rate limiting may affect update frequency

## Debugging

Enable debug logging by adding this to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.unraid_connect: debug
```

## Contributing

Contributions are welcome! Please read our [Contributing Guidelines](CONTRIBUTING.md) before submitting pull requests.

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This integration is not officially affiliated with Lime Technology, Inc. or Unraid. Use at your own risk.
