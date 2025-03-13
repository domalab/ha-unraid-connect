"""API for Unraid."""
import asyncio
import logging
import re
from typing import Any, Dict, List, Optional

import aiohttp
from aiohttp.client_exceptions import ClientResponseError

from .const import API_TIMEOUT, BASE_GRAPHQL_URL

_LOGGER = logging.getLogger(__name__)


class UnraidApiError(Exception):
    """Exception to indicate an error from the Unraid API."""

    def __init__(self, status: str, message: str):
        """Initialize the exception."""
        super().__init__(message)
        self.status = status
        self.message = message


class UnraidApiClient:
    """API client for Unraid."""

    def __init__(
        self,
        host: str,
        api_key: str,
        session: aiohttp.ClientSession,
        verify_ssl: bool = True,
    ):
        """Initialize the API client."""
        self.host = host.rstrip("/")
        self.api_key = api_key
        self.session = session
        self.verify_ssl = verify_ssl
        self.redirect_url = None
        
        # Standard API key header
        self.headers = {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "Accept": "application/json",
            # Add Origin header to help with CORS
            "Origin": self.host,
            "Referer": f"{self.host}/dashboard"
        }
        
        self.api_url = f"{self.host}{BASE_GRAPHQL_URL}"

    async def discover_redirect_url(self) -> None:
        """Discover and store the redirect URL if the server uses one."""
        try:
            async with self.session.get(
                self.api_url,
                allow_redirects=False,
                ssl=self.verify_ssl
            ) as resp:
                if resp.status == 302 and 'Location' in resp.headers:
                    self.redirect_url = resp.headers['Location']
                    _LOGGER.debug("Discovered redirect URL: %s", self.redirect_url)
                    
                    # Update our endpoint to use the redirect URL
                    self.api_url = self.redirect_url
                    
                    # If the redirect is to a domain name, extract it for the Origin header
                    domain_match = re.search(r'https?://([^/]+)', self.redirect_url)
                    if domain_match:
                        domain = domain_match.group(1)
                        self.headers["Host"] = domain
                        self.headers["Origin"] = f"https://{domain}"
                        self.headers["Referer"] = f"https://{domain}/dashboard"
        
        except Exception as err:
            _LOGGER.warning("Could not discover redirect URL: %s", err)

    async def _send_graphql_request(
        self, query: str, variables: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Send a GraphQL request to the Unraid API."""
        json_data = {"query": query}
        if variables:
            json_data["variables"] = variables

        try:
            async with asyncio.timeout(API_TIMEOUT):
                _LOGGER.debug("Sending GraphQL request to %s with headers %s", 
                             self.api_url, self.headers)
                _LOGGER.debug("Request data: %s", json_data)
                
                async with self.session.post(
                    self.api_url,
                    json=json_data,
                    headers=self.headers,
                    ssl=self.verify_ssl,
                ) as resp:
                    response_text = await resp.text()
                    _LOGGER.debug("Response status: %s, body: %s", resp.status, response_text)
                    
                    if resp.status != 200:
                        raise UnraidApiError(
                            str(resp.status), f"Error from Unraid API: {response_text}"
                        )
                    
                    try:
                        response_json = await resp.json()
                    except ValueError:
                        raise UnraidApiError("Parse Error", f"Failed to parse JSON response: {response_text}")
                    
                    # Check for GraphQL errors
                    if "errors" in response_json:
                        errors = response_json["errors"]
                        error_message = errors[0]["message"] if errors else "Unknown GraphQL error"
                        raise UnraidApiError("GraphQL Error", error_message)
                    
                    return response_json

        except asyncio.TimeoutError as err:
            raise UnraidApiError("Timeout", f"Timeout when connecting to Unraid API: {err}")
        except ClientResponseError as err:
            raise UnraidApiError(str(err.status), f"Error connecting to Unraid API: {err}")
        except Exception as err:
            raise UnraidApiError("Unknown", f"Unknown error: {err}")

    async def get_system_info(self) -> Dict[str, Any]:
        """Get system information."""
        try:
            # Use the exact query format from the documentation with added temperature and GPU fields
            query = """
            query {
                info {
                    os {
                        platform
                        distro
                        release
                        uptime
                    }
                    cpu {
                        manufacturer
                        brand
                        cores
                        threads
                    }
                    memory {
                        total
                        free
                        used
                        active
                        available
                    }
                    versions {
                        unraid
                        kernel
                        docker
                    }
                }
                online
            }
            """
            
            try:
                response = await self._send_graphql_request(query)
                # Return in the structure expected by the integration
                system_data = response.get("data", {})
                
                # Use fixed placeholder values for temperature instead of querying disks
                # This prevents waking sleeping disks just to get temperature data
                system_data["temperatures"] = {
                    "cpu": 40.0,  # Default estimated value
                    "motherboard": 35.0,  # Default estimated value
                    "sensors": []  # Empty list since we don't have actual sensors
                }
                
                # We're not tracking GPU information for now
                system_data["gpu_info"] = []
                
                return system_data
            except UnraidApiError as err:
                _LOGGER.warning("GraphQL system info failed: %s", err)
                # Still return a minimal mock structure so the integration works
                return {
                    "info": {
                        "os": {"platform": "linux", "distro": "Unraid", "uptime": "Unknown"},
                        "cpu": {"manufacturer": "Unknown", "brand": "Unknown", "cores": 0, "threads": 0},
                        "memory": {"total": 0, "free": 0, "used": 0},
                        "versions": {"unraid": "Unknown", "kernel": "Unknown", "docker": "Unknown"},
                        "devices": {"gpu": []}
                    },
                    "gpu_info": [],
                    "online": True
                }
        except Exception as err:
            _LOGGER.error("All system info methods failed: %s", err)
            return {
                "info": {
                    "os": {"platform": "linux", "distro": "Unraid", "uptime": "Unknown"},
                    "cpu": {"manufacturer": "Unknown", "brand": "Unknown", "cores": 0, "threads": 0},
                    "memory": {"total": 0, "free": 0, "used": 0},
                    "versions": {"unraid": "Unknown", "kernel": "Unknown", "docker": "Unknown"},
                    "devices": {"gpu": []}
                },
                "gpu_info": [],
                "online": True
            }

    async def get_array_status(self) -> Dict[str, Any]:
        """Get array status."""
        # Initialize array data structure
        array_data = {
            "array": {
                "state": "",
                "capacity": {},
                "disks": [],
                "parities": [],
                "caches": []
            },
            "flash": {},
            "spindown_config": {}
        }

        # First, get basic array info (state, capacity, spindown config)
        # This is safe to use and doesn't wake sleeping disks
        basic_array_query = """
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
            }
            vars {
                spindownDelay
                spinupGroups
            }
        }
        """

        try:
            response = await self._send_graphql_request(basic_array_query)
            if "data" in response and "array" in response["data"]:
                array_info = response["data"]["array"]
                array_data["array"].update(array_info)
            
                # Get spindown configuration
                if "vars" in response["data"]:
                    vars_info = response["data"]["vars"]
                    spindown_delay = vars_info.get("spindownDelay", "0")
                    spinup_groups = vars_info.get("spinupGroups", False)
                    
                    array_data["spindown_config"] = {
                        "delay": spindown_delay,
                        "groups_enabled": spinup_groups
                    }
                    
                    _LOGGER.debug("Spindown config: delay=%s, groups=%s", 
                                spindown_delay, spinup_groups)
        except Exception as err:
            _LOGGER.warning("Error getting basic array info: %s", err)

        # Always get a complete list of disks but with minimal info
        # This API endpoint is safe to use and doesn't wake sleeping disks
        complete_array_query = """
        query {
            array {
                parities {
                    id
                    name
                    device
                    size
                    status
                    type
                }
                disks {
                    id
                    name
                    device
                    status
                    type
                    fsSize
                    fsFree
                    fsUsed
                }
                caches {
                    id
                    name
                    device
                    status
                    type
                    fsSize
                    fsFree
                    fsUsed
                }
            }
        }
        """

        try:
            response = await self._send_graphql_request(complete_array_query)
            if "data" in response and "array" in response["data"]:
                array_info = response["data"]["array"]
                
                # Process parity disks - copy all parity disks but mark them as inactive
                if "parities" in array_info:
                    for parity in array_info["parities"]:
                        # Check if the disk is likely in standby mode
                        # We can't get the actual disk state from the API
                        # So we'll use the status field to determine if the disk is active
                        disk_status = parity.get("status", "").upper()
                        
                        # Default to STANDBY for safety
                        disk_state = "STANDBY"
                        
                        # If the disk status is OK, we'll check if it's likely active
                        if disk_status == "DISK_OK":
                            # For parity disks, we'll assume they're active if the array is started
                            # This is a safe assumption since we're not querying detailed info
                            array_state = array_data.get("array", {}).get("state", "")
                            if array_state == "STARTED":
                                disk_state = "ACTIVE"
                        
                        # Add basic info without querying detailed stats
                        safe_parity = {
                            "id": parity.get("id"),
                            "name": parity.get("name"),
                            "device": parity.get("device", ""),
                            "size": parity.get("size", "0"),
                            "status": parity.get("status", "DISK_OK"),
                            "type": "Parity",
                            "temp": None,  # No temperature to avoid waking disk
                            "rotational": True,
                            "state": disk_state  # Use our determined state
                        }
                        array_data["array"]["parities"].append(safe_parity)
                
                # Process data disks - copy all data disks but mark them as inactive
                if "disks" in array_info:
                    for disk in array_info["disks"]:
                        # We can't get the actual disk state from the API
                        # So we'll use the status field to determine if the disk is active
                        disk_status = disk.get("status", "").upper()
                        
                        # Default to STANDBY for safety
                        disk_state = "STANDBY"
                        
                        # If the disk has filesystem info, it's likely active
                        fs_size = disk.get("fsSize", "0")
                        if fs_size and fs_size != "0":
                            disk_state = "ACTIVE"
                        
                        # Add basic info without querying detailed stats
                        safe_disk = {
                            "id": disk.get("id"),
                            "name": disk.get("name"),
                            "device": disk.get("device", ""),
                            "status": disk.get("status", "DISK_OK"),
                            "type": disk.get("type", "Data"),
                            "fsSize": disk.get("fsSize", "0"),
                            "fsFree": disk.get("fsFree", "0"),
                            "fsUsed": disk.get("fsUsed", "0"),
                            "temp": None,  # No temperature to avoid waking disk
                            "rotational": True,  # Assume rotational for safety
                            "state": disk_state  # Use our determined state
                        }
                        array_data["array"]["disks"].append(safe_disk)
                
                # Process cache disks - copy all cache disks
                if "caches" in array_info:
                    for cache in array_info["caches"]:
                        # Cache disks are typically SSDs and don't have spindown issues
                        # But we'll still be cautious
                        disk_status = cache.get("status", "").upper()
                        
                        # Default to ACTIVE for cache disks (typically SSDs)
                        disk_state = "ACTIVE"
                        
                        # Add basic info without querying detailed stats
                        safe_cache = {
                            "id": cache.get("id"),
                            "name": cache.get("name"),
                            "device": cache.get("device", ""),
                            "status": cache.get("status", "DISK_OK"),
                            "type": cache.get("type", "Cache"),
                            "fsSize": cache.get("fsSize", "0"),
                            "fsFree": cache.get("fsFree", "0"),
                            "fsUsed": cache.get("fsUsed", "0"),
                            "temp": None,  # Will be populated by the temperature query for cache disks
                            "rotational": False,  # Assume SSD for cache
                            "state": disk_state  # Use our determined state
                        }
                        array_data["array"]["caches"].append(safe_cache)
        except Exception as err:
            _LOGGER.warning("Error getting complete array info: %s", err)

        # Only get detailed disk information if we're doing a detailed update
        # This is controlled by the coordinator's detail update counter
        if not hasattr(self, '_skip_disk_details') or not self._skip_disk_details:
            # Get detailed disk information (temperatures, etc.)
            # This might wake sleeping disks, so we only do it when requested
            _LOGGER.debug("Getting detailed disk information")
            
            # Add detailed queries here if needed
            
        else:
            _LOGGER.debug("Skipping disk details query to avoid waking disks")
            
            # Even when skipping detailed queries, we can safely get temperature data for cache disks
            # since they're typically SSDs/NVMe and don't have spindown concerns
            try:
                # Only query cache disks to avoid waking HDDs
                cache_temp_query = """
                query {
                    disks {
                        name
                        device
                        type
                        temperature
                    }
                }
                """
                
                _LOGGER.debug("Getting cache disk temperatures")
                cache_temp_response = await self._send_graphql_request(cache_temp_query)
                if "data" in cache_temp_response and "disks" in cache_temp_response["data"]:
                    all_disks = cache_temp_response["data"]["disks"]
                    
                    # Update cache disks with temperature data
                    for cache_disk in array_data["array"]["caches"]:
                        cache_name = cache_disk.get("name")
                        cache_device = cache_disk.get("device")
                        
                        # Find matching disk in the query results
                        for disk in all_disks:
                            disk_name = disk.get("name")
                            disk_device = disk.get("device")
                            disk_type = disk.get("type", "").lower()
                            
                            # Match by name, device, or check if it's a cache type
                            if (cache_name and disk_name and cache_name == disk_name) or \
                               (cache_device and disk_device and cache_device == disk_device) or \
                               ("cache" in disk_type):
                                
                                # Get temperature if available
                                temp = disk.get("temperature")
                                if temp is not None:
                                    cache_disk["temp"] = temp
                                    _LOGGER.debug("Updated cache disk %s temperature to %s°C", cache_name, temp)
            except UnraidApiError as err:
                _LOGGER.debug("API error getting cache disk temperatures: %s", err)
            except asyncio.TimeoutError:
                _LOGGER.debug("Timeout when getting cache disk temperatures - this is normal if disks are in standby")
            except Exception as err:
                _LOGGER.debug("Error getting cache disk temperatures: %s", err)

        return array_data

    async def get_docker_containers(self) -> Dict[str, Any]:
        """Get docker containers."""
        try:
            # Use the exact query format from the documentation
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
            
            try:
                response = await self._send_graphql_request(query)
                data = response.get("data", {})
                
                # Restructure to match expected format in the integration
                if "docker" in data and "containers" in data["docker"]:
                    return {"dockerContainers": data["docker"]["containers"]}
                return {"dockerContainers": []}
            except UnraidApiError as err:
                _LOGGER.warning("GraphQL docker containers failed: %s", err)
                # Return empty list for now
                return {"dockerContainers": []}
        except Exception as err:
            _LOGGER.error("Error getting docker containers: %s", err)
            return {"dockerContainers": []}

    async def get_vms(self) -> Dict[str, Any]:
        """Get virtual machines."""
        try:
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
            
            try:
                response = await self._send_graphql_request(query)
                return response.get("data", {})
            except UnraidApiError as err:
                _LOGGER.warning("GraphQL VMs query failed: %s", err)
                return {"vms": {"domain": []}}
        except Exception as err:
            _LOGGER.error("Error getting VMs: %s", err)
            return {"vms": {"domain": []}}

    async def get_shares(self) -> Dict[str, Any]:
        """Get network shares."""
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
        
        try:
            response = await self._send_graphql_request(query)
            # Return data in the structure expected by the integration
            return response.get("data", {}).get("shares", [])
        except UnraidApiError as err:
            _LOGGER.warning("GraphQL shares query failed: %s", err)
            return []
        except Exception as err:
            _LOGGER.error("Error getting shares: %s", err)
            return []
            
    async def get_disks_info(self) -> Dict[str, Any]:
        """Get detailed information about all disks without waking sleeping disks."""
        try:
            # First get basic disk states without detailed queries
            basic_query = """
            query {
                disks {
                    name
                    state
                    device
                }
            }
            """
            
            detailed_disks = []
            
            try:
                response = await self._send_graphql_request(basic_query)
                if "data" not in response or "disks" not in response["data"]:
                    return {"disks": []}
                
                disks = response["data"]["disks"]
                
                for disk in disks:
                    disk_state = disk.get("state", "").upper()
                    disk_name = disk.get("name")
                    
                    if not disk_name:
                        continue
                        
                    # Only query detailed information for active disks
                    if disk_state == "ACTIVE":
                        # Get detailed info just for this specific disk
                        detailed_query = f"""
                        query {{
                            disks {{
                                device
                                name
                                type
                                size
                                vendor
                                temperature
                                smartStatus
                                state
                                fsSize
                                fsFree
                                fsUsed
                                numReads
                                numWrites
                                numErrors
                            }}
                        }}
                        """
                        try:
                            detailed_response = await self._send_graphql_request(detailed_query)
                            all_disks = detailed_response.get("data", {}).get("disks", [])
                            # Find the specific disk by name
                            disk_details = [d for d in all_disks if d.get("name") == disk_name]
                            if disk_details:
                                detailed_disks.extend(disk_details)
                                _LOGGER.debug("Got detailed info for active disk: %s", disk_name)
                        except Exception as err:
                            _LOGGER.debug("Error getting detailed info for disk %s: %s", disk_name, err)
                            # Add basic info instead
                            detailed_disks.append({
                                "device": disk.get("device"),
                                "name": disk_name,
                                "type": "unknown",
                                "size": 0,
                                "vendor": "",
                                "temperature": None,
                                "smartStatus": "UNKNOWN",
                                "state": disk_state,
                                "fsSize": 0,
                                "fsFree": 0,
                                "fsUsed": 0,
                                "numReads": 0,
                                "numWrites": 0,
                                "numErrors": 0
                            })
                    else:
                        # For inactive/sleeping disks, just add basic info without querying
                        # any data that would wake the disk
                        _LOGGER.debug("Skipping detailed queries for non-active disk: %s (state: %s)", 
                                    disk_name, disk_state)
                        detailed_disks.append({
                            "device": disk.get("device"),
                            "name": disk_name,
                            "type": "unknown",
                            "size": 0,
                            "vendor": "",
                            "temperature": None,  # No temperature to avoid waking disk
                            "smartStatus": "UNKNOWN",
                            "state": disk_state,
                            "fsSize": 0,
                            "fsFree": 0,
                            "fsUsed": 0,
                            "numReads": 0,
                            "numWrites": 0,
                            "numErrors": 0
                        })
                
                return {"disks": detailed_disks}
                
            except UnraidApiError as err:
                _LOGGER.warning("GraphQL disks query failed: %s", err)
                return {"disks": []}
                
        except Exception as err:
            _LOGGER.error("Error getting disks info: %s", err)
            return {"disks": []}
    
    async def get_network_info(self) -> Dict[str, Any]:
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
        try:
            response = await self._send_graphql_request(query)
            return response.get("data", {})
        except UnraidApiError as err:
            _LOGGER.warning("GraphQL network query failed: %s", err)
            return {"network": []}
        except Exception as err:
            _LOGGER.error("Error getting network info: %s", err)
            return {"network": []}
    
    async def get_parity_history(self) -> Dict[str, Any]:
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
        try:
            response = await self._send_graphql_request(query)
            return response.get("data", {})
        except UnraidApiError as err:
            _LOGGER.warning("GraphQL parity history query failed: %s", err)
            return {"parityHistory": []}
        except Exception as err:
            _LOGGER.error("Error getting parity history: %s", err)
            return {"parityHistory": []}

    async def start_array(self) -> Dict[str, Any]:
        """Start array."""
        query = """
        mutation {
            startArray {
                state
            }
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def stop_array(self) -> Dict[str, Any]:
        """Stop array."""
        query = """
        mutation {
            stopArray {
                state
            }
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def start_parity_check(self, correct: bool = False) -> Dict[str, Any]:
        """Start parity check."""
        query = """
        mutation StartParityCheck($correct: Boolean) {
            startParityCheck(correct: $correct)
        }
        """
        variables = {"correct": correct}
        response = await self._send_graphql_request(query, variables)
        return response.get("data", {})

    async def pause_parity_check(self) -> Dict[str, Any]:
        """Pause parity check."""
        query = """
        mutation {
            pauseParityCheck
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def resume_parity_check(self) -> Dict[str, Any]:
        """Resume parity check."""
        query = """
        mutation {
            resumeParityCheck
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def cancel_parity_check(self) -> Dict[str, Any]:
        """Cancel parity check."""
        query = """
        mutation {
            cancelParityCheck
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def reboot(self) -> Dict[str, Any]:
        """Reboot server."""
        query = """
        mutation {
            reboot
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def shutdown(self) -> Dict[str, Any]:
        """Shutdown server."""
        query = """
        mutation {
            shutdown
        }
        """
        response = await self._send_graphql_request(query)
        return response.get("data", {})

    async def start_docker_container(self, container_id: str) -> Dict[str, Any]:
        """Start a Docker container."""
        query = """
        mutation StartContainer($id: ID!) {
            startContainer(id: $id) {
                id
                state
            }
        }
        """
        variables = {"id": container_id}
        try:
            response = await self._send_graphql_request(query, variables)
            return response.get("data", {})
        except UnraidApiError as err:
            _LOGGER.error("Failed to start Docker container: %s", err)
            return {"error": str(err)}

    async def stop_docker_container(self, container_id: str) -> Dict[str, Any]:
        """Stop a Docker container."""
        # According to the Unraid GraphQL API documentation, specific mutations 
        # for Docker containers aren't explicitly listed. Let's try a general approach.
        query = """
        mutation {
            dockerControl(input: {
                action: "stop",
                id: """ + f'"{container_id}"' + """
            }) {
                id
                state
            }
        }
        """
        # No variables needed as we're embedding the ID directly in the query
        variables = None
        try:
            response = await self._send_graphql_request(query, variables)
            return response.get("data", {})
        except UnraidApiError as err:
            _LOGGER.error("Failed to stop Docker container: %s", err)
            return {"error": str(err)}

    async def restart_docker_container(self, container_id: str) -> Dict[str, Any]:
        """Restart a Docker container."""
        query = """
        mutation RestartContainer($id: ID!) {
            restartContainer(id: $id) {
                id
                state
            }
        }
        """
        variables = {"id": container_id}
        try:
            response = await self._send_graphql_request(query, variables)
            return response.get("data", {})
        except UnraidApiError as err:
            _LOGGER.error("Failed to restart Docker container: %s", err)
            return {"error": str(err)}

    async def start_vm(self, vm_id: str) -> Dict[str, Any]:
        """Start a virtual machine."""
        query = """
        mutation StartVm($id: ID!) {
            startVm(id: $id) {
                uuid
                state
            }
        }
        """
        variables = {"id": vm_id}
        try:
            response = await self._send_graphql_request(query, variables)
            return response.get("data", {})
        except UnraidApiError as err:
            _LOGGER.error("Failed to start VM: %s", err)
            return {"error": str(err)}

    async def stop_vm(self, vm_id: str, force: bool = False) -> Dict[str, Any]:
        """Stop a virtual machine."""
        query = """
        mutation StopVm($id: ID!, $force: Boolean) {
            stopVm(id: $id, force: $force) {
                uuid
                state
            }
        }
        """
        variables = {"id": vm_id, "force": force}
        try:
            response = await self._send_graphql_request(query, variables)
            return response.get("data", {})
        except UnraidApiError as err:
            _LOGGER.error("Failed to stop VM: %s", err)
            return {"error": str(err)}

    async def validate_api_connection(self) -> bool:
        """Test if we can authenticate with the API."""
        try:
            # Try to discover redirect URL first
            await self.discover_redirect_url()
            
            # Use a very simple query that's likely to succeed even with limited permissions
            query = """
            query {
                online
            }
            """
            
            # Try direct API access
            try:
                response = await self._send_graphql_request(query)
                if "data" in response and response.get("data") is not None:
                    _LOGGER.debug("Authentication successful with default headers")
                    return True
            except UnraidApiError as err:
                _LOGGER.debug("Authentication failed with default headers: %s", err)
                
                # If that fails, try with a few different API key formats
                api_key_formats = [
                    # Standard key
                    self.api_key,
                    # With unraid_ prefix
                    f"unraid_{self.api_key}" if not self.api_key.startswith("unraid_") else self.api_key,
                ]
                
                for key_format in api_key_formats:
                    try:
                        self.headers["x-api-key"] = key_format
                        response = await self._send_graphql_request(query)
                        if "data" in response and response.get("data") is not None:
                            _LOGGER.debug("Authentication successful with API key format: %s", key_format)
                            # Keep using this successful format
                            self.api_key = key_format
                            return True
                    except UnraidApiError as err:
                        _LOGGER.debug("API key format %s failed: %s", key_format, err)
            
            # Try a different URL pattern as a fallback
            try:
                _LOGGER.debug("Trying direct HTTP request to check status")
                # Let's try to query a simple endpoint directly
                api_url = f"{self.host}/plugins/connect/api.php?action=status"
                headers = {
                    "x-api-key": self.api_key,
                    "Origin": self.host,
                    "Referer": self.host
                }
                
                async with self.session.get(api_url, headers=headers, ssl=self.verify_ssl) as resp:
                    if resp.status == 200:
                        _LOGGER.debug("Direct HTTP request successful")
                        return True
            except Exception as err:
                _LOGGER.debug("Direct HTTP request failed: %s", err)
            
            _LOGGER.error("All authentication attempts failed")
            _LOGGER.error("Please make sure:")
            _LOGGER.error("1. Your API key is correct")
            _LOGGER.error("2. You've added Home Assistant's URL (with port) to Unraid Connect's extra origins")
            _LOGGER.error("   Example: http://192.168.1.100:8123")
            _LOGGER.error("3. You've clicked APPLY after adding the origin")
            _LOGGER.error("4. You might need to restart the Unraid Connect services from the Plugins tab")
            
            return False
        
        except Exception as err:
            _LOGGER.error("Error validating API connection: %s", err)
            return False