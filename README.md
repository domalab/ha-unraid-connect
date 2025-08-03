# Unraid Connect Integration for Home Assistant

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/custom-components/hacs)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-2025.1.0%2B-blue.svg)](https://www.home-assistant.io/)
[![Version](https://img.shields.io/badge/Version-0.1.0--beta.1-orange.svg)](https://github.com/domalab/ha-unraid-connect/releases)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/domalab/ha-unraid-connect)

> **⚠️ BETA SOFTWARE WARNING**
> This integration is currently in **beta phase**. The Unraid GraphQL API is under active development by the Unraid team, and many features may not work as expected or may be unavailable. Use at your own risk and expect breaking changes.

A comprehensive Home Assistant integration for monitoring and controlling Unraid servers via the Unraid Connect plugin's GraphQL API.

## Features

- **System Monitoring**: Uptime, and system information
- **Array Management**: Array status, disk health, space usage, and parity operations
- **Docker Container Control**: Monitor and control Docker containers
- **Real-time Updates**: Configurable polling intervals with intelligent caching
- **Comprehensive Services**: Control array, Docker containers, and system operations

## Prerequisites

### Unraid Connect Plugin

This integration requires the **Unraid Connect** plugin to be installed on your Unraid server:

1. Install the Unraid Connect plugin from the Community Applications
2. Configure the plugin and obtain an API key - [docs/setup.md](https://github.com/domalab/ha-unraid-connect/blob/main/docs/setup.md)

## Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right corner
4. Select "Custom repositories"
5. Add this repository URL: `https://github.com/domalab/ha-unraid-connect`
6. Select "Integration" as the category
7. Click "Add"
8. Find "Unraid Connect" in the integration list and install it

**Alternatively, click the badge below to directly open this repository in HACS:**

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=domalab&repository=ha-unraid-connect&category=integration)

9. Restart Home Assistant

### Manual Installation

1. Download the latest release from the [releases page](https://github.com/domalab/ha-unraid-connect/releases)
2. Extract the `custom_components/unraid_connect` folder to your Home Assistant `custom_components` directory
3. Restart Home Assistant

## Configuration

### Adding the Integration

1. Go to **Settings** → **Devices & Services**
2. Click **Add Integration**
3. Search for "Unraid Connect"
4. Enter your Unraid server details:
   - **Host URL**: Your Unraid server URL (e.g., `http://192.168.1.100` or `https://unraid.local`)
   - **API Key**: The API key from the Unraid Connect plugin
   - **Name**: A friendly name for your server (optional)
   - **Verify SSL**: Whether to verify SSL certificates (default: true)
   - **Scan Interval**: How often to update data in seconds (default: 30)

### Configuration Options

You can modify these settings after setup by clicking **Configure** on the integration:

- **Scan Interval**: Adjust polling frequency (15-300 seconds recommended)
- **Verify SSL**: Toggle SSL certificate verification

## Entities

The integration creates various entities organized by category:

### System Entities

- **System State**: Overall system status and information
- **Online Status**: Binary sensor for server connectivity
- **Uptime**: Server uptime in days
- **Notifications**: Count of active Unraid notifications

### Array Entities

- **Array State**: Current array status (Started/Stopped)
- **Array Running**: Binary sensor for array operational status
- **Array Space Used**: Used storage space with total/free as attributes
- **Array Space Free**: Available storage space

### Disk Entities

For each disk in your array:

- **Disk Health**: Binary sensor indicating disk status
- **Disk Space Used**: Individual disk usage with size and type attributes

### Docker Container Entities

For each Docker container:

- **Container Switch**: Start/stop container control
- **Container Status**: Binary sensor for running state

### Control Buttons

- **Reboot**: Restart the Unraid server
- **Shutdown**: Shut down the server
- **Start Array**: Start the disk array
- **Stop Array**: Stop the disk array
- **Start Parity Check**: Begin parity verification
- **Pause/Resume/Cancel Parity Check**: Parity operation controls

## Services

The integration provides comprehensive services for automation:

### Array Services

- `unraid.start_array`: Start the disk array
- `unraid.stop_array`: Stop the disk array
- `unraid.start_parity_check`: Start parity check (with optional correction)
- `unraid.pause_parity_check`: Pause running parity check
- `unraid.resume_parity_check`: Resume paused parity check
- `unraid.cancel_parity_check`: Cancel parity check

### System Services

- `unraid.reboot`: Reboot the server
- `unraid.shutdown`: Shutdown the server

### Docker Services

- `unraid.docker_restart`: Restart a container
- `unraid.docker_logs`: Get container logs

## Beta Status & Known Limitations

### Current Beta Limitations

This integration is in beta because the underlying Unraid GraphQL API is still under development. Known issues include:

- **API Instability**: Some GraphQL queries may fail or return incomplete data
- **Feature Availability**: Not all Unraid features are exposed via the GraphQL API yet
- **Breaking Changes**: API schema changes may require integration updates
- **Performance**: Some operations may be slower than expected
- **Documentation**: Unraid's GraphQL API documentation is still evolving

### Known API Issues (Tracked in Unraid Repository)

Based on analysis of the [Unraid API repository](https://github.com/unraid/api), the following issues affect this integration:

- **VM Query Issues** ([#1392](https://github.com/unraid/api/issues/1392)): VM queries may fail intermittently
- **Memory Limitations** ([#1375](https://github.com/unraid/api/issues/1375)): Memory values limited to 32-bit integers
- **Parity Check Issues** ([#1372](https://github.com/unraid/api/issues/1372)): Parity check queries may not work reliably
- **Missing Plugin Support** ([#1350](https://github.com/unraid/api/issues/1350)): No GraphQL endpoints for plugin management
- **Disk Spin Status** ([#1315](https://github.com/unraid/api/issues/1315)): No API to detect if disks are spinning

### Feature Comparison with SSH Integration

| Feature                  | Connect (GraphQL) | SSH Integration | Notes                                  |
| ------------------------ | ----------------- | --------------- | -------------------------------------- |
| **System Monitoring**    |
| CPU Usage                | ✅                | ✅              | Both provide real-time data            |
| Memory Usage             | ⚠️                | ✅              | Connect limited to 32-bit values       |
| Disk Usage               | ✅                | ✅              | Connect provides more detailed info    |
| Temperatures             | ✅                | ✅              | Connect has better sensor coverage     |
| **Array Management**     |
| Array Status             | ✅                | ✅              | Connect provides more detailed states  |
| Disk Health              | ✅                | ✅              | Connect has structured health data     |
| Parity Operations        | ⚠️                | ✅              | Connect has known issues               |
| Disk Spin Status         | ❌                | ✅              | Missing from GraphQL API               |
| **Container Management** |
| Docker Control           | ✅                | ✅              | Both support start/stop/restart        |
| Container Logs           | ✅                | ✅              | Connect provides structured access     |
| **VM Management**        |
| VM Control               | ⚠️                | ✅              | Connect has query reliability issues   |
| VM Status                | ⚠️                | ✅              | Intermittent failures in Connect       |
| **Advanced Features**    |
| User Scripts             | ❌                | ✅              | Not available in GraphQL API           |
| UPS Monitoring           | ✅                | ✅              | Not exposed via GraphQL                |
| Plugin Management        | ❌                | ✅              | No GraphQL endpoints                   |
| System Fans              | ❌                | ✅              | Not available in GraphQL API           |
| **Reliability**          |
| Connection Stability     | ⚠️                | ✅              | Connect depends on plugin stability    |
| Error Handling           | ✅                | ⚠️              | Connect has better structured errors   |
| Performance              | ✅                | ⚠️              | Connect is more efficient when working |

**Legend**: ✅ Fully Supported | ⚠️ Partial/Issues | ❌ Not Available

### Semantic Versioning

This project follows [Semantic Versioning](https://semver.org/):

- **0.x.x-beta.x**: Beta releases (current phase)
- **0.x.x**: Pre-release versions with potential breaking changes
- **1.x.x**: First stable release when Unraid's GraphQL API stabilizes

### Reporting Issues

When reporting issues, please include:

1. Your Unraid version
2. Unraid Connect plugin version
3. Integration version
4. Home Assistant version
5. Debug logs (see Debug Logging section below)
6. Specific error messages or unexpected behavior

## Troubleshooting

### Common Issues

**Authentication Failed**

- Verify your API key is correct
- Ensure the Unraid Connect plugin is running and properly configured
- Try using the HTTPS URL if your server redirects

**Cannot Connect**

- Check if the Unraid Connect plugin is running
- Verify the server URL is accessible from Home Assistant
- Ensure firewall settings allow the connection
- Try disabling SSL verification if using self-signed certificates

**Missing Entities**

- Some entities only appear when the corresponding services are available
- Docker entities require containers to be present

**Slow Updates**

- Adjust the scan interval in integration options
- The integration uses intelligent caching to minimize API calls
- Some data is cached longer than others to balance performance and freshness

### Debug Logging

Enable debug logging by adding to your `configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.unraid_connect: debug
```

## Contributing

### Contributing to This Integration

Contributions are welcome! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

### Contributing to Unraid API Development

Since this integration depends on the evolving Unraid GraphQL API, you can also help by:

1. **Reporting API Issues**: Submit detailed bug reports to the [Unraid API repository](https://github.com/unraid/api/issues)
2. **Feature Requests**: Request missing GraphQL endpoints needed for Home Assistant integration
3. **Testing**: Help test new API releases and report compatibility issues
4. **Documentation**: Improve API documentation and integration guides

See our [Proposed API Issues](PROPOSED_UNRAID_API_ISSUES.md) document for specific improvements needed in the Unraid GraphQL API.

## Development Environment

This section provides comprehensive guidance for setting up a development environment to contribute to the Unraid Connect integration.

### Prerequisites

Before starting development, ensure you have the following software installed:

- **Docker**: Required for running the development container

  - [Install Docker Desktop](https://docs.docker.com/get-docker/) (Windows/macOS)
  - [Install Docker Engine](https://docs.docker.com/engine/install/) (Linux)
  - Minimum version: Docker 20.10+

- **Visual Studio Code**: Primary development environment

  - [Download VS Code](https://code.visualstudio.com/)
  - Minimum version: VS Code 1.60+

- **Dev Containers Extension**: Essential for devcontainer support
  - Install from [VS Code Marketplace](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)
  - Or search for "Dev Containers" in VS Code Extensions

### Devcontainer Setup

The project includes a pre-configured development container that provides a complete Home Assistant development environment with all necessary dependencies.

#### Opening the Project in Devcontainer

1. **Clone the repository**:

   ```bash
   git clone https://github.com/domalab/ha-unraid-connect.git
   cd ha-unraid-connect
   ```

2. **Open in VS Code**:

   ```bash
   code .
   ```

3. **Launch the devcontainer**:

   - VS Code should automatically detect the devcontainer configuration
   - Click "Reopen in Container" when prompted, or
   - Use Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`) → "Dev Containers: Reopen in Container"

4. **Wait for container setup**:
   - The container will automatically build and install dependencies
   - This may take 2-5 minutes on first run
   - The `scripts/setup` command runs automatically to install Python dependencies

#### What the Devcontainer Provides

The development environment includes:

- **Python 3.13**: Latest Python runtime with Home Assistant compatibility
- **Home Assistant Core**: Full HA installation for integration testing
- **Pre-configured Extensions**:
  - Ruff (Python linting and formatting)
  - Python language support with Pylance
  - GitHub Pull Request integration
  - Coverage gutters for test coverage visualization
- **Development Dependencies**: All required packages from `requirements.txt`
- **Port Forwarding**: Home Assistant web interface accessible on port 8123
- **Additional Packages**: FFmpeg, libturbojpeg0, libpcap-dev for HA multimedia support

### Development Workflow

#### Starting the Development Environment

1. **Launch Home Assistant with the integration**:

   ```bash
   scripts/develop
   ```

   This command:

   - Creates a `config` directory if it doesn't exist
   - Initializes Home Assistant configuration
   - Sets up Python path to include the custom component
   - Starts Home Assistant in debug mode

2. **Access the Home Assistant interface**:
   - Open your browser to `http://localhost:8123`
   - Complete the initial setup if running for the first time
   - The integration will be available for configuration

#### Testing the Integration

1. **Configure the integration**:

   - Go to Settings → Devices & Services
   - Click "Add Integration" and search for "Unraid Connect"
   - Enter your Unraid server details for testing

2. **Monitor logs and debug output**:

   - Debug logs are enabled by default when using `scripts/develop`
   - Watch the terminal for integration-specific log messages
   - Use Home Assistant's Developer Tools → Logs for web-based log viewing

3. **Hot reload capabilities**:
   - Home Assistant will automatically detect changes to Python files
   - Restart Home Assistant (`Ctrl+C` then `scripts/develop`) to reload the integration
   - Configuration changes may require a full restart

#### Code Quality and Linting

1. **Run code linting**:

   ```bash
   scripts/lint
   ```

   This runs Ruff to check code style and catch potential issues.

2. **Automatic formatting**:
   - VS Code is configured to format code on save using Ruff
   - Manual formatting: `Ctrl+Shift+P` → "Format Document"

### Configuration and Files

#### Key Development Files

- **`.devcontainer.json`**: Devcontainer configuration with Python 3.13 base image
- **`scripts/setup`**: Dependency installation script (runs automatically)
- **`scripts/develop`**: Home Assistant development server launcher
- **`scripts/lint`**: Code quality checking script
- **`requirements.txt`**: Python dependencies for development
- **`config/`**: Home Assistant configuration directory (created automatically)

#### Customization Options

- **Python interpreter**: Pre-configured to use `/usr/local/bin/python`
- **Code formatting**: Ruff formatter with 4-space indentation
- **Type checking**: Basic type checking enabled with Pylance
- **Port forwarding**: Home Assistant accessible on `localhost:8123`

### Additional Developer Resources

#### Useful Commands

```bash
# Start development server
scripts/develop

# Run code linting
scripts/lint

# Install/update dependencies
scripts/setup

# Access Home Assistant logs
tail -f config/home-assistant.log

# Restart Home Assistant service (if running as daemon)
# Note: Use Ctrl+C and restart scripts/develop for development
```

#### Debugging and Logging

1. **Enable debug logging** in `config/configuration.yaml`:

   ```yaml
   logger:
     default: info
     logs:
       custom_components.unraid_connect: debug
   ```

2. **Use VS Code debugging**:
   - Set breakpoints in Python code
   - Use "Python: Current File" debug configuration
   - Attach to running Home Assistant process if needed

#### Testing Procedures

1. **Manual testing**:

   - Test integration setup and configuration
   - Verify entity creation and updates
   - Test service calls and automation triggers

2. **Integration testing**:

   - Use a real Unraid server with Connect plugin for full testing
   - Test various Unraid configurations (different array states, containers, etc.)
   - Verify error handling with network issues or API failures

3. **Code quality checks**:
   - Run `scripts/lint` before committing
   - Ensure all new code follows existing patterns
   - Add appropriate error handling and logging

#### Contribution Workflow

1. **Before starting development**:

   - Check existing issues and pull requests
   - Create an issue to discuss major changes
   - Fork the repository and create a feature branch

2. **During development**:

   - Follow the existing code style and patterns
   - Add appropriate logging and error handling
   - Test changes thoroughly with real Unraid servers

3. **Before submitting**:
   - Run `scripts/lint` to ensure code quality
   - Test the integration with various Unraid configurations
   - Update documentation if adding new features
   - Create a detailed pull request description

For more detailed contribution guidelines, see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

---

**Note**: This integration is not affiliated with Lime Technology or the official Unraid project.
