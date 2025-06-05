# Unraid Connect Integration Setup Guide

This guide walks you through setting up the Unraid Connect integration for Home Assistant.

## Prerequisites

- **Unraid Server**: Running Unraid 6.12+ with Unraid Connect plugin
- **Home Assistant**: Version 2025.1.0 or later
- **Network Access**: Home Assistant can reach your Unraid server

## Step 1: Install and Configure Unraid Connect Plugin

1. **Install Plugin**: Make sure you have the latest Unraid Connect plugin installed in Unraid (version 2025.05.01.2159 or later)

2. **Enable Developer Sandbox**: Access the plugin via Settings → Management Access. Make sure "Enable Developer Sandbox" is enabled.

![Image](https://github.com/user-attachments/assets/6aef1b02-b348-4f96-a370-c327e85156e0)

3. **Verify GraphQL API**: Click the /graphql link to open the Unraid GraphQL Developer Sandbox in a new tab. This confirms the API is working.

![Image](https://github.com/user-attachments/assets/5c21c7ca-8314-47ef-835c-cce43cbccb9e)

> **Note**: CORS configuration is no longer required! Recent plugin versions (2025.05.01.2159+) have resolved the API origins issue, significantly simplifying the setup process.

## Step 2: Generate API Key

1. **Open Unraid Terminal**: Access the terminal from the Unraid web interface

![Image](https://github.com/user-attachments/assets/a37c0919-639f-4901-a30a-5e75b607d800)

2. **Run API Key Generation Command**: Execute the API key creation script in the terminal

3. **Assign Permissions**: When prompted, press "a" to assign all permissions (or customize as needed)

![Image](https://github.com/user-attachments/assets/12e24042-4759-4446-af54-7d9f250b43af)

4. **Copy API Key**: The API key will be generated and displayed at the bottom of the output. Copy this key for use in Home Assistant.

![Image](https://github.com/user-attachments/assets/89a80155-0622-478b-9e6f-1d427099a62e)

API Key shown at the bottom:

![Image](https://github.com/user-attachments/assets/fbf2c48b-210a-468c-9bbb-e6a7ea0e2410)

## Step 3: Install Home Assistant Integration

1. **Install Integration**: Make sure you have the latest Unraid Connect Integration installed. You can install via HACS:

   [![Open in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=domalab&repository=ha-unraid-connect&category=integration)

## Step 4: Configure Home Assistant Integration

1. **Add Integration**: Go to Settings → Devices & Services → Add Integration → Search for "Unraid Connect"

2. **Setup Screen**: You will see the integration setup screen:

![Image](https://github.com/user-attachments/assets/ec0dc08d-7a9f-4f13-a233-03437080b903)

3. **Enter Configuration**: Fill in your Unraid server details and the API key you created, then click Submit:

![Image](https://github.com/user-attachments/assets/8a09a307-0c6d-47c4-9076-fcf851934f95)

4. **Verify Setup**: The integration will initialize and show as configured:

![Image](https://github.com/user-attachments/assets/869f0469-f67f-4cf6-a6d5-3f40d29ebf1a)

## Known Issues

- **VM Warnings**: If you have VMs, you may see warnings in the log. This is a known issue in the current Unraid Connect plugin version.

![Image](https://github.com/user-attachments/assets/7c1a5c14-9ec2-416a-a6d3-375d4c1baa71)

## Troubleshooting

### Authentication Failed
- Verify your API key was copied correctly
- Ensure the Unraid Connect plugin is running
- Check that Home Assistant can reach your Unraid server

### Cannot Connect
- Verify the Unraid server URL is correct
- Check network connectivity between Home Assistant and Unraid
- Ensure the Unraid Connect plugin is enabled and running

### Missing Entities
- Some entities only appear when corresponding services are available
- VMs require the VM service to be enabled in Unraid
- Docker entities require containers to be present

For more help, see the [GitHub Issues](https://github.com/domalab/ha-unraid-connect/issues) or [project documentation](https://github.com/domalab/ha-unraid-connect).