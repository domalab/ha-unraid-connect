#!/usr/bin/env python3
"""Standalone test script for Unraid GraphQL API."""
import asyncio
import json
import logging
import re

import aiohttp

logging.basicConfig(level=logging.DEBUG)
_LOGGER = logging.getLogger(__name__)

API_TIMEOUT = 10

class UnraidApiError(Exception):
    """Exception to indicate an error from the Unraid API."""
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message

async def send_graphql_request(session, url, headers, query, variables=None):
    """Send a GraphQL request."""
    json_data = {"query": query}
    if variables:
        json_data["variables"] = variables
    
    try:
        async with session.post(
            url,
            json=json_data,
            headers=headers,
            ssl=False,
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
    except Exception as err:
        raise UnraidApiError("Unknown", f"Error: {err}")

async def main():
    """Main function."""
    # Configuration
    host = "192.168.20.21"
    api_key = "d19cc212ffe54c88397398237f87791e75e8161e9d78c41509910ceb8f07e688"
    api_url = f"http://{host}/graphql"
    
    # Standard API key header - without Origin to avoid CORS issues
    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "Accept": "application/json"
    }
    
    # Create session
    async with aiohttp.ClientSession() as session:
        # Test connection
        try:
            query = """
            query {
                online
            }
            """
            response = await send_graphql_request(session, api_url, headers, query)
            print("CONNECTION TEST:")
            print(json.dumps(response, indent=2))
            
            # System info
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
            response = await send_graphql_request(session, api_url, headers, query)
            print("\nSYSTEM INFO:")
            print(json.dumps(response, indent=2))
            
            # Try to get CPU temperature
            query = """
            query {
                info {
                    cpu {
                        temperature
                        manufacturer
                        brand
                        cores
                        threads
                    }
                }
            }
            """
            try:
                response = await send_graphql_request(session, api_url, headers, query)
                print("\nCPU TEMPERATURE QUERY:")
                print(json.dumps(response, indent=2))
            except Exception as e:
                print(f"Error retrieving CPU temperature: {e}")
            
            # Let's try to query temperatures endpoint
            query = """
            query {
                temperatures {
                    main
                    cpu
                    motherboard
                    sensors {
                        adapter
                        name
                        value
                    }
                }
            }
            """
            try:
                response = await send_graphql_request(session, api_url, headers, query)
                print("\nTEMPERATURES QUERY:")
                print(json.dumps(response, indent=2))
            except Exception as e:
                print(f"Error retrieving temperatures: {e}")
            
            # Try with a different query format for temperatures
            query = """
            query {
                system {
                    temperatures {
                        main
                        cpu
                        motherboard
                    }
                }
            }
            """
            try:
                response = await send_graphql_request(session, api_url, headers, query)
                print("\nSYSTEM TEMPERATURES QUERY:")
                print(json.dumps(response, indent=2))
            except Exception as e:
                print(f"Error retrieving system temperatures: {e}")
                
            # Let's try to get the full schema to see what's available
            query = """
            query {
                __schema {
                    types {
                        name
                        fields {
                            name
                        }
                    }
                }
            }
            """
            try:
                response = await send_graphql_request(session, api_url, headers, query)
                print("\nSCHEMA QUERY:")
                # Find types that might contain UPS or temperature info
                for type_info in response.get("data", {}).get("__schema", {}).get("types", []):
                    if type_info.get("fields") and any(
                        field.get("name") and (
                            "ups" in field.get("name").lower() or 
                            "temp" in field.get("name").lower() or 
                            "cpu" in field.get("name").lower() or
                            "motherboard" in field.get("name").lower() or
                            "power" in field.get("name").lower() or
                            "battery" in field.get("name").lower()
                        )
                        for field in type_info.get("fields", [])
                    ):
                        print(f"Type with relevant fields: {type_info['name']}")
                        print(f"  Fields: {[field['name'] for field in type_info['fields']]}")
                
                # Try a specific UPS query to see if it exists
                try:
                    ups_query = """
                    query {
                        ups {
                            name
                            model
                            status
                            load
                            batteryCharge
                            timeLeft
                            nominalPower
                            beeper
                            testResult
                            input {
                                voltage
                                frequency
                            }
                            output {
                                voltage
                                frequency
                            }
                        }
                    }
                    """
                    print("\nTRYING UPS QUERY:")
                    ups_response = await send_graphql_request(session, api_url, headers, ups_query)
                    print(json.dumps(ups_response, indent=2))
                except Exception as ups_err:
                    print(f"UPS query failed: {ups_err}")
                    
            except Exception as e:
                print(f"Error retrieving schema: {e}")
                
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())