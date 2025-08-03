# Unraid Connect Integration Setup Guide

This guide walks you through setting up the Unraid Connect integration for Home Assistant.

## Prerequisites

- **Unraid Server**: Running Unraid 6.12+ with Unraid Connect plugin
- **Home Assistant**: Version 2025.1.0 or later
- **Network Access**: Home Assistant can reach your Unraid server

## Step 1: Install and Configure Unraid Connect Plugin

1. **Install Plugin**: Make sure you have the latest Unraid Connect plugin installed in Unraid (version 2025.05.01.2159 or later)

## Step 2: Generate API Key

1. **Create API Keys**: Access the API Keys via Settings → Management Access.

   <img width="425" height="442" alt="Screenshot 2025-08-03 at 1 31 18 pm" src="https://github.com/user-attachments/assets/dce5221b-5496-4b45-93e4-40c121695999" />
   
3. **Copy API Key**: The API key will be generated and displayed at the bottom of the output. Copy this key for use in Home Assistant.

   <img width="1000" height="326" alt="Screenshot 2025-08-03 at 1 32 09 pm" src="https://github.com/user-attachments/assets/00da9cbc-530c-4676-84a2-5dc54e18cf31" />

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
