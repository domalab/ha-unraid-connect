#!/bin/bash
# Curl-based script to test the Unraid GraphQL API

# Configuration (default values)
SERVER_IP="192.168.1.100"
API_KEY=""
QUERY_TYPE="info"
DIRECT_IP=false

# Help message
show_help() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  -h, --help       Show this help message"
    echo "  -i, --ip         Server IP address (default: $SERVER_IP)"
    echo "  -k, --key        API key (default: predefined key)"
    echo "  -t, --type       Query type: info, array, docker, disks, network, shares, vms"
    echo "                   (default: info)"
    echo "  -d, --direct     Use direct IP connection without checking for redirects"
    echo ""
    echo "Examples:"
    echo "  $0 --type info"
    echo "  $0 --ip 192.168.1.100 --type docker"
    echo "  $0 --ip 192.168.1.100 --direct"
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    key="$1"
    case $key in
        -h|--help)
            show_help
            exit 0
            ;;
        -i|--ip)
            SERVER_IP="$2"
            shift
            shift
            ;;
        -k|--key)
            API_KEY="$2"
            shift
            shift
            ;;
        -t|--type)
            QUERY_TYPE="$2"
            shift
            shift
            ;;
        -d|--direct)
            DIRECT_IP=true
            shift
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# Define queries
INFO_QUERY='{
  "query": "{ info { os { platform distro release uptime } cpu { manufacturer brand cores threads } memory { total free used } versions { unraid } } }"
}'

ARRAY_QUERY='{
  "query": "{ array { state capacity { disks { free used total } } disks { name size status type temp } } }"
}'

DOCKER_QUERY='{
  "query": "{ docker { containers { id names image state status autoStart ports { ip privatePort publicPort type } } } }"
}'

DISKS_QUERY='{
  "query": "{ disks { device name type size vendor temperature smartStatus } }"
}'

NETWORK_QUERY='{
  "query": "{ network { iface ifaceName ipv4 ipv6 mac operstate type duplex speed accessUrls { type name ipv4 ipv6 } } }"
}'

SHARES_QUERY='{
  "query": "{ shares { name comment free size used } }"
}'

VMS_QUERY='{
  "query": "{ vms { domain { uuid name state } } }"
}'

# Set the query based on type
case $QUERY_TYPE in
    info)
        QUERY=$INFO_QUERY
        TITLE="Server Information"
        ;;
    array)
        QUERY=$ARRAY_QUERY
        TITLE="Array Status"
        ;;
    docker)
        QUERY=$DOCKER_QUERY
        TITLE="Docker Containers"
        ;;
    disks)
        QUERY=$DISKS_QUERY
        TITLE="Disk Information"
        ;;
    network)
        QUERY=$NETWORK_QUERY
        TITLE="Network Information"
        ;;
    shares)
        QUERY=$SHARES_QUERY
        TITLE="Shares Information"
        ;;
    vms)
        QUERY=$VMS_QUERY
        TITLE="Virtual Machines"
        ;;
    *)
        echo "Unknown query type: $QUERY_TYPE"
        show_help
        exit 1
        ;;
esac

echo "Connecting to Unraid at $SERVER_IP to query $TITLE..."
echo "---------------------------------------------"

# Check for redirect first
REDIRECT_URL=""
if [ "$DIRECT_IP" = false ]; then
    echo "Checking for redirect..."
    REDIRECT_URL=$(curl -s -I "http://$SERVER_IP/graphql" | grep -i "Location:" | awk '{print $2}' | tr -d '\r')
    
    if [ -n "$REDIRECT_URL" ]; then
        echo "Found redirect URL: $REDIRECT_URL"
        # Extract domain for headers
        DOMAIN=$(echo "$REDIRECT_URL" | sed -E 's|https?://([^/]+).*|\1|')
        echo "Using domain: $DOMAIN for headers"
    else
        echo "No redirect found, using direct IP"
        DOMAIN="$SERVER_IP"
        REDIRECT_URL="http://$SERVER_IP/graphql"
    fi
else
    echo "Using direct IP as requested"
    DOMAIN="$SERVER_IP"
    REDIRECT_URL="http://$SERVER_IP/graphql"
fi

# Execute the GraphQL query using curl and follow redirects
# Adding -s for silent operation (removes progress bar) but keeping errors
# Using jq for pretty output if available
if command -v jq &> /dev/null; then
    curl -s -L \
      -X POST \
      -H "Content-Type: application/json" \
      -H "x-api-key: $API_KEY" \
      -H "Origin: https://$DOMAIN" \
      -H "Host: $DOMAIN" \
      -H "Referer: https://$DOMAIN/dashboard" \
      -d "$QUERY" \
      "$REDIRECT_URL" | jq '.'
else
    curl -L \
      -X POST \
      -H "Content-Type: application/json" \
      -H "x-api-key: $API_KEY" \
      -H "Origin: https://$DOMAIN" \
      -H "Host: $DOMAIN" \
      -H "Referer: https://$DOMAIN/dashboard" \
      -d "$QUERY" \
      "$REDIRECT_URL"
fi

echo ""
echo "---------------------------------------------"