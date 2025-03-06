#\!/usr/bin/env python3
"""Test client for Unraid API."""
import asyncio
import json
import sys
import aiohttp

async def test_unraid_api(host, api_key):
    """Test connectivity and data from Unraid API."""
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "Accept": "application/json",
        "Origin": f"https://{host}",
        "Referer": f"https://{host}/dashboard",
        "Host": host
    }
    
    base_url = f"https://{host}/graphql"
    
    async with aiohttp.ClientSession() as session:
        # Try to detect redirect first
        try:
            async with session.get(
                base_url,
                allow_redirects=False,
                ssl=False
            ) as resp:
                if resp.status == 302 and 'Location' in resp.headers:
                    redirect_url = resp.headers['Location']
                    print(f"Discovered redirect URL: {redirect_url}")
                    
                    # If redirected, update URL and headers
                    base_url = redirect_url
                    domain_match = redirect_url.split('/graphql')[0]
                    if domain_match:
                        headers["Host"] = domain_match.replace('https://', '')
                        headers["Origin"] = domain_match
                        headers["Referer"] = f"{domain_match}/dashboard"
                else:
                    print("No redirect detected, using direct URL")
        except Exception as e:
            print(f"Error checking redirect: {e}")
            
        # 1. Test basic connectivity - simple online check
        print("\n1. Testing basic connectivity...")
        query = {
            "query": """
            query {
                online
            }
            """
        }
        
        try:
            async with session.post(base_url, json=query, headers=headers, ssl=False) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"Basic connectivity test: {json.dumps(data, indent=2)}")
                else:
                    text = await resp.text()
                    print(f"Failed with status {resp.status}: {text}")
        except Exception as e:
            print(f"Error testing basic connectivity: {e}")
            
        # 2. Test system info
        print("\n2. Testing system info...")
        query = {
            "query": """
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
                        temperature
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
                    temps {
                        main
                        name
                        temp
                    }
                }
            }
            """
        }
        
        try:
            async with session.post(base_url, json=query, headers=headers, ssl=False) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"System info result: {json.dumps(data, indent=2)}")
                else:
                    text = await resp.text()
                    print(f"Failed with status {resp.status}: {text}")
        except Exception as e:
            print(f"Error getting system info: {e}")
            
        # 3. Test array status
        print("\n3. Testing array status...")
        query = {
            "query": """
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
        }
        
        try:
            async with session.post(base_url, json=query, headers=headers, ssl=False) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    # Show compact version of disk info for readability
                    if 'data' in data and 'array' in data['data']:
                        array_data = data['data']['array']
                        # Extract disk temperatures for checking
                        for disk_type in ['disks', 'parities', 'caches']:
                            if disk_type in array_data:
                                for disk in array_data[disk_type]:
                                    print(f"Disk: {disk.get('name')} - Temp: {disk.get('temp')} - Status: {disk.get('status')}")
                        
                        print(f"Array state: {array_data.get('state')}")
                        print(f"Capacity: {array_data.get('capacity', {}).get('kilobytes', {})}")
                    else:
                        print(f"Full array result: {json.dumps(data, indent=2)}")
                else:
                    text = await resp.text()
                    print(f"Failed with status {resp.status}: {text}")
        except Exception as e:
            print(f"Error getting array status: {e}")
            
        # 4. Test Docker containers
        print("\n4. Testing docker containers...")
        query = {
            "query": """
            query {
                docker {
                    containers {
                        id
                        names
                        image
                        state
                        status
                    }
                }
            }
            """
        }
        
        try:
            async with session.post(base_url, json=query, headers=headers, ssl=False) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if 'data' in data and 'docker' in data['data'] and 'containers' in data['data']['docker']:
                        containers = data['data']['docker']['containers']
                        print(f"Found {len(containers)} containers")
                        for container in containers[:3]:  # Just show first 3 for brevity
                            print(f"Container: {container.get('names', [''])[0]} - State: {container.get('state')}")
                    else:
                        print(f"Full docker result: {json.dumps(data, indent=2)}")
                else:
                    text = await resp.text()
                    print(f"Failed with status {resp.status}: {text}")
        except Exception as e:
            print(f"Error getting docker containers: {e}")
            
        # 5. Test VM status
        print("\n5. Testing VMs...")
        query = {
            "query": """
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
        }
        
        try:
            async with session.post(base_url, json=query, headers=headers, ssl=False) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"VM result: {json.dumps(data, indent=2)}")
                else:
                    text = await resp.text()
                    print(f"Failed with status {resp.status}: {text}")
        except Exception as e:
            print(f"Error getting VMs: {e}")

if __name__ == "__main__":
    if len(sys.argv) \!= 3:
        print("Usage: python unraid_api_client.py <host> <api_key>")
        sys.exit(1)
        
    host = sys.argv[1]
    api_key = sys.argv[2]
    
    asyncio.run(test_unraid_api(host, api_key))
