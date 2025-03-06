# Unraid Connect Integration for Home Assistant

[![GitHub Release][releases-shield]][releases]
[![GitHub Activity][commits-shield]][commits]
[![License][license-shield]][license]
[![hacs][hacsbadge]][hacs]
[![Quality Scale][quality-scale-badge]][quality-scale]

This custom integration allows you to monitor and control your Unraid server through Home Assistant, providing detailed system information, array status, and Docker container management capabilities.

## Features

- **System Monitoring**
  - CPU usage, temperature, and thread count
  - Memory usage and availability with detailed metrics
  - System uptime with human-readable format
  - Motherboard temperature (estimated if not directly available)
  - Hardware information

- **Array Management**
  - Array status and protection state
  - Array capacity and usage metrics with percentage displays
  - Total, used, and free space with proper unit formatting
  - Parity check progress and status
  - Individual disk health monitoring

- **Disk Management**
  - Individual disk temperatures and health status
  - Space usage metrics with percentage displays
  - Free and used space with detailed attributes
  - Smart status monitoring

- **Docker Container Control**
  - Container status monitoring through binary sensors
  - Start/stop/restart capabilities via service calls
  - Resource usage tracking
  - Container health checks

- **VM Management**
  - Virtual machine status monitoring
  - Start/stop functionality via service calls

- **Network Shares**
  - Share space usage with percentage displays
  - Free and used space metrics
  - Detailed attributes for automation

## Requirements

- Home Assistant 2025.2.0 or newer
- Unraid server with Unraid Connect plugin installed and configured
- Valid API key from Unraid Connect plugin

## Installation

### Option 1: HACS (Recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=domalab&category=integration&repository=ha-unraid-connect)

### Option 2: Manual Installation

1. Download the latest release from GitHub
2. Create a directory named `unraid_connect` in your Home Assistant `custom_components` directory if it doesn't already exist
3. Copy all files from the `custom_components/unraid_connect` directory in the downloaded release to your `custom_components/unraid_connect` directory
4. Restart Home Assistant

## Configuration

### Setting up Unraid Connect

1. Install the "Unraid Connect" plugin from the Community Applications in your Unraid server
2. Configure the plugin and ensure it's running
3. Generate an API key:
   - Connect to your Unraid server via SSH
   - Run the command: `unraid-api apikey --create`
   - Note down the generated API key for use with Home Assistant

### Setting up Home Assistant Integration

1. In Home Assistant, go to **Settings** → **Devices & Services**
2. Click **+ ADD INTEGRATION** and search for "Unraid Connect"
3. Enter your:
   - **Unraid server address**: Either local IP (e.g., `http://192.168.1.100`) or myunraid.net address (e.g., `https://your-server.myunraid.net`)
   - **API key**: The key generated from your Unraid server
   - **Name** (optional): Custom name for the integration (defaults to "Unraid Connect")
4. Click **Submit** to complete the setup

### Connection Options

The integration supports two connection methods:

1. **Direct connection** (recommended for local networks): Use your Unraid server's local IP address
2. **Remote connection**: Use your myunraid.net URL with full HTTPS path

### CORS Configuration

If you encounter connection issues, you may need to add Home Assistant to the allowed origins in the Unraid Connect plugin:

1. Open the Unraid Connect plugin settings in your Unraid server
2. Add your Home Assistant URL (including port) to the "Extra Origins" field:
   - Example: `http://192.168.1.100:8123`
3. Click "Apply" to save the settings
4. Restart the Unraid Connect plugin services

## Available Entities

### Binary Sensors

- **Array Status**: Indicates if the array is started/stopped
- **Disk Health Status**: One sensor per disk showing health status (normal/problem)
- **Docker Container Status**: Shows running status for each container
- **VM Status**: Shows running status for each virtual machine
- **System Online Status**: Indicates if the Unraid server is online and responding

### Sensors

- **System State**: General server state with Unraid version info
- **CPU Temperature**: CPU temperature in Celsius
- **Motherboard Temperature**: Motherboard temperature in Celsius
- **Memory Usage**: RAM usage percentage with detailed memory statistics
- **Uptime**: System uptime in human-readable format (days, hours, minutes, seconds)
- **Array Usage**: Array space usage as percentage
- **Array Free Space**: Available array space as percentage
- **Array Total Space**: Total array space with human-readable formatting
- **Disk Usage**: Per-disk space usage as percentage
- **Disk Free Space**: Per-disk available space as percentage
- **Share Usage**: Per-share space usage as percentage
- **Share Free Space**: Per-share available space as percentage

### Services

- `unraid_connect.start_array`: Start the Unraid array
- `unraid_connect.stop_array`: Stop the Unraid array
- `unraid_connect.start_parity_check`: Start a parity check (with optional correction)
- `unraid_connect.pause_parity_check`: Pause a running parity check
- `unraid_connect.resume_parity_check`: Resume a paused parity check
- `unraid_connect.cancel_parity_check`: Cancel a running parity check
- `unraid_connect.reboot`: Reboot the Unraid server
- `unraid_connect.shutdown`: Shut down the Unraid server

## Troubleshooting

### Debugging

To enable detailed logs, add the following to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.unraid_connect: debug
```

### Common Issues

1. **Connection Errors**:
   - Verify API key is correct
   - Ensure Home Assistant URL is added to Unraid Connect's Extra Origins
   - Try using the myunraid.net URL instead of local IP

2. **Missing Entities**:
   - Some entities might not appear if the corresponding hardware or software is not present in your Unraid server
   - Check if the Docker container or VM exists and is properly named

3. **Temperature Sensors Not Working**:
   - CPU and motherboard temperatures are estimated from available data if not directly reported
   - Some Unraid servers may not provide temperature data depending on hardware

## Advanced Usage

### Automation Examples

**Monitor Array Space and Send Notification When Low:**

```yaml
automation:
  - alias: "Unraid Array Space Low"
    trigger:
      - platform: numeric_state
        entity_id: sensor.unraid_array_free_space
        below: 10  # Percentage free space
    action:
      - service: notify.mobile_app
        data:
          title: "Unraid Array Space Critical"
          message: "Your Unraid array is below 10% free space!"
```

**Restart a Docker Container if it Stops:**

```yaml
automation:
  - alias: "Restart Plex if Stopped"
    trigger:
      - platform: state
        entity_id: binary_sensor.docker_plex
        from: "on"
        to: "off"
    action:
      - service: switch.turn_on
        target:
          entity_id: switch.docker_plex
```

## Contributing

Contributions to improve the integration are welcome! Whether it's:

- Reporting bugs
- Suggesting enhancements
- Submitting pull requests with code improvements
- Improving documentation

Please open an issue before making significant changes to discuss your ideas.

### Development

This integration uses standard Home Assistant patterns and follows these quality guidelines:

- Type hints for all function parameters and return values
- Full test suite for core functionality
- Clean error handling and logging
- Comprehensive documentation

To set up a development environment:

1. Clone the repository
2. Install development dependencies: `pip install -r requirements-dev.txt`
3. Run tests: `pytest`

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This integration is not officially affiliated with Lime Technology, Inc. or Unraid. Use at your own risk.

---

[commits-shield]: https://img.shields.io/github/commit-activity/m/your-github-username/ha-unraid-connect?style=for-the-badge
[commits]: https://github.com/your-github-username/ha-unraid-connect/commits/main
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg?style=for-the-badge
[license]: LICENSE
[license-shield]: https://img.shields.io/github/license/your-github-username/ha-unraid-connect?style=for-the-badge
[quality-scale]: https://developers.home-assistant.io/docs/quality_scale
[quality-scale-badge]: https://img.shields.io/badge/quality%20scale-silver-B8B8B8.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/your-github-username/ha-unraid-connect.svg?style=for-the-badge
[releases]: https://github.com/your-github-username/ha-unraid-connect/releases
