"""
Unraid GraphQL API Client

This script demonstrates how to connect to the Unraid GraphQL API,
authenticate with an API key, and perform various queries.
"""

import requests
import json
import argparse
from typing import Dict, Any, Optional, List
import urllib3
import re
import warnings

# Disable SSL warnings for self-signed certificates if needed
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Suppress urllib3 OpenSSL warnings
warnings.filterwarnings('ignore', category=urllib3.exceptions.InsecureRequestWarning)
warnings.filterwarnings('ignore', message='.*NotOpenSSLWarning.*')

class UnraidGraphQLClient:
    """Client for interacting with the Unraid GraphQL API."""
    
    def __init__(self, server_ip: str, api_key: str, port: int = 80):
        """
        Initialize the Unraid GraphQL client.
        
        Args:
            server_ip: IP address of the Unraid server
            api_key: API key for authentication
            port: Port number (default: 80)
        """
        self.server_ip = server_ip
        self.api_key = api_key
        self.port = port
        self.base_url = f"http://{server_ip}:{port}"
        self.endpoint = f"{self.base_url}/graphql"
        self.redirect_url = None
        
        # Initial set of headers
        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "Accept": "application/json"
        }
        
        # Discover the redirect URL if any
        self._discover_redirect_url()
    
    def _discover_redirect_url(self):
        """Discover and store the redirect URL if the server uses one."""
        try:
            response = requests.get(self.endpoint, allow_redirects=False)
            
            if response.status_code == 302 and 'Location' in response.headers:
                self.redirect_url = response.headers['Location']
                print(f"Discovered redirect URL: {self.redirect_url}")
                
                # Update our endpoint to use the redirect URL
                self.endpoint = self.redirect_url
                
                # If the redirect is to a domain name, extract it for the Origin header
                domain_match = re.search(r'https?://([^/]+)', self.redirect_url)
                if domain_match:
                    domain = domain_match.group(1)
                    self.headers["Host"] = domain
                    self.headers["Origin"] = f"https://{domain}"
                    self.headers["Referer"] = f"https://{domain}/dashboard"
        
        except requests.exceptions.RequestException as e:
            print(f"Warning: Could not discover redirect URL: {e}")
    
    def execute_query(self, query: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Execute a GraphQL query against the Unraid API.
        
        Args:
            query: The GraphQL query string
            variables: Optional variables for the query
            
        Returns:
            The JSON response from the API
        """
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        
        try:
            # Create a session that will persist across requests
            session = requests.Session()
            
            # Always follow redirects
            session.max_redirects = 5
            
            # Add all headers to the session
            for key, value in self.headers.items():
                session.headers[key] = value
            
            # Make the GraphQL request
            response = session.post(
                self.endpoint,
                json=payload,
                verify=False,  # Skip SSL verification for self-signed certificates
                timeout=15
            )
            
            # Check for HTTP errors
            response.raise_for_status()
            
            return response.json()
            
        except requests.exceptions.RequestException as e:
            print(f"Error making the request: {e}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"Response status: {e.response.status_code}")
                print(f"Response body: {e.response.text}")
            return {"error": str(e)}
    
    def get_server_info(self) -> Dict[str, Any]:
        """Get detailed server information including CPU, memory, and system details."""
        query = """
        query {
            info {
                os {
                    platform
                    distro
                    release
                    kernel
                    arch
                    hostname
                    uptime
                }
                cpu {
                    manufacturer
                    brand
                    vendor
                    family
                    model
                    speed
                    speedmin
                    speedmax
                    cores
                    threads
                    processors
                    socket
                    cache
                }
                memory {
                    total
                    free
                    used
                    active
                    available
                    buffcache
                    swaptotal
                    swapused
                    swapfree
                    layout {
                        size
                        bank
                        type
                        clockSpeed
                        manufacturer
                    }
                }
                baseboard {
                    manufacturer
                    model
                    version
                    serial
                }
                system {
                    manufacturer
                    model
                    version
                    serial
                }
                versions {
                    unraid
                    kernel
                    docker
                }
            }
        }
        """
        return self.execute_query(query)
    
    def get_array_status(self) -> Dict[str, Any]:
        """Get detailed array status including all disk types."""
        query = """
        query {
            array {
                state
                capacity {
                    kilobytes {
                        free
                        used
                        total
                    }
                    disks {
                        free
                        used
                        total
                    }
                }
                boot {
                    id
                    name
                    device
                    size
                    temp
                    rotational
                    fsSize
                    fsFree
                    fsUsed
                    type
                }
                parities {
                    id
                    name
                    device
                    size
                    temp
                    status
                    rotational
                    type
                }
                disks {
                    id
                    name
                    device
                    size
                    status
                    type
                    temp
                    rotational
                    fsSize
                    fsFree
                    fsUsed
                    numReads
                    numWrites
                    numErrors
                }
                caches {
                    id
                    name
                    device
                    size
                    temp
                    status
                    rotational
                    fsSize
                    fsFree
                    fsUsed
                    type
                }
            }
        }
        """
        return self.execute_query(query)
    
    def get_docker_containers(self) -> Dict[str, Any]:
        """Get detailed information about Docker containers."""
        query = """
        query {
            docker {
                containers {
                    id
                    names
                    image
                    state
                    status
                    autoStart
                    ports {
                        ip
                        privatePort
                        publicPort
                        type
                    }
                }
            }
        }
        """
        return self.execute_query(query)
        
    def start_docker_container(self, container_id: str) -> Dict[str, Any]:
        """
        Start a Docker container.
        
        Args:
            container_id: The ID of the container to start
            
        Note:
            This operation is not currently supported by the Unraid GraphQL API.
            It is included for possible future API support.
        """
        # This is a custom mutation that might be supported in future API versions
        return {"error": "Docker container control operations are not currently supported by the Unraid GraphQL API"}
    
    def stop_docker_container(self, container_id: str) -> Dict[str, Any]:
        """
        Stop a Docker container.
        
        Args:
            container_id: The ID of the container to stop
            
        Note:
            This operation is not currently supported by the Unraid GraphQL API.
            It is included for possible future API support.
        """
        # This is a custom mutation that might be supported in future API versions
        return {"error": "Docker container control operations are not currently supported by the Unraid GraphQL API"}
    
    def restart_docker_container(self, container_id: str) -> Dict[str, Any]:
        """
        Restart a Docker container.
        
        Args:
            container_id: The ID of the container to restart
            
        Note:
            This operation is not currently supported by the Unraid GraphQL API.
            It is included for possible future API support.
        """
        # This is a custom mutation that might be supported in future API versions
        return {"error": "Docker container control operations are not currently supported by the Unraid GraphQL API"}
    
    def get_disks_info(self) -> Dict[str, Any]:
        """Get detailed information about all disks."""
        query = """
        query {
            disks {
                device
                name
                type
                size
                vendor
                temperature
                smartStatus
            }
        }
        """
        return self.execute_query(query)
    
    def get_network_info(self) -> Dict[str, Any]:
        """Get network interface information."""
        query = """
        query {
            network {
                iface
                ifaceName
                ipv4
                ipv6
                mac
                operstate
                type
                duplex
                speed
                accessUrls {
                    type
                    name
                    ipv4
                    ipv6
                }
            }
        }
        """
        return self.execute_query(query)
        
    def get_detailed_network_info(self) -> Dict[str, Any]:
        """Get detailed network interface information including all devices."""
        query = """
        query {
            info {
                devices {
                    network {
                        id
                        iface
                        ifaceName
                        ipv4
                        ipv6
                        mac
                        internal
                        operstate
                        type
                        duplex
                        mtu
                        speed
                        carrierChanges
                    }
                }
            }
        }
        """
        return self.execute_query(query)
    
    def get_shares(self) -> Dict[str, Any]:
        """Get information about network shares."""
        query = """
        query {
            shares {
                name
                comment
                free
                size
                used
            }
        }
        """
        return self.execute_query(query)
    
    def get_vms(self) -> Dict[str, Any]:
        """Get information about virtual machines."""
        query = """
        query {
            vms {
                domain {
                    uuid
                    name
                    state
                }
            }
        }
        """
        return self.execute_query(query)
    
    def start_vm(self, vm_uuid: str) -> Dict[str, Any]:
        """
        Start a virtual machine.
        
        Args:
            vm_uuid: The UUID of the VM to start
            
        Note:
            This operation is not currently supported by the Unraid GraphQL API.
            It is included for possible future API support.
        """
        # This is a custom mutation that might be supported in future API versions
        return {"error": "VM control operations are not currently supported by the Unraid GraphQL API"}
    
    def stop_vm(self, vm_uuid: str, force: bool = False) -> Dict[str, Any]:
        """
        Stop a virtual machine.
        
        Args:
            vm_uuid: The UUID of the VM to stop
            force: Force power off if True, otherwise graceful shutdown
            
        Note:
            This operation is not currently supported by the Unraid GraphQL API.
            It is included for possible future API support.
        """
        # This is a custom mutation that might be supported in future API versions
        return {"error": "VM control operations are not currently supported by the Unraid GraphQL API"}
    
    def pause_vm(self, vm_uuid: str) -> Dict[str, Any]:
        """
        Pause a virtual machine.
        
        Args:
            vm_uuid: The UUID of the VM to pause
            
        Note:
            This operation is not currently supported by the Unraid GraphQL API.
            It is included for possible future API support.
        """
        # This is a custom mutation that might be supported in future API versions
        return {"error": "VM control operations are not currently supported by the Unraid GraphQL API"}
    
    def resume_vm(self, vm_uuid: str) -> Dict[str, Any]:
        """
        Resume a paused virtual machine.
        
        Args:
            vm_uuid: The UUID of the VM to resume
            
        Note:
            This operation is not currently supported by the Unraid GraphQL API.
            It is included for possible future API support.
        """
        # This is a custom mutation that might be supported in future API versions
        return {"error": "VM control operations are not currently supported by the Unraid GraphQL API"}
        
    def get_parity_history(self) -> Dict[str, Any]:
        """Get parity check history."""
        query = """
        query {
            parityHistory {
                date
                duration
                speed
                status
                errors
            }
        }
        """
        return self.execute_query(query)
        
    def get_vars(self) -> Dict[str, Any]:
        """Get system variables and settings."""
        query = """
        query {
            vars {
                version
                name
                timeZone
                security
                workgroup
                domain
                sysModel
                useSsl
                port
                portssl
                startArray
                spindownDelay
                shareCount
                shareSmbCount
                shareNfsCount
                shareAfpCount
            }
        }
        """
        return self.execute_query(query)
    
    def run_custom_query(self, query_string: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Run a custom GraphQL query."""
        return self.execute_query(query_string, variables)
        
    # System control methods
    
    def reboot_system(self) -> Dict[str, Any]:
        """Reboot the Unraid system."""
        mutation = """
        mutation {
            reboot
        }
        """
        return self.execute_query(mutation)
    
    def shutdown_system(self) -> Dict[str, Any]:
        """Shutdown the Unraid system."""
        mutation = """
        mutation {
            shutdown
        }
        """
        return self.execute_query(mutation)
    
    # Array control methods
    
    def start_array(self) -> Dict[str, Any]:
        """Start the Unraid array."""
        mutation = """
        mutation {
            startArray {
                state
            }
        }
        """
        return self.execute_query(mutation)
    
    def stop_array(self) -> Dict[str, Any]:
        """Stop the Unraid array."""
        mutation = """
        mutation {
            stopArray {
                state
            }
        }
        """
        return self.execute_query(mutation)
    
    # Parity control methods
    
    def start_parity_check(self, correct: bool = False) -> Dict[str, Any]:
        """Start a parity check. Set correct=True to correct errors."""
        mutation = """
        mutation {
            startParityCheck(correct: %s)
        }
        """ % ("true" if correct else "false")
        return self.execute_query(mutation)
    
    def pause_parity_check(self) -> Dict[str, Any]:
        """Pause a running parity check."""
        mutation = """
        mutation {
            pauseParityCheck
        }
        """
        return self.execute_query(mutation)
    
    def resume_parity_check(self) -> Dict[str, Any]:
        """Resume a paused parity check."""
        mutation = """
        mutation {
            resumeParityCheck
        }
        """
        return self.execute_query(mutation)
    
    def cancel_parity_check(self) -> Dict[str, Any]:
        """Cancel a running parity check."""
        mutation = """
        mutation {
            cancelParityCheck
        }
        """
        return self.execute_query(mutation)
    
    # User management methods
    
    def add_user(self, name: str, password: str, description: str = "") -> Dict[str, Any]:
        """Add a new user to the system."""
        mutation = """
        mutation {
            addUser(input: {
                name: "%s",
                password: "%s",
                description: "%s"
            }) {
                id
                name
                description
                roles
            }
        }
        """ % (name, password, description)
        return self.execute_query(mutation)
    
    def delete_user(self, name: str) -> Dict[str, Any]:
        """Delete a user from the system."""
        mutation = """
        mutation {
            deleteUser(input: {
                name: "%s"
            }) {
                id
                name
            }
        }
        """ % name
        return self.execute_query(mutation)
    
    def get_users(self) -> Dict[str, Any]:
        """Get information about the current user."""
        query = """
        query {
            me {
                id
                name
                description
                roles
                permissions {
                    resource
                    actions
                }
            }
        }
        """
        return self.execute_query(query)
    
    # API key management
    
    def create_api_key(self, name: str, description: str = "", roles: List[str] = None) -> Dict[str, Any]:
        """Create a new API key."""
        roles_str = ""
        if roles:
            roles_str = ", roles: [%s]" % ", ".join(roles)
            
        mutation = """
        mutation {
            createApiKey(input: {
                name: "%s",
                description: "%s"%s
            }) {
                id
                key
                name
                description
                roles
                createdAt
            }
        }
        """ % (name, description, roles_str)
        return self.execute_query(mutation)
    
    def get_api_keys(self) -> Dict[str, Any]:
        """Get all API keys."""
        query = """
        query {
            apiKeys {
                id
                name
                description
                roles
                createdAt
                permissions {
                    resource
                    actions
                }
            }
        }
        """
        return self.execute_query(query)
    
    # Notification management
    
    def create_notification(self, title: str, subject: str, description: str, 
                           importance: str = "INFO", link: str = None) -> Dict[str, Any]:
        """
        Create a new notification.
        
        Args:
            title: The notification title
            subject: The notification subject
            description: The notification description
            importance: Importance level (INFO, WARNING, ALERT)
            link: Optional link
        """
        link_str = ""
        if link:
            link_str = ', link: "%s"' % link
            
        mutation = """
        mutation {
            createNotification(input: {
                title: "%s",
                subject: "%s",
                description: "%s",
                importance: %s%s
            }) {
                id
                title
                subject
                description
                importance
                timestamp
                formattedTimestamp
            }
        }
        """ % (title, subject, description, importance, link_str)
        return self.execute_query(mutation)
    
    def get_notifications(self, notification_type: str = "UNREAD", 
                         importance: str = None, limit: int = 100) -> Dict[str, Any]:
        """
        Get notifications.
        
        Args:
            notification_type: Type of notifications to retrieve (UNREAD or ARCHIVE)
            importance: Optional filter by importance (INFO, WARNING, ALERT)
            limit: Maximum number of notifications to return
        """
        importance_str = ""
        if importance:
            importance_str = ", importance: %s" % importance
            
        query = """
        query {
            notifications {
                list(filter: {
                    type: %s%s,
                    offset: 0,
                    limit: %d
                }) {
                    id
                    title
                    subject
                    description
                    importance
                    link
                    type
                    timestamp
                    formattedTimestamp
                }
                overview {
                    unread {
                        info
                        warning
                        alert
                        total
                    }
                    archive {
                        info
                        warning
                        alert
                        total
                    }
                }
            }
        }
        """ % (notification_type, importance_str, limit)
        return self.execute_query(query)
    
    def archive_notification(self, notification_id: str) -> Dict[str, Any]:
        """Archive a notification."""
        mutation = """
        mutation {
            archiveNotification(id: "%s") {
                id
                title
                type
            }
        }
        """ % notification_id
        return self.execute_query(mutation)
    
    def archive_all_notifications(self, importance: str = None) -> Dict[str, Any]:
        """
        Archive all notifications.
        
        Args:
            importance: Optional filter by importance (INFO, WARNING, ALERT)
        """
        importance_str = ""
        if importance:
            importance_str = "(importance: %s)" % importance
            
        mutation = """
        mutation {
            archiveAll%s {
                unread {
                    total
                }
                archive {
                    total
                }
            }
        }
        """ % importance_str
        return self.execute_query(mutation)
    
    # Remote access configuration
    
    def setup_remote_access(self, access_type: str, forward_type: str = None, 
                           port: int = None) -> Dict[str, Any]:
        """
        Configure remote access to the server.
        
        Args:
            access_type: Access type (DYNAMIC, ALWAYS, DISABLED)
            forward_type: Forward type (UPNP, STATIC)
            port: Port number
        """
        forward_type_str = ""
        port_str = ""
        
        if forward_type:
            forward_type_str = ', forwardType: %s' % forward_type
        
        if port:
            port_str = ', port: %d' % port
            
        mutation = """
        mutation {
            setupRemoteAccess(input: {
                accessType: %s%s%s
            })
        }
        """ % (access_type, forward_type_str, port_str)
        return self.execute_query(mutation)
    
    def pretty_print_response(self, data: Dict[str, Any]) -> None:
        """Print the API response in a readable format."""
        print(json.dumps(data, indent=2))

def main():
    """Main function to run the script."""
    parser = argparse.ArgumentParser(description="Unraid GraphQL API Client")
    parser.add_argument("--ip", default="192.168.20.21", help="Unraid server IP address (default: 192.168.20.21)")
    parser.add_argument("--key", default="d19cc212ffe54c88397398237f87791e75e8161e9d78c41509910ceb8f07e688", 
                        help="API key")
    parser.add_argument("--port", type=int, default=80, help="Port (default: 80)")
    parser.add_argument("--query", 
                        choices=["info", "array", "docker", "disks", "network", "shares", "vms", 
                                "parity", "vars", "users", "apikeys", "notifications", "all"], 
                        default="info", help="Query type to execute")
    parser.add_argument("--direct", action="store_true", 
                        help="Use direct IP connection without checking for redirects")
    parser.add_argument("--custom", type=str, help="Run a custom GraphQL query from a string")
    
    # System control arguments
    control_group = parser.add_argument_group("System Control")
    control_group.add_argument("--reboot", action="store_true", help="Reboot the Unraid system")
    control_group.add_argument("--shutdown", action="store_true", help="Shutdown the Unraid system")
    
    # Array control arguments
    array_group = parser.add_argument_group("Array Control")
    array_group.add_argument("--start-array", action="store_true", help="Start the Unraid array")
    array_group.add_argument("--stop-array", action="store_true", help="Stop the Unraid array")
    
    # Parity control arguments
    parity_group = parser.add_argument_group("Parity Control")
    parity_group.add_argument("--start-parity", action="store_true", help="Start a parity check")
    parity_group.add_argument("--correct-parity", action="store_true", 
                             help="Start a parity check with correction")
    parity_group.add_argument("--pause-parity", action="store_true", help="Pause a running parity check")
    parity_group.add_argument("--resume-parity", action="store_true", help="Resume a paused parity check")
    parity_group.add_argument("--cancel-parity", action="store_true", help="Cancel a running parity check")
    
    # User management arguments
    user_group = parser.add_argument_group("User Management")
    user_group.add_argument("--add-user", action="store_true", help="Add a new user")
    user_group.add_argument("--username", type=str, help="Username for user operations")
    user_group.add_argument("--password", type=str, help="Password for user operations")
    user_group.add_argument("--description", type=str, help="Description for user or API key")
    user_group.add_argument("--delete-user", action="store_true", help="Delete a user")
    
    # API key management
    apikey_group = parser.add_argument_group("API Key Management")
    apikey_group.add_argument("--create-apikey", action="store_true", help="Create a new API key")
    apikey_group.add_argument("--apikey-name", type=str, help="Name for the API key")
    apikey_group.add_argument("--apikey-roles", type=str, help="Comma-separated list of roles (admin,guest,connect)")
    
    # Notification management
    notification_group = parser.add_argument_group("Notification Management")
    notification_group.add_argument("--create-notification", action="store_true", help="Create a notification")
    notification_group.add_argument("--title", type=str, help="Title for notification")
    notification_group.add_argument("--subject", type=str, help="Subject for notification")
    notification_group.add_argument("--message", type=str, help="Message content for notification")
    notification_group.add_argument("--importance", choices=["INFO", "WARNING", "ALERT"], 
                                  default="INFO", help="Importance level of notification")
    notification_group.add_argument("--link", type=str, help="Link for notification")
    notification_group.add_argument("--archive-notification", type=str, help="ID of notification to archive")
    notification_group.add_argument("--archive-all", action="store_true", help="Archive all notifications")
    
    # Remote access configuration
    remote_group = parser.add_argument_group("Remote Access")
    remote_group.add_argument("--setup-remote", action="store_true", help="Configure remote access")
    remote_group.add_argument("--access-type", choices=["DYNAMIC", "ALWAYS", "DISABLED"], 
                             help="Remote access type")
    remote_group.add_argument("--forward-type", choices=["UPNP", "STATIC"], 
                             help="Port forwarding type")
    remote_group.add_argument("--remote-port", type=int, help="Port for remote access")
    
    # Docker container control
    docker_group = parser.add_argument_group("Docker Container Control")
    docker_group.add_argument("--start-container", type=str, help="ID of Docker container to start")
    docker_group.add_argument("--stop-container", type=str, help="ID of Docker container to stop")
    docker_group.add_argument("--restart-container", type=str, 
                            help="ID of Docker container to restart")
    
    # VM control
    vm_group = parser.add_argument_group("Virtual Machine Control")
    vm_group.add_argument("--start-vm", type=str, help="UUID of VM to start")
    vm_group.add_argument("--stop-vm", type=str, help="UUID of VM to stop")
    vm_group.add_argument("--force-stop-vm", action="store_true", 
                         help="Force power off VM instead of graceful shutdown")
    vm_group.add_argument("--pause-vm", type=str, help="UUID of VM to pause")
    vm_group.add_argument("--resume-vm", type=str, help="UUID of VM to resume")
    
    args = parser.parse_args()
    
    # Create the client
    client = UnraidGraphQLClient(args.ip, args.key, args.port)
    
    # If direct mode is enabled, force using the direct IP
    if args.direct:
        client.endpoint = f"http://{args.ip}:{args.port}/graphql"
        client.redirect_url = None
    
    try:
        # Handle control operations first
        if args.reboot:
            print("\n=== REBOOTING SYSTEM ===")
            response = client.reboot_system()
            client.pretty_print_response(response)
            return
            
        if args.shutdown:
            print("\n=== SHUTTING DOWN SYSTEM ===")
            response = client.shutdown_system()
            client.pretty_print_response(response)
            return
            
        if args.start_array:
            print("\n=== STARTING ARRAY ===")
            response = client.start_array()
            client.pretty_print_response(response)
            return
            
        if args.stop_array:
            print("\n=== STOPPING ARRAY ===")
            response = client.stop_array()
            client.pretty_print_response(response)
            return
            
        if args.start_parity:
            print("\n=== STARTING PARITY CHECK ===")
            response = client.start_parity_check(False)
            client.pretty_print_response(response)
            return
            
        if args.correct_parity:
            print("\n=== STARTING PARITY CHECK WITH CORRECTION ===")
            response = client.start_parity_check(True)
            client.pretty_print_response(response)
            return
            
        if args.pause_parity:
            print("\n=== PAUSING PARITY CHECK ===")
            response = client.pause_parity_check()
            client.pretty_print_response(response)
            return
            
        if args.resume_parity:
            print("\n=== RESUMING PARITY CHECK ===")
            response = client.resume_parity_check()
            client.pretty_print_response(response)
            return
            
        if args.cancel_parity:
            print("\n=== CANCELLING PARITY CHECK ===")
            response = client.cancel_parity_check()
            client.pretty_print_response(response)
            return
            
        # User management
        if args.add_user:
            if not args.username or not args.password:
                print("Error: Username and password are required for adding a user")
                return
                
            print(f"\n=== ADDING USER: {args.username} ===")
            response = client.add_user(args.username, args.password, args.description or "")
            client.pretty_print_response(response)
            return
            
        if args.delete_user:
            if not args.username:
                print("Error: Username is required for deleting a user")
                return
                
            print(f"\n=== DELETING USER: {args.username} ===")
            response = client.delete_user(args.username)
            client.pretty_print_response(response)
            return
            
        # API key management
        if args.create_apikey:
            if not args.apikey_name:
                print("Error: API key name is required")
                return
                
            roles = None
            if args.apikey_roles:
                roles = [role.strip() for role in args.apikey_roles.split(",")]
                
            print(f"\n=== CREATING API KEY: {args.apikey_name} ===")
            response = client.create_api_key(args.apikey_name, args.description or "", roles)
            client.pretty_print_response(response)
            return
            
        # Notification management
        if args.create_notification:
            if not args.title or not args.subject or not args.message:
                print("Error: Title, subject, and message are required for creating a notification")
                return
                
            print(f"\n=== CREATING NOTIFICATION: {args.title} ===")
            response = client.create_notification(args.title, args.subject, args.message, 
                                              args.importance, args.link)
            client.pretty_print_response(response)
            return
            
        if args.archive_notification:
            print(f"\n=== ARCHIVING NOTIFICATION: {args.archive_notification} ===")
            response = client.archive_notification(args.archive_notification)
            client.pretty_print_response(response)
            return
            
        if args.archive_all:
            print("\n=== ARCHIVING ALL NOTIFICATIONS ===")
            response = client.archive_all_notifications(args.importance if args.importance != "INFO" else None)
            client.pretty_print_response(response)
            return
            
        # Remote access configuration
        if args.setup_remote:
            if not args.access_type:
                print("Error: Access type is required for setting up remote access")
                return
                
            print(f"\n=== SETTING UP REMOTE ACCESS: {args.access_type} ===")
            response = client.setup_remote_access(args.access_type, args.forward_type, args.remote_port)
            client.pretty_print_response(response)
            return
            
        # Docker container control
        if args.start_container:
            print(f"\n=== STARTING DOCKER CONTAINER: {args.start_container} ===")
            response = client.start_docker_container(args.start_container)
            client.pretty_print_response(response)
            return
            
        if args.stop_container:
            print(f"\n=== STOPPING DOCKER CONTAINER: {args.stop_container} ===")
            response = client.stop_docker_container(args.stop_container)
            client.pretty_print_response(response)
            return
            
        if args.restart_container:
            print(f"\n=== RESTARTING DOCKER CONTAINER: {args.restart_container} ===")
            response = client.restart_docker_container(args.restart_container)
            client.pretty_print_response(response)
            return
            
        # VM control
        if args.start_vm:
            print(f"\n=== STARTING VM: {args.start_vm} ===")
            response = client.start_vm(args.start_vm)
            client.pretty_print_response(response)
            return
            
        if args.stop_vm:
            print(f"\n=== STOPPING VM: {args.stop_vm} ===")
            response = client.stop_vm(args.stop_vm, args.force_stop_vm)
            client.pretty_print_response(response)
            return
            
        if args.pause_vm:
            print(f"\n=== PAUSING VM: {args.pause_vm} ===")
            response = client.pause_vm(args.pause_vm)
            client.pretty_print_response(response)
            return
            
        if args.resume_vm:
            print(f"\n=== RESUMING VM: {args.resume_vm} ===")
            response = client.resume_vm(args.resume_vm)
            client.pretty_print_response(response)
            return
        
        # Handle custom query if provided
        if args.custom:
            print("\n=== CUSTOM QUERY RESULT ===")
            response = client.run_custom_query(args.custom)
            client.pretty_print_response(response)
            return
            
        # Execute the requested queries
        if args.query == "info" or args.query == "all":
            print("\n=== SERVER INFORMATION ===")
            response = client.get_server_info()
            client.pretty_print_response(response)
            
        if args.query == "array" or args.query == "all":
            print("\n=== ARRAY STATUS ===")
            response = client.get_array_status()
            client.pretty_print_response(response)
            
        if args.query == "docker" or args.query == "all":
            print("\n=== DOCKER CONTAINERS ===")
            response = client.get_docker_containers()
            client.pretty_print_response(response)
            
        if args.query == "disks" or args.query == "all":
            print("\n=== DISK INFORMATION ===")
            response = client.get_disks_info()
            client.pretty_print_response(response)
            
        if args.query == "network" or args.query == "all":
            print("\n=== NETWORK INFORMATION ===")
            response = client.get_network_info()
            client.pretty_print_response(response)
            
            print("\n=== DETAILED NETWORK INTERFACES ===")
            detailed_response = client.get_detailed_network_info()
            client.pretty_print_response(detailed_response)
            
        if args.query == "shares" or args.query == "all":
            print("\n=== SHARES INFORMATION ===")
            response = client.get_shares()
            client.pretty_print_response(response)
            
        if args.query == "vms" or args.query == "all":
            print("\n=== VIRTUAL MACHINES ===")
            response = client.get_vms()
            client.pretty_print_response(response)
        
        if args.query == "parity" or args.query == "all":
            print("\n=== PARITY HISTORY ===")
            response = client.get_parity_history()
            client.pretty_print_response(response)
            
        if args.query == "vars" or args.query == "all":
            print("\n=== SYSTEM VARIABLES ===")
            response = client.get_vars()
            client.pretty_print_response(response)
            
        if args.query == "users" or args.query == "all":
            print("\n=== CURRENT USER ===")
            response = client.get_users()
            client.pretty_print_response(response)
            
        if args.query == "apikeys" or args.query == "all":
            print("\n=== API KEYS ===")
            response = client.get_api_keys()
            client.pretty_print_response(response)
            
        if args.query == "notifications" or args.query == "all":
            print("\n=== NOTIFICATIONS ===")
            response = client.get_notifications()
            client.pretty_print_response(response)
            
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to the API: {e}")
    except json.JSONDecodeError:
        print("Error decoding the API response")
    except Exception as e:
        print(f"Unexpected error: {e}")

if __name__ == "__main__":
    main()